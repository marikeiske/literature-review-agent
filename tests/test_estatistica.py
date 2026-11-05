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


def test_pass_k():
    # N01 passa nas 3; N02 passa em 1 de 3; N03 só tem 2 tentativas e fica de fora
    t = {"N01": [1, 1, 1], "N02": [0, 1, 0], "N03": [1, 1]}
    assert r.pass_k(t, 3) == (2, 1, 2)
    assert r.pass_k(t, 2) == (3, 2, 3)


def test_parcial_conta_como_falha():
    revs = {"N01": {"status": "Confere"}, "N02": {"status": "Parcial"}, "N03": {"status": "Não confere"}, "N04": {}}
    assert r.binario_humano(revs, ["N01", "N02", "N03", "N04"]) == (1, 3)


def test_caminho_dos_logs(tmp_path):
    import json
    llm = {"tipo": "chamada_llm"}
    eventos = [{"tipo": "pergunta"}, {"tipo": "tool", "nome": "buscar_trechos"}, {"tipo": "tool", "nome": "listar_artigos"}, llm,
               {"tipo": "pergunta"}, {"tipo": "tool", "nome": "buscar_trechos"}, {"tipo": "tool", "nome": "ler_pagina"},
               {"tipo": "trava"}, llm, {"tipo": "ramo_de_erro"},
               {"tipo": "pergunta"}, llm,                          # respondeu sem buscar
               {"tipo": "pergunta"}, {"tipo": "erro"}]            # erro do provedor: fica de fora
    (tmp_path / "sessao_x.jsonl").write_text("\n".join(json.dumps(e) for e in eventos), encoding="utf-8")
    c = r.caminho_dos_logs(tmp_path)
    assert c["perguntas"] == 3 and c["sem_resposta"] == 1 and c["sem_busca"] == 1
    assert c["distribuicao"] == {0: 1, 1: 1, 2: 1} and c["trava"] == 1 and c["ramo_de_erro"] == 1


def test_separar_suites():
    rodadas = {("A", "rag"): {"x": 1, "y": 0, "z": 1}, ("B", "rag"): {"x": 1, "y": 1, "z": 0},
               ("A", "contexto"): {"x": 0, "y": 0, "z": 0}, ("C", "rag"): {"x": 0}}  # C incompleta: fica de fora
    s = r.separar_suites(rodadas, ["x", "y", "z"])
    assert s == {"rodadas_usadas": 2, "capacidade": ["y", "z"], "regressao": ["x"]}
