@echo off
chcp 65001 >nul
title MashuperBot Studio
color 0A
cd /d "%~dp0"

:restart
if not exist "%~dp0.venv\Scripts\activate.bat" goto no_venv

call "%~dp0.venv\Scripts\activate.bat"
python "%~dp0run.py"

echo.
echo [%time%] Сервис остановлен. Перезапуск через 5 секунд...
timeout /t 5 /nobreak >nul
goto restart

:no_venv
echo [%time%] Ошибка: Виртуальное окружение не найдено!
echo [%time%] Запустите: python -m venv .venv
pause
exit /b 1