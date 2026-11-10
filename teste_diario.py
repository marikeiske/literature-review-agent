"""Teste diário até a apresentação: confere, uma vez por dia, que a mesa ainda funciona de ponta a ponta.

Por que existe: os modelos gratuitos mudam ou saem do ar sem aviso (limite declarado no artigo,
Seção VI). Rodar um pouco todo dia mostra a quebra no dia em que ela acontece, e não na hora da demo.

O que roda a cada dia (perguntas diferentes a cada dia, sem repetir):
  1. testes do código (pytest, sem rede e sem gastar cota)
  2. 5 afirmações do gabarito revisado, pontuadas como em avaliar.py
  3. 1 pergunta negativa (o certo é recusar ou corrigir a premissa), pontuada como em avaliar.py
  4. 1 pergunta livre, como na demo, conferida só pelo verificador
A escolha do dia é fixa (semente 20261105): o dia 1 é 05/11, o dia 8 é 12/11.

Saída (fora do git, como todo log): logs/monitoramento/<data>.json com o detalhe,
uma linha em logs/monitoramento/resumo.md e um aviso do Windows com o resultado.
Na sessão do agente (logs/sessao_*.jsonl) a primeira linha marca origem "teste_diario",
para não confundir com uso feito pela autora.

Uso:
  python teste_diario.py                      o teste do dia, com o GPT-OSS 120B (Groq), o modelo da demo
  python teste_diario.py --modelo gemini      outro modelo
  python teste_diario.py --dia 3              força o conjunto do dia 3 (1 a 8)
  python teste_diario.py --sem-pytest         pula os testes do código
Agendamento: scripts/agendar_teste_diario.ps1.
"""
import argparse
import json
import os
import random
import subprocess
import sys
import time
import urllib.request
from datetime import date

from openai import APIStatusError, APITimeoutError, APIConnectionError, RateLimitError

import avaliar
from agente.config import PROVEDORES, RAIZ
from agente.harness import Agente
from negativas import NEGATIVAS

INICIO = date(2026, 11, 5)  # dia 1
DIAS = 8                     # até 12/11, véspera da primeira apresentação
POR_DIA = 5
SEMENTE = 20261105
# O modelo da demo. Até 09/11 era o Nemotron 3 Ultra no Ollama Cloud; em 10/11 o Ollama passou a cobrar
# por token (erro 402) e a chave gratuita do OpenRouter tinha expirado, então a demo passou ao GPT-OSS 120B
# no Groq (sem custo, 104/109 na avaliação de 26/10).
MODELO_PADRAO = "groq"
PASTA = RAIZ / "logs" / "monitoramento"

# Perguntas livres, no estilo da demo: um documento diferente por dia. Não têm gabarito;
# passam se a resposta citar só páginas lidas e cada frase tiver citação (ou se recusar).
LIVRES = [
    "Quanto a arquitetura de Nimbekar consome na FPGA, comparada à GPU?",
    "No estudo de Breyer, qual backend foi mais rápido em cada fabricante de GPU?",
    "O que o AC 20-193 da FAA chama de interferência entre núcleos e o que ele pede do requerente?",
    "Que problema o trabalho de Leppänen resolve e em que hardware ele foi avaliado?",
    "Quais limites da automação de projeto de sistemas Sifakis aponta?",
    "Que plataforma heterogênea Lozano usa e que ganho de desempenho relata?",
    "O que Mzid propõe e como avalia a proposta?",
    "Qual é a contribuição principal de Yoshida e com que métrica ela é medida?",
]


def conjunto_do_dia(dia: int, itens: list[dict]) -> tuple[list[dict], dict, str]:
    """Afirmações, negativa e pergunta livre do dia (1 a 8), sem repetir entre os dias."""
    ordem = sorted(itens, key=lambda i: i["id"])
    random.Random(SEMENTE).shuffle(ordem)
    negs = sorted(NEGATIVAS, key=lambda n: n["id"])
    random.Random(SEMENTE + 1).shuffle(negs)
    k = (dia - 1) % DIAS
    return ordem[k * POR_DIA:(k + 1) * POR_DIA], negs[k % len(negs)], LIVRES[k % len(LIVRES)]


