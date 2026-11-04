@echo off
rem ============================================================================
rem  Thai SET IR Universe - put a "Thai SET IR" icon on your Windows Desktop.
rem  Run once (double-click). The icon opens the dashboard in your browser.
rem ============================================================================
for %%I in ("%~dp0..") do set "ROOT=%%~fI"
if not exist "%ROOT%\index.html" (
  echo [X] index.html not found in %ROOT%
  pause
  exit /b 1
)
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$d=[Environment]::GetFolderPath('Desktop');" ^
  "$s=(New-Object -ComObject WScript.Shell).CreateShortcut((Join-Path $d 'Thai SET IR.lnk'));" ^
  "$s.TargetPath=(Join-Path $env:ROOT 'index.html');" ^
  "$s.WorkingDirectory=$env:ROOT;" ^
  "$s.IconLocation='shell32.dll,13';" ^
  "$s.Description='Thai SET IR Universe dashboard';" ^
  "$s.Save()"
if errorlevel 1 (
  echo [X] Could not create the shortcut.
  pause
  exit /b 1
)
echo [OK] Created "Thai SET IR" on your Desktop.
pause
