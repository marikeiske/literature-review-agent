// Mesa de revisão: conversa com o agente, conferência das páginas e decisão humana.
"use strict";

const $ = (s) => document.querySelector(s);
const CITACAO = /\[\s*([A-Za-z][A-Za-z\-]*\d{4})\s*,?\s*p(?:ág)?\.?\s*(\d+)\s*\]/g;
const NUMERO = /(?<![\w.])\d+(?:[.,]\d+)?/g;

// Acerto = página exata nas 109 afirmações do gabarito, condição RAG (resultados/resumo_numeros.md, 26/10/2026).
// O primeiro modelo disponível do grupo "Recomendados" é o padrão.
// O modelo local (Bonsai 2 4B) saiu da lista em 26/10: só em CPU leu o prompt a 3,66 tokens/s, inviável.
const MODELOS = [
  { grupo: "Recomendados", alvo: "ollama:nemotron-3-ultra:cloud", rotulo: "Nemotron 3 Ultra · Ollama Cloud · 97%", provedor: "ollama" },
  { grupo: "Recomendados", alvo: "groq", rotulo: "GPT-OSS 120B · Groq · 95%", provedor: "groq" },
  { grupo: "Recomendados", alvo: "ollama:gpt-oss:120b-cloud", rotulo: "GPT-OSS 120B · Ollama Cloud · 95%", provedor: "ollama" },
  { grupo: "Recomendados", alvo: "ollama:gemma4:31b-cloud", rotulo: "Gemma 4 31B · Ollama Cloud · 94%", provedor: "ollama" },
  { grupo: "Outros", alvo: "gemini", rotulo: "Gemini Flash-Lite · Google · 91%", provedor: "gemini" },
  { grupo: "Outros", alvo: "groq:qwen/qwen3.8-27b", rotulo: "Qwen3.8 27B · Groq · amostra de 80", provedor: "groq" },
  { grupo: "Outros", alvo: "openrouter", rotulo: "Nemotron 3 Ultra · OpenRouter · não avaliado", provedor: "openrouter" },
];
const EXEMPLOS = [
  "Quanto a arquitetura de Nimbekar consome na FPGA?",
  "Quanto de sobrecarga a sincronização dentro do chip elimina no trabalho de Leppänen?",
  "Faça o fichamento do artigo de Sifakis",
];
const VEREDITOS = {
  "rastreável": { sinal: "✓", classe: "v-rastreavel", dica: "Página lida e números conferem. Ainda falta você ver se o trecho sustenta a frase." },
  "número ausente": { sinal: "?", classe: "v-numero", dica: "Há um número na frase que não aparece na página citada." },
  "página não lida": { sinal: "✗", classe: "v-nao-lida", dica: "Cita uma página que o agente não leu nesta resposta." },
  "recusa sem página lida": { sinal: "✗", classe: "v-sem-pagina", dica: "Disse que não consta sem ter lido nenhuma página." },
  "sem citação": { sinal: "!", classe: "v-sem-citacao", dica: "Afirmação sem página." },
  "recusa": { sinal: "–", classe: "v-recusa", dica: "Não encontrou no material lido." },
};

let estado = null;
let ocupado = false;
const fonte = { artigo: null, pagina: 1, total: 1, destaque: { numeros: [], termos: [] }, modo: "pdf", aba: null };

// ---------------- utilidades ----------------
function esc(t) {
  return String(t).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}
function el(tag, attrs = {}, ...filhos) {
  const n = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "class") n.className = v;
    else if (k === "html") n.innerHTML = v;
    else if (k.startsWith("on")) n.addEventListener(k.slice(2), v);
    else n.setAttribute(k, v);
  }
  for (const f of filhos) if (f != null) n.append(f);
  return n;
}
let avisoTimer;
function aviso(msg) {
  const a = $("#aviso");
  a.textContent = msg;
  a.hidden = false;
  clearTimeout(avisoTimer);
  avisoTimer = setTimeout(() => (a.hidden = true), 4200);
}
async function api(caminho, dados) {
  const op = dados ? { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados) } : {};
  const r = await fetch(caminho, op);
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(j.erro || `Erro ${r.status}`);
  return j;
}
function explicarErro(erro) {
  if (/429|RateLimit|rate.limit/i.test(erro)) return "O limite gratuito deste modelo acabou por agora. Escolha outro modelo no seletor acima ou tente mais tarde.";
  if (/413|too large/i.test(erro)) return "A conversa ficou grande demais para o plano gratuito. Clique em Nova conversa e pergunte de novo.";
  if (/Timeout|timed out/i.test(erro)) return "O provedor demorou mais de 2 minutos para responder. Tente de novo ou escolha outro modelo no seletor acima.";
  if (/402|not included in your free/i.test(erro)) return "Este modelo saiu do plano gratuito do provedor. Escolha outro no seletor acima.";
  if (/401|invalid.api.key|Unauthorized/i.test(erro)) return "A chave deste provedor no arquivo .env não foi aceita. Confira a chave ou escolha outro modelo.";
  if (/Connection|connect|recusad/i.test(erro)) return "Não consegui falar com o provedor. Se o modelo for do Ollama, confira se o Docker Desktop está aberto (consertar_docker.bat) e tente de novo.";
  if (/503|UNAVAILABLE|high demand/i.test(erro)) return "O modelo está sobrecarregado no provedor agora. Tente de novo em alguns minutos ou escolha outro modelo no seletor acima.";
  if (/404|model_not_found/i.test(erro)) return "O provedor não reconhece esse modelo. Escolha outro no seletor acima.";
  return "O provedor devolveu um erro. Tente de novo ou troque de modelo.";
}

