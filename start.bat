@echo off
cd /d "%~dp0"
echo ============================================
echo  G8 Monitor
echo  XEM GIAO DIEN (dien thoai/may khac trong LAN):
echo    http://192.168.110.189:5503
echo  KHAI TRONG RCS (Third-party Service Configuration) - cong 5502:
echo    http://192.168.110.189:5502/ics/agv-status
echo    http://192.168.110.189:5502/ics/alarm
echo    http://192.168.110.189:5502/ics/task-status
echo  QUAN TRI TELEGRAM (co mat khau):
echo    http://192.168.110.189:5504
echo  Neu khong vao duoc: chay tools\firewall_open.bat (Run as administrator)
echo ============================================
python src\main.py
pause
