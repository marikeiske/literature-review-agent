"""Perguntas negativas: a resposta certa é recusar ou corrigir a premissa.

Avaliação mínima da Aula 5 (p. 74): além de citar o trecho certo, o agente precisa
recusar o que está fora do corpus ("não consta"). Cada pergunta foi conferida no texto
extraído dos PDFs em 19/10: o dado pedido não aparece no material.

Tipos:
  fora_do_corpus    o assunto não está em nenhum documento
  premissa_falsa    a pergunta afirma algo que o documento contradiz
  dado_inexistente  o documento trata do assunto, mas não traz o dado pedido
  so_em_figura      o dado existe só numa figura, que não vira texto

"esperado" descreve a resposta certa, com a página que a sustenta. Serve à revisão humana
(revisar_negativas.py), não à pontuação automática.

Critérios:
  modo "recusar":  acerta se recusar e não inventar
  modo "corrigir": acerta se recusar, escrever "A premissa não confere" OU corrigir a premissa
                   (regex "correcao"), sem inventar
  "invencao":      regex que denuncia dado inventado (além das falhas do verificador)
"""

NEGATIVAS = [
    {"id": "N01", "esperado": "Recusar: nenhum documento trata do ChatGPT.", "tipo": "fora_do_corpus", "modo": "recusar",
     "pergunta": "O que os artigos dizem sobre o consumo de energia do ChatGPT?",
     "invencao": None, "correcao": None},
    {"id": "N02", "esperado": "Recusar: nenhum documento traz resultados de MLPerf.", "tipo": "fora_do_corpus", "modo": "recusar",
     "pergunta": "Quais resultados de MLPerf aparecem nos artigos?",
     "invencao": None, "correcao": None},
    {"id": "N03", "esperado": "Recusar: o AC 20-193 trata de processadores multicore, não de redes neurais.", "tipo": "fora_do_corpus", "modo": "recusar",
     "pergunta": "O que o AC 20-193 da FAA diz sobre o uso de redes neurais em aviônica?",
     "invencao": None, "correcao": None},
    {"id": "N04", "esperado": "Corrigir: a GPU usada foi a NVIDIA Jetson TX2, não a A100 [Nimbekar2023 p.7].", "tipo": "premissa_falsa", "modo": "corrigir",
     "pergunta": "Por que Nimbekar usou a GPU NVIDIA A100 na comparação?",
     "invencao": None, "correcao": r"Jetson|TX2"},
    {"id": "N05", "esperado": "Corrigir: nenhum backend foi o mais rápido em todo hardware; CUDA venceu nas GPUs NVIDIA e OpenCL nas AMD e Intel [Breyer2022 p.11].", "tipo": "premissa_falsa", "modo": "corrigir",
     "pergunta": "Por que o SYCL foi o mais rápido em todas as GPUs no estudo de Breyer?",
     "invencao": None, "correcao": r"CUDA|OpenCL"},
    {"id": "N06", "esperado": "Corrigir ou recusar: Sifakis não fala de GPUs; o artigo discute os limites da automação de projeto de sistemas.", "tipo": "premissa_falsa", "modo": "corrigir",
     "pergunta": "Por que Sifakis conclui que as GPUs resolvem a automação de projeto de sistemas?",
     "invencao": None, "correcao": r"nunca|never|VLSI|não (?:menciona|trata|fala)"},
    {"id": "N07", "esperado": "Corrigir: o AC 20-193 NÃO cobre simultaneous multithreading, porque o conhecimento sobre o recurso é insuficiente [FAA2024 p.2].", "tipo": "premissa_falsa", "modo": "corrigir",
     "pergunta": "Segundo o AC 20-193, por que o simultaneous multithreading é recomendado para software de nível A?",
     "invencao": None, "correcao": r"não (?:cobre|abrange|trata)|not cover|insuficiente|insufficient"},
    {"id": "N08", "esperado": "Corrigir: o modelo Buffers é mais LENTO que o USM [PeraltaQuesada2023 p.5–7].", "tipo": "premissa_falsa", "modo": "corrigir",
     "pergunta": "Por que Peralta Quesada concluiu que o modelo SYCL Buffers é mais rápido que o USM?",
     "invencao": None,
     "correcao": r"USM.{0,80}(?:mais rápid|melhor|superior|faster|better)|Buffers?.{0,80}(?:mais lent|pior|inferior|slower)"},
    {"id": "N09", "esperado": "Recusar: o artigo não informa a frequência de clock.", "tipo": "dado_inexistente", "modo": "recusar",
     "pergunta": "Qual a frequência de clock do processador no estudo de caso de Mzid?",
     "invencao": r"\d+(?:[.,]\d+)?\s*(?:MHz|GHz)", "correcao": None},
    {"id": "N10", "esperado": "Recusar: o artigo diz só que o OpenMP reduz bastante o tempo de execução, sem número de speedup [YoungS2023 p.1–2].", "tipo": "dado_inexistente", "modo": "recusar",
     "pergunta": "Qual foi o speedup numérico obtido pelos programas OpenMP de Young-S.?",
     "invencao": r"\d+(?:[.,]\d+)?\s*(?:x|×|vezes)\b", "correcao": None},
    {"id": "N11", "esperado": "Recusar: o artigo informa o modo de potência de 15 W, não a energia em joules [PeraltaQuesada2023 p.4].", "tipo": "dado_inexistente", "modo": "recusar",
     "pergunta": "Quanta energia, em joules, a Xavier gastou nos testes de Peralta Quesada?",
     "invencao": r"\d+(?:[.,]\d+)?\s*(?:J|joules?)\b", "correcao": None},
    {"id": "N12", "esperado": "Recusar: o texto diz que são quatro normas, mas os nomes estão só na figura do slide [Loubach2019 p.8].", "tipo": "so_em_figura", "modo": "recusar",
     "pergunta": "Quais são as quatro normas de certificação de aeronaves citadas por Loubach?",
     "invencao": r"ARP\s?-?47\d\d|DO-?297|DO-?160|ED-?79", "correcao": None},
]
