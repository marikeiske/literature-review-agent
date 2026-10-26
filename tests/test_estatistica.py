"""Estatística do resumo: IC de Wilson e McNemar exato (resultados/resumo_numeros.md)."""
import resumo_avaliacao as r


def test_wilson():
    assert r.wilson(106, 109) == "92–99%"
    assert r.wilson(0, 0) == "–"


def test_mcnemar_exato():
    # 12 contra 3 discordantes: p = 0,035 (GPT-OSS, RAG × contexto, 26/10)
    a = {i: 1 for i in range(15)} | {i: 0 for i in range(15, 18)}
    b = {i: 0 for i in range(12)} | {i: 1 for i in range(12, 18)}
    n, so_a, so_b, p = r.mcnemar(a, b)
    assert (n, so_a, so_b) == (18, 12, 3)
    assert round(p, 3) == 0.035


def test_mcnemar_sem_discordancia():
    assert r.mcnemar({1: 1, 2: 0}, {1: 1, 2: 0})[3] == 1.0
