# Termina os testes que faltam e gera o resumo. Log em logs\rodar_testes.txt
# Cada avaliacao continua de onde parou (avaliar.py pula o que ja esta no CSV).
$raiz = Split-Path -Parent $PSScriptRoot
$log = Join-Path $raiz "logs\rodar_testes.txt"
Set-Location $raiz
$py = Join-Path $raiz ".venv\Scripts\python.exe"
[Console]::OutputEncoding = [Text.Encoding]::UTF8
$OutputEncoding = [Text.Encoding]::UTF8
& {
  "Inicio: " + (Get-Date)
  "`n== 1. Docker (Ollama Cloud passa pelo conteiner ollama-novo) =="
  & (Join-Path $PSScriptRoot "consertar_docker.ps1")
  docker start ollama-novo | Out-Null
  Start-Sleep 5
  "`n== 2. Nemotron 3 Ultra: afirmacoes que faltam =="
  & $py -X utf8 -u avaliar.py ollama:nemotron-3-ultra:cloud 2>&1 | Select-String "^\[|=====|Acerto|erro"
  "`n== 3. Nemotron 3 Ultra: 12 perguntas negativas =="
  & $py -X utf8 -u avaliar.py ollama:nemotron-3-ultra:cloud --negativas 2>&1 | Select-String "^\[|=====|Acerto|erro"
  "`n== 4. Qwen3.8 27B (Groq): continua ate o limite do dia =="
  & $py -X utf8 -u avaliar.py groq:qwen/qwen3.8-27b 2>&1 | Select-String "^\[|=====|Acerto|erro"
  "`n== 5. Resumo =="
  & $py -X utf8 resumo_avaliacao.py
  "`nFim: " + (Get-Date)
} *>&1 | Tee-Object -FilePath $log
