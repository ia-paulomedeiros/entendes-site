# entendes.com.br

Site de apresentação do **Entendes**. O app fica em https://www.entendes.app.

O site é HTML e CSS estáticos, com várias páginas:
- sem framework, sem rastreadores e sem cookies; gerado do banco por um GitHub Actions diário;
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

## Gerar as páginas de novo (automático, uma vez por dia)

As páginas de `index.html`, `404.html`, `sitemap.xml`, `estudos/`, `tradicoes/`, `como-funciona/` e `sobre/` são **geradas**: não edite à mão. O gerador fica em `scripts/gerar_site.py` (só Python 3.11, sem dependências).

### GitHub Actions

O workflow `.github/workflows/gerar-site.yml` ("Gerar o site") roda:
- **todo dia às 04:17 de Brasília** (07:17 UTC);
- e **quando alguém pede**: aba **Actions → Gerar o site → Run workflow**.

Ele lê o banco só para leitura, com a chave pública **anon**, pela API pública do Supabase. O RLS do app só mostra à anon os estudos publicados e as fontes liberadas. Depois roda os testes e **faz commit só se algo mudou**: a data de `dados/site.json` só muda quando os dados mudam. Por fim, o GitHub Pages publica.

**Segredo necessário (o dono cria uma vez):** `SUPABASE_ANON_KEY`.

1. No Supabase, abra o projeto **BibliandoApp** e vá em **Project Settings → API Keys**. Na aba **Legacy API keys**, copie a chave **`anon` `public`** (começa com `eyJ`). A chave publicável nova (`sb_publishable_…`) também funciona. **Nunca** use a `service_role` nem a `secret`.
2. No GitHub, abra o repositório `entendes-site` e vá em **Settings → Secrets and variables → Actions → New repository secret**.
3. Em **Name**, escreva `SUPABASE_ANON_KEY`; em **Secret**, cole a chave. Clique em **Add secret**.
4. Vá em **Actions → Gerar o site → Run workflow** para a primeira rodada. Sem o segredo, o workflow para no passo "Conferir o segredo", com a mensagem de erro.
5. Se o passo do commit falhar com erro de permissão, confira em **Settings → Actions → General → Workflow permissions** se o repositório deixa o workflow escrever (o arquivo já pede `contents: write`).

### Rodar à mão

```sh
export SUPABASE_ANON_KEY=...       # chave anon pública; nunca no Git
python3 scripts/gerar_site.py      # lê o banco, grava dados/site.json e gera as páginas
python3 -m unittest discover -s tests
```

- Sem a chave anon, o gerador usa `SUPABASE_ACCESS_TOKEN` (token pessoal), pela rota `database/query/read-only` da Management API. Os dois caminhos devolvem os mesmos dados (conferido em 04/10/2026).
- `python3 scripts/gerar_site.py --sem-banco` gera as páginas a partir de `dados/site.json`, sem acesso ao banco, por exemplo depois de mudar o visual.
- `dados/site.json` é o retrato do que foi lido e entra no Git, para a revisão mostrar o que mudou. Ele só traz dados públicos:
  - dos estudos publicados: título, tipo, tema, referências, data, tradições comparadas, as obras citadas e as duas primeiras afirmações das concordâncias e das divergências;
  - das fontes liberadas: título e autor.

  O texto das fontes e o estudo inteiro ficam no app.
- O gerador apaga e refaz as pastas geradas: um estudo despublicado some do site na próxima geração.
- As tradições vêm da tabela `tradicoes`: as de status `fase_2` aparecem como "em breve", sem página própria.

## Imagens