// ---------------- estado inicial ----------------
async function carregarEstado() {
  estado = await api("/api/estado");
  $("#sub-corpus").textContent = `${estado.artigos.length} documentos no corpus`;
  const sel = $("#modelo");
  sel.innerHTML = "";
  const prontos = Object.fromEntries(estado.provedores.map((p) => [p.nome, p.pronto]));
  const grupos = {};
  for (const m of MODELOS) {
    if (!grupos[m.grupo]) sel.append((grupos[m.grupo] = el("optgroup", { label: m.grupo })));
    const op = el("option", { value: m.alvo }, m.rotulo + (prontos[m.provedor] ? "" : " (sem chave)"));
    if (!prontos[m.provedor]) op.disabled = true;
    grupos[m.grupo].append(op);
  }
  // Modelo da última vez; senão, o melhor recomendado que tenha chave
  const disponivel = (alvo) => MODELOS.some((m) => m.alvo === alvo && prontos[m.provedor]);
  const salvo = lembrar("mesa.modelo");
  const escolhido = disponivel(salvo) ? salvo : (MODELOS.find((m) => m.grupo === "Recomendados" && prontos[m.provedor]) || {}).alvo;
  const atual = MODELOS.find((m) => estado.modelo === rotuloDe(m.alvo));
  if (escolhido && (!atual || atual.alvo !== escolhido)) {
    try {
      Object.assign(estado, await api("/api/modelo", { alvo: escolhido }));
    } catch { /* fica no modelo do servidor */ }
  }
  const agora = MODELOS.find((m) => estado.modelo === rotuloDe(m.alvo)) || MODELOS[0];
  sel.value = agora.alvo;

  const est = $("#estante");
  est.innerHTML = "";
  $("#estante-resumo").textContent = `Os ${estado.artigos.length} documentos do corpus`;
  for (const a of estado.artigos) {
    est.append(el("li", {}, el("button", { type: "button", class: "doc", title: a.titulo, onclick: () => abrirFonte(a.id, 1, null) },
      el("span", { class: "id" }, a.id), el("span", { class: "pags" }, `${a.paginas} p.`))));
  }
  const ex = $("#exemplos");
  ex.innerHTML = "";
  for (const t of EXEMPLOS) ex.append(el("button", { type: "button", class: "exemplo", onclick: () => perguntar(t) }, t));
}
function rotuloDe(alvo) {
  const [prov, ...resto] = alvo.split(":");
  const p = estado.provedores.find((x) => x.nome === prov);
  return `${prov}:${resto.length ? resto.join(":") : p ? p.modelo_padrao : ""}`;
}

// ---------------- pergunta e acompanhamento ----------------
async function perguntar(texto, rotuloCorrecao) {
  texto = (texto || "").trim();
  if (!texto || ocupado) return;
  $("#vazio").hidden = true;
  const rodada = criarRodada(rotuloCorrecao ? null : texto, rotuloCorrecao);
  try {
    definirOcupado(true);
    const { job } = await api("/api/perguntar", { pergunta: texto });
    acompanhar(job, rodada);
  } catch (e) {
    mostrarErro(rodada, e.message);
    definirOcupado(false);
  }
}

function criarRodada(pergunta, correcao) {
  const r = el("article", { class: "rodada" });
  r.termos = [];
  if (pergunta) r.append(el("h2", { class: "pergunta" }, pergunta));
  if (correcao) r.append(el("p", { class: "correcao-pedida" }, `Correção pedida: ${correcao}`));
  r.trilha = el("ol", { class: "trilha", "aria-label": "O que o agente fez" });
  r.inicio = Date.now();
  r.espera = el("div", { class: "espera", "aria-hidden": "true" },
    el("p", { class: "relogio" }, "Respondendo… 0 s"), el("span", { class: "osso" }), el("span", { class: "osso" }), el("span", { class: "osso curto" }));
  r.append(r.trilha, r.espera);
  $("#conversa").append(r);
  r.scrollIntoView({ behavior: "smooth", block: "end" });
  return r;
}

function acompanhar(job, rodada, vistos = 0) {
  setTimeout(async () => {
    let j;
    try {
      j = await api(`/api/job?id=${job}`);
    } catch (e) {
      mostrarErro(rodada, e.message);
      return definirOcupado(false);
    }
    for (const ev of j.eventos.slice(vistos)) mostrarEvento(rodada, ev);
    const relogio = rodada.espera && rodada.espera.querySelector(".relogio");
    if (relogio) relogio.textContent = `Respondendo… ${Math.round((Date.now() - rodada.inicio) / 1000)} s`;
    if (j.estado === "rodando") return acompanhar(job, rodada, j.eventos.length);
    if (rodada.espera) rodada.espera.remove();
    rodada.trilha.querySelectorAll(".agora").forEach((n) => n.remove());
    if (j.estado === "erro") mostrarErro(rodada, j.erro);
    else mostrarResposta(rodada, job, j.resultado);
    definirOcupado(false);
  }, 600);
}

