@echo off
rem Installation depuis le code source : environnement Python + raccourci sur le Bureau.
setlocal
cd /d "%~dp0"
where py >nul 2>nul && (set "PY=py -3") || (set "PY=python")
%PY% --version >nul 2>nul
if errorlevel 1 (
    echo Python 3.10 ou plus recent est necessaire : https://www.python.org/downloads/
    echo Coche "Add python.exe to PATH" pendant l'installation, puis relance install.bat.
    start "" https://www.python.org/downloads/
    pause
    exit /b 1
)
echo Creation de l'environnement...
if not exist ".venv\Scripts\python.exe" %PY% -m venv .venv || goto :error
".venv\Scripts\python.exe" -m pip install --upgrade pip -q || goto :error
echo Installation des dependances...
".venv\Scripts\python.exe" -m pip install -r requirements.txt -q || goto :error
echo Creation du raccourci sur le Bureau...
powershell -NoProfile -Command ^
  "$s=(New-Object -ComObject WScript.Shell).CreateShortcut([Environment]::GetFolderPath('Desktop')+'\Forge411.lnk');" ^
  "$s.TargetPath='%CD%\.venv\Scripts\pythonw.exe'; $s.Arguments='\"%CD%\Forge411.pyw\"';" ^
  "$s.WorkingDirectory='%CD%'; $s.IconLocation='%CD%\forge411\assets\forge411.ico'; $s.Save()"
echo.
echo Installation terminee : lance Forge411 depuis le raccourci du Bureau.
start "" ".venv\Scripts\pythonw.exe" Forge411.pyw
exit /b 0
:error
echo L'installation a echoue.
pause
exit /b 1
