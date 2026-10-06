/* Seções exclusivas da aba Câmara. Usa as funções de app.js (carregadas depois; só são chamadas após a inicialização). */
"use strict";

const URL_VI_OFICIAL = "https://www.primaveradoleste.mt.leg.br/transparencia";
const SEC_CAM = {};
const pl = (n, w) => `${n} ${w}${n === 1 ? "" : "s"}`;
const MES_CHEIO = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro", "novembro", "dezembro"];
const dec1 = new Intl.NumberFormat("pt-BR", { minimumFractionDigits: 0, maximumFractionDigits: 1 });
const coletaCam = (f) => (ESTADO.meta.entidades.camara.fontes.find((x) => x.fonte === f) || {}).coletado_em;

SEC_CAM.resumo = async (el) => {
  const custo = await carregar("camara/custo.json"), anos = Object.keys(ESTADO.resumo.anos).map(Number);
  const a = ESTADO.resumo.anos[ESTADO.ano], c = custo[ESTADO.ano], k = K[ESTADO.medida];
  const tot = c.composicao.reduce((s, g) => s + g[k], 0) || 1, max = Math.max(1, ...c.composicao.map((g) => g[k]));
  el.innerHTML = cabecalhoSecao("Custo da Câmara", "Quanto a Câmara Municipal custa e como esse valor se divide. Valores oficiais do portal, coletados nesta ferramenta.") +
    `<div class="ferramentas">${seletorAno(anos)}${seletorMedida()}</div>` +
    (c.parcial ? `<div class="aviso-caixa">Exercício em andamento: os valores são acumulados até a última coleta e comparados com a receita e o repasse do mesmo período.</div>` : "") +
    `<div class="grade">
      <div class="card"><div class="k">${MEDIDAS[ESTADO.medida]} no ano</div><div class="v">${brl0(c.despesa[k])}</div><div class="p">Dotação atualizada: ${brl0(a.dotacao_atualizada)}</div></div>
      <div class="card"><div class="k">Por habitante no ano</div><div class="v">${c.por_habitante[k] != null ? brl(c.por_habitante[k]) : "—"}</div><div class="p">${c.habitantes ? NUM.format(c.habitantes) + " hab. (IBGE)" : ""}</div></div>
      <div class="card"><div class="k">% da receita corrente da Prefeitura</div><div class="v">${c.pct_receita_corrente[k] != null ? PCT.format(c.pct_receita_corrente[k]) : "—"}</div><div class="p">Receita corrente arrecadada: ${brl0(c.receita_corrente_prefeitura)}</div></div>
      <div class="card"><div class="k">Repasse da Prefeitura (duodécimo)</div><div class="v">${brl0(c.repasse_recebido)}</div><div class="p">Devolvido à Prefeitura: ${brl0(c.devolucao)}<br>Repasse líquido: ${brl0(c.repasse_liquido)}</div></div>
      <div class="card"><div class="k">Pago ÷ repasse líquido</div><div class="v">${c.pago_sobre_repasse_liquido != null ? PCT.format(c.pago_sobre_repasse_liquido) : "—"}</div><div class="p">Relaciona o valor pago ao repasse líquido do mesmo período.</div></div></div>` +
    `<h3>Como o valor se divide</h3><div class="tabela-wrap"><table><caption>${MEDIDAS[ESTADO.medida]} por grupo de despesa em ${ESTADO.ano}</caption><thead><tr><th>Grupo (elementos de despesa)</th><th class="n">${MEDIDAS[ESTADO.medida]}</th><th class="n">% do total</th></tr></thead><tbody>` +
    c.composicao.map((g) => `<tr><td>${esc(g.grupo)}</td><td class="celbarra"><i style="width:${Math.max(0, g[k]) / max * 100}%"></i><span class="n" style="display:block;text-align:right">${brl(g[k])}</span></td><td class="n">${PCT.format(g[k] / tot)}</td></tr>`).join("") +
    `</tbody></table></div><p class="sub">Pessoal e encargos = vencimentos (11), obrigações patronais (13), auxílio-alimentação (46) e auxílio-transporte (49). Diárias = 14. Verba indenizatória e reembolsos = 93. Administrativas = serviços de terceiros PJ (39), material de consumo (30), tecnologia (40), equipamentos (52), passagens e locação de veículos (33) e exercícios anteriores (92).</p>` +
    `<h3>Repasses mensais da Prefeitura à Câmara</h3><div class="tabela-wrap"><table><caption>Duodécimo repassado em ${ESTADO.ano}, conforme a consulta de transferências do portal da Prefeitura</caption><thead><tr><th>Mês</th><th>Data</th><th class="n">Repassado</th><th class="n">Previsto</th></tr></thead><tbody>` +
    (c.repasse_mensal.map((r) => `<tr><td>${MESES[r.mes - 1] || r.mes}</td><td>${dataBR(r.data)}</td><td class="n">${brl(r.valor)}</td><td class="n">${brl(r.previsto)}</td></tr>`).join("") || `<tr><td colspan="4" class="vazio">Sem repasses coletados.</td></tr>`) +
    (c.devolucoes.map((r) => `<tr><td>${MESES[r.mes - 1] || r.mes}</td><td>${dataBR(r.data)}</td><td class="n">−${brl(r.valor)} (devolução da Câmara à Prefeitura)</td><td></td></tr>`).join("")) +
    `</tbody></table></div>` +
    `<h3>Comparativo entre exercícios</h3><div class="tabela-wrap"><table><caption>Despesa da Câmara por exercício (${MEDIDAS[ESTADO.medida].toLowerCase()})</caption><thead><tr><th>Ano</th><th class="n">${MEDIDAS[ESTADO.medida]}</th><th class="n">Por habitante</th><th class="n">% da receita corrente da Prefeitura</th><th class="n">Repasse líquido</th></tr></thead><tbody>` +
    anos.map((y) => `<tr><td>${y}${custo[y].parcial ? " (parcial)" : ""}</td><td class="n">${brl0(custo[y].despesa[k])}</td><td class="n">${custo[y].por_habitante[k] != null ? brl(custo[y].por_habitante[k]) : "—"}</td><td class="n">${custo[y].pct_receita_corrente[k] != null ? PCT.format(custo[y].pct_receita_corrente[k]) : "—"}</td><td class="n">${brl0(custo[y].repasse_liquido)}</td></tr>`).join("") +
    `</tbody></table></div>` + fonteLinha(a.coleta_empenhos, "Fórmulas em <a href=\"#/metodologia\">Metodologia</a>.");
  ligaSeletores(() => SEC_CAM.resumo(el));
};

