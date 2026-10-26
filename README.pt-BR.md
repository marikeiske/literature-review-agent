# Agente de revisão de literatura com rastreio de fonte

*[English version](README.md)*

Projeto Final da TE-251 (2026.2). Domínio: revisão de literatura em computação heterogênea para
aviônica crítica (modelos de programação, aceleradores, hypervisors e particionamento, verificação
de tempo real). Em aeroespacial, toda afirmação precisa deixar rastro até a fonte.

Você pergunta sobre os artigos do corpus; o agente busca nos PDFs, responde com uma afirmação por
linha e a página de cada uma, e só grava o fichamento depois que você aprova.

## Abrir a interface

Dê dois cliques em **`abrir_agente.bat`**. O navegador abre a mesa de revisão em
`http://127.0.0.1:8765`. Para encerrar, feche a janela preta que abriu junto.

A interface tem três abas. **Perguntar**: escreva a pergunta embaixo, acompanhe a trilha do que o
agente fez, clique numa etiqueta de página para abrir o PDF ao lado (com os números da frase
grifados) e decida:
**Aprovar e salvar** grava em `fichamentos/`, **Pedir correção** devolve ao agente,
**Rejeitar** só registra no log. Na margem: ✓ página lida e números conferem, ? número que
não está na página, ✗ página não lida ou recusa sem ler nada, ! frase sem página.
**Histórico**: as perguntas anteriores, lidas dos logs, com a decisão que cada uma recebeu.
**Revisar**: a revisão humana da avaliação (abaixo).

## Rodar no terminal do VS Code (Windows)

