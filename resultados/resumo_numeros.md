# Números da avaliação (gerado em 2026-10-26 por resumo_avaliacao.py)

Gabarito: 109 afirmações, com a revisão da autora aplicada (revisao_gabarito.csv).

## Afirmações do gabarito (página citada)

| Modelo | Condição | Avaliadas | Página exata | IC 95% (Wilson) | Exata antes de ver respostas* | ±1 página | Exata lendo citações de várias páginas | Citações de várias páginas | Recusas | Citou página não lida | Número ausente | Copiou marcador <<<PÁGINA N>>> | Exata início/meio/fim | Chamadas ao LLM por afirmação | Segundos por afirmação |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Gemini Flash-Lite (Google) | contexto | 109 | 103/109 (94%) | 89–97% | 103/109 (94%) | 105/109 (96%) | 105/109 (96%) | 2 | 0 | 0 | 23 | 97 | 46/48 (96%) / 30/31 (97%) / 27/30 (90%) | 1.0 | 4.3 |
| Gemini Flash-Lite (Google) | rag | 109 | 99/109 (91%) | 84–95% | 97/109 (89%) | 100/109 (92%) | 102/109 (94%) | 3 | 2 | 0 | 2 | 0 | 44/48 (92%) / 29/31 (94%) / 26/30 (87%) | 2.2 | 24.1 |
| GPT-OSS 120B (Groq) | rag | 109 | 104/109 (95%) | 90–98% | 103/109 (94%) | 104/109 (95%) | 104/109 (95%) | 0 | 0 | 0 | 3 | 0 | 45/48 (94%) / 31/31 (100%) / 28/30 (93%) | 2.1 | 22.1 |
| Qwen3.8 27B (Groq) | rag | 80 | 80/80 (100%) | 95–100% | 79/80 (99%) | 80/80 (100%) | 80/80 (100%) | 0 | 0 | 0 | 4 | 0 | 31/31 (100%) / 27/27 (100%) / 22/22 (100%) | 2.1 | 46.9 |
| Gemma 4 31B (Ollama Cloud) | contexto | 109 | 105/109 (96%) | 91–99% | 105/109 (96%) | 106/109 (97%) | 107/109 (98%) | 2 | 0 | 0 | 4 | 0 | 47/48 (98%) / 31/31 (100%) / 27/30 (90%) | 1.0 | 1.0 |
| Gemma 4 31B (Ollama Cloud) | rag | 109 | 103/109 (94%) | 89–97% | 100/109 (92%) | 104/109 (95%) | 107/109 (98%) | 4 | 0 | 0 | 2 | 0 | 47/48 (98%) / 29/31 (94%) / 27/30 (90%) | 2.1 | 2.1 |
| GPT-OSS 120B (Ollama Cloud) | contexto | 109 | 95/109 (87%) | 80–92% | 94/109 (86%) | 107/109 (98%) | 95/109 (87%) | 0 | 0 | 0 | 7 | 0 | 41/48 (85%) / 30/31 (97%) / 24/30 (80%) | 1.0 | 1.4 |
| GPT-OSS 120B (Ollama Cloud) | rag | 109 | 104/109 (95%) | 90–98% | 102/109 (94%) | 106/109 (97%) | 104/109 (95%) | 0 | 1 | 0 | 2 | 0 | 45/48 (94%) / 31/31 (100%) / 28/30 (93%) | 2.0 | 2.0 |
| Nemotron 3 Ultra (Ollama Cloud) | rag | 109 | 106/109 (97%) | 92–99% | 104/109 (95%) | 107/109 (98%) | 106/109 (97%) | 0 | 0 | 0 | 4 | 0 | 46/48 (96%) / 31/31 (100%) / 29/30 (97%) | 2.2 | 20.4 |

Na condição contexto o artigo inteiro vai no prompt, então toda página conta como lida: "citou página não lida" é zero por construção e não se compara com o RAG. Quando o modelo copia o marcador <<<PÁGINA N>>> na resposta, o verificador lê N como número da frase e pode marcar "número ausente" por engano: compare as duas colunas.