/* ---------- Vereadores: comparativo e ficha ---------- */
const COLS = [["meses", "Meses de exercício"], ["proventos", "Proventos (folha)"], ["diarias", "Diárias"], ["verba", "Verba indenizatória"], ["reembolsos", "Reembolsos"], ["total", "Soma das colunas"]];

SEC_CAM.vereadores = async (el, id) => {
  const [comp, fich] = await Promise.all([carregar("camara/comparativo.json"), carregar("camara/vereadores.json")]);
  const anos = Object.keys(comp).map(Number);
  if (id) return fichaVereador(el, id, fich.anos[ESTADO.ano] || [], anos);
  const S = { modo: "total", ordem: "nome" };
  const desenha = () => {
    let L = [...comp[ESTADO.ano]];
    const val = (r, c) => (c === "meses" ? r.meses : S.modo === "media" ? r[c + "_mes"] : r[c]);
    L.sort(S.ordem === "nome" ? (a, b) => a.nome.localeCompare(b.nome, "pt-BR") : (a, b) => val(b, S.ordem) - val(a, S.ordem));
    const soma = (c) => L.reduce((s, r) => s + (c === "meses" ? 0 : r[c]), 0);
    $("#v-tab").innerHTML = `<div class="tabela-wrap"><table><caption>Comparativo entre vereadores em ${ESTADO.ano} — ${S.modo === "media" ? "média por mês de exercício" : "totais do período"}; ordem ${S.ordem === "nome" ? "alfabética" : "pela coluna escolhida"}</caption><thead><tr><th>Vereador</th>${COLS.map(([c, n]) => `<th class="n">${n}${S.modo === "media" && c !== "meses" ? " (por mês)" : ""}</th>`).join("")}</tr></thead><tbody>` +
      L.map((r) => `<tr><td><a href="#/camara/vereadores/${r.id}">${esc(r.nome)}</a>${r.cargos.some((x) => /SUPLENTE/i.test(x)) ? ' <span class="etq">suplente</span>' : ""}<br><span class="hist">${r.periodo ? "com proventos de " + MESES[r.periodo[0] - 1] + " a " + MESES[r.periodo[1] - 1] : "sem proventos no ano"}</span></td>` +
        COLS.map(([c]) => `<td class="n">${c === "meses" ? r.meses : brl(val(r, c))}</td>`).join("") + `</tr>`).join("") +
      (S.modo === "total" ? `<tr><td><strong>Soma</strong></td><td></td>${COLS.slice(1).map(([c]) => `<td class="n"><strong>${brl(soma(c))}</strong></td>`).join("")}</tr>` : "") +
      `</tbody></table></div>`;
  };
  el.innerHTML = cabecalhoSecao("Vereadores", "Os mesmos critérios para todos, a partir dos dados oficiais. Clique no nome para ver a ficha. A ordem padrão é alfabética: a tabela não classifica ninguém.") +
    `<div class="ferramentas">${seletorAno(anos)}
      <label>Mostrar<select id="v-modo"><option value="total">Totais do período</option><option value="media">Média por mês de exercício</option></select></label>
      <label>Ordenar por<select id="v-ordem"><option value="nome">Nome (A–Z)</option>${COLS.map(([c, n]) => `<option value="${c}">${n} (maior primeiro)</option>`).join("")}</select></label>
      <button class="acao" id="v-csv" type="button">Baixar CSV</button></div>
     <div class="aviso-caixa"><strong>Como ler.</strong> <em>Mês de exercício</em> é o mês com proventos na folha (afastamentos e substituições entram só pelos meses em que houve pagamento). Quem exerceu o mandato por menos meses tem totais menores por esse motivo; use “média por mês”. A verba indenizatória é contada pelo mês do <em>empenho</em>, e há defasagem entre a competência e o empenho. Não estão incluídos encargos patronais, auxílios, passagens aéreas nem a estrutura do gabinete. Detalhes em <a href="#/metodologia">Metodologia</a>.</div>
     <div id="v-tab"></div>`;
  $("#v-modo").onchange = (e) => { S.modo = e.target.value; desenha(); };
  $("#v-ordem").onchange = (e) => { S.ordem = e.target.value; desenha(); };
  $("#v-csv").onclick = () => baixarCSV(`vereadores_${ESTADO.ano}.csv`, ["Vereador", "Meses de exercicio", "Proventos", "Diarias", "Verba indenizatoria", "Reembolsos", "Soma", "Proventos por mes", "Diarias por mes", "Verba por mes", "Reembolsos por mes", "Soma por mes"],
    comp[ESTADO.ano].map((r) => [r.nome, r.meses, reais(r.proventos), reais(r.diarias), reais(r.verba), reais(r.reembolsos), reais(r.total), reais(r.proventos_mes), reais(r.diarias_mes), reais(r.verba_mes), reais(r.reembolsos_mes), reais(r.total_mes)]));
  ligaSeletores(() => SEC_CAM.vereadores(el));
  desenha();
};

