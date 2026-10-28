"""Testes de ponta a ponta da interface (Playwright, Chromium sem janela).

Cobrem o que só aparece no navegador: abas, lista de modelos, resposta com selo do verificador,
PDF com os números grifados, histórico, revisão humana (gravando sem horário), erro de provedor,
tela estreita e recusa de pedido vindo de outro site.
"""
import csv
import json
import urllib.error
import urllib.request

from playwright.sync_api import expect

RESPOSTA_FALSA = """() => {
  const r = criarRodada('Quanto a arquitetura de Nimbekar consome na FPGA?');
  mostrarResposta(r, 'teste', {
    linhas: [{texto: '- A arquitetura consome 3,5 W e 5 W na FPGA [Nimbekar2023 p.1]', veredito: 'rastreável', detalhe: ''}],
    itens: [{veredito: 'rastreável', citacoes: [['Nimbekar2023', 1]]}],
    chamadas: 2, segundos: 1.2, tokens: 1500, modelo: 'ollama:teste', lidas: [['Nimbekar2023', 1]]});
}"""


def test_tres_abas_e_modelos_agrupados(pagina):
    abas = pagina.locator(".modos [role=tab]").all_inner_texts()
    assert abas == ["Perguntar", "Histórico", "Revisar"]
    grupos = pagina.eval_on_selector_all("#modelo optgroup", "gs => gs.map(g => g.label)")
    assert grupos == ["Recomendados", "Outros"]
    opcoes = " ".join(pagina.locator("#modelo option").all_inner_texts())
    assert "Bonsai" not in opcoes  # modelo local saiu da lista em 26/10
    assert "97%" in opcoes


def test_resposta_abre_pdf_com_numeros_grifados(pagina):
    pagina.evaluate(RESPOSTA_FALSA)
    assert "1 de 1 frases conferidas" in pagina.locator(".selo").inner_text()
    # A primeira página citada abre sozinha, no modo PDF (PDF.js)
    pagina.wait_for_selector(".pdf-folha canvas", timeout=20000)
    pagina.wait_for_selector(".textLayer .grifo", timeout=20000)
    grifos = " ".join(pagina.locator(".textLayer .grifo").all_text_contents())
    assert "3.5" in grifos
    assert "p. 1 de" in pagina.locator("#pag-rotulo").inner_text()
    # No modo Texto, o mesmo número aparece grifado
    pagina.click("#ver-texto")
    assert "3.5" in " ".join(pagina.locator("#fonte-texto mark").all_text_contents())


def test_pergunta_com_provedor_fora_do_ar_mostra_erro_claro(pagina):
    pagina.fill("#pergunta", "Qual FPGA Nimbekar usou?")
    pagina.press("#pergunta", "Enter")
    erro = pagina.wait_for_selector(".erro", timeout=60000)
    assert "Não consegui falar com o provedor" in erro.inner_text()
    assert pagina.locator(".espera").count() == 0  # a animação de espera some no erro
    assert not pagina.locator("#enviar").is_disabled()


def test_historico_mostra_pergunta_antiga_com_decisao(pagina):
    pagina.click("#aba-historico")
    item = pagina.locator(".hist-item", has_text="Pergunta antiga de teste")
    item.wait_for(timeout=10000)
    assert "Salvo no fichamento" in item.inner_text()
    item.click()
    pagina.wait_for_selector(".historico .resposta li")
    assert "somente leitura" in pagina.locator(".historico .hist-meta").first.inner_text()
    assert "1 de 1 frases conferidas" in pagina.locator(".historico .selo").inner_text()


def test_revisao_grava_decisao_sem_horario_no_csv(pagina, servidor):
    pagina.click("#aba-revisar")
    # O gabarito é o primeiro conjunto; não reescolher (a troca recarrega a lista e desfaz o filtro).
    # Espera a lista de artigos montar: sinal de que o conjunto terminou de carregar.
    expect(pagina.locator("#rev-conjunto")).to_have_value("gabarito")
    expect(pagina.locator("#rev-artigo option")).to_have_count(12)  # "Todos" + 11 documentos
    pagina.select_option("#rev-artigo", "Loubach2019")
    expect(pagina.locator(".rev-meta")).to_contain_text("Loubach2019")
    item = pagina.locator(".rev-id").inner_text()
    with pagina.expect_response(lambda r: r.url.endswith("/api/revisao") and r.request.method == "POST") as resp:
        pagina.locator(".rev-opcao", has_text="Aprovada").click()
    assert resp.value.ok
    with open(servidor["pasta"] / "revisao_gabarito.csv", encoding="utf-8-sig") as f:
        linhas = list(csv.DictReader(f, delimiter=";"))
    assert list(linhas[0].keys()) == ["id", "status", "comentario"]  # horário não vai para o CSV
    assert {l["id"]: l["status"] for l in linhas}[item] == "Aprovada"
    horarios = (servidor["pasta"] / "logs" / "revisao_horarios.jsonl").read_text(encoding="utf-8")
    assert json.loads(horarios.splitlines()[-1])["id"] == item  # o horário fica só em logs/


def test_tela_estreita_sem_rolagem_horizontal(servidor, navegador):
    contexto = navegador.new_context(viewport={"width": 390, "height": 800})
    pg = contexto.new_page()
    pg.goto(servidor["url"])
    pg.wait_for_load_state("networkidle")
    assert pg.evaluate("() => document.documentElement.scrollWidth <= window.innerWidth")
    contexto.close()


def test_pedido_de_outro_site_e_recusado(servidor):
    pedido = urllib.request.Request(f"{servidor['url']}/api/modelo", data=b'{"alvo": "gemini"}', method="POST",
                                    headers={"Content-Type": "application/json", "Origin": "https://evil.example"})
    try:
        urllib.request.urlopen(pedido, timeout=10)
        raise AssertionError("o servidor aceitou um pedido de outro site")
    except urllib.error.HTTPError as e:
        assert e.code == 403
