@echo off
echo ============================================
echo   ProofLoop - Starting Application
echo ============================================
echo.

echo [1/2] Starting Backend on http://localhost:8000 ...
start "ProofLoop Backend" cmd /k "cd backend && python -m uvicorn app.main:app --reload --port 8000"

echo [2/2] Starting Frontend on http://localhost:5173 ...
start "ProofLoop Frontend" cmd /k "cd frontend && npm run dev"

echo.
echo Application started!
echo Frontend: http://localhost:5173
echo Backend:  http://localhost:8000
echo Docs:     http://localhost:8000/docs
echo.
