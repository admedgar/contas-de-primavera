/* Aba "Relatório": resumo da semana e do mês de cada instituição. Os números vêm de data/relatorios/*.json (calculados por código);
   o texto de abertura é escrito por IA (ou, se a IA não estiver ativa, por um modelo fixo) e vem rotulado. Usa funções de app.js. */
"use strict";

const REL = { ent: "prefeitura", tipo: "semana", chave: null };
const NOME_INST = { prefeitura: "Prefeitura", camara: "Câmara" };
const NOME_TIPO = { semana: "Semana", mes: "Mês" };
const pct1 = (x) => Math.abs(x).toLocaleString("pt-BR", { minimumFractionDigits: 1, maximumFractionDigits: 1 });
const pctTxt = (x) => (x == null ? "—" : (x >= 0 ? "+" : "−") + pct1(x) + "%");

function cartaoPanorama(ent, tipo, r) {
  if (!r) return `<div class="card"><div class="k">${NOME_INST[ent]} · ${NOME_TIPO[tipo]}</div><div class="p">Sem dados ainda.</div></div>`;
  const f = r.fatos, c = f.comparacao;
  return `<a class="card cartao-rel" href="#/relatorio/${ent}/${tipo}/${esc(f.chave)}">
    <div class="k">${NOME_INST[ent]} · ${esc(f.rotulo)}${f.parcial ? " (parcial)" : ""}</div>
    <div class="v">${brl0(f.emissao.empenhado)}</div>
    <div class="p">empenhado${c.variacao_pct != null ? ` · ${pctTxt(c.variacao_pct)} vs. mesma janela anterior` : ""}</div></a>`;
}

function selo(r) {
  if (r.origem === "ia") return `<p class="selo-ia"><strong>Texto gerado por IA</strong> (${esc(r.modelo || "Claude")}) em ${dataHoraBR(r.gerado_em)}, a partir dos números abaixo. Os números são calculados pelo sistema, sem IA; o texto passa por verificação automática (todo número citado precisa constar da ficha de dados). Confira sempre a tabela e a fonte oficial.</p>`;
  return `<p class="selo-ia selo-modelo"><strong>Texto padronizado, sem IA.</strong> O resumo por inteligência artificial ainda não está ativo neste site; este texto é montado por um modelo fixo a partir dos mesmos números abaixo.</p>`;
}

function linhasTabela(itens, colunas) {
  if (!itens || !itens.length) return `<p class="vazio">Nada registrado no período.</p>`;
  return `<div class="tabela-wrap"><table><thead><tr>${colunas.map((c) => `<th${c.n ? ' class="n"' : ""}>${c.t}</th>`).join("")}</tr></thead><tbody>${
    itens.map((i) => `<tr>${colunas.map((c) => `<td${c.n ? ' class="n"' : ""}>${c.f(i)}</td>`).join("")}</tr>`).join("")}</tbody></table></div>`;
}

