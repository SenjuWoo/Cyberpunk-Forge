@echo off
setlocal EnableExtensions DisableDelayedExpansion
rem Run Cyberpunk Forge from this folder without installing it.
set "CPFORGE_ROOT=%~dp0"
rem No parenthesised block around the python call: %ERRORLEVEL% inside one is expanded
rem before python runs, which would return the old errorlevel instead of python's.
if not exist "%CPFORGE_ROOT%.venv\Scripts\python.exe" goto :source
"%CPFORGE_ROOT%.venv\Scripts\python.exe" -m cpforge %*
exit /b %ERRORLEVEL%
:source
set "PYTHONPATH=%CPFORGE_ROOT%src;%PYTHONPATH%"
python -m cpforge %*
exit /b %ERRORLEVEL%
