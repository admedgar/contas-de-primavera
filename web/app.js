/* Contas de Primavera — site estático. Só lê JSON pré-gerado em data/. Valores em centavos. */
"use strict";

const ESTADO = { medida: "pago", ano: null, meta: null, cache: {}, ent: "prefeitura", resumos: {} };
const NOME_ENT = { prefeitura: "da Prefeitura", camara: "da Câmara" };
const PORTAL_NOME = { prefeitura: "Portal da Transparência da Prefeitura", camara: "Portal da Transparência da Câmara" };
const MEDIDAS = { empenhado: "Empenhado", liquidado: "Liquidado", pago: "Pago" };
const K = { empenhado: "e", liquidado: "l", pago: "p" };
const MESES = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"];
const SECOES = [
  ["resumo", "Resumo"], ["receitas", "Receitas (entradas)"], ["mensal", "Mês a mês"], ["secretarias", "Secretarias"], ["funcoes", "Funções e elementos"],
  ["fornecedores", "Fornecedores"], ["empenhos", "Empenhos"], ["licitacoes", "Licitações e contratos"],
  ["receita", "Receita × despesa"], ["folha", "Folha (agregada)"],
];
const BRL = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" });
const BRL0 = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL", maximumFractionDigits: 0 });
const NUM = new Intl.NumberFormat("pt-BR");
const PCT = new Intl.NumberFormat("pt-BR", { style: "percent", maximumFractionDigits: 1 });

const $ = (s, r = document) => r.querySelector(s);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const brl = (c) => BRL.format((c || 0) / 100);
const brl0 = (c) => BRL0.format((c || 0) / 100);
const dataBR = (iso) => (iso ? iso.slice(8, 10) + "/" + iso.slice(5, 7) + "/" + iso.slice(0, 4) : "—");
const dataHoraBR = (isoZ) => isoZ ? new Date(isoZ).toLocaleString("pt-BR", { timeZone: "America/Cuiaba", dateStyle: "short", timeStyle: "short" }) + " (Cuiabá)" : "—";
const norm = (s) => String(s || "").normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();
const soDigitos = (s) => String(s || "").replace(/\D/g, "");

async function carregar(caminho) {
  if (!ESTADO.cache[caminho]) {
    ESTADO.cache[caminho] = fetch("data/" + caminho, { cache: "no-cache" }).then((r) => {
      if (!r.ok) throw new Error("Não foi possível carregar " + caminho + " (HTTP " + r.status + ")");
      return r.json();
    });
  }
  return ESTADO.cache[caminho];
}

/* ---------- Contador (ESTIMATIVA linear) ---------- */
let contadorInfo = null, timer = null;
function iniciaContador(resumo, meta) {
  const ano = Math.max(...Object.keys(resumo.anos).map(Number));
  const c = resumo.anos[ano].contador;
  $("#ct-ano").textContent = ano;
  $("#ct-ent").textContent = ESTADO.ent === "camara" ? "da Câmara" : "da Prefeitura";
  contadorInfo = c;
  desenhaContadorFixo(resumo, ano, meta);
  clearInterval(timer);
  if (c) { tick(); timer = setInterval(tick, 150); }
}
function valorEstimado() {
  const c = contadorInfo, m = c.medidas[ESTADO.medida];
  const decorrido = Math.min((Date.now() - Date.parse(c.coleta_em)) / 1000, 3 * 86400); // não projeta além de 3 dias sem nova coleta
  return m.base + m.centavos_por_segundo * Math.max(decorrido, 0);
}
function tick() { $("#ct-valor").textContent = BRL.format(valorEstimado() / 100); }
function desenhaContadorFixo(resumo, ano, meta) {
  const r = resumo.anos[ano], c = r.contador;
  if (!c) { $("#ct-valor").textContent = brl(r[ESTADO.medida]); $("#ct-nota").textContent = "Totais do exercício, coletados em " + dataHoraBR(r.coleta_empenhos) + "."; return; }
  const total = r[ESTADO.medida], hab = r.habitantes, dias = c.dias_decorridos;
  $("#ct-sr").textContent = `Valor ${MEDIDAS[ESTADO.medida].toLowerCase()} coletado em ${dataHoraBR(c.coleta_em)}: ${brl(total)}. O contador na tela é uma estimativa.`;
  const horasAtraso = (Date.now() - Date.parse(c.coleta_em)) / 3.6e6;
  $("#ct-aviso").textContent = horasAtraso > 72 ? "Atenção: os dados não são atualizados há mais de 3 dias; o contador parou de estimar." : "";
  $("#ct-mini").innerHTML = [
    ["Valor coletado (real)", brl0(total) + " em " + dataBR(c.coleta_em.slice(0, 10))],
    ["Por habitante no ano", hab ? brl(total / hab) : "—"],
    ["Por dia (média do ano)", brl0(total / dias)],
    ["Por habitante por dia", hab ? brl(total / hab / dias) : "—"],
  ].map(([k, v]) => `<div><dt>${k}</dt><dd>${v}</dd></div>`).join("");
  ESTADO.compart = { ent: ESTADO.ent, ano, medida: ESTADO.medida, total, coleta: c.coleta_em, hab, dias };
  const p = meta.populacao[String(ano)];
  $("#ct-nota").innerHTML = `<strong>Estimativa:</strong> o valor sobe em ritmo constante, a média do ano até a última coleta (${dataHoraBR(c.coleta_em)}). O valor real é o "coletado". ` +
    (p ? `População: ${NUM.format(p.habitantes)} hab. (estimativa do <a href="${esc(p.url)}" style="color:#fff">IBGE</a>). ` : "") +
    `<a href="#/metodologia" style="color:#fff">Como é calculado</a>.`;
}

