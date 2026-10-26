"""Interface web local do agente (mesa de revisão).

Uso:  python app.py        (ou dê dois cliques em abrir_agente.bat)

Abre o navegador em http://127.0.0.1:8765. O servidor escuta só no seu
computador. Usa o mesmo agente do terminal (agente/harness.py): mesmas tools,
mesma trava, mesmo verificador, mesmo log. O gate humano continua valendo:
nada é gravado em fichamentos/ sem você clicar em "Aprovar e salvar".

A aba "Revisar" é o HITL da avaliação: você confere o gabarito e as respostas às
perguntas negativas, e cada decisão vai para um CSV com data e hora (revisao.py).
"""
import json
import mimetypes
import threading
import time
import uuid
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import revisao
from agente import hitl, verificador
from agente.config import PASTA_CORPUS, PROVEDORES, RAIZ
from agente.corpus import ARTIGOS_POR_ID
from agente.harness import Agente

PASTA_WEB = RAIZ / "web"
PORTA = 8765

agente = Agente()
trava_agente = threading.Lock()  # uma pergunta por vez
jobs: dict[str, dict] = {}


def _tem_chave(nome: str) -> bool:
    import os
    from dotenv import load_dotenv
    load_dotenv(RAIZ / ".env", override=True)  # chave colada com a interface aberta já conta
    env = PROVEDORES[nome]["api_key_env"]
    return env is None or bool(os.getenv(env))


def estado() -> dict:
    return {
        "modelo": agente.rotulo,
        "provedores": [{"nome": n, "modelo_padrao": c["modelo_padrao"], "pronto": _tem_chave(n)}
                       for n, c in PROVEDORES.items()],
        "artigos": [{"id": a["id"], "autores": a["autores"], "ano": a["ano"], "titulo": a["titulo"],
                     "paginas": a.get("n_paginas") or sum(1 for (x, _) in agente.ferramentas.paginas if x == a["id"])}
                    for a in agente.ferramentas.artigos],
        "chamadas_sessao": agente.chamadas_sessao,
    }


def linhas_verificadas(resposta: str, evidencias: dict) -> list[dict]:
    """Cada linha da resposta com o veredito do verificador (ou nenhum, se for título ou linha curta)."""
    saida = []
    for linha in resposta.splitlines():
        if not linha.strip():
            continue
        itens = verificador.verificar(linha, evidencias)
        item = itens[0] if itens else None
        saida.append({"texto": linha.strip(),
                      "veredito": item["veredito"] if item else None,
                      "detalhe": item["detalhe"] if item else "",
                      "citacoes": [list(c) for c in item["citacoes"]] if item else []})
    return saida


def rodar_job(job_id: str, texto: str):
    job = jobs[job_id]

    def ouvir(evento):
        evento["t"] = round(time.time() - job["inicio"], 1)
        job["eventos"].append(evento)

    with trava_agente:
        agente.ouvinte = ouvir
        try:
            resposta, chamadas = agente.responder(texto)
            evid = dict(agente.ferramentas.evidencias)
            itens = verificador.verificar(resposta, evid)
            agente._registrar({"tipo": "verificacao", "resumo": verificador.resumo(itens), "itens": itens,
                               "chamadas_turno": chamadas, "origem": "interface"})
            job["resultado"] = {
                "resposta": resposta, "itens": itens, "linhas": linhas_verificadas(resposta, evid),
                "chamadas": chamadas, "segundos": round(time.time() - job["inicio"], 1),
                "tokens": agente.tokens_contexto, "modelo": agente.rotulo,
                "lidas": sorted([a, p] for (a, p) in evid), "resumo": verificador.resumo(itens)}
            job["estado"] = "pronto"
        except Exception as e:  # erro do provedor, limite de requisições, rede
            job["estado"] = "erro"
            job["erro"] = f"{type(e).__name__}: {e}"
        finally:
            agente.ouvinte = None


def novo_job(texto: str, pergunta_original: str) -> str:
    job_id = uuid.uuid4().hex[:10]
    jobs[job_id] = {"estado": "rodando", "eventos": [], "inicio": time.time(), "pergunta": pergunta_original,
                    "resultado": None, "erro": None, "decidido": False}
    threading.Thread(target=rodar_job, args=(job_id, texto), daemon=True).start()
    return job_id


