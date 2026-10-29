"""Acessibilidade da interface (WCAG 2.1 AA): varredura automática com o axe-core e checagens de
teclado e foco que o axe não cobre. Cada teste corresponde a um problema achado na auditoria de 29/10;
se um deles voltar, o teste falha.
"""
from pathlib import Path

import pytest
from playwright.sync_api import expect

AXE = (Path(__file__).parent / "vendor" / "axe.min.js").read_text(encoding="utf-8")
REGRAS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"]

# Uma frase conferida e outra com página que o agente não leu
RESPOSTA_DUAS_LINHAS = """() => {
  const r = criarRodada('Quanto a arquitetura de Nimbekar consome na FPGA?');
  mostrarResposta(r, 'teste', {
    linhas: [
      {texto: '- A arquitetura consome 3,5 W e 5 W na FPGA [Nimbekar2023 p.1]', veredito: 'rastreável', detalhe: ''},
      {texto: '- A sincronização economiza 250 us [Leppanen2023 p.10]', veredito: 'página não lida', detalhe: 'Leppanen2023 p.10'}],
    itens: [],
    chamadas: 2, segundos: 1.2, tokens: 1500, modelo: 'ollama:teste', lidas: [['Nimbekar2023', 1]]});
}"""


def _abrir(navegador, url, largura=1500, altura=900, esquema="light"):
    # bypass_csp: a CSP da página (script-src 'self') bloquearia o axe injetado pelo teste
    ctx = navegador.new_context(viewport={"width": largura, "height": altura}, color_scheme=esquema, bypass_csp=True)
    pg = ctx.new_page()
    pg.erros = []
    pg.on("pageerror", lambda e: pg.erros.append(str(e)))
    pg.goto(url)
    pg.wait_for_load_state("networkidle")
    return ctx, pg


def _axe(pg):
    pg.add_script_tag(content=AXE)
    res = pg.evaluate("async (tags) => await axe.run(document, {runOnly: {type: 'tag', values: tags}})", REGRAS)
    return [f"{v['id']} ({v['impact']}): {[n['target'] for n in v['nodes']][:3]}" for v in res["violations"]]


@pytest.mark.parametrize("esquema", ["light", "dark"])
def test_axe_sem_violacoes(servidor, navegador, esquema):
    ctx, pg = _abrir(navegador, servidor["url"], esquema=esquema)
    try:
        problemas = {"inicio": _axe(pg)}
        pg.evaluate(RESPOSTA_DUAS_LINHAS)
        pg.wait_for_selector(".textLayer .grifo", timeout=20000)
        problemas["resposta"] = _axe(pg)
        pg.click("#ver-texto")
        problemas["texto"] = _axe(pg)
        pg.click("#aba-revisar")
        expect(pg.locator(".rev-meta")).to_be_visible(timeout=10000)
        problemas["revisar"] = _axe(pg)
        pg.click("#aba-historico")
        pg.locator(".hist-item").first.wait_for(timeout=10000)
        problemas["historico"] = _axe(pg)
        assert not any(problemas.values()), problemas
        assert not pg.erros, pg.erros
    finally:
        ctx.close()


def test_marcas_e_abas_tem_nome_para_leitor_de_tela(pagina):
    pagina.evaluate(RESPOSTA_DUAS_LINHAS)
    marca = pagina.locator(".marca-margem").first
    assert marca.get_attribute("role") == "img"
    assert "rastreável" in marca.get_attribute("aria-label")
    nao_lida = pagina.locator(".aba.nao-lida")
    assert nao_lida.get_attribute("aria-label") == "Leppanen p. 10, página não lida pelo agente"


def test_atalhos_da_revisao_so_valem_com_foco_no_cartao(pagina):
    pagina.click("#aba-revisar")
    expect(pagina.locator(".rev-meta")).to_be_visible(timeout=10000)
    item = pagina.locator(".rev-id").inner_text()
    gravacoes = []
    pagina.on("request", lambda r: gravacoes.append(r.url) if r.url.endswith("/api/revisao") else None)
    # Foco fora do cartão: "1" não grava nada e a seta não troca de item
    pagina.evaluate("() => document.activeElement.blur()")
    pagina.keyboard.press("1")
    pagina.keyboard.press("ArrowRight")
    pagina.wait_for_timeout(400)
    assert not gravacoes
    assert pagina.locator(".rev-id").inner_text() == item
    # Foco no cartão: as setas navegam
    pagina.focus("#rev-cartao")
    pagina.keyboard.press("ArrowRight")
    expect(pagina.locator(".rev-id")).not_to_have_text(item)
    expect(pagina.locator("#rev-cartao")).to_be_focused()  # o foco continua no cartão depois de redesenhar


