@echo off
rem Keo tha file Excel mapping highbay (.xlsx) vao file nay de cap nhat ten diem (nodes.json).
cd /d "%~dp0"
if "%~1"=="" (echo Keo tha file .xlsx vao update_names.bat) else (python update_names.py "%~1")
pause
