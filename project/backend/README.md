# Backend — Emergency Control

Python API that exposes `POST /api/solve`.

The backend exposes a fast satisficing search for the frontend and keeps UCS in
the solver module for the optimality tests. Both use canonical states and
state-pruning. The frontend plan is valid but is not guaranteed to have minimum
cost. Do not «fix» `scenario.json` (capacity, battery, rooms) to make the
search finish: formulate `Applicable` instead. See `project/design.md`.

## Run

```bash
cd project/backend
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS/Linux:
# source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload --app-dir src --port 8000
```

Or from `backend/src`:

```bash
cd project/backend/src
uvicorn main:app --reload --port 8000
```

## Tests

```powershell
cd project/backend
$env:PYTHONPATH = "src"
python tests/test_ucs_solver.py
```

The validation output reports each required case, the number of steps, cost,
expanded states and elapsed time. The frontend should only be tested after the
backend suite passes.
