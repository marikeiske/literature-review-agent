"""Roda UMA pergunta em um modelo, sem gate humano e sem gravar fichamento.

Serve para comparar modelos rapidamente. Tudo vai para o log da sessão.

Uso:
  python teste_rapido.py groq "Quanto a arquitetura de Nimbekar consome na FPGA?"
  python teste_rapido.py openrouter:google/gemma-4-31b-it:free "..."
  python teste_rapido.py ollama:qwen2.5:1.5b "..."
"""
import sys
import time

from agente import verificador
from agente.harness import Agente

if len(sys.argv) < 3:
    sys.exit(__doc__)

agente = Agente()
print(agente.trocar_modelo(sys.argv[1]))
inicio = time.time()
resposta, chamadas = agente.responder(sys.argv[2])
itens = verificador.verificar(resposta, agente.ferramentas.evidencias)
agente._registrar({"tipo": "verificacao", "resumo": verificador.resumo(itens), "itens": itens,
                   "chamadas_turno": chamadas, "origem": "teste_rapido"})
print(f"\n{resposta}\n")
print(f"Chamadas ao LLM: {chamadas} · tempo total: {time.time() - inicio:.0f} s · "
      f"tokens de entrada na última chamada: {agente.tokens_contexto}")
print("Páginas lidas:", ", ".join(f"{a} p.{p}" for a, p in sorted(agente.ferramentas.evidencias)) or "nenhuma")
for i, it in enumerate(itens, 1):
    print(f"{i:>2}. [{it['veredito']}{' ' + it['detalhe'] if it['detalhe'] else ''}] {it['frase'][:100]}")
print(f"Log: {agente.arquivo_log}")
