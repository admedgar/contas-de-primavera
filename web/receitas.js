/* Seção "Receitas (entradas)" da Prefeitura. Usa funções de app.js (só chamadas depois da inicialização).
   Regra de ouro: portal e SICONFI nunca são somados nem comparados entre si (perímetro e convenção diferentes). */
"use strict";

const SEC_REC = {};
const REC = { vista: "origem", filtro: "todas", nivel: 3, mesAte: null, no: "", dcaNivel: 4 };
const NOMES_NIVEL = { 2: "Origens", 3: "Espécies", 4: "Subespécies", 7: "Rubricas" };
const NOMES_NIVEL_DCA = { 2: "Origens", 3: "Espécies", 4: "Subespécies", 5: "Rubricas", 6: "Alíneas" };

const somaPeriodo = (n, k) => n.m.slice(0, k).reduce((s, v) => s + v, 0);
const varPct = (novo, velho) => (velho ? (novo - velho) / Math.abs(velho) : null);
const fmtVar = (v) => (v == null ? "—" : (v >= 0 ? "+" : "−") + PCT.format(Math.abs(v)));
const marcaVar = (v) => (v != null && (v > 1 || v < -0.5) ? ` <span class="etq" title="Variação acima de +100% ou abaixo de −50%: pode refletir mudança de classificação contábil nas declarações, não só de arrecadação. Confira o demonstrativo oficial.">⚠ confira</span>` : "");

const chaveNo = (c, o) => c + "|" + o;      // um nó pode ter o mesmo código do pai (deduções): a identidade é (código, nível)
function ancestral2(n, porCodigo) {
  let x = n, guarda = 0;
  while (x && x.o > 2 && guarda++ < 10) x = porCodigo.get(chaveNo(x.p, x.po));
  return x;
}
function nosPortal(d) {
  const porCodigo = new Map(d.nos.map((n) => [chaveNo(n.c, n.o), n]));
  d.nos.forEach((n) => { const a = n.o === 1 ? n : ancestral2(n, porCodigo); n.raiz2 = a && a.o === 2 ? a.c.slice(0, 4) : n.c.slice(0, 4); });
  return porCodigo;
}
function grupoDe(n) {
  if (n.c.startsWith("9")) return "deducoes";
  const r = n.raiz2 || n.c.slice(0, 4);
  return r === "1700" || r === "2400" ? "transferencias" : "propria";
}

SEC_REC.receitas = async (el) => {
  const D = await carregar("prefeitura/receitas.json");
  const abas = [["origem", "De onde vem (" + (D.portal ? D.portal.ano : "") + ")"], ["anoaano", "Ano a ano"], ["mesmo", "Mesmo período"], ["outras", "Outras entradas"]];
  el.innerHTML = cabecalhoSecao("Receitas: o que entra", "Quanto entra nos cofres da Prefeitura e de onde vem, com comparativos. As três primeiras visões usam fontes oficiais diferentes, que <strong>não são somadas nem comparadas entre si</strong>: cada uma explica seu perímetro.") +
    `<div class="subnav" role="tablist" aria-label="Visões de receita">${abas.map(([k, n]) => `<a href="#" role="tab" data-v="${k}" aria-current="${REC.vista === k}">${n}</a>`).join("")}</div><div id="rec-vista"></div>`;
  const desenha = () => {
    el.querySelectorAll("[data-v]").forEach((a) => a.setAttribute("aria-current", String(a.dataset.v === REC.vista)));
    const v = $("#rec-vista");
    ({ origem: vistaOrigem, anoaano: vistaAnoAno, mesmo: vistaMesmo, outras: vistaOutras })[REC.vista](v, D, desenha);
  };
  el.querySelectorAll("[data-v]").forEach((a) => (a.onclick = (e) => { e.preventDefault(); REC.vista = a.dataset.v; desenha(); }));
  desenha();
};

