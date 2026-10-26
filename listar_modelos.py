"""Lista os modelos gratuitos que aceitam tools (OpenRouter) e os modelos do Groq.

Uso:  python listar_modelos.py
Não imprime as chaves; só usa as do arquivo .env.
"""
import json
import os
import urllib.request

from dotenv import load_dotenv

load_dotenv()


def get(url, chave=None):
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {chave}"} if chave else {})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


print("== OpenRouter: modelos gratuitos com suporte a tools ==")
dados = get("https://openrouter.ai/api/v1/models?supported_parameters=tools")["data"]
gratis = [m for m in dados if m["id"].endswith(":free")
          or (m["pricing"]["prompt"] == "0" and m["pricing"]["completion"] == "0")]
for m in sorted(gratis, key=lambda m: -(m.get("context_length") or 0)):
    print(f'{m["id"]:<60} contexto {m.get("context_length")}')

print("\n== Groq: modelos disponíveis para a sua chave ==")
try:
    for m in sorted(get("https://api.groq.com/openai/v1/models", os.getenv("GROQ_API_KEY"))["data"],
                    key=lambda m: m["id"]):
        print(f'{m["id"]:<60} contexto {m.get("context_window")}')
except Exception as e:
    print("Erro ao consultar o Groq:", e)
