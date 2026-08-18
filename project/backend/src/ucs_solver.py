"""Agente UCS para planificar la misión Emergency Control."""

from __future__ import annotations

from dataclasses import dataclass
import heapq
from itertools import count
from typing import Any, Iterator


@dataclass(frozen=True)
class State:
    """Estado físico canónico del robot y del entorno."""

    zone: str
    battery: int
    payload: tuple[str, ...]
    ground: tuple[tuple[str, str, int], ...]
    doors: tuple[tuple[str, str], ...]
    panels: tuple[tuple[str, str], ...]
    stations: tuple[tuple[str, str], ...]

    def world_key(self) -> tuple[Any, ...]:
        """Devuelve la configuración física sin batería para aplicar dominancia."""

        # El orden de las colecciones no representa una diferencia física.
        return (
            self.zone,
            tuple(sorted(self.payload)),
            tuple(sorted(self.ground)),
            tuple(sorted(self.doors)),
            tuple(sorted(self.panels)),
            tuple(sorted(self.stations)),
        )


def _mapping(values: tuple[tuple[str, str], ...]) -> dict[str, str]:
    return dict(values)


def _replace(mapping: dict[str, str]) -> tuple[tuple[str, str], ...]:
    return tuple(sorted(mapping.items()))


def _ground_mapping(state: State) -> dict[str, tuple[str, int]]:
    return {item: (zone, count) for item, zone, count in state.ground if count > 0}


def _ground_tuple(ground: dict[str, tuple[str, int]]) -> tuple[tuple[str, str, int], ...]:
    return tuple(sorted((item, zone, count) for item, (zone, count) in ground.items() if count > 0))


def initial_state(scenario: dict[str, Any]) -> State:
    """Construye el estado inicial usando únicamente datos del escenario."""

    ground: dict[str, tuple[str, int]] = {}
    for item in scenario.get("keys", []):
        ground[item["id"]] = (item["zone"], 1)
    for item in scenario.get("tools", []):
        ground[item["id"]] = (item["zone"], 1)
    for item in scenario.get("materials", []):
        ground[item["type"]] = (item["zone"], int(item["count"]))

        # Los materiales se agrupan por tipo porque las unidades del mismo tipo son equivalentes.
    return State(
        zone=scenario["robot"]["start"],
        battery=int(scenario["robot"]["battery_start"]),
        payload=(),
        ground=_ground_tuple(ground),
        doors=tuple(sorted((d["id"], d["state"]) for d in scenario.get("doors", []))),
        panels=tuple(sorted((p["id"], p["state"]) for p in scenario.get("panels", []))),
        stations=tuple(sorted((s["id"], s["state"]) for s in scenario.get("stations", []))),
    )


def _payload_weight(payload: tuple[str, ...], weights: dict[str, int]) -> int:
    return sum(weights[item] for item in payload)


def _costs(scenario: dict[str, Any]) -> dict[str, int]:
    values = scenario.get("action_costs", {})
    return {
        "pickup": int(values.get("pickup", 1)),
        "drop": int(values.get("drop", 1)),
        "interact": int(values.get("interact", 2)),
        "recharge": int(values.get("recharge", 3)),
    }


def _item_weights(scenario: dict[str, Any]) -> dict[str, int]:
    weights: dict[str, int] = {}
    for item in scenario.get("keys", []):
        weights[item["id"]] = int(item.get("weight", 1))
    for item in scenario.get("tools", []):
        weights[item["id"]] = int(item.get("weight", 1))
    for item in scenario.get("materials", []):
        weights[item["type"]] = int(item.get("weight", 1))
    return weights


def _item_locations(scenario: dict[str, Any]) -> tuple[set[str], set[str], set[str]]:
    keys = {item["id"] for item in scenario.get("keys", [])}
    tools = {item["id"] for item in scenario.get("tools", [])}
    materials = {item["type"] for item in scenario.get("materials", [])}
    return keys, tools, materials


def _future_items(scenario: dict[str, Any], state: State) -> set[str]:
    """Calcula los objetos que todavía pueden habilitar una acción futura."""

    # Una llave, herramienta o material deja de distinguir estados cuando ya no
    # puede abrir una puerta ni participar en una reparación pendiente.
    needed: set[str] = set()
    doors = _mapping(state.doors)
    needed.update(
        door["key"]
        for door in scenario.get("doors", [])
        if doors[door["id"]] == "CLOSED"
    )
    panels = _mapping(state.panels)
    for panel in scenario.get("panels", []):
        if panels[panel["id"]] == "DAMAGED":
            needed.add(panel["requires"]["tool"])
            needed.add(panel["requires"]["material"])
    return needed


