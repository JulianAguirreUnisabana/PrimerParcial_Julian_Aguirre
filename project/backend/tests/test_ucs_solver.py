"""Pruebas del agente UCS y de las podas descritas en design.md."""

from __future__ import annotations

import sys
import time
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from simulator import goal_satisfied, load_scenario, simulate  # noqa: E402
from ucs_solver import State, initial_state, solve_satisficing, solve_ucs  # noqa: E402


def small_scenario(*, direct_cost: int = 20, include_middle: bool = True) -> dict:
    """Crea escenarios pequeños para probar propiedades de UCS."""

    zones = ["A", "C"]
    corridors = [
        {"from": "A", "to": "C", "cost": direct_cost, "door": None},
        {"from": "C", "to": "A", "cost": direct_cost, "door": None},
    ]
    if include_middle:
        zones.insert(1, "B")
        corridors.extend(
            [
                {"from": "A", "to": "B", "cost": 2, "door": None},
                {"from": "B", "to": "A", "cost": 2, "door": None},
                {"from": "B", "to": "C", "cost": 2, "door": None},
                {"from": "C", "to": "B", "cost": 2, "door": None},
            ]
        )
    return {
        "robot": {"start": "A", "battery_max": 100, "battery_start": 100, "cargo_capacity": 2},
        "zones": [{"id": zone, "name": zone, "recharge": False} for zone in zones],
        "corridors": corridors,
        "doors": [],
        "keys": [],
        "tools": [],
        "materials": [],
        "panels": [],
        "stations": [{"id": "TARGET", "kind": "target", "zone": "C", "state": "OFFLINE", "requires": {}}],
        "chargers": [],
        "goal": {"stations_online": ["TARGET"]},
        "action_costs": {"pickup": 1, "drop": 1, "interact": 2, "recharge": 3},
    }


def test_equivalent_states_have_same_canonical_key() -> None:
    """Caso 1: el orden de colecciones no cambia el estado lógico."""

    scenario = load_scenario()
    state = initial_state(scenario)
    equivalent = replace(
        state,
        payload=tuple(reversed(state.payload)),
        ground=tuple(reversed(state.ground)),
    )
    assert state.world_key() == equivalent.world_key()


def test_relevant_information_keeps_states_different() -> None:
    """Caso 2: cambiar batería o una puerta cambia el futuro posible."""

    scenario = load_scenario()
    state = initial_state(scenario)
    different_battery = replace(state, battery=state.battery - 1)
    different_door = replace(state, doors=(('DOOR1', 'OPEN'), ('DOOR2', 'CLOSED'), ('DOOR3', 'CLOSED')))
    assert state != different_battery
    assert state.world_key() != different_door.world_key()


def test_ucs_prefers_lower_cost_over_fewer_actions() -> None:
    """Caso 3: dos movimientos baratos vencen a un movimiento caro."""

    scenario = small_scenario(direct_cost=20)
    result = solve_ucs(scenario)
    assert result["solution_found"] is True
    assert result["total_cost"] == 6
    assert len([step for step in result["steps"] if step["op"] == "MOVE"]) == 2
    assert goal_satisfied(scenario, simulate(scenario, result["steps"]))


def test_ucs_returns_failure_when_no_solution_exists() -> None:
    """Caso 4: UCS termina y devuelve FAILURE si no hay camino a la meta."""

    scenario = small_scenario(include_middle=False)
    scenario["corridors"] = []
    result = solve_ucs(scenario, max_expansions=1000)
    assert result["solution_found"] is False
    assert result["steps"] == []
    assert result["message"].startswith("FAILURE")


def test_ucs_handles_alternative_routes() -> None:
    """Caso 5: conserva la ruta indirecta de menor costo."""

    scenario = small_scenario(direct_cost=20)
    result = solve_ucs(scenario)
    route = [(step.get("from"), step.get("to")) for step in result["steps"] if step["op"] == "MOVE"]
    assert route == [("A", "B"), ("B", "C")]
    assert result["total_cost"] == 6


def test_default_scenario_finishes_under_five_minutes() -> None:
    """El escenario completo debe validarse antes de conectarlo al frontend."""

    scenario = load_scenario()
    started = time.perf_counter()
    result = solve_satisficing(scenario)
    elapsed = time.perf_counter() - started
    print(
        f"\n  solution_found={result['solution_found']}"
        f"\n  total_cost={result['total_cost']}"
        f"\n  steps={len(result['steps'])}"
        f"\n  message={result['message']}"
        f"\n  elapsed={elapsed:.3f}s"
    )
    final = simulate(scenario, result["steps"])
    assert result["solution_found"] is True
    assert goal_satisfied(scenario, final)
    assert final["energy_spent"] == result["total_cost"]
    assert elapsed < 300


def run_case(name: str, test: callable) -> None:
    """Ejecuta un caso y muestra métricas útiles para revisar el backend."""

    started = time.perf_counter()
    test()
    elapsed = time.perf_counter() - started
    print(f"[OK] {name} | tiempo={elapsed:.3f}s")


if __name__ == "__main__":
    run_case("Caso 1 - estados equivalentes", test_equivalent_states_have_same_canonical_key)
    run_case("Caso 2 - información relevante", test_relevant_information_keeps_states_different)
    run_case("Caso 3 - costos diferentes", test_ucs_prefers_lower_cost_over_fewer_actions)
    run_case("Caso 4 - sin solución", test_ucs_returns_failure_when_no_solution_exists)
    run_case("Caso 5 - rutas alternativas", test_ucs_handles_alternative_routes)
    run_case("Rendimiento - escenario completo", test_default_scenario_finishes_under_five_minutes)
    print("Resultado: todos los casos de validación UCS pasaron.")
