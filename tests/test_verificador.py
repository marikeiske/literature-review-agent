"""O verificador é o que sustenta a métrica "citou página não lida" do artigo (R-1, R-2 do STPA)."""
from agente import verificador

PAGINA = "The on-chip power requirements for LoCoMo-Net and MyoNet on FPGA are 3.5 and 5 Watts, respectively."
EVID = {("Nimbekar2023", 1): PAGINA}


def veredito(frase, evid=EVID):
    itens = verificador.verificar(frase, evid)
    assert len(itens) == 1
    return itens[0]["veredito"]


def test_rastreavel_quando_pagina_lida_e_numeros_batem():
    assert veredito("- A arquitetura consome 3,5 W e 5 W na FPGA [Nimbekar2023 p.1].") == "rastreável"


def test_pagina_nao_lida():
    assert veredito("- A arquitetura consome 3,5 W na FPGA [Nimbekar2023 p.7].") == "página não lida"


def test_numero_ausente_na_pagina_citada():
    item = verificador.verificar("- A arquitetura consome 9,9 W na FPGA [Nimbekar2023 p.1].", EVID)[0]
    assert item["veredito"] == "número ausente"
    assert item["detalhe"] == "9.9"


def test_frase_sem_citacao():
    assert veredito("- A arquitetura consome pouca energia na FPGA.") == "sem citação"


def test_recusa_depois_de_ler_e_recusa_no_escuro():
    assert veredito("Não consta no material aberto.") == "recusa"
    assert veredito("Não consta no material aberto.", {}) == "recusa sem página lida"


def test_premissa_contradita_precisa_de_citacao():
    # Regra 4 do system prompt: a correção da premissa é uma afirmação e leva página
    assert veredito("- A premissa não confere: o artigo usa uma FPGA, não uma GPU [Nimbekar2023 p.1].") == "rastreável"
    assert veredito("- A premissa não confere: o artigo usa uma FPGA, não uma GPU.") == "sem citação"


def test_fator_com_x_e_ano_nao_viram_numero_ausente():
    evid = {("Leppanen2023", 9): "DMA can be up to 8x faster than host-initiated copies."}
    assert veredito("- Em 2023, o DMA ficou até 8x mais rápido [Leppanen2023 p.9].", evid) == "rastreável"


def test_titulos_e_linhas_curtas_sao_ignorados():
    assert verificador.verificar("**Resultados**\nOk.", EVID) == []
