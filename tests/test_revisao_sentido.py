"""Amostra da revisão de sentido: fixa (mesma semente), 30 itens, sem repetir."""
import pytest

import revisao


def test_amostra_fixa_e_sem_repeticao():
    a = revisao.itens_sentido()
    b = revisao.itens_sentido()
    assert [i["id"] for i in a] == [i["id"] for i in b]
    assert len(a) == revisao.SENTIDO_AMOSTRA
    assert len({i["id"] for i in a}) == len(a)
    assert all(i["resposta"] and i["texto"] for i in a)


def test_conjunto_desconhecido_recusado():
    with pytest.raises(ValueError):
        revisao.arquivo_revisao("sentido:../../outra_coisa")
    with pytest.raises(ValueError):
        revisao.arquivo_revisao("neg:../x")
