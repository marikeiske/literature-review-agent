"""O caso da sala (Aula 11, data.zip; Aula 12, slides 33–34), rodado nos modelos deste agente.

Cada linha de test.jsonl traz o trecho da norma na própria mensagem, a pergunta e a resposta-alvo:
citar o parágrafo, ou "not in the material." Aqui não há busca: mede-se só se o modelo cita um
parágrafo que está na mensagem ou recusa quando o trecho não sustenta, no modelo base (sem LoRA).

Grader de código (slides 33 e 34):
  passa                 recusa esperada e a resposta é exatamente "not in the material."; ou
                        citação esperada e todo parágrafo citado está no trecho da mensagem
  ao juiz               recusa esperada, mas com outras palavras: o código não reconhece a string
                        e a frase vai para um juiz (a autora, na aba Revisar, ou um modelo calibrado)
  falha: fora do trecho citou um parágrafo que não está na mensagem (o "4.4" do slide 33)
  falha: sem parágrafo  respondeu sem apontar parágrafo
  falha: recusou        recusou uma pergunta que o trecho sustenta
  falha: não recusou    respondeu (com ou sem citação) quando o certo era recusar

O código não julga se a frase diz o que o trecho diz (critério "sustentado"): isso é de quem revisa.

O conjunto de dados é material da disciplina e NÃO vai para o repositório: coloque os três
arquivos em dados/aula11/ (pasta fora do git) ou passe o caminho com --arquivo.

Uso:
  python -m experimentos.aula11_norma groq
  python -m experimentos.aula11_norma ollama:gemma4:31b-cloud --repeticoes 5
Saída: resultados/aula11_<modelo>.csv e um resumo no terminal (pass^k quando há repetições).
"""
import argparse
import csv
import json
import re
import sys
import time
from pathlib import Path

from agente.config import PASTA_DADOS, PROVEDORES, RAIZ

ARQUIVO_PADRAO = PASTA_DADOS / "aula11" / "test.jsonl"
RECUSA_EXATA = "not in the material"
ROTULO = re.compile(r"^(?:Paragraph|Table)\s+([0-9IVX]+(?:\.[0-9a-z]+)*)\s*:", re.M)
# "paragraph 3.2.28", "para. 5.3.a", "§ 4.4", "Table II"
CITADO = re.compile(r"(?:paragraph|para\.?|§|section)\s*([0-9]+(?:\.[0-9a-z]+)*)|\btable\s+([IVX]+|\d+)\b", re.I)
# Número de seção solto ("3.2.28"), usado só quando a resposta não nomeia parágrafo nem tabela,
# para um decimal da frase ("0.5") não virar citação
SOLTO = re.compile(r"(?<![\w.$])(\d+\.\d+(?:\.[0-9a-z]+)*)(?![\w])")
CAMPOS = ["linha", "tentativa", "esperado", "veredito", "passa", "no_trecho", "citados", "pergunta", "resposta", "segundos"]


def _normalizar(ident: str) -> str:
    return ident.strip().rstrip(".").lower()


def no_trecho(mensagem: str) -> set[str]:
    return {_normalizar(i) for i in ROTULO.findall(mensagem)}


def _aparece(ident: str, mensagem: str) -> bool:
    return re.search(rf"(?<![\w.]){re.escape(ident)}(?![\w])", mensagem.split("Question:")[0], re.I) is not None


def citados(resposta: str) -> set[str]:
    explicitos = {_normalizar(next(g for g in m if g)) for m in CITADO.findall(resposta)}
    return explicitos or {_normalizar(n) for n in SOLTO.findall(resposta)}


def e_recusa_exata(resposta: str) -> bool:
    return _normalizar(resposta.strip().strip('"').strip()) == RECUSA_EXATA


def grader_codigo(mensagem: str, alvo: str, resposta: str) -> str:
    recusa_esperada = e_recusa_exata(alvo)
    cit, trecho = citados(resposta), no_trecho(mensagem)
    menciona_recusa = RECUSA_EXATA in resposta.lower()
    if recusa_esperada:
        if e_recusa_exata(resposta):
            return "passa"
        if menciona_recusa and not cit:
            return "ao juiz"
        return "falha: não recusou"
    if e_recusa_exata(resposta) or (menciona_recusa and not cit):
        return "falha: recusou"
    if not cit:
        return "falha: sem parágrafo"
    # Um número citado vale se é o rótulo do trecho ("Paragraph 4.1:") ou aparece no próprio texto do
    # trecho ("Section 4", "Table III"): é o "4.4 está na saída?" do slide 33.
    if any(c not in trecho and not _aparece(c, mensagem) for c in cit):
        return "falha: fora do trecho"
    return "passa"


