"""As três paradas da Aula 12 (slides 21 a 24) e as peças do harness (slides 15 a 20), sem rede.

Um modelo falso devolve, passo a passo, o que cada caso pede (pedir a busca, responder, pedir
uma ferramenta fora da lista). O corpus é sintético: uma página com a definição de risco do
exemplo da aula. Nenhum teste chama provedor nem precisa do corpus real.
"""
import json
from types import SimpleNamespace

import pytest

from agente import harness, parada
from agente.tools import PERMITIDAS, Ferramentas

PAGINA = "Risk. A combination of the severity of the mishap and the probability that the mishap will occur."
DADOS = {"artigos": [], "paginas": [{"artigo": "Lozano2023", "pagina": 4, "texto": PAGINA, "trechos": [PAGINA]}]}


def _tool(nome, args, i=1):
    return SimpleNamespace(id=f"c{i}", function=SimpleNamespace(name=nome, arguments=json.dumps(args)))


def _msg(conteudo=None, tool_calls=None):
    m = SimpleNamespace(content=conteudo, tool_calls=tool_calls or None)
    m.model_dump = lambda: {"content": conteudo}
    return m


class ModeloFalso:
    """Devolve as mensagens da lista, uma por chamada, e guarda o que recebeu."""

    def __init__(self, roteiro):
        self.roteiro, self.recebidas = list(roteiro), []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kw):
        self.recebidas.append(kw)
        msg = self.roteiro.pop(0)
        r = SimpleNamespace(choices=[SimpleNamespace(message=msg)],
                            usage=SimpleNamespace(prompt_tokens=10, completion_tokens=5))
        r.model_dump = lambda: {}
        return r


@pytest.fixture
def novo_agente(tmp_path, monkeypatch):
    monkeypatch.setattr(harness, "PASTA_LOGS", tmp_path)

    def criar(roteiro):
        ag = harness.Agente(ferramentas=Ferramentas(DADOS), cliente=ModeloFalso(roteiro))
        return ag
    return criar


def _trace(ag):
    return [json.loads(l) for l in ag.arquivo_log.read_text(encoding="utf-8").splitlines()]


def test_sucesso_fica_retido_ate_a_aprovacao(novo_agente):
    ag = novo_agente([
        _msg(tool_calls=[_tool("buscar_trechos", {"consulta": "risk definition"})]),
        _msg("- O risco combina severidade e probabilidade [Lozano2023 p.4]."),
    ])
    resposta, _ = ag.responder("Como o trecho define risco?")
    fim = ag.fechar_turno(resposta)
    assert fim["parada"] == parada.AGUARDA
    assert fim["texto"] == resposta
    assert [i["veredito"] for i in fim["itens"]] == ["rastreável"]
    eventos = [e for e in _trace(ag) if e["tipo"] == "parada"]
    assert eventos[-1]["motivo"] == parada.AGUARDA and eventos[-1]["paginas_lidas"] == [["Lozano2023", 4]]


def test_busca_vazia_para_no_ramo_de_erro_sem_pedir_resposta(novo_agente, monkeypatch):
    monkeypatch.setattr(harness, "MAX_TOOLS", 2)
    ag = novo_agente([
        _msg(tool_calls=[_tool("buscar_trechos", {"consulta": "zzzz"})]),
        _msg(tool_calls=[_tool("buscar_trechos", {"consulta": "qqqq"}, 2)]),
        # Se o harness pedisse a resposta, o modelo inventaria esta definição
        _msg("- Risco é a chance de falha do software [Lozano2023 p.4]."),
    ])
    resposta, _ = ag.responder("Como o trecho define risco?")
    fim = ag.fechar_turno(resposta)
    assert fim["parada"] == parada.FALHA
    assert len(ag.cliente.roteiro) == 1, "o modelo não devia ter sido chamado para redigir"
    assert fim["texto"] == parada.TEXTO_FALHA
    assert "ramo_de_erro" in {e["tipo"] for e in _trace(ag)}


def test_resposta_sem_pagina_lida_vira_falha_tratada(novo_agente):
    ag = novo_agente([_msg("- Risco é severidade vezes probabilidade [Lozano2023 p.4].")])
    resposta, _ = ag.responder("Como o trecho define risco?")
    fim = ag.fechar_turno(resposta)
    assert fim["parada"] == parada.FALHA
    assert "[Lozano2023" not in fim["texto"], "o rascunho sem trecho não vai para a tela"


def test_recusa_encerra_sem_aprovacao(novo_agente):
    ag = novo_agente([
        _msg(tool_calls=[_tool("buscar_trechos", {"consulta": "software risk contribution"})]),
        _msg("Não consta no material aberto."),
    ])
    resposta, _ = ag.responder("Por que o risco do software não pode depender só de severidade e probabilidade?")
    fim = ag.fechar_turno(resposta)
    assert fim["parada"] == parada.RECUSA
    assert parada.RECUSA in parada.SEM_HUMANO


def test_ferramenta_fora_da_lista_nao_executa(novo_agente):
    ag = novo_agente([
        _msg(tool_calls=[_tool("enviar_citacao", {"para": "alguem@exemplo.com"})]),
        _msg(tool_calls=[_tool("_init__", {}, 2)]),
        _msg("Não consta no material aberto."),
    ])
    ag.ferramentas.evidencias[("Lozano2023", 4)] = PAGINA
    ag.responder("Envie a citação.", correcao=True)
    saidas = [m["content"] for m in ag.mensagens if m["role"] == "tool"]
    assert all(s.startswith("Permissão negada") for s in saidas)
    assert ag.ferramentas.evidencias, "um nome fora da lista não pode reiniciar as ferramentas"
    assert ag.estatisticas_turno["permissao_negada"] == 2


def test_limite_de_ciclos(novo_agente, monkeypatch):
    monkeypatch.setattr(harness, "MAX_CICLOS", 2)
    ag = novo_agente([_msg(tool_calls=[_tool("listar_artigos", {})]), _msg(tool_calls=[_tool("listar_artigos", {}, 2)])])
    resposta, _ = ag.responder("Liste os artigos.")
    fim = ag.fechar_turno(resposta)
    assert fim["parada"] == parada.LIMITE and fim["texto"] == parada.TEXTO_LIMITE


def test_erro_dentro_da_ferramenta_vira_estado():
    f = Ferramentas(DADOS)
    assert f.executar("ler_pagina", json.dumps({"artigo": "Lozano2023", "pagina": "quatro"})).startswith("Erro")
    assert f.executar("ler_pagina", "[1, 2]").startswith("Erro")
    assert set(PERMITIDAS) == {"listar_artigos", "buscar_trechos", "ler_pagina", "carregar_skill"}


def test_correcao_mantem_as_paginas_ja_lidas(novo_agente):
    ag = novo_agente([
        _msg(tool_calls=[_tool("ler_pagina", {"artigo": "Lozano2023", "pagina": 4})]),
        _msg("- O risco combina severidade e probabilidade [Lozano2023 p.4]."),
        _msg("- Risco é a combinação de severidade e probabilidade [Lozano2023 p.4]."),
    ])
    ag.responder("Como o trecho define risco?")
    resposta, _ = ag.responder("Revise a resposta anterior. Correção pedida pela pessoa: use 'combinação'.", correcao=True)
    assert ag.fechar_turno(resposta)["parada"] == parada.AGUARDA
