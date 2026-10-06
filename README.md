# Contas de Primavera (nome provisório)

Impostômetro de Primavera do Leste (MT) com dados **oficiais** do Portal da Transparência (Fiorilli SCPI, API JSON pública).
Apartidário: só números da fonte, com data/hora da coleta e link. Projeto independente, sem vínculo com Prefeitura, Câmara ou partidos.

**Estado atual: Fase 4 concluída** (atualização diária automática, alertas, compartilhamento, metodologia, deploy). Detalhamento da verba indenizatória = Fase 5 (depende da resposta da Câmara).

## Como rodar (Python 3.9+, sem dependências externas)

```bash
cd impostometropva
python3 -m contas coletar --anos 2026          # carga do ano corrente (≈2 min; 1 download de ~42 MB)
python3 -m contas validar --anos 2026          # confere soma dos empenhos × totais do portal
python3 -m contas publicar                     # gera web/data/*.json
python3 -m contas diario                       # coletar + validar + publicar (o que o agendador roda)
python3 -m http.server -d web 8000             # ver o site em http://localhost:8000
python3 -m unittest discover -s tests -t .     # testes
```

Câmara (mesmos comandos com `--entidade camara`; a Prefeitura continua sendo o padrão):

```bash
python3 -m contas coletar  --entidade camara --anos 2026      # despesas, mensal, receitas, licitações, contratos, folha (mês a mês), diárias, repasses
python3 -m contas derivar  --entidade camara --anos 2026      # vínculos nome↔vereador + verba indenizatória (sem rede)
python3 -m contas validar  --entidade camara --anos 2026
python3 -m contas publicar --entidade camara                  # gera web/data/camara/*.json
```

Histórico (uma vez): `python3 -m contas coletar --anos 2025 2024 --so despesas totais mensal receitas`, depois `validar --anos 2024 2025 2026` e `publicar`.
Opções úteis: `--so despesas|totais|mensal|receitas|licitacoes|contratos|folha|ibge`, `--force` (rebaixa mesmo se já houver download de hoje), `--db caminho.sqlite`.
Códigos de saída: `0` ok, `1` falha de coleta, `2` divergência de validação (usar no agendador para alertar).

### Agendar

**Recomendado: GitHub Actions** (grátis; ver "Publicar na internet" abaixo). Alternativa local, com `cron`, uma vez por dia de madrugada:

```
17 4 * * *  cd /caminho/impostometropva && CONTAS_CONTATO="seu-email@exemplo.com" /usr/bin/python3 -m contas diario >> data/diario.log 2>&1
```

`diario` faz, para Prefeitura **e** Câmara: coleta completa do ano corrente (1 download pesado por entidade) → confere os totais → registra alertas → publica JSONs. Às segundas-feiras (ou com `--completo`) revisa também os 2 anos anteriores; se faltar algum ano no banco (cache perdido), reconstrói sozinho. Se a conferência acusar divergência (código de saída 2), **não publica**.

## Como funciona

```
portal Fiorilli ──► contas/coleta/*  ──► SQLite (data/contas.sqlite)  ──► contas/validar.py ──► contas/publicar.py ──► web/data/*.json ──► site estático (web/)
```

- O **site nunca consulta o portal**: lê JSON pré-gerado. O portal recebe 1 coleta pesada por dia.
- Respeito ao servidor: User-Agent identificado, pausa de 2 s entre chamadas, retry com espera (5/15/45 s), download em disco, reuso do download do dia (`data/raw/`, fora do git).
- Valores em **centavos inteiros** (sem erro de ponto flutuante). Datas em ISO.
- Cada coleta grava em `execucao_coleta` (início, fim, status, registros, bytes, URL, erro).
- Coletas são idempotentes: o exercício é substituído numa transação; se der erro, o que havia continua.

### Regras de dados descobertas na Fase 1 (e codificadas)

