# AGENTS.md

Política deste projeto para qualquer agente de código que trabalhe nele (Claude Code, Copilot, Cursor).
Convenção pública de instruções em Markdown na raiz (Aula 7, p. 55).

## O que é o projeto

Agente de revisão de literatura com rastreio de fonte, em Python, para o domínio de computação
heterogênea em aviônica crítica. É o código do Projeto Final da TE-251 (artigo IEEE + defesa).
Tudo o que o artigo afirma precisa existir aqui e aparecer na demo.

Enquadramento aeroespacial: em aeroespacial, um claim precisa deixar rastro do requisito à fonte
e à evidência (Semana 2, p. 48); um claim falso que entra no processo de engenharia é o perigo
que grounding, evals, harness e HITL mitigam (Semana 2, p. 52).

## Regras que não mudam

- As tools do agente são **somente leitura**. Não adicione tool que execute comandos, apague ou
  escreva arquivos. Gravar um fichamento só acontece em `agente/hitl.py`, depois da aprovação humana.
- Toda citação usa a página **física** do PDF (1 = primeira página do arquivo), a mesma do gabarito.
- Só modelos sem custo de API: Ollama local, Ollama Cloud (plano gratuito), Groq (plano gratuito),
  Gemini (plano gratuito) e OpenRouter (modelos `:free`).
- Nunca versione `.env`, `corpus/*.pdf`, `logs/` ou `fichamentos/`.
- O horário de cada decisão da autora é dado pessoal, como uma chave de API: fica só em
  `logs/revisao_horarios.jsonl`. Nenhum arquivo versionado leva horário de revisão (só data, quando preciso).
- O servidor da interface só aceita pedidos da própria página (Host, Origin e JSON conferidos em
  `app.py`). Não afrouxe essas checagens nem abra o servidor para fora de `127.0.0.1`.
- Contêineres publicam porta só em `127.0.0.1` e usam versão fixa (nada de `:latest`).
- Documentos de distribuição restrita não vão para provedor cujo plano gratuito treina com os
  dados (Gemini gratuito). Ver "Segurança e privacidade" no README.
- Toda mudança de comportamento do agente que o artigo vai citar precisa ficar visível no log
  (`logs/*.jsonl`).
- O system prompt está congelado para a avaliação completa (desde 19/10, com a regra da premissa).
  Mudou o prompt, roda a avaliação de novo e versiona os resultados (`_v2`, `_v3`).
- Decisão humana sobre o gabarito vale pelo `revisao_gabarito.csv`, não pela coluna Status da planilha.
- A pré-conferência do Claude só sugere. O artigo declara que ela existiu e reporta quantas
  sugestões a autora aceitou ou mudou; ela nunca substitui a decisão humana.

## Antes de terminar qualquer mudança

- `pytest` e `ruff check .` passando (o CI roda os dois e o `pip-audit` a cada envio).
- Bug corrigido ganha um teste que falharia sem a correção.
- Número citado no artigo sai de `python resumo_avaliacao.py`, nunca digitado à mão.

## Como rodar

```
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python -m agente.corpus
python app.py        (interface no navegador)
python main.py       (terminal)
```

## Onde fica cada coisa