def _cliente(alvo: str):
    from agente.harness import Agente
    provedor, _, modelo = alvo.partition(":")
    if provedor not in PROVEDORES:
        sys.exit(f"Provedor desconhecido: {provedor}. Use um de: {', '.join(PROVEDORES)}")
    return Agente._criar_cliente(provedor), provedor, modelo or PROVEDORES[provedor]["modelo_padrao"]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("modelo", help="ex.: groq, gemini, ollama:gemma4:31b-cloud")
    ap.add_argument("--arquivo", type=Path, default=ARQUIVO_PADRAO)
    ap.add_argument("--repeticoes", type=int, default=1, help="tentativas por linha (pass^k)")
    args = ap.parse_args()
    if not args.arquivo.exists():
        sys.exit(f"Não achei {args.arquivo}. Descompacte o data.zip da Aula 11 em dados/aula11/.")
    linhas = [json.loads(l) for l in args.arquivo.read_text(encoding="utf-8").splitlines() if l.strip()]
    cliente, provedor, modelo = _cliente(args.modelo)
    nome = re.sub(r"[^a-zA-Z0-9.-]+", "_", f"{provedor}_{modelo}")
    saida = RAIZ / "resultados" / f"aula11_{nome}.csv"
    feitas = set()
    if saida.exists():
        with open(saida, encoding="utf-8-sig") as f:
            feitas = {(int(l["linha"]), int(l["tentativa"])) for l in csv.DictReader(f, delimiter=";")}
    novo = not saida.exists()
    with open(saida, "a", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=CAMPOS, delimiter=";")
        if novo:
            w.writeheader()
        for t in range(1, args.repeticoes + 1):
            for i, ex in enumerate(linhas):
                if (i, t) in feitas:
                    continue
                msgs = [m for m in ex["messages"] if m["role"] != "assistant"]
                alvo = next(m["content"] for m in ex["messages"] if m["role"] == "assistant")
                usuario = next(m["content"] for m in msgs if m["role"] == "user")
                inicio = time.time()
                try:
                    r = cliente.chat.completions.create(model=modelo, messages=msgs, temperature=0)
                except Exception as e:  # cota, rede: para e deixa continuar depois
                    print(f"Parou na linha {i}, tentativa {t}: {type(e).__name__}: {str(e)[:120]}")
                    print("Rode o mesmo comando de novo para continuar.")
                    return
                resposta = re.sub(r"<think>.*?</think>", "", r.choices[0].message.content or "", flags=re.S).strip()
                v = grader_codigo(usuario, alvo, resposta)
                w.writerow({"linha": i, "tentativa": t, "esperado": "recusa" if e_recusa_exata(alvo) else "citação",
                            "veredito": v, "passa": int(v == "passa"), "no_trecho": " ".join(sorted(no_trecho(usuario))),
                            "citados": " ".join(sorted(citados(resposta))),
                            "pergunta": usuario.split("Question:")[-1].strip(), "resposta": resposta.replace("\n", " ")[:600],
                            "segundos": round(time.time() - inicio, 1)})
                f.flush()
                print(f"[t{t}] linha {i:>2} {v}")
    print("\n" + resumo(saida))


def resumo(arquivo: Path) -> str:
    from collections import Counter, defaultdict

    import resumo_avaliacao as ra
    with open(arquivo, encoding="utf-8-sig") as f:
        linhas = list(csv.DictReader(f, delimiter=";"))
    por_linha = defaultdict(list)
    for l in sorted(linhas, key=lambda l: (int(l["linha"]), int(l["tentativa"]))):
        por_linha[(l["esperado"], l["linha"])].append(int(l["passa"]))
    k = min((len(v) for v in por_linha.values()), default=0)
    partes = []
    for esp in ("citação", "recusa"):
        sub = {i: v for (e, i), v in por_linha.items() if e == esp}
        n, todas, _ = ra.pass_k(sub, k)
        partes.append(f"{esp}: pass^{k} {ra.pct(todas, n)}")
    vered = Counter(l["veredito"] for l in linhas)
    return (f"{arquivo.stem.removeprefix('aula11_')} · {len(por_linha)} linhas, {k} tentativa(s) · " + " · ".join(partes)
            + " · vereditos: " + ", ".join(f"{v} {c}" for v, c in vered.most_common()))


if __name__ == "__main__":
    main()
