@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo Enviando para https://github.com/marikeiske/literature-review-agent ...
echo Se abrir uma janela do GitHub, entre com a sua conta e autorize.
echo.
git push -u origin main --follow-tags
echo.
pause