function fichaVereador(el, id, fichas, anos) {
  const f = fichas.find((x) => String(x.id) === String(id));
  if (!f) { el.innerHTML = `<p><a href="#/camara/vereadores">← Vereadores</a></p><div class="aviso-caixa">Este vereador não tem registro na folha de ${ESTADO.ano}. Escolha outro ano.</div><div class="ferramentas">${seletorAno(anos)}</div>`; ligaSeletores(() => SEC_CAM.vereadores(el, id)); return; }
  const dm = Object.fromEntries(f.diarias.mensal.map((x) => [x.mes, x.v])), vm = Object.fromEntries(f.verba.mensal.map((x) => [x.mes, x.pago]));
  const meses = [...new Set([...f.folha_mensal.map((x) => x.mes), ...Object.keys(dm).map(Number), ...Object.keys(vm).map(Number)])].sort((a, b) => a - b);
  const fm = Object.fromEntries(f.folha_mensal.map((x) => [x.mes, x]));
  const tab = (cab, linhas, vazio) => `<div class="tabela-wrap"><table><thead><tr>${cab.map((c) => `<th class="${c.n ? "n" : ""}">${c.t}</th>`).join("")}</tr></thead><tbody>${linhas.join("") || `<tr><td colspan="${cab.length}" class="vazio">${vazio}</td></tr>`}</tbody></table></div>`;
  el.innerHTML = `<p><a href="#/camara/vereadores">← Todos os vereadores</a></p>` + cabecalhoSecao(f.nome, `${esc(f.cargos.join(", "))} · ${esc(f.vinculo || "")}${f.admissao ? " · admissão " + dataBR(f.admissao) : ""} · ${f.folha.meses} ${f.folha.meses === 1 ? "mês" : "meses"} com proventos em ${ESTADO.ano}`) +
    `<div class="ferramentas">${seletorAno(anos)}</div>` +
    `<div class="grade">
      <div class="card"><div class="k">Proventos (folha)</div><div class="v">${brl0(f.folha.proventos)}</div><div class="p">Descontos: ${brl0(f.folha.descontos)}<br>${f.folha.meses ? brl0(f.folha.proventos / f.folha.meses) + " por mês de exercício" : ""}</div></div>
      <div class="card"><div class="k">Diárias</div><div class="v">${brl0(f.diarias.valor)}</div><div class="p">${pl(f.diarias.qtd, "lançamento")} · ${dec1.format(f.diarias.dias)} ${f.diarias.dias === 1 ? "diária" : "diárias"}</div></div>
      <div class="card"><div class="k">Verba indenizatória recebida</div><div class="v">${brl0(f.verba.pago)}</div><div class="p">${pl(f.verba.qtd, "pagamento")}${f.folha.meses ? " · " + brl0(f.verba.pago / f.folha.meses) + " por mês de exercício" : ""}</div></div>
      <div class="card"><div class="k">Reembolsos</div><div class="v">${brl0(f.reembolsos.pago)}</div><div class="p">${pl(f.reembolsos.qtd, "pagamento")}</div></div>
      <div class="card"><div class="k">Passagens com o nome no histórico</div><div class="v">${brl0(f.passagens.valor)}</div><div class="p">${pl(f.passagens.qtd, "lançamento")}. Não inclui as não identificadas.</div></div></div>` +
    (f.meses_sem_proventos.length ? `<div class="aviso-caixa">Meses com registro na folha, porém sem proventos: ${f.meses_sem_proventos.map((m) => MESES[m - 1]).join(", ")}. Esses meses não contam como “mês de exercício”.</div>` : "") +
    `<h3>Mês a mês</h3>` + tab([{ t: "Mês" }, { t: "Cargo na folha" }, { t: "Proventos", n: 1 }, { t: "Descontos", n: 1 }, { t: "Diárias (data do pagamento)", n: 1 }, { t: "Verba indenizatória (mês do empenho)", n: 1 }],
      meses.map((m) => `<tr><td>${MESES[m - 1]}</td><td>${fm[m] ? esc(fm[m].cargo) : "—"}</td><td class="n">${fm[m] ? brl(fm[m].proventos) : "—"}</td><td class="n">${fm[m] ? brl(fm[m].descontos) : "—"}</td><td class="n">${dm[m] ? brl(dm[m]) : "—"}</td><td class="n">${vm[m] ? brl(vm[m]) : "—"}</td></tr>`), "Sem registros.") +
    `<h3>Diárias</h3>` + tab([{ t: "Data" }, { t: "Diárias", n: 1 }, { t: "Valor", n: 1 }, { t: "Descrição oficial" }], f.diarias.itens.map((d) => `<tr><td>${dataBR(d.data)}</td><td class="n">${dec1.format(d.dias)}</td><td class="n">${brl(d.valor)}</td><td class="hist">${esc(d.descricao)}</td></tr>`), "Nenhuma diária no ano.") +
    `<h3>Verba indenizatória</h3><p class="sub">Valor recebido, conforme o portal. <strong>Detalhamento de como o vereador gastou a verba em breve.</strong> <a href="${URL_VI_OFICIAL}" rel="noopener">Página oficial da Câmara</a>.</p>` +
    tab([{ t: "Data do empenho" }, { t: "Competência informada" }, { t: "Valor pago", n: 1 }], f.verba.itens.map((v) => `<tr><td>${dataBR(v.data)}</td><td>${v.competencia ? MESES[Number(v.competencia.slice(5)) - 1] + "/" + v.competencia.slice(0, 4) : "não informada"}</td><td class="n">${brl(v.pago)}</td></tr>`), "Nenhum pagamento no ano.") +
    `<h3>Reembolsos</h3><p class="sub">Outros empenhos do elemento “Indenizações e restituições” pagos ao vereador, que não são a verba indenizatória.</p>` +
    tab([{ t: "Data" }, { t: "Valor pago", n: 1 }, { t: "Histórico oficial" }], f.reembolsos.itens.map((v) => `<tr><td>${dataBR(v.data)}</td><td class="n">${brl(v.pago)}</td><td class="hist">${esc(v.historico)}</td></tr>`), "Nenhum reembolso no ano.") +
    `<h3>Passagens aéreas com o nome do vereador no histórico</h3><p class="sub">O favorecido das passagens é a agência. Só entram aqui as que citam, no histórico oficial, um único passageiro com o nome completo do vereador; as demais não são atribuíveis e ficam de fora.</p>` +
    tab([{ t: "Data" }, { t: "Trecho informado" }, { t: "Valor", n: 1 }], f.passagens.itens.map((p) => `<tr><td>${dataBR(p.data)}</td><td class="hist">${esc(p.trecho || "")}</td><td class="n">${brl(p.valor)}</td></tr>`), "Nenhuma identificada.") +
    fonteLinha(coletaCam("servidores_mensal"), "Folha: consulta de servidores do portal. Os mesmos critérios valem para todos os vereadores (<a href=\"#/metodologia\">Metodologia</a>).");
  ligaSeletores(() => SEC_CAM.vereadores(el, id));
}