function corpoRelatorio(r) {
  const f = r.fatos, t = r.texto, e = f.emissao, c = f.comparacao;
  const cmp = c.variacao_pct != null
    ? `${pctTxt(c.variacao_pct)} em relação à mesma janela anterior (${dataBR(c.inicio)} a ${dataBR(c.fim)}: ${brl0(c.empenhado)} em ${NUM.format(c.qtd)} empenhos)`
    : "Sem período anterior para comparar.";
  let h = selo(r) +
    `<div class="card resumo-ia"><h3 style="margin-top:0">${esc(t.titulo)}</h3><p class="resumo-txt">${esc(t.resumo)}</p>` +
    `<ul class="limpo">${t.pontos.map((p) => `<li>${esc(p)}</li>`).join("")}</ul>` +
    `<details><summary>Limites e como ler</summary><ul class="limpo">${t.observacoes.map((o) => `<li>${esc(o)}</li>`).join("")}</ul></details></div>` +
    `<h3>Os números</h3><p class="sub">${esc(f.rotulo)} · dados do portal até ${dataBR(f.ate)}${f.parcial ? " (período em andamento)" : ""} · ${NUM.format(f.dias_com_registro)} dias com registro.</p>` +
    `<div class="grade">
      <div class="card"><div class="k">Empenhado (líquido de anulações)</div><div class="v">${brl(e.empenhado)}</div><div class="p">${esc(cmp)}</div></div>
      <div class="card"><div class="k">Empenhos emitidos</div><div class="v">${NUM.format(e.qtd)}</div><div class="p">Anulações: ${brl(e.anulado)}</div></div>
      <div class="card"><div class="k">Desses, já liquidado</div><div class="v">${brl(e.liquidado)}</div><div class="p">posição na coleta</div></div>
      <div class="card"><div class="k">Desses, já pago</div><div class="v">${brl(e.pago)}</div><div class="p">posição na coleta</div></div></div>`;
  if (f.dia_pico && f.dia_pico.pct != null && f.dias_com_registro > 1) h += `<p class="sub">Dia de maior valor empenhado: ${dataBR(f.dia_pico.data)} (${brl0(f.dia_pico.empenhado)}, ${pct1(f.dia_pico.pct)}% do total positivo do período). Quando um dia concentra boa parte do período, comparações com outros períodos oscilam bastante.</p>`;
  if (f.oficial_mes && f.oficial_mes.mes) {
    const o = f.oficial_mes, linhas = [["Neste mês", o.mes], o.mes_anterior && [o.mes_anterior.rotulo, o.mes_anterior], o.mesmo_mes_ano_anterior && [o.mesmo_mes_ano_anterior.rotulo, o.mesmo_mes_ano_anterior]].filter(Boolean);
    h += `<h3>Totais do mês informados pelo portal</h3><p class="sub">Mesmos valores da aba “Mês a mês”: o liquidado e o pago do mês incluem empenhos de meses anteriores.</p>` +
      linhasTabela(linhas, [{ t: "Mês", f: (l) => esc(l[0]) }, { t: "Empenhado", n: 1, f: (l) => brl(l[1].empenhado) }, { t: "Liquidado", n: 1, f: (l) => brl(l[1].liquidado) }, { t: "Pago", n: 1, f: (l) => brl(l[1].pago) }]);
  }
  h += `<h3>Onde foi empenhado</h3>` +
    linhasTabela(f.orgaos, [{ t: "Órgão", f: (i) => esc(i.nome) }, { t: "Empenhado", n: 1, f: (i) => brl(i.empenhado) }, { t: "% do total", n: 1, f: (i) => (i.pct == null ? "—" : pct1(i.pct) + "%") }]) +
    `<h3>Natureza da despesa</h3>` +
    linhasTabela(f.elementos, [{ t: "Natureza", f: (i) => esc(i.nome) }, { t: "Empenhado", n: 1, f: (i) => brl(i.empenhado) }, { t: "% do total", n: 1, f: (i) => (i.pct == null ? "—" : pct1(i.pct) + "%") }]) +
    `<h3>Maiores fornecedores (pessoas jurídicas)</h3>` +
    linhasTabela(f.fornecedores, [{ t: "Fornecedor", f: (i) => esc(i.nome) }, { t: "Empenhado", n: 1, f: (i) => brl(i.empenhado) }]) +
    (f.pessoas_fisicas ? `<p class="sub">Pagamentos a pessoas físicas (nomes omitidos por privacidade): ${brl(f.pessoas_fisicas.empenhado)}, ${NUM.format(f.pessoas_fisicas.pessoas)} pessoas. O valor segue somado nos totais; a lista completa está no portal oficial.</p>` : "") +
    `<h3>Maiores empenhos do período</h3><p class="sub">Não inclui pagamentos em nome da própria instituição (como a folha).</p>` +
    linhasTabela(f.maiores, [{ t: "Data", f: (i) => dataBR(i.data) }, { t: "Fornecedor", f: (i) => esc(i.fornecedor) }, { t: "Órgão", f: (i) => esc(i.orgao) }, { t: "Natureza", f: (i) => esc(i.elemento) },
      { t: "Modalidade", f: (i) => esc(i.modalidade || "—") }, { t: "Valor", n: 1, f: (i) => brl(i.valor) }]) +
    `<h3>Modalidade de compra registrada</h3>` +
    linhasTabela(f.modalidades, [{ t: "Modalidade (como no portal)", f: (i) => esc(i.nome) }, { t: "Empenhado", n: 1, f: (i) => brl(i.empenhado) }, { t: "% do total", n: 1, f: (i) => (i.pct == null ? "—" : pct1(i.pct) + "%") }]);
  const l = f.licitacoes, ct = f.contratos;
  h += `<h3>Licitações e contratos</h3><ul class="limpo"><li>Licitações no período: ${l.qtd ? `${NUM.format(l.qtd)} processos, valor ${brl0(l.valor)}${l.por_modalidade.length ? " (" + l.por_modalidade.map((m) => `${esc(m.nome)}: ${m.qtd}`).join("; ") + ")" : ""}` : "nenhum processo registrado"}.</li>` +
    `<li>Contratos assinados no período: ${ct.qtd ? `${NUM.format(ct.qtd)} contratos, valor ${brl0(ct.valor)}` : "nenhum"}.</li></ul>`;
  if (f.camara) {
    const v = f.camara.verba, d = f.camara.diarias;
    const verbas = Object.keys(v).length ? Object.entries(v).map(([k, x]) => `<li>${k === "verba" ? "Verba indenizatória" : "Reembolsos"}: ${brl(x.empenhado)} empenhado, ${brl(x.pago)} pago (${NUM.format(x.qtd)} empenhos).</li>`).join("") : "<li>Verba indenizatória e reembolsos: nenhum empenho no período.</li>";
    h += `<h3>Diárias por vereador</h3><p class="sub">Diárias do período, líquidas de anulações, sem passagens e locação de veículos. Vereadores aparecem com nome, como na aba Câmara; os demais servidores entram só somados.</p>` +
      (d.qtd ? linhasTabela(d.vereadores, [{ t: "Vereador", f: (i) => esc(i.nome) }, { t: "Lançamentos", n: 1, f: (i) => NUM.format(i.qtd) }, { t: "Dias", n: 1, f: (i) => NUM.format(i.dias) }, { t: "Valor", n: 1, f: (i) => brl(i.valor) }]) +
        `<ul class="limpo"><li><strong>Total de diárias no período:</strong> ${brl(d.valor)} em ${NUM.format(d.qtd)} lançamentos (vereadores: ${brl(d.vereadores_valor)}; demais servidores: ${brl(d.servidores.valor)} em ${NUM.format(d.servidores.qtd)} lançamentos${d.servidores.pessoas ? `, ${NUM.format(d.servidores.pessoas)} pessoas` : ""}).</li>` +
        (d.pendentes.qtd ? `<li>Aguardando vínculo a vereador: ${brl(d.pendentes.valor)} em ${NUM.format(d.pendentes.qtd)} lançamentos.</li>` : "") + `</ul>`
        : `<p class="vazio">Nenhuma diária registrada no período.</p>`) +
      `<h3>Verba indenizatória e reembolsos</h3><ul class="limpo">${verbas}</ul>`;
  }
  h += `<p class="sub">Fonte: <a href="${esc(r.portal)}" rel="noopener">Portal da Transparência ${NOME_INST[f.entidade] === "Câmara" ? "da Câmara" : "da Prefeitura"}</a>. Coletado em ${dataHoraBR(r.coleta)}. Cálculos e limites em <a href="#/metodologia">Metodologia</a>.</p>`;
  return h;
}

