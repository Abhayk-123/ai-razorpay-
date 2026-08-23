@echo off
setlocal
cd /d "%~dp0"

if not exist .venv\Scripts\python.exe (
  echo Creating virtualenv...
  py -m venv .venv
  .venv\Scripts\python.exe -m pip install --upgrade pip
  .venv\Scripts\python.exe -m pip install -r requirements-local.txt
)

if not exist .env (
  copy .env.example .env >nul
)

if not exist data\synthetic_failures.csv (
  .venv\Scripts\python.exe -m recoverpilot.data.generate --rows 15000
)

if not exist artifacts\recovery_model.joblib (
  .venv\Scripts\python.exe -m recoverpilot.ml.train
)

echo.
echo Starting API on http://127.0.0.1:8000 ...
start "RecoverPilot API" cmd /k ".venv\Scripts\python.exe -m uvicorn recoverpilot.api.main:app --reload --port 8000"

timeout /t 3 >nul
echo Starting recovery worker...
start "RecoverPilot Worker" cmd /k ".venv\Scripts\python.exe -m recoverpilot.workers.recovery_worker --poll 2"

timeout /t 1 >nul
echo Starting Streamlit Ops UI on http://127.0.0.1:8501 ...
start "RecoverPilot UI" cmd /k ".venv\Scripts\python.exe -m streamlit run recoverpilot\ui\app.py"

echo.
echo Open:
echo   API docs: http://127.0.0.1:8000/docs
echo   Ops UI:   http://127.0.0.1:8501
echo   Demo key: see /admin/demo-credentials or .env DEMO_API_KEY
endlocal
