# Prepara o Ollama novo (conteiner ollama-novo, porta 11435) e testa o agente com o modelo local.
# Log em logs\preparar_ollama.txt
$raiz = Split-Path -Parent $PSScriptRoot
$log = Join-Path $raiz "logs\preparar_ollama.txt"
$modelo = "bonsai-2:4b"
[Console]::OutputEncoding = [Text.Encoding]::UTF8
$OutputEncoding = [Text.Encoding]::UTF8
& {
  "Inicio: " + (Get-Date)
  "`n== 1. Docker =="
  docker info --format "{{.ServerVersion}}" 2>$null
  if ($LASTEXITCODE -ne 0) { "Docker nao respondeu. Rode consertar_docker.bat e depois este de novo."; return }

  "`n== 2. Conteiner ollama-novo com contexto de 8192 tokens =="
  $cfg = docker inspect ollama-novo --format "{{json .Config.Env}}" 2>$null
  if ($LASTEXITCODE -ne 0) { $cfg = "" }
  if ("$cfg" -notmatch "OLLAMA_CONTEXT_LENGTH=8192") {
    if ($cfg) {
      docker stop ollama-novo | Out-Null
      $novoNome = "ollama-novo_sem_ctx_" + (Get-Date -Format "yyyyMMdd_HHmm")
      docker rename ollama-novo $novoNome
      "Conteiner antigo guardado como $novoNome (o modelo baixado fica no volume e e reaproveitado)."
    }
    docker run -d --name ollama-novo --restart unless-stopped --network te251 -p 127.0.0.1:11435:11434 -e OLLAMA_CONTEXT_LENGTH=8192 -v ollama-novo:/root/.ollama ollama/ollama:latest
    Start-Sleep 8
  } else { docker start ollama-novo | Out-Null; "Ja estava com 8192." }
  docker exec ollama-novo ollama --version

  "`n== 3. Modelo $modelo =="
  $lista = docker exec ollama-novo ollama list
  $lista
  if (-not ("$lista" -match [regex]::Escape($modelo))) {
    "Baixando $modelo (1,2 GB)..."
    docker exec ollama-novo ollama pull $modelo 2>&1 | Select-Object -Last 3
    docker exec ollama-novo ollama list
  }

  "`n== 4. Teste do agente (pode levar alguns minutos no processador) =="
  $env:PYTHONIOENCODING = "utf-8"
  Push-Location $raiz
  & (Join-Path $raiz ".venv\Scripts\python.exe") teste_rapido.py ollama "Qual FPGA Nimbekar usou?"
  Pop-Location
  "`nFim: " + (Get-Date)
} *>&1 | Tee-Object -FilePath $log
