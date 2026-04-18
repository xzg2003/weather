@echo off
chcp 65001 >nul
echo ========================================
echo 气象数据采集系统 - 一键启动
echo ========================================
echo.

REM 检查 InfluxDB 是否已经在运行
tasklist /FI "IMAGENAME eq influxd.exe" 2>NUL | find /I /N "influxd.exe">NUL
if "%ERRORLEVEL%"=="0" (
    echo [√] InfluxDB 已在运行
) else (
    echo [!] 正在启动 InfluxDB...
    start "InfluxDB Server" /MIN cmd /c "cd /d %~dp0influxdb && start_influxdb.bat"
    echo [√] InfluxDB 启动中...
    echo     请等待 5 秒让数据库完全启动...
    timeout /t 5 /nobreak >nul
)

echo.
echo [√] 准备启动气象数据采集程序...
echo.
echo ========================================
echo 提示：
echo 1. 首次使用请先访问 http://localhost:8086 初始化数据库
echo 2. 将获得的 Token 填入 config.env 文件
echo 3. 按 Ctrl+C 可以停止数据采集
echo ========================================
echo.

REM 启动数据采集程序
python weather_collector.py

pause
