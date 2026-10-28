# Identidade visual: IA Gestão do Futuro

Este sistema segue a identidade oficial da marca IA Gestão do Futuro. Toda alteração de interface deve respeitar as regras abaixo. A fonte de verdade das cores e da tipografia é `tokens.css` (pasta `kit-ia`).

## Regra de ouro
Alterações visuais não mudam o comportamento do sistema. Não alterar regras de negócio, rotas, banco de dados, autenticação, variáveis de ambiente ou segredos ao adaptar a interface.

## Paleta oficial
| Cor | HEX | Uso |
| --- | --- | --- |
| Azul-noite | #0B1220 | fundos de destaque, títulos, navegação |
| Azul elétrico | #2563EB | cor principal, botões e links |
| Ciano | #06B6D4 | pequenos destaques; texto sobre ciano sempre em azul-noite |
| Branco gelo | #F8FAFC | fundo das áreas de conteúdo e leitura |
| Cinza ardósia | #64748B | textos de apoio sobre fundo claro |

Apoio de interface (derivados, não são cores de marca): azul hover #1D4ED8, linha #E2E8F0, e estados de sucesso, alerta e erro definidos em `tokens.css`. Não introduzir outras cores.

## Tipografia
Plus Jakarta Sans (arquivos em `fonts/`), pesos 400, 600, 700 e 800. Títulos em peso 800 (ou 700 em tamanhos pequenos), texto em 400, rótulos e botões em 700. Hospedar localmente, sem depender de CDN. O nome da marca é sempre imagem (logo), nunca texto reconstruído.

## Logos e ícones (pasta `assets/`)
- Cabeçalho claro: `logo.png` (letras escuras, fundo transparente).
- Áreas escuras (login, rodapé, abertura): `logo-claro.png`.
- Ícone isolado, avatar e favicon: `simbolo.png`, `favicon-32.png`, `favicon-64.png`, `apple-touch-icon.png`, `icon-192.png`, `icon-512.png`.
- Manter as proporções. Deixar área livre ao redor da logo equivalente, no mínimo, à altura da letra "I". Sem sombras, contornos, deformações, filtros ou aplicação sobre fotos cheias de detalhe.

## Estrutura de tela
- Cabeçalho claro com a logo principal à esquerda e navegação à direita.
- Conteúdo em superfícies claras (#F8FAFC e branco), com bastante espaço entre blocos.
- Abertura, tela de login e rodapé em azul-noite, com a logo clara.
- Cartões brancos com borda #E2E8F0 e raio de 16px. Botões com raio de 10px.

## Botões
- Principal: fundo #2563EB, texto branco, peso 700. Ex.: "Conheça as soluções".
- Secundário: contorno azul sobre fundo claro. Sobre fundo escuro: contorno branco translúcido.
- Ciano: texto azul-noite. Nunca texto branco pequeno sobre ciano.
- Desativado: contorno cinza claro, texto ardósia, cursor `not-allowed`.

## Tom de texto
Português do Brasil, direto e profissional, sem gírias. Frase de marca disponível para aberturas e rodapés: "Inteligência para gerir. Visão para crescer."

## Evitar
Gradientes, sombras pesadas, brilho, 3D, cores fora da paleta, ícones coloridos fora do azul e do ciano, fontes diferentes, texto menor que 14px em conteúdo importante, contraste abaixo de 4,5:1 em texto corrente.

## Acessibilidade e responsividade
Foco visível (anel ciano), alvos clicáveis de pelo menos 40px, rótulos em todos os campos, `alt` nas imagens informativas e `prefers-reduced-motion` respeitado. Toda tela deve funcionar de 360px a 1440px de largura.