function mostrarEvento(rodada, ev) {
  const t = rodada.trilha;
  t.querySelectorAll(".agora").forEach((n) => n.remove());
  let li;
  if (ev.tipo === "pensando") {
    li = el("li", { class: "agora" }, ev.ciclo === 1 ? "Lendo a pergunta" : "Pensando no que leu");
  } else if (ev.tipo === "trava") {
    li = el("li", { class: "trava" }, "Limite de buscas atingido: respondendo com o que já leu");
  } else if (ev.tipo === "tool") {
    const a = ev.argumentos || {};
    if (ev.nome === "buscar_trechos") {
      rodada.termos.push(...String(a.consulta || "").split(/\s+/).filter((w) => w.length >= 4));
      const consulta = String(a.consulta || "").replace(/["“”']/g, "").trim();
      li = el("li", { html: `Buscou <q>${esc(consulta)}</q> em ${esc(a.artigo || "todos os artigos")}` });
    } else if (ev.nome === "ler_pagina") li = el("li", {}, `Leu ${a.artigo}, p. ${a.pagina}`);
    else if (ev.nome === "carregar_skill") li = el("li", {}, `Abriu a skill ${a.nome}`);
    else if (ev.nome === "listar_artigos") li = el("li", {}, "Consultou a lista de artigos");
    else li = el("li", {}, ev.nome);
  }
  if (li) t.append(li);
}

function mostrarErro(rodada, erro) {
  if (rodada.espera) rodada.espera.remove();
  rodada.append(el("p", { class: "erro", title: erro }, explicarErro(erro)));
}

// ---------------- resposta verificada ----------------
// Etiqueta no topo da resposta: quantas frases com página passaram no verificador
function seloVerificador(itens) {
  const comPagina = itens.filter((i) => i.citacoes.length).length;
  const ok = itens.filter((i) => i.veredito === "rastreável").length;
  if (!comPagina) return el("p", { class: "selo" }, el("span", { class: "chip" }, "Nenhuma frase com página"));
  const classe = ok === comPagina ? "chip-ok" : ok ? "chip-meio" : "chip-erro";
  return el("p", { class: "selo" }, el("span", { class: `chip ${classe}`, title: "O verificador confere se a página foi lida e se os números estão nela. Se o trecho sustenta a frase, quem decide é você." },
    `${ok === comPagina ? "✓ " : ""}${ok} de ${comPagina} frases conferidas pelo verificador`));
}

function mostrarResposta(rodada, job, r) {
  if (rodada.espera) rodada.espera.remove();
  const lista = el("ul", { class: "resposta" });
  for (const linha of r.linhas) lista.append(linhaResposta(linha, rodada));
  rodada.append(seloVerificador(r.itens), lista);

  const n = (v) => r.itens.filter((i) => i.veredito === v).length;
  const comPagina = r.itens.filter((i) => i.citacoes.length).length;
  const pedidos = r.chamadas === 1 ? "1 chamada" : `${r.chamadas} chamadas`;
  const rod = el("div", { class: "rodape-rodada" },
    el("p", { class: "leitura", title: "O verificador confere se a página foi lida e se os números estão nela; se o trecho sustenta a frase, quem decide é você." },
      resumoLeitura(r, n("rastreável"), comPagina)),
    el("p", { class: "medidas" }, `${r.modelo.split(":").slice(1).join(":")} · ${pedidos} · ${r.segundos} s · ${r.tokens.toLocaleString("pt-BR")} tokens`));
  rod.append(barraDecisao(job, rodada));
  rodada.append(rod);
  rodada.scrollIntoView({ behavior: "smooth", block: "end" });
  // Abre logo a primeira página citada que o agente leu, para a conferência começar sem clique
  const primeira = lista.querySelector(".aba:not(.nao-lida)");
  if (primeira) primeira.click();
}

function resumoLeitura(r, ok, comPagina) {
  const lidas = {};
  for (const [a, p] of r.lidas) (lidas[a] ||= []).push(p);
  const txtLidas = Object.entries(lidas).map(([a, ps]) => `${a}, p. ${ps.join(", ")}`).join("; ");
  const base = comPagina ? `Verificador: ${ok} de ${comPagina} frases conferem` : "Nenhuma frase trouxe página";
  return `${base} · páginas lidas: ${txtLidas || "nenhuma"}`;
}

function linhaResposta(linha, rodada) {
  let texto = linha.texto.replace(/^[-*•]\s+/, "");
  const cits = [...texto.matchAll(CITACAO)].map((m) => [m[1], Number(m[2])]);
  const corpo = texto.replace(CITACAO, "").replace(/\s+([.,;:!?])/g, "$1").trim();
  const ehTitulo = !linha.veredito && !cits.length && (/^\*\*.+\*\*:?$/.test(corpo) || /:$/.test(corpo) || /^#+\s/.test(corpo));
  const li = el("li", { class: ehTitulo ? "titulo" : "" });
  const html = esc(corpo.replace(/^#+\s*/, "")).replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
  li.append(el("span", { html }));

  const v = VEREDITOS[linha.veredito];
  if (v) {
    li.prepend(el("span", { class: `marca-margem ${v.classe}`, title: v.dica, "aria-label": `Verificador: ${linha.veredito}. ${v.dica}` }, v.sinal));
    if (["página não lida", "recusa sem página lida", "sem citação"].includes(linha.veredito)) li.classList.add("alerta");
  }
  const numeros = [...corpo.matchAll(NUMERO)].map((m) => m[0]);
  for (const [a, p] of cits) {
    const naoLida = linha.veredito === "página não lida" && linha.detalhe.includes(`${a} p.${p}`);
    const aba = el("button", { type: "button", class: `aba${naoLida ? " nao-lida" : ""}`, title: naoLida ? "O agente não leu esta página" : `Abrir ${a}, página ${p}` },
      `${a.replace(/\d{4}$/, "")} p. ${p}`);
    aba.addEventListener("click", () => abrirFonte(a, p, { numeros, termos: rodada.termos }, aba));
    li.append(" ", aba);
  }
  return li;
}

function barraDecisao(job, rodada) {
  const barra = el("div", { class: "decisao" });
  const decidir = async (decisao, comentario = "") => {
    barra.querySelectorAll("button, input").forEach((b) => (b.disabled = true));
    try {
      const r = await api("/api/decisao", { job, decisao, comentario });
      barra.innerHTML = "";
      if (decisao === "aprovar") {
        const nome = r.arquivo.split(/[\\/]/).slice(-2).join("/");
        barra.append(el("p", { class: "decidido salvo" }, `Salvo em ${nome}`));
        aviso("Fichamento salvo.");
      } else if (decisao === "rejeitar") {
        barra.append(el("p", { class: "decidido rejeitado" }, "Rejeitado. A decisão ficou no log."));
      } else {
        barra.append(el("p", { class: "decidido" }, "Correção enviada ao agente."));
        const nova = criarRodada(null, comentario);
        definirOcupado(true);
        acompanhar(r.job, nova);
      }
    } catch (e) {
      aviso(e.message);
      barra.querySelectorAll("button, input").forEach((b) => (b.disabled = false));
    }
  };
  const corrigir = el("button", { type: "button", class: "botao-secundario" }, "Pedir correção");
  barra.append(
    el("p", { class: "decisao-legenda" }, "Sua decisão: só o que você aprovar vai para os fichamentos. O que decidir fica no histórico."),
    el("button", { type: "button", class: "botao-principal", onclick: () => decidir("aprovar") }, "Aprovar e salvar"),
    corrigir,
    el("button", { type: "button", class: "botao-secundario botao-rejeitar", onclick: () => decidir("rejeitar") }, "Rejeitar"));
  corrigir.addEventListener("click", () => {
    if (barra.querySelector(".correcao")) return;
    const campo = el("input", { type: "text", placeholder: "O que o agente deve corrigir?", "aria-label": "O que o agente deve corrigir" });
    const enviar = el("button", { type: "submit", class: "botao-secundario" }, "Enviar correção");
    const form = el("form", { class: "correcao" }, campo, enviar);
    form.addEventListener("submit", (e) => {
      e.preventDefault();
      if (campo.value.trim()) decidir("corrigir", campo.value.trim());
    });
    barra.append(form);
    campo.focus();
  });
  return barra;
}

// ---------------- histórico (perguntas anteriores, lidas dos logs) ----------------
const DECISOES = {
  aprovar: { rotulo: "Salvo no fichamento", classe: "chip-ok" },
  rejeitar: { rotulo: "Rejeitado", classe: "chip-erro" },
  corrigir: { rotulo: "Correção pedida", classe: "chip-meio" },
  "": { rotulo: "Sem decisão", classe: "" },
};

function dataHora(iso) {
  const d = new Date(iso);
  return isNaN(d) ? iso : d.toLocaleString("pt-BR", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });
}

async function listarHistorico() {
  const h = $("#historico");
  fecharFonte(); // a página aberta era da conversa ou da revisão, não do histórico
  h.innerHTML = "";
  h.append(el("p", { class: "hist-carregando" }, "Carregando…"));
  let conversas;
  try {
    ({ conversas } = await api("/api/historico"));
  } catch (e) {
    h.innerHTML = "";
    return h.append(el("p", { class: "erro" }, `Não consegui ler o histórico: ${e.message}`));
  }
  h.innerHTML = "";
  h.append(el("h2", { class: "hist-titulo" }, "Perguntas anteriores"),
    el("p", { class: "hist-sub" }, `${conversas.length} perguntas feitas na aba Perguntar, da mais recente para a mais antiga. Abrir uma delas só mostra; nada é enviado de novo ao modelo.`));
  if (!conversas.length) return h.append(el("p", { class: "rev-vazio" }, "Nenhuma pergunta ainda."));
  const lista = el("ul", { class: "hist-lista" });
  for (const c of conversas) {
    const d = DECISOES[c.decisao] || DECISOES[""];
    const b = el("button", { type: "button", class: "hist-item" },
      el("span", { class: "hist-meta" }, `${dataHora(c.quando)} · ${c.modelo.split(":").slice(1).join(":")}`),
      el("span", { class: "hist-pergunta" }, (c.correcao ? "Correção: " : "") + c.pergunta),
      el("span", { class: "hist-chips" },
        el("span", { class: `chip ${d.classe}` }, d.rotulo),
        c.resumo ? el("span", { class: "chip" }, c.resumo) : ""));
    b.addEventListener("click", () => abrirHistorico(c.id));
    lista.append(el("li", {}, b));
  }
  h.append(lista);
}

async function abrirHistorico(id) {
  const h = $("#historico");
  let it;
  try {
    it = await api(`/api/historico/item?id=${encodeURIComponent(id)}`);
  } catch (e) {
    return aviso(e.message);
  }
  h.innerHTML = "";
  const voltar = el("button", { type: "button", class: "botao-texto hist-voltar" }, "‹ Todas as perguntas");
  voltar.addEventListener("click", listarHistorico);
  const r = el("article", { class: "rodada" });
  r.termos = [];
  r.append(el("p", { class: "hist-meta" }, `${dataHora(it.quando)} · somente leitura`),
    el("h2", { class: "pergunta" }, (it.correcao ? "Correção: " : "") + it.pergunta));
  const res = it.resultado;
  r.append(seloVerificador(res.itens));
  const lista = el("ul", { class: "resposta" });
  for (const linha of res.linhas) lista.append(linhaResposta(linha, r));
  const n = res.itens.filter((i) => i.veredito === "rastreável").length;
  const comPagina = res.itens.filter((i) => i.citacoes.length).length;
  const d = DECISOES[it.decisao] || DECISOES[""];
  const pedidos = res.chamadas === 1 ? "1 chamada" : `${res.chamadas} chamadas`;
  r.append(lista, el("div", { class: "rodape-rodada" },
    el("p", { class: "leitura" }, resumoLeitura(res, n, comPagina)),
    el("p", { class: "medidas" }, `${res.modelo.split(":").slice(1).join(":")} · ${pedidos} · ${res.segundos} s · ${Number(res.tokens).toLocaleString("pt-BR")} tokens`),
    el("p", { class: "decidido" }, "Sua decisão: ", el("span", { class: `chip ${d.classe}` }, d.rotulo),
      it.comentario ? ` “${it.comentario}”` : "")));
  h.append(voltar, r);
  h.scrollTop = 0;
  const primeira = lista.querySelector(".aba:not(.nao-lida)");
  if (primeira && window.matchMedia("(min-width: 961px)").matches) primeira.click();
}

// ---------------- página-fonte ----------------
async function abrirFonte(artigo, pagina, destaque, aba) {
  try {
    const p = await api(`/api/pagina?artigo=${encodeURIComponent(artigo)}&pagina=${pagina}`);
    if (aba !== undefined) {
      document.querySelectorAll(".aba.ativa").forEach((x) => x.classList.remove("ativa"));
      if (aba) aba.classList.add("ativa");
      fonte.destaque = destaque || { numeros: [], termos: [] };
    }
    Object.assign(fonte, { artigo, pagina, total: p.total });
    const info = estado.artigos.find((a) => a.id === artigo);
    $("#fonte-vazia").hidden = true;
    $("#fonte-cheia").hidden = false;
    $("#fonte").classList.add("aberta");
    $("#fonte-artigo").textContent = `${artigo}, ${info ? info.autores : ""}`;
    $("#fonte-titulo").textContent = info ? info.titulo : "";
    $("#pag-rotulo").textContent = `p. ${pagina} de ${p.total}`;
    $("#pag-ant").disabled = pagina <= 1;
    $("#pag-prox").disabled = pagina >= p.total;
    $("#pdf-externo").href = `/pdf/${artigo}.pdf#page=${pagina}`;
    $("#fonte-texto").innerHTML = grifar(refluir(p.texto), fonte.destaque);
    $("#fonte-texto").scrollTop = 0;
    const marca = $("#fonte-texto mark:not(.termo)") || $("#fonte-texto mark");
    if (marca) marca.scrollIntoView({ block: "center" });
    if (fonte.modo === "pdf") mostrarPdf();
  } catch (e) {
    aviso(e.message);
  }
}

// Junta as linhas quebradas pelo PDF em parágrafos, mantendo as quebras duplas
function refluir(texto) {
  return texto.replace(/-\n(?=[a-z])/g, "").replace(/(?<!\n)\n(?!\n)/g, " ").replace(/[ \t]{2,}/g, " ");
}

function grifar(texto, destaque) {
  const escRe = (s) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  // Trecho literal (pré-conferência): grifa a passagem inteira e mais nada
  if (destaque.trecho) {
    const m = new RegExp(destaque.trecho.split(/\s+/).filter(Boolean).map(escRe).join("\\s+")).exec(texto);
    if (m) return `${esc(texto.slice(0, m.index))}<mark class="trecho">${esc(m[0])}</mark>${esc(texto.slice(m.index + m[0].length))}`;
  }
  let html = esc(texto);
  const nums = new Set();
  for (const n of destaque.numeros || []) {
    if (n.length < 2 && !/[.,]/.test(n)) continue; // dígito solto grifaria a página inteira
    nums.add(n.replace(",", "."));
    nums.add(n.replace(".", ","));
  }
  const termos = [...new Set((destaque.termos || []).map((t) => t.toLowerCase().replace(/[^\p{L}\p{N}-]/gu, "")).filter((t) => t.length >= 4))];
  const partes = [];
  if (nums.size) partes.push(`(?<![\\w.,])(${[...nums].map(escRe).join("|")})(?![\\w]|[.,]\\d)`);
  else partes.push("(?!)()"); // mantém a numeração dos grupos
  if (termos.length) partes.push(`(?<![\\p{L}&])(${termos.map(escRe).join("|")})(?![\\p{L};])`);
  if (!nums.size && !termos.length) return html;
  // Uma passada só, para um grifo nunca cair dentro da tag de outro
  const re = new RegExp(partes.join("|"), "giu");
  return html.replace(re, (m, num) => (num ? `<mark>${m}</mark>` : `<mark class="termo">${m}</mark>`));
}

// PDF.js (web/vendor) desenha a página e uma camada de texto por cima; os números e termos da
// afirmação são grifados nessa camada. Se o PDF.js falhar, cai no visualizador do navegador.
let pdfjs = null;
const pdfDocs = {};
async function carregarPdfjs() {
  if (!pdfjs) {
    pdfjs = await import("/vendor/pdf.min.mjs");
    pdfjs.GlobalWorkerOptions.workerSrc = "/vendor/pdf.worker.min.mjs";
  }
  return pdfjs;
}

async function mostrarPdf() {
  const caixa = $("#fonte-pdfjs");
  const pedido = (fonte.pdfPedido = (fonte.pdfPedido || 0) + 1);
  $("#pdf-externo").href = `/pdf/${fonte.artigo}.pdf#page=${fonte.pagina}`;
  try {
    const lib = await carregarPdfjs();
    pdfDocs[fonte.artigo] ||= lib.getDocument({ url: `/pdf/${fonte.artigo}.pdf`, isEvalSupported: false }).promise;
    const doc = await pdfDocs[fonte.artigo];
    const pagina = await doc.getPage(fonte.pagina);
    if (pedido !== fonte.pdfPedido) return; // o usuário já pediu outra página
    const escala = Math.max(0.5, (caixa.clientWidth - 24) / pagina.getViewport({ scale: 1 }).width);
    const vp = pagina.getViewport({ scale: escala });
    const dpr = window.devicePixelRatio || 1;
    const canvas = el("canvas", { width: String(Math.floor(vp.width * dpr)), height: String(Math.floor(vp.height * dpr)),
      style: `width:${vp.width}px;height:${vp.height}px` });
    const camada = el("div", { class: "textLayer" });
    const folha = el("div", { class: "pdf-folha", style: `width:${vp.width}px;height:${vp.height}px;--scale-factor:${escala}` }, canvas, camada);
    caixa.replaceChildren(folha);
    $("#fonte-pdf").hidden = true;
    caixa.hidden = false;
    await pagina.render({ canvasContext: canvas.getContext("2d"), viewport: vp, transform: dpr !== 1 ? [dpr, 0, 0, dpr, 0, 0] : null }).promise;
    await new lib.TextLayer({ textContentSource: pagina.streamTextContent(), container: camada, viewport: vp }).render();
    const primeiro = grifarPdf(camada, fonte.destaque);
    if (primeiro) primeiro.scrollIntoView({ block: "center" });
    else caixa.scrollTop = 0;
  } catch (e) {
    console.warn("PDF.js falhou; usando o visualizador do navegador.", e);
    caixa.hidden = true;
    const f = $("#fonte-pdf");
    f.hidden = false;
    f.src = "about:blank"; // força recarregar quando só a página muda
    setTimeout(() => (f.src = `/pdf/${fonte.artigo}.pdf#page=${fonte.pagina}&view=FitH`), 30);
  }
}

// Grifa, na camada de texto do PDF, os mesmos números/termos/trecho do modo Texto. Devolve o primeiro grifo.
function grifarPdf(camada, destaque) {
  const spans = [...camada.querySelectorAll("span")].filter((s) => !s.classList.contains("markedContent") && s.textContent.trim());
  const escRe = (s) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  let primeiro = null;
  const marcar = (s, classe) => { s.classList.add(classe); primeiro ||= s; };
  if (destaque && destaque.trecho) {
    // Junta os spans num texto só, acha o trecho e grifa os spans que ele cobre
    let texto = "";
    const faixas = spans.map((s) => { const ini = texto.length; texto += s.textContent + " "; return [ini, texto.length - 1]; });
    const m = new RegExp(destaque.trecho.split(/\s+/).filter(Boolean).map(escRe).join("\\s+"), "i").exec(texto);
    if (m) spans.forEach((s, k) => { if (faixas[k][1] > m.index && faixas[k][0] < m.index + m[0].length) marcar(s, "grifo"); });
    return primeiro;
  }
  const nums = new Set();
  for (const n of (destaque && destaque.numeros) || []) {
    if (n.length < 2 && !/[.,]/.test(n)) continue;
    nums.add(n.replace(",", ".")); nums.add(n.replace(".", ","));
  }
  const termos = [...new Set(((destaque && destaque.termos) || []).map((x) => x.toLowerCase().replace(/[^\p{L}\p{N}-]/gu, "")).filter((x) => x.length >= 4))];
  const reNum = nums.size ? new RegExp(`(?<![\\w.,])(${[...nums].map(escRe).join("|")})(?![\\w]|[.,]\\d)`) : null;
  const reTermo = termos.length ? new RegExp(`(?<![\\p{L}])(${termos.map(escRe).join("|")})(?![\\p{L}])`, "iu") : null;
  for (const s of spans) {
    if (reNum && reNum.test(s.textContent)) marcar(s, "grifo");
    else if (reTermo && reTermo.test(s.textContent)) marcar(s, "grifo-termo");
  }
  // Prefere rolar até um número (o que o verificador conferiu)
  return camada.querySelector(".grifo") || primeiro;
}

function alternarModo(modo) {
  fonte.modo = modo;
  $("#ver-texto").setAttribute("aria-selected", String(modo === "texto"));
  $("#ver-pdf").setAttribute("aria-selected", String(modo === "pdf"));
  guardar("mesa.fonte", modo);
  $("#fonte-texto").hidden = modo !== "texto";
  $("#fonte-pdfjs").hidden = modo !== "pdf";
  $("#fonte-pdf").hidden = true;
  if (modo === "pdf" && fonte.artigo) mostrarPdf();
}

// ---------------- revisão humana da avaliação (aba Revisar) ----------------
// Cada decisão vai para um CSV com data e hora (revisao.py). Nada aqui chama o modelo.
const REV_CLASSE = { "Aprovada": "s-ok", "Confere": "s-ok", "Corrigir": "s-meio", "Parcial": "s-meio", "Rejeitar": "s-ruim", "Não confere": "s-ruim" };
const REV_PEDE_NOTA = new Set(["Corrigir", "Parcial", "Não confere"]);
const CIT_FAIXA = /\[\s*([A-Za-z][A-Za-z\-]*\d{4})\s*,?\s*p(?:ág)?\.?\s*(\d+)(?:\s*[–-]\s*(\d+))?\s*\]/g;
const rev = { carregado: false, dados: null, ordem: [], pos: 0 };

function guardar(chave, valor) { try { localStorage.setItem(chave, valor); } catch { /* sem armazenamento: tudo bem */ } }
function lembrar(chave) { try { return localStorage.getItem(chave); } catch { return null; } }

function trocarModo(modo) {
  for (const m of ["perguntar", "historico", "revisar"]) {
    $(`#aba-${m}`).setAttribute("aria-selected", String(m === modo));
  }
  $("#painel-perguntar").hidden = modo !== "perguntar";
  $("#painel-historico").hidden = modo !== "historico";
  $("#painel-revisao").hidden = modo !== "revisar";
  $("#controles-pergunta").hidden = modo !== "perguntar";
  guardar("mesa.modo", modo);
  if (modo === "historico") listarHistorico();
  if (modo === "revisar" && !rev.carregado) carregarConjuntos();
}

async function carregarConjuntos(manter) {
  try {
    const { conjuntos } = await api("/api/revisao/conjuntos");
    const sel = $("#rev-conjunto");
    sel.innerHTML = "";
    for (const c of conjuntos) sel.append(el("option", { value: c.id }, `${c.rotulo} · ${c.revisadas}/${c.total}`));
    const salvo = manter || lembrar("mesa.conjunto");
    sel.value = conjuntos.some((c) => c.id === salvo) ? salvo : conjuntos[0].id;
    rev.carregado = true;
    await carregarConjunto(sel.value);
  } catch (e) {
    aviso(`Não consegui abrir a revisão: ${e.message}`);
  }
}

async function carregarConjunto(id) {
  rev.dados = await api(`/api/revisao?conjunto=${encodeURIComponent(id)}`);
  guardar("mesa.conjunto", id);
  montarFiltro();
  aplicarFiltro();
  const pend = rev.ordem.findIndex((i) => !statusDe(rev.dados.itens[i]));
  rev.pos = pend >= 0 ? pend : 0;
  desenharRevisao();
}

function statusDe(item) { return (rev.dados.revisoes[item.id] || {}).status || ""; }

function montarFiltro() {
  const f = $("#rev-filtro");
  f.innerHTML = "";
  const ops = [["todas", "Todos"], ["pendentes", "Pendentes"], ...rev.dados.opcoes.map((o) => [`s:${o}`, o])];
  for (const [v, t] of ops) f.append(el("option", { value: v }, t));
  f.value = "todas";
  // Artigo: caixa separada, só no gabarito
  const a = $("#rev-artigo");
  a.innerHTML = "";
  const artigos = rev.dados.tipo !== "negativas" ? [...new Set(rev.dados.itens.map((i) => i.artigo))] : [];
  a.closest("label").hidden = !artigos.length;
  a.append(el("option", { value: "" }, "Todos"));
  for (const art of artigos) a.append(el("option", { value: art }, art));
  a.value = "";
}

function aplicarFiltro() {
  const v = $("#rev-filtro").value;
  const art = $("#rev-artigo").value;
  const atual = rev.ordem[rev.pos];
  rev.ordem = rev.dados.itens.map((_, i) => i).filter((i) => {
    const it = rev.dados.itens[i];
    if (art && it.artigo !== art) return false;
    if (v === "pendentes") return !statusDe(it);
    if (v.startsWith("s:")) return statusDe(it) === v.slice(2);
    return true;
  });
  const k = rev.ordem.indexOf(atual);
  rev.pos = k >= 0 ? k : 0;
}

function desenharRevisao() {
  desenharProgresso();
  desenharCartao();
}

function desenharProgresso() {
  const itens = rev.dados.itens;
  const feitos = itens.filter(statusDe).length;
  const cont = rev.dados.opcoes.map((o) => `${itens.filter((i) => statusDe(i) === o).length} ${o}`).join(" · ");
  const pct = itens.length ? Math.round((100 * feitos) / itens.length) : 0;
  const p = $("#rev-progresso");
  p.innerHTML = "";
  p.append(
    el("p", { html: `<strong>${feitos} de ${itens.length}</strong> revisados${feitos ? ` · ${esc(cont)}` : ""}` }),
    el("div", { class: "rev-barra", role: "progressbar", "aria-valuemin": "0", "aria-valuemax": "100", "aria-valuenow": String(pct), "aria-label": "Progresso da revisão" },
      el("span", { style: `width:${pct}%` })));
}

function irPara(k) {
  if (!rev.ordem.length) return;
  rev.pos = Math.max(0, Math.min(rev.ordem.length - 1, k));
  desenharCartao();
}

function proximaPendente() {
  for (let d = 1; d <= rev.ordem.length; d++) {
    const k = (rev.pos + d) % rev.ordem.length;
    if (!statusDe(rev.dados.itens[rev.ordem[k]])) return irPara(k);
  }
  aviso("Tudo revisado neste conjunto.");
}

// Pré-conferência da IA: sugestão, trecho literal da página e observação. É rascunho:
// a tela deixa isso explícito e nada daqui é gravado como revisão.
function blocoClaude(it) {
  const pc = it.claude;
  const corrigir = pc.sugestao === "Corrigir";
  const chip = el("span", { class: `chip ${corrigir ? "chip-meio" : "chip-ok"}` },
    corrigir ? `sugere corrigir para ${pc.correcao}` : "sugere aprovar");
  const aba = el("button", { type: "button", class: "aba", title: `Abrir ${it.artigo}, página ${pc.pagina}, com o trecho grifado` },
    `${it.artigo.replace(/\d{4}$/, "")} p. ${pc.pagina}`);
  aba.addEventListener("click", () => abrirFonte(it.artigo, pc.pagina, { numeros: [], termos: [], trecho: pc.trecho }, aba));
  const bloco = el("details", { class: "rev-claude" },
    el("summary", {}, "Pré-conferência da IA ", chip),
    el("blockquote", { class: "rev-trecho" }, `“${pc.trecho}” `, aba));
  if (pc.nota) bloco.append(el("p", { class: "rev-claude-nota" }, pc.nota));
  if (corrigir) {
    const usar = el("button", { type: "button", class: "botao-texto" }, `Escrever “${pc.correcao}” na correção`);
    usar.addEventListener("click", () => {
      const nota = $("#rev-nota");
      nota.value = `${pc.correcao} (sugestão da IA, conferida por mim)`;
      nota.focus();
    });
    bloco.append(usar);
  }
  bloco.append(el("p", { class: "rev-claude-aviso" }, "Rascunho: confira o trecho na página ao lado. Só a sua decisão é gravada."));
  return bloco;
}

// Texto com as citações [Id p.N] ou [Id p.N–M] viradas em abas que abrem a página ao lado
function textoComAbas(texto) {
  const frag = document.createDocumentFragment();
  const numeros = [...texto.replace(CIT_FAIXA, "").matchAll(NUMERO)].map((m) => m[0]);
  let fim = 0;
  for (const m of texto.matchAll(CIT_FAIXA)) {
    frag.append(texto.slice(fim, m.index).replace(/\s+$/, " "));
    const [, art, p1, p2] = m;
    const aba = el("button", { type: "button", class: "aba", title: `Abrir ${art}, página ${p1}` },
      `${art.replace(/\d{4}$/, "")} p. ${p1}${p2 ? `–${p2}` : ""}`);
    aba.addEventListener("click", () => abrirFonte(art, Number(p1), { numeros, termos: [] }, aba));
    frag.append(aba);
    fim = m.index + m[0].length;
  }
  frag.append(texto.slice(fim));
  return frag;
}

function desenharCartao() {
  const c = $("#rev-cartao");
  c.innerHTML = "";
  if (!rev.ordem.length) {
    c.append(el("p", { class: "rev-vazio" }, "Nenhum item neste filtro."));
    return;
  }
  const it = rev.dados.itens[rev.ordem[rev.pos]];
  const r = rev.dados.revisoes[it.id] || {};
  const gab = rev.dados.tipo === "gabarito";

  if (gab) {
    c.append(
      el("p", { class: "rev-meta", html: `<span class="rev-id">${esc(it.id)}</span> · ${esc(it.artigo)} · ${esc(it.tipo)} · ${esc(it.posicao)} do documento` }),
      el("h2", { class: "rev-texto" }, it.texto));
    const pags = el("p", { class: "rev-paginas" }, "Página no gabarito:");
    const numeros = [...it.texto.matchAll(NUMERO)].map((m) => m[0]);
    for (const p of it.paginas) {
      const aba = el("button", { type: "button", class: "aba", title: `Abrir ${it.artigo}, página ${p}` }, `${it.artigo.replace(/\d{4}$/, "")} p. ${p}`);
      aba.addEventListener("click", () => abrirFonte(it.artigo, p, { numeros, termos: [] }, aba));
      pags.append(" ", aba);
    }
    c.append(pags);
    if (it.observacao) c.append(el("p", { class: "rev-nota" }, it.observacao));
    if (it.claude) c.append(blocoClaude(it));
    c.append(el("p", { class: "rev-pergunta-guia" }, "A página sustenta a afirmação, do jeito que ela está escrita?"));
  } else if (rev.dados.tipo === "sentido") {
    // Revisão de sentido: a avaliação automática só confere o número da página; aqui vale o conteúdo
    c.append(
      el("p", { class: "rev-meta", html: `<span class="rev-id">${esc(it.id)}</span> · ${esc(it.artigo)} · ${esc(it.tipo)} · ${esc(it.posicao)} do documento` }),
      el("h2", { class: "rev-texto" }, it.texto),
      el("div", { class: "rev-bloco agente" }, el("h3", {}, "Resposta do agente"), el("p", {}, textoComAbas(it.resposta.replace(/^-\s+/, "")))),
      el("p", { class: "rev-pergunta-guia" }, "A página citada sustenta a afirmação? Confira o conteúdo, não só o número da página."));
  } else {
    const modo = it.modo === "corrigir" ? "o certo é corrigir a premissa" : "o certo é recusar";
    c.append(
      el("p", { class: "rev-meta", html: `<span class="rev-id">${esc(it.id)}</span> · ${esc(it.tipo.replace(/_/g, " "))} · ${esc(modo)}` }),
      el("h2", { class: "rev-texto" }, it.pergunta));
    const esperado = el("div", { class: "rev-bloco esperado" }, el("h3", {}, "Resposta esperada"), el("p", {}, textoComAbas(it.esperado)));
    const auto = el("span", { class: `chip ${it.acerto ? "chip-ok" : "chip-erro"}` },
      `Automático: ${it.acerto ? "acerto" : "erro"}${it.marcas.length ? ` (${it.marcas.join(", ")})` : ""}`);
    const agente = el("div", { class: "rev-bloco agente" }, el("h3", {}, "Resposta do agente ", auto));
    for (const linha of it.resposta.split(/\s(?=- )/)) agente.append(el("p", {}, textoComAbas(linha.replace(/^-\s+/, ""))));
    c.append(esperado, agente, el("p", { class: "rev-pergunta-guia" }, "A resposta do agente confere com a esperada?"));
  }

  // Decisão: 1, 2, 3 no teclado
  const grupo = el("div", { class: "rev-decisao", role: "group", "aria-label": "Sua decisão" });
  rev.dados.opcoes.forEach((o, k) => {
    const b = el("button", { type: "button", class: `rev-opcao ${REV_CLASSE[o]}`, "aria-pressed": String(r.status === o) },
      el("kbd", {}, String(k + 1)), o);
    b.addEventListener("click", () => decidirRevisao(r.status === o ? "" : o));
    grupo.append(b);
  });
  const nota = el("textarea", { id: "rev-nota", rows: "2",
    placeholder: gab ? "Correção ou comentário. Se a página certa for outra, escreva p. N (vale na avaliação)." : "Observação: por que é parcial ou não confere",
    "aria-label": "Correção ou comentário" });
  nota.value = r.comentario || (gab ? it.comentario_planilha || "" : "");
  nota.addEventListener("change", () => salvarRevisao(it.id, statusDe(it), nota.value, false));
  const gravado = el("p", { class: "rev-gravado", id: "rev-gravado" }, r.quando ? `Gravado em ${r.quando}` : "");

  const ant = el("button", { type: "button", class: "botao-secundario", onclick: () => irPara(rev.pos - 1) }, "‹ Anterior");
  const prox = el("button", { type: "button", class: "botao-secundario", onclick: () => irPara(rev.pos + 1) }, "Próximo ›");
  ant.disabled = rev.pos === 0;
  prox.disabled = rev.pos >= rev.ordem.length - 1;
  const nav = el("div", { class: "rev-nav" }, ant, el("span", {}, `${rev.pos + 1} de ${rev.ordem.length}`), prox,
    el("button", { type: "button", class: "botao-texto", onclick: proximaPendente }, "Próximo pendente"));

  c.append(grupo, nota, gravado, nav,
    el("p", { class: "rev-dica" }, `Atalhos: ${rev.dados.opcoes.map((o, k) => `${k + 1} ${o}`).join(" · ")} · ← → navegam. Grava em ${rev.dados.arquivo}.`));
  c.scrollTop = 0;

  // Abre a página da fonte para a conferência começar sem clique (em tela larga; no celular
  // a página vira gaveta e cobriria o cartão)
  const primeira = c.querySelector(".rev-paginas .aba") || c.querySelector(".esperado .aba") || c.querySelector(".aba");
  if (!window.matchMedia("(min-width: 961px)").matches) return;
  if (primeira) primeira.click();
  else fecharFonte(); // sem página para conferir: não deixa aberta a página do item anterior
}

async function decidirRevisao(status) {
  const it = rev.dados.itens[rev.ordem[rev.pos]];
  const nota = $("#rev-nota");
  const ok = await salvarRevisao(it.id, status, nota ? nota.value : "", true);
  if (!ok) return;
  if (status && REV_PEDE_NOTA.has(status) && !(nota && nota.value.trim())) {
    nota.focus();
    aviso(status === "Corrigir" ? "Escreva a correção, por exemplo a página certa: p. 2." : "Escreva o motivo na observação: ele vai para o artigo.");
    return;
  }
  if (status) setTimeout(proximaPendente, 220);
}

async function salvarRevisao(id, status, comentario, redesenhar) {
  try {
    const { revisao } = await api("/api/revisao", { conjunto: rev.dados.conjunto, id, status, comentario });
    rev.dados.revisoes[id] = revisao;
    if (redesenhar) desenharRevisao();
    else desenharProgresso();
    const g = $("#rev-gravado");
    if (g) g.textContent = `Gravado em ${revisao.quando}`;
    const op = [...$("#rev-conjunto").options].find((o) => o.value === rev.dados.conjunto);
    if (op) op.textContent = op.textContent.replace(/\d+\/(\d+)$/, `${rev.dados.itens.filter(statusDe).length}/$1`);
    return true;
  } catch (e) {
    aviso(`Não gravou: ${e.message}`);
    return false;
  }
}

function teclasRevisao(e) {
  if ($("#painel-revisao").hidden || !rev.dados) return;
  if (e.target.closest("textarea, input, select") || e.ctrlKey || e.metaKey || e.altKey) return;
  const n = Number(e.key);
  if (n >= 1 && n <= rev.dados.opcoes.length) {
    e.preventDefault();
    const it = rev.dados.itens[rev.ordem[rev.pos]];
    const o = rev.dados.opcoes[n - 1];
    decidirRevisao(statusDe(it) === o ? "" : o);
  } else if (e.key === "ArrowRight") { e.preventDefault(); irPara(rev.pos + 1); }
  else if (e.key === "ArrowLeft") { e.preventDefault(); irPara(rev.pos - 1); }
}

function fecharFonte() {
  $("#fonte-cheia").hidden = true;
  $("#fonte-vazia").hidden = false;
  $("#fonte").classList.remove("aberta");
  document.querySelectorAll(".aba.ativa").forEach((x) => x.classList.remove("ativa"));
}

// ---------------- controles ----------------
function definirOcupado(sim) {
  ocupado = sim;
  $("#enviar").disabled = sim;
  $("#enviar").textContent = sim ? "Respondendo" : "Perguntar";
}

function iniciar() {
  const ta = $("#pergunta");
  const ajustar = () => {
    ta.style.height = "auto";
    ta.style.height = Math.min(ta.scrollHeight, 160) + "px";
    ta.style.overflowY = ta.scrollHeight > 160 ? "auto" : "hidden";
  };
  ta.addEventListener("input", ajustar);
  ta.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); $("#form").requestSubmit(); }
  });
  $("#form").addEventListener("submit", (e) => {
    e.preventDefault();
    const t = ta.value;
    if (!t.trim() || ocupado) return;
    ta.value = "";
    ajustar();
    perguntar(t);
  });
  $("#modelo").addEventListener("change", async (e) => {
    try {
      const r = await api("/api/modelo", { alvo: e.target.value });
      estado = { ...estado, ...r };
      guardar("mesa.modelo", e.target.value);
      aviso(`Agora respondendo com ${e.target.selectedOptions[0].textContent}.`);
    } catch (err) {
      aviso(err.message);
    }
  });
  $("#nova").addEventListener("click", async () => {
    if (ocupado) return aviso("Espere a resposta terminar.");
    await api("/api/limpar", {});
    document.querySelectorAll(".rodada").forEach((r) => r.remove());
    $("#vazio").hidden = false;
    ta.focus();
  });
  $("#pag-ant").addEventListener("click", () => abrirFonte(fonte.artigo, fonte.pagina - 1));
  $("#pag-prox").addEventListener("click", () => abrirFonte(fonte.artigo, fonte.pagina + 1));
  $("#ver-texto").addEventListener("click", () => alternarModo("texto"));
  $("#ver-pdf").addEventListener("click", () => alternarModo("pdf"));
  $("#fechar-fonte").addEventListener("click", fecharFonte);
  $("#aba-perguntar").addEventListener("click", () => trocarModo("perguntar"));
  $("#aba-revisar").addEventListener("click", () => trocarModo("revisar"));
  $("#aba-historico").addEventListener("click", () => trocarModo("historico"));
  $("#rev-conjunto").addEventListener("change", (e) => carregarConjunto(e.target.value).catch((err) => aviso(err.message)));
  $("#rev-filtro").addEventListener("change", () => { aplicarFiltro(); desenharRevisao(); });
  $("#rev-artigo").addEventListener("change", () => { aplicarFiltro(); desenharRevisao(); });
  document.addEventListener("keydown", teclasRevisao);
  alternarModo(lembrar("mesa.fonte") === "texto" ? "texto" : "pdf");
  carregarEstado()
    .then(() => { const m = lembrar("mesa.modo"); if (m === "revisar" || m === "historico") trocarModo(m); })
    .catch((e) => aviso(`Não consegui carregar o agente: ${e.message}`));
  ta.focus();
}

iniciar();