/* ---------- 1) Portal: de onde vem o dinheiro neste ano ---------- */
function vistaOrigem(v, D, redesenha) {
  const P = D.portal;
  if (!P) { v.innerHTML = `<div class="aviso-caixa">Sem receita do exercício corrente coletada.</div>`; return; }
  const porCodigo = nosPortal(P);
  const maxMes = Math.max(...P.meses_com_dados);
  const completoAte = Math.min(maxMes, P.mes_corrente > maxMes ? maxMes : Math.max(P.mes_corrente - 1, 1));
  if (!REC.mesAte || REC.mesAte > maxMes) REC.mesAte = completoAte;
  const k = REC.mesAte;
  const cat = P.nos.filter((n) => n.o === 1);
  const sp = (pred) => P.nos.filter(pred).reduce((s, n) => s + somaPeriodo(n, k), 0);
  const bruta = cat.filter((n) => !n.c.startsWith("9")).reduce((s, n) => s + somaPeriodo(n, k), 0);
  const ded = cat.filter((n) => n.c.startsWith("9")).reduce((s, n) => s + somaPeriodo(n, k), 0);
  const transf = P.nos.filter((n) => n.o === 2 && (n.c.startsWith("1700") || n.c.startsWith("2400"))).reduce((s, n) => s + somaPeriodo(n, k), 0);
  const propria = bruta - transf;
  const esferas = {};
  P.nos.filter((n) => n.o === 3 && (n.raiz2 === "1700" || n.raiz2 === "2400")).forEach((n) => { esferas[n.n] = (esferas[n.n] || 0) + somaPeriodo(n, k); });
  const lista = P.nos.filter((n) => {
    const nivelOk = n.o === Number(REC.nivel) || (REC.nivel === "1" && n.o === 1);
    const g = grupoDe(n);
    return nivelOk && (REC.filtro === "todas" || g === REC.filtro) && (!REC.no || n.c.startsWith(REC.no.slice(0, 4)) || n.n.toLowerCase().includes(REC.no.toLowerCase()));
  });
  const totBruto = bruta || 1;
  const mesesOpc = P.meses_com_dados.map((m) => `<option value="${m}" ${m === k ? "selected" : ""}>${MESES[m - 1]}${m === P.mes_corrente && P.ano === new Date().getFullYear() ? " (mês em andamento)" : ""}</option>`).join("");
  const serie = (pred) => P.nos.filter(pred).reduce((acc, n) => acc.map((x, i) => x + n.m[i]), Array(12).fill(0));
  const brutaMensal = serie((n) => n.o === 1 && !n.c.startsWith("9")).slice(0, maxMes);
  v.innerHTML = `<p class="sub">${esc(D.contexto.portal)} Valores de ${P.ano} em reais (nominais). Atualizado em ${dataHoraBR(P.coleta)}.</p>` +
    `<div class="ferramentas"><label>Período: janeiro até<select id="r-mes">${mesesOpc}</select></label>
      <label>Mostrar<select id="r-filtro"><option value="todas">Todas as receitas</option><option value="propria">Arrecadação própria</option><option value="transferencias">Transferências recebidas</option><option value="deducoes">Deduções (Fundeb e outras)</option></select></label>
      <label>Nível de detalhe<select id="r-nivel"><option value="1">Categorias</option>${Object.entries(NOMES_NIVEL).map(([o, n]) => `<option value="${o}">${n}</option>`).join("")}</select></label>
      <label>Buscar<input type="search" id="r-busca" placeholder="ex.: IPTU, FPM, ICMS"></label><button class="acao" id="r-csv" type="button">Baixar CSV</button></div>` +
    (k === P.mes_corrente && P.ano === new Date().getFullYear() ? `<div class="aviso-caixa">O mês em andamento está incompleto; os valores do período não são comparáveis a meses fechados.</div>` : "") +
    `<div class="grade"><div class="card"><div class="k">Receita bruta (jan–${MESES[k - 1]})</div><div class="v">${brl0(bruta)}</div><div class="p">correntes + capital, como no portal</div></div>
      <div class="card"><div class="k">Deduções</div><div class="v">${brl0(ded)}</div><div class="p">parcela destinada ao Fundeb e outras</div></div>
      <div class="card"><div class="k">Receita líquida</div><div class="v">${brl0(bruta + ded)}</div></div>
      <div class="card"><div class="k">Arrecadação própria</div><div class="v">${brl0(propria)}</div><div class="p">${PCT.format(propria / totBruto)} da receita bruta</div></div>
      <div class="card"><div class="k">Transferências recebidas</div><div class="v">${brl0(transf)}</div><div class="p">${PCT.format(transf / totBruto)} da receita bruta</div></div></div>` +
    `<h3>Transferências por origem (jan–${MESES[k - 1]})</h3><div class="tabela-wrap"><table><caption>Transferências correntes e de capital por esfera de origem</caption><thead><tr><th>Origem</th><th class="n">Arrecadado</th><th class="n">% das transferências</th></tr></thead><tbody>` +
    Object.entries(esferas).sort((a, b) => b[1] - a[1]).map(([n, val]) => `<tr><td>${esc(n)}</td><td class="n">${brl(val)}</td><td class="n">${PCT.format(val / (transf || 1))}</td></tr>`).join("") + `</tbody></table></div>` +
    `<h3>Mês a mês: receita bruta de ${P.ano}</h3>` +
    grafico([brutaMensal], { rotulos: P.meses_com_dados.map((m) => MESES[m - 1]), titulo: `Receita bruta arrecadada por mês em ${P.ano}` }) +
    tabelaApoio(P.meses_com_dados.map((m) => MESES[m - 1]), [{ nome: "Receita bruta", v: brutaMensal }]) +
    `<h3>Detalhe por classificação</h3><p class="sub">${NUM.format(lista.length)} linhas. Ordem pelo código oficial da receita (não por valor).</p>` +
    `<div class="tabela-wrap"><table><caption>Receita arrecadada em ${P.ano} por classificação, jan–${MESES[k - 1]}</caption><thead><tr><th>Código</th><th>Descrição</th><th class="n">Arrecadado no período</th><th class="n">% da receita bruta</th><th class="n">Arrecadado no ano</th><th class="n">Previsão atualizada do ano</th><th class="n">Arrecadado ÷ previsão</th></tr></thead><tbody>` +
    (lista.map((n) => { const per = somaPeriodo(n, k); return `<tr><td class="hist">${esc(n.c.slice(0, 13))}</td><td>${esc(n.n)}</td><td class="n">${brl(per)}</td><td class="n">${n.c.startsWith("9") ? "—" : PCT.format(per / totBruto)}</td><td class="n">${brl(n.arr)}</td><td class="n">${n.prev ? brl(n.prev) : "—"}</td><td class="n">${n.prev ? PCT.format(n.arr / n.prev) : "—"}</td></tr>`; }).join("") || `<tr><td colspan="7" class="vazio">Nada encontrado.</td></tr>`) +
    `</tbody></table></div><p class="sub">“Arrecadado no ano” e “previsão” referem-se ao ano inteiro até a coleta. Receitas negativas são deduções. Fonte: <a href="${esc(ESTADO.meta.entidades.prefeitura.portal)}" rel="noopener">Portal da Transparência</a>.</p>`;
  $("#r-filtro").value = REC.filtro; $("#r-nivel").value = String(REC.nivel); $("#r-busca").value = REC.no;
  $("#r-mes").onchange = (e) => { REC.mesAte = Number(e.target.value); redesenha(); };
  $("#r-filtro").onchange = (e) => { REC.filtro = e.target.value; redesenha(); };
  $("#r-nivel").onchange = (e) => { REC.nivel = e.target.value; redesenha(); };
  $("#r-busca").onchange = (e) => { REC.no = e.target.value; redesenha(); };
  $("#r-csv").onclick = () => baixarCSV(`receitas_${P.ano}_ate_${MESES[k - 1]}.csv`, ["Codigo", "Descricao", "Arrecadado no periodo", "Arrecadado no ano", "Previsao atualizada"], lista.map((n) => [n.c, n.n, reais(somaPeriodo(n, k)), reais(n.arr), reais(n.prev)]));
}

