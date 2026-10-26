@echo off
rem Abre a Mesa de revisao no navegador. Feche esta janela para encerrar.
cd /d "%~dp0"
call .venv\Scripts\activate.bat
set PYTHONIOENCODING=utf-8
python app.py
pause
