@echo off
setlocal EnableExtensions DisableDelayedExpansion
rem Run Cyberpunk Forge from this folder without installing it.
set "CPFORGE_ROOT=%~dp0"
if exist "%CPFORGE_ROOT%.venv\Scripts\python.exe" (
  "%CPFORGE_ROOT%.venv\Scripts\python.exe" -m cpforge %*
  exit /b %ERRORLEVEL%
)
set "PYTHONPATH=%CPFORGE_ROOT%src;%PYTHONPATH%"
python -m cpforge %*
exit /b %ERRORLEVEL%
