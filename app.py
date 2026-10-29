"""Interface web local do agente (mesa de revisão).

Uso:  python app.py        (ou dê dois cliques em abrir_agente.bat)

Abre o navegador em http://127.0.0.1:8765. O servidor escuta só no seu
computador. Usa o mesmo agente do terminal (agente/harness.py): mesmas tools,
mesma trava, mesmo verificador, mesmo log. O gate humano continua valendo:
nada é gravado em fichamentos/ sem você clicar em "Aprovar e salvar".

O botão "Histórico" mostra as perguntas anteriores feitas na interface, lidas dos logs
(somente leitura), com a decisão humana que cada uma recebeu.

A aba "Revisar" é o HITL da avaliação: você confere o gabarito e as respostas às
perguntas negativas, e cada decisão vai para um CSV (revisao.py); o horário fica só em logs/, fora do repositório.

Pelo celular (opcional): com MESA_REMOTO=1 no .env, abre também um servidor no endereço do
Tailscale, protegido pelo código MESA_CODIGO (regras em seguranca.py; passo a passo no README).
"""
import json
import mimetypes
import os
import re
import socket
import subprocess
import threading
import time
import uuid
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import revisao
import seguranca
from agente import hitl, verificador
from agente.config import PASTA_CORPUS, PASTA_LOGS, PROVEDORES, RAIZ
from agente.corpus import ARTIGOS_POR_ID
from agente.harness import Agente

PASTA_WEB = RAIZ / "web"
PASTA_VENDOR = PASTA_WEB / "vendor"  # PDF.js empacotado (Apache-2.0), para não depender de CDN
PORTA = 8765
porta_ativa = PORTA  # a porta em que o servidor abriu de fato (main)

# Segurança do servidor local: regras em seguranca.py (testadas em tests/test_seguranca.py).
CSP = ("default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
       "font-src https://fonts.gstatic.com; img-src 'self' data: blob:; frame-src 'self'; worker-src 'self' blob:; "
       "connect-src 'self'; object-src 'none'; base-uri 'none'; form-action 'self'; frame-ancestors 'self'")

agente = Agente()
trava_agente = threading.Lock()  # uma pergunta por vez
jobs: dict[str, dict] = {}
tentativas = seguranca.Tentativas()  # códigos errados no acesso pelo celular


def _tem_chave(nome: str) -> bool:
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


# ---------- histórico: perguntas feitas na interface, lidas dos logs ----------
CORRECAO = "Revise a resposta anterior. Correção pedida pela pessoa:"
MARCA_PAGINA = re.compile(r"\[([A-Za-z][A-Za-z\-]*\d{4}) p\.(\d+)\]")
_cache_hist: dict = {}  # arquivo -> (mtime, entradas)


def _entradas_do_log(arquivo: Path) -> list[dict]:
    """Uma entrada por pergunta respondida na interface, com a resposta e as páginas lidas."""
    mtime = arquivo.stat().st_mtime
    if arquivo in _cache_hist and _cache_hist[arquivo][0] == mtime:
        return _cache_hist[arquivo][1]
    entradas, atual = [], None
    with open(arquivo, encoding="utf-8") as f:
        for linha in f:
            try:
                ev = json.loads(linha)
            except json.JSONDecodeError:
                continue
            tipo = ev.get("tipo")
            if tipo == "pergunta":
                atual = {"pergunta": ev.get("texto", ""), "quando": ev.get("quando", ""), "modelo": ev.get("modelo", ""),
                         "resposta": "", "lidas": set(), "chamadas": 0, "segundos": 0.0, "tokens": 0}
            elif tipo == "decisao_humana":
                # A decisão vem depois da verificação: vale para a última pergunta respondida
                if entradas and ev.get("origem") == "interface":
                    entradas[-1]["decisao"] = ev.get("decisao", "")
                    entradas[-1]["comentario"] = ev.get("comentario", "")
            elif atual is None:
                continue
            elif tipo == "chamada_llm":
                atual["chamadas"] += 1
                atual["segundos"] += float(ev.get("segundos") or 0)
                atual["tokens"] = ev.get("tokens_entrada") or atual["tokens"]
                saida = ev.get("saida")
                conteudo = saida.get("content") if isinstance(saida, dict) else None
                if conteudo:
                    atual["resposta"] = conteudo
            elif tipo == "tool":
                args = ev.get("argumentos") or {}
                if isinstance(args, str):
                    try:
                        args = json.loads(args)
                    except json.JSONDecodeError:
                        args = {}
                if ev.get("nome") == "ler_pagina" and args.get("artigo") and args.get("pagina"):
                    atual["lidas"].add((args["artigo"], int(args["pagina"])))
                for a, pg in MARCA_PAGINA.findall(str(ev.get("saida") or "")):
                    atual["lidas"].add((a, int(pg)))
            elif tipo == "verificacao" and ev.get("origem") == "interface":
                # Logs novos gravam as páginas lidas completas; nos antigos, o texto das buscas vem
                # cortado no log, então vale o veredito gravado na hora (não se recalcula).
                atual["lidas_completas"] = bool(ev.get("lidas"))
                if ev.get("lidas"):
                    atual["lidas"] = {(a, int(pg)) for a, pg in ev["lidas"]}
                atual["itens_log"] = ev.get("itens") or []
                atual.update({"resumo": ev.get("resumo", ""), "decisao": "", "comentario": "",
                              "id": f"{arquivo.stem}#{len(entradas)}"})
                entradas.append(atual)
                atual = None
    _cache_hist[arquivo] = (mtime, entradas)
    return entradas


