@echo off
setlocal EnableExtensions DisableDelayedExpansion
title Yier OC2DIYChef Installer

for %%I in ("%~dp0.") do set "INSTALLER_DIR=%%~fI"
for %%I in ("%CD%\.") do set "GAME_DIR=%%~fI"
set "INSTALLER_PS1=%INSTALLER_DIR%\Install-Yier.ps1"
set "EXIT_CODE=0"

echo ========================================
echo   Yier OC2DIYChef One-Click Installer
echo   Author: DUKEY
echo ========================================
echo.

if not exist "%INSTALLER_PS1%" (
    echo [ERROR] Installer not found:
    echo "%INSTALLER_PS1%"
    echo Extract the complete package before running this file.
    set "EXIT_CODE=2"
    goto :finish
)

rem Prefer the launch directory, then try the batch file directory.
if exist "%GAME_DIR%\Overcooked2.exe" goto :game_found
set "GAME_DIR=%INSTALLER_DIR%"
if exist "%GAME_DIR%\Overcooked2.exe" goto :game_found

echo [ERROR] This is not the Overcooked! 2 game directory.
echo.
echo Copy every extracted package file into the directory containing
echo Overcooked2.exe, then double-click Install-Yier.bat.
echo.
echo Launch directory: "%CD%"
echo Script directory: "%INSTALLER_DIR%"
set "EXIT_CODE=3"
goto :finish

:game_found
echo [GAME FOUND] "%GAME_DIR%"
echo [INSTALLING] Yier model, YierCap, and Trail Color GUI
echo.

powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%INSTALLER_PS1%" -GameDir "%GAME_DIR%"
set "EXIT_CODE=%ERRORLEVEL%"

echo.
if "%EXIT_CODE%"=="0" (
    echo [DONE] Yier installation finished.
    echo Select 174-yier in game. If the summary says the GUI was installed,
    echo press F10 in game to open it.
) else (
    echo [FAILED] Installer exit code: %EXIT_CODE%
    echo Review the error above. If the game is running, close it and retry.
)

:finish
echo.
if /I not "%YIER_INSTALL_NO_PAUSE%"=="1" pause
exit /b %EXIT_CODE%
