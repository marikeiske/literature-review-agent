# Literature-review agent with source tracing

*[Versão em português](README.pt-BR.md)*

An LLM agent that answers questions about a closed corpus of scientific papers and **cites the PDF
page behind every claim**. A deterministic verifier checks each citation, and nothing is saved
until a human approves it. Domain: heterogeneous computing for safety-critical avionics, where
every engineering claim must be traceable to its source.

Final project of TE-251 (ITA, 2026.2). The accompanying paper (IEEE format, in Portuguese) reports
the evaluation below.

## How it works

1. **Agentic RAG.** The model gets read-only tools (`buscar_trechos`, BM25 search over page
   snippets; `ler_pagina`; `listar_artigos`; `carregar_skill`) and decides what to read. A budget of
   4 tool calls per question stops search loops (`agente/harness.py`).
2. **One claim per line, with `[DocId p.N]`.** The system prompt requires a citation on every
   line, an explicit refusal ("Não consta no material aberto.") when the data is missing, and a
   correction ("A premissa não confere: …", with a citation) when the question's premise is false.
3. **Deterministic verifier** (`agente/verificador.py`, no LLM). Each line is marked as
   *traceable* (the cited page was read in this turn and its numbers appear on it), *number
   missing*, *page not read* (a fabricated citation), *refusal without reading*, or *no citation*.
   It is necessary, not sufficient: it does not check meaning.
4. **Human in the loop.** The web UI opens the cited PDF page next to the answer, with the numbers
   highlighted. The reviewer approves, asks for a correction or rejects; only approval writes a note
   to `fichamentos/` (`agente/hitl.py`).

## Results (109 gold claims, 11 documents)

Exact cited page vs. the human-reviewed gold set, agentic RAG, temperature 0
(`resultados/resumo_numeros.md`, 26 Oct 2026):

| Model (provider) | Exact page | 95% CI (Wilson) | Cited an unread page |
|---|---|---|---|
| Nemotron 3 Ultra (Ollama Cloud) | 106/109 (97%) | 92–99% | 0 |
| GPT-OSS 120B (Groq) | 104/109 (95%) | 90–98% | 0 |
| GPT-OSS 120B (Ollama Cloud) | 104/109 (95%) | 90–98% | 0 |
| Gemma 4 31B (Ollama Cloud) | 103/109 (94%) | 89–97% | 0 |
| Gemini Flash-Lite (Google) | 99/109 (91%) | 84–95% | 0 |

- **No model cited a page it had not read** (the verifier would flag it).
- **Negative questions** (out of corpus, false premise, missing data, data only in a figure):
  12/12 for every model above; a human reviewer checked every answer.
- **RAG vs. whole paper in the prompt:** no significant difference for Gemma or Gemini
  (McNemar p = 0.73 and 0.39). For GPT-OSS, RAG was better (95% vs. 87%, p = 0.035): with the
  whole paper, it found the right passage but cited the neighbouring page. Long context also costs
  about 3× more input tokens.
- **Model ranking:** the confidence intervals overlap; with 109 items, none of the differences
  between models is significant (best vs. worst p = 0.065).

Limitations and risks (data sent to third-party providers, indirect prompt injection, a single gold
set annotator) are discussed in the paper's AI Assurance section and in
[README.pt-BR.md](README.pt-BR.md#segurança-e-privacidade).

## Quick start (Windows)

```
py -3.11 -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env          (add at least one free API key)
python -m agente.corpus         (indexes the PDFs in corpus/, see corpus/FONTES.md)
python app.py                   (web UI at http://127.0.0.1:8765)
```

Or double-click `abrir_agente.bat`. Free providers only: Groq, Google AI Studio, OpenRouter
`:free` models and Ollama Cloud (free plan).

## Evaluation

```
python avaliar.py groq                       109 gold claims (resumes where it stopped)
python avaliar.py groq --condicao contexto   no RAG: whole paper in the prompt
python avaliar.py groq --negativas           12 questions whose right answer is to refuse or correct
python resumo_avaliacao.py                   all numbers, CIs and McNemar tests from the CSVs
```

Since 26 Oct 2026, every run logs the git commit, system-prompt hash and gold-set hash to `resultados/execucoes.jsonl`.
The PDFs are not in the repository (copyright; one is not for redistribution): `corpus/FONTES.md`
lists each source and its SHA-256, and `python corpus_fontes.py --conferir` checks your copies.

## Development

```
pip install -r requirements-dev.txt
pytest            verifier, page parsing, local-server security, statistics
ruff check .
```

GitHub Actions runs tests, lint and `pip-audit` on every push. Project rules for coding agents are in
`AGENTS.md`.

## Security

The local server only listens on `127.0.0.1` and rejects requests from other origins (Host, Origin and
JSON content type are checked), which blocks cross-site requests and DNS rebinding. Agent tools are
read-only. See `seguranca.py` and `tests/test_seguranca.py`.

## License

MIT for the source code (`LICENSE`). The corpus PDFs are not included; PDF.js in `web/vendor` is
Apache-2.0.