\* Sem as correções de página feitas depois de ver as respostas dos modelos (A1-08, A8-11, A9-02): nesses itens vale a página original da planilha.

## Comparações pareadas (McNemar exato, bicaudal)

Mesmas afirmações nos dois lados; conta só as que um acertou e o outro errou. p < 0,05: diferença que dificilmente é acaso. Com 109 itens, diferenças de 2 a 4 acertos costumam não passar.

| Comparação | Afirmações em comum | Só o 1º acertou | Só o 2º acertou | p | Diferença real (p < 0,05)? |
|---|---|---|---|---|---|
| Gemini Flash-Lite (Google) (rag) × Gemini Flash-Lite (Google) (contexto) | 109 | 4 | 8 | 0.388 | não |
| Gemma 4 31B (Ollama Cloud) (rag) × Gemma 4 31B (Ollama Cloud) (contexto) | 109 | 3 | 5 | 0.727 | não |
| GPT-OSS 120B (Ollama Cloud) (rag) × GPT-OSS 120B (Ollama Cloud) (contexto) | 109 | 12 | 3 | 0.035 | sim |
| Nemotron 3 Ultra (Ollama Cloud) (rag) × GPT-OSS 120B (Groq) (rag) | 109 | 3 | 1 | 0.625 | não |
| Nemotron 3 Ultra (Ollama Cloud) (rag) × GPT-OSS 120B (Ollama Cloud) (rag) | 109 | 2 | 0 | 0.500 | não |
| Nemotron 3 Ultra (Ollama Cloud) (rag) × Gemma 4 31B (Ollama Cloud) (rag) | 109 | 5 | 2 | 0.453 | não |
| Nemotron 3 Ultra (Ollama Cloud) (rag) × Gemini Flash-Lite (Google) (rag) | 109 | 9 | 2 | 0.065 | não |

## Perguntas negativas (12: recusar ou corrigir a premissa)

| Modelo | Acerto automático | Inventou | Recusou sem ler | Revisão humana: Confere / Parcial / Não confere |
|---|---|---|---|---|
| Gemini Flash-Lite (Google) (v1) | 12/12 (100%) | 0 | 1 | 11 / 1 / 0 (de 12 revisadas) |
| Gemini Flash-Lite (Google) (v2) | 12/12 (100%) | 0 | 1 | 11 / 1 / 0 (de 12 revisadas) |
| GPT-OSS 120B (Groq) | 12/12 (100%) | 0 | 2 | 12 / 0 / 0 (de 12 revisadas) |
| Qwen3.8 27B (Groq) | 10/12 (83%) | 2 | 0 | 10 / 0 / 2 (de 12 revisadas) |
| Gemma 4 31B (Ollama Cloud) | 12/12 (100%) | 0 | 2 | 12 / 0 / 0 (de 12 revisadas) |
| GPT-OSS 120B (Ollama Cloud) | 12/12 (100%) | 0 | 1 | 12 / 0 / 0 (de 12 revisadas) |
| Nemotron 3 Ultra (Ollama Cloud) | 12/12 (100%) | 0 | 0 | 12 / 0 / 0 (de 12 revisadas) |

## Revisão de sentido (aval_ollama_nemotron-3-ultra_cloud_rag, amostra de 30, semente 2026)

A página citada sustenta a afirmação? (julgamento humano do conteúdo, não só do número da página)

- Revisadas: 30 de 30. Confere: 30, Parcial: 0, Não confere: 0. Confere: 30/30 (100%), IC 95% 89–100%.


## Revisão humana do gabarito (HITL)

- Revisadas: 109 de 109. Corrigir: 21, Aprovada: 88
- Correções que mudam a página: 6 (A1-01, A1-08, A5-08, A7-09, A8-11, A9-02); as outras corrigem o texto da paráfrase.
- Pré-conferência do Claude × decisão da autora: Claude Aprovada → autora Aprovada: 88; Claude Aprovada → autora Corrigir: 18; Claude Corrigir → autora Corrigir: 3
