@echo off
net session >nul 2>&1 || (echo Hay chuot phai - Run as administrator & pause & exit /b 1)
netsh advfirewall firewall delete rule name="G8 Monitor 5502" >nul 2>&1
netsh advfirewall firewall delete rule name="G8 Monitor 5503" >nul 2>&1
netsh advfirewall firewall delete rule name="G8 Monitor 5504" >nul 2>&1
netsh advfirewall firewall delete rule name="G8 Monitor 5505" >nul 2>&1
netsh advfirewall firewall add rule name="G8 Monitor 5502" dir=in action=allow protocol=TCP localport=5502 profile=private,domain
netsh advfirewall firewall add rule name="G8 Monitor 5503" dir=in action=allow protocol=TCP localport=5503 profile=private,domain
netsh advfirewall firewall add rule name="G8 Monitor 5504" dir=in action=allow protocol=TCP localport=5504 profile=private,domain
netsh advfirewall firewall add rule name="G8 Monitor 5505" dir=in action=allow protocol=TCP localport=5505 profile=private,domain
echo Da mo cong 5502 (RCS gui du lieu vao) 5503 (xem web), 5504 (quan tri Telegram) va 5505 (keo file). Mang phai la Private/Domain.
pause