/* ---------- Utilitários de UI ---------- */
function seletorMedida(id = "sel-medida") {
  return `<label>Valor<select id="${id}">${Object.entries(MEDIDAS).map(([k, v]) => `<option value="${k}" ${k === ESTADO.medida ? "selected" : ""}>${v}</option>`).join("")}</select></label>`;
}
function seletorAno(anos) {
  return `<label>Ano<select id="sel-ano">${anos.map((a) => `<option ${a == ESTADO.ano ? "selected" : ""}>${a}</option>`).join("")}</select></label>`;
}
function ligaSeletores(rerender) {
  const m = $("#sel-medida"), a = $("#sel-ano");
  if (m) m.onchange = () => { definirMedida(m.value); rerender(); };
  if (a) a.onchange = () => { ESTADO.ano = Number(a.value); rerender(); };
}
function definirMedida(m) {
  ESTADO.medida = m;
  document.querySelectorAll(".medidas button").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.medida === m)));
  if (ESTADO.resumo) { desenhaContadorFixo(ESTADO.resumo, Math.max(...Object.keys(ESTADO.resumo.anos).map(Number)), ESTADO.meta); if (contadorInfo) tick(); }
}
function tabelaBarras(linhas, { rotulo, valor, extra = [], caption }) {
  const max = Math.max(1, ...linhas.map((l) => Math.abs(valor(l))));
  const total = linhas.reduce((s, l) => s + valor(l), 0) || 1;
  return `<div class="tabela-wrap"><table><caption>${esc(caption)}</caption><thead><tr><th>${esc(rotulo.titulo)}</th><th class="n">${MEDIDAS[ESTADO.medida]}</th><th class="n">% do total</th>${extra.map((e) => `<th class="n">${esc(e.titulo)}</th>`).join("")}</tr></thead><tbody>` +
    linhas.map((l) => `<tr><td>${esc(rotulo.fn(l))}</td><td class="celbarra"><i style="width:${Math.max(0, valor(l)) / max * 100}%"></i><span class="n" style="display:block;text-align:right">${brl(valor(l))}</span></td><td class="n">${PCT.format(valor(l) / total)}</td>${extra.map((e) => `<td class="n">${e.fn(l)}</td>`).join("")}</tr>`).join("") +
    `</tbody></table></div>`;
}
function baixarCSV(nome, cabecalho, linhas) {
  const cel = (v) => { const s = String(v ?? ""); return /[;"\n]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s; };
  const csv = "﻿" + [cabecalho, ...linhas].map((l) => l.map(cel).join(";")).join("\r\n");
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([csv], { type: "text/csv;charset=utf-8" }));
  a.download = nome; document.body.appendChild(a); a.click(); a.remove();
}
const reais = (c) => ((c || 0) / 100).toFixed(2).replace(".", ",");

function grafico(serie, { rotulos, titulo, formatar = brl0, cores = ["var(--barra)"], nomes = [] }) {
  // serie: array de arrays (um array por série), mesmo tamanho de rotulos
  const W = 640, H = 240, mL = 8, mB = 26, mT = 12, n = rotulos.length, ns = serie.length;
  const max = Math.max(1, ...serie.flat());
  const gw = (W - mL * 2) / n, bw = Math.min(34, (gw - 6) / ns);
  let s = `<svg class="grafico" viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(titulo)}"><line class="eixo" x1="${mL}" x2="${W - mL}" y1="${H - mB}" y2="${H - mB}"/>`;
  for (let i = 0; i < n; i++) {
    for (let j = 0; j < ns; j++) {
      const v = Math.max(0, serie[j][i] || 0), h = (v / max) * (H - mB - mT);
      const x = mL + i * gw + (gw - bw * ns) / 2 + j * bw;
      s += `<rect x="${x.toFixed(1)}" y="${(H - mB - h).toFixed(1)}" width="${(bw - 1).toFixed(1)}" height="${h.toFixed(1)}" fill="${cores[j]}" rx="2"><title>${esc(rotulos[i])}${nomes[j] ? " — " + esc(nomes[j]) : ""}: ${formatar(serie[j][i])}</title></rect>`;
    }
    s += `<text x="${(mL + i * gw + gw / 2).toFixed(1)}" y="${H - 8}" text-anchor="middle">${esc(rotulos[i])}</text>`;
  }
  return s + `<text x="${mL}" y="10">${formatar(max)}</text></svg>`;
}
function tabelaApoio(rotulos, colunas) {
  return `<details><summary>Ver os valores do gráfico em tabela</summary><div class="tabela-wrap"><table><thead><tr><th>Mês</th>${colunas.map((c) => `<th class="n">${esc(c.nome)}</th>`).join("")}</tr></thead><tbody>${rotulos.map((r, i) => `<tr><td>${esc(r)}</td>${colunas.map((c) => `<td class="n">${brl(c.v[i])}</td>`).join("")}</tr>`).join("")}</tbody></table></div></details>`;
}
function cabecalhoSecao(titulo, sub) { return `<h2>${esc(titulo)}</h2><p class="sub">${sub}</p>`; }
function fonteLinha(coletaIso, extra = "") {
  return `<p class="sub">Fonte: <a href="${esc(ESTADO.meta.entidades[ESTADO.ent].portal)}" rel="noopener">${PORTAL_NOME[ESTADO.ent]}</a>. Coletado em ${dataHoraBR(coletaIso)}. ${extra}</p>`;
}

/* ---------- Seções da Prefeitura ---------- */
const SEC = {};

SEC.resumo = async (el) => {
  const r = ESTADO.resumo, anos = Object.keys(r.anos).map(Number);
  const a = r.anos[ESTADO.ano], ant = r.anos[ESTADO.ano - 1];
  const parcial = ESTADO.ano === Math.max(...anos);
  el.innerHTML = cabecalhoSecao("Resumo do exercício", "Valores oficiais do exercício, somando todos os empenhos (anulações já descontadas).") +
    `<div class="ferramentas">${seletorAno(anos)}</div>` +
    `<div class="grade">${Object.entries(MEDIDAS).map(([k, nome]) => `<div class="card"><div class="k">${nome}</div><div class="v">${brl0(a[k])}</div><div class="p">${a.habitantes ? brl(a[k] / a.habitantes) + " por habitante" : ""}</div></div>`).join("")}
      <div class="card"><div class="k">Dotação atualizada (orçamento)</div><div class="v">${brl0(a.dotacao_atualizada)}</div><div class="p">${PCT.format(a.empenhado / (a.dotacao_atualizada || 1))} já empenhado</div></div></div>` +
    (parcial ? `<div class="aviso-caixa">Exercício em andamento: último empenho lançado em ${dataBR(a.ultimo)}. Os valores crescem conforme o portal é atualizado.</div>` : "") +
    `<h3>Comparativo entre exercícios</h3><div class="tabela-wrap"><table><caption>Totais por exercício (valores do portal, coletados nesta ferramenta)</caption><thead><tr><th>Ano</th><th class="n">Empenhado</th><th class="n">Liquidado</th><th class="n">Pago</th><th class="n">Dotação atualizada</th><th class="n">Nº de empenhos</th></tr></thead><tbody>` +
    anos.map((y) => `<tr><td>${y}${y === Math.max(...anos) ? " (parcial)" : ""}</td><td class="n">${brl0(r.anos[y].empenhado)}</td><td class="n">${brl0(r.anos[y].liquidado)}</td><td class="n">${brl0(r.anos[y].pago)}</td><td class="n">${brl0(r.anos[y].dotacao_atualizada)}</td><td class="n">${NUM.format(r.anos[y].qtd)}</td></tr>`).join("") +
    `</tbody></table></div>` + fonteLinha(a.coleta_empenhos, "Veja a <a href=\"#/metodologia\">conferência dos totais</a>.");
  ligaSeletores(() => SEC.resumo(el));
};

SEC.mensal = async (el) => {
  const m = (await carregar(`${ESTADO.ent}/mensal.json`)), anos = Object.keys(m).map(Number);
  if (!m[ESTADO.ano]) ESTADO.ano = anos[anos.length - 1];
  const d = m[ESTADO.ano], k = K[ESTADO.medida];
  const mesAtual = ESTADO.ano === new Date().getFullYear() ? new Date().getMonth() + 1 : 13;
  el.innerHTML = cabecalhoSecao("Mês a mês", "Valores do próprio mês (não acumulados). O empenhado é pela data do empenho; liquidado e pago, pela data do lançamento no portal.") +
    `<div class="ferramentas">${seletorAno(Object.keys(m).map(Number))}${seletorMedida()}</div>` +
    (ESTADO.ano === new Date().getFullYear() ? `<div class="aviso-caixa">O mês em andamento está incompleto.</div>` : "") +
    grafico([d.map((x) => x[k])], { rotulos: d.map((x) => MESES[x.mes - 1]), titulo: `${MEDIDAS[ESTADO.medida]} por mês em ${ESTADO.ano}` }) +
    tabelaApoio(d.map((x) => MESES[x.mes - 1] + (x.mes === mesAtual ? " (parcial)" : "")), [{ nome: "Empenhado", v: d.map((x) => x.e) }, { nome: "Liquidado", v: d.map((x) => x.l) }, { nome: "Pago", v: d.map((x) => x.p) }]) +
    fonteLinha(ESTADO.meta.entidades[ESTADO.ent].fontes.find((f) => f.fonte === "mensal")?.coletado_em);
  ligaSeletores(() => SEC.mensal(el));
};

SEC.secretarias = async (el) => {
  const s = await carregar(`${ESTADO.ent}/secretarias.json`), anos = Object.keys(s).map(Number);
  const linhas = [...s[ESTADO.ano]].sort((a, b) => b[K[ESTADO.medida]] - a[K[ESTADO.medida]]);
  el.innerHTML = cabecalhoSecao("Por secretaria", "Órgãos da administração conforme o portal. Ordem: pelo valor selecionado, do maior para o menor (critério único para todos).") +
    `<div class="ferramentas">${seletorAno(anos)}${seletorMedida()}</div>` +
    tabelaBarras(linhas, { rotulo: { titulo: "Secretaria", fn: (l) => l.nome }, valor: (l) => l[K[ESTADO.medida]], caption: `${MEDIDAS[ESTADO.medida]} por secretaria em ${ESTADO.ano}`,
      extra: [{ titulo: "Dotação atualizada", fn: (l) => brl0(l.dot) }, { titulo: "Empenhado / dotação", fn: (l) => PCT.format(l.e / (l.dot || 1)) }] });
  ligaSeletores(() => SEC.secretarias(el));
};

SEC.funcoes = async (el) => {
  const [f, e] = await Promise.all([carregar(`${ESTADO.ent}/funcoes.json`), carregar(`${ESTADO.ent}/elementos.json`)]);
  const anos = Object.keys(f).map(Number), k = K[ESTADO.medida];
  const ord = (L) => [...L].sort((a, b) => b[k] - a[k]);
  el.innerHTML = cabecalhoSecao("Funções e elementos de despesa", "Função = área de governo (ex.: Saúde, Educação). Elemento = natureza do gasto (ex.: pessoal, material de consumo). Veja o glossário em <a href=\"#/entenda\">Entenda</a>.") +
    `<div class="ferramentas">${seletorAno(anos)}${seletorMedida()}</div><h3>Por função</h3>` +
    tabelaBarras(ord(f[ESTADO.ano]), { rotulo: { titulo: "Função", fn: (l) => l.nome }, valor: (l) => l[k], caption: `${MEDIDAS[ESTADO.medida]} por função em ${ESTADO.ano}` }) +
    `<h3>Por elemento de despesa</h3>` +
    tabelaBarras(ord(e[ESTADO.ano]), { rotulo: { titulo: "Elemento", fn: (l) => l.codigo + " – " + l.nome }, valor: (l) => l[k], caption: `${MEDIDAS[ESTADO.medida]} por elemento em ${ESTADO.ano}` });
  ligaSeletores(() => SEC.funcoes(el));
};

function paginar(total, pagina, tam) {
  const n = Math.max(1, Math.ceil(total / tam));
  return { n, p: Math.min(Math.max(1, pagina), n), de: (Math.min(Math.max(1, pagina), n) - 1) * tam };
}

SEC.fornecedores = async (el) => {
  const meta = ESTADO.resumo.anos, anos = Object.keys(meta).map(Number);
  const d = await carregar(`${ESTADO.ent}/fornecedores_${ESTADO.ano}.json`);
  let ordem = "valor", busca = "", pagina = 1, ocultar = true;
  const TAM = 50, k = { empenhado: 3, liquidado: 4, pago: 5 }[ESTADO.medida];
  const pe = ESTADO.resumo.anos[ESTADO.ano].proprio_ente, totAno = ESTADO.resumo.anos[ESTADO.ano][ESTADO.medida];
  const peVal = pe ? pe[K[ESTADO.medida]] : 0;
  el.innerHTML = cabecalhoSecao("Fornecedores", "Quem recebeu, por ano. Pessoas físicas que prestam serviço ou vendem material aparecem com CPF mascarado, como no portal oficial. Pessoas que recebem diárias, auxílios, sentenças, premiações ou reembolsos têm nome, documento e histórico omitidos e entram somadas numa linha única" + (d.pf_omitidas ? ` (${NUM.format(d.pf_omitidas)} pessoas)` : "") + ", sem alterar nenhum total.") +
    `<div class="ferramentas">${seletorAno(anos)}${seletorMedida()}<label>Buscar por nome ou CNPJ<input type="search" id="f-busca" placeholder="ex.: nome ou 12.345.678"></label>
     <label>Ordenar por<select id="f-ordem"><option value="valor">Valor (maior primeiro)</option><option value="nome">Nome (A–Z)</option></select></label>
     <button class="acao" id="f-csv" type="button">Baixar CSV</button></div>` +
    (peVal ? `<div class="aviso-caixa"><label style="flex-direction:row;gap:8px;align-items:center;color:inherit;font-size:inherit"><input type="checkbox" id="f-ocultar" checked> Ocultar empenhos em nome ${ESTADO.ent === "camara" ? "da própria Câmara" : "da própria Prefeitura"}</label>
      <br>Esses empenhos somam <strong>${brl0(peVal)}</strong> (${PCT.format(peVal / (totAno || 1))} do ${MEDIDAS[ESTADO.medida].toLowerCase()} em ${ESTADO.ano}) concentram-se nos elementos de pessoal (vencimentos e benefícios do servidor; o histórico oficial diz “incorporação da folha de pagamento”). Não são compras de terceiros; por isso saem da lista por padrão. Os totais do site <em>incluem</em> esses valores.</div>` : "") +
    `<div id="f-lista"></div>`;
  const desenha = () => {
    const q = norm(busca), qd = soDigitos(busca);
    let L = d.linhas.filter((r) => !(ocultar && r[7]) && (!q || norm(r[0]).includes(q) || (qd.length >= 4 && soDigitos(r[1]).includes(qd))));
    L = ordem === "nome" ? [...L].sort((a, b) => a[0].localeCompare(b[0], "pt-BR")) : [...L].sort((a, b) => b[k] - a[k]);
    const pg = paginar(L.length, pagina, TAM); pagina = pg.p;
    $("#f-lista").innerHTML = `<p class="sub">${NUM.format(L.length)} fornecedores${q ? " encontrados" : ""} · ordem por ${ordem === "nome" ? "nome" : "valor " + MEDIDAS[ESTADO.medida].toLowerCase()}</p>` +
      `<div class="tabela-wrap"><table><caption>Fornecedores em ${ESTADO.ano}</caption><thead><tr><th>Fornecedor</th><th>CNPJ / CPF</th><th class="n">Empenhado</th><th class="n">Liquidado</th><th class="n">Pago</th><th class="n">Empenhos</th></tr></thead><tbody>` +
      (L.slice(pg.de, pg.de + TAM).map((r) => `<tr><td>${esc(r[0])}${r[7] ? ' <span class="etq">em nome do próprio ente</span>' : ""}</td><td>${esc(r[1])}</td><td class="n">${brl(r[3])}</td><td class="n">${brl(r[4])}</td><td class="n">${brl(r[5])}</td><td class="n">${NUM.format(r[6])}</td></tr>`).join("") || `<tr><td colspan="6" class="vazio">Nada encontrado.</td></tr>`) +
      `</tbody></table></div><div class="pag"><button class="acao" id="f-ant" ${pg.p <= 1 ? "disabled" : ""}>← Anterior</button><span>Página ${pg.p} de ${pg.n}</span><button class="acao" id="f-prox" ${pg.p >= pg.n ? "disabled" : ""}>Próxima →</button></div>`;
    $("#f-ant").onclick = () => { pagina--; desenha(); }; $("#f-prox").onclick = () => { pagina++; desenha(); };
    $("#f-csv").onclick = () => baixarCSV(`fornecedores_${ESTADO.ano}.csv`, ["Fornecedor", "CNPJ/CPF", "Empenhado", "Liquidado", "Pago", "Empenhos"], L.map((r) => [r[0], r[1], reais(r[3]), reais(r[4]), reais(r[5]), r[6]]));
  };
  const oc = $("#f-ocultar"); if (oc) oc.onchange = () => { ocultar = oc.checked; pagina = 1; desenha(); };
  $("#f-busca").oninput = (e) => { busca = e.target.value; pagina = 1; desenha(); };
  $("#f-ordem").onchange = (e) => { ordem = e.target.value; pagina = 1; desenha(); };
  ligaSeletores(() => SEC.fornecedores(el));
  desenha();
};

SEC.empenhos = async (el) => {
  const anos = Object.keys(ESTADO.resumo.anos).map(Number), orgaos = ESTADO.resumo.orgaos;
  el.innerHTML = cabecalhoSecao("Empenhos", "Cada linha é um registro do portal: quem, quanto, para quê e quando. <a href=\"#/entenda\">O que é empenho, liquidação e pagamento?</a>") +
    `<p class="carregando">Carregando lista de empenhos…</p>`;
  const d = await carregar(`${ESTADO.ent}/empenhos_${ESTADO.ano}.json`);
  const tipos = [...new Set(d.linhas.map((r) => r[1]))].sort(), elems = [...new Set(d.linhas.map((r) => r[6]))].sort();
  const mods = [...new Set(d.linhas.map((r) => r[12]).filter(Boolean))].sort();
  const F = { q: "", tipo: "", orgao: "", elem: "", mod: "", de: "", ate: "", vmin: "", vmax: "", pagina: 1 };
  const TAM = 50;
  el.innerHTML = cabecalhoSecao("Empenhos", "Cada linha é um registro do portal: quem, quanto, para quê e quando. <a href=\"#/entenda\">O que é empenho, liquidação e pagamento?</a>") +
    `<div class="ferramentas">${seletorAno(anos)}
      <label>Buscar (fornecedor, CNPJ, descrição ou número)<input type="search" id="e-q"></label></div>
     <div class="ferramentas">
      <label>Secretaria<select id="e-orgao"><option value="">Todas</option>${Object.entries(orgaos).map(([c, n]) => `<option value="${c}">${esc(n)}</option>`).join("")}</select></label>
      <label>Tipo<select id="e-tipo"><option value="">Todos</option>${tipos.map((t) => `<option>${t}</option>`).join("")}</select></label>
      <label>Elemento<select id="e-elem"><option value="">Todos</option>${elems.map((t) => `<option>${t}</option>`).join("")}</select></label>
      <label>Contratação<select id="e-mod"><option value="">Todas</option>${mods.map((t) => `<option>${esc(t)}</option>`).join("")}</select></label>
      <label>De<input type="date" id="e-de"></label><label>Até<input type="date" id="e-ate"></label>
      <label>Valor empenhado mín. (R$)<input type="number" id="e-vmin" min="0" step="0.01" inputmode="decimal"></label>
      <label>Valor empenhado máx. (R$)<input type="number" id="e-vmax" min="0" step="0.01" inputmode="decimal"></label>
      <button class="acao" id="e-csv" type="button">Baixar CSV (filtro atual)</button></div><div id="e-lista"></div>`;
  const desenha = () => {
    const q = norm(F.q), qd = soDigitos(F.q);
    const vmin = F.vmin === "" ? null : Math.round(Number(F.vmin) * 100), vmax = F.vmax === "" ? null : Math.round(Number(F.vmax) * 100);
    const L = d.linhas.filter((r) =>
      (!F.tipo || r[1] === F.tipo) && (!F.orgao || r[5] === F.orgao) && (!F.elem || r[6] === F.elem) && (!F.mod || r[12] === F.mod) &&
      (!F.de || r[2] >= F.de) && (!F.ate || r[2] <= F.ate) && (vmin === null || r[8] >= vmin) && (vmax === null || r[8] <= vmax) &&
      (!q || norm(r[3]).includes(q) || norm(r[11]).includes(q) || r[0] === F.q.trim() || (qd.length >= 4 && soDigitos(r[4]).includes(qd))));
    const tot = L.reduce((s, r) => [s[0] + r[8], s[1] + r[9], s[2] + r[10]], [0, 0, 0]);
    const pg = paginar(L.length, F.pagina, TAM); F.pagina = pg.p;
    $("#e-lista").innerHTML = `<p class="sub"><strong>${NUM.format(L.length)}</strong> registros · soma no filtro: empenhado ${brl(tot[0])} · liquidado ${brl(tot[1])} · pago ${brl(tot[2])}</p>` +
      `<div class="tabela-wrap"><table><caption>Empenhos de ${ESTADO.ano}, do mais recente ao mais antigo</caption><thead><tr><th>Data</th><th>Nº</th><th>Fornecedor</th><th>Para quê (histórico oficial)</th><th>Secretaria</th><th class="n">Empenhado</th><th class="n">Liquidado</th><th class="n">Pago</th></tr></thead><tbody>` +
      (L.slice(pg.de, pg.de + TAM).map((r) => `<tr><td>${dataBR(r[2])}</td><td>${esc(r[0])} <span class="etq ${r[1] === "AN" || r[1] === "DA" ? "an" : ""}">${esc(r[1])}</span></td><td>${esc(r[3])}<br><span class="hist">${esc(r[4])}</span></td><td class="hist">${esc(r[11])}${r[12] ? `<br><span class="etq">${esc(r[12])}</span>` : ""}</td><td>${esc(orgaos[r[5]] || r[5])}</td><td class="n">${brl(r[8])}</td><td class="n">${brl(r[9])}</td><td class="n">${brl(r[10])}</td></tr>`).join("") || `<tr><td colspan="8" class="vazio">Nenhum empenho com esses filtros.</td></tr>`) +
      `</tbody></table></div><div class="pag"><button class="acao" id="e-ant" ${pg.p <= 1 ? "disabled" : ""}>← Anterior</button><span>Página ${pg.p} de ${pg.n}</span><button class="acao" id="e-prox" ${pg.p >= pg.n ? "disabled" : ""}>Próxima →</button></div>` +
      `<p class="sub">AN/DA = anulação (valores negativos). Registros de “Pessoa física (nome omitido)” são pagamentos a beneficiários (diárias, auxílios, sentenças, reembolsos…): o valor conta nos totais, mas nome, documento e histórico não são exibidos para proteger a privacidade. Nota fiscal e ordens de pagamento de cada empenho estão no <a href="${esc(ESTADO.meta.entidades[ESTADO.ent].portal)}" rel="noopener">portal oficial</a>.</p>`;
    $("#e-ant").onclick = () => { F.pagina--; desenha(); }; $("#e-prox").onclick = () => { F.pagina++; desenha(); };
    $("#e-csv").onclick = () => baixarCSV(`empenhos_${ESTADO.ano}.csv`, ["Data", "Numero", "Tipo", "Fornecedor", "CNPJ/CPF", "Secretaria", "Elemento", "Funcao", "Empenhado", "Liquidado", "Pago", "Historico", "Contratacao"],
      L.map((r) => [dataBR(r[2]), r[0], r[1], r[3], r[4], orgaos[r[5]] || r[5], r[6], r[7], reais(r[8]), reais(r[9]), reais(r[10]), r[11], r[12]]));
  };
  const liga = (id, campo) => { const x = $(id); x.oninput = x.onchange = () => { F[campo] = x.value; F.pagina = 1; desenha(); }; };
  [["#e-q", "q"], ["#e-orgao", "orgao"], ["#e-tipo", "tipo"], ["#e-elem", "elem"], ["#e-mod", "mod"], ["#e-de", "de"], ["#e-ate", "ate"], ["#e-vmin", "vmin"], ["#e-vmax", "vmax"]].forEach(([i, c]) => liga(i, c));
  ligaSeletores(() => SEC.empenhos(el));
  desenha();
};

SEC.licitacoes = async (el) => {
  const [L, C] = await Promise.all([carregar(`${ESTADO.ent}/licitacoes.json`), carregar(`${ESTADO.ent}/contratos.json`)]);
  const mods = [...new Set(L.linhas.map((r) => r[2]).filter(Boolean))].sort();
  const S = { q: "", mod: "", ano: "", aba: "lic", pagina: 1 }, TAM = 40;
  el.innerHTML = cabecalhoSecao("Licitações e contratos", "Processos de contratação e contratos firmados, como publicados no portal. Dispensas e inexigibilidades são modalidades legais de contratação; aqui são apenas listadas.") +
    `<div class="ferramentas"><label>Mostrar<select id="l-aba"><option value="lic">Licitações e processos</option><option value="con">Contratos</option></select></label>
      <label>Buscar<input type="search" id="l-q" placeholder="objeto, fornecedor ou número"></label>
      <label>Modalidade<select id="l-mod"><option value="">Todas</option>${mods.map((m) => `<option>${esc(m)}</option>`).join("")}</select></label>
      <button class="acao" id="l-csv" type="button">Baixar CSV</button></div><div id="l-lista"></div>`;
  const desenha = () => {
    const q = norm(S.q), qd = soDigitos(S.q);
    let cab, linhas, nome;
    if (S.aba === "lic") {
      linhas = L.linhas.filter((r) => (!S.mod || r[2] === S.mod) && (!q || norm(r[3]).includes(q) || norm(r[1]).includes(q)));
      cab = ["Ano", "Nº", "Modalidade", "Objeto", "Data", "Situação", "Valor"]; nome = "licitacoes";
    } else {
      linhas = C.linhas.filter((r) => (!S.mod || r[4] === S.mod) && (!q || norm(r[3]).includes(q) || norm(r[1]).includes(q) || norm(r[0]).includes(q) || (qd.length >= 4 && soDigitos(r[2]).includes(qd))));
      cab = ["Contrato", "Fornecedor", "CNPJ/CPF", "Objeto", "Modalidade", "Valor", "Assinatura", "Vigência até"]; nome = "contratos";
    }
    const pg = paginar(linhas.length, S.pagina, TAM); S.pagina = pg.p;
    const cel = (r) => S.aba === "lic"
      ? `<td>${r[0]}</td><td>${esc(r[1])}</td><td>${esc(r[2] || "Não informada")}</td><td class="hist">${esc(r[3])}</td><td>${dataBR(r[4])}</td><td>${esc(r[5])}</td><td class="n">${brl(r[6])}</td>`
      : `<td>${esc(r[0])}</td><td>${esc(r[1])}</td><td>${esc(r[2])}</td><td class="hist">${esc(r[3])}</td><td>${esc(r[4])}</td><td class="n">${brl(r[5])}</td><td>${dataBR(r[6])}</td><td>${dataBR(r[8])}</td>`;
    $("#l-lista").innerHTML = `<p class="sub">${NUM.format(linhas.length)} registros</p><div class="tabela-wrap"><table><caption>${S.aba === "lic" ? "Licitações e processos (exercícios " + ESTADO.resumo.anoMin + " em diante)" : "Contratos"}</caption><thead><tr>${cab.map((c, i) => `<th class="${/Valor/.test(c) ? "n" : ""}">${c}</th>`).join("")}</tr></thead><tbody>` +
      (linhas.slice(pg.de, pg.de + TAM).map((r) => `<tr>${cel(r)}</tr>`).join("") || `<tr><td colspan="${cab.length}" class="vazio">Nada encontrado.</td></tr>`) +
      `</tbody></table></div><div class="pag"><button class="acao" id="l-ant" ${pg.p <= 1 ? "disabled" : ""}>← Anterior</button><span>Página ${pg.p} de ${pg.n}</span><button class="acao" id="l-prox" ${pg.p >= pg.n ? "disabled" : ""}>Próxima →</button></div>` +
      fonteLinha(S.aba === "lic" ? L.coleta : C.coleta, S.aba === "lic" ? "Valor: campo \"valor\" informado pelo portal para o processo." : "Valor: valor do contrato informado pelo portal.");
    $("#l-ant").onclick = () => { S.pagina--; desenha(); }; $("#l-prox").onclick = () => { S.pagina++; desenha(); };
    $("#l-csv").onclick = () => baixarCSV(nome + ".csv", cab, linhas.map((r) => S.aba === "lic" ? [r[0], r[1], r[2], r[3], dataBR(r[4]), r[5], reais(r[6])] : [r[0], r[1], r[2], r[3], r[4], reais(r[5]), dataBR(r[6]), dataBR(r[8])]));
  };
  $("#l-aba").onchange = (e) => { S.aba = e.target.value; S.pagina = 1; S.mod = ""; const m = $("#l-mod"); const lista = S.aba === "lic" ? mods : [...new Set(C.linhas.map((r) => r[4]).filter(Boolean))].sort(); m.innerHTML = `<option value="">Todas</option>` + lista.map((x) => `<option>${esc(x)}</option>`).join(""); desenha(); };
  $("#l-q").oninput = (e) => { S.q = e.target.value; S.pagina = 1; desenha(); };
  $("#l-mod").onchange = (e) => { S.mod = e.target.value; S.pagina = 1; desenha(); };
  desenha();
};

SEC.receita = async (el) => {
  const [rec, mensal] = await Promise.all([carregar(`${ESTADO.ent}/receita.json`), carregar(`${ESTADO.ent}/mensal.json`)]);
  const anos = Object.keys(rec).map(Number); if (!rec[ESTADO.ano]) ESTADO.ano = anos[anos.length - 1];
  const r = rec[ESTADO.ano], d = ESTADO.resumo.anos[ESTADO.ano];
  const porMes = {}; r.mensal.forEach((x) => { porMes[x.mes] = (porMes[x.mes] || 0) + x.a; });
  const meses = (mensal[ESTADO.ano] || []).map((x) => x.mes);
  const rv = meses.map((m) => porMes[m] || 0), dp = (mensal[ESTADO.ano] || []).map((x) => x.p), de = (mensal[ESTADO.ano] || []).map((x) => x.e);
  const rot = meses.map((m) => MESES[m - 1]);
  el.innerHTML = cabecalhoSecao("Receita × despesa", "Receita orçamentária líquida arrecadada (receitas correntes + de capital − deduções, como no portal) comparada com a despesa do mesmo período.") +
    `<div class="ferramentas">${seletorAno(anos)}</div>` +
    `<div class="grade"><div class="card"><div class="k">Receita líquida arrecadada</div><div class="v">${brl0(r.liquida)}</div><div class="p">Previsão atualizada: ${brl0(r.previsao_liquida)}</div></div>
      <div class="card"><div class="k">Despesa empenhada</div><div class="v">${brl0(d.empenhado)}</div></div>
      <div class="card"><div class="k">Despesa paga</div><div class="v">${brl0(d.pago)}</div></div>
      <div class="card"><div class="k">Receita líquida − despesa paga</div><div class="v">${brl0(r.liquida - d.pago)}</div><div class="p">Diferença do período, sem considerar saldos de exercícios anteriores.</div></div></div>` +
    `<div class="legenda"><span><i style="background:var(--barra)"></i>Receita líquida arrecadada</span><span><i style="background:var(--barra2)"></i>Despesa paga</span></div>` +
    grafico([rv, dp], { rotulos: rot, titulo: `Receita líquida arrecadada e despesa paga por mês em ${ESTADO.ano}`, cores: ["var(--barra)", "var(--barra2)"], nomes: ["Receita", "Despesa paga"] }) +
    tabelaApoio(rot, [{ nome: "Receita líquida", v: rv }, { nome: "Despesa empenhada", v: de }, { nome: "Despesa paga", v: dp }]) +
    `<h3>Componentes da receita (totais do exercício)</h3><div class="tabela-wrap"><table><caption>Linhas de totalização da receita orçamentária</caption><thead><tr><th>Grupo</th><th class="n">Previsão atualizada</th><th class="n">Arrecadado</th></tr></thead><tbody>` +
    r.topo.map((t) => `<tr><td>${esc(t.nome)}</td><td class="n">${brl0(t.prev)}</td><td class="n">${brl0(t.a)}</td></tr>`).join("") + `</tbody></table></div>` +
    fonteLinha(r.coleta, "As receitas do portal formam uma árvore com códigos repetidos; só as linhas de totalização são somadas (veja Metodologia).");
  ligaSeletores(() => SEC.receita(el));
};

SEC.folha = async (el) => {
  const f = await carregar(`${ESTADO.ent}/folha.json`);
  if (!f) { el.innerHTML = cabecalhoSecao("Folha", "Sem dados coletados."); return; }
  const t = f.total[0];
  const tab = (L, titulo) => `<h3>${titulo}</h3><div class="tabela-wrap"><table><caption>${titulo} — folha de ${f.ref}</caption><thead><tr><th>${titulo.replace("Por ", "")}</th><th class="n">Servidores</th><th class="n">Proventos (total)</th><th class="n">Provento médio</th><th class="n">Líquido (total)</th></tr></thead><tbody>` +
    L.map((x) => `<tr><td>${esc(x.chave)}</td><td class="n">${NUM.format(x.qtd)}</td><td class="n">${brl0(x.proventos)}</td><td class="n">${brl0(x.proventos / x.qtd)}</td><td class="n">${brl0(x.liquido)}</td></tr>`).join("") + `</tbody></table></div>`;
  el.innerHTML = cabecalhoSecao("Folha de pagamento (agregada)", `Folha mensal de ${f.ref}. Por decisão do projeto, <strong>não há nomes</strong> de servidores: só quantidade, total e média por cargo, setor e vínculo.${ESTADO.ent === "camara" ? " A exceção são os vereadores, tratados na seção Vereadores." : ""} Grupos com menos de ${f.k} pessoas são reunidos em “Outros” para não identificar ninguém.`) +
    `<div class="grade"><div class="card"><div class="k">Servidores na folha</div><div class="v">${NUM.format(t.qtd)}</div></div><div class="card"><div class="k">Proventos do mês</div><div class="v">${brl0(t.proventos)}</div></div>
      <div class="card"><div class="k">Descontos</div><div class="v">${brl0(t.descontos)}</div></div><div class="card"><div class="k">Líquido pago</div><div class="v">${brl0(t.liquido)}</div></div></div>` +
    tab(f.vinculo, "Por vínculo") + tab(f.divisao, "Por setor (divisão)") + tab(f.cargo, "Por cargo") + fonteLinha(f.coleta);
};

/* ---------- Páginas ---------- */
const SECOES_CAM = [
  ["resumo", "Resumo e custo"], ["vereadores", "Vereadores"], ["verba", "Verba indenizatória"], ["diarias", "Diárias"],
  ["administrativas", "Despesas administrativas"], ["mensal", "Mês a mês"], ["funcoes", "Funções e elementos"],
  ["fornecedores", "Fornecedores"], ["empenhos", "Empenhos"], ["licitacoes", "Licitações e contratos"], ["folha", "Quadro de pessoal"],
];

async function usaEntidade(ent) {
  ESTADO.ent = ent;
  if (!ESTADO.resumos[ent]) {
    const r = await carregar(`${ent}/resumo.json`);
    r.anoMin = Math.min(...Object.keys(r.anos).map(Number));
    ESTADO.resumos[ent] = r;
  }
  ESTADO.resumo = ESTADO.resumos[ent];
  const anos = ESTADO.meta.entidades[ent].anos;
  if (!ESTADO.ano || !anos.includes(ESTADO.ano)) ESTADO.ano = anos[anos.length - 1];
  iniciaContador(ESTADO.resumo, ESTADO.meta);
  const f = ESTADO.meta.entidades[ent].fontes.find((x) => x.fonte === "despesas_gerais");
  $("#rodape-coleta").textContent = "Dados " + NOME_ENT[ent] + " coletados em " + dataHoraBR(f && f.coletado_em) + ".";
}

async function paginaEntidade(ent, sec, extra) {
  await usaEntidade(ent);
  const lista = ent === "camara" ? SECOES_CAM : SECOES;
  const tabela = ent === "camara" ? Object.assign({}, SEC, SEC_CAM) : Object.assign({}, SEC, SEC_REC);
  const s = lista.find((x) => x[0] === sec) ? sec : "resumo";
  $("#pagina").innerHTML = `<nav class="subnav" aria-label="Seções ${NOME_ENT[ent]}">${lista.map(([k, n]) => `<a href="#/${ent}/${k}" ${k === s ? 'aria-current="true"' : ""}>${n}</a>`).join("")}</nav><section id="secao" aria-live="polite"></section>`;
  try { await tabela[s]($("#secao"), extra); }
  catch (e) { $("#secao").innerHTML = `<div class="aviso-caixa">Não foi possível exibir esta seção: ${esc(e.message)}</div>`; }
}

function paginaEntenda() {
  $("#pagina").innerHTML = cabecalhoSecao("Entenda os termos", "Explicações simples dos termos usados nos portais de transparência.") +
    `<div class="card"><dl>
      <dt><strong>Empenho</strong></dt><dd>É a reserva do dinheiro: o órgão registra que vai gastar um valor com um fornecedor. Ainda não é pagamento.</dd>
      <dt><strong>Liquidação</strong></dt><dd>É a conferência de que o produto foi entregue ou o serviço foi feito, geralmente com nota fiscal. Só depois disso o pagamento pode ocorrer.</dd>
      <dt><strong>Pagamento</strong></dt><dd>É a saída efetiva do dinheiro. “Pago” é o valor que de fato saiu dos cofres.</dd>
      <dt><strong>Dotação</strong></dt><dd>É o valor autorizado no orçamento para cada área. A “dotação atualizada” inclui as alterações feitas durante o ano.</dd>
      <dt><strong>Tipos de empenho</strong></dt><dd><code>OR</code> ordinário (valor conhecido), <code>ES</code> estimativo (valor aproximado, ex.: contas de consumo), <code>GL</code> global, <code>AN</code> anulação (cancela parte ou todo de um empenho; aparece com valor negativo), <code>AD</code> adiantamento de despesa (ex.: viagem) e <code>DA</code> anulação de adiantamento.</dd>
      <dt><strong>Função e elemento de despesa</strong></dt><dd>Função é a área de governo (saúde, educação…). Elemento é a natureza do gasto (pessoal, material de consumo, serviços de terceiros, obras…).</dd>
      <dt><strong>Dispensa e inexigibilidade</strong></dt><dd>São hipóteses previstas em lei em que a contratação ocorre sem licitação tradicional. Aparecem na lista de contratações apenas como informação.</dd>
      <dt><strong>Duodécimo (repasse)</strong></dt><dd>Valor que a Prefeitura transfere todo mês à Câmara para o funcionamento do Legislativo. “Devolução” é o dinheiro que a Câmara devolve à Prefeitura.</dd>
      <dt><strong>Verba indenizatória (Câmara)</strong></dt><dd>Valor mensal pago a cada vereador para ressarcir despesas ligadas ao exercício do mandato, nos termos da lei municipal. O portal de dados informa o <em>valor recebido</em> por vereador; como cada vereador gastou a verba consta em relatórios mensais da Câmara, que ainda não estão neste site.</dd>
      <dt><strong>Diária</strong></dt><dd>Valor pago para cobrir despesas de viagem a serviço (hospedagem, alimentação e locomoção).</dd>
      <dt><strong>Vereador suplente</strong></dt><dd>Pessoa que exerce o mandato quando o titular está afastado. Na folha, aparece com cargo “Vereador suplente”.</dd>
      <dt><strong>Receita bruta, deduções e receita líquida</strong></dt><dd>Receita bruta é tudo que foi arrecadado (receitas correntes e de capital). Deduções são parcelas que não ficam com a Prefeitura, como a contribuição ao Fundeb. Receita líquida = bruta − deduções.</dd>
      <dt><strong>Arrecadação própria e transferências</strong></dt><dd>Arrecadação própria vem de impostos, taxas e outras fontes do próprio município (IPTU, ITBI, ISS, taxas, rendimentos). Transferências são repasses de outros entes: da União (ex.: FPM, SUS, FNDE), dos Estados (ex.: parte do ICMS e do IPVA) e de fundos (ex.: Fundeb).</dd>
      <dt><strong>FPM, cota-parte do ICMS e Fundeb</strong></dt><dd>FPM é o Fundo de Participação dos Municípios, repassado pela União. A cota-parte do ICMS é a fatia do imposto estadual que cabe ao município. O Fundeb é o fundo da educação básica: o município contribui com parte da receita e recebe de volta conforme o número de alunos.</dd>
      <dt><strong>Ingresso extraorçamentário</strong></dt><dd>Dinheiro que passa pelo caixa mas pertence a terceiros (descontos retidos de servidores, tributos retidos, cauções). Não é receita da Prefeitura e não entra nos totais do site.</dd>
      <dt><strong>SICONFI, DCA e RREO</strong></dt><dd>SICONFI é o sistema do Tesouro Nacional onde as prefeituras declaram suas contas. A DCA é a declaração anual; o RREO é o relatório bimestral de execução orçamentária. O site usa esses demonstrativos para comparar a receita entre anos, porque o portal da Prefeitura só informa a receita do ano corrente.</dd></dl></div>`;
}

const CONTA_QTD = /orgaos|sem_|confere|carregad|pendentes|vereador|vinculado/;
async function paginaMetodologia() {
  const meta = ESTADO.meta;
  const rot = { ok: "ok", divergente: "divergente", aviso: "aviso" }, cls = { ok: "ok", divergente: "div", aviso: "av" };
  let html = cabecalhoSecao("Metodologia e fontes", "Como os números são obtidos, conferidos e calculados.");
  for (const ent of ["prefeitura", "camara"]) {
    const e = meta.entidades[ent], val = await carregar(`${ent}/validacao.json`);
    const anos = [...new Set(val.map((v) => v.exercicio))];
    const fmt = (v, x) => (x == null ? "—" : CONTA_QTD.test(v.checagem) ? NUM.format(x) : brl(x));
    html += `<h3>${ent === "prefeitura" ? "Prefeitura" : "Câmara"}: fontes oficiais e última coleta</h3><div class="tabela-wrap"><table><caption>Fontes usadas ${NOME_ENT[ent]}</caption><thead><tr><th>Dado</th><th>Coletado em</th><th class="n">Registros</th></tr></thead><tbody>` +
      e.fontes.map((f) => `<tr><td>${esc(f.rotulo)}${f.url ? `<br><a class="hist" href="${esc(f.url)}" rel="noopener">consulta oficial (JSON)</a>` : ""}</td><td>${dataHoraBR(f.coletado_em)}</td><td class="n">${f.registros == null ? "—" : NUM.format(f.registros)}</td></tr>`).join("") +
      `</tbody></table></div><p class="sub">Portal: <a href="${esc(e.portal)}" rel="noopener">${esc(e.portal)}</a> (sistema Fiorilli SCPI, dados abertos em JSON). O site não consulta o portal a cada visita: usa os dados coletados uma vez por dia.</p>` +
      `<h3>${ent === "prefeitura" ? "Prefeitura" : "Câmara"}: conferência dos totais</h3>` +
      anos.map((a) => `<div class="tabela-wrap" style="margin-bottom:12px"><table><caption>Conferências do exercício ${a} (feitas em ${dataHoraBR(val.find((v) => v.exercicio === a).em)})</caption><thead><tr><th>Checagem</th><th>Resultado</th><th class="n">Esperado</th><th class="n">Obtido</th><th class="n">Diferença</th></tr></thead><tbody>` +
        val.filter((v) => v.exercicio === a).map((v) => `<tr><td>${esc(v.checagem.replace(/_/g, " "))}<br><span class="hist">${esc(v.detalhe)}</span></td><td class="${cls[v.status]}">${rot[v.status]}</td><td class="n">${fmt(v, v.esperado)}</td><td class="n">${fmt(v, v.obtido)}</td><td class="n">${fmt(v, v.diferenca)}</td></tr>`).join("") + `</tbody></table></div>`).join("");
  }
  const vb = await carregar("camara/verba.json");
  let atualizacaoHtml = `<h3>Atualização automática e alertas</h3><ul class="limpo"><li>Os dados são coletados <strong>uma vez por dia</strong>, de madrugada (horário de Cuiabá), para não sobrecarregar o portal. Antes de publicar, o sistema confere os totais; se algo não bater, a atualização é suspensa e o site continua com a última versão conferida.</li>
    <li>Se o portal mudar de formato ou ficar fora do ar, a coleta daquela fonte falha sem apagar o que já havia, e uma faixa de aviso aparece no topo do site.</li>
    <li><a href="#/novidades">Novidades</a> lista registros novos acima de limites de valor, ou contratados por dispensa/inexigibilidade, com os critérios à vista. Não indica irregularidade.</li></ul>`;
  try {
    const st = await carregar("status.json"), si = await carregar("site.json").catch(() => ({}));
    atualizacaoHtml += `<div class="tabela-wrap"><table><caption>Última atualização por fonte (gerado em ${dataHoraBR(st.gerado_em)})</caption><thead><tr><th>Entidade</th><th>Fonte</th><th>Último sucesso</th><th>Situação</th></tr></thead><tbody>` +
      Object.entries(st.entidades).flatMap(([e, v]) => v.fontes.map((f) => `<tr><td>${e === "camara" ? "Câmara" : "Prefeitura"}</td><td>${esc(f.fonte)}</td><td>${dataHoraBR(f.ultimo_ok)}</td><td class="${f.status === "ok" ? "ok" : "div"}">${f.status === "ok" ? "ok" : "falhou na última tentativa"}${f.erro ? `<br><span class="hist">${esc(f.erro)}</span>` : ""}</td></tr>`)).join("") + `</tbody></table></div>`;
    if (si && si.contato) atualizacaoHtml += `<p class="sub">Para apontar um erro ou pedir uma correção: ${esc(si.contato)}.</p>`;
  } catch (e) { /* status.json só existe no site publicado */ }
  html += `<p class="sub">A soma de todos os empenhos coletados é comparada, ao centavo, com os totais que o próprio portal informa por órgão e por fornecedor. “Aviso” indica diferença esperada por horário (o portal é atualizado continuamente) ou pendência de cadastro.</p>` +
    (vb.pendencias_de_vinculo.length ? `<div class="aviso-caixa"><strong>Cadastros aguardando confirmação (Câmara).</strong> ${vb.pendencias_de_vinculo.length === 1 ? "Há 1 cadastro" : "Há " + vb.pendencias_de_vinculo.length + " cadastros"} de favorecido com nome igual ou parecido ao de um vereador, mas que o sistema não vincula sozinho (por exemplo, documento diferente). Valores desses cadastros <strong>não</strong> entram nos totais do vereador até a confirmação: ` +
      vb.pendencias_de_vinculo.map((p) => `${esc(p.cadastro || "")} (${esc(p.nota)}; ${brl(p.valor_pago_93_14)} pagos em verba/reembolso e diárias)`).join("; ") + `.</div>` : "") +
    `<h3>Como os números são calculados</h3><ul class="limpo">
     <li><strong>Empenhado, liquidado e pago</strong>: soma dos campos de mesmo nome em todos os registros de empenho do exercício. Anulações (AN/DA) já vêm com valor negativo no portal e entram na soma como vêm.</li>
     <li><strong>Mês a mês</strong>: consultas mensais do portal. O empenhado é do mês; para secretarias, liquidado e pago do mês são a diferença entre acumulados consecutivos informados pelo portal.</li>
     <li><strong>Contador (estimativa)</strong>: taxa = total do ano na última coleta ÷ segundos desde 1º de janeiro (horário de Cuiabá). O contador soma essa taxa ao valor coletado a partir do momento da coleta e para após 3 dias sem atualização. Não é um dado oficial.</li>
     <li><strong>Por habitante</strong>: total ÷ população estimada do IBGE para o ano (${Object.entries(meta.populacao).map(([a, p]) => `${a}: ${NUM.format(p.habitantes)}`).join("; ")}). <strong>Por dia</strong>: total ÷ dias decorridos do ano até a coleta.</li>
     <li><strong>Receitas (entradas) do portal</strong>: árvore de classificação oficial (categoria → origem → espécie → subespécie → rubrica). Cada nível é conferido contra a soma dos seus filhos; o nível mais detalhado do portal só repete as rubricas divididas por vinculação e não é somado. “Arrecadação própria” = receita bruta − transferências (origens 1700 e 2400). O portal só informa a arrecadação do exercício corrente.</li>
     <li><strong>Receita ano a ano e mesmo período</strong>: vêm do SICONFI (Tesouro Nacional): DCA para anos fechados e RREO para o mesmo bimestre em quatro anos. As linhas do RREO já vêm líquidas do Fundeb e o consolidado inclui o regime próprio de previdência, por isso <strong>não são comparadas nem somadas com o portal</strong>. Variações acima de +100% ou abaixo de −50% recebem um alerta porque podem refletir mudança de classificação contábil. Valores nominais, sem correção pela inflação.</li>
     <li><strong>Receita líquida</strong>: soma das linhas de totalização do portal (receitas correntes + receitas de capital − deduções). A árvore completa tem códigos repetidos e não pode ser somada.</li>
     <li><strong>Folha</strong>: agregados por cargo, setor e vínculo, sem nomes; grupos com menos de 3 servidores ficam em “Outros”. <em>Exceção:</em> os vereadores (cargo que começa com “Vereador”, incluindo suplentes) aparecem com nome, como agentes políticos.</li>
     <li><strong>Custo da Câmara</strong>: despesa da Câmara (empenhado, liquidado ou pago) ÷ população; e ÷ receita corrente arrecadada da Prefeitura no mesmo ano. O repasse (duodécimo) vem da consulta de transferências da Prefeitura, que registra os dois sentidos (repasse e devolução).</li>
     <li><strong>Ficha e comparativo dos vereadores</strong> (mesmos critérios para todos): <em>mês de exercício</em> = mês com proventos na folha; <em>proventos</em> = soma da folha; <em>diárias</em> = valor líquido das diárias pagas ao vereador; <em>verba indenizatória</em> = empenhos do elemento “93 – Indenizações e restituições” cujo histórico cita “verba indenizatória”, pagos ao vereador, por <em>mês do empenho</em> (a data do pagamento não está na consulta usada); <em>reembolsos</em> = demais empenhos do elemento 93 pagos ao vereador. As médias mensais dividem o total pelos meses de exercício. Encargos patronais, auxílios e passagens não entram no comparativo. O comparativo é listado em ordem alfabética.</li>
     <li><strong>Quem é o vereador num pagamento</strong>: o favorecido é ligado ao vereador quando o CPF mascarado e o nome são idênticos (ignorando acentos e espaços) ou por decisão registrada pelos responsáveis do projeto. Casos duvidosos ficam de fora até serem decididos.</li>
     <li><strong>Privacidade de pessoas físicas</strong>: nas listas de empenhos e fornecedores, nome, documento e histórico de pessoas físicas são omitidos quando o pagamento não é compra ou prestação de serviço (diárias, auxílios financeiros, sentenças judiciais, premiações, reembolsos, folha). Isso vale também para quem tem CNPJ de microempreendedor com o próprio nome nesses casos. Os valores continuam somados nos totais. Vereadores identificados seguem nominais. O portal oficial continua sendo a fonte completa.</li>
     <li><strong>Passagens aéreas</strong>: o favorecido é a agência. Só aparecem na ficha quando o histórico oficial cita um único passageiro pelo nome completo do vereador; as demais não são atribuíveis.</li></ul>` +
    atualizacaoHtml + `<h3>Limites dos dados</h3><ul class="limpo"><li>Os dados dependem do que o portal oficial publica e podem sofrer atraso de lançamento. O mês corrente é sempre parcial.</li><li>Nota fiscal, ordens de pagamento e itens de cada empenho não são exibidos aqui; estão no portal oficial.</li><li>CPFs aparecem mascarados, exatamente como na fonte. Dados bancários de fornecedores nunca são coletados.</li><li>O detalhamento de como cada vereador gastou a verba indenizatória não está disponível nos dados abertos e ainda não consta deste site.</li></ul>` +
    `<p class="sub">Gerado em ${dataHoraBR(meta.gerado_em)}. Projeto independente, sem vínculo com a Prefeitura, Câmara ou partidos.</p>`;
  $("#pagina").innerHTML = html;
}

/* ---------- Roteador ---------- */
async function rota() {
  const [, pag = "prefeitura", sec, extra] = (location.hash || "#/prefeitura").split("/");
  document.querySelectorAll(".nav-principal a").forEach((a) => {
    if (a.dataset.pag === pag) a.setAttribute("aria-current", "page"); else a.removeAttribute("aria-current");
  });
  $("#carregando").hidden = true;
  try {
    if (pag === "entenda") paginaEntenda();
    else if (pag === "metodologia") await paginaMetodologia();
    else if (pag === "novidades") await paginaNovidades();
    else await paginaEntidade(pag === "camara" ? "camara" : "prefeitura", sec, extra);
  } catch (e) { $("#pagina").innerHTML = `<div class="aviso-caixa">Erro ao carregar: ${esc(e.message)}</div>`; }
  window.scrollTo({ top: 0 });
}

async function iniciar() {
  try {
    ESTADO.meta = await carregar("meta.json");
  } catch (e) {
    $("#carregando").textContent = "Dados indisponíveis no momento: " + e.message; return;
  }
  document.querySelectorAll(".medidas button").forEach((b) => (b.onclick = () => { definirMedida(b.dataset.medida); const a = $("#sel-medida"); if (a) { a.value = b.dataset.medida; a.onchange(); } }));
  window.addEventListener("hashchange", rota);
  ligaCompartilhar();
  verificaAtraso();
  rota();
}
iniciar();


/* ---------- Compartilhar (cartão gerado no navegador) ---------- */
function textoCompartilhar() {
  const c = ESTADO.compart; if (!c) return "";
  const url = location.origin + location.pathname;
  return `Gasto ${NOME_ENT[c.ent]} de Primavera do Leste em ${c.ano} (${MEDIDAS[c.medida].toLowerCase()}): ${brl0(c.total)} coletados até ${dataBR(c.coleta.slice(0, 10))}, com dados do Portal da Transparência oficial. Projeto independente. ${url}`;
}
function desenhaCartao() {
  const c = ESTADO.compart, W = 1080, H = 1080, cv = document.createElement("canvas"); cv.width = W; cv.height = H;
  const g = cv.getContext("2d"), css = getComputedStyle(document.documentElement);
  g.fillStyle = "#0b5c7a"; g.fillRect(0, 0, W, H); g.fillStyle = "#08465e"; g.fillRect(0, H - 150, W, 150);
  const t = (txt, x, y, tam, cor = "#fff", peso = "600") => { g.fillStyle = cor; g.font = `${peso} ${tam}px system-ui, -apple-system, "Segoe UI", sans-serif`; g.fillText(txt, x, y); };
  const quebra = (txt, x, y, larg, tam, cor, lh) => { g.font = `500 ${tam}px system-ui, sans-serif`; let linha = ""; for (const w of txt.split(" ")) { const tt = linha + w + " "; if (g.measureText(tt).width > larg && linha) { t(linha, x, y, tam, cor, "500"); y += lh; linha = w + " "; } else linha = tt; } t(linha, x, y, tam, cor, "500"); return y; };
  t("Contas de Primavera", 70, 110, 44, "#cde4ee");
  t(`Gasto acumulado ${NOME_ENT[c.ent]} em ${c.ano}`, 70, 220, 54);
  const est = contadorInfo ? valorEstimado() : c.total;
  t(BRL.format(est / 100), 70, 380, 100, "#fff", "800");
  t("ESTIMATIVA · " + MEDIDAS[c.medida].toUpperCase(), 70, 450, 34, "#ffd27a");
  let y = quebra(`Valor real coletado: ${brl0(c.total)} em ${dataBR(c.coleta.slice(0, 10))}.`, 70, 560, 940, 40, "#fff", 52);
  if (c.hab) y = quebra(`Por habitante no ano: ${brl(c.total / c.hab)} · por dia: ${brl0(c.total / c.dias)}.`, 70, y + 70, 940, 40, "#cde4ee", 52);
  quebra("A estimativa sobe em ritmo constante, pela média do ano até a última coleta. Não é dado oficial.", 70, y + 90, 940, 30, "#cde4ee", 40);
  quebra("Dados do Portal da Transparência oficial. Projeto independente, sem vínculo com a Prefeitura, Câmara ou partidos.", 70, H - 95, 940, 26, "#cde4ee", 34);
  t(location.host || "", 70, H - 25, 26, "#fff");
  return cv;
}
async function compartilharCartao() {
  if (!ESTADO.compart) return;
  const cv = desenhaCartao(), blob = await new Promise((r) => cv.toBlob(r, "image/png"));
  const arq = new File([blob], "contas-de-primavera.png", { type: "image/png" });
  try {
    if (navigator.canShare && navigator.canShare({ files: [arq] })) { await navigator.share({ files: [arq], text: textoCompartilhar() }); return; }
  } catch (e) { if (e && e.name === "AbortError") return; }
  const a = document.createElement("a"); a.href = URL.createObjectURL(blob); a.download = arq.name; document.body.appendChild(a); a.click(); a.remove();
}
function ligaCompartilhar() {
  $("#bt-cartao").onclick = compartilharCartao;
  $("#bt-whats").addEventListener("click", (e) => { $("#bt-whats").href = "https://wa.me/?text=" + encodeURIComponent(textoCompartilhar()); });
}

/* ---------- Faixa de atraso ---------- */
async function verificaAtraso() {
  try {
    const st = await carregar("status.json");
    const f = Object.values(st.entidades).flatMap((e) => e.fontes).filter((x) => x.fonte === "despesas_gerais" && x.ultimo_ok);
    if (!f.length) return;
    const horas = (Date.now() - Math.min(...f.map((x) => Date.parse(x.ultimo_ok)))) / 3.6e6;
    const falhas = Object.values(st.entidades).flatMap((e) => e.fontes).filter((x) => x.status === "erro");
    const el = $("#faixa-atraso");
    if (horas > 48) { el.hidden = false; el.textContent = `Atenção: os dados não são atualizados há ${Math.floor(horas / 24)} dias. Os valores mostrados são os da última coleta (${dataHoraBR(new Date(Date.now() - horas * 3.6e6).toISOString())}).`; }
    else if (falhas.length) { el.hidden = false; el.textContent = `Algumas fontes falharam na última atualização (${falhas.map((x) => x.fonte).join(", ")}); essas partes mostram a coleta anterior. Veja Metodologia.`; }
  } catch (e) { /* status.json só existe no site publicado (build); localmente é ignorado */ }
}

/* ---------- Novidades (alertas) ---------- */
async function paginaNovidades() {
  const A = await carregar("alertas.json"), meta = ESTADO.meta, cr = A.criterios;
  const F = { ent: "", motivo: "" };
  const lim = (o) => Object.entries(o).map(([e, v]) => `${e === "camara" ? "Câmara" : "Prefeitura"}: ${BRL0.format(v)}`).join(" · ");
  $("#pagina").innerHTML = cabecalhoSecao("Novidades: novos registros", "Registros que apareceram no portal oficial e passam de limites objetivos de valor ou são contratações por dispensa ou inexigibilidade. <strong>Um aviso não indica irregularidade:</strong> é só um registro novo que atende ao critério.") +
    `<div class="card"><p><strong>Critérios (configuráveis).</strong> Empenho novo a partir de: ${lim(cr.empenho_valor_minimo)}. Dispensa ou inexigibilidade a partir de: ${lim(cr.dispensa_valor_minimo)}. Contrato novo a partir de: ${lim(cr.contrato_valor_minimo)}. Só entram registros dos últimos ${cr.janela_dias} dias; empenhos de folha em nome do próprio ente e anulações ficam de fora.</p>
      <p><a href="data/alertas.xml">Assinar por feed (Atom)</a> · Atualizado em ${dataHoraBR(A.gerado_em)}</p></div>
     <div class="ferramentas"><label>Entidade<select id="n-ent"><option value="">Todas</option><option value="prefeitura">Prefeitura</option><option value="camara">Câmara</option></select></label>
      <label>Critério<select id="n-mot"><option value="">Todos</option><option value="valor_alto">Valor acima do limite</option><option value="dispensa">Dispensa</option><option value="inexigibilidade">Inexigibilidade</option></select></label></div><div id="n-lista"></div>`;
  const ROT = { valor_alto: "valor", dispensa: "dispensa", inexigibilidade: "inexigibilidade" };
  const desenha = () => {
    const L = A.itens.filter((i) => (!F.ent || i.entidade === F.ent) && (!F.motivo || i.motivos.includes(F.motivo)));
    $("#n-lista").innerHTML = `<p class="sub">${NUM.format(L.length)} registros</p><div class="tabela-wrap"><table><caption>Novos registros que atendem aos critérios, do mais recente ao mais antigo</caption><thead><tr><th>Registro</th><th>Entidade</th><th>Tipo</th><th>Favorecido</th><th>Secretaria</th><th class="n">Valor</th><th>Critério</th></tr></thead><tbody>` +
      (L.map((i) => `<tr class="alerta-linha"><td>${dataBR(i.data_registro)}<br><span class="hist">visto em ${dataBR(i.criado_em.slice(0, 10))}</span></td><td>${i.entidade === "camara" ? "Câmara" : "Prefeitura"}</td><td>${i.tipo === "contrato" ? "contrato" : "empenho"}</td><td>${esc(i.fornecedor || "—")}<br><span class="hist">${esc(i.descricao || "")}</span></td><td class="hist">${esc(i.secretaria || "")}</td><td class="n">${brl(i.valor)}</td><td>${i.motivos.map((m) => `<span class="etq motivo">${ROT[m] || m}</span>`).join(" ")}</td></tr>`).join("") ||
        `<tr><td colspan="7" class="vazio">Nenhum registro novo que atenda aos critérios${A.itens.length ? " com esse filtro" : " até agora"}. Os avisos começam a aparecer a partir da segunda atualização diária.</td></tr>`) + `</tbody></table></div>` +
      `<p class="sub">Fonte: <a href="${esc(meta.entidades.prefeitura.portal)}" rel="noopener">Portal da Transparência</a>. “Visto em” é a data em que esta ferramenta coletou o registro, que pode ser posterior à data de registro no portal.</p>`;
  };
  $("#n-ent").onchange = (e) => { F.ent = e.target.value; desenha(); };
  $("#n-mot").onchange = (e) => { F.motivo = e.target.value; desenha(); };
  desenha();
}
