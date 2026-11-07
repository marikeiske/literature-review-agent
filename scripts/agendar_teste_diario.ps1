# Agenda o teste diario no Agendador de Tarefas do Windows: todo dia as 10:13, de hoje ate 12/11/2026.
# Se o notebook estiver desligado ou dormindo nesse horario, roda assim que ele for ligado (StartWhenAvailable).
# Roda so com voce logada (o Docker Desktop precisa da sua sessao). Nao precisa de administrador.
# Para apagar o agendamento: Unregister-ScheduledTask -TaskName "Mesa de revisao - teste diario"
$raiz = Split-Path -Parent $PSScriptRoot
$nome = "Mesa de revisao - teste diario"
# Roda sem janela (conhost --headless): em 06/11 a janela preta foi fechada logo ao abrir e o teste
# terminou com 0xC000013A (STATUS_CONTROL_C_EXIT) antes de comecar.
$acao = New-ScheduledTaskAction -Execute "conhost.exe" -Argument "--headless cmd.exe /c `"$raiz\teste_diario.bat`"" -WorkingDirectory $raiz
$gatilho = New-ScheduledTaskTrigger -Daily -At "10:13"
$gatilho.EndBoundary = "2026-11-12T23:59:00"
$config = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Hours 1) -MultipleInstances IgnoreNew
$descricao = "Teste automatico da mesa de revisao ate a apresentacao (teste_diario.py). Resultado em logs\monitoramento\resumo.md."
Register-ScheduledTask -TaskName $nome -Action $acao -Trigger $gatilho -Settings $config -Description $descricao -Force | Out-Null
$t = Get-ScheduledTask -TaskName $nome
"Agendado: '$nome' ($($t.State)). Proxima execucao: $((Get-ScheduledTaskInfo -TaskName $nome).NextRunTime)"
