"""Motivo de parada do ciclo (Aula 12, slides 21, 23, 24 e 28).

O trace só está completo com a parada: pergunta, ferramenta, trecho, resposta e o motivo de o
ciclo ter acabado. A frase fluente não mostra se o harness deixou a ação sair (slide 4).

Paradas deste agente:
  aguarda aprovação   há frase com página: a citação fica retida até a pessoa decidir (slide 12)
  objetivo cumprido   a pessoa aprovou e o fichamento foi gravado (slide 22)
  rejeitada           a pessoa rejeitou; nada foi gravado
  recusa              a resposta só recusa ("Não consta no material aberto.") depois de ler
                      alguma página; não há citação pendente, o humano não é chamado (slide 24)
  falha tratada       nenhuma página foi lida (busca vazia, ferramenta com erro, ou o modelo
                      respondeu sem buscar): o ramo de erro para o ciclo, a frase não sai e o
                      humano não é chamado (slides 18 e 23)
  limite              o ciclo atingiu MAX_CICLOS sem resposta final (slide 16)

"Pedir correção" não é parada: o ciclo volta com o comentário da pessoa.
"""

AGUARDA = "aguarda aprovação"
CUMPRIDO = "objetivo cumprido"
REJEITADA = "rejeitada"
RECUSA = "recusa"
FALHA = "falha tratada"
LIMITE = "limite"

# Texto que a interface e o terminal mostram no lugar do rascunho quando o ciclo para no erro.
# Começa com "Não consta" de propósito: o verificador e a avaliação continuam lendo como recusa.
TEXTO_FALHA = ("Não consta no material aberto: nenhuma página foi lida nesta pergunta, então o ciclo "
               "parou no ramo de erro (falha tratada) sem redigir afirmação.")
TEXTO_LIMITE = "Limite de ciclos atingido sem resposta final. O ciclo parou sem redigir afirmação."

# Paradas em que a pessoa NÃO é chamada: não há citação para aprovar
SEM_HUMANO = {RECUSA, FALHA, LIMITE}


def classificar(itens: list[dict], evidencias: dict, motivo_harness: str = "resposta") -> str:
    """Decide a parada a partir do que o harness registrou e do veredito do verificador.

    motivo_harness: "resposta" (o modelo respondeu), "limite" (MAX_CICLOS) ou "falha" (o harness
    parou antes de pedir a resposta, porque nada foi lido)."""
    if motivo_harness == "limite":
        return LIMITE
    if motivo_harness == "falha" or not evidencias:
        return FALHA
    if itens and all(i["veredito"] == "recusa" for i in itens):
        return RECUSA
    if not itens:
        # Resposta vazia ou só títulos: não há o que aprovar nem o que recusar
        return FALHA
    return AGUARDA


def texto_para_mostrar(parada: str, resposta: str) -> str:
    """O que a pessoa vê. Na falha e no limite, o rascunho fica só no log."""
    if parada == FALHA:
        return TEXTO_FALHA
    if parada == LIMITE:
        return TEXTO_LIMITE
    return resposta
