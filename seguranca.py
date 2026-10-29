"""Regras de segurança do servidor local (app.py), separadas para poderem ser testadas sem o corpus.

Análise de 26/10/2026: o servidor escuta só em 127.0.0.1, mas o navegador deixa qualquer site
mandar pedidos para lá. Por isso:
  - o Host precisa ser 127.0.0.1/localhost na porta certa (bloqueia DNS rebinding);
  - pedido que altera algo (POST) precisa vir da própria página (Origin/Sec-Fetch-Site) e com corpo
    JSON: um site de fora não consegue mandar JSON sem a pré-verificação CORS, que o servidor nega.

Acesso pelo celular (29/10/2026, opcional, MESA_REMOTO=1 no .env): um segundo servidor escuta só no
endereço do Tailscale (100.64.0.0/10, rede privada entre os aparelhos da autora), nunca no Wi-Fi.
Nele, tudo além da tela de entrada exige o código de acesso do .env (MESA_CODIGO); depois de entrar,
um cookie HttpOnly e SameSite=Strict, derivado do código, vale por 30 dias. Trocar o código derruba
as sessões. Cinco códigos errados seguidos bloqueiam a entrada por 10 minutos.
"""
import hashlib
import hmac
import ipaddress
import re
import secrets
import threading
import time

ID_HISTORICO = re.compile(r"sessao_[\d_-]+#\d+")
NOME_VENDOR = re.compile(r"[\w.-]+")


def pedido_confiavel(headers, porta: int, post: bool, hosts_extra=frozenset()) -> bool:
    """headers: qualquer objeto com .get (os cabeçalhos do pedido HTTP).
    hosts_extra: "host:porta" aceitos além do próprio computador (só no servidor do Tailscale)."""
    hosts = {f"127.0.0.1:{porta}", f"localhost:{porta}", *hosts_extra}
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


# ---------- acesso pelo celular (Tailscale) ----------
REDE_TAILSCALE = ipaddress.ip_network("100.64.0.0/10")
COOKIE = "mesa_sessao"
ALFABETO_CODIGO = "abcdefghjkmnpqrstuvwxyz23456789"  # sem 0/o, 1/l/i: fácil de digitar no celular


def ip_remoto_valido(ip: str) -> bool:
    """Só endereço do Tailscale. Loopback é aceito para os testes (não sai do computador)."""
    try:
        end = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return end.version == 4 and (end in REDE_TAILSCALE or end.is_loopback)


def novo_codigo() -> str:
    """Quatro grupos de 4 caracteres (~79 bits): 'k7mq-3xvd-...'."""
    return "-".join("".join(secrets.choice(ALFABETO_CODIGO) for _ in range(4)) for _ in range(4))


def codigo_forte(codigo: str) -> bool:
    return len(codigo or "") >= 12


def codigo_confere(digitado: str, certo: str) -> bool:
    if not (digitado and certo):
        return False
    return hmac.compare_digest(digitado.strip().lower().encode(), certo.strip().lower().encode())


def token_sessao(codigo: str) -> str:
    """O cookie não é o código: é um HMAC dele. Trocar o código invalida os cookies antigos."""
    return hmac.new(codigo.strip().lower().encode(), b"mesa-de-revisao/sessao", hashlib.sha256).hexdigest()


def cookie_valido(cabecalho_cookie: str, codigo: str) -> bool:
    if not codigo:
        return False
    for parte in (cabecalho_cookie or "").split(";"):
        nome, _, valor = parte.strip().partition("=")
        if nome == COOKIE and hmac.compare_digest(valor.encode(), token_sessao(codigo).encode()):
            return True
    return False


class Tentativas:
    """Conta códigos errados. Depois de `limite` erros seguidos, bloqueia por `bloqueio` segundos."""

    def __init__(self, limite: int = 5, bloqueio: float = 600, relogio=time.monotonic):
        self.limite, self.bloqueio, self.relogio = limite, bloqueio, relogio
        self.erros, self.ate = 0, 0.0
        self.trava = threading.Lock()

    def bloqueado(self) -> bool:
        with self.trava:
            return self.relogio() < self.ate

    def registrar(self, acertou: bool):
        with self.trava:
            if acertou:
                self.erros = 0
                return
            self.erros += 1
            if self.erros >= self.limite:
                self.ate, self.erros = self.relogio() + self.bloqueio, 0
