"""Gera resultados/resumo_numeros.md: todos os números da avaliação, recalculados dos CSVs.

Nada aqui é digitado à mão: cada número sai de resultados/*.csv, revisao_gabarito.csv e
pre_conferencia_gabarito.json, com o gabarito revisado pela autora (avaliar.repontuar).
O artigo deve citar este arquivo e a data em que foi gerado.

Uso: python resumo_avaliacao.py
"""
import csv
import json
import re
import time
from collections import Counter

import avaliar
import revisao
from agente.config import RAIZ

PASTA = RAIZ / "resultados"
# Correções de página feitas DEPOIS de ver as respostas dos modelos (21–23/10): podem inflar o acerto.
# A coluna "antes de ver respostas" mede com a página original da planilha nesses itens.
POS_RESPOSTAS = {"A1-08", "A8-11", "A9-02"}
MARCADOR = re.compile(r"<<<\s*P[ÁA]GINA", re.I)
# Citação de várias páginas, fora do formato pedido no prompt: [Lozano2023 p.14, 15, 16], [X p.7-8]
MULTI = re.compile(r"\[\s*([A-Za-z][A-Za-z\-]*\d{4})\s*,?\s*p(?:ág)?\.?\s*(\d+(?:\s*(?:,|[–-]|\be\b)\s*\d+)+)\s*\]")


def paginas_multi(resposta, artigo):
    pags = set()
    for a, trecho in MULTI.findall(resposta or ""):
        if a == artigo:
            pags.update(revisao.paginas_corrigidas("p. " + trecho))
    return pags


def pct(n, d):
    return f"{n}/{d} ({100 * n / d:.0f}%)" if d else "–"


def nome_modelo(stem):
    return revisao.NOMES_MODELOS.get(stem, stem)


