"""Agente de revisão de literatura com rastreio de fonte (TE-251, Projeto Final).

Uso:  python main.py

Comandos (os mesmos da demo da disciplina, mais alguns):
  /model <provedor>[:<modelo>]   troca o modelo (ollama, groq, openrouter)
  /context                       tamanho do contexto da última chamada (tokens)
  /chamadas                      chamadas ao LLM feitas nesta sessão
  /log                           resposta bruta da última chamada
  /clear                         limpa a conversa e mantém as instruções
  /sair                          encerra
"""
import json
import sys

from openai import APIError

from agente.harness import Agente


def main():
    try:
        agente = Agente()
    except ValueError as e:
        sys.exit(str(e))
    print("Agente de revisão de literatura. Pergunte sobre os artigos do corpus. /sair para encerrar.")
    print(f"Log desta sessão: {agente.arquivo_log}")
    while True:
        try:
            entrada = input(f"\n[{agente.rotulo}] > ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not entrada:
            continue
        if entrada == "/sair":
            break
        if entrada == "/clear":
            agente.limpar()
            print("Conversa limpa; instruções do agente mantidas.")
            continue
        if entrada == "/context":
            print(f"Contexto na última chamada: {agente.tokens_contexto} tokens de entrada.")
            continue
        if entrada == "/chamadas":
            print(f"{agente.chamadas_sessao} chamada(s) ao LLM nesta sessão.")
            continue
        if entrada == "/log":
            print(json.dumps(agente.ultimo_log, ensure_ascii=False, indent=2)[:6000])
            continue
        if entrada.startswith("/model"):
            alvo = entrada[len("/model"):].strip()
            try:
                print(agente.trocar_modelo(alvo) if alvo else f"Modelo ativo: {agente.rotulo}")
            except ValueError as e:
                print(e)
            continue
        try:
            agente.turno_com_revisao(entrada)
        except APIError as e:
            print(f"Erro do provedor ({agente.rotulo}): {e}")
        except Exception as e:  # conexão recusada, modelo inexistente etc.
            print(f"Erro: {type(e).__name__}: {e}")


if __name__ == "__main__":
    main()
