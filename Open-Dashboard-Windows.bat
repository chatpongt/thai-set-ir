@echo off
rem ============================================================================
rem  Thai SET IR Universe - double-click to open the dashboard on Windows
rem  No install needed: opens index.html in your default browser.
rem  Want a Desktop icon? Double-click scripts\windows-desktop-shortcut.bat once.
rem ============================================================================
cd /d "%~dp0"
if not exist "%~dp0index.html" (
  echo [X] index.html not found next to this file: %~dp0
  echo     Keep this .bat file in the thai-set-ir folder.
  pause
  exit /b 1
)
start "" "%~dp0index.html"
