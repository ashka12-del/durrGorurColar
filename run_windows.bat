@echo off
setlocal
cd /d "%~dp0"

set "VENV_PYTHON=.venv-windows\Scripts\python.exe"

if exist "%VENV_PYTHON%" (
  "%VENV_PYTHON%" -c "import sys" >nul 2>&1
)
if not exist "%VENV_PYTHON%" goto create_venv
if errorlevel 1 goto create_venv
goto check_dependencies

:create_venv
echo Creating the NeuroGoru Python environment...
py -3 -m venv --clear .venv-windows
if errorlevel 1 python -m venv --clear .venv-windows
if not exist "%VENV_PYTHON%" (
  echo Could not create the Python environment.
  echo Install Python 3 and enable the Python launcher, then try again.
  pause
  exit /b 1
)

:check_dependencies
"%VENV_PYTHON%" -c "import PySide6" >nul 2>&1
if errorlevel 1 (
  echo Installing NeuroGoru dependencies...
  "%VENV_PYTHON%" -m pip install -r requirements.txt
  if errorlevel 1 (
    echo Dependency installation failed.
    pause
    exit /b 1
  )
)

echo Starting NeuroGoru...
"%VENV_PYTHON%" main.py
if errorlevel 1 pause
endlocal
