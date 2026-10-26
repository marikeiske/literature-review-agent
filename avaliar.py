"""Avaliação contra o gabarito: taxa de acerto das citações.

Para cada afirmação do gabarito, o agente recebe a afirmação e precisa localizar
a página do PDF que a sustenta. A página certa está no gabarito, então a
conferência é automática.

Condições (as do desenho do artigo):
  rag       o agente busca com as tools (RAG agentic), como no uso normal
  contexto  sem tools: o artigo inteiro vai no prompt, com marcadores de página
            (testa contexto longo e "lost in the middle", Liu et al. 2023)

Métricas por afirmação:
  acerto_exato      alguma página citada está entre as páginas do gabarito
  acerto_vizinha    acerto com tolerância de ±1 página
  recusa            respondeu "não consta"
  grounding_falso   citou página que não leu (só na condição rag)
  numero_ausente    escreveu número que não está na página citada

Uso:
  python avaliar.py groq                          todas as 109 afirmações, condição rag
  python avaliar.py groq --condicao contexto
  python avaliar.py openrouter --limite 20        só as 20 primeiras (cota de 50/dia)
  python avaliar.py groq --artigos Nimbekar2023 Mzid2024
  python avaliar.py groq --por-artigo 3           piloto: 3 afirmações de cada artigo
  python avaliar.py groq --negativas              perguntas cuja resposta certa é recusar
  python avaliar.py groq --so-resumo              refaz o resumo com o gabarito revisado, sem gastar cota

Se a cota acabar no meio, rode o mesmo comando de novo: ele continua de onde parou.
Duas execuções não gravam o mesmo CSV ao mesmo tempo: a segunda para com um aviso.
Saída: resultados/aval_<modelo>_<condicao>.csv e um resumo no terminal.
"""
import argparse
import contextlib
import csv
import hashlib
import json
import os
import subprocess
import re
import sys
import time
from collections import defaultdict
from pathlib import Path

from openai import APIStatusError, RateLimitError

import revisao
from agente import verificador
from agente.config import MAX_CICLOS, MAX_TOOLS, RAIZ, TOP_K
from agente.harness import Agente


PERGUNTA = ('Afirmação sobre o artigo {art}: "{texto}"\n'
            "Localize no artigo a página (física do PDF) que sustenta essa afirmação. "
            "Responda com UMA linha no formato: - <a afirmação, resumida> [{art} p.N]. "
            'Se o artigo não sustenta a afirmação, escreva: "Não consta no material aberto."')

CAMPOS = ["id", "artigo", "tipo", "posicao", "paginas_gabarito", "paginas_citadas", "acerto_exato",
          "acerto_vizinha", "recusa", "grounding_falso", "numero_ausente", "chamadas", "segundos",
          "status_gabarito", "resposta"]


def carregar_gabarito(artigos=None):
    """Afirmações do gabarito com a revisão humana aplicada (revisao.py, tela Revisar).

    "Rejeitar" sai da avaliação. Em "Corrigir", se a correção traz uma página, ela passa a valer.
    Sem decisão na interface, vale a coluna Status da planilha."""
    revs = revisao.ler_revisoes(revisao.ARQ_REV_GABARITO)
    itens = []
    for g in revisao.ler_gabarito():
        rev = revs.get(g["id"], {})
        status = rev.get("status") or g["status_planilha"]
        if status == "Rejeitar":
            continue
        if artigos and g["artigo"] not in artigos:
            continue
        paginas = set(g["paginas"])
        if status == "Corrigir":
            paginas = set(revisao.paginas_corrigidas(rev.get("comentario") or g["comentario_planilha"])) or paginas
        itens.append({"id": g["id"], "artigo": g["artigo"], "tipo": g["tipo"], "posicao": g["posicao"],
                      "texto": g["texto"], "paginas": paginas, "status": status or "sem revisão"})
    return itens


def _sha256(dados: bytes) -> str:
    return hashlib.sha256(dados).hexdigest()[:16]