/* ---------- Verba indenizatória ---------- */
SEC_CAM.verba = async (el) => {
  const v = await carregar("camara/verba.json"), anos = Object.keys(v.anos).map(Number), d = v.anos[ESTADO.ano];
  const meses = [...new Set(d.vereadores.flatMap((x) => Object.keys(x.meses).map(Number)))].sort((a, b) => a - b);
  const totMes = (m) => d.vereadores.reduce((s, x) => s + (x.meses[m] || 0), 0);
  el.innerHTML = cabecalhoSecao("Verba indenizatória", "Valor mensal recebido por vereador, conforme o portal de dados abertos (elemento 93, histórico “verba indenizatória”). Mostra apenas <strong>quanto foi recebido</strong>.") +
    `<div class="aviso-caixa">Detalhamento de como cada vereador gastou a verba em breve. <a href="${v.detalhamento.link_oficial}" rel="noopener">Página oficial da Câmara</a>.</div>` +
    `<div class="ferramentas">${seletorAno(anos)}<button class="acao" id="vb-csv" type="button">Baixar CSV</button></div>` +
    `<div class="tabela-wrap"><table><caption>Verba indenizatória paga por vereador e mês do empenho, ${ESTADO.ano}</caption><thead><tr><th>Vereador</th>${meses.map((m) => `<th class="n">${MESES[m - 1]}</th>`).join("")}<th class="n">Total</th></tr></thead><tbody>` +
    d.vereadores.map((x) => `<tr><td><a href="#/camara/vereadores/${x.id}">${esc(x.nome)}</a></td>${meses.map((m) => `<td class="n">${x.meses[m] ? brl(x.meses[m]) : "—"}</td>`).join("")}<td class="n"><strong>${brl(x.total)}</strong></td></tr>`).join("") +
    `<tr><td><strong>Soma</strong></td>${meses.map((m) => `<td class="n"><strong>${brl(totMes(m))}</strong></td>`).join("")}<td class="n"><strong>${brl(d.vereadores.reduce((s, x) => s + x.total, 0))}</strong></td></tr></tbody></table></div>` +
    `<p class="sub">Mês do <em>empenho</em> (a consulta não informa a data do pagamento); a competência, quando o histórico a cita, aparece na ficha de cada vereador. Ordem alfabética.</p>` +
    `<h3>Conferência com o portal</h3><ul class="limpo"><li>Total do elemento 93 pago em ${ESTADO.ano}: <strong>${brl(d.total_elemento_93_pago)}</strong> = verba indenizatória ${brl(d.total_verba)} + reembolsos e restituições ${brl(d.total_reembolsos)}.</li>` +
    (d.nao_vinculado.verba_qtd || d.nao_vinculado.reembolsos_qtd ? `<li>Há ${brl(d.nao_vinculado.verba_pago)} de verba indenizatória (${d.nao_vinculado.verba_qtd} pagamento${d.nao_vinculado.verba_qtd === 1 ? "" : "s"}) e ${brl(d.nao_vinculado.reembolsos_pago)} de reembolsos pagos a favorecidos que <strong>ainda não estão vinculados a um vereador</strong>: constam no total acima, mas não nas linhas dos vereadores${d.nao_vinculado.itens.length ? " (" + d.nao_vinculado.itens.map((i) => dataBR(i.data) + " " + brl(i.pago)).join("; ") + ")" : ""}. Veja <a href="#/metodologia">Metodologia</a>.</li>` : "") +
    `</ul>` + fonteLinha(coletaCam("despesas_gerais"));
  $("#vb-csv").onclick = () => baixarCSV(`verba_indenizatoria_${ESTADO.ano}.csv`, ["Vereador", ...meses.map((m) => MESES[m - 1]), "Total"], d.vereadores.map((x) => [x.nome, ...meses.map((m) => reais(x.meses[m] || 0)), reais(x.total)]));
  ligaSeletores(() => SEC_CAM.verba(el));
};

