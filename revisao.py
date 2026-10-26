"""Revisão humana (HITL) da avaliação: gabarito e respostas às perguntas negativas.

A tela "Revisar" da interface (app.py) grava aqui as decisões da autora. Cada decisão é
uma linha de CSV com data e hora, para o artigo poder dizer quem revisou o quê e quando.

  revisao_gabarito.csv                  Status de cada afirmação do gabarito
                                        (Aprovada, Corrigir, Rejeitar) e a correção.
                                        Substitui a coluna Status da planilha, que fica
                                        como valor inicial.
  resultados/revisao_<neg_...>.csv      Confere, Parcial ou Não confere para cada
                                        resposta negativa de uma rodada.

avaliar.py lê revisao_gabarito.csv: afirmação "Rejeitar" sai da avaliação; em "Corrigir",
se a correção traz páginas ("p. 2", "p. 2–3", "p. 1, 2, 8"), elas passam a valer.

pre_conferencia_gabarito.json é a pré-conferência feita pelo Claude (sugestão e trecho literal
da página). Aparece na tela como rascunho; não conta como revisão e não entra na avaliação.
"""
import csv
import json
import os
import re
import threading
import time
from pathlib import Path

import openpyxl

from agente.config import RAIZ
from agente.corpus import ARTIGOS

ARQ_GABARITO = RAIZ / "gabarito-corpus-avaliacao.xlsx"
ARQ_REV_GABARITO = RAIZ / "revisao_gabarito.csv"
ARQ_PRE_CONFERENCIA = RAIZ / "pre_conferencia_gabarito.json"  # rascunho do Claude, não é revisão
PASTA_RESULTADOS = RAIZ / "resultados"
OPCOES = {"gabarito": ["Aprovada", "Corrigir", "Rejeitar"],
          "negativas": ["Confere", "Parcial", "Não confere"],
          "sentido": ["Confere", "Parcial", "Não confere"]}
# Revisão de sentido: a avaliação automática só confere o NÚMERO da página. Aqui a autora julga, numa
# amostra fixa, se a página citada sustenta mesmo a afirmação (inclusive quando a página difere do gabarito).
SENTIDO_RODADA = "aval_ollama_nemotron-3-ultra_cloud_rag"  # melhor modelo na avaliação de 26/10
SENTIDO_AMOSTRA = 30
SENTIDO_SEMENTE = 2026
CAMPOS = ["id", "status", "comentario", "quando"]
_trava = threading.Lock()


# ---------- páginas ----------
def paginas_de(texto) -> list[int]:
    """'p. 7' -> [7]; 'p. 7–8' -> [7, 8]; 'p. 3, 5' -> [3, 5]."""
    texto = str(texto or "")
    nums = [int(n) for n in re.findall(r"\d+", texto)]
    if not nums:
        return []
    if re.search(r"\d\s*[–-]\s*\d", texto):
        return list(range(nums[0], nums[-1] + 1))
    return sorted(set(nums))


def paginas_corrigidas(comentario: str) -> list[int]:
    """Páginas escritas na correção: 'p. 2', 'p. 30–31', 'p. 1, 2, 8', 'p. 2 e 3'. Vazio se não houver."""
    # Exige "p." ou "pág."/"página": sem o ponto, "Tesla P100" virava página 100 (achado em 21/10).
    m = re.search(r"\b(?:p\.|pág\.?|página)\s*(\d+(?:\s*(?:[–-]|,|\be\b)\s*\d+)*)", comentario or "", re.I)
    if not m:
        return []
    pags = set()
    for parte in re.split(r"\s*(?:,|\be\b)\s*", m.group(1)):
        nums = [int(n) for n in re.findall(r"\d+", parte)]
        if len(nums) == 2:
            pags.update(range(nums[0], nums[1] + 1))
        elif nums:
            pags.add(nums[0])
    return sorted(pags)


# ---------- leitura e gravação das decisões ----------
def ler_revisoes(arquivo: Path) -> dict[str, dict]:
    if not arquivo.exists():
        return {}
    with open(arquivo, encoding="utf-8-sig") as f:
        return {l["id"]: l for l in csv.DictReader(f, delimiter=";")}


