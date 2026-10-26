"""Verificador determinístico das citações (sem LLM, sem custo).

Para cada linha do fichamento, aplica as travas da Aula 10 (p. 66–70):
  - sem citação           -> a frase não tem fonte (exceto se for uma recusa)
  - recusa sem página lida -> disse "não consta" sem ter lido nenhuma página
                             (não buscou, ou a busca não achou nada)
  - página não lida       -> citou uma página que o agente não leu neste turno:
                             candidata a "grounding falso" (Aula 10, p. 67)
  - número ausente        -> a frase traz um número que não aparece na página citada
  - rastreável            -> a página citada foi lida e os números batem

"Rastreável" NÃO quer dizer que o trecho sustenta a frase. Isso só a pessoa
confere, no gate humano (hitl.py). O verificador é necessário, não suficiente.
"""
import re

from .corpus import ARTIGOS_POR_ID

CITACAO = re.compile(r"\[\s*([A-Za-z][A-Za-z\-]*\d{4})\s*,?\s*p(?:ág)?\.?\s*(\d+)\s*\]")
# Número isolado, inclusive colado em "x" ou "×" (fator de speedup, por exemplo "8x")
NUMERO = re.compile(r"(?<![\w.])\d+(?:[.,]\d+)?(?=(?:x|×)?(?:[^\w]|$))")
# Linha que é só título de seção: "**Resultados**", "**Método:**", "Resultados:"
TITULO = re.compile(r"^\*\*[^*\[\]]+\*\*:?$|^\*\*[^*\[\]]+:\*\*$|^[^\[\]]{1,60}:$")
RECUSA = re.compile(r"não consta|não está (?:sustentad|no material)|não encontrei", re.I)
# Correção de premissa falsa (regra 4 do system prompt). Não é recusa: a linha precisa de citação,
# senão o verificador a marca como "sem citação".
PREMISSA = re.compile(r"premissa não confere", re.I)


def _numeros(texto: str) -> set[str]:
    return {n.replace(",", ".") for n in NUMERO.findall(texto)}


def verificar(resposta: str, evidencias: dict[tuple[str, int], str]) -> list[dict]:
    resultado = []
    for linha in resposta.splitlines():
        # Tira só o marcador de lista ("- ", "* ", "• "), não o negrito de "**Título**"
        frase = re.sub(r"^\s*(?:[-*•]\s+)", "", linha).strip()
        if len(frase) < 15 or frase.startswith("#") or TITULO.match(frase):
            continue
        citacoes = [(a, int(p)) for a, p in CITACAO.findall(frase)]
        if not citacoes:
            if RECUSA.search(frase):
                # Recusa só vale depois de ler alguma página: sem nenhuma, é recusa no escuro
                veredito = "recusa" if evidencias else "recusa sem página lida"
            else:
                veredito = "sem citação"
            resultado.append({"frase": frase, "citacoes": [], "veredito": veredito, "detalhe": ""})
            continue
        nao_lidas = [c for c in citacoes if c not in evidencias]
        if nao_lidas:
            detalhe = ", ".join(f"{a} p.{p}" for a, p in nao_lidas)
            resultado.append({"frase": frase, "citacoes": citacoes,
                              "veredito": "página não lida", "detalhe": detalhe})
            continue
        sem_cit = CITACAO.sub("", frase)
        texto_paginas = " ".join(evidencias[c] for c in citacoes)
        # Números do próprio nome do documento ("AC 20-193", "SYCL 2020") não são dados da afirmação
        nomes = " ".join(f'{a} {ARTIGOS_POR_ID.get(a, {}).get("titulo", "")}' for a, _ in citacoes)
        numeros_pag = _numeros(texto_paginas) | _numeros(nomes)
        anos = {str(a) for a in range(1950, 2031)}
        faltando = sorted(n for n in _numeros(sem_cit) if n not in numeros_pag and n not in anos)
        if faltando:
            resultado.append({"frase": frase, "citacoes": citacoes,
                              "veredito": "número ausente", "detalhe": ", ".join(faltando)})
        else:
            resultado.append({"frase": frase, "citacoes": citacoes,
                              "veredito": "rastreável", "detalhe": ""})
    return resultado


def resumo(itens: list[dict]) -> str:
    from collections import Counter
    c = Counter(i["veredito"] for i in itens)
    return ", ".join(f"{v}: {n}" for v, n in c.most_common()) or "nenhuma frase avaliada"