/* ---------- Diárias ---------- */
SEC_CAM.diarias = async (el) => {
  const D = await carregar("camara/diarias.json"), anos = Object.keys(D).map(Number), d = D[ESTADO.ano];
  const pl = d.passagens_e_locomocao;
  el.innerHTML = cabecalhoSecao("Diárias", "Valores pagos para viagens a serviço. Vereadores aparecem com nome (ver Vereadores); os demais servidores, apenas somados por cargo.") +
    `<div class="ferramentas">${seletorAno(anos)}</div>` +
    `<div class="grade"><div class="card"><div class="k">Total de diárias</div><div class="v">${brl0(d.total)}</div><div class="p">${NUM.format(d.lancamentos)} lançamentos</div></div>
      <div class="card"><div class="k">Pagas a vereadores</div><div class="v">${brl0(d.vereadores.valor)}</div><div class="p">${NUM.format(d.vereadores.lancamentos)} lançamentos</div></div>
      <div class="card"><div class="k">Pagas a outros servidores</div><div class="v">${brl0(d.servidores.valor)}</div><div class="p">${NUM.format(d.servidores.lancamentos)} lançamentos</div></div>` +
    (d.vereadores_pendentes.lancamentos ? `<div class="card"><div class="k">Aguardando vínculo a vereador</div><div class="v">${brl0(d.vereadores_pendentes.valor)}</div><div class="p">${d.vereadores_pendentes.lancamentos} lançamento(s); veja Metodologia</div></div>` : "") + `</div>` +
    grafico([d.mensal.map((x) => x.valor)], { rotulos: d.mensal.map((x) => MESES[x.mes - 1]), titulo: `Diárias pagas por mês em ${ESTADO.ano}` }) +
    tabelaApoio(d.mensal.map((x) => MESES[x.mes - 1]), [{ nome: "Diárias", v: d.mensal.map((x) => x.valor) }]) +
    `<h3>Servidores que não são vereadores, por cargo</h3><div class="tabela-wrap"><table><caption>Diárias a servidores por cargo em ${ESTADO.ano} (sem nomes; cargos com menos de 3 pessoas são reunidos em “Outros”)</caption><thead><tr><th>Cargo</th><th class="n">Pessoas</th><th class="n">Lançamentos</th><th class="n">Valor</th><th class="n">Média por lançamento</th></tr></thead><tbody>` +
    (d.servidores.por_cargo.map((g) => `<tr><td>${esc(g.cargo)}</td><td class="n">${g.pessoas}</td><td class="n">${NUM.format(g.lancamentos)}</td><td class="n">${brl(g.valor)}</td><td class="n">${brl(g.valor / g.lancamentos)}</td></tr>`).join("") || `<tr><td colspan="5" class="vazio">Sem dados.</td></tr>`) +
    `</tbody></table></div>` +
    `<h3>Passagens e locação de veículos</h3><p class="sub">Pagos a empresas (agência de viagens e locadoras): ${brl0(pl.total)} em ${ESTADO.ano}. Só as passagens que citam, no histórico oficial, um único passageiro com o nome completo do vereador podem ser atribuídas: ${brl0(pl.atribuidas_a_vereador)}. Elas aparecem na ficha de cada vereador, fora do comparativo.</p>` +
    `<p class="sub">Conferência: o total de diárias (${brl(d.total)}) ${d.total === d.pago_elemento_14 ? "é igual ao" : "difere do"} valor pago no elemento 14 “Diárias – civil” (${brl(d.pago_elemento_14)}).</p>` + fonteLinha(coletaCam("diarias"));
  ligaSeletores(() => SEC_CAM.diarias(el));
};