async function paginaRelatorio(ent, tipo, chave) {
  await usaEntidade(ent === "camara" ? "camara" : "prefeitura");           // inicia os contadores do topo, como nas outras abas
  let idx;
  try { idx = await carregar("relatorios/index.json"); }
  catch (e) { $("#pagina").innerHTML = `<h2>Relatório da semana e do mês</h2><div class="aviso-caixa">Os relatórios ainda não foram gerados. Eles aparecem aqui após a próxima atualização dos dados.</div>`; return; }
  if (ent !== "camara" && ent !== "prefeitura") { ent = null; }
  if (ent) { REL.ent = ent; REL.tipo = tipo === "mes" ? "mes" : "semana"; REL.chave = chave || null; }
  const lista = (idx.itens[REL.ent] || {})[REL.tipo] || [];
  const escolhida = lista.find((i) => i.chave === REL.chave) ? REL.chave : (idx.padrao[REL.ent] || {})[REL.tipo];
  const nav = (e2, t2, c2) => `#/relatorio/${e2}/${t2}/${c2 || ""}`;
  let h = `<h2>Relatório da semana e do mês</h2><p class="sub">Resumo do que o portal registrou, em linguagem simples, para a Prefeitura e para a Câmara. O texto é redigido por inteligência artificial; os números são calculados pelo sistema a partir do Portal da Transparência, sempre até a data da última atualização do portal.</p>`;
  if (!ent) {                                                          // panorama (sem instituição escolhida)
    const par = [];
    for (const e2 of ["prefeitura", "camara"]) for (const t2 of ["semana", "mes"]) {
      const ch = (idx.padrao[e2] || {})[t2];
      par.push(ch ? carregar(`relatorios/${e2}_${t2}_${ch}.json`).catch(() => null) : Promise.resolve(null));
    }
    const rs = await Promise.all(par);
    h += `<div class="grade">${["prefeitura", "camara"].flatMap((e2, i) => ["semana", "mes"].map((t2, j) => cartaoPanorama(e2, t2, rs[i * 2 + j]))).join("")}</div>` +
      `<p class="sub">Escolha uma instituição e um período abaixo para ver o relatório completo.</p>`;
    REL.chave = null;
  }
  h += `<nav class="subnav" aria-label="Instituição">${["prefeitura", "camara"].map((e2) => `<a href="${nav(e2, REL.tipo)}" ${ent && REL.ent === e2 ? 'aria-current="true"' : ""}>${NOME_INST[e2]}</a>`).join("")}</nav>`;
  if (ent) {
    h += `<nav class="subnav" aria-label="Tipo de período">${["semana", "mes"].map((t2) => `<a href="${nav(REL.ent, t2)}" ${REL.tipo === t2 ? 'aria-current="true"' : ""}>${t2 === "semana" ? "Semana" : "Mês"}</a>`).join("")}</nav>` +
      (lista.length ? `<div class="ferramentas"><label>Período<select id="rel-periodo">${lista.map((i) => `<option value="${esc(i.chave)}" ${i.chave === escolhida ? "selected" : ""}>${esc(i.rotulo)}${i.parcial ? " (em andamento)" : ""}</option>`).join("")}</select></label></div>` : "") +
      `<section id="rel-corpo" aria-live="polite"><p class="carregando">Carregando…</p></section>`;
  }
  $("#pagina").innerHTML = h;
  if (!ent) return;
  const sel = $("#rel-periodo");
  if (sel) sel.onchange = () => { location.hash = nav(REL.ent, REL.tipo, sel.value); };
  const corpo = $("#rel-corpo");
  if (!escolhida) { corpo.innerHTML = `<p class="vazio">Sem relatório disponível para este tipo de período.</p>`; return; }
  try {
    const r = await carregar(`relatorios/${REL.ent}_${REL.tipo}_${escolhida}.json`);
    corpo.innerHTML = corpoRelatorio(r) +
      `<div class="compartilhar compartilhar-claro"><a href="https://wa.me/?text=${encodeURIComponent(`${r.texto.titulo}: ${r.texto.resumo} — ${location.origin}${location.pathname}#/relatorio/${REL.ent}/${REL.tipo}/${escolhida}`)}" target="_blank" rel="noopener">Compartilhar no WhatsApp</a></div>`;
  } catch (e) { corpo.innerHTML = `<div class="aviso-caixa">Não foi possível carregar este relatório: ${esc(e.message)}</div>`; }
}
