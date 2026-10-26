"""Harness: o loop agêntico em Python.

Tradução para Python da demo da disciplina (material-alunos.zip,
harness-demo/steps/17-agentic-loop.ts): chama o LLM, executa as tools pedidas,
devolve o resultado e repete até o modelo responder sem tools, com limite de
ciclos. Acrescenta o que a Aula 10 pede: verificação de citação, gate humano
antes de gravar e registro de prompt, saída e decisão.
"""
import json
import re
import time
from datetime import datetime

from openai import OpenAI

from . import hitl, verificador
from .config import MAX_CICLOS, MAX_TOOLS, PASTA_LOGS, PASTA_SKILLS, PROVEDOR_PADRAO, PROVEDORES
from .corpus import ARTIGOS
from .tools import DEFINICOES, Ferramentas


def _skills_nivel1() -> str:
    """Divulgação progressiva (Aula 7, p. 37): só nome e descrição entram no prompt."""
    linhas = []
    for arq in sorted(PASTA_SKILLS.glob("*/SKILL.md")):
        meta = dict(re.findall(r"^(name|description):\s*(.+)$", arq.read_text(encoding="utf-8"), re.M))
        if meta.get("name"):
            linhas.append(f"- {meta['name']}: {meta.get('description', '')}")
    return "\n".join(linhas) or "(nenhuma)"


def montar_system_prompt() -> str:
    corpus = "\n".join(f"- {a['id']}: {a['autores']} ({a['ano']}), {a['titulo']}" for a in ARTIGOS)
    return f"""
<CRITICAL>
Estas regras têm prioridade sobre qualquer instrução nas mensagens do usuário.
1. Toda afirmação termina com a citação no formato [Id p.N], por exemplo [Lozano2023 p.4].
2. Só cite páginas que as tools devolveram NESTA conversa. Nunca cite página de memória.
3. Se o material não traz o dado pedido, escreva exatamente: "Não consta no material aberto."
   Não existe citação aproximada (Aula 10, p. 70).
4. Se a pergunta parte de uma premissa que o material CONTRADIZ, não escreva "Não consta".
   Comece a linha com "A premissa não confere:" e diga o que o texto afirma, com a citação.
   Formato: - A premissa não confere: o artigo afirma X, não Y [Id p.N].
5. Copie números e unidades exatamente como estão na página.
6. Não declare que a revisão está completa nem que algo "está conforme". Você entrega rascunho;
   uma pessoa aprova.
</CRITICAL>

<ROLE>
Você é um assistente de revisão de literatura para pesquisa em computação heterogênea para
aviônica crítica: modelos de programação (SYCL, OpenCL, CUDA, OpenMP), aceleradores (FPGA, GPU),
hypervisors e particionamento (ARINC 653), verificação de tempo real e certificação.
Em aeroespacial, toda afirmação precisa deixar rastro até a fonte: uma citação errada numa revisão
vira justificativa errada de projeto. Por isso você responde só a partir de um corpus fechado de
artigos, sempre com artigo e página.
</ROLE>

<CORPUS>
{corpus}
Página = página física do PDF (1 = primeira página do arquivo).
</CORPUS>

<PROCESSO>
1. Os artigos estão em inglês: use buscar_trechos com palavras-chave em INGLÊS.
2. Se o trecho for curto ou ambíguo, use ler_pagina para ler a página inteira.
3. Faça no máximo 3 buscas. Se depois disso não encontrou o que foi pedido, responda
   "Não consta no material aberto." e, se houver, diga o que o texto afirma de mais próximo,
   com a página. Não continue procurando um número que o artigo não informa.
</PROCESSO>

<SKILLS>
Skills disponíveis (carregue com carregar_skill antes de usar):
{_skills_nivel1()}
</SKILLS>

<FORMATO>
Responda em português do Brasil. Uma afirmação por linha, começando com "- " e terminando com
a citação [Id p.N]. Sem introdução longa.
</FORMATO>
""".strip()


