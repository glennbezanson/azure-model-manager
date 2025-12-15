@echo off
REM Azure AI Model Manager Launcher
REM Ensures dependencies are available and launches the application

echo Azure AI Model Manager
echo ======================
echo.

REM Check if Python is available
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python is not installed or not in PATH
    echo Please install Python 3.9 or higher
    pause
    exit /b 1
)

REM Check if we're in the right directory
if not exist "main.py" (
    echo ERROR: main.py not found
    echo Please run this script from the azure-model-manager directory
    pause
    exit /b 1
)

REM Run the application
echo Starting application...
python main.py

if errorlevel 1 (
    echo.
    echo Application exited with an error
    pause
)