/* ---------- 2) SICONFI/DCA: ano a ano ---------- */
function vistaAnoAno(v, D, redesenha) {
  const A = D.dca;
  if (!A) { v.innerHTML = `<div class="aviso-caixa">Dados do SICONFI ainda não coletados.</div>`; return; }
  const anos = A.anos, ult = anos[anos.length - 1], pen = anos[anos.length - 2];
  const T = (a) => A.totais[String(a)];
  const nivel = Number(REC.dcaNivel);
  const linhas = A.contas.filter((c) => c.o <= nivel && c.o >= 2);
  const celulas = (c) => anos.map((a) => `<td class="n">${c.v[String(a)] != null ? brl0(c.v[String(a)]) : "—"}</td>`).join("");
  v.innerHTML = `<div class="aviso-caixa"><strong>Fonte: SICONFI (Tesouro Nacional).</strong> ${esc(D.contexto.siconfi)} Valores nominais, sem correção pela inflação.</div>` +
    `<div class="grade">${anos.map((a) => `<div class="card"><div class="k">Receita líquida ${a}</div><div class="v">${brl0(T(a).liquida)}</div><div class="p">${a === anos[0] ? "" : "vs " + (a - 1) + ": " + fmtVar(varPct(T(a).liquida, T(a - 1).liquida))}</div></div>`).join("")}</div>` +
    `<div class="tabela-wrap"><table><caption>Receita realizada (exceto intra-orçamentárias) — DCA, anexo I-C</caption><thead><tr><th>Item</th>${anos.map((a) => `<th class="n">${a}</th>`).join("")}<th class="n">Variação ${ult} × ${pen}</th></tr></thead><tbody>` +
    [["Receita bruta realizada", "bruta"], ["(−) Dedução do Fundeb", "fundeb"], ["(−) Outras deduções da receita", "outras"], ["Receita líquida", "liquida"]].map(([n, k]) => `<tr><td>${n}</td>${anos.map((a) => `<td class="n">${brl0(T(a)[k])}</td>`).join("")}<td class="n">${fmtVar(varPct(T(ult)[k], T(pen)[k]))}</td></tr>`).join("") + `</tbody></table></div>` +
    `<h3>Receita bruta por classificação</h3><div class="ferramentas"><label>Nível de detalhe<select id="d-nivel">${Object.entries(NOMES_NIVEL_DCA).map(([o, n]) => `<option value="${o}">${n}</option>`).join("")}</select></label><button class="acao" id="d-csv" type="button">Baixar CSV</button></div>` +
    `<div class="tabela-wrap"><table><caption>Receita bruta realizada por classificação, ${anos[0]}–${ult} (SICONFI/DCA)</caption><thead><tr><th>Classificação</th>${anos.map((a) => `<th class="n">${a}</th>`).join("")}<th class="n">Variação ${ult} × ${pen}</th></tr></thead><tbody>` +
    linhas.map((c) => { const vr = varPct(c.v[String(ult)] || 0, c.v[String(pen)] || 0); return `<tr><td style="padding-left:${(c.o - 2) * 14 + 10}px">${esc(c.n)}<br><span class="hist">${esc(c.c.slice(2))}</span></td>${celulas(c)}<td class="n">${fmtVar(vr)}${marcaVar(vr)}</td></tr>`; }).join("") + `</tbody></table></div>` +
    `<p class="sub">Coletado em ${dataHoraBR(D.coletas.siconfi_dca[0])}. Fonte: <a href="https://apidatalake.tesouro.gov.br/docs/siconfi/" rel="noopener">SICONFI – Tesouro Nacional (dados abertos)</a>, Declaração de Contas Anuais.</p>`;
  $("#d-nivel").value = String(nivel);
  $("#d-nivel").onchange = (e) => { REC.dcaNivel = e.target.value; redesenha(); };
  $("#d-csv").onclick = () => baixarCSV("receita_bruta_siconfi_dca.csv", ["Codigo", "Classificacao", ...anos.map(String)], linhas.map((c) => [c.c.slice(2), c.n, ...anos.map((a) => (c.v[String(a)] != null ? reais(c.v[String(a)]) : ""))]));
}

