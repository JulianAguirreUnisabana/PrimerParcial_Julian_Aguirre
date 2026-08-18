# Diseño del agente de planificación

## Descripción del archivo

Este documento describe el problema de planificación de la misión Emergency Control y define el modelo de inteligencia artificial que utilizará el backend. Primero se explica el entorno, el estado y las reglas del mundo. Después se presenta UCS como estrategia de referencia para los casos de optimalidad y una búsqueda satisficiente con poda de estados para resolver rápidamente la misión completa.

El robot debe desplazarse por varias zonas, recoger llaves, herramientas y materiales, abrir puertas, reparar paneles y activar estaciones. Cada acción tiene un costo y consume batería. La misión termina cuando todas las estaciones indicadas por el escenario están en estado `ONLINE`.

El entorno es totalmente observable, determinista, secuencial, estático, discreto y de agente único. Por esto se modela como un problema clásico de búsqueda. El backend recibe el escenario en `POST /api/solve` y devuelve un plan usando las operaciones del contrato: `MOVE`, `PICKUP`, `DROP` e `INTERACT`.

## Estado

### Definición formal

El estado físico se representa como:

```text
s = <zona, bateria, carga, suelo, puertas, paneles, estaciones>
```

- `zona`: ubicación actual del robot.
- `bateria`: energía restante.
- `carga`: objetos que transporta el robot.
- `suelo`: ubicación de llaves, herramientas y materiales que no están en la carga.
- `puertas`: estado de cada puerta, abierta o cerrada.
- `paneles`: estado de cada panel, dañado o reparado.
- `estaciones`: estado de cada estación, offline u online.

Esta información es suficiente para determinar qué acciones pueden ejecutarse y cuál sería su resultado.

### Por qué cada variable es necesaria

La zona determina qué objetos están disponibles, qué puertas puede abrir el robot, qué paneles puede reparar, qué estaciones puede operar y qué movimientos son posibles.

La batería es parte del estado porque todas las acciones tienen un costo. Dos estados iguales en todo excepto en la batería pueden tener diferentes acciones futuras disponibles.

La carga es necesaria para saber si el robot posee una llave, herramienta o material y para comprobar la capacidad de transporte.

El suelo es necesario porque el robot puede usar `DROP` y luego recoger un objeto en otra zona o en otra etapa del plan.

Las puertas, paneles y estaciones también pertenecen al estado porque sus cambios son permanentes y modifican las acciones futuras. Una puerta abierta permite cruzar un corredor, un panel reparado habilita una estación y una estación online puede ser requisito de otra.

### Qué información se deriva y no se almacena

El grafo de corredores, los costos, la capacidad de carga, la batería máxima, las dependencias y las zonas de recarga son constantes tomadas del escenario. No se repiten dentro de cada estado.

El peso de la carga se deriva sumando el peso de sus objetos. También se derivan las acciones aplicables comprobando las reglas del escenario, por ejemplo si una llave abre una puerta o si una herramienta y un material permiten reparar un panel.

### Qué pertenece al historial de búsqueda y no al estado físico

El costo acumulado `g(n)`, el padre del nodo y la acción que produjo el nodo pertenecen al historial de búsqueda. Se conservan para reconstruir el plan, pero no describen la situación física.

Si se incluyera el camino recorrido dentro del estado, dos rutas que llegan a la misma configuración se considerarían diferentes y se repetiría trabajo innecesario.

### Cuándo dos configuraciones son el mismo estado

Dos configuraciones son el mismo estado si tienen la misma zona, batería, carga, suelo y estados de puertas, paneles y estaciones. El orden en que se recogieron los objetos no cambia la situación física.

Los materiales del mismo tipo se representan mediante cantidades, no mediante identificadores artificiales. Antes de almacenarse en `CLOSED`, el estado se canonicaliza ordenando sus colecciones y usando una representación inmutable. Así, estados físicamente equivalentes tienen la misma clave de comparación.

### Relevancia: objetos que ya no cambian el futuro

Los cambios del entorno son monotónicos: las puertas no vuelven a cerrarse, los paneles reparados no vuelven a dañarse y las estaciones online no vuelven a offline.

Una llave puede dejar de ser relevante cuando su puerta ya está abierta. Una herramienta puede dejar de ser relevante cuando ya reparó el único panel que la necesitaba. Estos objetos solo se ignoran después de comprobar que no son necesarios para otra acción futura.

Esta reducción evita permutaciones de objetos muertos sin eliminar una posibilidad necesaria para un plan óptimo.

## Acciones

Las acciones internas representan operaciones del robot. Sus costos se toman siempre del escenario.

