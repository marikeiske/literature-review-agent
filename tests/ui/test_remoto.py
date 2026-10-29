"""Acesso pelo celular (MESA_REMOTO=1): o servidor do Tailscale exige o código; o local continua igual.

Nos testes o "endereço do Tailscale" é 127.0.0.2 (loopback: nada sai do computador)."""
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request

import pytest

from .conftest import _montar_copia

CODIGO = "abcd-efgh-jkmn-pqrs"
PORTA = 8796


@pytest.fixture(scope="module")
def remoto(tmp_path_factory):
    pasta = tmp_path_factory.mktemp("mesa_remota")
    _montar_copia(pasta)
    env = {k: v for k, v in os.environ.items() if not k.endswith(("_API_KEY", "_KEY"))}
    env.update({"MESA_SEM_NAVEGADOR": "1", "MESA_PORTA": str(PORTA), "MESA_REMOTO": "1", "MESA_IP_REMOTO": "127.0.0.2",
                "MESA_CODIGO": CODIGO, "PROVEDOR": "ollama", "OLLAMA_BASE_URL": "http://127.0.0.1:9/v1",
                "PYTHONIOENCODING": "utf-8", "PYTHONUNBUFFERED": "1"})
    proc = subprocess.Popen([sys.executable, "app.py"], cwd=pasta, env=env, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, text=True, encoding="utf-8")
    saida, local, fora, inicio = [], None, None, time.time()
    while time.time() - inicio < 60 and not fora:
        linha = proc.stdout.readline()
        saida.append(linha)
        local = local or (m.group(1) if (m := re.search(r"aberta em (http://127\.0\.0\.1:\d+)", linha)) else None)
        fora = m.group(1) if (m := re.search(r"ou\s+(http://127\.0\.0\.2:\d+)", linha)) else None
        if proc.poll() is not None or "não consegui abrir" in linha or "não achei" in linha:
            break
    if not (local and fora):
        proc.kill()
        pytest.fail("O servidor remoto de teste não abriu:\n" + "".join(saida))
    yield {"local": local, "fora": fora, "saida": "".join(saida)}
    proc.terminate()
    proc.wait(timeout=10)


class SemRedirecionar(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


def pedir(url, dados=None, cookie=None, origem=None):
    cab = {"Content-Type": "application/json"}
    if cookie:
        cab["Cookie"] = cookie
    if dados is not None:
        cab["Origin"] = origem or re.match(r"http://[^/]+", url).group(0)
    req = urllib.request.Request(url, data=None if dados is None else json.dumps(dados).encode(), headers=cab,
                                 method="GET" if dados is None else "POST")
    try:
        r = urllib.request.build_opener(SemRedirecionar).open(req, timeout=15)
        return r.status, dict(r.headers), r.read()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read()


def test_sem_codigo_so_a_tela_de_entrada(remoto):
    st, cab, _ = pedir(remoto["fora"] + "/")
    assert st == 303 and cab["Location"] == "/entrar"
    for caminho in ("/api/estado", "/api/historico", "/api/revisao/conjuntos", "/pdf/Nimbekar2023.pdf", "/app.js"):
        assert pedir(remoto["fora"] + caminho)[0] == 401, caminho
    assert pedir(remoto["fora"] + "/api/modelo", {"alvo": "gemini"})[0] == 401
    st, _, corpo = pedir(remoto["fora"] + "/entrar")
    assert st == 200 and b"MESA_CODIGO" in corpo
    assert CODIGO not in remoto["saida"]  # o código veio do .env: não é impresso


def test_codigo_errado_e_certo(remoto):
    st, cab, _ = pedir(remoto["fora"] + "/api/entrar", {"codigo": "errado-errado-errado"})
    assert st == 401 and "Set-Cookie" not in cab
    st, cab, _ = pedir(remoto["fora"] + "/api/entrar", {"codigo": CODIGO.upper()})
    assert st == 200
    biscoito = cab["Set-Cookie"]
    assert "HttpOnly" in biscoito and "SameSite=Strict" in biscoito and CODIGO not in biscoito
    sessao = biscoito.split(";")[0]
    assert pedir(remoto["fora"] + "/api/estado", cookie=sessao)[0] == 200
    assert pedir(remoto["fora"] + "/", cookie=sessao)[0] == 200
    # Com sessão, mas pedido vindo de outro site: recusado como no servidor local
    assert pedir(remoto["fora"] + "/api/limpar", {}, cookie=sessao, origem="https://evil.example")[0] == 403
    assert pedir(remoto["fora"] + "/api/limpar", {}, cookie=sessao)[0] == 200


def test_servidor_local_continua_sem_codigo(remoto):
    assert pedir(remoto["local"] + "/api/estado")[0] == 200
    assert pedir(remoto["local"] + "/entrar")[0] == 404  # a tela de entrada só existe no remoto
    assert pedir(remoto["local"] + "/api/entrar", {"codigo": CODIGO})[0] == 404


def test_celular_entra_e_ve_o_pdf(remoto, navegador):
    from .test_acessibilidade import RESPOSTA_DUAS_LINHAS
    ctx = navegador.new_context(viewport={"width": 390, "height": 800}, is_mobile=True, has_touch=True)
    pg = ctx.new_page()
    try:
        pg.goto(remoto["fora"] + "/")
        assert pg.url.endswith("/entrar")
        pg.fill("#codigo", "errado-errado-errado")
        pg.click("button[type=submit]")
        pg.wait_for_selector("#entrar-erro:has-text('Código errado')")
        pg.fill("#codigo", CODIGO)
        pg.click("button[type=submit]")
        pg.wait_for_url(remoto["fora"] + "/")
        pg.wait_for_selector("#modelo option", state="attached")
        pg.evaluate(RESPOSTA_DUAS_LINHAS)
        pg.locator(".aba:not(.nao-lida)").first.click()
        pg.wait_for_selector(".textLayer .grifo", timeout=20000)  # o PDF.js leva o cookie
        assert pg.evaluate("() => document.documentElement.scrollWidth <= window.innerWidth")
    finally:
        ctx.close()