/* ---------- 3) SICONFI/RREO: mesmo período ---------- */
function vistaMesmo(v, D) {
  const R = D.rreo;
  if (!R) { v.innerHTML = `<div class="aviso-caixa">Dados do SICONFI ainda não coletados.</div>`; return; }
  const anos = R.anos, ult = String(anos[anos.length - 1]), pen = String(anos[anos.length - 2]);
  const fim = MES_CHEIO[R.mes_fim - 1];
  v.innerHTML = `<div class="aviso-caixa"><strong>Mesmo período em todos os anos: janeiro a ${fim} (até o ${R.bimestre}º bimestre).</strong> Fonte: SICONFI, Relatório Resumido da Execução Orçamentária (anexo 01). ${esc(D.contexto.siconfi)} Valores nominais.</div>` +
    `<div class="tabela-wrap"><table><caption>Receita realizada de janeiro a ${fim}, por origem (SICONFI/RREO), ${anos[0]}–${anos[anos.length - 1]}</caption><thead><tr><th>Receita</th>${anos.map((a) => `<th class="n">${a}</th>`).join("")}<th class="n">Variação ${ult} × ${pen}</th></tr></thead><tbody>` +
    R.linhas.map((l) => { const vr = varPct(l.v[ult] || 0, l.v[pen] || 0), forte = l.o <= 2; return `<tr><td style="padding-left:${(l.o - 1) * 14 + 10}px">${forte ? "<strong>" : ""}${esc(l.n)}${forte ? "</strong>" : ""}</td>${anos.map((a) => `<td class="n">${l.v[String(a)] != null ? brl0(l.v[String(a)]) : "—"}</td>`).join("")}<td class="n">${fmtVar(vr)}${marcaVar(vr)}</td></tr>`; }).join("") +
    `</tbody></table></div><p class="sub">Coletado em ${dataHoraBR(D.coletas.siconfi_rreo[0])}. O RREO do bimestre seguinte só aparece quando a prefeitura o declara ao Tesouro (prazo de até 30 dias após o fim do bimestre). Fonte: <a href="https://apidatalake.tesouro.gov.br/docs/siconfi/" rel="noopener">SICONFI – Tesouro Nacional</a>.</p>`;
}

