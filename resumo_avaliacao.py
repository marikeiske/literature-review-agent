"""Gera resultados/resumo_numeros.md: todos os números da avaliação, recalculados dos CSVs.

Nada aqui é digitado à mão: cada número sai de resultados/*.csv, revisao_gabarito.csv e
pre_conferencia_gabarito.json, com o gabarito revisado pela autora (avaliar.repontuar).
O artigo deve citar este arquivo e a data em que foi gerado.

Uso: python resumo_avaliacao.py
"""
import csv
import json
import math
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


def wilson(k, n, z=1.96):
    """Intervalo de confiança de 95% de Wilson para uma proporção k/n (em %)."""
    if not n:
        return "–"
    p = k / n
    centro = (p + z * z / (2 * n)) / (1 + z * z / n)
    meia = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return f"{100 * (centro - meia):.0f}–{100 * (centro + meia):.0f}%"


def mcnemar(a: dict, b: dict):
    """McNemar exato (binomial, bicaudal) para acertos pareados por afirmação.
    Devolve (n em comum, só A acertou, só B acertou, p)."""
    ids = a.keys() & b.keys()
    so_a = sum(1 for i in ids if a[i] and not b[i])
    so_b = sum(1 for i in ids if b[i] and not a[i])
    n = so_a + so_b
    if not n:
        return len(ids), 0, 0, 1.0
    p = 2 * sum(math.comb(n, k) for k in range(min(so_a, so_b) + 1)) / 2 ** n
    return len(ids), so_a, so_b, min(p, 1.0)


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
            "| Modelo | Condição | Avaliadas | Página exata | IC 95% (Wilson) | Exata antes de ver respostas* | ±1 página | Exata lendo citações de várias páginas | "
            "Citações de várias páginas | Recusas | Citou página não lida | Número ausente | Copiou marcador <<<PÁGINA N>>> | Exata início/meio/fim | "
            "Chamadas ao LLM por afirmação | Segundos por afirmação |",
            "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    rodadas = {}  # (nome, condicao) -> {id: acertou}
    for arq in sorted(PASTA.glob("aval_*.csv")):
        if arq.stem.endswith("_piloto"):
            continue
        provedor_modelo, condicao = arq.stem.removeprefix("aval_").rsplit("_", 1)
        linhas = [avaliar.repontuar(l, gab[i]) for i, l in avaliar.ler_feitas(arq).items() if i in gab]
        n = len(linhas)
        soma = lambda c, linhas=linhas: sum(int(l[c]) for l in linhas)
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
        rodadas[(nome, condicao)] = {l["id"]: int(l["acerto_exato"]) for l in linhas}
        media = lambda c, linhas=linhas, n=n: sum(float(l.get(c) or 0) for l in linhas) / n if n else 0
        out.append(f"| {nome} | {condicao} | {n} | {pct(soma('acerto_exato'), n)} | {wilson(soma('acerto_exato'), n)} | {pct(cego, n)} | {pct(soma('acerto_vizinha'), n)} | "
                   f"{pct(flex, n)} | {multi} | {soma('recusa')} | {soma('grounding_falso')} | {soma('numero_ausente')} | {marcador} | {posicoes} | {media('chamadas'):.1f} | {media('segundos'):.1f} |")
    out += ["", "Na condição contexto o artigo inteiro vai no prompt, então toda página conta como lida: "
            "\"citou página não lida\" é zero por construção e não se compara com o RAG. "
            "Quando o modelo copia o marcador <<<PÁGINA N>>> na resposta, o verificador lê N como número da frase "
            "e pode marcar \"número ausente\" por engano: compare as duas colunas.", "",
            f"\\* Sem as correções de página feitas depois de ver as respostas dos modelos ({', '.join(sorted(POS_RESPOSTAS))}): "
            "nesses itens vale a página original da planilha.", ""]

    # ---- comparações pareadas ----
    out += ["## Comparações pareadas (McNemar exato, bicaudal)", "",
            "Mesmas afirmações nos dois lados; conta só as que um acertou e o outro errou. "
            "p < 0,05: diferença que dificilmente é acaso. Com 109 itens, diferenças de 2 a 4 acertos costumam não passar.", "",
            "| Comparação | Afirmações em comum | Só o 1º acertou | Só o 2º acertou | p | Diferença real (p < 0,05)? |",
            "|---|---|---|---|---|---|"]
    pares = [((m, "rag"), (m, "contexto")) for (m, c) in rodadas if c == "contexto" and (m, "rag") in rodadas]
    rag = sorted((k for k in rodadas if k[1] == "rag" and len(rodadas[k]) == len(gab)),
                 key=lambda k: -sum(rodadas[k].values()))
    if rag:
        pares += [(rag[0], k) for k in rag[1:]]
    for a, b in pares:
        n_, so_a, so_b, p = mcnemar(rodadas[a], rodadas[b])
        out.append(f"| {a[0]} ({a[1]}) × {b[0]} ({b[1]}) | {n_} | {so_a} | {so_b} | {p:.3f} | {'sim' if p < 0.05 else 'não'} |")
    out.append("")

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
        s = lambda c, itens=itens: sum(l[c] == "1" for l in itens.values())
        revs = revisao.ler_revisoes(PASTA / f"revisao_{arq.stem}.csv")
        c = Counter(r["status"] for i, r in revs.items() if i in itens and r.get("status"))
        humano = f"{c['Confere']} / {c['Parcial']} / {c['Não confere']} (de {sum(c.values())} revisadas)" if c else "não revisada"
        out.append(f"| {revisao._rotulo_negativas(arq.stem).removeprefix('Negativas · ')} | {pct(s('acerto'), n)} | "
                   f"{s('inventou')} | {s('recusa_sem_ler')} | {humano} |")

    # ---- revisão de sentido ----
    try:
        amostra = revisao.itens_sentido()
    except FileNotFoundError:
        amostra = []
    if amostra:
        revs_s = revisao.ler_revisoes(revisao.arquivo_revisao(f"sentido:{revisao.SENTIDO_RODADA}"))
        c = Counter(r["status"] for i, r in revs_s.items() if i in {x["id"] for x in amostra} and r.get("status"))
        feitas = sum(c.values())
        out += ["", f"## Revisão de sentido ({revisao.SENTIDO_RODADA}, amostra de {len(amostra)}, semente {revisao.SENTIDO_SEMENTE})", "",
                "A página citada sustenta a afirmação? (julgamento humano do conteúdo, não só do número da página)", "",
                f"- Revisadas: {feitas} de {len(amostra)}. Confere: {c['Confere']}, Parcial: {c['Parcial']}, Não confere: {c['Não confere']}."
                + (f" Confere: {pct(c['Confere'], feitas)}, IC 95% {wilson(c['Confere'], feitas)}." if feitas else ""), ""]

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
