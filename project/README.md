# Proyecto — Emergency Control

Este proyecto implementa un planificador autónomo para una misión de control de
emergencias. El backend genera un plan válido a partir del escenario y el
frontend lo ejecuta en una simulación 3D.

El backend utiliza una búsqueda satisficiente para encontrar rápidamente una
solución válida. También conserva UCS para validar estados equivalentes, rutas
alternativas y diferencias de costo. La búsqueda satisficiente no garantiza el
menor costo, pero utiliza el costo como criterio de preferencia y aplica poda de
estados.

## Estructura

```text
project/
├── backend/           # FastAPI y agente de búsqueda
├── frontend/          # React, TypeScript, Vite y simulación 3D
├── scenarios/         # scenario.json, fuente de verdad del mundo
├── design.md          # diseño del estado, acciones y búsquedas
└── README.md          # estas instrucciones
```

## Requisitos

- Python 3.10 o posterior.
- Node.js y npm.
- Windows PowerShell, macOS Terminal o Linux Shell.

## 1. Instalar dependencias del backend

Desde la carpeta raíz del repositorio:

```powershell
cd project/backend
py -m venv .venv
.\.venv\Scripts\Activate.ps1
py -m pip install -r requirements.txt
```

En macOS o Linux:

```bash
cd project/backend
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

## 2. Iniciar el backend

Con el entorno virtual activado y ubicados en `project/backend`:

```powershell
py -m uvicorn main:app --app-dir src --reload --port 8000
```

En macOS o Linux:

```bash
python -m uvicorn main:app --app-dir src --reload --port 8000
```

Comprobar que funciona:

```text
http://127.0.0.1:8000/api/health
```

La respuesta esperada es:

```json
{"status":"ok"}
```

La documentación interactiva de FastAPI está en:

```text
http://127.0.0.1:8000/docs
```

## 3. Instalar e iniciar el frontend

Abre una segunda terminal:

```powershell
cd project/frontend
npm install
npm run dev
```

Abre la dirección mostrada por Vite, normalmente:

```text
http://localhost:5173
```

El frontend utiliza el proxy de Vite para enviar `/api/*` al backend en el
puerto `8000`. Por eso ambos procesos deben estar ejecutándose.

## 4. Ejecutar el agente directamente

Para probar el agente sin abrir el frontend:

```powershell
cd project/backend
$env:PYTHONPATH = "src"
py -c "from main import solve; from simulator import load_scenario; result=solve(load_scenario()); print(result)"
```

La respuesta debe incluir:

```text
solution_found: True
total_cost: ...
steps: [...]
```

## 5. Probar una misión

Con backend y frontend ejecutándose, abre `http://localhost:5173` y pulsa
`EXECUTE PLAN`.

El frontend solicitará un plan a `POST /api/solve`, ejecutará sus pasos y
mostrará el resultado en el registro de la interfaz.

También puedes probar la API desde PowerShell:

```powershell
$scenario = Invoke-RestMethod http://127.0.0.1:8000/api/scenario
$body = $scenario | ConvertTo-Json -Depth 20
$result = Invoke-RestMethod http://127.0.0.1:8000/api/solve -Method Post -ContentType "application/json" -Body $body
$result.solution_found
$result.total_cost
$result.steps.Count
$result.message
```

## 6. Ejecutar las pruebas del backend

Las pruebas cubren estados equivalentes, información relevante, costos
diferentes, ausencia de solución, rutas alternativas y rendimiento:

```powershell
cd project/backend
$env:PYTHONPATH = "src"
py tests/test_ucs_solver.py
```

La salida muestra cada caso y sus métricas. Debe terminar con:

```text
Resultado: todos los casos de validación UCS pasaron.
```

## 7. Interpretar el resultado

- `solution_found=True`: se encontró un plan ejecutable.
- `solution_found=False`: no se encontró una solución dentro del límite de
	búsqueda o el escenario no tiene solución.
- `total_cost`: suma de los costos oficiales de todos los pasos.
- `steps`: acciones que ejecutará el frontend.
- `message`: estrategia utilizada y cantidad de estados expandidos.

Durante la ejecución visual, el registro debe terminar con:

```text
MISSION COMPLETE — all stations ONLINE
```

También se muestran la batería restante, el costo gastado y las acciones
ejecutadas. Si aparece `API ERROR`, revisa que el backend esté activo en el
puerto `8000`. Si aparece un error de una acción, el plan fue rechazado por una
regla del simulador y el mensaje del registro indica la causa.

## Contrato visual

El plan solo utiliza estas operaciones:

```text
MOVE | PICKUP | DROP | INTERACT
```

Dentro de `INTERACT`, las acciones válidas son `OPEN_DOOR`, `REPAIR`,
`ACTIVATE` y `RECHARGE`. Las reglas completas están en
[`CONTRATO.md`](../CONTRATO.md), y el diseño del agente en
[`design.md`](design.md).
