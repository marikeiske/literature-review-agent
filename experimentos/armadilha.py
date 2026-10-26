"""Experimento: a pergunta-armadilha (Young-S. não informa número de speedup).

Roda a mesma pergunta nas três versões de idioma e registra chamadas, tokens,
se a trava do harness disparou e se algum número foi inventado.

Uso:  python -m experimentos.armadilha groq
"""
import re
import sys

from agente import verificador
from agente.harness import Agente

PERGUNTAS = {
    "pt": "Qual foi o speedup numérico obtido pelos programas OpenMP de Young-S.?",
    "pt_termo": "Qual foi o speedup numérico (speedup factor) obtido pelos programas OpenMP de Young-S.?",
    "en": "What numerical speedup did Young-S.'s OpenMP programs achieve?",
}

agente = Agente()
print(agente.trocar_modelo(sys.argv[1] if len(sys.argv) > 1 else "groq"))
for variante, pergunta in PERGUNTAS.items():
    agente.limpar()
    tokens = []
    original = agente._chamar_llm

    def contando(*a, _original=original, _tokens=tokens, **k):
        m = _original(*a, **k)
        _tokens.append(agente.tokens_contexto)
        return m

    agente._chamar_llm = contando
    try:
        resposta, chamadas = agente.responder(pergunta)
    except Exception as e:
        resposta, chamadas = f"ERRO: {type(e).__name__}: {str(e)[:150]}", len(tokens)
    agente._chamar_llm = original
    trava = any(m.get("content", "").startswith("Limite de buscas") for m in agente.mensagens if isinstance(m, dict))
    inventou = bool(re.search(r"\d+(?:[.,]\d+)?\s*(?:x|×|vezes|%)", verificador.CITACAO.sub("", resposta), re.I))
    itens = verificador.verificar(resposta, agente.ferramentas.evidencias)
    print(f"\n[{variante}] {chamadas} chamadas · maior contexto {max(tokens or [0])} tokens · "
          f"trava {'sim' if trava else 'não'} · inventou número {'SIM' if inventou else 'não'} · "
          f"{verificador.resumo(itens)}")
    print("   " + resposta.replace("\n", "\n   ")[:500])
print(f"\nLog: {agente.arquivo_log}")