# ---------- Ollama no Docker ----------
def _ollama_responde() -> bool:
    base = PROVEDORES["ollama"]["base_url"].rstrip("/").removesuffix("/v1")
    try:
        with urllib.request.urlopen(base + "/api/version", timeout=5) as r:
            return r.status == 200
    except OSError:
        return False


def _rodar(cmd, timeout=60) -> bool:
    try:
        return subprocess.run(cmd, capture_output=True, timeout=timeout).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def garantir_ollama(log: list[str]) -> bool:
    """Se o contêiner do Ollama não responde, tenta subir o Docker Desktop e o contêiner."""
    if _ollama_responde():
        return True
    log.append("Ollama não respondeu; tentando ligar o Docker")
    if not _rodar(["docker", "info"], 30):
        # 07/11: o Docker Desktop travava ao abrir por causa de um engine.sock antigo. O script de
        # conserto fecha o Docker travado, renomeia as pastas de conexão (não apaga) e abre de novo.
        conserto = RAIZ / "scripts" / "consertar_docker.ps1"
        if conserto.is_file():
            _rodar(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(conserto)], 360)
            log.append("Docker não respondia; rodou scripts/consertar_docker.ps1")
        for _ in range(24):  # mais 2 minutos de folga
            if _rodar(["docker", "info"], 30):
                break
            time.sleep(5)
    _rodar(["docker", "start", "ollama-novo"], 60)
    for _ in range(12):
        time.sleep(5)
        if _ollama_responde():
            log.append("Ollama ligado pelo teste")
            return True
    return False


# ---------- partes do teste ----------
def testes_do_codigo() -> dict:
    inicio = time.time()
    try:
        r = subprocess.run([sys.executable, "-X", "utf8", "-m", "pytest", "tests", "-q", "-p", "no:cacheprovider"],
                           cwd=RAIZ, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=900,
                           env={k: v for k, v in os.environ.items() if not k.startswith("MESA_")})  # testes sem o .env
        ultima = [x for x in r.stdout.strip().splitlines() if x.strip()][-1:] or ["sem saída"]
        if r.returncode != 0:  # guarda a saída inteira para achar a causa (07/11: 19 erros só no agendador)
            PASTA.mkdir(parents=True, exist_ok=True)
            (PASTA / f"{date.today().isoformat()}_pytest.txt").write_text(r.stdout + r.stderr, encoding="utf-8")
        return {"ok": r.returncode == 0, "resumo": ultima[0].strip(" ="), "segundos": round(time.time() - inicio)}
    except subprocess.TimeoutExpired:
        return {"ok": False, "resumo": "passou de 15 minutos", "segundos": 900}


def _perguntar(funcao, *args):
    """Chama o modelo; devolve (resultado, erro). Erros do provedor viram texto, não quebram o dia."""
    try:
        return avaliar.com_retentativa(funcao, *args), ""
    except RateLimitError as e:
        return None, f"cota/limite (429): {str(e)[:120]}"
    except (APITimeoutError, APIConnectionError) as e:
        return None, f"sem conexão com o provedor: {type(e).__name__}"
    except APIStatusError as e:
        return None, f"erro do provedor ({e.status_code}): {str(e)[:120]}"


def afirmacoes(agente: Agente, itens: list[dict]) -> list[dict]:
    saida = []
    for item in itens:
        inicio = time.time()
        r, erro = _perguntar(avaliar.responder_rag, agente, item)
        linha = {"id": item["id"], "artigo": item["artigo"], "gabarito": sorted(item["paginas"]),
                 "segundos": round(time.time() - inicio, 1), "erro": erro}
        if r:
            resposta, chamadas, evid = r
            linha.update(avaliar.pontuar(item, resposta, evid), chamadas=chamadas, resposta=resposta[:600])
        saida.append(linha)
        print(f"  {item['id']} {item['artigo']:<14} gabarito p.{linha['gabarito']} citou p.{linha.get('paginas_citadas') or '-'}"
              f" {'ACERTO' if linha.get('acerto_exato') else 'erro'} {erro}")
    return saida


