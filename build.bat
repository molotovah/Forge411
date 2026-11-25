@echo off
rem Compile Forge411.exe (dossier dist\). Nécessite Python 3.10+.
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" python -m venv .venv || goto :error
".venv\Scripts\python.exe" -m pip install --upgrade pip -q || goto :error
".venv\Scripts\python.exe" -m pip install -r requirements.txt pyinstaller -q || goto :error
".venv\Scripts\python.exe" -m unittest -q || goto :error
".venv\Scripts\python.exe" -m PyInstaller --noconfirm --clean forge411.spec || goto :error
echo.
echo Fini : dist\Forge411.exe
exit /b 0
:error
echo La compilation a echoue.
exit /b 1