1. Abra esta pasta no VS Code (Arquivo → Abrir Pasta).
2. Abra o terminal do VS Code (Ctrl + ') e rode:

```
.venv\Scripts\activate
python main.py
```

O ambiente virtual (`.venv`), as dependências e o índice das páginas (`dados/paginas.json`)
já estão prontos. Se precisar refazer do zero:

```
py -3.11 -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python -m agente.corpus
```

## Modelos (todos sem custo)

| Provedor | Modelo padrão | Limite gratuito (out/2026) |
|---|---|---|
| Groq (padrão) | `openai/gpt-oss-120b` | 200 mil tokens/dia e 8 mil tokens/minuto por modelo |
| Gemini | `gemini-flash-lite-latest` | plano gratuito do AI Studio; limites por modelo, ver no AI Studio |
| OpenRouter | `nvidia/nemotron-3-ultra-550b-a55b:free` | 50 requisições/dia sem comprar créditos (o Super saiu do ar em 20/10) |
| Ollama Cloud | `gemma4:31b-cloud`, `gpt-oss:120b-cloud`, `nemotron-3-ultra:cloud` (o `minimax-m3.1-flash:cloud` saiu do plano gratuito em 23/10) | plano gratuito com limite por sessão (5 h) e por semana; precisa do Docker aberto e da conta conectada (`docker exec -it ollama-novo ollama signin`) |
| Ollama (local) | `bonsai-2:4b` | fora da interface desde 26/10: lê o prompt a ~3,7 tokens/s na CPU (21/10), inviável; continua acessível pelo terminal (`/model ollama`) |

Dentro do agente, troque com `/model groq`, `/model gemini`, `/model openrouter` ou `/model ollama:qwen2.5:1.5b`.
Para ver os modelos gratuitos do momento: `python listar_modelos.py`.

## Avaliação (resultado principal do artigo)

```
python avaliar.py groq --por-artigo 3           piloto: 33 afirmações (3 por documento: início, meio e fim)
python avaliar.py groq                          as 109 afirmações do gabarito
python avaliar.py groq --condicao contexto      sem RAG: artigo inteiro no prompt
python avaliar.py groq --negativas              12 perguntas em que o certo é recusar ou corrigir
python revisar_negativas.py                     exporta a sua revisão das negativas para planilha
```

## Revisão humana (aba Revisar)

Na interface, a aba **Revisar** mostra um item por vez, com a página da fonte aberta ao lado.

- **Gabarito:** a página sustenta a afirmação? Aprovada, Corrigir ou Rejeitar. Em Corrigir,
  escreva a página certa (por exemplo, `p. 2`): a avaliação passa a usar essa página.
  Rejeitar tira a afirmação da avaliação. Grava em `revisao_gabarito.csv`.
- **Negativas:** a resposta do agente confere com a esperada? Confere, Parcial ou Não confere,
  com observação. Grava em `resultados/revisao_<rodada>.csv`.
- **Sentido:** amostra fixa de 30 respostas do melhor modelo (Nemotron 3 Ultra). A avaliação
  automática só confere o número da página; aqui você julga se a página citada sustenta mesmo a
  afirmação. Grava em `resultados/revisao_sentido_<rodada>.csv`.


Teclas 1, 2 e 3 decidem; as setas navegam. Cada decisão fica com data e hora. Para anexar ao
artigo, `python revisar_negativas.py` exporta a revisão das negativas para planilha.

Se a cota do dia acabar, rode o mesmo comando no dia seguinte: ele continua de onde parou.
Os resultados ficam em `resultados/`. Só entram afirmações do gabarito que não estão como
"Rejeitar"; revise a coluna Status da planilha antes da rodada final.

Outros testes: `python teste_rapido.py groq "pergunta"` e `python -m experimentos.idioma groq`.

## Testes e qualidade

```
pip install -r requirements-dev.txt
pytest                      verificador, leitura de páginas, segurança do servidor, estatística
ruff check .                lint
python -m pip_audit -r requirements.txt
```

O GitHub Actions (`.github/workflows/testes.yml`) roda os três a cada envio. Os testes não
precisam do corpus nem de chaves.

## Reprodutibilidade

- `python resumo_avaliacao.py` recalcula todos os números a partir dos CSVs e grava
  `resultados/resumo_numeros.md`, com intervalo de confiança de 95% (Wilson) e comparações
  pareadas (McNemar exato).
- Cada rodada do `avaliar.py` grava em `resultados/execucoes.jsonl` o commit, o hash do system
  prompt e do gabarito revisado, as versões e os parâmetros.
- Os PDFs não estão no repositório. `corpus/FONTES.md` diz de onde vem cada um e traz o SHA-256;
  `python corpus_fontes.py --conferir` confere os PDFs baixados.

## Comandos

`/model`, `/context`, `/chamadas`, `/log`, `/clear`, `/sair` (os mesmos da demo da disciplina,
mais `/chamadas`, que conta as requisições).

## Onde fica cada coisa

- `logs/` — um arquivo por sessão com cada chamada, tool, verificação e decisão sua.
- `fichamentos/` — os fichamentos que você aprovou.
- `AGENTS.md` — regras do projeto e mapa dos arquivos.
- `skills/fichamento/SKILL.md` — instruções carregadas quando você pede o fichamento de um artigo.

## Licença

Código sob licença MIT (`LICENSE`). Não cobre os PDFs do corpus nem o PDF.js em `web/vendor`
(Apache-2.0).

## Segurança e privacidade

Análise feita em 26/10/2026. O que foi corrigido e o que continua como risco declarado.

**Servidor local (`app.py`)**
- Escuta só em `127.0.0.1`. Recusa pedidos com `Host` diferente de `127.0.0.1`/`localhost` na
  porta certa, o que bloqueia *DNS rebinding*.
- Alterações (POST) só valem quando vêm da própria página: o servidor confere `Origin` e
  `Sec-Fetch-Site` e exige corpo JSON. Sem isso, qualquer site aberto no navegador poderia mudar
  a revisão humana (`revisao_gabarito.csv`) ou gastar a cota dos provedores.
- Cabeçalhos: `Content-Security-Policy`, `X-Frame-Options`, `X-Content-Type-Options`, `Referrer-Policy`.
- O texto dos PDFs e as respostas dos modelos passam por escape antes de virar HTML.
  `/pdf/` só serve PDFs do corpus, e `/vendor/` só serve arquivos da pasta `web/vendor`.

**Docker**
- n8n (`n8nio/n8n:2.43.7`) e Ollama (`ollama/ollama:0.40.6`) publicam porta só em `127.0.0.1`.
  O n8n estava em `0.0.0.0:5678`, acessível por qualquer pessoa na mesma rede.
  Para recriar o n8n do mesmo jeito:
  ```
  docker run -d --name n8n --restart unless-stopped -p 127.0.0.1:5678:5678 -e GENERIC_TIMEZONE=America/Sao_Paulo -e TZ=America/Sao_Paulo -e N8N_ENFORCE_SETTINGS_FILE_PERMISSIONS=true -v n8n_te251:/home/node/.n8n n8nio/n8n:2.43.7
  docker network connect te251 n8n
  ```

**Dependências**
- Versões fixas em `requirements.txt`. `python -m pip_audit` em 26/10: nenhuma vulnerabilidade
  conhecida (pip e setuptools do `.venv` foram atualizados).

**Riscos que continuam (declarados no artigo, seção de AI Assurance)**
- *Prompt injection* indireta: o texto dos PDFs entra no prompt. Um PDF com instruções escondidas
  pode induzir uma resposta falsa. Barreiras: tools só de leitura, verificador (página lida e
  números), e nada vira fichamento sem aprovação humana.
- Dados que saem da máquina: trechos do corpus vão para o provedor escolhido.
  - Gemini, plano gratuito: o Google usa o conteúdo enviado para melhorar produtos, revisores
    humanos podem ler, e os termos pedem para não enviar informação confidencial
    (Gemini API Additional Terms, seção "How Google Uses Your Data", Unpaid Services).
    Não use o Gemini gratuito com documentos de distribuição restrita.
  - Groq: por padrão não retém dados de inferência; pode guardar até 30 dias para
    confiabilidade e abuso (console.groq.com/docs/your-data). A página não fala de treino.
  - Ollama Cloud: "Prompt or response data is never logged or trained on" (ollama.com/cloud).
- O verificador não confere se o trecho sustenta o sentido da frase: isso continua sendo da pessoa.

## Ollama no Docker

O agente usa o contêiner `ollama-novo` (Ollama 0.40.6, porta 11435, contexto de 8192 tokens).
`preparar_ollama.bat` cria o contêiner, baixa o modelo local e faz uma pergunta de teste.
Se o Docker travar ao abrir, use `consertar_docker.bat`: renomeia as pastas de `.sock` antigas e reabre o Docker.

O contêiner antigo, descrito abaixo, continua com o Qwen3 1,7B.

O contêiner `ollama-porta` repassa a porta 11434 do Windows para o contêiner `ollama`
(rede `te251`), sem mexer no que o n8n usa. Se o Docker não subir com erro de `.sock`,
renomeie a pasta citada no erro (em `%LOCALAPPDATA%\Docker\run` ou
`%LOCALAPPDATA%\docker-secrets-engine`) e abra o Docker de novo.