| Arquivo | Papel |
|---|---|
| `agente/config.py` | Provedores, modelos e caminhos |
| `agente/corpus.py` | Lista dos 11 documentos (8 artigos + 3 de aviônica) e extração por página |
| `agente/busca.py` | Busca BM25 por trecho |
| `agente/tools.py` | Tools expostas ao modelo |
| `agente/harness.py` | System prompt e loop agêntico |
| `agente/verificador.py` | Checagem determinística das citações |
| `agente/hitl.py` | Gate humano e gravação do fichamento |
| `skills/` | Skills carregadas sob demanda pelo agente |
| `app.py`, `web/` | Interface no navegador: abas Perguntar, Histórico e Revisar; `abrir_agente.bat` abre com dois cliques |
| `web/vendor/` | PDF.js 4.10.38 (Apache-2.0), empacotado para grifar a página do PDF sem depender de CDN |
| `avaliar.py` | Avaliação contra o gabarito (taxa de acerto das citações) e perguntas negativas (`--negativas`) |
| `negativas.py` | 12 perguntas cuja resposta certa é recusar ou corrigir a premissa, com a resposta esperada |
| `seguranca.py` | Regras de segurança do servidor local (Host, Origin, JSON, ids), testáveis sem o corpus |
| `tests/`, `pyproject.toml`, `.github/workflows/testes.yml` | Testes (pytest), lint (ruff) e CI com pip-audit; rodam sem corpus e sem chaves |
| `corpus_fontes.py`, `corpus/FONTES.md` | Origem (DOI) e SHA-256 de cada PDF do corpus; `--conferir` checa uma cópia baixada |
| `resultados/execucoes.jsonl` | Uma linha por rodada de avaliação: commit, hash do system prompt e do gabarito, versões |
| `revisao.py` | Revisão humana da avaliação (aba Revisar da interface): grava `revisao_gabarito.csv` e `resultados/revisao_neg_*.csv` |
| `pre_conferencia_gabarito.json` | Pré-conferência do gabarito feita pelo Claude (sugestão e trecho literal); rascunho, não é revisão |
| `resumo_avaliacao.py` | Recalcula todos os números da avaliação a partir dos CSVs e grava `resultados/resumo_numeros.md` (fonte dos números do artigo) |
| `revisar_negativas.py` | Exporta a revisão das negativas para planilha (`resultados/revisao_*.xlsx`) |
| `gabarito-corpus-avaliacao.xlsx` | Gabarito: 109 afirmações com página (77 dos artigos + 32 de aviônica), a revisar pela autora |
| `experimentos/` | Experimentos citados no artigo (idioma, pergunta-armadilha) |
| `teste_rapido.py` | Uma pergunta, sem gate humano, para comparar modelos |
| `listar_modelos.py` | Modelos gratuitos disponíveis no momento |
| `resultados/` | CSVs dos experimentos e da avaliação (versionar: são a evidência do artigo) |

## Regras criadas a partir de falhas observadas