def _compact_state(scenario: dict[str, Any], state: State) -> State:
    """Elimina del estado objetos del suelo que ya no pueden habilitar acciones."""

    # Esta es la poda principal: evita guardar ubicaciones de objetos muertos.
    relevant = _future_items(scenario, state)
    ground = {
        item: (zone, count)
        for item, (zone, count) in _ground_mapping(state).items()
        if item in relevant
    }
    return State(
        zone=state.zone,
        battery=state.battery,
        payload=state.payload,
        ground=_ground_tuple(ground),
        doors=state.doors,
        panels=state.panels,
        stations=state.stations,
    )


def _has_item(state: State, item: str) -> bool:
    return item in state.payload


def _move_successors(scenario: dict[str, Any], state: State, costs: dict[str, int]) -> Iterator[tuple[dict[str, Any], State]]:
    doors = _mapping(state.doors)
    for corridor in scenario.get("corridors", []):
        if corridor["from"] != state.zone:
            continue
        door = corridor.get("door")
        if door and doors.get(door) != "OPEN":
            continue
        cost = int(corridor["cost"])
        if state.battery < cost:
            continue
        next_state = State(
            zone=corridor["to"],
            battery=state.battery - cost,
            payload=state.payload,
            ground=state.ground,
            doors=state.doors,
            panels=state.panels,
            stations=state.stations,
        )
        yield {"op": "MOVE", "from": state.zone, "to": corridor["to"], "cost": cost}, next_state


def _resource_successors(scenario: dict[str, Any], state: State, costs: dict[str, int], weights: dict[str, int]) -> Iterator[tuple[dict[str, Any], State]]:
    capacity = int(scenario["robot"]["cargo_capacity"])
    ground = _ground_mapping(state)
    current_weight = _payload_weight(state.payload, weights)
    future_items = _future_items(scenario, state)

    for item, (zone, count) in ground.items():
        if zone != state.zone or count <= 0:
            continue
        # Los duplicados de materiales y los objetos ya usados no aportan progreso.
        if item not in future_items or item in state.payload:
            continue
        item_weight = weights.get(item, 1)
        if current_weight + item_weight > capacity or state.battery < costs["pickup"]:
            continue
        updated_ground = dict(ground)
        updated_ground[item] = (zone, count - 1)
        next_state = State(
            zone=state.zone,
            battery=state.battery - costs["pickup"],
            payload=tuple(sorted((*state.payload, item))),
            ground=_ground_tuple(updated_ground),
            doors=state.doors,
            panels=state.panels,
            stations=state.stations,
        )
        yield {"op": "PICKUP", "item": item, "cost": costs["pickup"]}, next_state

    # Soltar solo cuando la carga bloquea un recurso pendiente en la zona actual.
    pending_here = sum(
        weights.get(item, 1)
        for item, (zone, count) in ground.items()
        if zone == state.zone and count > 0 and item in future_items and item not in state.payload
    )
    needs_space = (
        current_weight >= capacity
        or current_weight + pending_here > capacity
    )
    if not needs_space:
        return
    for item in state.payload:
        if state.battery < costs["drop"]:
            continue
        updated_ground = dict(ground)
        old_zone, old_count = updated_ground.get(item, (state.zone, 0))
        updated_ground[item] = (state.zone, old_count + 1)
        payload = list(state.payload)
        payload.remove(item)
        next_state = State(
            zone=state.zone,
            battery=state.battery - costs["drop"],
            payload=tuple(payload),
            ground=_ground_tuple(updated_ground),
            doors=state.doors,
            panels=state.panels,
            stations=state.stations,
        )
        yield {"op": "DROP", "item": item, "cost": costs["drop"]}, next_state