def negativa(agente: Agente, neg: dict) -> dict:
    inicio = time.time()
    agente.limpar()
    r, erro = _perguntar(agente.responder, neg["pergunta"])
    linha = {"id": neg["id"], "tipo": neg["tipo"], "pergunta": neg["pergunta"], "segundos": round(time.time() - inicio, 1),
             "erro": erro}
    if r:
        resposta, chamadas = r
        linha.update(avaliar.pontuar_negativa(neg, resposta, dict(agente.ferramentas.evidencias)),
                     chamadas=chamadas, resposta=resposta[:600])
    print(f"  {neg['id']} {neg['tipo']:<16} {'ACERTO' if linha.get('acerto') else 'erro'} {erro}")
    return linha


def livre(agente: Agente, pergunta: str) -> dict:
    inicio = time.time()
    agente.limpar()
    r, erro = _perguntar(agente.responder, pergunta)
    linha = {"pergunta": pergunta, "segundos": round(time.time() - inicio, 1), "erro": erro}
    if r:
        resposta, chamadas = r
        fim = agente.fechar_turno(resposta)
        vereditos = [it["veredito"] for it in fim["itens"]]
        ruins = {"página não lida", "sem citação", "recusa sem página lida"}
        linha.update(chamadas=chamadas, parada=fim["parada"], vereditos=vereditos, resposta=resposta[:800],
                     paginas_lidas=sorted(f"{a} p.{p}" for a, p in fim["evidencias"]),
                     ok=bool(vereditos) and not (set(vereditos) & ruins))
    print(f"  livre: {'ok' if linha.get('ok') else 'FALHA'} · {', '.join(linha.get('vereditos', [])) or erro}")
    return linha


