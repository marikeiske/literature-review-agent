// Tela de entrada do acesso pelo celular (só existe no servidor do Tailscale; ver seguranca.py)
document.getElementById("form-entrar").addEventListener("submit", async (e) => {
  e.preventDefault();
  const erro = document.getElementById("entrar-erro");
  const botao = e.target.querySelector("button");
  erro.textContent = "";
  botao.disabled = true;
  try {
    const r = await fetch("/api/entrar", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ codigo: document.getElementById("codigo").value }),
    });
    if (r.ok) { location.replace("/"); return; }
    const j = await r.json().catch(() => ({}));
    erro.textContent = j.erro || `Erro ${r.status}`;
  } catch {
    erro.textContent = "Não consegui falar com o notebook. O Tailscale está ligado nos dois?";
  } finally {
    botao.disabled = false;
  }
});
