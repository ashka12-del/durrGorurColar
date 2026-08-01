@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv-cpython\Scripts\python.exe" (
  echo Virtual environment not found. Install dependencies first.
  pause
  exit /b 1
)
".venv-cpython\Scripts\python.exe" main.py
endlocal

