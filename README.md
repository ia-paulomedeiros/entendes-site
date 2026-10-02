# entendes.com.br

Site de apresentação do **Entendes**. O app fica em https://www.entendes.app.

O site é HTML e CSS estáticos:
- sem framework, sem JavaScript, sem rastreadores e sem cookies;
- fontes servidas daqui mesmo (Cormorant Garamond e Source Sans 3, licença OFL, em `fontes/`);
- publicado pelo GitHub Pages com o domínio `entendes.com.br` (arquivo `CNAME`).

## Arquivos

| Arquivo | O que é |
|---|---|
| `index.html` | a página única |
| `404.html` | página de erro |
| `estilo.css` | cores e fontes do app, com modo escuro automático |
| `og.png` | imagem de compartilhamento (1200×630) |
| `favicon.*`, `apple-touch-icon.png` | ícones, iguais aos do app |
| `robots.txt`, `sitemap.xml` | para os buscadores |

## Imagens

Todas são de domínio público e vêm do Wikimedia Commons. A licença foi conferida na página de cada arquivo em 02/10/2026, e nenhuma tem restrição NC. Nenhuma foi gerada por IA. Ficam em `imagens/`, convertidas para WebP em dois tamanhos.

| Arquivo | Origem | Licença no Commons | Uso |
|---|---|---|---|
| `filipe-eunuco-{claro,escuro}-{800,1600}.webp` | [Julius Schnorr von Carolsfeld, *Die Bibel in Bildern*, 1860, prancha 229](https://commons.wikimedia.org/wiki/File:Schnorr_von_Carolsfeld_Bibel_in_Bildern_1860_229.png) | `{{PD-Art|PD-old-auto-expired|deathyear=1872}}` | fundo do topo, sem moldura, tingido nas cores do tema |
| `rembrandt-batismo-eunuco-{600,960}.webp` | [Rembrandt, *O batismo do eunuco*, 1626, Museum Catharijneconvent](https://commons.wikimedia.org/wiki/File:Rembrandt,_The_Baptism_of_the_Eunuch,_1626,_Museum_Catharijneconvent,_Utrecht.jpg) | `{{PD-Art|PD-old-100-expired}}` | seção "O nome" |
| `biblia-1534-{claro,escuro}-{600,960}.webp` | [Página de rosto da Bíblia de Lutero, 1534; foto de Torsten Schleese](https://commons.wikimedia.org/wiki/File:Lutherbibel.jpg) | `{{PD-self}}` (o fotógrafo liberou a foto) | fundo bem esmaecido do chamado final |

Os créditos também aparecem no rodapé da página.

O símbolo vem de `src/lib/simbolo.ts`, no repositório do app. Se ele mudar, troque o `<svg>` das páginas e os ícones.

## Publicar no GitHub Pages

1. **Settings → Pages:** Source "Deploy from a branch", branch `main`, pasta `/ (root)`.
2. **Custom domain:** `entendes.com.br`. O arquivo `CNAME` já traz esse valor.
3. Depois que o DNS propagar, marque **Enforce HTTPS**.

## DNS do entendes.com.br

Os registros do GitHub Pages ficam ao lado dos de e-mail. Os registros MX, SPF, DKIM e DMARC da caixa `contato@entendes.com.br` continuam como estão.

| Tipo | Nome | Valor |
|---|---|---|
| A | @ | 185.199.108.153 |
| A | @ | 185.199.109.153 |
| A | @ | 185.199.110.153 |
| A | @ | 185.199.111.153 |
| AAAA | @ | 2606:50c0:8000::153 |
| AAAA | @ | 2606:50c0:8001::153 |
| AAAA | @ | 2606:50c0:8002::153 |
| AAAA | @ | 2606:50c0:8003::153 |
| CNAME | www | ia-paulomedeiros.github.io |

Antes, apague qualquer outro registro A, AAAA ou CNAME de `@` e de `www` que aponte para outro lugar, como uma página de "domínio estacionado".