Todas são de domínio público, do Wikimedia Commons ou do Flickr. A licença foi conferida na página de cada arquivo, e nenhuma tem restrição NC. Nenhuma foi gerada por IA, e nenhuma representa Deus ou Cristo. Ficaram de fora, pela regra de neutralidade: a foto do interior do Mosteiro de Sinaia (afrescos com Cristo) e a *Paisagem com São Jerônimo penitente* (Art Institute of Chicago), em que o santo segura um crucifixo com Cristo. As imagens do Art Institute são baixadas com o cabeçalho `AIC-User-Agent: Entendes (contato@entendes.com.br)`, como o museu pede na documentação da API. A imagem de cada página fica em `IMAGENS`, `IMAGEM_ESTUDO`, `IMAGEM_TRADICAO` e `IMAGEM_PAGINA`, em `scripts/gerar_site.py` (uma por página, no máximo). Ficam em `imagens/`, convertidas para WebP em dois tamanhos.

| Arquivo | Origem | Licença no Commons | Uso |
|---|---|---|---|
| `filipe-eunuco-{claro,escuro}-{800,1600}.webp` | [Julius Schnorr von Carolsfeld, *Die Bibel in Bildern*, 1860, prancha 229](https://commons.wikimedia.org/wiki/File:Schnorr_von_Carolsfeld_Bibel_in_Bildern_1860_229.png) | `{{PD-Art|PD-old-auto-expired|deathyear=1872}}` | fundo do topo, sem moldura, tingido nas cores do tema |
| `rembrandt-batismo-eunuco-{600,960}.webp` | [Rembrandt, *O batismo do eunuco*, 1626, Museum Catharijneconvent](https://commons.wikimedia.org/wiki/File:Rembrandt,_The_Baptism_of_the_Eunuch,_1626,_Museum_Catharijneconvent,_Utrecht.jpg) | `{{PD-Art|PD-old-100-expired}}` | seção "O nome" |
| `biblia-1534-{claro,escuro}-{600,960}.webp` | [Página de rosto da Bíblia de Lutero, 1534; foto de Torsten Schleese](https://commons.wikimedia.org/wiki/File:Lutherbibel.jpg) | `{{PD-self}}` (o fotógrafo liberou a foto) | fundo bem esmaecido do chamado final |
| `igreja-zlatari-bucareste-{480,768}.webp` | [Igreja de Zlătari (São Cipriano), Bucareste; foto de M. Cristian-Ioan, 2005, Flickr](https://www.flickr.com/photos/sky-clouds/55404283986/) | Public Domain Mark 1.0 (conferida na página da foto em 03/10/2026; uso aprovado pelo dono do projeto) | página da tradição Ortodoxa |
| `rembrandt-davi-oracao-{480,768}.webp` | [Rembrandt, *Davi em oração*, 1652, gravura, Art Institute of Chicago](https://www.artic.edu/artworks/48960) | `is_public_domain: true` na API do museu (conferido em 03/10/2026); imagem em CC0 | estudo Salmos 51.5 |
| `ribera-pedro-penitente-{480,768}.webp` | [Jusepe de Ribera, *São Pedro penitente*, c. 1630, Art Institute of Chicago](https://www.artic.edu/artworks/120172) | `is_public_domain: true` na API do museu (conferido em 03/10/2026); imagem em CC0 | estudo Confissão e perdão dos pecados |
| `salomao-rainha-saba-{480,768}.webp` | [Mestre do Grupo da Adoração de Antuérpia, *O rei Salomão recebe a rainha de Sabá*, 1515-20, Art Institute of Chicago](https://www.artic.edu/artworks/111670) (detalhe, a parte de baixo do painel) | `is_public_domain: true` na API do museu (conferido em 03/10/2026); imagem em CC0 | Como funciona |
| `lucas-van-leyden-expulsao-{480,768}.webp` | [Lucas van Leyden, *A expulsão do Paraíso*, 1510, gravura, Art Institute of Chicago](https://www.artic.edu/artworks/106566) | `is_public_domain: true` na API do museu (conferido em 03/10/2026); imagem em CC0 | estudos Pecado original, Romanos 5.12 e Gênesis 3.15 |

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
