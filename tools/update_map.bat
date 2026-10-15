@echo off
rem Keo tha file zip map RCS vao file nay, hoac chay khong tham so de tai map thang tu RCS (topologyList).
cd /d "%~dp0"
if "%~1"=="" (python update_map.py --rcs) else (python update_map.py "%~1")
pause
