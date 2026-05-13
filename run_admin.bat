@echo off
title MashMachine Admin Panel
color 0A
echo.
echo ========================================
echo      АДМИН-ПАНЕЛЬ MashMachine
echo ========================================
echo.
call .venv\Scripts\activate
python admin_cli.py
pause