def registrar_execucao(agente: Agente, tipo: str, condicao: str, arquivo: Path):
    """Uma linha em resultados/execucoes.jsonl por rodada: com que código, prompt e gabarito ela rodou.

    Prova, rodada a rodada, que o system prompt não mudou (hash igual) e de qual commit veio o
    resultado. O provedor pode trocar o modelo por trás do mesmo nome: a data fica registrada."""
    def git(*args):
        try:
            return subprocess.run(["git", *args], cwd=RAIZ, capture_output=True, text=True, timeout=10).stdout.strip()
        except (OSError, subprocess.SubprocessError):
            return ""
    from agente.harness import montar_system_prompt
    import openai
    gab = revisao.ARQ_REV_GABARITO
    linha = {
        "quando": time.strftime("%Y-%m-%dT%H:%M:%S"), "tipo": tipo, "condicao": condicao,
        "modelo": agente.rotulo, "arquivo": arquivo.name,
        "commit": git("rev-parse", "--short", "HEAD"), "codigo_alterado": bool(git("status", "--porcelain", "--", "agente", "avaliar.py")),
        "sha_system_prompt": _sha256(montar_system_prompt().encode("utf-8")),
        "sha_revisao_gabarito": _sha256(gab.read_bytes()) if gab.exists() else "",
        "python": sys.version.split()[0], "openai": openai.__version__,
        "temperatura": 0, "max_ciclos": MAX_CICLOS, "max_tools": MAX_TOOLS, "top_k": TOP_K,
    }
    with open(RAIZ / "resultados" / "execucoes.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(linha, ensure_ascii=False) + "\n")


@contextlib.contextmanager
def execucao_exclusiva(arquivo: Path):
    """Impede duas execuções gravando o mesmo CSV (falha de 19/10: a execução interrompida pela
    queda de conexão continuou rodando junto com a nova e duplicou linhas). A trava do sistema
    operacional some sozinha quando o processo termina, mesmo se ele cair."""
    trava = open(arquivo.with_suffix(".lock"), "a+")
    try:
        if os.name == "nt":
            import msvcrt
            trava.seek(0)
            msvcrt.locking(trava.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(trava, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        trava.close()
        sys.exit(f"Outra execução já está gravando {arquivo.name}. Espere ela terminar ou feche o terminal dela.")
    try:
        yield
    finally:
        trava.close()


def ler_feitas(arquivo: Path) -> dict:
    """Linhas já avaliadas. Se um id aparecer repetido, vale a primeira execução."""
    feitas = {}
    if arquivo.exists():
        with open(arquivo, encoding="utf-8-sig") as f:
            for linha in csv.DictReader(f, delimiter=";"):
                feitas.setdefault(linha["id"], linha)
    return feitas


# ---------- condição "contexto": artigo inteiro no prompt, sem tools ----------
def responder_contexto(agente: Agente, item: dict) -> tuple[str, int, dict]:
    paginas = sorted((p for (a, p) in agente.ferramentas.paginas if a == item["artigo"]))
    corpo = "\n\n".join(f"<<<PÁGINA {p}>>>\n{agente.ferramentas.paginas[(item['artigo'], p)]}" for p in paginas)
    sistema = ("Você localiza a página que sustenta uma afirmação num artigo. Cite no formato [Id p.N], "
               "usando os marcadores <<<PÁGINA N>>>. Se o artigo não sustenta a afirmação, escreva "
               '"Não consta no material aberto." Responda em português.')
    msgs = [{"role": "system", "content": sistema},
            {"role": "user", "content": f"ARTIGO {item['artigo']}:\n\n{corpo}\n\n"
                                        + PERGUNTA.format(art=item["artigo"], texto=item["texto"])}]
    r = agente.cliente.chat.completions.create(model=agente.modelo, messages=msgs, temperature=0)
    agente.tokens_contexto = getattr(r.usage, "prompt_tokens", 0)
    texto = agente._sem_raciocinio(r.choices[0].message.content)
    agente._registrar({"tipo": "chamada_llm", "condicao": "contexto", "afirmacao": item["id"],
                       "tokens_entrada": agente.tokens_contexto, "saida": texto})
    evidencias ={(item["artigo"], p): agente.ferramentas.paginas[(item["artigo"], p)] for p in paginas}
    return texto, 1, evidencias


def responder_rag(agente: Agente, item: dict) -> tuple[str, int, dict]:
    agente.limpar()
    texto, chamadas = agente.responder(PERGUNTA.format(art=item["artigo"], texto=item["texto"]))
    return texto, chamadas, dict(agente.ferramentas.evidencias)


def com_retentativa(funcao, *args, tentativas=4):
    espera = 20
    for t in range(tentativas):
        try:
            return funcao(*args)
        except RateLimitError as e:
            # "Request too large": o pedido passa do limite de tokens do plano gratuito.
            # Esperar não resolve (o pedido continua grande), então pula na hora (achado em 26/10, Qwen no Groq).
            if t == tentativas - 1 or "too large" in str(e).lower():
                raise
            print(f"   limite de requisições (429); esperando {espera}s... ({str(e)[:90]})")
            time.sleep(espera)
            espera *= 2


def pontuar(item, resposta, evidencias):
    itens = verificador.verificar(resposta, evidencias)
    citadas = sorted({p for it in itens for a, p in it["citacoes"] if a == item["artigo"]})
    exato = any(p in item["paginas"] for p in citadas)
    vizinha = any(abs(p - g) <= 1 for p in citadas for g in item["paginas"])
    vereditos = {it["veredito"] for it in itens}
    return {"paginas_citadas": " ".join(map(str, citadas)), "acerto_exato": int(exato),
            "acerto_vizinha": int(vizinha),
            "recusa": int(bool(vereditos & {"recusa", "recusa sem página lida"}) and not citadas),
            "grounding_falso": int("página não lida" in vereditos),
            "numero_ausente": int("número ausente" in vereditos)}


def repontuar(linha: dict, item: dict) -> dict:
    """Recalcula o acerto com o gabarito de hoje: a revisão humana pode ter corrigido a página
    depois que a afirmação foi avaliada. O que o modelo citou não muda; só a régua."""
    citadas = [int(p) for p in str(linha.get("paginas_citadas") or "").split()]
    l = dict(linha)
    l["paginas_gabarito"] = " ".join(map(str, sorted(item["paginas"])))
    l["acerto_exato"] = int(any(p in item["paginas"] for p in citadas))
    l["acerto_vizinha"] = int(any(abs(p - g) <= 1 for p in citadas for g in item["paginas"]))
    l["status_gabarito"] = item["status"]
    return l


def resumir(linhas: list[dict], titulo: str):
    def taxa(sub, campo):
        return f"{sum(int(l[campo]) for l in sub)}/{len(sub)} ({100 * sum(int(l[campo]) for l in sub) / len(sub):.0f}%)" if sub else "-"
    print(f"\n===== {titulo} · {len(linhas)} afirmações =====")
    print(f"Acerto exato da página:      {taxa(linhas, 'acerto_exato')}")
    print(f"Acerto com ±1 página:        {taxa(linhas, 'acerto_vizinha')}")
    print(f"Recusas:                     {taxa(linhas, 'recusa')}")
    print(f"Grounding falso:             {taxa(linhas, 'grounding_falso')}")
    print(f"Número ausente na página:    {taxa(linhas, 'numero_ausente')}")
    total_ch = sum(int(l["chamadas"]) for l in linhas)
    print(f"Chamadas ao LLM: {total_ch} (média {total_ch / max(len(linhas), 1):.1f} por afirmação)")
    for campo in ("posicao", "artigo"):
        grupos = defaultdict(list)
        for l in linhas:
            grupos[l[campo]].append(l)
        print(f"Acerto exato por {campo}: " + " · ".join(f"{k} {taxa(v, 'acerto_exato')}" for k, v in sorted(grupos.items())))
    nao_revisadas = sum(1 for l in linhas if l["status_gabarito"] == "sem revisão")
    if nao_revisadas:
        print(f"ATENÇÃO: {nao_revisadas} afirmações do gabarito ainda não foram revisadas por você (HITL).")


# ---------- perguntas negativas: o certo é recusar ou corrigir a premissa ----------
CAMPOS_NEG = ["id", "tipo", "modo", "acerto", "recusou", "corrigiu", "inventou", "recusa_sem_ler",
              "falha_verificador", "chamadas", "segundos", "pergunta", "resposta"]


def pontuar_negativa(neg: dict, resposta: str, evidencias: dict) -> dict:
    itens = verificador.verificar(resposta, evidencias)
    vereditos = {it["veredito"] for it in itens}
    recusou = bool(verificador.RECUSA.search(resposta) or verificador.PREMISSA.search(resposta))
    corrigiu = bool(neg["correcao"] and re.search(neg["correcao"], resposta, re.I))
    sem_citacao = verificador.CITACAO.sub("", resposta)
    falha_verif = bool(vereditos & {"página não lida", "número ausente"})
    inventou = falha_verif or bool(neg["invencao"] and re.search(neg["invencao"], sem_citacao, re.I))
    if neg["modo"] == "recusar":
        acerto = recusou and not inventou
    else:
        acerto = (recusou or corrigiu) and not inventou
    return {"acerto": int(acerto), "recusou": int(recusou), "corrigiu": int(corrigiu), "inventou": int(inventou),
            "recusa_sem_ler": int("recusa sem página lida" in vereditos), "falha_verificador": int(falha_verif)}


def avaliar_negativas(agente: Agente, nome: str, limite: int | None):
    from negativas import NEGATIVAS
    arquivo = RAIZ / "resultados" / f"neg_{nome}.csv"
    feitas = ler_feitas(arquivo)
    if feitas:
        print(f"Continuando: {len(feitas)} perguntas já avaliadas em {arquivo.name}")
    pendentes = [n for n in NEGATIVAS if n["id"] not in feitas][:limite]
    novo = not arquivo.exists()
    with open(arquivo, "a", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=CAMPOS_NEG, delimiter=";")
        if novo:
            w.writeheader()
        for k, neg in enumerate(pendentes, 1):
            inicio = time.time()
            agente.limpar()
            try:
                resposta, chamadas = com_retentativa(agente.responder, neg["pergunta"])
            except RateLimitError as e:
                if "too large" in str(e).lower():
                    print(f"{neg['id']}: pedido grande demais para o limite do plano gratuito; pulando.")
                    continue
                print("Cota esgotada. Rode o mesmo comando mais tarde para continuar.")
                break
            except APIStatusError as e:
                print(f"{neg['id']}: erro do provedor ({e.status_code}); pulando.")
                continue
            linha = {"id": neg["id"], "tipo": neg["tipo"], "modo": neg["modo"], "chamadas": chamadas,
                     "segundos": round(time.time() - inicio, 1), "pergunta": neg["pergunta"],
                     "resposta": resposta.replace("\n", " ")[:2000],
                     **pontuar_negativa(neg, resposta, dict(agente.ferramentas.evidencias))}
            w.writerow(linha)
            f.flush()
            feitas[neg["id"]] = linha
            print(f"[{k}/{len(pendentes)}] {neg['id']} {neg['tipo']:<16} {'ACERTO' if linha['acerto'] else 'erro'}"
                  f"{' · recusou' if linha['recusou'] else ''}{' · corrigiu' if linha['corrigiu'] else ''}"
                  f"{' · INVENTOU' if linha['inventou'] else ''}{' · recusou sem ler' if linha['recusa_sem_ler'] else ''}")

    linhas = list(feitas.values())
    if not linhas:
        return
    def taxa(sub, campo):
        n = sum(int(l[campo]) for l in sub)
        return f"{n}/{len(sub)} ({100 * n / len(sub):.0f}%)"
    print(f"\n===== {agente.rotulo} · perguntas negativas · {len(linhas)} perguntas =====")
    print(f"Acerto (recusou ou corrigiu, sem inventar): {taxa(linhas, 'acerto')}")
    print(f"Inventou dado ou citou página não lida:     {taxa(linhas, 'inventou')}")
    print(f"Recusou sem ler nenhuma página:             {taxa(linhas, 'recusa_sem_ler')}")
    grupos = defaultdict(list)
    for l in linhas:
        grupos[l["tipo"]].append(l)
    print("Acerto por tipo: " + " · ".join(f"{t} {taxa(v, 'acerto')}" for t, v in sorted(grupos.items())))
    # Revisão humana da rodada (tela Revisar): o automático é necessário, não suficiente
    revs = revisao.ler_revisoes(arquivo.parent / f"revisao_{arquivo.stem}.csv")
    marcadas = [revs[l["id"]]["status"] for l in linhas if revs.get(l["id"], {}).get("status")]
    if marcadas:
        cont = " · ".join(f"{o} {marcadas.count(o)}" for o in revisao.OPCOES["negativas"])
        print(f"Revisão humana: {len(marcadas)}/{len(linhas)} revisadas · {cont}")
    else:
        print("Revisão humana: nenhuma ainda. Abra a interface (python app.py), aba Revisar.")
    print(f"Resultados: {arquivo}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("modelo", help="ex.: groq, openrouter, ollama:qwen2.5:1.5b")
    ap.add_argument("--condicao", choices=["rag", "contexto"], default="rag")
    ap.add_argument("--limite", type=int, default=None, help="avaliar no máximo N afirmações novas")
    ap.add_argument("--artigos", nargs="*", default=None)
    ap.add_argument("--por-artigo", type=int, default=None, help="no máximo K afirmações de cada artigo")
    ap.add_argument("--so-resumo", action="store_true",
                    help="não chama o modelo: só refaz o resumo com o gabarito revisado de hoje")
    ap.add_argument("--negativas", action="store_true",
                    help="avalia as perguntas negativas (negativas.py) em vez das afirmações do gabarito")
    args = ap.parse_args()

    agente = Agente()
    print(agente.trocar_modelo(args.modelo))
    (RAIZ / "resultados").mkdir(exist_ok=True)
    if args.negativas:
        nome = re.sub(r"[^a-zA-Z0-9.-]+", "_", agente.rotulo)
        with execucao_exclusiva(RAIZ / "resultados" / f"neg_{nome}.csv"):
            registrar_execucao(agente, "negativas", "rag", RAIZ / "resultados" / f"neg_{nome}.csv")
            return avaliar_negativas(agente, nome, args.limite)
    itens = carregar_gabarito(args.artigos)
    # Ordem intercalada: um item de cada documento por vez, alternando início, meio e fim.
    # Como a cota gratuita acaba no meio, o que já rodou em cada dia é uma amostra equilibrada
    # (todos os documentos e posições), e não só os primeiros artigos da planilha.
    grupos = defaultdict(lambda: defaultdict(list))
    for item in itens:
        grupos[item["artigo"]][item["posicao"]].append(item)
    filas = {}
    for art, pos in grupos.items():
        fila = []
        while any(pos.values()):
            for p in ("início", "meio", "fim"):
                if pos[p]:
                    fila.append(pos[p].pop(0))
        filas[art] = fila[: args.por_artigo] if args.por_artigo else fila
    itens = []
    while any(filas.values()):
        for art in list(filas):
            if filas[art]:
                itens.append(filas[art].pop(0))
    nome = re.sub(r"[^a-zA-Z0-9.-]+", "_", agente.rotulo)
    pasta = RAIZ / "resultados"
    pasta.mkdir(exist_ok=True)
    arquivo = pasta / f"aval_{nome}_{args.condicao}.csv"
    with execucao_exclusiva(arquivo):
        if not args.so_resumo:
            registrar_execucao(agente, "afirmacoes", args.condicao, arquivo)
        avaliar_afirmacoes(agente, args, itens, arquivo)


def avaliar_afirmacoes(agente: Agente, args, itens: list[dict], arquivo: Path):
    feitas = ler_feitas(arquivo)
    if feitas:
        print(f"Continuando: {len(feitas)} afirmações já avaliadas em {arquivo.name}")
    pendentes = [] if args.so_resumo else [i for i in itens if i["id"] not in feitas][: args.limite]
    responder = responder_rag if args.condicao == "rag" else responder_contexto

    novo = not arquivo.exists()
    with open(arquivo, "a", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=CAMPOS, delimiter=";")
        if novo:
            w.writeheader()
        for n, item in enumerate(pendentes, 1):
            inicio = time.time()
            try:
                resposta, chamadas, evid = com_retentativa(responder, agente, item)
            except RateLimitError as e:
                if "too large" in str(e).lower():
                    print(f"{item['id']}: pedido grande demais para o limite do plano gratuito; pulando.")
                    continue
                print("Cota esgotada. Rode o mesmo comando mais tarde para continuar.")
                break
            except APIStatusError as e:
                print(f"{item['id']}: erro do provedor ({e.status_code}); pulando. {str(e)[:120]}")
                continue
            linha = {"id": item["id"], "artigo": item["artigo"], "tipo": item["tipo"], "posicao": item["posicao"],
                     "paginas_gabarito": " ".join(map(str, sorted(item["paginas"]))), "chamadas": chamadas,
                     "segundos": round(time.time() - inicio, 1), "status_gabarito": item["status"],
                     "resposta": resposta.replace("\n", " ")[:1000], **pontuar(item, resposta, evid)}
            w.writerow(linha)
            f.flush()
            feitas[item["id"]] = linha
            print(f"[{n}/{len(pendentes)}] {item['id']} {item['artigo']:<13} gabarito p.{linha['paginas_gabarito']:<6} "
                  f"citou p.{linha['paginas_citadas'] or '-':<8} {'ACERTO' if linha['acerto_exato'] else 'erro'}"
                  f"{' · recusa' if linha['recusa'] else ''}{' · grounding falso' if linha['grounding_falso'] else ''}")

    # Rejeitadas na revisão saem; corrigidas são repontuadas com a página nova
    resumir([repontuar(feitas[i["id"]], i) for i in itens if i["id"] in feitas],
            f"{agente.rotulo} · condição {args.condicao}")
    print(f"Resultados: {arquivo}")


if __name__ == "__main__":
    main()
