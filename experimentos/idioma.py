"""Experimento: a língua da pergunta muda a qualidade da resposta?

Mesmas 4 perguntas em três versões: português, português com o termo técnico
em inglês entre parênteses, e inglês. Para cada resposta mede:
  - pagina_ok:   alguma citação aponta para uma página esperada
  - numero_ok:   o número esperado aparece na resposta (quando há número)
  - sem_invencao: nenhuma citação de página não lida e nenhum número inventado
  - consultas:   as palavras que o agente usou na busca (mostra se traduziu)

Uso:  python -m experimentos.idioma groq
Saída: resultados/idioma_<modelo>_<data>.csv
"""
import csv
import re
import sys
import time
from datetime import datetime

from agente import verificador
from agente.config import RAIZ
from agente.harness import Agente

PERGUNTAS = [
    {"id": "Q1", "artigo": "Nimbekar2023", "paginas": {7}, "numeros": {"3.6", "5"},
     "pt": "Quanto de potência a arquitetura de Nimbekar consome na FPGA?",
     "pt_termo": "Quanto de potência (power consumption) a arquitetura de Nimbekar consome na FPGA?",
     "en": "How much power does Nimbekar's architecture consume on the FPGA?"},
    {"id": "Q2", "artigo": "Leppanen2023", "paginas": {1, 8, 10}, "numeros": {"246", "250"},
     "pt": "Quanto de sobrecarga a sincronização dentro do chip elimina no trabalho de Leppänen?",
     "pt_termo": "Quanto de sobrecarga (overhead) a sincronização dentro do chip (on-chip synchronization) elimina no trabalho de Leppänen?",
     "en": "How much overhead does on-chip synchronization remove in Leppänen's work?"},
    {"id": "Q3", "artigo": "Lozano2023", "paginas": {2}, "numeros": set(),
     "pt": "Em quantos grupos Cinque et al. classificaram os hypervisors de sistemas de criticidade mista, segundo Lozano?",
     "pt_termo": "Em quantos grupos Cinque et al. classificaram os hypervisors de sistemas de criticidade mista (mixed-criticality), segundo Lozano?",
     "en": "Into how many groups did Cinque et al. classify hypervisors for mixed-criticality systems, according to Lozano?",
     "palavra": r"\b(quatro|four|4)\b"},
    {"id": "Q4", "artigo": "YoungS2023", "paginas": {1, 2}, "numeros": set(), "armadilha": True,
     "pt": "Qual foi o speedup numérico obtido pelos programas OpenMP de Young-S.?",
     "pt_termo": "Qual foi o speedup numérico (speedup factor) obtido pelos programas OpenMP de Young-S.?",
     "en": "What numerical speedup did Young-S.'s OpenMP programs achieve?"},
]
VARIANTES = ["pt", "pt_termo", "en"]


def numeros(texto):
    sem_cit = verificador.CITACAO.sub("", texto)
    return {n.replace(",", ".") for n in verificador.NUMERO.findall(sem_cit)}


def avaliar(p, resposta, evidencias, itens):
    citadas = {(a, pg) for it in itens for a, pg in it["citacoes"]}
    pagina_ok = any(a == p["artigo"] and pg in p["paginas"] for a, pg in citadas)
    nums = numeros(resposta)
    if p.get("armadilha"):
        # Young-S. não traz número de speedup: qualquer fator "Nx" ou porcentagem é invenção
        inventou = bool(re.search(r"\d+(?:[.,]\d+)?\s*(?:x|×|vezes|%)", resposta, re.I))
        numero_ok = not inventou
    elif p["numeros"]:
        numero_ok = bool(p["numeros"] & nums)
    else:
        numero_ok = bool(re.search(p.get("palavra", r"$^"), resposta, re.I))
    sem_invencao = not any(it["veredito"] in ("página não lida", "número ausente") for it in itens)
    return pagina_ok, numero_ok, sem_invencao


def main():
    alvo = sys.argv[1] if len(sys.argv) > 1 else "groq"
    agente = Agente()
    print(agente.trocar_modelo(alvo))
    pasta = RAIZ / "resultados"
    pasta.mkdir(exist_ok=True)
    nome = re.sub(r"[^a-zA-Z0-9.-]+", "_", agente.rotulo)
    arquivo = pasta / f"idioma_{nome}_{datetime.now():%Y-%m-%d_%H%M}.csv"
    linhas = []
    for p in PERGUNTAS:
        for v in VARIANTES:
            agente.limpar()
            inicio = time.time()
            try:
                resposta, chamadas = agente.responder(p[v])
            except Exception as e:  # limite de requisições, rede etc.
                resposta, chamadas = f"ERRO: {type(e).__name__}: {e}", 0
            consultas = [json_args for json_args in _consultas(agente)]
            itens = verificador.verificar(resposta, agente.ferramentas.evidencias)
            pag, num, limpo = avaliar(p, resposta, agente.ferramentas.evidencias, itens)
            linha = {"pergunta": p["id"], "variante": v, "pagina_ok": int(pag), "numero_ok": int(num),
                     "sem_invencao": int(limpo), "chamadas": chamadas,
                     "segundos": round(time.time() - inicio, 1), "consultas": " | ".join(consultas),
                     "resposta": resposta.replace("\n", " ")[:500]}
            linhas.append(linha)
            print(f"{p['id']} {v:<9} página {'OK' if pag else '--'} · número {'OK' if num else '--'} · "
                  f"sem invenção {'OK' if limpo else '--'} · {chamadas} chamadas · busca: {linha['consultas'][:70]}")
    with open(arquivo, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(linhas[0].keys()), delimiter=";")
        w.writeheader()
        w.writerows(linhas)
    print("\nResumo por variante (acertos de página / número / sem invenção, em 4 perguntas):")
    for v in VARIANTES:
        sub = [l for l in linhas if l["variante"] == v]
        print(f"  {v:<9} {sum(l['pagina_ok'] for l in sub)}/4 · {sum(l['numero_ok'] for l in sub)}/4 · "
              f"{sum(l['sem_invencao'] for l in sub)}/4")
    print(f"Resultados: {arquivo}")


def _consultas(agente):
    """Extrai, da última conversa, as consultas que o agente mandou para buscar_trechos."""
    import json
    saida = []
    for m in agente.mensagens:
        for c in m.get("tool_calls", []) if isinstance(m, dict) else []:
            if c["function"]["name"] == "buscar_trechos":
                try:
                    saida.append(json.loads(c["function"]["arguments"]).get("consulta", ""))
                except json.JSONDecodeError:
                    pass
    return saida


if __name__ == "__main__":
    main()
