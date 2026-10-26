"""Tools do agente. Todas são SOMENTE LEITURA.

Diferente da demo da disciplina (harness-demo, passo 15–17), não há tool Bash:
o agente não executa comandos nem altera arquivos. Gravar o fichamento é um
efeito, e efeito só acontece depois do gate humano (hitl.py).

Cada tool registra as páginas que devolveu ao modelo em `self.evidencias`.
O verificador usa esse registro: uma citação só vale se a página citada foi
de fato lida pelo agente neste turno (grounding, Aula 10, p. 66).
"""
import json

from .busca import IndiceBM25
from .config import PASTA_SKILLS, TOP_K
from .corpus import ARTIGOS_POR_ID, carregar

DEFINICOES = [
    {"type": "function", "function": {
        "name": "listar_artigos",
        "description": "Lista os artigos do corpus (id, autores, ano, título, número de páginas).",
        "parameters": {"type": "object", "properties": {}, "additionalProperties": False}}},
    {"type": "function", "function": {
        "name": "buscar_trechos",
        "description": ("Busca por palavras-chave nos artigos do corpus e devolve os trechos mais "
                        "relevantes, cada um com artigo e página. Os artigos estão em INGLÊS: "
                        "use termos em inglês na consulta."),
        "parameters": {"type": "object", "properties": {
            "consulta": {"type": "string", "description": "Palavras-chave em inglês."},
            "artigo": {"type": "string", "description": "Opcional: id de um artigo para restringir a busca."},
        }, "required": ["consulta"], "additionalProperties": False}}},
    {"type": "function", "function": {
        "name": "ler_pagina",
        "description": "Devolve o texto completo de uma página de um artigo (página física do PDF, 1 = primeira).",
        "parameters": {"type": "object", "properties": {
            "artigo": {"type": "string", "description": "Id do artigo, por exemplo Lozano2023."},
            "pagina": {"type": "integer", "description": "Número da página física do PDF."},
        }, "required": ["artigo", "pagina"], "additionalProperties": False}}},
    {"type": "function", "function": {
        "name": "carregar_skill",
        "description": "Carrega as instruções completas de uma Skill listada no system prompt.",
        "parameters": {"type": "object", "properties": {
            "nome": {"type": "string", "description": "Nome da Skill."},
        }, "required": ["nome"], "additionalProperties": False}}},
]


class Ferramentas:
    def __init__(self):
        dados = carregar()
        self.artigos = dados["artigos"]
        self.paginas = {(p["artigo"], p["pagina"]): p["texto"] for p in dados["paginas"]}
        self.indice = IndiceBM25(dados["paginas"])
        self.evidencias: dict[tuple[str, int], str] = {}  # (artigo, página) -> texto lido

    def novo_turno(self):
        self.evidencias = {}

    def executar(self, nome: str, argumentos: str) -> str:
        try:
            args = json.loads(argumentos or "{}")
        except json.JSONDecodeError:
            return "Erro: argumentos não são JSON válido."
        metodo = getattr(self, f"_{nome}", None)
        if metodo is None:
            return f"Tool desconhecida: {nome}"
        try:
            return metodo(**args)
        except TypeError as e:
            return f"Erro nos argumentos de {nome}: {e}"

    def _listar_artigos(self) -> str:
        linhas = [f'{a["id"]} | {a["autores"]} ({a["ano"]}) | {a["titulo"]} | {a.get("n_paginas", "?")} p.'
                  for a in self.artigos]
        return "\n".join(linhas)

    def _buscar_trechos(self, consulta: str, artigo: str | None = None) -> str:
        if artigo and artigo not in ARTIGOS_POR_ID:
            return f"Artigo desconhecido: {artigo}. Use listar_artigos."
        achados = self.indice.buscar(consulta, k=TOP_K, artigo=artigo)
        if not achados:
            return "Nenhum trecho encontrado. Tente outras palavras-chave em inglês."
        partes = []
        for r in achados:
            self.evidencias[(r["artigo"], r["pagina"])] = self.paginas[(r["artigo"], r["pagina"])]
            partes.append(f'[{r["artigo"]} p.{r["pagina"]}] (score {r["score"]})\n{r["texto"]}')
        return "\n\n---\n\n".join(partes)

    def _ler_pagina(self, artigo: str, pagina: int) -> str:
        texto = self.paginas.get((artigo, int(pagina)))
        if texto is None:
            return f"Página não existe: {artigo} p.{pagina}."
        self.evidencias[(artigo, int(pagina))] = texto
        return f"[{artigo} p.{pagina}]\n{texto}"

    def _carregar_skill(self, nome: str) -> str:
        arquivo = PASTA_SKILLS / nome / "SKILL.md"
        if not arquivo.exists():
            return f"Skill não encontrada: {nome}"
        return arquivo.read_text(encoding="utf-8")