def avisar_windows(titulo: str, texto: str):
    """Balão de notificação do Windows. Os textos vão por variável de ambiente (nada de aspas no comando)."""
    if os.name != "nt":
        return
    ps = ("Add-Type -AssemblyName System.Windows.Forms; $n = New-Object System.Windows.Forms.NotifyIcon; "
          "$n.Icon = [System.Drawing.SystemIcons]::Information; $n.Visible = $true; "
          "$n.ShowBalloonTip(15000, $env:AVISO_TITULO, $env:AVISO_TEXTO, 'Info'); Start-Sleep 16; $n.Dispose()")
    env = {**os.environ, "AVISO_TITULO": titulo[:60], "AVISO_TEXTO": texto[:240]}
    subprocess.Popen(["powershell", "-NoProfile", "-WindowStyle", "Hidden", "-Command", ps], env=env,
                     creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--modelo", default=MODELO_PADRAO)
    ap.add_argument("--dia", type=int, default=None, help="1 a 8; padrão: o dia de hoje contado a partir de 05/11")
    ap.add_argument("--sem-pytest", action="store_true")
    ap.add_argument("--so-codigo", action="store_true", help="só os testes do código; não grava o dia")
    args = ap.parse_args()
    if args.so_codigo:
        r = testes_do_codigo()
        print(f"Testes do código: {r['resumo']}")
        return 0 if r["ok"] else 1

    hoje = date.today()
    dia = args.dia or max(1, (hoje - INICIO).days + 1)
    PASTA.mkdir(parents=True, exist_ok=True)
    notas: list[str] = []
    print(f"Teste diário · dia {dia} de {DIAS} · {hoje:%d/%m/%Y} · {args.modelo}")

    rel = {"data": hoje.isoformat(), "dia": dia, "modelo": args.modelo}  # só a data: horário é pessoal
    try:
        rel["commit"] = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=RAIZ, capture_output=True,
                                       text=True, timeout=10).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        rel["commit"] = ""

    if not args.sem_pytest:
        print("1. Testes do código...")
        rel["testes_codigo"] = testes_do_codigo()
        print(f"  {rel['testes_codigo']['resumo']}")

    itens, neg, pergunta = conjunto_do_dia(dia, avaliar.carregar_gabarito())
    if args.modelo.startswith("ollama") and not garantir_ollama(notas):
        rel["erro_geral"] = "Ollama não respondeu (Docker Desktop ou contêiner ollama-novo desligado)"
    else:
        agente = Agente()
        print(agente.trocar_modelo(args.modelo))
        agente._registrar({"tipo": "monitoramento", "origem": "teste_diario", "dia": dia,
                           "aviso": "execução automática agendada, não é uso da autora"})
        print("2. Afirmações do gabarito...")
        rel["afirmacoes"] = afirmacoes(agente, itens)
        print("3. Pergunta negativa...")
        rel["negativa"] = negativa(agente, neg)
        print("4. Pergunta livre...")
        rel["livre"] = livre(agente, pergunta)
        rel["log_sessao"] = agente.arquivo_log.name
    rel["notas"] = notas

    # ---------- veredito do dia ----------
    afs = rel.get("afirmacoes", [])
    acertos = sum(int(a.get("acerto_exato", 0)) for a in afs)
    falsos = sum(int(a.get("grounding_falso", 0)) for a in afs)
    erros_api = [x["erro"] for x in [*afs, rel.get("negativa", {}), rel.get("livre", {})] if x.get("erro")]
    problemas = []
    if rel.get("erro_geral"):
        problemas.append(rel["erro_geral"])
    if not rel.get("testes_codigo", {"ok": True})["ok"]:
        problemas.append(f"testes do código: {rel['testes_codigo']['resumo']}")
    if erros_api:
        problemas.append(f"{len(erros_api)} pergunta(s) sem resposta do provedor: {erros_api[0]}")
    if falsos:
        problemas.append(f"{falsos} citação(ões) de página não lida")
    if afs and acertos < POR_DIA - 1:
        problemas.append(f"só {acertos}/{len(afs)} páginas exatas")
    if rel.get("negativa") and not rel["negativa"].get("acerto") and not rel["negativa"].get("erro"):
        problemas.append(f"negativa {rel['negativa']['id']} errada")
    if rel.get("livre") and not rel["livre"].get("ok") and not rel["livre"].get("erro"):
        problemas.append("pergunta livre com frase sem citação ou página não lida")
    rel["ok"] = not problemas
    rel["problemas"] = problemas

    (PASTA / f"{hoje.isoformat()}.json").write_text(json.dumps(rel, ensure_ascii=False, indent=1), encoding="utf-8")
    resumo = PASTA / "resumo.md"
    if not resumo.exists():
        resumo.write_text("# Teste diário da mesa de revisão\n\nGerado por teste_diario.py. Uma linha por dia.\n\n"
                          "| Data | Dia | Testes do código | Páginas exatas | Negativa | Pergunta livre | Resultado |\n"
                          "|---|---|---|---|---|---|---|\n", encoding="utf-8")
    neg_txt = (("acertou" if rel["negativa"].get("acerto") else "errou") + f" ({rel['negativa']['id']})") if rel.get("negativa") else "-"
    liv_txt = ("ok" if rel["livre"].get("ok") else "falhou") if rel.get("livre") else "-"
    linha = (f"| {hoje:%d/%m} | {dia} | {rel.get('testes_codigo', {}).get('resumo', 'pulado')} | "
             f"{f'{acertos}/{len(afs)}' if afs else '-'} | {neg_txt} | {liv_txt} | "
             f"{'OK' if rel['ok'] else 'PROBLEMA: ' + '; '.join(problemas)} |\n")
    with open(resumo, "a", encoding="utf-8") as f:
        f.write(linha)

    texto = (f"Páginas exatas {acertos}/{len(afs)}, negativa {neg_txt}, pergunta livre {liv_txt}."
             if rel["ok"] else "; ".join(problemas))
    print(f"\nResultado do dia {dia}: {'OK' if rel['ok'] else 'PROBLEMA'} · {texto}")
    print(f"Detalhe: {PASTA / (hoje.isoformat() + '.json')}")
    avisar_windows(f"Mesa de revisão: teste do dia {dia} {'OK' if rel['ok'] else 'com problema'}", texto)
    return 0 if rel["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
