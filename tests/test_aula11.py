"""Grader de código do caso da sala (Aula 12, slides 33, 34 e 47 a 49), sem rede e sem o data.zip."""
import pytest

from experimentos.aula11_norma import grader_codigo

TRECHO = ("Paragraph 3.2.28:\nRisk. A combination of the severity of the mishap and the probability that the "
          "mishap will occur.\n\nQuestion: How does this excerpt define risk?")
CITA = "Under paragraph 3.2.28, risk is a combination of severity and probability."
RECUSA = "not in the material."


@pytest.mark.parametrize("alvo, resposta, veredito", [
    (CITA, CITA, "passa"),                                                     # slide 47
    (CITA, "Under paragraph 4.4, software risk cannot rely only on severity and probability.", "falha: fora do trecho"),  # slide 48
    (CITA, "Risk is a combination of severity and probability.", "falha: sem parágrafo"),
    (CITA, RECUSA, "falha: recusou"),
    (RECUSA, RECUSA, "passa"),                                                 # slide 49
    (RECUSA, "Not in the material", "passa"),
    (RECUSA, "The excerpt does not cover software; not in the material for this question.", "ao juiz"),  # slide 34
    (RECUSA, CITA, "falha: não recusou"),
])
def test_grader_de_codigo(alvo, resposta, veredito):
    assert grader_codigo(TRECHO, alvo, resposta) == veredito


def test_numero_que_aparece_no_trecho_vale():
    trecho = "Paragraph 4.2:\nSection 4 defines the system safety requirements.\n\nQuestion: What does Section 4 define?"
    assert grader_codigo(trecho, "x", "Under paragraph 4.2, Section 4 defines the requirements.") == "passa"


def test_decimal_da_frase_nao_vira_citacao():
    trecho = "Paragraph 3.2.1:\nThe ratio is 0.5 at most.\n\nQuestion: What is the ratio?"
    assert grader_codigo(trecho, "x", "Under paragraph 3.2.1, the ratio is 0.5 at most.") == "passa"