| Data | Falha | Regra | Onde |
|---|---|---|---|
| 19/10 | Modelo diz "não consta" sem ter buscado | Verificador marca "recusa sem página lida" | `agente/verificador.py` |
| 19/10 | Agente buscou 10 vezes um número que o artigo não tem; estourou 8 mil tokens no Groq | Máximo de 3 buscas no system prompt + trava de 4 tools no harness | `agente/harness.py`, `MAX_TOOLS` |
| 19/10 | Verificador não via números como "8x" | Padrão de número aceita "x" e "×" | `agente/verificador.py` |
| 19/10 | Verificador lia "**Título**" como frase sem citação | Tira só o marcador de lista e pula linhas de título | `agente/verificador.py` |
| 19/10 | Slides repetem o menu lateral em todas as páginas e a busca se perdia | Índice remove linhas presentes em 60% ou mais das páginas de um documento | `agente/corpus.py` |
| 19/10 | Ligaduras do PDF ("ﬂight") impediam achar "flight" | Texto normalizado (NFKC) no índice | `agente/corpus.py` |
| 19/10 | Skill de fichamento pedia 5 buscas, acima da trava | Skill com 1 leitura + 3 buscas; listar e carregar Skill não gastam orçamento | `skills/fichamento/SKILL.md`, `agente/harness.py` |
| 19/10 | Em premissa falsa, o modelo escrevia "Não consta" e logo depois corrigia, com citação (frase contraditória) | Regra 4 do CRITICAL: premissa contradita começa com "A premissa não confere:" e leva citação; "Não consta" só quando o dado não existe | `agente/harness.py`, `agente/verificador.py` (`PREMISSA`), teste: `negativas.py` N04–N08 |
| 19/10 | Execução interrompida pela queda de conexão continuou rodando junto com a nova e duplicou linhas do CSV | Trava de execução por arquivo (`.lock`); ao continuar, id repetido vale a primeira execução | `avaliar.py` (`execucao_exclusiva`, `ler_feitas`) |
| 19/10 | Regex de "corrigiu" só confere palavra-chave, não se a correção está certa | Revisão humana de cada resposta negativa; o artigo reporta taxa automática e revisada | `revisao.py`, aba Revisar |
| 19/10 | Excel sem licença não salva a planilha: a revisão humana se perdia | Revisão feita na interface, gravada em CSV com data e hora; a planilha vira só exportação | `revisao.py`, `app.py`, `web/` |
| 21/10 | Modelo local (Bonsai 2 4B) lê o prompt a ~3,7 tokens/s na CPU: uma pergunta passaria de 30 min | Modelos abertos rodam pelo Ollama Cloud (plano gratuito); o local fica só como opção offline | `.env`, `web/app.js` |
| 21/10 | Docker Desktop não abre por arquivos `.sock` antigos (três dias seguidos) | Script que renomeia as pastas, sem apagar, e reabre o Docker | `consertar_docker.bat` |
| 21/10 | Leitor da correção do gabarito lia "Tesla P100" como página 100 | Página na correção só com "p.", "pág." ou "página" | `revisao.py` (`paginas_corrigidas`) |
| 21/10 | Gemma 4 cita várias páginas num colchete (`[Lozano2023 p.14, 15, 16]`), fora do formato pedido | Verificador mantido estrito (conta como erro); o resumo mostra também a contagem lendo essas citações | `resumo_avaliacao.py` |
| 26/10 | Qwen3.8 no Groq: "Request too large" (pedido acima do limite de tokens do plano gratuito) e o script esperava à toa | Esse erro pula a afirmação na hora; ela fica sem resposta e o artigo reporta quantas | `avaliar.py` (`com_retentativa`) |
| 26/10 | Acentos quebrados na janela do Windows (Python em UTF-8, console em outra codificação) | Scripts `.ps1` forçam UTF-8 na saída | `scripts/*.ps1` |
| 26/10 | "Nova conversa" apagava a tela sem jeito de rever as perguntas anteriores | Aba Histórico: lê as perguntas feitas na interface direto dos logs, com a resposta, os vereditos e a decisão humana (somente leitura) | `app.py` (`historico`), `web/` |
| 26/10 | Reconstruir o histórico a partir do log marcava "página não lida" à toa: o log corta o texto das buscas | Logs antigos mostram o veredito gravado na hora; os novos gravam as páginas lidas completas na verificação | `app.py` (`_entradas_do_log`, `rodar_job`) |
| 26/10 | Servidor local aceitava pedidos de qualquer site aberto no navegador (podia mudar a revisão humana) e não conferia o Host (DNS rebinding) | Host, Origin/Sec-Fetch-Site e corpo JSON conferidos; cabeçalhos de segurança | `app.py` (`_pedido_confiavel`) |
| 26/10 | n8n publicado em `0.0.0.0:5678`, visível na rede | Recriado em `127.0.0.1`, versão fixa 2.43.7 (o antigo ficou parado, renomeado) | Docker, README |
| 26/10 | Id do histórico aceitava `../` no nome do arquivo | Id conferido com expressão regular estrita | `app.py` (`item_historico`) |
| 26/10 | Versões soltas (`>=`, `:latest`) | `requirements.txt` com `==`; `pip-audit` sem vulnerabilidades; imagens com versão | `requirements.txt`, `scripts/preparar_ollama.ps1` |
| 26/10 | Comparações de acurácia sem teste estatístico: "o contexto longo ganhou em 2 de 3" não se sustentava (p = 0,39 e 0,73) | Resumo com IC 95% de Wilson e McNemar exato pareado | `resumo_avaliacao.py` |
| 26/10 | Nada provava que o system prompt estava congelado entre rodadas | Cada rodada grava commit e hash do prompt e do gabarito | `avaliar.py` (`registrar_execucao`) |
| 26/10 | Avaliação só mede o número da página, não o sentido | Revisão de sentido numa amostra fixa de 30 respostas | `revisao.py` (`itens_sentido`), aba Revisar |
| 26/10 | Provedor travado prendia a interface por até 10 min | Tempo limite de 120 s por chamada | `agente/harness.py` |
| 26/10 | CSVs de revisão publicavam o horário de cada decisão da autora | Horário só em `logs/revisao_horarios.jsonl`; histórico do git reescrito sem horários (envio forçado autorizado pela autora) | `revisao.py`, teste em `tests/test_revisao.py` |
| 28/10 | No Windows, dois servidores abriam a mesma porta (SO_REUSEADDR do Python): pedidos de teste podiam cair na interface de verdade | `SO_EXCLUSIVEADDRUSE` no Windows; testes de interface em porta própria (8790+) | `app.py` (`ServidorLocal`), `tests/ui/conftest.py` |

## Quando uma falha se repetir

Falha observada vira regra aqui ou na Skill, e vira caso de teste (Semana 2, p. 69).