| Acción | Precondiciones | Efectos | Costo |
| --- | --- | --- | --- |
| `MOVE(from, to)` | Existe un corredor, el robot está en `from`, la puerta requerida está abierta y hay batería suficiente. | Cambia la zona a `to` y descuenta el costo del corredor. | Costo del corredor |
| `PICKUP(item)` | El objeto está en el suelo de la zona actual, hay capacidad disponible y batería suficiente. | Pasa el objeto del suelo a la carga y descuenta batería. | `action_costs.pickup` |
| `DROP(item)` | El objeto está en la carga y hay batería suficiente. | Pasa el objeto de la carga al suelo de la zona actual y descuenta batería. | `action_costs.drop` |
| `OPEN_DOOR(door)` | El robot está junto a la puerta, la puerta está cerrada y posee la llave correspondiente. | Abre la puerta y descuenta batería. | `action_costs.interact` |
| `REPAIR(panel, material)` | El robot está en la zona del panel, tiene la herramienta requerida, tiene el material correcto y el panel está dañado. | Repara el panel, consume el material y descuenta batería. | `action_costs.interact` |
| `ACTIVATE(station)` | El robot está en la zona de la estación, está offline y cumple sus dependencias. | Cambia la estación a online y descuenta batería. | `action_costs.interact` |
| `RECHARGE(charger)` | El robot está en la zona del cargador, la batería no está llena y puede pagar el costo. | Descuenta el costo y restaura la batería máxima. | `action_costs.recharge` |

Todas las acciones requieren que la batería sea mayor o igual al costo. Las acciones internas se traducen antes de responder para cumplir el contrato del frontend.

### `Applicable` interno vs legalidad del contrato

El simulador permite `DROP` en cualquier zona si el objeto está en la carga. Sin embargo, generar todos los `DROP` posibles produciría muchas ubicaciones innecesarias para los objetos.

La búsqueda genera `DROP` únicamente cuando la carga está llena o cuando un
recurso pendiente de la zona actual no cabe. No se generan drops arbitrarios en
todas las zonas.

Esta restricción es válida porque dejar un objeto en una zona sin utilidad no mejora la posición, la batería ni el progreso de la misión; solo agrega costo y crea estados adicionales.

## Modelo de transición

El modelo es determinista y parcial:

```text
s --a--> s' solamente si a pertenece a Applicable(s)
```

La transición comprueba las precondiciones, aplica los efectos y descuenta el costo de la acción. Puede cambiar la zona, la batería, la carga, la posición de objetos, las puertas, los paneles y las estaciones. El escenario y sus constantes no cambian.

Después de cada transición se canonicaliza el estado. Esto permite que la búsqueda de grafos reconozca configuraciones físicas equivalentes aunque se hayan alcanzado por historias diferentes.

La implementación también compacta el suelo después de cada transición:
elimina objetos que ya no pueden abrir puertas ni participar en reparaciones
pendientes. La carga no se elimina automáticamente porque su peso todavía puede
afectar la capacidad y debe liberarse mediante `DROP`.

## Prueba de meta

La prueba de meta se define como:

```text
Goal(s) <=> todas las estaciones de goal.stations_online están ONLINE
```

La meta se verifica sobre el estado final del mundo. Las puertas abiertas y los paneles reparados son medios para alcanzar la misión, no necesariamente condiciones finales independientes.

## Función de costo

El costo acumulado de un nodo es:

```text
g(n) = suma de los costos oficiales de las acciones desde el estado inicial hasta n
```

Los movimientos usan el costo del corredor. `PICKUP`, `DROP`, interacción y recarga usan los valores de `action_costs` del escenario.

Minimizar la cantidad de pasos no es lo mismo que minimizar el costo: un plan con menos acciones puede usar corredores caros. La solución preferida es la que alcanza la meta con menor costo total.

## Estrategia de búsqueda

### UCS con búsqueda de grafos

Se utilizará búsqueda de costo uniforme (UCS) con búsqueda de grafos. UCS es adecuada porque los costos son heterogéneos, no negativos y la misión exige una solución de menor costo.

La búsqueda mantiene:

- `OPEN`: cola de prioridad ordenada por `g(n)`.
- `CLOSED`: estados canónicos ya explorados o dominados.
- `Nodo`: estado, costo acumulado, padre y acción anterior.

Se inserta el estado inicial con costo cero. En cada iteración se extrae el nodo de menor costo, se descartan entradas obsoletas y se comprueba la meta. La meta se comprueba al extraer, porque en ese momento UCS garantiza que no existe una solución más barata pendiente en `OPEN`.

Si se encuentra la meta, se reconstruye el plan siguiendo los padres. Si `OPEN` queda vacío, se devuelve `solution_found: false` con `steps: []`.

### Búsqueda satisficiente para la integración

