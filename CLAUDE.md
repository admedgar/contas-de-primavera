# Transparência Primavera

Impostômetro apartidário de Primavera do Leste-MT. Detalhes técnicos, fases e política de privacidade no `README.md`.

## Interface
Seguir a identidade da marca em `kit-ia/CLAUDE.md`. Os tokens (cores, fontes) ficam em `web/marca/tokens.css` e são a fonte única; `web/style.css` só mapeia as variáveis do site para eles. Decisões deste projeto:
- O nome do site é "Transparência Primavera" (texto no cabeçalho). A logo da marca aparece só como assinatura no rodapé, porque o projeto se apresenta como independente.
- Somente tema claro (sem `prefers-color-scheme: dark`). Gráficos usam azul elétrico e ciano.
- O rodapé obrigatório ("Dados do Portal da Transparência oficial. Projeto independente, sem vínculo com a Prefeitura, Câmara ou partidos.") não muda.
- Mudança visual nunca altera dados, coleta, validação, rotas (`#/prefeitura|camara|novidades|entenda|metodologia`) nem textos de fonte e data de coleta.
