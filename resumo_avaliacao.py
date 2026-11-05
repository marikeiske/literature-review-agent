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
from agente.config import PASTA_FICHAMENTOS, PASTA_LOGS, RAIZ

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


def pass_k(tentativas: dict[str, list[int]], k: int) -> tuple[int, int, int]:
    """pass^k e pass@k (Aula 12, slide 41; Anthropic, 2026).

    tentativas: id -> acertos (1/0) na ordem das tentativas. Só contam perguntas com k tentativas.
    Devolve (perguntas com k tentativas, quantas passaram nas k, quantas passaram em pelo menos uma)."""
    completas = {i: v[:k] for i, v in tentativas.items() if len(v) >= k}
    return len(completas), sum(all(v) for v in completas.values()), sum(any(v) for v in completas.values())


def ler_tentativas(arquivo) -> tuple[dict[str, list[int]], Counter]:
    """Lê resultados/negk_*.csv: acertos por pergunta (ordem das tentativas) e as paradas."""
    por_id, paradas = {}, Counter()
    with open(arquivo, encoding="utf-8-sig") as f:
        linhas = sorted(csv.DictReader(f, delimiter=";"), key=lambda l: (l["id"], int(l["tentativa"])))
    for l in linhas:
        por_id.setdefault(l["id"], []).append(int(l["acerto"]))
        paradas[l["parada"]] += 1
    return por_id, paradas


def texto_pass_k(arquivo, k: int | None = None) -> str:
    por_id, paradas = ler_tentativas(arquivo)
    k = k or min((len(v) for v in por_id.values()), default=0)
    n, todas, alguma = pass_k(por_id, k)
    total = sum(len(v) for v in por_id.values())
    acertos = sum(sum(v) for v in por_id.values())
    return (f"{arquivo.stem.removeprefix('negk_')}: k = {k}, perguntas com k tentativas: {n}. "
            f"pass^{k}: {pct(todas, n)} (IC 95% {wilson(todas, n)}); pass@{k}: {pct(alguma, n)}; "
            f"tentativas certas: {pct(acertos, total)}. Paradas: " + ", ".join(f"{m} {c}" for m, c in paradas.most_common()))


# Rubrica binária (Aula 12, slide 30): passa ou falha, sem meio-termo. "Parcial" conta como falha.
PASSA_HUMANO = {"Confere"}


def binario_humano(revs: dict, ids) -> tuple[int, int]:
    """(passa, revisadas) de uma revisão humana, com Parcial e Não confere como falha."""
    marcadas = [revs[i]["status"] for i in ids if revs.get(i, {}).get("status")]
    return sum(m in PASSA_HUMANO for m in marcadas), len(marcadas)


def caminho_dos_logs(pasta=None) -> dict | None:
    """Métrica de caminho (Aula 12, slide 38), lida dos logs locais.

    Conta só as perguntas que chegaram a uma resposta do modelo: pergunta com erro do provedor
    (cota, rede) ou sem chamada ao LLM fica de fora e é contada à parte. Para as que ficam:
    buscas e leituras por pergunta, quantas acionaram a trava de tools, quantas foram respondidas
    sem nenhuma busca (a partir de 05/11 elas param como falha tratada), ramos de erro e pedidos
    fora da lista permitida. Os logs ficam só na máquina da autora (logs/ está no .gitignore);
    sem eles, devolve None."""
    pasta = pasta or PASTA_LOGS
    arquivos = sorted(pasta.glob("sessao_*.jsonl")) if pasta.exists() else []
    if not arquivos:
        return None
    buscas, trava, erro, negada, sem_resposta = Counter(), 0, 0, 0, 0
    for arq in arquivos:
        blocos, atual = [], None
        with open(arq, encoding="utf-8") as f:
            for linha in f:
                try:
                    ev = json.loads(linha)
                except json.JSONDecodeError:
                    continue
                if ev.get("tipo") == "pergunta":
                    atual = []
                    blocos.append(atual)
                elif atual is not None:
                    atual.append(ev)
        for bloco in blocos:
            tipos = [e.get("tipo") for e in bloco]
            if "erro" in tipos or "chamada_llm" not in tipos:
                sem_resposta += 1
                continue
            buscas[sum(1 for e in bloco if e.get("tipo") == "tool" and e.get("nome") in ("buscar_trechos", "ler_pagina"))] += 1
            trava += "trava" in tipos
            erro += "ramo_de_erro" in tipos
            negada += tipos.count("permissao_negada")
    perguntas = sum(buscas.values())
    total = sum(k * v for k, v in buscas.items())
    return {"perguntas": perguntas, "sem_resposta": sem_resposta, "media_buscas": total / perguntas if perguntas else 0,
            "distribuicao": dict(sorted(buscas.items())), "sem_busca": buscas.get(0, 0), "trava": trava,
            "ramo_de_erro": erro, "permissao_negada": negada}


