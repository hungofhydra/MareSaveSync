@echo off
rem Builds the portable app: dist\MareSaveSync\ holds MareSaveSync.exe, its runtime (_internal\) and, once it
rem has run, its data\ folder (settings, sign-in, cached covers, backups). Copy that whole folder anywhere.
rem The build itself is in build.py (the GitHub release workflow uses it too).
cd /d "%~dp0"
set PY=python
if exist .venv\Scripts\python.exe set PY=.venv\Scripts\python.exe
%PY% -m pip install --upgrade pyinstaller -r requirements.txt || goto :err
%PY% build.py || goto :err
echo.
echo Done: dist\MareSaveSync\MareSaveSync.exe
echo Copy the whole dist\MareSaveSync folder around; settings are kept in its data folder.
pause
exit /b 0
:err
echo Build failed.
pause
exit /b 1