def historico() -> list[dict]:
    saida = []
    for arq in sorted(PASTA_LOGS.glob("sessao_*.jsonl"), reverse=True):
        for e in reversed(_entradas_do_log(arq)):
            correcao = e["pergunta"].startswith(CORRECAO)
            saida.append({"id": e["id"], "quando": e["quando"], "modelo": e["modelo"], "resumo": e["resumo"],
                          "pergunta": e["pergunta"].removeprefix(CORRECAO).strip() if correcao else e["pergunta"],
                          "correcao": correcao, "decisao": e["decisao"]})
    return saida


def item_historico(id_: str) -> dict:
    if not seguranca.id_historico_valido(id_):  # nada de "../" no id
        raise ValueError("Conversa não encontrada.")
    stem, _, n = id_.partition("#")
    arquivo = PASTA_LOGS / f"{stem}.jsonl"
    if not arquivo.is_file():
        raise ValueError("Conversa não encontrada.")
    entradas = _entradas_do_log(arquivo)
    if int(n) >= len(entradas):
        raise ValueError("Conversa não encontrada.")
    e = entradas[int(n)]
    evid = {k: agente.ferramentas.paginas[k] for k in e["lidas"] if k in agente.ferramentas.paginas}
    if e["lidas_completas"]:
        itens = verificador.verificar(e["resposta"], evid)
        linhas = linhas_verificadas(e["resposta"], evid)
    else:
        itens = e["itens_log"]
        linhas = [{"texto": it.get("frase", ""), "veredito": it.get("veredito"), "detalhe": it.get("detalhe", ""),
                   "citacoes": [list(c) for c in it.get("citacoes", [])]} for it in itens]
        # Páginas citadas que o verificador deu como lidas também foram lidas
        for it in itens:
            if it.get("veredito") in ("rastreável", "número ausente"):
                for art, pg in it.get("citacoes", []):
                    if (art, int(pg)) in agente.ferramentas.paginas:
                        evid[(art, int(pg))] = agente.ferramentas.paginas[(art, int(pg))]
    correcao = e["pergunta"].startswith(CORRECAO)
    return {"pergunta": e["pergunta"].removeprefix(CORRECAO).strip() if correcao else e["pergunta"],
            "correcao": correcao, "quando": e["quando"], "decisao": e["decisao"], "comentario": e["comentario"],
            "resultado": {"resposta": e["resposta"], "itens": itens, "linhas": linhas,
                          "chamadas": e["chamadas"], "segundos": round(e["segundos"], 1), "tokens": e["tokens"],
                          "modelo": e["modelo"], "lidas": sorted([a, pg] for (a, pg) in evid),
                          "resumo": e["resumo"]}}


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
                               "chamadas_turno": chamadas, "origem": "interface",
                               "lidas": sorted([a, p] for (a, p) in evid)})
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
        self._cabecalhos_seguranca()
        self.send_header("Content-Length", str(len(corpo)))
        self.end_headers()
        self.wfile.write(corpo)

    def _cabecalhos_seguranca(self, pagina=False):
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Frame-Options", "SAMEORIGIN")
        if pagina:
            self.send_header("Content-Security-Policy", CSP)

    def _pedido_confiavel(self, post: bool) -> bool:
        return seguranca.pedido_confiavel(self.headers, porta_ativa, post, self.server.hosts_extra)

    # ---------- acesso pelo celular ----------
    LIVRES_SEM_CODIGO = {"/entrar", "/entrar.js", "/estilo.css"}

    def _barrar_sem_codigo(self, post: bool) -> bool:
        """No servidor do Tailscale, responde e devolve True se o pedido não traz sessão válida."""
        if not self.server.remoto:
            return False
        if seguranca.cookie_valido(self.headers.get("Cookie", ""), self.server.codigo):
            return False
        caminho = urlparse(self.path).path
        if (not post and caminho in self.LIVRES_SEM_CODIGO) or (post and caminho == "/api/entrar"):
            return False
        if not post and caminho in ("/", "/index.html"):
            self.send_response(303)
            self.send_header("Location", "/entrar")
            self._cabecalhos_seguranca()
            self.send_header("Content-Length", "0")
            self.end_headers()
        else:
            self._json({"erro": "Entre com o código de acesso."}, 401)
        return True

    def _entrar(self, dados: dict):
        if not self.server.remoto:
            return self._json({"erro": "não encontrado"}, 404)
        if tentativas.bloqueado():
            return self._json({"erro": "Muitos códigos errados. Espere 10 minutos."}, 429)
        certo = seguranca.codigo_confere(str(dados.get("codigo") or ""), self.server.codigo)
        tentativas.registrar(certo)
        if not certo:
            time.sleep(1)  # deixa a adivinhação lenta
            return self._json({"erro": "Código errado."}, 401)
        corpo = b'{"ok": true}'
        self.send_response(200)
        self.send_header("Set-Cookie", f"{seguranca.COOKIE}={seguranca.token_sessao(self.server.codigo)}; "
                                       "Max-Age=2592000; Path=/; HttpOnly; SameSite=Strict")
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self._cabecalhos_seguranca()
        self.send_header("Content-Length", str(len(corpo)))
        self.end_headers()
        self.wfile.write(corpo)

    def _arquivo(self, caminho, tipo=None):
        if not caminho.is_file():
            return self._json({"erro": "não encontrado"}, 404)
        dados = caminho.read_bytes()
        self.send_response(200)
        self._cabecalhos_seguranca(pagina=caminho.suffix == ".html")
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
        if not self._pedido_confiavel(post=False):
            return self._json({"erro": "Pedido recusado: abra a interface em http://127.0.0.1."}, 403)
        if self._barrar_sem_codigo(post=False):
            return None
        url = urlparse(self.path)
        q = {k: v[0] for k, v in parse_qs(url.query).items()}
        if url.path in ("/", "/index.html"):
            return self._arquivo(PASTA_WEB / "index.html", "text/html; charset=utf-8")
        if url.path == "/entrar" and self.server.remoto:
            return self._arquivo(PASTA_WEB / "entrar.html", "text/html; charset=utf-8")
        if url.path == "/entrar.js" and self.server.remoto:
            return self._arquivo(PASTA_WEB / "entrar.js", "text/javascript; charset=utf-8")
        if url.path.startswith("/vendor/"):
            nome = url.path[len("/vendor/"):]
            if not seguranca.nome_vendor_valido(nome):
                return self._json({"erro": "não encontrado"}, 404)
            tipo = "text/javascript; charset=utf-8" if nome.endswith(".mjs") else None
            return self._arquivo(PASTA_VENDOR / nome, tipo)
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
        if url.path == "/api/historico":
            return self._json({"conversas": historico()})
        if url.path == "/api/historico/item":
            try:
                return self._json(item_historico(q.get("id", "")))
            except ValueError as e:
                return self._json({"erro": str(e)}, 404)
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
        if not self._pedido_confiavel(post=True):
            return self._json({"erro": "Pedido recusado: só a própria interface pode fazer alterações."}, 403)
        if self._barrar_sem_codigo(post=True):
            return None
        url = urlparse(self.path)
        dados = self._corpo()
        if url.path == "/api/entrar":
            return self._entrar(dados)
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