def main():
    gab = {g["id"]: g for g in avaliar.carregar_gabarito()}
    original = {g["id"]: set(g["paginas"]) for g in revisao.ler_gabarito()}
    out = [f"# Números da avaliação (gerado em {time.strftime('%Y-%m-%d %H:%M')} por resumo_avaliacao.py)", "",
           f"Gabarito: {len(gab)} afirmações, com a revisão da autora aplicada (revisao_gabarito.csv).", ""]

    # ---- afirmações ----
    out += ["## Afirmações do gabarito (página citada)", "",
            "| Modelo | Condição | Avaliadas | Página exata | Exata antes de ver respostas* | ±1 página | Exata lendo citações de várias páginas | "
            "Citações de várias páginas | Recusas | Citou página não lida | Número ausente | Copiou marcador <<<PÁGINA N>>> | Exata início/meio/fim |",
            "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for arq in sorted(PASTA.glob("aval_*.csv")):
        if arq.stem.endswith("_piloto"):
            continue
        provedor_modelo, condicao = arq.stem.removeprefix("aval_").rsplit("_", 1)
        linhas = [avaliar.repontuar(l, gab[i]) for i, l in avaliar.ler_feitas(arq).items() if i in gab]
        n = len(linhas)
        soma = lambda c: sum(int(l[c]) for l in linhas)
        multi = flex = cego = 0
        marcador = sum(bool(MARCADOR.search(l["resposta"] or "")) for l in linhas)
        pos = Counter(); pos_ok = Counter()
        for l in linhas:
            g = gab[l["id"]]
            pm = paginas_multi(l["resposta"], g["artigo"])
            multi += bool(pm)
            citadas = {int(x) for x in str(l["paginas_citadas"] or "").split()}
            ref = original[l["id"]] if l["id"] in POS_RESPOSTAS else g["paginas"]
            cego += bool(citadas & ref)
            flex += int(l["acerto_exato"]) or bool(pm & g["paginas"])
            pos[g["posicao"]] += 1; pos_ok[g["posicao"]] += int(l["acerto_exato"])
        posicoes = " / ".join(pct(pos_ok[p], pos[p]) for p in ("início", "meio", "fim"))
        nome = nome_modelo(provedor_modelo.partition("_")[2])
        out.append(f"| {nome} | {condicao} | {n} | {pct(soma('acerto_exato'), n)} | {pct(cego, n)} | {pct(soma('acerto_vizinha'), n)} | "
                   f"{pct(flex, n)} | {multi} | {soma('recusa')} | {soma('grounding_falso')} | {soma('numero_ausente')} | {marcador} | {posicoes} |")
    out += ["", "Na condição contexto o artigo inteiro vai no prompt, então toda página conta como lida: "
            "\"citou página não lida\" é zero por construção e não se compara com o RAG. "
            "Quando o modelo copia o marcador <<<PÁGINA N>>> na resposta, o verificador lê N como número da frase "
            "e pode marcar \"número ausente\" por engano: compare as duas colunas.", "",
            f"\\* Sem as correções de página feitas depois de ver as respostas dos modelos ({', '.join(sorted(POS_RESPOSTAS))}): "
            "nesses itens vale a página original da planilha.", ""]

    # ---- negativas ----
    out += ["## Perguntas negativas (12: recusar ou corrigir a premissa)", "",
            "| Modelo | Acerto automático | Inventou | Recusou sem ler | Revisão humana: Confere / Parcial / Não confere |",
            "|---|---|---|---|---|"]
    for arq in sorted(PASTA.glob("neg_*.csv")):
        if arq.stem.endswith("_bruto"):
            continue
        itens = {}
        with open(arq, encoding="utf-8-sig") as f:
            for l in csv.DictReader(f, delimiter=";"):
                itens.setdefault(l["id"], l)
        n = len(itens)
        s = lambda c: sum(l[c] == "1" for l in itens.values())
        revs = revisao.ler_revisoes(PASTA / f"revisao_{arq.stem}.csv")
        c = Counter(r["status"] for i, r in revs.items() if i in itens and r.get("status"))
        humano = f"{c['Confere']} / {c['Parcial']} / {c['Não confere']} (de {sum(c.values())} revisadas)" if c else "não revisada"
        out.append(f"| {revisao._rotulo_negativas(arq.stem).removeprefix('Negativas · ')} | {pct(s('acerto'), n)} | "
                   f"{s('inventou')} | {s('recusa_sem_ler')} | {humano} |")

    # ---- HITL do gabarito ----
    revs = revisao.ler_revisoes(revisao.ARQ_REV_GABARITO)
    pre = json.loads(revisao.ARQ_PRE_CONFERENCIA.read_text(encoding="utf-8"))["itens"]
    st = Counter(r["status"] for i, r in revs.items() if i in gab)
    cruz = Counter((pre.get(i, {}).get("sugestao"), r["status"]) for i, r in revs.items() if i in gab)
    muda_pag = [i for i, r in revs.items() if r["status"] == "Corrigir" and revisao.paginas_corrigidas(r["comentario"])]
    datas = sorted(r["quando"] for r in revs.values() if r.get("quando"))
    out += ["", "## Revisão humana do gabarito (HITL)", "",
            f"- Revisadas: {sum(st.values())} de {len(gab)} ({datas[0]} a {datas[-1]}). " + ", ".join(f"{k}: {v}" for k, v in st.items()),
            f"- Correções que mudam a página: {len(muda_pag)} ({', '.join(sorted(muda_pag))}); as outras corrigem o texto da paráfrase.",
            "- Pré-conferência do Claude × decisão da autora: " + "; ".join(f"Claude {a} → autora {b}: {v}" for (a, b), v in sorted(cruz.items())),
            ""]
    destino = PASTA / "resumo_numeros.md"
    destino.write_text("\n".join(out), encoding="utf-8")
    print("\n".join(out))
    print(f"\nGravado em {destino}")


if __name__ == "__main__":
    main()