def test_caixa_de_pergunta_mostra_foco(pagina):
    pagina.focus("#pergunta")
    estilo = pagina.eval_on_selector("#pergunta", "e => getComputedStyle(e).outlineStyle")
    assert estilo != "none"
    pagina.click("#aba-revisar")
    expect(pagina.locator("#rev-nota")).to_be_visible(timeout=10000)
    pagina.focus("#rev-nota")
    assert pagina.eval_on_selector("#rev-nota", "e => getComputedStyle(e).outlineStyle") != "none"


def test_pergunta_vazia_avisa(pagina):
    pagina.press("#pergunta", "Enter")
    expect(pagina.locator("#aviso")).to_have_text("Escreva uma pergunta.")
    expect(pagina.locator("#pergunta")).to_be_focused()


def test_tela_de_320px_com_resposta_aberta(servidor, navegador):
    ctx, pg = _abrir(navegador, servidor["url"], largura=320, altura=640)
    try:
        pg.evaluate(RESPOSTA_DUAS_LINHAS)
        assert pg.locator("#fonte.aberta").count() == 0  # no celular a página não cobre a resposta sozinha
        pg.locator(".aba:not(.nao-lida)").first.click()
        expect(pg.locator("#fonte")).to_have_class("fonte aberta")
        assert pg.evaluate("() => document.documentElement.scrollWidth <= window.innerWidth")
        largura_nav = pg.eval_on_selector(".fonte-nav", "e => e.scrollWidth <= e.clientWidth")
        assert largura_nav, "a barra da página-fonte transborda em 320 px"
    finally:
        ctx.close()


def test_esc_fecha_a_pagina_e_devolve_o_foco(pagina):
    pagina.evaluate(RESPOSTA_DUAS_LINHAS)
    aba = pagina.locator(".aba:not(.nao-lida)").first
    expect(pagina.locator("#fonte-cheia")).to_be_visible()
    pagina.focus("#fechar-fonte")
    pagina.keyboard.press("Escape")
    expect(pagina.locator("#fonte-cheia")).to_be_hidden()
    expect(aba).to_be_focused()


def test_setas_trocam_de_aba(pagina):
    pagina.focus("#aba-perguntar")
    pagina.keyboard.press("ArrowRight")
    expect(pagina.locator("#aba-historico")).to_be_focused()
    expect(pagina.locator("#aba-historico")).to_have_attribute("aria-selected", "true")
    assert pagina.locator("#aba-perguntar").get_attribute("tabindex") == "-1"
    pagina.keyboard.press("End")
    expect(pagina.locator("#aba-revisar")).to_have_attribute("aria-selected", "true")
    pagina.keyboard.press("ArrowRight")  # dá a volta
    expect(pagina.locator("#aba-perguntar")).to_have_attribute("aria-selected", "true")


CONTRASTE = """(sel) => {
  const lum = (c) => {
    const [r, g, b] = c.match(/[\\d.]+/g).slice(0, 3).map(Number).map((v) => {
      v /= 255; return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4; });
    return 0.2126 * r + 0.7152 * g + 0.0722 * b;
  };
  const e = document.querySelector(sel);
  const borda = lum(getComputedStyle(e).borderTopColor);
  const fundo = lum(getComputedStyle(document.querySelector('.folha')).backgroundColor);
  const [a, b] = [borda, fundo].sort((x, y) => y - x);
  return (a + 0.05) / (b + 0.05);
}"""


@pytest.mark.parametrize("esquema", ["light", "dark"])
def test_bordas_de_campo_com_contraste_3(servidor, navegador, esquema):
    ctx, pg = _abrir(navegador, servidor["url"], esquema=esquema)
    try:
        assert pg.evaluate(CONTRASTE, "#modelo") >= 3
        pg.click("#aba-revisar")
        expect(pg.locator("#rev-nota")).to_be_visible(timeout=10000)
        for sel in ["#rev-nota", ".rev-opcao", ".rev-nav .botao-secundario"]:
            assert pg.evaluate(CONTRASTE, sel) >= 3, sel
    finally:
        ctx.close()