def _interact_successors(scenario: dict[str, Any], state: State, costs: dict[str, int]) -> Iterator[tuple[dict[str, Any], State]]:
    if state.battery < costs["interact"]:
        return
    doors = _mapping(state.doors)
    for door in scenario.get("doors", []):
        if doors[door["id"]] != "CLOSED" or state.zone not in door["between"]:
            continue
        if not _has_item(state, door["key"]):
            continue
        updated = dict(doors)
        updated[door["id"]] = "OPEN"
        yield (
            {"op": "INTERACT", "target": door["id"], "action": "OPEN_DOOR", "cost": costs["interact"]},
            State(state.zone, state.battery - costs["interact"], state.payload, state.ground, _replace(updated), state.panels, state.stations),
        )

    panels = _mapping(state.panels)
    tools = {item["id"]: item for item in scenario.get("tools", [])}
    for panel in scenario.get("panels", []):
        requirement = panel["requires"]
        if panels[panel["id"]] != "DAMAGED" or panel["zone"] != state.zone:
            continue
        if not _has_item(state, requirement["tool"]) or not _has_item(state, requirement["material"]):
            continue
        if requirement["tool"] not in tools:
            continue
        payload = list(state.payload)
        payload.remove(requirement["material"])
        updated = dict(panels)
        updated[panel["id"]] = "OK"
        yield (
            {"op": "INTERACT", "target": panel["id"], "action": "REPAIR", "consumes": requirement["material"], "cost": costs["interact"]},
            State(state.zone, state.battery - costs["interact"], tuple(payload), state.ground, state.doors, _replace(updated), state.stations),
        )

    stations = _mapping(state.stations)
    for station in scenario.get("stations", []):
        if stations[station["id"]] != "OFFLINE" or station["zone"] != state.zone:
            continue
        required = station.get("requires", {})
        if any(panels.get(panel) != "OK" for panel in required.get("panels_ok", [])):
            continue
        if any(stations.get(other) != "ONLINE" for other in required.get("stations_online", [])):
            continue
        updated = dict(stations)
        updated[station["id"]] = "ONLINE"
        yield (
            {"op": "INTERACT", "target": station["id"], "action": "ACTIVATE", "cost": costs["interact"]},
            State(state.zone, state.battery - costs["interact"], state.payload, state.ground, state.doors, state.panels, _replace(updated)),
        )


def _recharge_successors(scenario: dict[str, Any], state: State, costs: dict[str, int]) -> Iterator[tuple[dict[str, Any], State]]:
    maximum = int(scenario["robot"]["battery_max"])
    if state.battery >= maximum or state.battery < costs["recharge"]:
        return
    for charger in scenario.get("chargers", []):
        if charger["zone"] != state.zone:
            continue
        yield (
            {"op": "INTERACT", "target": charger["id"], "action": "RECHARGE", "cost": costs["recharge"]},
            State(state.zone, maximum, state.payload, state.ground, state.doors, state.panels, state.stations),
        )


def successors(scenario: dict[str, Any], state: State) -> Iterator[tuple[dict[str, Any], State]]:
    """Genera sucesores legales y relevantes para la búsqueda."""

    # Se compacta antes y después de cada transición para que CLOSED reciba
    # siempre estados canónicos, incluso después de abrir o reparar algo.
    state = _compact_state(scenario, state)
    costs = _costs(scenario)
    weights = _item_weights(scenario)
    generators = (
        _move_successors(scenario, state, costs),
        _resource_successors(scenario, state, costs, weights),
        _interact_successors(scenario, state, costs),
        _recharge_successors(scenario, state, costs),
    )
    for generator in generators:
        for action, next_state in generator:
            yield action, _compact_state(scenario, next_state)


def _goal(scenario: dict[str, Any], state: State) -> bool:
    stations = _mapping(state.stations)
    return all(stations.get(item) == "ONLINE" for item in scenario.get("goal", {}).get("stations_online", []))


def _progress_score(scenario: dict[str, Any], state: State) -> int:
    """Ordena estados por progreso de misión; no garantiza optimalidad."""

    panels = _mapping(state.panels)
    stations = _mapping(state.stations)
    pending_panels = sum(value == "DAMAGED" for value in panels.values())
    pending_stations = sum(
        stations.get(item) != "ONLINE"
        for item in scenario.get("goal", {}).get("stations_online", [])
    )
    useful_zones: set[str] = set()
    for item, (zone, count) in _ground_mapping(state).items():
        if count > 0 and item in _future_items(scenario, state):
            useful_zones.add(zone)
    for panel in scenario.get("panels", []):
        if panels[panel["id"]] == "DAMAGED":
            useful_zones.add(panel["zone"])
    for station in scenario.get("stations", []):
        if stations[station["id"]] == "OFFLINE":
            useful_zones.add(station["zone"])
    distance_hint = 0 if state.zone in useful_zones else 5
    return pending_stations * 100 + pending_panels * 20 + distance_hint


