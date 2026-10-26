"""Servidor local: só a própria página pode alterar algo (análise de segurança de 26/10/2026)."""
import seguranca

PORTA = 8765
OK = {"Host": "127.0.0.1:8765", "Origin": "http://127.0.0.1:8765", "Content-Type": "application/json",
      "Sec-Fetch-Site": "same-origin"}


def com(**mudancas):
    h = dict(OK)
    for k, v in mudancas.items():
        k = k.replace("_", "-")
        if v is None:
            h.pop(k, None)
        else:
            h[k] = v
    return h


def test_pagina_propria_passa():
    assert seguranca.pedido_confiavel(OK, PORTA, post=True)
    assert seguranca.pedido_confiavel(com(Host="localhost:8765", Origin="http://localhost:8765"), PORTA, post=True)
    assert seguranca.pedido_confiavel({"Host": "127.0.0.1:8765"}, PORTA, post=False)


def test_dns_rebinding_bloqueado():
    assert not seguranca.pedido_confiavel({"Host": "evil.com:8765"}, PORTA, post=False)
    assert not seguranca.pedido_confiavel({"Host": "127.0.0.1:9999"}, PORTA, post=False)


def test_post_de_outro_site_bloqueado():
    assert not seguranca.pedido_confiavel(com(Origin="https://evil.com"), PORTA, post=True)
    assert not seguranca.pedido_confiavel(com(Sec_Fetch_Site="cross-site"), PORTA, post=True)


def test_post_sem_json_bloqueado():
    # Formulário HTML simples (sem pré-verificação CORS) manda text/plain ou form-urlencoded
    assert not seguranca.pedido_confiavel(com(Content_Type="text/plain"), PORTA, post=True)
    assert not seguranca.pedido_confiavel(com(Content_Type="application/x-www-form-urlencoded"), PORTA, post=True)
    assert not seguranca.pedido_confiavel(com(Content_Type=None), PORTA, post=True)


def test_id_do_historico():
    assert seguranca.id_historico_valido("sessao_2026-10-26_192246#3")
    for ruim in ("sessao_../../x#0", "../sessao_1#0", "sessao_1", "sessao_1#a", "", "outro_1#0"):
        assert not seguranca.id_historico_valido(ruim), ruim


def test_arquivos_do_vendor():
    assert seguranca.nome_vendor_valido("pdf.min.mjs")
    for ruim in ("..", ".", "../app.py", "sub/arquivo.js", ""):
        assert not seguranca.nome_vendor_valido(ruim), ruim