/* ---------- 4) Outras entradas ---------- */
function vistaOutras(v, D) {
  const X = D.extra, E = D.emendas;
  v.innerHTML = `<h3>Emendas parlamentares federais e estaduais</h3><p class="sub">Recursos de emendas de outras esferas destinados ao município, como no cadastro do portal. (As emendas impositivas <em>municipais</em> são despesa e não aparecem aqui.)</p>` +
    `<div class="tabela-wrap"><table><caption>Emendas de origem federal ou estadual</caption><thead><tr><th>Emenda</th><th>Ano</th><th>Esfera e tipo</th><th>Autor</th><th class="n">Valor da emenda</th><th class="n">Empenhado</th><th class="n">Pago</th></tr></thead><tbody>` +
    (E.itens.map((e) => `<tr><td class="hist">${esc(e.numero)}</td><td>${e.ano}</td><td>${esc(e.esfera)} · ${esc(e.tipo)}<br><span class="hist">${esc(e.transferencia)}</span></td><td>${esc(e.autor)}</td><td class="n">${brl(e.valor_total)}</td><td class="n">${brl(e.empenhado)}</td><td class="n">${brl(e.pago)}</td></tr>`).join("") || `<tr><td colspan="7" class="vazio">Nenhuma emenda federal ou estadual cadastrada.</td></tr>`) + `</tbody></table></div>` +
    (X ? `<h3>Ingressos extraorçamentários: <em>não são receita</em></h3><div class="aviso-caixa">São valores que passam pelo caixa da Prefeitura e pertencem a terceiros: descontos retidos de servidores e fornecedores (previdência, planos de saúde, empréstimos consignados, sindicatos, tributos retidos, cauções). A Prefeitura os repassa a quem de direito; <strong>não entram na receita nem nos totais do site</strong>. Agrupamento automático por palavras do nome do lançamento, com possíveis imprecisões. Nomes individuais não são exibidos.</div>` +
      `<div class="tabela-wrap"><table><caption>Ingressos extraorçamentários de ${X.ano} por tipo</caption><thead><tr><th>Tipo</th><th class="n">Valor</th><th class="n">Lançamentos</th></tr></thead><tbody>` +
      X.grupos.map((g) => `<tr><td>${esc(g.grupo)}</td><td class="n">${brl0(g.valor)}</td><td class="n">${NUM.format(g.lancamentos)}</td></tr>`).join("") + `</tbody></table></div><p class="sub">Coletado em ${dataHoraBR(X.coleta)}.</p>` : "");
}