| Regra | Onde |
|---|---|
| `EMPENHADO/LIQUIDADO/PAGO` já são líquidos; linhas de anulação (AN/DA) vêm negativas. **Não subtrair `ANULADO` de novo.** | `coleta/despesas.py`, teste `test_subtrair_anulado_de_novo_nao_bate` |
| Chave do empenho é `PKEMP` (número+tipo colide). Órgão = 4 primeiros dígitos de `CODLO`. | `db.py`, `despesas.py` |
| `DespesasPorFornecedor` com período mensal devolve valores **do mês**; `DespesasPorOrgao` devolve liquidado/pago **acumulados** (só o empenhado é do mês). | `coleta/mensal.py` |
| Receita é árvore com códigos repetidos: só linhas `ORDEM = 1` (correntes, capital, deduções) podem ser somadas. | `coleta/receitas.py` |
| Modalidade de licitação = campo `LICIT` (texto). `LICITACAO` é só o sequencial. | `coleta/licitacoes.py` |
| Folha: nomes de servidores **nunca** são gravados (Prefeitura); grupos com < 3 pessoas viram "Outros". | `coleta/pessoal.py`, `config.K_ANONIMATO` |
| Dados bancários/logins de `OrdemPagto_*` **nunca** são coletados. CPF só mascarado, como vem. | (nenhum coletor os lê); teste de publicação |

### Validação (automática, a cada `diario`)

Soma dos empenhos × totais do portal (por órgão e por fornecedor), ao centavo; por órgão; integridade fornecedor; soma dos 12 meses × anual; receita (meses × ano). Resultado em `validacao` e na página **Metodologia**.
"Aviso" = diferença esperada por horário (o portal é "vivo"); "divergente" = problema real e o comando sai com código 2.

## Publicar na internet (GitHub Pages + GitHub Actions: custo zero)

Por que assim: o site é 100% estático (HTML + JSON), então não precisa de servidor; o Pages hospeda de graça e o Actions roda a coleta diária. O banco SQLite não vai para o Git: fica no cache do Actions (`actions/cache`, ~10 MB compactado) e, se o cache for apagado, a execução seguinte reconstrói os 3 anos (≈20–30 min). Alternativa equivalente: Cloudflare Pages (também grátis; útil se quiser domínio próprio com CDN) publicando a pasta `dist/` gerada por `python3 -m contas build`.

Passo a passo (uma vez):

1. Criar um repositório no GitHub e enviar este projeto (`.gitignore` já exclui banco, downloads e `web/data/`).
2. Em **Settings → Pages → Build and deployment → Source: GitHub Actions**.
3. Em **Settings → Secrets and variables → Actions → Variables**: `CONTAS_CONTATO` = e-mail ou site para contato (entra no User-Agent enviado ao portal, para a prefeitura poder falar com você; não fica no código).
4. (Opcional) Em **Secrets**: `ALERTA_WEBHOOK_URL` = endereço de webhook (Slack, Discord, Telegram via ponte, n8n…) para receber os alertas novos.
5. Preencher `config/site.json` (`url_site` do Pages e `contato` que aparece na Metodologia) e fazer commit.
6. **Actions → Atualização diária → Run workflow** (a primeira execução reconstrói o histórico). Depois roda sozinha todo dia às 03:17 de Cuiabá.

Se algo falhar o job fica vermelho e o GitHub envia e-mail; o site continua com a última versão publicada. Domínio próprio (opcional): Settings → Pages → Custom domain (um `.com.br` custa cerca de R$ 40 por ano no Registro.br).

### Publicar também na Vercel (opcional)

O site é estático, então a Vercel só hospeda a pasta `dist/` que a execução diária gera (os dados não ficam no Git; por isso a Vercel não "puxa" do repositório: **o GitHub Actions envia** o site pronto, depois de conferido). Passo a passo (uma vez):

