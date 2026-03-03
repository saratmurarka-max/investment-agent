# Start Investment Agent (backend + frontend)
# Run from: investment-agent\ directory

Write-Host "Starting backend..." -ForegroundColor Cyan
Start-Process powershell -ArgumentList "-NoExit", "-Command", `
    "cd '$PSScriptRoot'; .venv\Scripts\Activate.ps1; uvicorn backend.main:app --reload --port 8000"

Write-Host "Starting frontend..." -ForegroundColor Cyan
Start-Process powershell -ArgumentList "-NoExit", "-Command", `
    "cd '$PSScriptRoot\frontend'; npm run dev"

Write-Host "Both servers starting. Open http://localhost:5173" -ForegroundColor Green
