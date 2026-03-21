@echo off
:: ╔══════════════════════════════════════════════════════════════╗
:: ║  InfraWatch Agent v2.3 — Build Script Windows (.exe)        ║
:: ║  Genera dos .exe:                                            ║
:: ║    1. InfraWatch-Installer.exe  — Instalador con GUI        ║
:: ║    2. iw-agent.exe              — Agente (servicio)         ║
:: ╚══════════════════════════════════════════════════════════════╝
::
:: Requisitos:
::   pip install pyinstaller psutil pywin32
::
:: Uso: build_exe.bat

setlocal enabledelayedexpansion
set "PYTHON=python"
set "DIST=dist"
set "BUILD=build"

echo.
echo [IW] InfraWatch Agent v2.3 - Build Script
echo ============================================

:: Verificar Python
%PYTHON% --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python no encontrado en PATH
    pause & exit /b 1
)
echo [OK] Python encontrado

:: Instalar dependencias de build
echo [IW] Instalando dependencias de build...
%PYTHON% -m pip install pyinstaller psutil pywin32 --quiet
if errorlevel 1 (
    echo [WARN] Algunas dependencias fallaron - continuando...
)
echo [OK] Dependencias instaladas

:: ── Build 1: Instalador GUI ────────────────────────────────────────────────
echo.
echo [IW] Construyendo instalador GUI...

%PYTHON% -m PyInstaller ^
    --onefile ^
    --noconsole ^
    --name "InfraWatch-Agent-Installer" ^
    --add-data "agent.py;." ^
    --hidden-import psutil ^
    --hidden-import winreg ^
    --hidden-import tkinter ^
    --hidden-import tkinter.ttk ^
    --distpath "%DIST%" ^
    --workpath "%BUILD%" ^
    --clean ^
    --noconfirm ^
    installer_windows.py

if errorlevel 1 (
    echo [ERROR] Fallo al construir el instalador
    pause & exit /b 1
)
echo [OK] InfraWatch-Agent-Installer.exe creado

:: ── Build 2: Agente (servicio) ─────────────────────────────────────────────
echo.
echo [IW] Construyendo agente (servicio)...

%PYTHON% -m PyInstaller ^
    --onefile ^
    --console ^
    --name "iw-agent" ^
    --hidden-import psutil ^
    --hidden-import win32service ^
    --hidden-import win32serviceutil ^
    --hidden-import win32event ^
    --hidden-import servicemanager ^
    --hidden-import winreg ^
    --distpath "%DIST%" ^
    --workpath "%BUILD%" ^
    --noconfirm ^
    agent.py

if errorlevel 1 (
    echo [WARN] iw-agent.exe fallo (puede ser por pywin32)
) else (
    echo [OK] iw-agent.exe creado
)

:: ── Resultado ──────────────────────────────────────────────────────────────
echo.
echo ╔══════════════════════════════════════════════════════════════╗
echo ║  Build completado                                            ║
echo ╠══════════════════════════════════════════════════════════════╣
if exist "%DIST%\InfraWatch-Agent-Installer.exe" (
    echo ║  OK  dist\InfraWatch-Agent-Installer.exe  ^<-- Distribuir
) else (
    echo ║  --  InfraWatch-Agent-Installer.exe  [no generado]
)
if exist "%DIST%\iw-agent.exe" (
    echo ║  OK  dist\iw-agent.exe
) else (
    echo ║  --  iw-agent.exe  [no generado]
)
echo ╚══════════════════════════════════════════════════════════════╝
echo.
echo Distribuye: dist\InfraWatch-Agent-Installer.exe
echo El usuario solo necesita ejecutarlo como Administrador.
echo.
pause