1. Conta em vercel.com (o plano *Hobby* é gratuito, mas de uso não comercial) e `npx vercel@latest login`.
2. Na pasta do projeto: `npx vercel@latest link --yes --project contas-de-primavera` (cria o projeto e o arquivo local `.vercel/project.json` com os identificadores).
3. Criar um token em vercel.com/account/tokens (escopo da sua conta, com validade) e guardar no GitHub: `gh secret set VERCEL_TOKEN --repo admedgar/contas-de-primavera` (cole o token no prompt; ele nunca vai para o código).
4. Gravar os identificadores como variáveis do repositório: `VERCEL_ORG_ID` e `VERCEL_PROJECT_ID` (valores de `.vercel/project.json`).
5. Rodar o workflow "Atualização diária". O passo "Publicar na Vercel" só roda se `VERCEL_TOKEN` existir e a conferência dos dados tiver passado.
6. Atualizar `url_site` em `config/site.json` para o endereço da Vercel (para a imagem de prévia e o feed). O GitHub Pages pode continuar como reserva ou ser desativado.

`web/vercel.json` define cabeçalhos de segurança e cache curto para `/data/`.

### Configurações versionadas (`config/`)

| Arquivo | Para quê |
|---|---|
| `alertas.json` | Limites dos alertas (empenho, dispensa/inexigibilidade, contrato; por entidade) e janela de dias. |
| `site.json` | `url_site` (metadados de compartilhamento, sitemap, feed) e `contato`. |
| `validacao_conhecida.json` | Divergências que existem **na própria fonte**, já verificadas (viram "aviso" só enquanto a diferença for exatamente a registrada). |
| `vinculos_vereadores.csv` | Decisões humanas de vínculo favorecido ↔ vereador. |

### Alertas, feed e compartilhamento

- `Novidades` (`#/novidades`) lista **registros novos** do portal (empenhos e contratos) acima dos limites ou por dispensa/inexigibilidade. A 1ª coleta de cada entidade é só linha de base (não alerta); só entram registros dos últimos 45 dias; anulações e empenhos de folha em nome do próprio ente ficam de fora. O texto é neutro e o nome/histórico de pessoas físicas beneficiárias segue a política de privacidade. Feed Atom em `data/alertas.xml`.
- Botão **Compartilhar imagem** gera no navegador um cartão 1080×1080 (a estimativa aparece rotulada, com o valor real coletado e a fonte) e usa o compartilhamento do celular; também há link de WhatsApp com texto. A pré-visualização de links (`og.png`) é gerada no build com os números reais do dia.

## Câmara (Fase 3)

- **Vereadores** são as únicas pessoas com nome na folha. Critério: cargo que **começa com "Vereador"** (inclui "Vereador suplente"). Os demais servidores só entram agregados (grupos < 3 pessoas viram "Outros"); nomes de não vereadores são descartados em memória.
- **Vínculo nome↔vereador (`config/vinculos_vereadores.csv`)**: um favorecido só é somado a um vereador se (a) CPF mascarado e nome são idênticos (ignorando acento/espaço) ou (b) há linha `confirmar` nesse arquivo, decidida por um responsável. Casos duvidosos (ex.: nome igual com CNPJ) viram "sugerido": ficam **fora** das somas e aparecem em *Metodologia* e no relatório de validação. Formato da linha: `123;Nome Do Vereador;confirmar;nota`.
- **Mês de exercício** = mês com proventos > 0 na folha; todas as médias mensais usam esse divisor para todos os vereadores. Tabela sempre em ordem alfabética por padrão.
- **Verba indenizatória** (valor recebido; origem API): empenhos do elemento 93 cujo histórico cita "verba indenizatória"; os demais do 93 são "reembolsos". Mês = mês do *empenho* (a data do pagamento exigiria uma chamada por empenho); a competência (ex.: "REF: 01/2026") é lida do histórico quando existe. Tabela `verba_indenizatoria_item` (vereador, mês, categoria, fornecedor, valor, documento) **existe e está vazia**, pronta para a Fase 5. A interface mostra o aviso "Detalhamento de como cada vereador gastou a verba em breve" com link à página oficial. **Os PDFs da Câmara nunca são baixados nem lidos** (o robots do site proíbe até a Câmara autorizar).
- **Passagens aéreas**: o favorecido é a agência; só entram na ficha se o histórico citar **um** passageiro com o nome completo do vereador. Ficam fora do comparativo (critério não uniforme).
- **Repasses**: vêm da consulta `Transf` do portal da **Prefeitura** (traz repasse e devolução); a consulta da Câmara só mostra recebimentos, na coluna `DEVOLUCAO`.
- **Custo da Câmara**: despesa ÷ habitantes (IBGE); ÷ receita corrente arrecadada da Prefeitura; pago ÷ repasse líquido.