def separar_suites(rodadas: dict, ids) -> dict:
    """Suítes de capacidade e de regressão (Aula 12, slides 39 e 40).

    rodadas: (modelo, condição) -> {id: acertou}. Só entram rodadas RAG completas.
    Regressão: afirmações que todas as rodadas acertaram; a taxa deve ficar perto de 100%, e uma
    queda aponta uma mudança que quebrou o que já passava. Capacidade: afirmações que pelo menos
    uma rodada errou (falhas reais); é a suíte que mede melhoria."""
    completas = [v for (m, c), v in rodadas.items() if c == "rag" and set(ids) <= v.keys()]
    capacidade = sorted(i for i in ids if any(not v[i] for v in completas))
    regressao = sorted(i for i in ids if completas and all(v[i] for v in completas))
    return {"rodadas_usadas": len(completas), "capacidade": capacidade, "regressao": regressao}


def pct(n, d):
    return f"{n}/{d} ({100 * n / d:.0f}%)" if d else "–"


def nome_modelo(stem):
    return revisao.NOMES_MODELOS.get(stem, stem)


def main():
    gab = {g["id"]: g for g in avaliar.carregar_gabarito()}
    original = {g["id"]: set(g["paginas"]) for g in revisao.ler_gabarito()}
    out = [f"# Números da avaliação (gerado em {time.strftime('%Y-%m-%d')} por resumo_avaliacao.py)", "",
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

    # ---- suítes de capacidade e regressão ----
    suites = separar_suites(rodadas, gab.keys())
    (PASTA / "suites.json").write_text(json.dumps({"gerado_em": time.strftime("%Y-%m-%d"), **suites},
                                                  ensure_ascii=False, indent=1), encoding="utf-8")
    out += ["## Suítes de capacidade e regressão (Aula 12, slides 39 e 40)", "",
            f"A partir das {suites['rodadas_usadas']} rodadas RAG completas (resultados/suites.json):", "",
            f"- Regressão: {len(suites['regressao'])} afirmações que todos os modelos acertaram. Depois de mudar prompt, "
            "harness ou modelo, rodar `python avaliar.py <modelo> --suite regressao`: a taxa deve ficar perto de 100%.",
            f"- Capacidade: {len(suites['capacidade'])} afirmações que pelo menos um modelo errou "
            f"({', '.join(suites['capacidade'])}). É aqui que uma melhoria aparece: `--suite capacidade`.", ""]

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

    # ---- pass^k ----
    negk = sorted(PASTA.glob("negk_*.csv"))
    if negk:
        out += ["", "## Negativas repetidas: pass^k (Aula 12, slide 41)", "",
                "Cada negativa rodou k vezes nas condições de uso. pass^k: as k tentativas passaram; "
                "pass@k: pelo menos uma passou. Para a recusa, a métrica é pass^k.", ""]
        out += [f"- {texto_pass_k(arq)}" for arq in negk]

    # ---- caso da sala (Aula 11, data.zip) ----
    aula11 = sorted(PASTA.glob("aula11_*.csv"))
    if aula11:
        from experimentos import aula11_norma
        out += ["", "## Caso da sala: test.jsonl da Aula 11, modelo base sem LoRA (grader de código)", "",
                "Trecho na mensagem, sem busca. Passa: parágrafo citado está no trecho, ou a resposta é exatamente "
                "\"not in the material.\"; \"ao juiz\": recusa com outras palavras (Aula 12, slide 34).", ""]
        out += [f"- {aula11_norma.resumo(arq)}" for arq in aula11]

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

    # ---- rubrica por critério (Aula 12, slides 30 e 31) ----
    out += ["", "## Rubrica binária, um critério por vez (Aula 12, slides 30 e 31)", "",
            "Passa ou falha em cada critério, sem somar critérios num número só. Na revisão humana, "
            "\"Parcial\" conta como falha.", ""]
    if amostra:
        ok, n = binario_humano(revs_s, {x["id"] for x in amostra})
        out.append(f"- **Sustentado** (a frase diz só o que a página citada diz; juiz: a autora, amostra de {len(amostra)} do "
                   f"{nome_modelo(revisao.SENTIDO_RODADA.removeprefix('aval_').partition('_')[2].removesuffix('_rag'))}): "
                   f"{pct(ok, n)}, IC 95% {wilson(ok, n)}.")
    linhas_cit = []
    for arq in sorted(PASTA.glob("aval_*_rag.csv")):
        feitas = [l for i, l in avaliar.ler_feitas(arq).items() if i in gab]
        if feitas:
            ok = sum(1 for l in feitas if not int(l["grounding_falso"]))
            linhas_cit.append(f"{nome_modelo(arq.stem.removeprefix('aval_').removesuffix('_rag').partition('_')[2])} {pct(ok, len(feitas))}")
    out.append("- **Citação identificável** (toda página citada foi devolvida por uma ferramenta no mesmo turno; juiz: código, "
               "verificador.py; só na condição RAG): " + "; ".join(linhas_cit) + ".")
    linhas_rec = []
    for arq in sorted(PASTA.glob("neg_*.csv")):
        if arq.stem.endswith("_bruto"):
            continue
        with open(arq, encoding="utf-8-sig") as f:
            ids = {l["id"] for l in csv.DictReader(f, delimiter=";")}
        ok, n = binario_humano(revisao.ler_revisoes(PASTA / f"revisao_{arq.stem}.csv"), ids)
        if n:
            linhas_rec.append(f"{revisao._rotulo_negativas(arq.stem).removeprefix('Negativas · ')} {pct(ok, n)}")
    out.append("- **Recusa** (recusa, ou corrige a premissa, quando o material não sustenta; juiz: a autora, uma tentativa por "
               "pergunta; a repetição está em pass^k): " + "; ".join(linhas_rec) + ".")
    fich = len(list(PASTA_FICHAMENTOS.glob("*.md"))) if PASTA_FICHAMENTOS.exists() else None
    out.append("- **Revisão antes da ação** (nada é gravado sem a decisão humana): garantido pelo fluxo "
               "(hitl.py e /api/decisao gravam só depois de \"aprovar\"; recusa, falha tratada e limite não chamam o humano, "
               "tests/test_harness.py)" + (f"; fichamentos gravados nesta máquina: {fich}." if fich is not None else "."))
    cam = caminho_dos_logs()
    if cam:
        dist = ", ".join(f"{k} busca(s): {v}" for k, v in cam["distribuicao"].items())
        out += ["", "## Caminho (Aula 12, slide 38), dos logs locais", "",
                f"- Perguntas com resposta do modelo: {cam['perguntas']} (fora: {cam['sem_resposta']} com erro do provedor "
                f"ou sem chamada). Buscas e leituras por pergunta: média {cam['media_buscas']:.1f} ({dist}).",
                f"- Respondidas sem nenhuma busca: {cam['sem_busca']} (desde 05/11 param como falha tratada) · "
                f"trava de tools disparada: {cam['trava']} · ramo de erro: {cam['ramo_de_erro']} · "
                f"pedidos fora da lista permitida: {cam['permissao_negada']}.",
                "- Os logs incluem as rodadas de avaliação e o uso na interface. Ramo de erro e lista permitida só "
                "entram nos logs a partir de 05/11/2026."]

    # ---- HITL do gabarito ----
    revs = revisao.ler_revisoes(revisao.ARQ_REV_GABARITO)
    pre = json.loads(revisao.ARQ_PRE_CONFERENCIA.read_text(encoding="utf-8"))["itens"]
    st = Counter(r["status"] for i, r in revs.items() if i in gab)
    cruz = Counter((pre.get(i, {}).get("sugestao"), r["status"]) for i, r in revs.items() if i in gab)
    muda_pag = [i for i, r in revs.items() if r["status"] == "Corrigir" and revisao.paginas_corrigidas(r["comentario"])]
    out += ["", "## Revisão humana do gabarito (HITL)", "",
            f"- Revisadas: {sum(st.values())} de {len(gab)}. " + ", ".join(f"{k}: {v}" for k, v in st.items()),
            f"- Correções que mudam a página: {len(muda_pag)} ({', '.join(sorted(muda_pag))}); as outras corrigem o texto da paráfrase.",
            "- Pré-conferência do Claude × decisão da autora: " + "; ".join(f"Claude {a} → autora {b}: {v}" for (a, b), v in sorted(cruz.items())),
            ""]
    destino = PASTA / "resumo_numeros.md"
    destino.write_text("\n".join(out), encoding="utf-8")
    print("\n".join(out))
    print(f"\nGravado em {destino}")


if __name__ == "__main__":
    main()