def gravar_revisao(arquivo: Path, id_: str, status: str, comentario: str) -> dict:
    with _trava:
        revs = ler_revisoes(arquivo)
        linha = {"id": id_, "status": status, "comentario": comentario.strip(),
                 "quando": time.strftime("%Y-%m-%d %H:%M")}
        revs[id_] = linha
        tmp = arquivo.with_suffix(".tmp")
        with open(tmp, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=CAMPOS, delimiter=";")
            w.writeheader()
            for l in sorted(revs.values(), key=lambda x: x["id"]):
                w.writerow({k: l.get(k, "") for k in CAMPOS})
        os.replace(tmp, arquivo)
    return linha


# ---------- conjuntos ----------
def ler_gabarito() -> list[dict]:
    """Todas as afirmações da planilha, inclusive as rejeitadas."""
    wb = openpyxl.load_workbook(ARQ_GABARITO, data_only=True)
    linhas = list(wb["Gabarito"].iter_rows(values_only=True))
    cab = {nome: i for i, nome in enumerate(linhas[0])}
    itens = []
    for r in linhas[1:]:
        if not r[cab["ID"]]:
            continue
        pag = r[cab["Página(s) no PDF"]]
        itens.append({
            "id": r[cab["ID"]], "artigo": ARTIGOS[int(r[cab["Artigo"]]) - 1]["id"],
            "tipo": r[cab["Tipo"]] or "", "posicao": r[cab["Posição"]] or "",
            "texto": r[cab["Afirmação (paráfrase)"]] or "", "paginas_texto": str(pag or ""),
            "paginas": paginas_de(pag), "status_planilha": (r[cab["Status"]] or "").strip(),
            "comentario_planilha": r[cab["Correção / comentário"]] or "",
            "observacao": r[cab["Observação"]] or ""})
    return itens


def _arquivos_negativas() -> list[Path]:
    return [p for p in sorted(PASTA_RESULTADOS.glob("neg_*.csv")) if not p.stem.endswith("_bruto")]


NOMES_MODELOS = {"openai_gpt-oss-120b": "GPT-OSS 120B (Groq)", "qwen_qwen3.8-27b": "Qwen3.8 27B (Groq)",
                 "gemini-flash-lite-latest": "Gemini Flash-Lite (Google)", "qwen3_1.7b": "Qwen3 1,7B",
                 "nvidia_nemotron-3-super-120b-a12b_free": "Nemotron 3 Super",
                 "nvidia_nemotron-3-ultra-550b-a55b_free": "Nemotron 3 Ultra",
                 "bonsai-2_4b": "Bonsai 2 4B (local)",
                 "gemma4_31b-cloud": "Gemma 4 31B (Ollama Cloud)",
                 "minimax-m3.1-flash_cloud": "MiniMax M3.1 Flash (Ollama Cloud)",
                 "gpt-oss_120b-cloud": "GPT-OSS 120B (Ollama Cloud)",
                 "nemotron-3-ultra_cloud": "Nemotron 3 Ultra (Ollama Cloud)"}


def _rotulo_negativas(stem: str) -> str:
    """'neg_gemini_gemini-flash-lite-latest_v2' -> 'Negativas · Gemini Flash-Lite (v2)'."""
    nome = stem.removeprefix("neg_").partition("_")[2]
    versao = ""
    m = re.search(r"_(v\d+)$", nome)
    if m:
        versao, nome = f" ({m.group(1)})", nome[: m.start()]
    return f"Negativas · {NOMES_MODELOS.get(nome, nome)}{versao}"


def arquivo_revisao(conjunto: str) -> Path:
    if conjunto == "gabarito":
        return ARQ_REV_GABARITO
    if conjunto.startswith("sentido:"):
        stem = conjunto.removeprefix("sentido:")
        if stem != SENTIDO_RODADA or not (PASTA_RESULTADOS / f"{stem}.csv").exists():
            raise ValueError("Conjunto desconhecido.")
        return PASTA_RESULTADOS / f"revisao_sentido_{stem}.csv"
    stem = conjunto.removeprefix("neg:")
    if not re.fullmatch(r"neg_[\w.-]+", stem) or not (PASTA_RESULTADOS / f"{stem}.csv").exists():
        raise ValueError("Conjunto desconhecido.")
    return PASTA_RESULTADOS / f"revisao_{stem}.csv"


def _contar(revs: dict, ids: set) -> int:
    return sum(1 for i, r in revs.items() if i in ids and r.get("status"))


