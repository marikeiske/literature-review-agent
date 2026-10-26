"""Gera corpus/FONTES.md: de onde vem cada PDF do corpus e o SHA-256 do arquivo usado na avaliação.

Os PDFs não vão para o repositório (direitos autorais; um deles é "Not for redistribution").
Quem quiser reproduzir a avaliação baixa cada PDF pela fonte e confere o hash:

  python corpus_fontes.py            gera corpus/FONTES.md a partir dos PDFs desta máquina
  python corpus_fontes.py --conferir confere os PDFs de corpus/ com os hashes de FONTES.md
"""
import hashlib
import re
import sys

from agente.config import PASTA_CORPUS
from agente.corpus import ARTIGOS

# DOI ou origem de cada documento (mesmas referências de artigo/refs.bib)
ORIGEM = {
    "Nimbekar2023": "https://doi.org/10.1109/ACCESS.2023.3293422",
    "Breyer2022": "https://doi.org/10.1145/3529538.3529980",
    "Sifakis2015": "https://doi.org/10.1109/JPROC.2015.2484060",
    "Lozano2023": "https://doi.org/10.1109/ACCESS.2023.3264825",
    "Mzid2024": "https://doi.org/10.1007/s11227-023-05866-0",
    "YoungS2023": "https://doi.org/10.1016/j.cpc.2023.108669",
    "Leppanen2023": "https://doi.org/10.1016/j.micpro.2023.104772",
    "Yoshida2024": "https://doi.org/10.1016/j.parco.2024.103081",
    "FAA2024": "FAA, Advisory Circular AC 20-193 (documento público no site da FAA)",
    "PeraltaQuesada2023": "IWOCL'23 (DOI a conferir). Marcado \"Not for redistribution\": não redistribuir",
    "Loubach2019": "Slides de apresentação (FT2019), cedidos pelo autor; não publicados",
}
DESTINO = PASTA_CORPUS / "FONTES.md"


def sha256(caminho) -> str:
    h = hashlib.sha256()
    with open(caminho, "rb") as f:
        for bloco in iter(lambda: f.read(1 << 20), b""):
            h.update(bloco)
    return h.hexdigest()


def gerar():
    linhas = ["# Fontes do corpus", "",
              "Os PDFs não estão no repositório. Baixe cada um pela fonte, salve em `corpus/` com o nome",
              "indicado e rode `python corpus_fontes.py --conferir`: o SHA-256 precisa bater com o da tabela,",
              "senão as páginas citadas podem não ser as mesmas da avaliação.", "",
              "| Id | Arquivo | Ano | Título | Origem | SHA-256 |", "|---|---|---|---|---|---|"]
    for a in ARTIGOS:
        pdf = PASTA_CORPUS / a["arquivo"]
        hash_ = sha256(pdf) if pdf.exists() else "(arquivo ausente)"
        linhas.append(f"| {a['id']} | `{a['arquivo']}` | {a['ano']} | {a['titulo']} | {ORIGEM.get(a['id'], '–')} | `{hash_}` |")
    DESTINO.write_text("\n".join(linhas) + "\n", encoding="utf-8")
    print(f"Gravado em {DESTINO}")


def conferir() -> int:
    esperado = dict(re.findall(r"\| `([^`]+\.pdf)` \|.*\| `([0-9a-f]{64})` \|", DESTINO.read_text(encoding="utf-8")))
    erros = 0
    for arquivo, hash_ in esperado.items():
        pdf = PASTA_CORPUS / arquivo
        if not pdf.exists():
            print(f"FALTA   {arquivo}")
            erros += 1
        elif sha256(pdf) != hash_:
            print(f"DIFERE  {arquivo} (outra versão do PDF: as páginas podem não bater)")
            erros += 1
        else:
            print(f"ok      {arquivo}")
    return 1 if erros else 0


if __name__ == "__main__":
    sys.exit(conferir() if "--conferir" in sys.argv else gerar())