/* ---------- Despesas administrativas ---------- */
SEC_CAM.administrativas = async (el) => {
  const A = await carregar("camara/administrativas.json"), anos = Object.keys(A).map(Number), d = A[ESTADO.ano] || [], k = K[ESTADO.medida], ki = { empenhado: 2, liquidado: 3, pago: 4 }[ESTADO.medida];
  const total = d.reduce((s, x) => s + x[k], 0);
  const linhas = (L) => L.map((r) => `<tr><td>${esc(r[0])}</td><td>${esc(r[1])}</td><td class="n">${brl(r[2])}</td><td class="n">${brl(r[3])}</td><td class="n">${brl(r[4])}</td><td class="n">${r[5]}</td></tr>`).join("");
  const cab = `<thead><tr><th>Fornecedor</th><th>CNPJ / CPF</th><th class="n">Empenhado</th><th class="n">Liquidado</th><th class="n">Pago</th><th class="n">Empenhos</th></tr></thead>`;
  el.innerHTML = cabecalhoSecao("Despesas administrativas", "Serviços, materiais, tecnologia, equipamentos e locomoção contratados pela Câmara, por fornecedor. Em cada grupo, fornecedores ordenados pelo valor selecionado (critério único).") +
    `<div class="ferramentas">${seletorAno(anos)}${seletorMedida()}</div><div class="grade"><div class="card"><div class="k">Total das despesas administrativas (${MEDIDAS[ESTADO.medida].toLowerCase()})</div><div class="v">${brl0(total)}</div></div></div>` +
    d.map((g) => { const F = [...g.fornecedores].sort((a, b) => b[ki] - a[ki]); return `<details ${g === d[0] ? "open" : ""}><summary><strong>${esc(g.elemento)} – ${esc(g.nome)}</strong>: ${brl0(g[k])} (${PCT.format(g[k] / (total || 1))} das administrativas) · ${F.length} fornecedores</summary>` +
      `<div class="tabela-wrap"><table><caption>${esc(g.nome)}: ${F.length} fornecedores em ${ESTADO.ano}</caption>${cab}<tbody>${linhas(F.slice(0, 15))}</tbody></table></div>` +
      (F.length > 15 ? `<details><summary>Ver os outros ${F.length - 15} fornecedores</summary><div class="tabela-wrap"><table>${cab}<tbody>${linhas(F.slice(15))}</tbody></table></div></details>` : "") + `</details>`; }).join("") +
    fonteLinha(coletaCam("despesas_gerais"));
  ligaSeletores(() => SEC_CAM.administrativas(el));
};
