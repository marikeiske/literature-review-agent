"""Regras de segurança do servidor local (app.py), separadas para poderem ser testadas sem o corpus.

Análise de 26/10/2026: o servidor escuta só em 127.0.0.1, mas o navegador deixa qualquer site
mandar pedidos para lá. Por isso:
  - o Host precisa ser 127.0.0.1/localhost na porta certa (bloqueia DNS rebinding);
  - pedido que altera algo (POST) precisa vir da própria página (Origin/Sec-Fetch-Site) e com corpo
    JSON: um site de fora não consegue mandar JSON sem a pré-verificação CORS, que o servidor nega.
"""
import re

ID_HISTORICO = re.compile(r"sessao_[\d_-]+#\d+")
NOME_VENDOR = re.compile(r"[\w.-]+")


def pedido_confiavel(headers, porta: int, post: bool) -> bool:
    """headers: qualquer objeto com .get (os cabeçalhos do pedido HTTP)."""
    hosts = {f"127.0.0.1:{porta}", f"localhost:{porta}"}
    if headers.get("Host", "") not in hosts:
        return False
    if not post:
        return True
    origem = headers.get("Origin")
    if origem is not None and origem not in {f"http://{h}" for h in hosts}:
        return False
    if headers.get("Sec-Fetch-Site", "same-origin") not in ("same-origin", "none"):
        return False
    return headers.get("Content-Type", "").split(";")[0].strip() == "application/json"


def id_historico_valido(id_: str) -> bool:
    """'sessao_2026-10-26_192246#3'; nada de '../' nem outro arquivo."""
    return bool(ID_HISTORICO.fullmatch(id_ or ""))


def nome_vendor_valido(nome: str) -> bool:
    """Só arquivos soltos da pasta web/vendor, sem subpastas."""
    return bool(NOME_VENDOR.fullmatch(nome or "")) and nome not in (".", "..")