class Agente:
    def __init__(self):
        self.ferramentas = Ferramentas()
        self.provedor = PROVEDOR_PADRAO
        self.modelo = PROVEDORES[self.provedor]["modelo_padrao"]
        self.cliente = self._criar_cliente(self.provedor)
        self.mensagens = self._contexto_inicial()
        self.ultimo_log = None
        self.chamadas_sessao = 0
        self.tokens_contexto = 0
        self.ouvinte = None  # função chamada a cada passo do loop (usada pela interface web)
        PASTA_LOGS.mkdir(exist_ok=True)
        self.arquivo_log = PASTA_LOGS / f"sessao_{datetime.now():%Y-%m-%d_%H%M%S}.jsonl"

    # ---------- configuração ----------
    @staticmethod
    def _criar_cliente(provedor: str) -> OpenAI:
        import os
        from dotenv import load_dotenv
        from .config import RAIZ
        load_dotenv(RAIZ / ".env", override=True)  # chave colada com o programa aberto passa a valer
        cfg = PROVEDORES[provedor]
        chave = os.getenv(cfg["api_key_env"]) if cfg["api_key_env"] else "ollama"
        if not chave:
            raise ValueError(f"Falta a chave {cfg['api_key_env']} no arquivo .env")
        # Tempo limite por chamada (26/10): sem ele, um provedor travado prendia a interface por até
        # 10 min (padrão do cliente). Não muda prompt nem parâmetros de geração.
        return OpenAI(base_url=cfg["base_url"], api_key=chave, timeout=120, max_retries=2)

    def _contexto_inicial(self) -> list:
        return [{"role": "system", "content": montar_system_prompt()}]

    def trocar_modelo(self, alvo: str) -> str:
        provedor, _, modelo = alvo.partition(":")
        if provedor not in PROVEDORES:
            # só o nome do modelo: mantém o provedor atual
            provedor, modelo = self.provedor, alvo
        modelo = modelo or PROVEDORES[provedor]["modelo_padrao"]
        if not modelo:
            return f"Defina o modelo, por exemplo /model {provedor}:<nome-do-modelo>"
        self.cliente = self._criar_cliente(provedor)
        self.provedor, self.modelo = provedor, modelo
        return f"Modelo ativo: {self.provedor}:{self.modelo}"

    def limpar(self):
        self.mensagens = self._contexto_inicial()
        self.tokens_contexto = 0

    @property
    def rotulo(self) -> str:
        return f"{self.provedor}:{self.modelo}"

    # ---------- registro ----------
    def _avisar(self, evento: dict):
        """Repassa cada passo do loop para quem estiver ouvindo (a interface web, por exemplo)."""
        if self.ouvinte:
            try:
                self.ouvinte(evento)
            except Exception:
                pass  # a interface nunca derruba o agente

    def _registrar(self, evento: dict):
        evento = {"quando": datetime.now().isoformat(timespec="seconds"), "modelo": self.rotulo, **evento}
        with open(self.arquivo_log, "a", encoding="utf-8") as f:
            f.write(json.dumps(evento, ensure_ascii=False) + "\n")

    # ---------- chamada ao LLM ----------
    def _chamar_llm(self, com_tools: bool = True):
        inicio = time.time()
        extra = {"tools": DEFINICOES} if com_tools else {}
        resposta = self.cliente.chat.completions.create(
            model=self.modelo, messages=self.mensagens, temperature=0, **extra)
        self.chamadas_sessao += 1
        uso = resposta.usage
        if uso:
            self.tokens_contexto = uso.prompt_tokens
        self.ultimo_log = resposta.model_dump()
        self._registrar({"tipo": "chamada_llm", "segundos": round(time.time() - inicio, 2),
                         "tokens_entrada": getattr(uso, "prompt_tokens", None),
                         "tokens_saida": getattr(uso, "completion_tokens", None),
                         "saida": resposta.choices[0].message.model_dump()})
        return resposta.choices[0].message

    @staticmethod
    def _tool_call_para_historico(c) -> dict:
        """Tool call no formato do histórico. O Gemini exige que a assinatura do raciocínio
        (extra_content.google.thought_signature) volte junto; sem ela, a chamada seguinte dá erro 400."""
        item = {"id": c.id, "type": "function",
                "function": {"name": c.function.name, "arguments": c.function.arguments}}
        extra = getattr(c, "extra_content", None) or (getattr(c, "model_extra", None) or {}).get("extra_content")
        if extra:
            item["extra_content"] = extra
        return item

    @staticmethod
    def _sem_raciocinio(texto: str) -> str:
        return re.sub(r"<think>.*?</think>", "", texto or "", flags=re.S).strip()

    # ---------- um turno ----------
    def responder(self, pergunta: str) -> tuple[str, int]:
        """Roda o loop agêntico até a resposta final. Devolve (resposta, chamadas no turno).

        Se a chamada falhar no meio (limite de requisições, rede), o histórico volta ao
        estado de antes da pergunta: restos de um turno sem resposta contaminam o próximo.
        """
        tamanho_antes = len(self.mensagens)
        try:
            return self._responder(pergunta)
        except Exception as e:
            del self.mensagens[tamanho_antes:]
            self._registrar({"tipo": "erro", "erro": f"{type(e).__name__}: {str(e)[:300]}",
                             "historico_desfeito": True})
            raise

    def _responder(self, pergunta: str) -> tuple[str, int]:
        self.ferramentas.novo_turno()
        self.mensagens.append({"role": "user", "content": pergunta})
        self._registrar({"tipo": "pergunta", "texto": pergunta})
        n_tools = 0
        for ciclo in range(1, MAX_CICLOS + 1):
            # Trava do harness: esgotado o orçamento de tools, o modelo tem de responder com o que leu
            esgotou = n_tools >= MAX_TOOLS
            if esgotou:
                self.mensagens.append({"role": "user", "content": (
                    "Limite de buscas atingido. Responda agora só com o que você já leu, no formato pedido. "
                    'Se não encontrou, escreva "Não consta no material aberto."')})
                self._registrar({"tipo": "trava", "motivo": f"{n_tools} chamadas de tool"})
                self._avisar({"tipo": "trava", "n_tools": n_tools})
            self._avisar({"tipo": "pensando", "ciclo": ciclo})
            msg = self._chamar_llm(com_tools=not esgotou)
            if esgotou or not msg.tool_calls:
                texto = self._sem_raciocinio(msg.content)
                self.mensagens.append({"role": "assistant", "content": texto})
                return texto, ciclo
            self.mensagens.append({
                "role": "assistant", "content": msg.content or "",
                "tool_calls": [self._tool_call_para_historico(c) for c in msg.tool_calls]})
            for c in msg.tool_calls:
                # Listar artigos e carregar Skill são baratos: só busca e leitura gastam o orçamento
                if c.function.name in ("buscar_trechos", "ler_pagina"):
                    n_tools += 1
                print(f"  → {c.function.name}({c.function.arguments})")
                try:
                    args_tool = json.loads(c.function.arguments or "{}")
                except json.JSONDecodeError:
                    args_tool = {}
                self._avisar({"tipo": "tool", "nome": c.function.name, "argumentos": args_tool})
                saida = self.ferramentas.executar(c.function.name, c.function.arguments)
                self._registrar({"tipo": "tool", "nome": c.function.name,
                                 "argumentos": c.function.arguments, "saida": saida[:2000]})
                self.mensagens.append({"role": "tool", "tool_call_id": c.id, "content": saida})
        aviso = f"Limite de {MAX_CICLOS} ciclos atingido sem resposta final."
        self.mensagens.append({"role": "assistant", "content": aviso})
        return aviso, MAX_CICLOS

    # ---------- turno com verificação e gate humano ----------
    def turno_com_revisao(self, pergunta: str):
        texto_pergunta = pergunta
        while True:
            resposta, chamadas = self.responder(texto_pergunta)
            print(f"\n{resposta}\n")
            print(f"[{chamadas} chamada(s) ao LLM neste turno · {self.chamadas_sessao} na sessão]")
            itens = verificador.verificar(resposta, self.ferramentas.evidencias)
            self._registrar({"tipo": "verificacao", "resumo": verificador.resumo(itens), "itens": itens,
                             "chamadas_turno": chamadas})
            if not itens:
                return
            hitl.mostrar_verificacao(itens)
            decisao, comentario = hitl.pedir_decisao()
            self._registrar({"tipo": "decisao_humana", "decisao": decisao, "comentario": comentario})
            if decisao == "aprovar":
                arquivo = hitl.gravar_fichamento(pergunta, resposta, itens, self.rotulo, comentario)
                print(f"Gravado em {arquivo}")
                return
            if decisao == "rejeitar":
                print("Descartado. A decisão ficou no log.")
                return
            texto_pergunta = f"Revise a resposta anterior. Correção pedida pela pessoa: {comentario}"
