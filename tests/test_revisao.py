"""Leitura das páginas escritas na correção do gabarito (vale na avaliação)."""
import revisao


def test_formatos_de_pagina():
    assert revisao.paginas_corrigidas("p. 2") == [2]
    assert revisao.paginas_corrigidas("p. 30–31 (sugestão da IA, conferida por mim)") == [30, 31]
    assert revisao.paginas_corrigidas("p. 1, 2, 7, 8") == [1, 2, 7, 8]
    assert revisao.paginas_corrigidas("p. 2 e 3") == [2, 3]
    assert revisao.paginas_corrigidas("pág. 7") == [7]
    assert revisao.paginas_corrigidas("página 4") == [4]


def test_texto_sem_pagina_nao_muda_o_gabarito():
    # Falha de 21/10: "Tesla P100" virava página 100 e todo modelo errava o item A8-09
    assert revisao.paginas_corrigidas("No FiniteDifferenceKernel na Tesla P100, o CUDA12M obtém 1,55 s") == []
    assert revisao.paginas_corrigidas("") == []


def test_paginas_da_planilha():
    assert revisao.paginas_de("p. 7") == [7]
    assert revisao.paginas_de("7–8") == [7, 8]
    assert revisao.paginas_de("3, 5") == [3, 5]
    assert revisao.paginas_de(None) == []