## Privacidade de pessoas físicas (todas as entidades)

Política padrão `CONTAS_PF=beneficiarios` (`config.PF_POLITICA`): nas listas publicadas de empenhos/fornecedores, **nome, documento e histórico** são omitidos para pagamentos a pessoas que não são fornecedoras (diárias, auxílios financeiros, premiações, sentenças, reembolsos, folha), inclusive quando o favorecido tem CNPJ de microempreendedor com o próprio nome nos elementos 14, 31 e 48. Prestadores de serviço/material (elementos 30, 35, 36, 37, 39, 40, 51, 52) continuam como no portal. Totais não mudam. `CONTAS_PF=portal` publica tudo como o portal; `CONTAS_PF=todos` omite toda pessoa física. Motivo: os históricos oficiais citam pacientes, beneficiários de programas sociais etc.

## Estrutura

```
contas/            pacote Python (config, http, parsers, db, coleta/*, validar, publicar, publicar_camara, cli)
config/            decisões humanas versionadas (vinculos_vereadores.csv)
tests/             testes (unittest) de parsers, coletores, validação, privacidade, publicação
web/               site estático (index.html, app.js, style.css) e web/data/ (JSON gerado)
fase1/             relatório e amostras da validação técnica (amostras sem dados sensíveis)
data/              banco SQLite e downloads brutos (não versionados)
```

## Plano de manutenção (se o portal mudar)

0. **Rotina**: ver o e-mail/aba Actions só se o job ficar vermelho. A página Metodologia mostra, por fonte, o último sucesso e erros.

1. **Formato mudou** (campo sumiu/renomeado): o coletor levanta `FormatoMudou` listando os campos ausentes, grava `erro` em `execucao_coleta`, **não altera o banco**, e o site continua com os últimos dados bons (a data da coleta mostra o atraso; após 3 dias o contador para e avisa).
2. **Totais não batem** (`validar` sai com código 2): não publicar; comparar `validacao.detalhe` com o portal; usual causa = tipo novo de empenho ou mudança de semântica de campo.
3. **Endpoint fora do ar / HTTP 5xx**: retry automático; se persistir, tentar no dia seguinte (nada a fazer).
4. **Novo tipo de empenho** (como AD/DA, descobertos na Fase 2): é gravado como vem e entra nas somas; só adicionar explicação em "Entenda".
5. **Divergência nova na conferência** (job vermelho, nada publicado): comparar com o portal; se for um defeito da própria fonte, registrar em `config/validacao_conhecida.json` (com a diferença exata e a nota); se for do coletor, corrigir e adicionar teste.
6. **Cache do banco perdido**: nada a fazer; a execução seguinte reconstrói (os alertas voltam a ter uma nova linha de base, sem enxurrada).
7. **Limites de alerta** muito altos/baixos: editar `config/alertas.json`.
8. Rodar `python3 -m unittest` antes de publicar qualquer ajuste de parser; adicionar um teste com o registro que quebrou.

## Limites conhecidos (Fase 2)

- Notas fiscais, ordens de pagamento e itens por empenho não são baixados em massa (seriam ~20 mil chamadas/dia); o site aponta para o portal oficial.
- `web/data/prefeitura/empenhos_ANO.json` tem ~6 MB (cerca de 1 MB comprimido); se necessário, dividir por mês.
- Excel: exportação em CSV (`;`, UTF-8 com BOM, vírgula decimal), que o Excel em português abre direto.
- População IBGE: só 2024–2026 (a série pula os anos do Censo).
