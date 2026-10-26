"""Recuperação por palavras-chave (BM25), sem custo e sem serviço externo.

É o "recuperador único" do RAG naïve (Aula 5, p. 37), trocando embeddings por
BM25 para não depender de API de embeddings. Limitação conhecida: BM25 compara
palavras, então uma pergunta em português não acha texto em inglês. Por isso o
system prompt manda o agente buscar com termos em inglês.
"""
import math
import re
from collections import Counter

PARADAS = set("""
a an and are as at be by for from has have in is it its of on or that the this to was were which with
we our their they these those can not also than then there such into using used use based between
o os as um uma de da do das dos e em no na nos nas para por com que se ao à é são
""".split())


def tokenizar(texto: str) -> list[str]:
    tokens = re.findall(r"[a-zà-ÿ0-9]+(?:[.,][0-9]+)?", texto.lower())
    return [t for t in tokens if t not in PARADAS and len(t) > 1]


class IndiceBM25:
    def __init__(self, paginas: list[dict], k1: float = 1.5, b: float = 0.75):
        self.docs = []  # cada doc = um trecho com artigo e página
        for p in paginas:
            for j, trecho in enumerate(p["trechos"]):
                self.docs.append({"artigo": p["artigo"], "pagina": p["pagina"],
                                  "trecho_id": f'{p["artigo"]}:p{p["pagina"]}:t{j + 1}',
                                  "texto": trecho, "tokens": tokenizar(trecho)})
        self.k1, self.b = k1, b
        self.n = len(self.docs)
        self.media_len = sum(len(d["tokens"]) for d in self.docs) / max(self.n, 1)
        df = Counter()
        for d in self.docs:
            d["tf"] = Counter(d["tokens"])
            df.update(d["tf"].keys())
        self.idf = {t: math.log(1 + (self.n - f + 0.5) / (f + 0.5)) for t, f in df.items()}

    def buscar(self, consulta: str, k: int = 5, artigo: str | None = None) -> list[dict]:
        termos = tokenizar(consulta)
        resultados = []
        for d in self.docs:
            if artigo and d["artigo"] != artigo:
                continue
            score, L = 0.0, len(d["tokens"])
            for t in termos:
                tf = d["tf"].get(t, 0)
                if tf:
                    score += self.idf[t] * tf * (self.k1 + 1) / (
                        tf + self.k1 * (1 - self.b + self.b * L / self.media_len))
            if score > 0:
                resultados.append((score, d))
        resultados.sort(key=lambda x: -x[0])
        return [{"trecho_id": d["trecho_id"], "artigo": d["artigo"], "pagina": d["pagina"],
                 "score": round(s, 2), "texto": d["texto"]} for s, d in resultados[:k]]
