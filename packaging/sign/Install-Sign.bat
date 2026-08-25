@echo off
setlocal EnableExtensions DisableDelayedExpansion
title Sign OC2DIYChef Special Installer

for %%I in ("%~dp0.") do set "INSTALLER_DIR=%%~fI"
for %%I in ("%INSTALLER_DIR%\..") do set "GAME_DIR=%%~fI"
set "INSTALLER_PS1=%INSTALLER_DIR%\Install-Sign.ps1"
set "EXIT_CODE=0"

echo ========================================
echo   Sign OC2DIYChef Special Installer
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

rem The extracted package folder must be directly under the game directory.
if exist "%GAME_DIR%\Overcooked2.exe" goto :game_found

echo [ERROR] The package folder is not directly inside the Overcooked! 2 game directory.
echo.
echo Extract the ZIP into the directory containing Overcooked2.exe,
echo then run Install-Sign.bat inside the extracted Sign package folder.
echo.
echo Package folder: "%INSTALLER_DIR%"
echo Expected game directory: "%GAME_DIR%"
set "EXIT_CODE=3"
goto :finish

:game_found
echo [GAME FOUND] "%GAME_DIR%"
echo [INSTALLING] Sign, optional SignCap, Trail Color GUI, and async level support
echo.

powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%INSTALLER_PS1%" -GameDir "%GAME_DIR%"
set "EXIT_CODE=%ERRORLEVEL%"

echo.
if "%EXIT_CODE%"=="0" (
    echo [DONE] Sign special installation finished.
    echo Sign is hatless by default. Select Sign in game. If the summary
    echo says the GUI was installed,
    echo press F10 in game to open it. Async level support is installed only
    echo when a compatible OC2DIYLevel 0.9.0 is already present.
) else (
    echo [FAILED] Installer exit code: %EXIT_CODE%
    echo Review the error above. If the game is running, close it and retry.
)

:finish
echo.
if /I not "%SIGN_INSTALL_NO_PAUSE%"=="1" pause
exit /b %EXIT_CODE%
