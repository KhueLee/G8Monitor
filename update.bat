@echo off
cd /d "%~dp0"
echo ============================================
echo  G8 Monitor - CAP NHAT BAN MOI (git pull)
echo  Nen tat tool (dong cua so start.bat) truoc khi cap nhat.
echo ============================================
where git >nul 2>&1 || (echo Chua cai Git. Xem muc "Cai Git" trong README.md & pause & exit /b 1)
git pull
if errorlevel 1 (
  echo.
  echo CAP NHAT LOI. Neu bao file da sua tren may: chay "git status" de xem,
  echo "git checkout -- ." de bo thay doi tren may - khong anh huong config.json -, roi chay lai file nay.
  pause & exit /b 1
)
echo.
echo Da cap nhat xong. Chay lai start.bat de dung ban moi.
pause
