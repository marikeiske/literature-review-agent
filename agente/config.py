"""Configuração: provedores de LLM, modelos e caminhos do projeto.

Os três provedores aceitam o mesmo cliente `openai` (API compatível com OpenAI),
então trocar de provedor é só trocar a base_url, a chave e o nome do modelo.
Todos têm uso sem custo: Ollama roda local; Groq e OpenRouter têm plano gratuito
com limite diário de requisições.
"""
import os
from pathlib import Path

from dotenv import load_dotenv

RAIZ = Path(__file__).resolve().parent.parent
load_dotenv(RAIZ / ".env")

PASTA_CORPUS = RAIZ / "corpus"
PASTA_DADOS = RAIZ / "dados"
PASTA_LOGS = RAIZ / "logs"
PASTA_FICHAMENTOS = RAIZ / "fichamentos"
PASTA_SKILLS = RAIZ / "skills"
ARQUIVO_PAGINAS = PASTA_DADOS / "paginas.json"

PROVEDORES = {
    "ollama": {
        "base_url": os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1"),
        "api_key_env": None,  # Ollama local não usa chave
        "modelo_padrao": os.getenv("OLLAMA_MODEL", "qwen3:1.7b"),
    },
    "groq": {
        "base_url": "https://api.groq.com/openai/v1",
        "api_key_env": "GROQ_API_KEY",
        "modelo_padrao": os.getenv("GROQ_MODEL", "openai/gpt-oss-120b"),
    },
    "gemini": {
        # Endpoint compatível com OpenAI do Google (plano gratuito do AI Studio)
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
        "api_key_env": "GEMINI_API_KEY",
        "modelo_padrao": os.getenv("GEMINI_MODEL", "gemini-flash-lite-latest"),
    },
    "openrouter": {
        "base_url": "https://openrouter.ai/api/v1",
        "api_key_env": "OPENROUTER_KEY",  # mesmo nome usado nas demos da disciplina
        "modelo_padrao": os.getenv("OPENROUTER_MODEL", ""),
    },
}

PROVEDOR_PADRAO = os.getenv("PROVEDOR", "ollama")

# Limite de ciclos do loop agêntico (a demo da disciplina usa 12)
MAX_CICLOS = int(os.getenv("MAX_CICLOS", "12"))
# Orçamento de tools por pergunta: depois disso o harness obriga a responder
# (regra criada após o agente buscar 10 vezes um número inexistente; ver logs de 19/10)
MAX_TOOLS = int(os.getenv("MAX_TOOLS", "4"))
# Quantos trechos a busca devolve por chamada (top-k)
TOP_K = int(os.getenv("TOP_K", "5"))
# Tamanho aproximado de cada trecho (em caracteres) dentro de uma página
TAMANHO_TRECHO = int(os.getenv("TAMANHO_TRECHO", "900"))
