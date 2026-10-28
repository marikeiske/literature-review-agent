"""Servidor de teste para os testes de interface (Playwright).

Cada sessão de testes monta uma cópia do projeto numa pasta temporária, com PDFs SINTÉTICOS no lugar
do corpus (os artigos reais não vão para o repositório) e um log de conversa antiga. O servidor roda
nessa cópia: os testes podem gravar revisões sem tocar nos arquivos de verdade, e rodam igual no
notebook e no GitHub Actions. Nenhum teste chama um modelo de verdade: o Ollama aponta para uma porta
fechada, então perguntar exercita o caminho de erro do provedor.

Rodar:  pip install -r requirements-dev.txt && python -m playwright install chromium
        pytest tests/ui
"""
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest

sync_api = pytest.importorskip("playwright.sync_api", reason="instale playwright (requirements-dev.txt)")

RAIZ = Path(__file__).resolve().parents[2]
COPIAR = ["app.py", "seguranca.py", "revisao.py", "negativas.py", "gabarito-corpus-avaliacao.xlsx",
          "revisao_gabarito.csv", "pre_conferencia_gabarito.json", "agente", "web", "skills", "resultados"]
PAGINAS_POR_DOC = 45  # cobre a maior página citada no gabarito (Mzid2024, p. 40)
# Frases com números, para conferir o grifo no PDF e no texto
FRASES = {
    ("Nimbekar2023", 1): "The on-chip power requirements for LoCoMo-Net and MyoNet on FPGA are 3.5 and 5 Watts, respectively.",
    ("Leppanen2023", 10): "On-chip synchronization removed 250 us host synchronization overhead when dependent kernels were launched.",
}
LOG_ANTIGO = [
    {"tipo": "pergunta", "quando": "2026-10-20T10:00:00", "modelo": "groq:openai/gpt-oss-120b",
     "texto": "Pergunta antiga de teste: quanto a arquitetura consome?"},
    {"tipo": "tool", "quando": "2026-10-20T10:00:01", "modelo": "groq:openai/gpt-oss-120b", "nome": "ler_pagina",
     "argumentos": {"artigo": "Nimbekar2023", "pagina": 1}, "saida": "..."},
    {"tipo": "chamada_llm", "quando": "2026-10-20T10:00:02", "modelo": "groq:openai/gpt-oss-120b", "segundos": 1.5,
     "tokens_entrada": 1200, "tokens_saida": 40,
     "saida": {"content": "- A arquitetura consome 3,5 W e 5 W na FPGA [Nimbekar2023 p.1]."}},
    {"tipo": "verificacao", "quando": "2026-10-20T10:00:03", "modelo": "groq:openai/gpt-oss-120b",
     "resumo": "rastreável: 1", "itens": [], "origem": "interface", "lidas": [["Nimbekar2023", 1]]},
    {"tipo": "decisao_humana", "quando": "2026-10-20T10:00:09", "modelo": "groq:openai/gpt-oss-120b",
     "decisao": "aprovar", "comentario": "", "origem": "interface"},
]


def _montar_copia(destino: Path):
    import pymupdf
    for nome in COPIAR:
        origem = RAIZ / nome
        if origem.is_dir():
            shutil.copytree(origem, destino / nome, ignore=shutil.ignore_patterns("__pycache__", "*.lock", "vendor_tmp"))
        else:
            shutil.copy2(origem, destino / nome)
    sys.path.insert(0, str(RAIZ))
    from agente.corpus import ARTIGOS
    (destino / "corpus").mkdir()
    for art in ARTIGOS:
        doc = pymupdf.open()
        for n in range(1, PAGINAS_POR_DOC + 1):
            pagina = doc.new_page()
            texto = f"{art['id']} sintetico, pagina {n}.\n{FRASES.get((art['id'], n), 'Texto de exemplo sem numeros.')}"
            pagina.insert_textbox(pymupdf.Rect(50, 50, 550, 800), texto, fontsize=11)
        doc.save(destino / "corpus" / art["arquivo"])
    subprocess.run([sys.executable, "-m", "agente.corpus"], cwd=destino, check=True, capture_output=True)
    (destino / "logs").mkdir()
    with open(destino / "logs" / "sessao_2026-10-20_100000.jsonl", "w", encoding="utf-8") as f:
        for ev in LOG_ANTIGO:
            f.write(json.dumps(ev, ensure_ascii=False) + "\n")


@pytest.fixture(scope="session")
def servidor(tmp_path_factory):
    pasta = tmp_path_factory.mktemp("mesa")
    _montar_copia(pasta)
    env = {k: v for k, v in os.environ.items() if not k.endswith(("_API_KEY", "_KEY"))}
    # Porta própria (8790+): nunca disputa com a interface de verdade, que fica em 8765+
    env.update({"MESA_SEM_NAVEGADOR": "1", "MESA_PORTA": "8790", "PROVEDOR": "ollama", "OLLAMA_BASE_URL": "http://127.0.0.1:9/v1",
                "PYTHONIOENCODING": "utf-8", "PYTHONUNBUFFERED": "1"})
    proc = subprocess.Popen([sys.executable, "app.py"], cwd=pasta, env=env, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, text=True, encoding="utf-8")
    url, inicio = None, time.time()
    while time.time() - inicio < 60:
        linha = proc.stdout.readline()
        m = re.search(r"(http://127\.0\.0\.1:\d+)", linha or "")
        if m:
            url = m.group(1)
            break
        if proc.poll() is not None:
            break
    if not url:
        proc.kill()
        pytest.fail("O servidor de teste não abriu.")
    yield {"url": url, "pasta": pasta}
    proc.terminate()
    proc.wait(timeout=10)


@pytest.fixture(scope="session")
def navegador():
    with sync_api.sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        yield b
        b.close()


@pytest.fixture
def pagina(servidor, navegador):
    contexto = navegador.new_context(viewport={"width": 1500, "height": 900}, color_scheme="dark")
    pg = contexto.new_page()
    pg.erros = []
    pg.on("pageerror", lambda e: pg.erros.append(str(e)))
    pg.goto(servidor["url"])
    pg.wait_for_load_state("networkidle")
    yield pg
    contexto.close()
    assert not pg.erros, f"Erros de JavaScript na página: {pg.erros}"