class Manipulador(BaseHTTPRequestHandler):
    def log_message(self, *args):  # silencia o log padrão no terminal
        pass

    # ---------- utilidades ----------
    def _json(self, dados, status=200):
        corpo = json.dumps(dados, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(corpo)))
        self.end_headers()
        self.wfile.write(corpo)

    def _arquivo(self, caminho, tipo=None):
        if not caminho.is_file():
            return self._json({"erro": "não encontrado"}, 404)
        dados = caminho.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", tipo or mimetypes.guess_type(str(caminho))[0] or "application/octet-stream")
        self.send_header("Content-Length", str(len(dados)))
        self.end_headers()
        self.wfile.write(dados)

    def _corpo(self) -> dict:
        n = int(self.headers.get("Content-Length") or 0)
        try:
            return json.loads(self.rfile.read(n) or b"{}")
        except json.JSONDecodeError:
            return {}

    # ---------- GET ----------
    def do_GET(self):
        url = urlparse(self.path)
        q = {k: v[0] for k, v in parse_qs(url.query).items()}
        if url.path in ("/", "/index.html"):
            return self._arquivo(PASTA_WEB / "index.html", "text/html; charset=utf-8")
        if url.path in ("/estilo.css", "/app.js"):
            tipo = "text/css; charset=utf-8" if url.path.endswith(".css") else "text/javascript; charset=utf-8"
            return self._arquivo(PASTA_WEB / url.path.lstrip("/"), tipo)
        if url.path == "/api/estado":
            return self._json(estado())
        if url.path == "/api/job":
            job = jobs.get(q.get("id", ""))
            if not job:
                return self._json({"erro": "pergunta não encontrada"}, 404)
            return self._json({k: job[k] for k in ("estado", "eventos", "resultado", "erro", "decidido")})
        if url.path == "/api/pagina":
            art, pag = q.get("artigo", ""), int(q.get("pagina", "0") or 0)
            texto = agente.ferramentas.paginas.get((art, pag))
            if texto is None:
                return self._json({"erro": f"{art} não tem a página {pag}"}, 404)
            total = sum(1 for (a, _) in agente.ferramentas.paginas if a == art)
            return self._json({"artigo": art, "pagina": pag, "total": total, "texto": texto})
        if url.path == "/api/revisao/conjuntos":
            return self._json({"conjuntos": revisao.conjuntos()})
        if url.path == "/api/revisao":
            try:
                return self._json(revisao.carregar(q.get("conjunto", "")))
            except ValueError as e:
                return self._json({"erro": str(e)}, 404)
        if url.path.startswith("/pdf/"):
            art = url.path[len("/pdf/"):].removesuffix(".pdf")
            if art not in ARTIGOS_POR_ID:  # só serve PDFs do corpus
                return self._json({"erro": "artigo desconhecido"}, 404)
            return self._arquivo(PASTA_CORPUS / ARTIGOS_POR_ID[art]["arquivo"], "application/pdf")
        return self._json({"erro": "não encontrado"}, 404)

    # ---------- POST ----------
    def do_POST(self):
        url = urlparse(self.path)
        dados = self._corpo()
        if url.path == "/api/perguntar":
            pergunta = (dados.get("pergunta") or "").strip()
            if not pergunta:
                return self._json({"erro": "Escreva uma pergunta."}, 400)
            if trava_agente.locked():
                return self._json({"erro": "O agente ainda está respondendo a pergunta anterior."}, 409)
            # Cada pergunta nova começa do zero: perguntas são independentes, e o histórico de
            # uma não deve puxar a resposta da outra (nem gastar tokens). Correções continuam a conversa.
            agente.limpar()
            return self._json({"job": novo_job(pergunta, pergunta)})
        if url.path == "/api/decisao":
            job = jobs.get(dados.get("job", ""))
            if not job or job["estado"] != "pronto":
                return self._json({"erro": "Não há resposta pronta para decidir."}, 400)
            if job["decidido"]:
                return self._json({"erro": "Essa resposta já foi decidida."}, 409)
            decisao, comentario = dados.get("decisao"), (dados.get("comentario") or "").strip()
            if decisao not in ("aprovar", "corrigir", "rejeitar"):
                return self._json({"erro": "Decisão inválida."}, 400)
            if decisao == "corrigir" and not comentario:
                return self._json({"erro": "Escreva o que o agente deve corrigir."}, 400)
            job["decidido"] = True
            agente._registrar({"tipo": "decisao_humana", "decisao": decisao, "comentario": comentario,
                               "origem": "interface"})
            r = job["resultado"]
            if decisao == "aprovar":
                arquivo = hitl.gravar_fichamento(job["pergunta"], r["resposta"], r["itens"], r["modelo"], comentario)
                return self._json({"ok": True, "arquivo": str(arquivo)})
            if decisao == "rejeitar":
                return self._json({"ok": True})
            if trava_agente.locked():
                return self._json({"erro": "O agente ainda está ocupado."}, 409)
            texto = f"Revise a resposta anterior. Correção pedida pela pessoa: {comentario}"
            return self._json({"ok": True, "job": novo_job(texto, job["pergunta"])})
        if url.path == "/api/modelo":
            try:
                msg = agente.trocar_modelo((dados.get("alvo") or "").strip())
            except ValueError as e:
                return self._json({"erro": str(e)}, 400)
            return self._json({"mensagem": msg, **estado()})
        if url.path == "/api/revisao":
            try:
                linha = revisao.decidir(dados.get("conjunto", ""), dados.get("id", ""),
                                        (dados.get("status") or "").strip(), dados.get("comentario") or "")
            except ValueError as e:
                return self._json({"erro": str(e)}, 400)
            return self._json({"ok": True, "revisao": linha})
        if url.path == "/api/limpar":
            if trava_agente.locked():
                return self._json({"erro": "Espere a resposta terminar."}, 409)
            agente.limpar()
            return self._json({"ok": True})
        return self._json({"erro": "não encontrado"}, 404)


def main():
    porta = PORTA
    for tentativa in range(10):
        try:
            servidor = ThreadingHTTPServer(("127.0.0.1", porta), Manipulador)
            break
        except OSError:
            porta += 1
    else:
        raise SystemExit("Nenhuma porta livre entre 8765 e 8774.")
    endereco = f"http://127.0.0.1:{porta}"
    print(f"Mesa de revisão aberta em {endereco}  (Ctrl+C para encerrar)")
    print(f"Modelo: {agente.rotulo} · log: {agente.arquivo_log}")
    threading.Timer(0.8, lambda: webbrowser.open(endereco)).start()
    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        print("\nEncerrado.")


if __name__ == "__main__":
    main()
