@echo off
:: Enable ANSI color codes in CMD
reg add HKCU\Console /v VirtualTerminalLevel /t REG_DWORD /d 1 /f >nul 2>&1

:: Quick Python check before delegating to the visual installer
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo.
    echo  [ERROR] Python is not installed or not in PATH.
    echo  Please install Python 3.10+ from https://www.python.org/downloads/
    echo  Make sure to check "Add Python to PATH" during setup.
    echo.
    pause
    exit /b 1
)

:: Hand off to the Python visual installer
python _install.py
