"""Gate humano (HITL) antes do efeito.

"O gate fica antes do efeito, não depois dele." (Semana 2, p. 71)
O efeito aqui é gravar o fichamento em fichamentos/. Nada é gravado sem a
decisão da pessoa, e a decisão fica registrada no log (Aula 10, p. 64 e p. 71).
"""
import re
from datetime import datetime

from .config import PASTA_FICHAMENTOS

SIMBOLO = {"rastreável": "OK ", "recusa": "-- ", "sem citação": "!! ",
           "página não lida": "XX ", "número ausente": "?? ", "recusa sem página lida": "XX "}


def mostrar_verificacao(itens: list[dict]) -> None:
    print("\n=== Verificação automática das citações ===")
    for i, item in enumerate(itens, 1):
        detalhe = f"  ({item['detalhe']})" if item["detalhe"] else ""
        frase = item["frase"] if len(item["frase"]) <= 110 else item["frase"][:107] + "..."
        print(f"{SIMBOLO.get(item['veredito'], '   ')}{i:>2}. [{item['veredito']}{detalhe}] {frase}")
    print("Legenda: OK rastreável · ?? número não está na página · XX página citada não foi lida "
          "ou recusa sem ter lido nenhuma página · !! sem citação · -- recusa depois de buscar")
    print("Rastreável não garante que o trecho sustenta a frase: confira as páginas antes de aprovar.")


def pedir_decisao() -> tuple[str, str]:
    """Devolve (decisao, comentario). decisao: aprovar | corrigir | rejeitar."""
    while True:
        op = input("\n[a]provar e gravar · [c]orrigir (você escreve o que mudar) · [r]ejeitar > ").strip().lower()
        if op in ("a", "aprovar"):
            return "aprovar", input("Comentário opcional (Enter para pular): ").strip()
        if op in ("c", "corrigir"):
            return "corrigir", input("O que o agente deve corrigir? ").strip()
        if op in ("r", "rejeitar"):
            return "rejeitar", input("Motivo (fica no log): ").strip()


def gravar_fichamento(pergunta: str, resposta: str, itens: list[dict], modelo: str, comentario: str) -> str:
    PASTA_FICHAMENTOS.mkdir(exist_ok=True)
    agora = datetime.now()
    slug = re.sub(r"[^a-z0-9]+", "-", pergunta.lower())[:50].strip("-") or "fichamento"
    arquivo = PASTA_FICHAMENTOS / f"{agora:%Y-%m-%d_%H%M}_{slug}.md"
    linhas_verif = "\n".join(f"| {i + 1} | {it['veredito']} | {it['detalhe']} |" for i, it in enumerate(itens))
    arquivo.write_text(
        f"# Fichamento: {pergunta}\n\n"
        f"- Gerado por: {modelo}\n- Aprovado em: {agora:%d/%m/%Y %H:%M}\n"
        f"- Comentário de quem aprovou: {comentario or '(nenhum)'}\n"
        f"- Status: rascunho aceito por uma pessoa (HITL). As citações seguem a página física do PDF.\n\n"
        f"## Texto\n\n{resposta}\n\n"
        f"## Verificação automática\n\n| Frase | Veredito | Detalhe |\n|---|---|---|\n{linhas_verif}\n",
        encoding="utf-8")
    return str(arquivo)