class ServidorLocal(ThreadingHTTPServer):
    """Servidor que não divide a porta com outro programa.

    No Windows, o HTTPServer do Python liga SO_REUSEADDR, e aí dois servidores abrem a MESMA porta
    sem erro: os pedidos caem em qualquer um deles (achado em 28/10, nos testes de interface).
    SO_EXCLUSIVEADDRUSE faz a segunda tentativa falhar, e o laço de main() passa para a próxima porta."""
    daemon_threads = True
    remoto = False  # True só no servidor do Tailscale (acesso pelo celular)
    hosts_extra = frozenset()
    codigo = ""
    if os.name == "nt":
        allow_reuse_address = False

        def server_bind(self):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            super().server_bind()


def _ip_tailscale() -> tuple[str, set[str]]:
    """Endereço 100.x deste computador no Tailscale e os nomes dele (MagicDNS). ("", set()) se não houver."""
    nomes = {socket.gethostname().lower()}
    ip = (os.getenv("MESA_IP_REMOTO") or "").strip()
    try:
        r = subprocess.run(["tailscale", "status", "--json"], capture_output=True, text=True, timeout=8)
        eu = json.loads(r.stdout or "{}").get("Self", {})
        if eu.get("DNSName"):
            nome = eu["DNSName"].rstrip(".").lower()
            nomes |= {nome, nome.split(".")[0]}
        ip = ip or next((x for x in eu.get("TailscaleIPs", []) if "." in x), "")
    except (OSError, ValueError, subprocess.SubprocessError):
        pass
    if not ip:  # sem o comando tailscale no PATH: procura um 100.x entre os endereços da máquina
        try:
            ends = {i[4][0] for i in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET)}
            ip = next((x for x in sorted(ends) if seguranca.ip_remoto_valido(x) and not x.startswith("127.")), "")
        except OSError:
            ip = ""
    return (ip, nomes) if seguranca.ip_remoto_valido(ip) else ("", set())


