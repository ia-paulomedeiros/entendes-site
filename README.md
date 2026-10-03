# entendes.com.br

Site de apresentação do **Entendes**. O app fica em https://www.entendes.app.

O site é HTML e CSS estáticos, com várias páginas:
- sem framework, sem rastreadores e sem cookies;
- JavaScript só no filtro da lista de estudos (sem ele, a lista inteira aparece); o menu de celular funciona sem JavaScript;
- fontes servidas daqui mesmo (Cormorant Garamond e Source Sans 3, licença OFL, em `fontes/`);
- publicado pelo GitHub Pages com o domínio `entendes.com.br` (arquivo `CNAME`).

## Páginas

| Endereço | O que é |
|---|---|
| `/` | início: chamada, estudos recentes, como funciona, tradições e o nome |
| `/estudos/` | todos os estudos publicados, com filtro por texto, tipo (tema ou passagem) e livro |
| `/estudos/<slug>/` | um estudo: resumo, referências, tradições comparadas, as duas primeiras concordâncias e divergências, obras citadas e o botão "Ler o estudo completo no app" (`https://www.entendes.app/estudos/<slug>`) |
| `/tradicoes/` | as tradições com acervo e as que entram em breve (Anglicana e Adventista, sem página própria) |
| `/tradicoes/<id>/` | uma tradição: principais documentos e autores do acervo e os estudos em que aparece |
| `/como-funciona/` | acervo, como um estudo é feito, as conferências antes de publicar e os rótulos |
| `/sobre/` | o nome (Atos 8), os princípios, o contato e os créditos das imagens |

Menu fixo no topo; no celular, o menu abre num botão. O rodapé de todas as páginas traz o contato.

Arquivos fixos, que o gerador não toca: `estilo.css` (cores e fontes do app, com modo escuro automático), `og.png` (imagem de compartilhamento, 1200×630), `favicon.*` e `apple-touch-icon.png` (iguais aos do app), `robots.txt`, `CNAME`, `.nojekyll`, `fontes/` e `imagens/`.

## Gerar as páginas de novo (quando sair estudo novo)

As páginas de `index.html`, `404.html`, `sitemap.xml`, `estudos/`, `tradicoes/`, `como-funciona/` e `sobre/` são **geradas**: não edite à mão. O gerador fica em `scripts/gerar_site.py` (só Python 3.11, sem dependências):

```sh
export SUPABASE_ACCESS_TOKEN=...   # token pessoal da Management API do Supabase; nunca no Git
python3 scripts/gerar_site.py      # lê o banco, grava dados/site.json e gera as páginas
python3 -m unittest discover -s tests
git add -A && git commit -m "Site: estudos de <data>" && git push
```

- O banco é lido **só para leitura**, pela rota `database/query/read-only` da Management API, no projeto BibliandoApp (São Paulo).
- `dados/site.json` é o retrato do que foi lido. Ele entra no Git para a revisão mostrar o que mudou e para `python3 scripts/gerar_site.py --sem-banco` gerar as páginas sem acesso ao banco, por exemplo depois de mudar o visual.
- O retrato só traz dados públicos:
  - dos estudos publicados: título, tipo, tema, referências, data, tradições comparadas, as obras citadas e as duas primeiras afirmações das concordâncias e das divergências;
  - das fontes liberadas: título e autor.

  O texto das fontes e o estudo inteiro ficam no app.
- O gerador apaga e refaz as pastas geradas: um estudo despublicado some do site na próxima geração.
- As tradições vêm da tabela `tradicoes`: as de status `fase_2` aparecem como "em breve", sem página própria.
- Ainda não há automação. Depois, um GitHub Actions pode rodar o mesmo comando.

## Imagens

Todas são de domínio público e vêm do Wikimedia Commons. A licença foi conferida na página de cada arquivo em 02/10/2026, e nenhuma tem restrição NC. Nenhuma foi gerada por IA. Ficam em `imagens/`, convertidas para WebP em dois tamanhos.

| Arquivo | Origem | Licença no Commons | Uso |
|---|---|---|---|
| `filipe-eunuco-{claro,escuro}-{800,1600}.webp` | [Julius Schnorr von Carolsfeld, *Die Bibel in Bildern*, 1860, prancha 229](https://commons.wikimedia.org/wiki/File:Schnorr_von_Carolsfeld_Bibel_in_Bildern_1860_229.png) | `{{PD-Art|PD-old-auto-expired|deathyear=1872}}` | fundo do topo, sem moldura, tingido nas cores do tema |
| `rembrandt-batismo-eunuco-{600,960}.webp` | [Rembrandt, *O batismo do eunuco*, 1626, Museum Catharijneconvent](https://commons.wikimedia.org/wiki/File:Rembrandt,_The_Baptism_of_the_Eunuch,_1626,_Museum_Catharijneconvent,_Utrecht.jpg) | `{{PD-Art|PD-old-100-expired}}` | seção "O nome" |
| `biblia-1534-{claro,escuro}-{600,960}.webp` | [Página de rosto da Bíblia de Lutero, 1534; foto de Torsten Schleese](https://commons.wikimedia.org/wiki/File:Lutherbibel.jpg) | `{{PD-self}}` (o fotógrafo liberou a foto) | fundo bem esmaecido do chamado final |

Os créditos aparecem no rodapé de todas as páginas e na página Sobre (`/sobre/#creditos`). Imagem nova entra em `CREDITOS`, em `scripts/gerar_site.py`, e nesta tabela, com a licença conferida na fonte.

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
