"""Corpus: 8 artigos da dissertação + 3 documentos de aviônica, extraídos página por página.

Convenção de página: página física do PDF (1 = primeira página do arquivo),
a mesma usada no gabarito. Não é a numeração impressa do periódico.

Recorte (Aula 5, p. 66): cada página é a unidade "larga" (parent) e é dividida
em trechos menores (child) para a busca. A busca acha o trecho; a tool
ler_pagina devolve a página inteira quando o agente precisa de mais contexto.

Uso:  python -m agente.corpus      (gera dados/paginas.json)
"""
import json
import re
import sys
import unicodedata

import pymupdf

from .config import ARQUIVO_PAGINAS, PASTA_CORPUS, PASTA_DADOS, TAMANHO_TRECHO

ARTIGOS = [
    {"id": "Nimbekar2023", "arquivo": "Nimbekar2023.pdf", "ano": 2023,
     "autores": "Nimbekar et al.",
     "titulo": "Reconfigurable VLSI Design Architecture for Deep Learning Established Forelimb and Hindlimb Gesture Recognition for Rehabilitation Application"},
    {"id": "Breyer2022", "arquivo": "Breyer2022.pdf", "ano": 2022,
     "autores": "Breyer, Van Craen, Pflüger",
     "titulo": "A Comparison of SYCL, OpenCL, CUDA, and OpenMP for Massively Parallel Support Vector Machine Classification on Multi-Vendor Hardware"},
    {"id": "Sifakis2015", "arquivo": "Sifakis2015.pdf", "ano": 2015,
     "autores": "Sifakis",
     "titulo": "System Design Automation: Challenges and Limitations"},
    {"id": "Lozano2023", "arquivo": "Lozano2023.pdf", "ano": 2023,
     "autores": "Lozano, Lugo, Carretero",
     "titulo": "A Comprehensive Survey on the Use of Hypervisors in Safety-Critical Systems"},
    {"id": "Mzid2024", "arquivo": "Mzid2024.pdf", "ano": 2024,
     "autores": "Mzid",
     "titulo": "Real-time design patterns for the verification of safety-critical embedded systems in model-based approach"},
    {"id": "YoungS2023", "arquivo": "YoungS2023.pdf", "ano": 2023,
     "autores": "Young-S., Muruganandam, Balaž, Adhikari",
     "titulo": "OpenMP Fortran programs for solving the time-dependent dipolar Gross-Pitaevskii equation"},
    {"id": "Leppanen2023", "arquivo": "Leppanen2023.pdf", "ano": 2023,
     "autores": "Leppänen et al.",
     "titulo": "Efficient OpenCL system integration of non-blocking FPGA accelerators"},
    {"id": "Yoshida2024", "arquivo": "Yoshida2024.pdf", "ano": 2024,
     "autores": "Yoshida, Miwa, Yamaki, Honda",
     "titulo": "Analyzing the impact of CUDA versions on GPU applications"},
    # Documentos explicitamente aeroespaciais (enquadramento: aviônica crítica)
    {"id": "FAA2024", "arquivo": "FAA2024.pdf", "ano": 2024,
     "autores": "Federal Aviation Administration (FAA)",
     "titulo": "Advisory Circular AC 20-193: Use of Multi-Core Processors"},
    {"id": "PeraltaQuesada2023", "arquivo": "PeraltaQuesada2023.pdf", "ano": 2023,
     "autores": "Peralta Quesada, Trompouki, Kosmidis",
     "titulo": "Evaluation of SYCL's Suitability for High-Performance Critical Systems"},
    {"id": "Loubach2019", "arquivo": "Loubach2019.pdf", "ano": 2019,
     "autores": "Loubach, Marques, da Cunha",
     "titulo": "Considerations on Domain-Specific Architectures Applicability in Future Avionics Systems (slides)"},
]
ARTIGOS_POR_ID = {a["id"]: a for a in ARTIGOS}


def _limpar(texto: str) -> str:
    texto = unicodedata.normalize("NFKC", texto)      # ligaduras: "ﬂight" -> "flight"
    texto = texto.replace("­", "")              # hífen invisível
    texto = re.sub(r"-\n(?=[a-z])", "", texto)       # palavra quebrada no fim da linha
    texto = re.sub(r"[ \t]+", " ", texto)
    texto = re.sub(r"\n{3,}", "\n\n", texto)
    return texto.strip()


def _dividir_em_trechos(texto: str, tamanho: int) -> list[str]:
    """Agrupa parágrafos até ~tamanho caracteres, com um parágrafo de sobreposição."""
    paragrafos = [p.strip() for p in re.split(r"\n\s*\n|(?<=\.)\n", texto) if p.strip()]
    trechos, atual = [], []
    for p in paragrafos:
        if atual and sum(len(x) for x in atual) + len(p) > tamanho:
            trechos.append(" ".join(atual))
            atual = atual[-1:]  # sobreposição de um parágrafo
        atual.append(p.replace("\n", " "))
    if atual:
        trechos.append(" ".join(atual))
    return trechos


def _sem_repeticoes(textos: list[str]) -> list[str]:
    """Remove linhas que se repetem na maioria das páginas de um documento: menus de slides,
    cabeçalhos e rodapés. Sem isso, toda página parece falar de tudo e a busca se perde."""
    if len(textos) < 4:
        return textos
    from collections import Counter
    conta = Counter(l.strip() for t in textos for l in set(t.splitlines()) if l.strip())
    limite = 0.6 * len(textos)
    repetidas = {l for l, n in conta.items() if n >= limite and not l.isdigit()}
    return ["\n".join(l for l in t.splitlines() if l.strip() not in repetidas) for t in textos]


def gerar_indice() -> dict:
    PASTA_DADOS.mkdir(exist_ok=True)
    paginas, faltando = [], []
    for art in ARTIGOS:
        caminho = PASTA_CORPUS / art["arquivo"]
        if not caminho.exists():
            faltando.append(art["arquivo"])
            continue
        with pymupdf.open(caminho) as doc:
            art["n_paginas"] = doc.page_count
            textos = _sem_repeticoes([pagina.get_text("text") for pagina in doc])
            for i, bruto in enumerate(textos, start=1):
                texto = _limpar(bruto)
                paginas.append({
                    "artigo": art["id"], "pagina": i, "texto": texto,
                    "trechos": _dividir_em_trechos(texto, TAMANHO_TRECHO),
                })
    dados = {"artigos": ARTIGOS, "paginas": paginas}
    ARQUIVO_PAGINAS.write_text(json.dumps(dados, ensure_ascii=False, indent=1), encoding="utf-8")
    return {"paginas": len(paginas), "faltando": faltando}


def carregar() -> dict:
    if not ARQUIVO_PAGINAS.exists():
        sys.exit("Índice não encontrado. Rode antes:  python -m agente.corpus")
    return json.loads(ARQUIVO_PAGINAS.read_text(encoding="utf-8"))


if __name__ == "__main__":
    r = gerar_indice()
    print(f"{r['paginas']} páginas indexadas em {ARQUIVO_PAGINAS}")
    if r["faltando"]:
        print("Faltando em corpus/:", ", ".join(r["faltando"]))