def _codigo_de_acesso() -> str:
    """Lê MESA_CODIGO do .env; se faltar ou for curto, cria um e acrescenta ao .env (que nunca vai ao git)."""
    codigo = (os.getenv("MESA_CODIGO") or "").strip()
    if seguranca.codigo_forte(codigo):
        return codigo
    codigo = seguranca.novo_codigo()
    env = RAIZ / ".env"
    fim = env.read_bytes()[-1:] if env.exists() else b"\n"
    with open(env, "ab") as f:  # só acrescenta: as chaves que já estão no .env ficam intactas
        f.write((b"" if fim in (b"\n", b"") else b"\n") + f"MESA_CODIGO={codigo}\n".encode())
    os.environ["MESA_CODIGO"] = codigo
    print(f"Código de acesso novo, gravado no .env: {codigo}")
    return codigo


def abrir_remoto(porta: int):
    """Servidor para o celular: só no endereço do Tailscale, nunca no Wi-Fi nem em 0.0.0.0."""
    ip, nomes = _ip_tailscale()
    if not ip:
        print("Acesso pelo celular: não achei o endereço do Tailscale (100.x). O Tailscale está ligado?")
        return
    try:
        remoto = ServidorLocal((ip, porta), Manipulador)
    except OSError as e:
        print(f"Acesso pelo celular: não consegui abrir {ip}:{porta} ({e}).")
        return
    remoto.remoto = True
    remoto.codigo = _codigo_de_acesso()
    remoto.hosts_extra = frozenset(f"{h}:{porta}" for h in {ip, *nomes})
    threading.Thread(target=remoto.serve_forever, daemon=True).start()
    nome = max(nomes, key=len)
    print(f"Pelo celular (Tailscale ligado nos dois): http://{nome}:{porta}  ou  http://{ip}:{porta}")
    print("Na primeira vez o celular pede o código de acesso: está no .env, em MESA_CODIGO.")


def main():
    porta = int(os.getenv("MESA_PORTA") or PORTA)  # os testes de interface usam outra faixa de portas
    for _ in range(10):
        try:
            servidor = ServidorLocal(("127.0.0.1", porta), Manipulador)
            break
        except OSError:
            porta += 1
    else:
        raise SystemExit(f"Nenhuma porta livre a partir de {int(os.getenv('MESA_PORTA') or PORTA)}.")
    global porta_ativa
    porta_ativa = porta
    endereco = f"http://127.0.0.1:{porta}"
    print(f"Mesa de revisão aberta em {endereco}  (Ctrl+C para encerrar)")
    print(f"Modelo: {agente.rotulo} · log: {agente.arquivo_log}")
    if (os.getenv("MESA_REMOTO") or "").strip().lower() in ("1", "sim", "true"):
        abrir_remoto(porta)
    if not os.getenv("MESA_SEM_NAVEGADOR"):  # os testes de interface (tests/ui) abrem o próprio navegador
        threading.Timer(0.8, lambda: webbrowser.open(endereco)).start()
    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        print("\nEncerrado.")


if __name__ == "__main__":
    main()