def conjuntos() -> list[dict]:
    gab = ler_gabarito()
    ids = {g["id"] for g in gab}
    saida = [{"id": "gabarito", "rotulo": f"Gabarito · {len(gab)} afirmações", "total": len(gab),
              "revisadas": _contar(ler_revisoes(ARQ_REV_GABARITO), ids)}]
    if (PASTA_RESULTADOS / f"{SENTIDO_RODADA}.csv").exists():
        cid = f"sentido:{SENTIDO_RODADA}"
        itens = itens_sentido()
        saida.append({"id": cid, "rotulo": f"Sentido · {NOMES_MODELOS.get('nemotron-3-ultra_cloud')} · amostra de {len(itens)}",
                      "total": len(itens), "revisadas": _contar(ler_revisoes(arquivo_revisao(cid)), {i["id"] for i in itens})})
    for arq in _arquivos_negativas():
        itens = itens_negativas(arq)
        saida.append({"id": f"neg:{arq.stem}", "rotulo": _rotulo_negativas(arq.stem), "total": len(itens),
                      "revisadas": _contar(ler_revisoes(arquivo_revisao(f"neg:{arq.stem}")),
                                           {i["id"] for i in itens})})
    return saida


def itens_negativas(arq: Path) -> list[dict]:
    from negativas import NEGATIVAS
    esperado = {n["id"]: n["esperado"] for n in NEGATIVAS}
    linhas = {}
    with open(arq, encoding="utf-8-sig") as f:
        for l in csv.DictReader(f, delimiter=";"):
            linhas.setdefault(l["id"], l)  # id repetido: vale a primeira execução
    itens = []
    for l in sorted(linhas.values(), key=lambda x: x["id"]):
        marcas = [m for m, c in (("recusou", "recusou"), ("corrigiu", "corrigiu"), ("inventou", "inventou"),
                                 ("recusou sem ler", "recusa_sem_ler")) if l.get(c) == "1"]
        itens.append({"id": l["id"], "tipo": l["tipo"], "modo": l["modo"], "pergunta": l["pergunta"],
                      "esperado": esperado.get(l["id"], ""), "resposta": l["resposta"],
                      "acerto": l["acerto"] == "1", "marcas": marcas})
    return itens


def itens_sentido() -> list[dict]:
    """Amostra fixa (semente 2026) de respostas do melhor modelo, com a afirmação do gabarito."""
    import random
    gab = {g["id"]: g for g in ler_gabarito()}
    linhas = {}
    with open(PASTA_RESULTADOS / f"{SENTIDO_RODADA}.csv", encoding="utf-8-sig") as f:
        for l in csv.DictReader(f, delimiter=";"):
            if l["id"] in gab:
                linhas.setdefault(l["id"], l)
    ids = sorted(linhas)
    amostra = sorted(random.Random(SENTIDO_SEMENTE).sample(ids, min(SENTIDO_AMOSTRA, len(ids))),
                     key=lambda i: (int(i[1:].split("-")[0]), i))
    return [{"id": i, "artigo": gab[i]["artigo"], "tipo": gab[i]["tipo"], "posicao": gab[i]["posicao"],
             "texto": gab[i]["texto"], "resposta": linhas[i]["resposta"],
             "paginas_citadas": linhas[i]["paginas_citadas"]} for i in amostra]


def carregar(conjunto: str) -> dict:
    arq = arquivo_revisao(conjunto)
    if conjunto == "gabarito":
        itens, tipo = ler_gabarito(), "gabarito"
        # Pré-conferência do Claude: sugestão + trecho literal da página. Só ajuda a revisar;
        # a decisão continua sendo da autora e só ela vai para revisao_gabarito.csv.
        if ARQ_PRE_CONFERENCIA.exists():
            pre = json.loads(ARQ_PRE_CONFERENCIA.read_text(encoding="utf-8")).get("itens", {})
            for it in itens:
                it["claude"] = pre.get(it["id"])
    elif conjunto.startswith("sentido:"):
        itens, tipo = itens_sentido(), "sentido"
    else:
        itens, tipo = itens_negativas(PASTA_RESULTADOS / f"{conjunto.removeprefix('neg:')}.csv"), "negativas"
    return {"conjunto": conjunto, "tipo": tipo, "opcoes": OPCOES[tipo], "itens": itens,
            "revisoes": ler_revisoes(arq), "arquivo": arq.relative_to(RAIZ).as_posix()}


def decidir(conjunto: str, id_: str, status: str, comentario: str) -> dict:
    dados = carregar(conjunto)
    if status and status not in dados["opcoes"]:
        raise ValueError("Opção inválida.")
    if id_ not in {i["id"] for i in dados["itens"]}:
        raise ValueError("Item desconhecido.")
    return gravar_revisao(arquivo_revisao(conjunto), id_, status, comentario)
