@echo off
echo ============================================
echo   ProofLoop - AI Task Worker
echo ============================================
echo.

REM Check if .env exists
if not exist "backend\.env" (
    echo [SETUP] Copying .env.example to backend\.env
    copy ".env.example" "backend\.env"
    echo [ACTION] Edit backend\.env and add your GEMINI_API_KEY
    echo          (or leave blank to use deterministic mode)
    echo.
)

echo [1] Installing backend dependencies...
cd backend
pip install -r requirements.txt --quiet
if errorlevel 1 (
    echo ERROR: pip install failed
    exit /b 1
)

echo [2] Seeding database...
python ..\scripts\seed_demo.py

echo.
echo ============================================
echo  Setup complete!
echo.
echo  Start the backend:
echo    cd backend
echo    uvicorn app.main:app --reload --port 8000
echo.
echo  Start the frontend (new terminal):
echo    cd frontend
echo    npm run dev
echo.
echo  Open: http://localhost:5173
echo ============================================