Para la ejecución del frontend se utiliza una búsqueda satisficiente guiada por
el progreso y el costo. Esta estrategia prioriza recoger recursos, reparar
paneles y activar estaciones, pero no garantiza el menor costo. Su objetivo es
encontrar rápidamente cualquier plan legal que alcance la meta. La prioridad
penaliza el costo acumulado y las acciones caras, especialmente movimientos y
recargas.

UCS se conserva para demostrar completitud y optimalidad en los casos de prueba
con costos y rutas alternativas. Ambas estrategias usan el mismo estado
canónico, las mismas transiciones y la misma poda de estados.

### Poda de estados y dominancia

La primera poda consiste en canonicalizar los estados. Si dos rutas alcanzan la misma situación física, no se exploran como estados diferentes.

También se aplica dominancia. Para una misma configuración de zona, carga, suelo y entorno, un estado `A` domina a otro `B` cuando:

```text
g(A) <= g(B) y bateria(A) >= bateria(B)
```

El estado `B` se elimina porque llegó con igual o mayor costo y tiene igual o menor batería. Para cada configuración se puede conservar una frontera de pares `(costo, bateria)` y descartar los pares dominados.

También se podan acciones que no generan progreso: abrir puertas abiertas, reparar paneles reparados, activar estaciones online, recargar con batería llena, recoger objetos que no caben y soltar objetos sin necesidad futura.

Estas podas reducen el factor de ramificación. Para UCS, la dominancia conserva
la posibilidad de encontrar el menor costo; para la búsqueda satisficiente, la
prioridad de costo es una preferencia práctica y no una garantía de optimalidad.

### Propiedades de UCS

UCS es completa si el espacio es finito y los costos son no negativos. Es óptima si la meta se comprueba al extraer el nodo de menor costo.

El tiempo y el espacio dependen de la cantidad de sucesores generados, no únicamente del número de zonas. `DROP`, `PICKUP` y la ubicación de objetos pueden hacer crecer mucho el espacio.

Las garantías pueden fallar si existen costos negativos, estados mal canonicalizados, una prueba de meta realizada demasiado pronto o una generación ilimitada de acciones irrelevantes.

### Batería como recurso

La batería sí forma parte del estado porque limita las acciones futuras. No se deben explorar todos los recorridos que solo gastan energía. Si dos caminos llegan a la misma configuración física y uno tiene menor o igual costo y mayor o igual batería, el otro está dominado y se elimina.

## Formulación y tamaño del espacio

### 1. Por qué el espacio puede crecer mucho

Aunque el mapa tenga pocas zonas y el robot transporte pocos objetos, cada objeto puede estar en la carga o en el suelo de diferentes zonas. Al combinar esas posiciones con la batería y los estados de puertas, paneles y estaciones, aparecen muchas configuraciones.

### 2. Papel de `DROP`

`DROP` aumenta el espacio porque cada objeto puede quedar en varias zonas. Si se generan todos los drops legales, UCS explora historias que no ayudan a la misión y puede tardar demasiado.

### 3. Podas y abstracciones

La implementación utiliza estados canónicos, equivalencia de materiales por
tipo, compactación de objetos del suelo que ya no afectan el futuro, generación
restringida de `DROP` y eliminación de estados dominados por costo y batería.

Estas decisiones son válidas porque conservan las acciones necesarias para abrir puertas, reparar paneles, recargar, activar estaciones y alcanzar la meta con menor costo.

### 4. Por qué no se modifica el escenario

No se debe aumentar la capacidad, ignorar la batería ni eliminar estaciones para hacer más fácil la instancia actual. El escenario es la fuente de verdad y el profesor puede probar otras posiciones, costos, recursos y situaciones sin solución.

La solución debe trabajar con el escenario recibido, detectar correctamente el fracaso y devolver un plan que cumpla el contrato del backend.

## Validación previa en el backend

Antes de probar la integración con el frontend se crearán tests dentro de
`backend/tests`. Estos tests validarán el agente directamente sobre el modelo
del mundo, sin depender de la interfaz visual.

Se comprobará que el agente:

- encuentre una solución legal y alcance todas las estaciones objetivo;
- devuelva `solution_found: false` cuando no exista una solución;
- respete la batería, la capacidad, las puertas, los materiales y las
	dependencias entre estaciones;
- calcule `total_cost` como la suma de los costos oficiales;
- produzca estados equivalentes de forma canónica;
- descarte estados dominados y no genere `DROP` irrelevantes;
- termine en un tiempo razonable y no explore indefinidamente estados
	repetidos.

También se medirán el tiempo de ejecución, la cantidad de estados expandidos y
el costo del plan encontrado. Primero se corregirán los problemas detectados en
estas pruebas del backend. Después se ejecutará el plan mediante el frontend
para comprobar únicamente la comunicación y la visualización de la solución.

no se puede modificar scenarios