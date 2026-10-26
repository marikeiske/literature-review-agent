# Conserta o Docker Desktop quando ele trava ao iniciar por causa de arquivos de conexao antigos.
# Nao apaga nada: renomeia as pastas com sufixo _old_<data>. Log em logs\consertar_docker.txt
$raiz = Split-Path -Parent $PSScriptRoot
$log = Join-Path $raiz "logs\consertar_docker.txt"
[Console]::OutputEncoding = [Text.Encoding]::UTF8
$OutputEncoding = [Text.Encoding]::UTF8
& {
  "Inicio: " + (Get-Date)
  docker info --format "{{.ServerVersion}}" 2>$null | Out-Null
  if ($LASTEXITCODE -eq 0) { "Docker ja esta funcionando. Nada a fazer."; return }
  $procs = Get-Process "Docker Desktop","com.docker.backend","com.docker.build" -ErrorAction SilentlyContinue
  if ($procs) { "Fechando o Docker travado..."; $procs | Stop-Process -Force; Start-Sleep 5 }
  $ts = Get-Date -Format "yyyyMMdd_HHmm"
  foreach ($p in "$env:LOCALAPPDATA\Docker\run", "$env:LOCALAPPDATA\docker-secrets-engine") {
    if (Test-Path $p) { Rename-Item $p ((Split-Path $p -Leaf) + "_old_$ts"); "Renomeada: $p" }
  }
  "Abrindo o Docker Desktop..."
  Start-Process "$env:LOCALAPPDATA\Programs\DockerDesktop\Docker Desktop.exe"
  for ($i = 0; $i -lt 36; $i++) {
    Start-Sleep 5
    docker info --format "{{.ServerVersion}}" 2>$null | Out-Null
    if ($LASTEXITCODE -eq 0) { "Docker funcionando depois de $(5*($i+1)) s."; docker ps --format "{{.Names}} | {{.Status}}"; return }
  }
  "Docker nao respondeu em 3 minutos. Mande print para o Claude."
} *>&1 | Tee-Object -FilePath $log
