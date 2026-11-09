@echo off
setlocal
cd /d "%~dp0"
set "PYTHONPATH=%~dp0src;%PYTHONPATH%"

where streamlit >nul 2>nul
if %errorlevel%==0 (
  start "OpenCarbonChem" streamlit run "app\1_Overview.py"
) else (
  start "OpenCarbonChem" py -m streamlit run "app\1_Overview.py"
)
endlocal