def solve_satisficing(scenario: dict[str, Any], max_expansions: int = 200_000) -> dict[str, Any]:
    """Encuentra rápidamente una solución válida, sin prometer costo óptimo."""

    # La prioridad favorece el progreso de la misión, no el costo mínimo.
    start = initial_state(scenario)
    queue: list[tuple[int, int, int, State, tuple[dict[str, Any], ...]]] = []
    sequence = count()
    heapq.heappush(queue, (_progress_score(scenario, start), 0, next(sequence), start, ()))
    best_battery: dict[tuple[Any, ...], int] = {}
    expanded = 0

    while queue and expanded < max_expansions:
        _, cost, _, state, plan = heapq.heappop(queue)
        key = state.world_key()
        if best_battery.get(key, -1) >= state.battery:
            continue
        best_battery[key] = state.battery
        expanded += 1
        if _goal(scenario, state):
            return {
                "solution_found": True,
                "total_cost": cost,
                "steps": list(plan),
                "message": f"Búsqueda satisficiente: {expanded} estados expandidos.",
            }

        for action, next_state in successors(scenario, state):
            next_plan = (*plan, action)
            # Prioriza progreso, pero evita corredores y recargas innecesariamente caros.
            action_bonus = {"INTERACT": -30, "PICKUP": -10, "DROP": 5, "MOVE": 0}.get(action["op"], 0)
            action_cost = int(action["cost"])
            score = (
                _progress_score(scenario, next_state)
                + action_bonus
                + cost // 10
                + action_cost * 3
            )
            heapq.heappush(queue, (score, cost + int(action["cost"]), next(sequence), next_state, next_plan))

    return {
        "solution_found": False,
        "total_cost": 0,
        "steps": [],
        "message": f"FAILURE: búsqueda satisficiente agotó {expanded} estados.",
    }


def solve_ucs(scenario: dict[str, Any], max_expansions: int = 100_000) -> dict[str, Any]:
    """Encuentra el plan de menor costo mediante UCS con poda por dominancia."""

    # UCS siempre extrae el nodo de menor g(n); por eso sí puede justificar
    # optimalidad cuando termina sin alcanzar el límite de expansión.
    start = initial_state(scenario)
    queue: list[tuple[int, int, State, tuple[dict[str, Any], ...]]] = []
    sequence = count()
    heapq.heappush(queue, (0, next(sequence), start, ()))
    frontier: dict[tuple[Any, ...], list[tuple[int, int]]] = {start.world_key(): [(0, start.battery)]}
    expanded = 0

    while queue and expanded < max_expansions:
        cost, _, state, plan = heapq.heappop(queue)
        # La cola puede contener una versión antigua del mismo estado. Si otro
        # camino la domina, se descarta sin volver a expandirla.
        current_pairs = frontier.get(state.world_key(), [])
        if not any(pair_cost == cost and pair_battery == state.battery for pair_cost, pair_battery in current_pairs):
            continue
        expanded += 1
        if _goal(scenario, state):
            return {"solution_found": True, "total_cost": cost, "steps": list(plan), "message": f"UCS: {expanded} estados expandidos."}

        last_action = plan[-1] if plan else None
        for action, next_state in successors(scenario, state):
            # Un movimiento inmediatamente reversible solo gasta batería y no cambia el mundo.
            if (
                last_action
                and last_action["op"] == "MOVE"
                and action["op"] == "MOVE"
                and action["to"] == last_action.get("from")
                and action["from"] == last_action.get("to")
            ):
                continue
            next_cost = cost + int(action["cost"])
            # Para el mismo mundo, una llegada más barata con más batería domina.
            key = next_state.world_key()
            pairs = frontier.setdefault(key, [])
            if any(old_cost <= next_cost and old_battery >= next_state.battery for old_cost, old_battery in pairs):
                continue
            frontier[key] = [
                (old_cost, old_battery)
                for old_cost, old_battery in pairs
                if not (next_cost <= old_cost and next_state.battery >= old_battery)
            ] + [(next_cost, next_state.battery)]
            heapq.heappush(queue, (next_cost, next(sequence), next_state, (*plan, action)))

    message = "FAILURE" if not queue else "LIMIT_REACHED"
    return {"solution_found": False, "total_cost": 0, "steps": [], "message": f"{message}: UCS expandió {expanded} estados."}
