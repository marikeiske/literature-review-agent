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


# ---------- acesso pelo celular (Tailscale), 29/10/2026 ----------
REMOTO = frozenset({"100.70.57.98:8765", "laptop-teste:8765", "laptop-teste.tail1234.ts.net:8765"})


def test_servidor_do_tailscale_aceita_so_os_proprios_nomes():
    for host in REMOTO:
        ok = {"Host": host, "Origin": f"http://{host}", "Content-Type": "application/json"}
        assert seguranca.pedido_confiavel(ok, PORTA, post=True, hosts_extra=REMOTO)
    assert not seguranca.pedido_confiavel({"Host": "evil.com:8765"}, PORTA, post=False, hosts_extra=REMOTO)
    # Origin de outro nome, mesmo que também da rede, não altera nada
    misto = {"Host": "100.70.57.98:8765", "Origin": "http://evil.com:8765", "Content-Type": "application/json"}
    assert not seguranca.pedido_confiavel(misto, PORTA, post=True, hosts_extra=REMOTO)
    # Sem hosts_extra (servidor local), o endereço do Tailscale é recusado
    assert not seguranca.pedido_confiavel({"Host": "100.70.57.98:8765"}, PORTA, post=False)


def test_so_escuta_em_endereco_do_tailscale():
    assert seguranca.ip_remoto_valido("100.70.57.98")
    assert seguranca.ip_remoto_valido("127.0.0.2")  # testes
    for ruim in ("0.0.0.0", "192.168.0.10", "10.0.0.5", "100.128.0.1", "8.8.8.8", "", "abc", "::1"):
        assert not seguranca.ip_remoto_valido(ruim), ruim


def test_codigo_e_cookie():
    c = seguranca.novo_codigo()
    assert seguranca.codigo_forte(c) and len(c) == 19 and not set(c) & set("01ilo")
    assert seguranca.novo_codigo() != c
    assert seguranca.codigo_confere(f"  {c.upper()} ", c)  # o teclado do celular põe maiúscula
    assert not seguranca.codigo_confere("", c) and not seguranca.codigo_confere(c, "")
    assert not seguranca.codigo_confere(c[:-1], c)
    token = seguranca.token_sessao(c)
    assert c not in token  # o cookie não carrega o código
    assert seguranca.cookie_valido(f"outro=1; mesa_sessao={token}", c)
    assert not seguranca.cookie_valido(f"mesa_sessao={token}", seguranca.novo_codigo())  # trocar o código derruba
    assert not seguranca.cookie_valido("mesa_sessao=", c)
    assert not seguranca.cookie_valido(f"mesa_sessao={token}", "")


def test_cinco_erros_bloqueiam():
    agora = [0.0]
    t = seguranca.Tentativas(limite=5, bloqueio=600, relogio=lambda: agora[0])
    for _ in range(4):
        t.registrar(False)
    t.registrar(True)  # acerto zera a conta
    for _ in range(4):
        t.registrar(False)
    assert not t.bloqueado()
    t.registrar(False)
    assert t.bloqueado()
    agora[0] = 601
    assert not t.bloqueado()
