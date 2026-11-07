@echo off
rem Teste diario da mesa de revisao (chamado pelo Agendador de Tarefas; ver scripts\agendar_teste_diario.ps1).
rem A saida do terminal vai para logs\monitoramento\saida.txt.
cd /d "%~dp0"
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
set PYTHONUNBUFFERED=1
if not exist logs\monitoramento mkdir logs\monitoramento
echo. >> logs\monitoramento\saida.txt
echo === inicio %date% >> logs\monitoramento\saida.txt
.venv\Scripts\python.exe -X utf8 teste_diario.py %* >> logs\monitoramento\saida.txt 2>&1
