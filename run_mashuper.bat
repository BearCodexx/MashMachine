@echo off
chcp 65001 >nul
title MashuperBot (Auto-Restart)
color 0A
cd /d "%~dp0"

echo ========================================
echo      MASHUPERBOT - АВТОРЕСТАРТ
echo ========================================
echo.
echo Лог ошибок: mashuper_error.log
echo.

:: проверка наличия Applio (без автоматического скачивания 5 ГБ)
set APPLIO_DIR=applio

:check_applio
if not exist "%APPLIO_DIR%\app.py" goto no_applio
if not exist "%APPLIO_DIR%\core.py" goto no_applio
if not exist "%APPLIO_DIR%\ffmpeg.exe" goto no_applio
goto check_port

:no_applio
echo [%time%] ПРЕДУПРЕЖДЕНИЕ: Applio не найден!
echo.
echo   Applio нужен для работы бота. Скачай его вручную:
echo   https://huggingface.co/IAHispano/Applio/resolve/main/Compiled/Windows/ApplioV3.6.2.zip
echo.
echo   Затем распакуй архив в папку: %~dp0applio\
echo.
pause
goto restart

:check_port
:: проверка запущен ли Applio
netstat -an | find "6969" >nul 2>&1
if errorlevel 1 goto start_applio
echo [%time%] Applio уже запущен (порт 6969)
goto restart

:start_applio
echo [%time%] Запускаю Applio...

if not exist "%APPLIO_DIR%\env\python.exe" (
    echo [%time%] Ошибка: Applio установлен некорректно (нет env\python.exe)
    echo [%time%] Переустанови Applio вручную или удали папку applio
    pause
    goto restart
)

start "Applio" /D "%~dp0%APPLIO_DIR%" "%~dp0%APPLIO_DIR%\env\python.exe" "%~dp0%APPLIO_DIR%\app.py" --open
echo [%time%] Жду запуск Applio (30 сек)
timeout /t 30 /nobreak >nul

:restart
echo [%date% %time%] Запуск бота... >> mashuper_error.log
echo [%time%] Запуск MashuperBot...

if exist "%~dp0.venv\Scripts\activate.bat" (
    call "%~dp0.venv\Scripts\activate.bat"
) else (
    echo [%time%] Ошибка: Виртуальное окружение не найдено!
    echo [%time%] Запустите python -m venv .venv
    pause
    exit /b 1
)

python "%~dp0bot.py" 2>> "%~dp0mashuper_error.log"

echo [%date% %time%] Бот остановлен. Перезапуск через 10 секунд... >> mashuper_error.log
echo [%time%] Ошибка! Перезапуск через 10 секунд
timeout /t 10 /nobreak >nul
goto restart