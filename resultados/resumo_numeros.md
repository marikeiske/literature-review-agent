# Números da avaliação (gerado em 2026-10-26 por resumo_avaliacao.py)

Gabarito: 109 afirmações, com a revisão da autora aplicada (revisao_gabarito.csv).

## Afirmações do gabarito (página citada)

| Modelo | Condição | Avaliadas | Página exata | Exata antes de ver respostas* | ±1 página | Exata lendo citações de várias páginas | Citações de várias páginas | Recusas | Citou página não lida | Número ausente | Copiou marcador <<<PÁGINA N>>> | Exata início/meio/fim |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Gemini Flash-Lite (Google) | contexto | 109 | 103/109 (94%) | 103/109 (94%) | 105/109 (96%) | 105/109 (96%) | 2 | 0 | 0 | 23 | 97 | 46/48 (96%) / 30/31 (97%) / 27/30 (90%) |
| Gemini Flash-Lite (Google) | rag | 109 | 99/109 (91%) | 97/109 (89%) | 100/109 (92%) | 102/109 (94%) | 3 | 2 | 0 | 2 | 0 | 44/48 (92%) / 29/31 (94%) / 26/30 (87%) |
| GPT-OSS 120B (Groq) | rag | 109 | 104/109 (95%) | 103/109 (94%) | 104/109 (95%) | 104/109 (95%) | 0 | 0 | 0 | 3 | 0 | 45/48 (94%) / 31/31 (100%) / 28/30 (93%) |
| Qwen3.8 27B (Groq) | rag | 80 | 80/80 (100%) | 79/80 (99%) | 80/80 (100%) | 80/80 (100%) | 0 | 0 | 0 | 4 | 0 | 31/31 (100%) / 27/27 (100%) / 22/22 (100%) |
| Gemma 4 31B (Ollama Cloud) | contexto | 109 | 105/109 (96%) | 105/109 (96%) | 106/109 (97%) | 107/109 (98%) | 2 | 0 | 0 | 4 | 0 | 47/48 (98%) / 31/31 (100%) / 27/30 (90%) |
| Gemma 4 31B (Ollama Cloud) | rag | 109 | 103/109 (94%) | 100/109 (92%) | 104/109 (95%) | 107/109 (98%) | 4 | 0 | 0 | 2 | 0 | 47/48 (98%) / 29/31 (94%) / 27/30 (90%) |
| GPT-OSS 120B (Ollama Cloud) | contexto | 109 | 95/109 (87%) | 94/109 (86%) | 107/109 (98%) | 95/109 (87%) | 0 | 0 | 0 | 7 | 0 | 41/48 (85%) / 30/31 (97%) / 24/30 (80%) |
| GPT-OSS 120B (Ollama Cloud) | rag | 109 | 104/109 (95%) | 102/109 (94%) | 106/109 (97%) | 104/109 (95%) | 0 | 1 | 0 | 2 | 0 | 45/48 (94%) / 31/31 (100%) / 28/30 (93%) |
| Nemotron 3 Ultra (Ollama Cloud) | rag | 109 | 106/109 (97%) | 104/109 (95%) | 107/109 (98%) | 106/109 (97%) | 0 | 0 | 0 | 4 | 0 | 46/48 (96%) / 31/31 (100%) / 29/30 (97%) |

Na condição contexto o artigo inteiro vai no prompt, então toda página conta como lida: "citou página não lida" é zero por construção e não se compara com o RAG. Quando o modelo copia o marcador <<<PÁGINA N>>> na resposta, o verificador lê N como número da frase e pode marcar "número ausente" por engano: compare as duas colunas.

\* Sem as correções de página feitas depois de ver as respostas dos modelos (A1-08, A8-11, A9-02): nesses itens vale a página original da planilha.

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

## Revisão humana do gabarito (HITL)

- Revisadas: 109 de 109. Corrigir: 21, Aprovada: 88
- Correções que mudam a página: 6 (A1-01, A1-08, A5-08, A7-09, A8-11, A9-02); as outras corrigem o texto da paráfrase.
- Pré-conferência do Claude × decisão da autora: Claude Aprovada → autora Aprovada: 88; Claude Aprovada → autora Corrigir: 18; Claude Corrigir → autora Corrigir: 3
