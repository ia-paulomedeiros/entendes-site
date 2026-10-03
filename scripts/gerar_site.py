#!/usr/bin/env python3
"""Gera as páginas do site entendes.com.br a partir do banco do Entendes (só leitura).

Uso:
  python3 scripts/gerar_site.py             # lê o banco, grava dados/site.json e gera as páginas
  python3 scripts/gerar_site.py --sem-banco # gera as páginas a partir de dados/site.json

Rode de novo quando sair estudo novo. O banco é lido pela consulta SÓ DE LEITURA da Management
API do Supabase (projeto BibliandoApp, São Paulo), com o token pessoal em SUPABASE_ACCESS_TOKEN
(nunca no Git). Só entram dados públicos: estudos publicados (título, referências, tradições,
as duas primeiras concordâncias e divergências) e os títulos e autores das fontes liberadas.
Nada do texto das fontes nem do estudo inteiro: o estudo completo fica no app.

Sem dependências: só a biblioteca padrão do Python 3.11.
"""
from __future__ import annotations

import argparse
import html
import json
import os
import re
import shutil
import sys
import urllib.request
from datetime import date
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
DADOS = RAIZ / "dados" / "site.json"
PROJETO = "acamorsjdrfbactkfywo"  # BibliandoApp (sa-east-1); nunca o projeto antigo dos EUA
API_LEITURA = f"https://api.supabase.com/v1/projects/{PROJETO}/database/query/read-only"

SITE = "https://entendes.com.br"
APP = "https://www.entendes.app"
EMAIL = "contato@entendes.com.br"
INSTAGRAM = "https://www.instagram.com/entendes.app"
# Pastas e arquivos que o gerador escreve (e apaga antes de escrever de novo)
PASTAS_GERADAS = ["estudos", "tradicoes", "como-funciona", "sobre"]
ARQUIVOS_GERADOS = ["index.html", "404.html", "sitemap.xml"]

# Quantas afirmações de concordâncias e de divergências vão para o site (o resto fica no app)
AFIRMACOES_POR_BLOCO = 2
ROTULO_SINTESE = "Síntese gerada a partir das fontes"

# ------------------------------------------------------------------ leitura do banco

CONSULTAS = {
    "tradicoes": """
        select id, nome, sigla, grupo, status, ordem from public.tradicoes order by ordem""",
    "subtradicoes": """
        select tradicao_id, id, nome from public.subtradicoes order by tradicao_id, id""",
    "livros": """
        select codigo, nome, abreviacao, testamento, ordem from public.livros_biblicos order by ordem""",
    "fontes": """
        select f.id, f.titulo, f.autor, f.tipo_autoridade, f.papel_no_app
        from public.fontes f where f.liberada order by f.id""",
    # obras de cada tradição no acervo: com trechos, sem Bíblia, fora das listas de exclusão
    "obras_por_tradicao": """
        select t.tradicao_id, t.fonte_id, count(*)::int as trechos
        from public.trechos t join public.fontes f on f.id = t.fonte_id
        where f.liberada and f.papel_no_app <> 'biblia' and t.tipo <> 'indice' and t.tradicao_id is not null
          and f.id not in (select fonte_id from public.fontes_fora_da_busca)
          and f.id not in (select fonte_id from public.fontes_fora_da_comparacao)
        group by 1, 2 order by 1, 3 desc""",
    "estudos": f"""
        select e.slug, e.versao, e.tipo, e.titulo, e.tema, e.referencias, e.resumo,
               e.publicado_em::date::text as publicado_em, e.atribuicoes, e.licencas_derivadas,
               (select json_agg(json_build_object(
                  'tipo', s.tipo, 'tradicao_id', s.tradicao_id, 'subtradicao_id', s.subtradicao_id,
                  'sem_material', s.sem_material_suficiente,
                  'afirmacoes', (select coalesce(json_agg(a.texto order by a.ordem), '[]'::json)
                                 from public.estudo_afirmacoes a
                                 where a.secao_id = s.id and s.tipo in ('concordancias', 'divergencias')
                                   and a.ordem <= {AFIRMACOES_POR_BLOCO}),
                  'fontes', (select coalesce(json_agg(distinct t.fonte_id), '[]'::json)
                             from public.estudo_afirmacoes a
                             join public.citacoes c on c.afirmacao_id = a.id
                             join public.trechos t on t.id = c.trecho_id
                             where a.secao_id = s.id)
                ) order by s.ordem) from public.estudo_secoes s where s.estudo_id = e.id) as secoes
        from public.estudos e where e.status = 'publicado'
        order by e.publicado_em desc, e.slug""",
}


def consultar(sql: str) -> list[dict]:
    """Uma consulta pela rota só de leitura da Management API."""
    cab = {"content-type": "application/json", "user-agent": "entendes-site/1.0"}
    token = os.environ.get("SUPABASE_ACCESS_TOKEN")
    if token:
        cab["authorization"] = f"Bearer {token}"
    req = urllib.request.Request(API_LEITURA, data=json.dumps({"query": sql}).encode(), headers=cab, method="POST")
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read())


def ler_banco() -> dict:
    dados = {nome: consultar(sql) for nome, sql in CONSULTAS.items()}
    dados["gerado_em"] = date.today().isoformat()
    return dados


# ------------------------------------------------------------------ modelo

class Site:
    """Os dados do banco já organizados para as páginas."""

    def __init__(self, d: dict):
        self.gerado_em: str = d["gerado_em"]
        self.tradicoes = [t for t in d["tradicoes"]]
        self.trad = {t["id"]: t for t in self.tradicoes}
        self.disponiveis = [t for t in self.tradicoes if t["status"] in ("ativo", "acervo_em_construcao")]
        self.em_breve = [t for t in self.tradicoes if t["status"] == "fase_2"]
        self.sub = {(s["tradicao_id"], s["id"]): s["nome"] for s in d["subtradicoes"]}
        self.livros = {l["codigo"]: l for l in d["livros"]}
        self.fontes = {f["id"]: f for f in d["fontes"]}
        self.obras: dict[str, list[dict]] = {}
        for o in d["obras_por_tradicao"]:
            if o["fonte_id"] in self.fontes:
                self.obras.setdefault(o["tradicao_id"], []).append(o)
        self.estudos = [e for e in d["estudos"] if e.get("secoes")]

    # referências
    def ref_extenso(self, ref: str) -> str:
        """'ROM.9.16' → 'Romanos 9.16'; 'ROM.9' → 'Romanos 9'."""
        livro, _, resto = ref.partition(".")
        nome = self.livros.get(livro, {}).get("nome", livro)
        return f"{nome} {resto}".strip()

    def livros_do_estudo(self, e: dict) -> list[str]:
        codigos = {r.split(".")[0] for r in e["referencias"]}
        return [c for c in sorted(codigos, key=lambda c: self.livros.get(c, {}).get("ordem", 999))]

    # seções
    def secoes_tradicao(self, e: dict) -> list[dict]:
        return [s for s in e["secoes"] if s["tipo"] == "tradicao" and s["tradicao_id"] in self.trad]

    def nome_secao(self, s: dict) -> str:
        nome = self.trad[s["tradicao_id"]]["nome"]
        sub = self.sub.get((s["tradicao_id"], s.get("subtradicao_id")))
        return f"{nome} ({sub.lower()})" if sub else nome

    def bloco(self, e: dict, tipo: str) -> list[str]:
        for s in e["secoes"]:
            if s["tipo"] == tipo:
                return list(s["afirmacoes"])[:AFIRMACOES_POR_BLOCO]
        return []

    def fontes_do_estudo(self, e: dict) -> dict[str, list[dict]]:
        """Obras citadas, por tradição (na ordem do app)."""
        saida: dict[str, list[dict]] = {}
        for s in self.secoes_tradicao(e):
            obras = [self.fontes[f] for f in s["fontes"] if f in self.fontes]
            if obras:
                saida[s["tradicao_id"]] = sorted(obras, key=lambda f: (f["autor"] or "", f["titulo"]))
        return saida

    def resumo(self, e: dict) -> str:
        if e.get("resumo"):
            return e["resumo"]
        com = [self.trad[s["tradicao_id"]]["nome"] for s in self.secoes_tradicao(e) if not s["sem_material"]]
        sem = [self.trad[s["tradicao_id"]]["nome"] for s in self.secoes_tradicao(e) if s["sem_material"]]
        n_obras = len({f["id"] for lista in self.fontes_do_estudo(e).values() for f in lista})
        assunto = self.assunto(e)
        texto = f"Como as tradições {juntar(com)} leem {assunto}, com base em {n_obras} obras do acervo."
        if sem:
            quem = f"a tradição {sem[0]}" if len(sem) == 1 else f"as tradições {juntar(sem)}"
            texto += f" Para {quem}, o acervo ainda não tem material suficiente sobre este assunto."
        return texto

    def assunto(self, e: dict) -> str:
        if e["tipo"] == "tema":
            return f"o tema {e['tema'] or e['titulo']}"
        return juntar([self.ref_extenso(r) for r in e["referencias"]])

    def descricao(self, e: dict) -> str:
        n = sum(1 for s in self.secoes_tradicao(e) if not s["sem_material"])
        return cortar(f"{e['titulo']}. Como {n} tradições cristãs leem {self.assunto(e)}, lado a lado e com as fontes. "
                      "Concordâncias, divergências e obras citadas.")

    def estudos_da_tradicao(self, tid: str) -> tuple[list[dict], list[dict]]:
        com, sem = [], []
        for e in self.estudos:
            for s in self.secoes_tradicao(e):
                if s["tradicao_id"] == tid:
                    (sem if s["sem_material"] else com).append(e)
                    break
        return com, sem

    def obras_da_tradicao(self, tid: str, limite: int = 14) -> list[dict]:
        ordem = {"oficial": 0, "autor_representativo": 1, "historico": 2}
        lista = [dict(self.fontes[o["fonte_id"]], trechos=o["trechos"]) for o in self.obras.get(tid, [])]
        lista.sort(key=lambda f: (ordem.get(f["tipo_autoridade"], 3), -f["trechos"], f["titulo"]))
        return lista[:limite]


def juntar(itens: list[str]) -> str:
    itens = [i for i in itens if i]
    if len(itens) <= 1:
        return "".join(itens)
    return ", ".join(itens[:-1]) + " e " + itens[-1]


def data_br(iso: str) -> str:
    a, m, d = iso[:10].split("-")
    return f"{d}/{m}/{a}"


def esc(t: object) -> str:
    return html.escape(str(t), quote=True)


def cortar(t: str, n: int = 158) -> str:
    """Descrição para o Google: até n caracteres, cortada no fim de palavra."""
    t = re.sub(r"\s+", " ", t).strip()
    if len(t) <= n:
        return t
    return t[: n - 1].rsplit(" ", 1)[0].rstrip(",;:") + "…"


ROTULO_AUTORIDADE = {
    "oficial": "Documento oficial",
    "autor_representativo": "Autor representativo",
    "historico": "Texto histórico",
    "recurso_de_estudo": "Recurso de estudo",
    "dados_academicos": "Dados acadêmicos",
}

# ------------------------------------------------------------------ imagens (domínio público)
# Licença conferida na página de cada arquivo (README). Imagem nova entra aqui e no README, com a
# licença conferida na fonte, sem NC, sem IA e sem representar Deus ou Cristo. `arquivos` é o
# começo do nome dos arquivos em imagens/ (o teste confere que toda imagem tem crédito).

CREDITOS = [
    {
        "id": "schnorr",
        "texto": "Julius Schnorr von Carolsfeld, Filipe e o eunuco, Die Bibel in Bildern, 1860",
        "obra": "Die Bibel in Bildern",
        "url": "https://commons.wikimedia.org/wiki/File:Schnorr_von_Carolsfeld_Bibel_in_Bildern_1860_229.png",
        "licenca": "domínio público",
        "origem": "Wikimedia Commons",
        "arquivos": "filipe-eunuco",
    },
    {
        "id": "rembrandt",
        "texto": "Rembrandt, O batismo do eunuco, 1626, Museum Catharijneconvent, Utrecht",
        "obra": "O batismo do eunuco",
        "url": "https://commons.wikimedia.org/wiki/File:Rembrandt,_The_Baptism_of_the_Eunuch,_1626,_Museum_Catharijneconvent,_Utrecht.jpg",
        "licenca": "domínio público",
        "origem": "Wikimedia Commons",
        "arquivos": "rembrandt-batismo-eunuco",
    },
    {
        "id": "biblia1534",
        "texto": "Página de rosto da Bíblia de Lutero, 1534 (foto de Torsten Schleese)",
        "obra": "Bíblia de Lutero, 1534",
        "url": "https://commons.wikimedia.org/wiki/File:Lutherbibel.jpg",
        "licenca": "domínio público (o fotógrafo liberou a foto)",
        "origem": "Wikimedia Commons",
        "arquivos": "biblia-1534",
    },
    {
        # Flickr, licença Public Domain Mark 1.0 conferida na página da foto em 03/10/2026; uso
        # aprovado pelo dono do projeto. Só arquitetura e cruzes (a foto do interior de Sinaia,
        # com afrescos de Cristo, ficou de fora pela regra de neutralidade).
        "id": "zlatari",
        "texto": "Igreja de Zlătari (São Cipriano), Bucareste, foto de M. Cristian-Ioan, 2005",
        "obra": "Igreja de Zlătari, Bucareste",
        "url": "https://www.flickr.com/photos/sky-clouds/55404283986/",
        "licenca": "Public Domain Mark 1.0",
        "origem": "Flickr",
        "arquivos": "igreja-zlatari-bucareste",
    },
    # Art Institute of Chicago: is_public_domain = true na API (conferido em 03/10/2026); o museu
    # publica essas imagens em CC0. O "São Jerônimo penitente" ficou de fora (crucifixo com Cristo).
    {
        "id": "davi",
        "texto": "Rembrandt, Davi em oração, 1652, gravura, Art Institute of Chicago",
        "obra": "Davi em oração",
        "url": "https://www.artic.edu/artworks/48960",
        "licenca": "domínio público (CC0)",
        "origem": "Art Institute of Chicago",
        "arquivos": "rembrandt-davi-oracao",
    },
    {
        "id": "pedro",
        "texto": "Jusepe de Ribera, São Pedro penitente, c. 1630, Art Institute of Chicago",
        "obra": "São Pedro penitente",
        "url": "https://www.artic.edu/artworks/120172",
        "licenca": "domínio público (CC0)",
        "origem": "Art Institute of Chicago",
        "arquivos": "ribera-pedro-penitente",
    },
    {
        "id": "salomao",
        "texto": "Mestre do Grupo da Adoração de Antuérpia, O rei Salomão recebe a rainha de Sabá, 1515-20, Art Institute of Chicago",
        "obra": "O rei Salomão recebe a rainha de Sabá",
        "url": "https://www.artic.edu/artworks/111670",
        "licenca": "domínio público (CC0)",
        "origem": "Art Institute of Chicago",
        "arquivos": "salomao-rainha-saba",
    },
    {
        "id": "expulsao",
        "texto": "Lucas van Leyden, A expulsão do Paraíso, 1510, gravura, Art Institute of Chicago",
        "obra": "A expulsão do Paraíso",
        "url": "https://www.artic.edu/artworks/106566",
        "licenca": "domínio público (CC0)",
        "origem": "Art Institute of Chicago",
        "arquivos": "lucas-van-leyden-expulsao",
    },
]

# Imagens das páginas internas (uma por página, no máximo). Arquivos em imagens/<base>-<largura>.webp.
IMAGENS = {
    "zlatari": {
        "base": "/imagens/igreja-zlatari-bucareste", "larguras": (480, 768), "altura_768": 1024,
        "alt": "Fachada de uma igreja ortodoxa romena com quatro cúpulas cinzentas encimadas por cruzes, arcos de tijolo aparente e um pórtico na entrada.",
        "legenda": "Igreja ortodoxa de Zlătari, em Bucareste (Romênia), conhecida pelas relíquias de São Cipriano. Foto de M. Cristian-Ioan, 2005",
    },
    "davi": {
        "base": "/imagens/rembrandt-davi-oracao", "larguras": (480, 768), "altura_768": 1143,
        "alt": "Gravura de Rembrandt: o rei Davi, de costas, ajoelhado junto a uma cama com dossel, reza com as mãos postas; a harpa está no chão, à frente.",
        "legenda": "Rembrandt, Davi em oração, 1652. A tradição atribui o Salmo 51 a Davi",
    },
    "pedro": {
        "base": "/imagens/ribera-pedro-penitente", "larguras": (480, 768), "altura_768": 998,
        "alt": "Pintura de Ribera: São Pedro, idoso e de barba branca, olha para o alto, com uma mão no peito e a outra erguida, sobre fundo escuro.",
        "legenda": "Jusepe de Ribera, São Pedro penitente, c. 1630",
    },
    "salomao": {
        "base": "/imagens/salomao-rainha-saba", "larguras": (480, 768), "altura_768": 1048,
        "alt": "Pintura: a rainha de Sabá, ajoelhada e de vestido claro, oferece um vaso de ouro ao rei Salomão, sentado num palácio de colunas; atrás, damas e cortesãos.",
        "legenda": "O rei Salomão recebe a rainha de Sabá, c. 1515-20 (detalhe). A rainha veio pôr Salomão à prova com perguntas difíceis (1 Reis 10.1)",
    },
    "expulsao": {
        "base": "/imagens/lucas-van-leyden-expulsao", "larguras": (480, 768), "altura_768": 1051,
        "alt": "Gravura de Lucas van Leyden: Adão, com uma enxada ao ombro, e Eva, com o filho no colo, caminham juntos para fora do jardim.",
        "legenda": "Lucas van Leyden, Adão e Eva depois da expulsão do Paraíso, 1510",
    },
}
IMAGEM_TRADICAO = {"ortodoxa": "zlatari"}
IMAGEM_ESTUDO = {
    "pecado-original": "expulsao",
    "romanos-5-12": "expulsao",
    "genesis-3-15": "expulsao",
    "salmos-51-5": "davi",
    "confissao-e-perdao": "pedro",
}
IMAGEM_PAGINA = {"/como-funciona/": "salomao"}

# ------------------------------------------------------------------ peças das páginas

# Símbolo do app (src/lib/simbolo.ts, no repositório do app), recortado sem fundo
SIMBOLO_PATHS = (
    '<path fill="var(--capa)" d="M256 156 C 206 124, 128 116, 52 132 L 52 392 C 128 378, 206 386, 256 420 C 306 386'
    ', 384 378, 460 392 L 460 132 C 384 116, 306 124, 256 156 Z"/><path fill="var(--pagina)" d="M249 150 C 206 122,'
    ' 140 114, 72 126 L 72 362 C 140 350, 206 358, 249 388 Z"/><path fill="var(--pagina)" d="M263 150 C 306 122, 37'
    '2 114, 440 126 L 440 362 C 372 350, 306 358, 263 388 Z"/><path fill="none" stroke="var(--pagina)" stroke-width'
    '="5" d="M72 374 C 140 362, 206 370, 249 400 M263 400 C 306 370, 372 362, 440 374"/><path fill="none" stroke="v'
    'ar(--capa)" stroke-width="9" stroke-linecap="round" d="M106 174 Q 161 170, 216 180"/><path fill="none" stroke='
    '"var(--capa)" stroke-width="9" stroke-linecap="round" d="M106 204 Q 161 200, 216 210"/><path fill="none" strok'
    'e="var(--capa)" stroke-width="9" stroke-linecap="round" d="M106 234 Q 161 230, 216 240"/><path fill="none" str'
    'oke="var(--capa)" stroke-width="9" stroke-linecap="round" d="M106 264 Q 161 260, 216 270"/><path fill="none" s'
    'troke="var(--capa)" stroke-width="9" stroke-linecap="round" d="M106 294 Q 161 290, 216 300"/><path fill="none"'
    ' stroke="var(--capa)" stroke-width="9" stroke-linecap="round" d="M106 324 Q 137 320, 168 330"/><path fill="var'
    '(--capa)" d="M341.7 187.4Q340.9 194.5 338.2 199.1Q335.5 203.6 328 203.6Q321.8 203.6 318.8 200.3Q315.8 196.9 31'
    '5.8 192.3Q315.8 183.7 325.9 177.5Q336.1 171.2 350.9 171.2Q367.9 171.2 379.4 179.6Q390.9 188 390.9 203.4Q390.9 '
    '213.6 386 220.4Q381.2 227.1 371.4 235.8L366.6 239.8Q357.9 247.7 354 255.5Q350.1 263.3 350.1 273Q350.1 278.2 35'
    '1.7 287.6Q352 288.4 350 288.8Q347.9 289.2 347.7 288.4Q344.4 281.1 342.5 271.8Q340.7 262.5 340.7 256Q340.7 247.'
    '7 343.5 242.4Q346.3 237.1 352 230.4Q358.2 223.1 361.4 216.7Q364.7 210.4 364.7 200.1Q364.7 189.3 360.9 182.6Q35'
    '7.1 175.8 350.6 175.8Q345.8 175.8 344 178.9Q342.3 182 341.7 187.4ZM332.6 328.1Q332.6 321.6 336.6 317.9Q340.7 3'
    '14.1 347.4 314.1Q354.4 314.1 358.2 317.9Q362 321.6 362 328.1Q362 335.1 358.2 339.1Q354.4 343 347.4 343Q340.7 3'
    '43 336.6 338.9Q332.6 334.9 332.6 328.1Z"/><path fill="var(--capa)" d="M245 396 L 267 396 L 267 488 L 256 474 L'
    ' 245 488 Z"/>'
)

SIMBOLO = "".join(SIMBOLO_PATHS)
MENU = [
    ("/", "Início"),
    ("/estudos/", "Estudos"),
    ("/tradicoes/", "Tradições"),
    ("/como-funciona/", "Como funciona"),
    ("/sobre/", "Sobre"),
]


def simbolo(rotulo: str | None = None) -> str:
    if rotulo:
        return f'<svg viewBox="40 100 432 400" role="img" aria-label="{esc(rotulo)}">{SIMBOLO}</svg>'
    return f'<svg viewBox="40 100 432 400" aria-hidden="true">{SIMBOLO}</svg>'


def cabecalho(atual: str) -> str:
    def links(cls: str) -> str:
        itens = []
        for href, nome in MENU:
            ativo = href == atual or (href != "/" and atual.startswith(href))
            corrente = ' aria-current="page"' if ativo else ""
            itens.append(f'<li><a href="{href}"{corrente}>{nome}</a></li>')
        itens.append(f'<li><a class="{cls}" href="{APP}">Abrir o app</a></li>')
        return "".join(itens)

    return f"""<header class="topo-fixo">
  <div class="largura topo">
    <a class="marca" href="/" aria-label="Entendes, início">{simbolo()}Entendes</a>
    <nav class="menu" aria-label="Menu principal"><ul>{links("menu-app")}</ul></nav>
    <details class="menu-celular">
      <summary aria-label="Abrir o menu"><span class="hamburguer" aria-hidden="true"></span>Menu</summary>
      <nav aria-label="Menu principal (celular)"><ul>{links("botao")}</ul></nav>
    </details>
  </div>
</header>"""


def rodape() -> str:
    return f"""<footer class="rodape">
  <div class="largura">
    <div class="linhas">
      <a href="mailto:{EMAIL}">{EMAIL}</a>
      <a href="{INSTAGRAM}" rel="noopener">Instagram @entendes.app</a>
      <a href="{APP}">Abrir o app</a>
      <a href="/sobre/#creditos">Créditos das imagens</a>
      <a href="{APP}/privacidade">Privacidade</a>
      <a href="{APP}/termos">Termos</a>
    </div>
    <p class="verso">“Entendes tu o que lês?” Atos 8.30</p>
    <p class="creditos">Imagens em domínio público: {"; ".join(f'<a href="{esc(c["url"])}">{esc(c["texto"])}</a> ({esc(c["origem"])}{", " + esc(c["licenca"]) if c["origem"] == "Flickr" else ""})' for c in CREDITOS)}.</p>
  </div>
</footer>"""


def pagina(caminho: str, titulo: str, descricao: str, corpo: str, *, titulo_completo: str | None = None,
           noindex: bool = False, extra_head: str = "", script: str = "") -> str:
    titulo_html = titulo_completo or f"{titulo} · Entendes"
    url = SITE + caminho
    robots = '\n  <meta name="robots" content="noindex">' if noindex else ""
    canonico = "" if noindex else f'\n  <link rel="canonical" href="{esc(url)}">'
    return f"""<!doctype html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{esc(titulo_html)}</title>
  <meta name="description" content="{esc(descricao)}">{canonico}{robots}
  <meta name="theme-color" content="#F6F1E7" media="(prefers-color-scheme: light)">
  <meta name="theme-color" content="#1A1612" media="(prefers-color-scheme: dark)">
  <meta property="og:type" content="website">
  <meta property="og:locale" content="pt_BR">
  <meta property="og:site_name" content="Entendes">
  <meta property="og:url" content="{esc(url)}">
  <meta property="og:title" content="{esc(titulo_html)}">
  <meta property="og:description" content="{esc(descricao)}">
  <meta property="og:image" content="{SITE}/og.png">
  <meta property="og:image:width" content="1200">
  <meta property="og:image:height" content="630">
  <meta property="og:image:alt" content="Símbolo do Entendes, uma Bíblia aberta com um ponto de interrogação, e a pergunta “Entendes tu o que lês?” (Atos 8.30).">
  <meta name="twitter:card" content="summary_large_image">
  <link rel="icon" href="/favicon.svg" type="image/svg+xml">
  <link rel="icon" href="/favicon.png" type="image/png" sizes="48x48">
  <link rel="apple-touch-icon" href="/apple-touch-icon.png">
  <link rel="preload" href="/fontes/cormorant-garamond-latin-600-normal.woff2" as="font" type="font/woff2" crossorigin>{extra_head}
  <link rel="stylesheet" href="/estilo.css">
</head>
<body>
  <a class="pular" href="#conteudo">Pular para o conteúdo</a>
{cabecalho(caminho)}
<main id="conteudo">
{corpo}
</main>
{rodape()}{script}
</body>
</html>
"""


def migalhas(*itens: tuple[str, str | None]) -> str:
    partes = []
    for nome, href in itens:
        partes.append(f'<li><a href="{href}">{esc(nome)}</a></li>' if href else f'<li aria-current="page">{esc(nome)}</li>')
    return f'<nav class="migalhas" aria-label="Você está em"><ol>{"".join(partes)}</ol></nav>'


def cabeca_pagina(titulo: str, texto: str = "", antes: str = "") -> str:
    p = f'<p class="lead">{texto}</p>' if texto else ""
    return f'<div class="cabeca-pagina">{antes}<h1>{esc(titulo)}</h1>{p}</div>'


def botao_app(href: str, texto: str = "Abrir o Entendes") -> str:
    return f'<a class="botao" href="{esc(href)}">{esc(texto)}</a>'


# ------------------------------------------------------------------ cartões

def cartao_estudo(site: Site, e: dict, nivel: str = "h3") -> str:
    tipo = "Tema" if e["tipo"] == "tema" else "Passagem"
    refs = " · ".join(site.ref_extenso(r) for r in e["referencias"][:3])
    if len(e["referencias"]) > 3:
        refs += " · …"
    siglas = "".join(
        f'<span class="sigla{" sem" if s["sem_material"] else ""}" title="{esc(site.trad[s["tradicao_id"]]["nome"])}'
        f'{" (acervo ainda sem material suficiente)" if s["sem_material"] else ""}">{esc(site.trad[s["tradicao_id"]]["sigla"])}</span>'
        for s in site.secoes_tradicao(e)
    )
    return f"""<article class="cartao-estudo">
  <p class="sobrelinha">{tipo}</p>
  <{nivel}><a href="/estudos/{esc(e["slug"])}/">{esc(e["titulo"])}</a></{nivel}>
  <p class="refs">{esc(refs)}</p>
  <p class="siglas">{siglas}</p>
</article>"""


# ------------------------------------------------------------------ páginas

def pagina_inicio(site: Site) -> str:
    recentes = site.estudos[:6]
    cartoes = "\n".join(cartao_estudo(site, e) for e in recentes)
    trads = "".join(f'<li><a href="/tradicoes/{t["id"]}/">{esc(t["nome"])}</a></li>' for t in site.disponiveis)
    breve = juntar([t["nome"] for t in site.em_breve])
    corpo = f"""<section class="hero" aria-labelledby="titulo">
  <picture class="fundo">
    <source media="(prefers-color-scheme: dark)" srcset="/imagens/filipe-eunuco-escuro-800.webp 800w, /imagens/filipe-eunuco-escuro-1600.webp 1600w" sizes="100vw">
    <img src="/imagens/filipe-eunuco-claro-1600.webp" srcset="/imagens/filipe-eunuco-claro-800.webp 800w, /imagens/filipe-eunuco-claro-1600.webp 1600w" sizes="100vw" width="1600" height="1288" alt="" fetchpriority="high">
  </picture>
  <div class="estreita hero-conteudo">
    {simbolo("Símbolo do Entendes: uma Bíblia aberta com um ponto de interrogação")}
    <h1 id="titulo">Entendes tu o que lês?</h1>
    <p class="referencia">Atos 8.30, Almeida 1911</p>
    <p class="subtitulo">Veja, lado a lado, como as tradições cristãs leem o mesmo texto da Bíblia, sempre com as fontes.</p>
    <div class="acoes">
      {botao_app(APP)}
      <a href="/estudos/">Ver os estudos</a>
    </div>
  </div>
</section>

<section class="bloco" aria-labelledby="t-estudos">
  <div class="largura">
    <div class="titulo-com-link"><h2 id="t-estudos">Estudos recentes</h2><a href="/estudos/">Ver todos os {len(site.estudos)} estudos</a></div>
    <div class="grade-estudos">
{cartoes}
    </div>
  </div>
</section>

<section class="bloco" aria-labelledby="t-como">
  <div class="largura">
    <h2 id="t-como">Como funciona</h2>
    <ol class="passos">
      <li><h3>Escolha um texto ou tema</h3><p>Um versículo, uma passagem ou um assunto, como batismo ou graça.</p></li>
      <li><h3>Veja as leituras lado a lado</h3><p>Cada tradição aparece na sua própria seção, com o mesmo cuidado.</p></li>
      <li><h3>Confira as fontes</h3><p>Cada afirmação aponta para o trecho de onde veio: catecismos, confissões, Padres da Igreja e comentários clássicos.</p></li>
    </ol>
    <p class="mais"><a href="/como-funciona/">Como os estudos são feitos e conferidos</a></p>
  </div>
</section>

<section class="bloco" aria-labelledby="t-tradicoes">
  <div class="largura">
    <h2 id="t-tradicoes">Tradições</h2>
    <p>Hoje o acervo reúne textos de {len(site.disponiveis)} tradições cristãs. {esc(breve)} {"entram" if len(site.em_breve) > 1 else "entra"} em breve.</p>
    <ul class="lista-chips">{trads}</ul>
    <p class="mais"><a href="/tradicoes/">Conheça as tradições e as fontes de cada uma</a></p>
  </div>
</section>

<section class="bloco" aria-labelledby="t-nome">
  <div class="estreita">
    <h2 id="t-nome">Por que Entendes</h2>
    <p>O nome vem de Atos 8: na estrada para Gaza, Filipe perguntou a um oficial etíope se ele entendia o que lia. “Como o poderei eu, se alguem me não ensinar?” O Entendes quer caminhar ao lado de quem lê, mostrando como a Igreja, em suas tradições, entendeu cada texto ao longo dos séculos.</p>
    <p class="mais"><a href="/sobre/">Sobre o Entendes</a></p>
  </div>
</section>

<section class="bloco convite" aria-labelledby="t-convite">
  <picture class="fundo">
    <source media="(prefers-color-scheme: dark)" srcset="/imagens/biblia-1534-escuro-600.webp 600w, /imagens/biblia-1534-escuro-960.webp 960w" sizes="100vw">
    <img src="/imagens/biblia-1534-claro-960.webp" srcset="/imagens/biblia-1534-claro-600.webp 600w, /imagens/biblia-1534-claro-960.webp 960w" sizes="100vw" width="960" height="729" alt="" loading="lazy" decoding="async">
  </picture>
  <div class="estreita convite-conteudo">
    <h2 id="t-convite">Leia com companhia</h2>
    <p>O Entendes é gratuito para começar e funciona no navegador e no celular.</p>
    {botao_app(APP)}
  </div>
</section>"""
    nomes = juntar([t["nome"].split(" ")[0].split("/")[0].lower() for t in site.disponiveis])
    return pagina(
        "/", "Início",
        cortar(f"Veja, lado a lado, como as tradições cristãs leem o mesmo texto da Bíblia, sempre com as fontes: {nomes}."),
        corpo, titulo_completo="Entendes: como as tradições cristãs leem a Bíblia",
        extra_head='\n  <link rel="preload" as="image" href="/imagens/filipe-eunuco-claro-1600.webp" imagesrcset="/imagens/filipe-eunuco-claro-800.webp 800w, /imagens/filipe-eunuco-claro-1600.webp 1600w" imagesizes="100vw" media="(prefers-color-scheme: light)">',
    )


FILTRO_JS = """
<script>
// Filtro da lista de estudos. Sem JavaScript, a lista inteira continua visível.
(function () {
  var f = document.getElementById("filtro"), lista = document.querySelectorAll("[data-estudo]");
  var busca = document.getElementById("f-busca"), tipo = document.getElementById("f-tipo"), livro = document.getElementById("f-livro");
  var contagem = document.getElementById("f-contagem"), vazio = document.getElementById("f-vazio");
  if (!f) return;
  f.hidden = false;
  function norm(t) { return t.normalize("NFD").replace(/[\\u0300-\\u036f]/g, "").toLowerCase(); }
  function aplicar() {
    var q = norm(busca.value.trim()), n = 0;
    lista.forEach(function (el) {
      var ok = (!q || norm(el.dataset.busca).indexOf(q) >= 0)
        && (!tipo.value || el.dataset.tipo === tipo.value)
        && (!livro.value || (" " + el.dataset.livros + " ").indexOf(" " + livro.value + " ") >= 0);
      el.hidden = !ok; if (ok) n++;
    });
    contagem.textContent = n === 1 ? "1 estudo" : n + " estudos";
    vazio.hidden = n > 0;
  }
  [busca, tipo, livro].forEach(function (c) { c.addEventListener("input", aplicar); });
  f.addEventListener("submit", function (e) { e.preventDefault(); });
  aplicar();
})();
</script>"""


def pagina_estudos(site: Site) -> str:
    livros = sorted({c for e in site.estudos for c in site.livros_do_estudo(e)},
                    key=lambda c: site.livros.get(c, {}).get("ordem", 999))
    opcoes = "".join(f'<option value="{c}">{esc(site.livros[c]["nome"] if c in site.livros else c)}</option>' for c in livros)
    itens = []
    for e in site.estudos:
        busca = " ".join([e["titulo"], e["tema"] or ""] + [site.ref_extenso(r) for r in e["referencias"]])
        itens.append(f'<li data-estudo data-tipo="{e["tipo"]}" data-livros="{" ".join(site.livros_do_estudo(e))}" '
                     f'data-busca="{esc(busca)}">{cartao_estudo(site, e, "h2")}</li>')
    temas = sum(1 for e in site.estudos if e["tipo"] == "tema")
    corpo = f"""<div class="largura pagina">
{migalhas(("Início", "/"), ("Estudos", None))}
{cabeca_pagina("Estudos", f"{len(site.estudos)} estudos publicados: {temas} sobre temas e {len(site.estudos) - temas} sobre passagens. Cada um mostra, lado a lado, como as tradições leem o texto, com as fontes. O estudo completo fica no app.")}
<form id="filtro" class="filtro" hidden role="search" aria-label="Filtrar estudos">
  <label>Buscar<input id="f-busca" type="search" placeholder="Tema, título ou referência" autocomplete="off"></label>
  <label>Tipo<select id="f-tipo"><option value="">Todos</option><option value="tema">Temas</option><option value="passagem">Passagens</option></select></label>
  <label>Livro<select id="f-livro"><option value="">Todos os livros</option>{opcoes}</select></label>
  <p id="f-contagem" class="contagem" aria-live="polite"></p>
</form>
<ul class="lista-estudos">
{chr(10).join(itens)}
</ul>
<p id="f-vazio" class="nota" hidden>Nenhum estudo com esses filtros. No app, você pode pedir um estudo novo.</p>
<p class="nota">As siglas mostram as tradições comparadas em cada estudo; as riscadas ainda não têm material suficiente no acervo sobre aquele texto.</p>
</div>"""
    return pagina("/estudos/", "Estudos",
                  cortar(f"{len(site.estudos)} estudos que comparam como as tradições cristãs leem temas e passagens da Bíblia, com as fontes de cada leitura."),
                  corpo, script=FILTRO_JS)


def pagina_estudo(site: Site, e: dict) -> str:
    refs = "".join(f"<li>{esc(site.ref_extenso(r))}</li>" for r in e["referencias"])
    trads = []
    for s in site.secoes_tradicao(e):
        nome = esc(site.nome_secao(s))
        if s["sem_material"]:
            trads.append(f'<li class="sem"><a href="/tradicoes/{s["tradicao_id"]}/">{nome}</a> <span>acervo ainda sem material suficiente</span></li>')
        else:
            trads.append(f'<li><a href="/tradicoes/{s["tradicao_id"]}/">{nome}</a></li>')

    def bloco(tipo: str, titulo: str) -> str:
        afs = site.bloco(e, tipo)
        if not afs:
            return ""
        lis = "".join(f"<li>{esc(a)}</li>" for a in afs)
        return f"""<section class="sintese" aria-labelledby="t-{tipo}">
  <h2 id="t-{tipo}">{titulo}</h2>
  <p class="rotulo">{ROTULO_SINTESE}</p>
  <ul>{lis}</ul>
</section>"""

    obras = []
    for tid, lista in site.fontes_do_estudo(e).items():
        itens = "".join(f"<li><cite>{esc(f['titulo'])}</cite>{', ' + esc(f['autor']) if f['autor'] else ''}</li>" for f in lista)
        obras.append(f'<div><h3>{esc(site.trad[tid]["nome"])}</h3><ul>{itens}</ul></div>')
    creditos = ""
    if e.get("atribuicoes") or e.get("licencas_derivadas"):
        linhas = "".join(f"<li>{esc(a)}</li>" for a in e.get("atribuicoes") or [])
        lic = "".join(f"<li>Este estudo usa fonte com licença {esc(l)}.</li>" for l in e.get("licencas_derivadas") or [])
        creditos = f'<section class="creditos-estudo" aria-labelledby="t-creditos"><h2 id="t-creditos">Créditos das fontes</h2><ul>{linhas}{lic}</ul></section>'

    url_app = f"{APP}/estudos/{e['slug']}"
    tipo = "Estudo de tema" if e["tipo"] == "tema" else "Estudo de passagem"
    resumo = site.resumo(e)
    corpo = f"""<div class="estreita pagina">
{migalhas(("Início", "/"), ("Estudos", "/estudos/"), (e["titulo"], None))}
<div class="cabeca-pagina">
  <p class="sobrelinha">{tipo} · publicado em {data_br(e["publicado_em"])}</p>
  <h1>{esc(e["titulo"])}</h1>
  <p class="lead">{esc(resumo)}</p>
  <div class="acoes esquerda">{botao_app(url_app, "Ler o estudo completo no app")}</div>
</div>
{figura(IMAGEM_ESTUDO.get(e["slug"]))}
<div class="duas-colunas">
  <section aria-labelledby="t-refs"><h2 id="t-refs">Referências</h2><ul class="refs-lista">{refs}</ul></section>
  <section aria-labelledby="t-trads"><h2 id="t-trads">Tradições comparadas</h2><ul class="trads-lista">{"".join(trads)}</ul></section>
</div>
{bloco("concordancias", "Concordâncias")}
{bloco("divergencias", "Divergências")}
<p class="nota">Aqui vão só algumas linhas. No app, cada tradição tem a sua seção, e cada afirmação aponta para o trecho da fonte, que você pode abrir e ler.</p>
<section class="obras" aria-labelledby="t-obras">
  <h2 id="t-obras">Obras citadas</h2>
  <div class="obras-grade">{"".join(obras)}</div>
</section>
{creditos}
<div class="convite-final">
  <p>Leia as seções de cada tradição, com os trechos das fontes.</p>
  {botao_app(url_app, "Ler o estudo completo no app")}
</div>
</div>"""
    return pagina(f"/estudos/{e['slug']}/", e["titulo"], site.descricao(e), corpo)


def pagina_tradicoes(site: Site) -> str:
    cartoes = []
    for t in site.disponiveis:
        com, _ = site.estudos_da_tradicao(t["id"])
        obras = site.obras_da_tradicao(t["id"], limite=3)
        exemplos = juntar([f["titulo"] for f in obras])
        aviso = '<p class="aviso">Acervo em construção</p>' if t["status"] == "acervo_em_construcao" else ""
        cartoes.append(f"""<li class="cartao-trad">
  <p class="sobrelinha">{esc(t["grupo"])} · {esc(t["sigla"])}</p>
  <h2><a href="/tradicoes/{t["id"]}/">{esc(t["nome"])}</a></h2>
  {aviso}<p>{esc(exemplos)}</p>
  <p class="contagem">{len(com)} estudos · {len(site.obras.get(t["id"], []))} obras no acervo</p>
</li>""")
    breve = "".join(f'<li class="cartao-trad breve"><p class="sobrelinha">{esc(t["grupo"])} · {esc(t["sigla"])}</p>'
                    f'<h2>{esc(t["nome"])}</h2><p class="aviso">Em breve</p><p>O acervo desta tradição está sendo montado.</p></li>'
                    for t in site.em_breve)
    corpo = f"""<div class="largura pagina">
{migalhas(("Início", "/"), ("Tradições", None))}
{cabeca_pagina("Tradições", "As tradições aparecem agrupadas só por critério histórico, sem ranking. Cada uma é representada pelos próprios documentos e autores, todos em domínio público ou com licença livre.")}
<ul class="grade-trads">
{"".join(cartoes)}
{breve}
</ul>
<p class="nota">Antes da comparação, os estudos mostram as raízes comuns, como os credos antigos e os Padres da Igreja. Quando uma tradição ainda tem poucas fontes sobre um texto, o app diz isso, em vez de preencher o espaço.</p>
</div>"""
    nomes = juntar([t["nome"] for t in site.disponiveis])
    return pagina("/tradicoes/", "Tradições", cortar(f"As tradições cristãs no Entendes e as fontes de cada uma: {nomes}."), corpo)


def figura(chave: str | None) -> str:
    """Imagem da página, com legenda, link para a origem e a licença."""
    img = IMAGENS.get(chave or "")
    if not img:
        return ""
    c = next(c for c in CREDITOS if c["id"] == chave)
    w1, w2 = img["larguras"]
    srcset = f'{img["base"]}-{w1}.webp {w1}w, {img["base"]}-{w2}.webp {w2}w'
    return f"""<figure class="obra foto-pagina">
  <img src="{img["base"]}-{w2}.webp" srcset="{srcset}" sizes="(min-width: 720px) 340px, 100vw" width="{w2}" height="{img["altura_768"]}" loading="lazy" decoding="async" alt="{esc(img["alt"])}">
  <figcaption>{esc(img["legenda"])}. <a href="{esc(c["url"])}">{esc(c["origem"])}</a>, {esc(c["licenca"])}.</figcaption>
</figure>"""


def pagina_tradicao(site: Site, t: dict) -> str:
    com, sem = site.estudos_da_tradicao(t["id"])
    obras = site.obras_da_tradicao(t["id"])
    subs = [nome for (tid, _), nome in site.sub.items() if tid == t["id"]]
    itens_obras = "".join(
        f'<li><cite>{esc(f["titulo"])}</cite>{", " + esc(f["autor"]) if f["autor"] else ""}'
        f'<span>{ROTULO_AUTORIDADE.get(f["tipo_autoridade"], "")}</span></li>' for f in obras)
    total = len(site.obras.get(t["id"], []))
    mais = f'<p class="nota">E mais {total - len(obras)} obras no acervo.</p>' if total > len(obras) else ""
    estudos = "".join(f'<li><a href="/estudos/{esc(e["slug"])}/">{esc(e["titulo"])}</a></li>' for e in com)
    sem_txt = ""
    if sem:
        sem_txt = (f'<p class="nota">Em {len(sem)} {"estudo" if len(sem) == 1 else "estudos"}, o acervo ainda não tinha material '
                   f'suficiente desta tradição sobre o texto, e a seção aparece como “acervo em construção”.</p>')
    aviso = ""
    if t["status"] == "acervo_em_construcao":
        aviso = '<p class="aviso grande">Acervo em construção: por enquanto, só material histórico em domínio público.</p>'
    sub_txt = f'<p class="sobrelinha">Inclui: {esc(juntar(subs))}</p>' if subs else ""
    imagem = figura(IMAGEM_TRADICAO.get(t["id"]))
    corpo = f"""<div class="estreita pagina">
{migalhas(("Início", "/"), ("Tradições", "/tradicoes/"), (t["nome"], None))}
<div class="cabeca-pagina">
  <p class="sobrelinha">{esc(t["grupo"])} · {esc(t["sigla"])}</p>
  <h1>{esc(t["nome"])}</h1>
  {sub_txt}{aviso}
  <p class="lead">Nos estudos do Entendes, a tradição {esc(t["nome"])} é representada pelos próprios documentos e autores do acervo. Cada afirmação aponta para o trecho de onde veio.</p>
</div>
{imagem}
<section aria-labelledby="t-obras">
  <h2 id="t-obras">Principais documentos e autores no acervo</h2>
  <ul class="obras-lista">{itens_obras}</ul>
  {mais}
</section>
<section aria-labelledby="t-estudos">
  <h2 id="t-estudos">Estudos em que aparece</h2>
  <ul class="estudos-lista">{estudos}</ul>
  {sem_txt}
</section>
<div class="convite-final">{botao_app(f"{APP}/tradicoes/{t['id']}", "Ver no app")}</div>
</div>"""
    exemplos = juntar([f["titulo"] for f in obras[:3]])
    return pagina(f"/tradicoes/{t['id']}/", f"Tradição {t['nome']}",
                  cortar(f"Como a tradição {t['nome']} aparece nos estudos do Entendes: {exemplos}. {len(com)} estudos com fontes."),
                  corpo)


def pagina_como_funciona(site: Site) -> str:
    corpo = f"""<div class="estreita pagina">
{migalhas(("Início", "/"), ("Como funciona", None))}
{cabeca_pagina("Como funciona", "O Entendes compara como as tradições cristãs leem a Bíblia. Cada leitura vem de uma fonte que você pode abrir e conferir.")}
{figura(IMAGEM_PAGINA.get("/como-funciona/"))}
<ol class="passos lista-passos">
  <li><h2>Escolha um texto ou tema</h2><p>Um versículo, uma passagem ou um assunto, como batismo, graça ou Maria. Você também pode buscar no acervo com as suas palavras.</p></li>
  <li><h2>Veja as leituras lado a lado</h2><p>Cada tradição aparece na sua própria seção, na mesma ordem e com o mesmo cuidado. Antes delas, aparecem as raízes comuns, como os credos antigos. Depois, o que as tradições têm em comum e onde elas se afastam.</p></li>
  <li><h2>Confira as fontes</h2><p>Cada afirmação aponta para o trecho de onde veio: catecismos, confissões, Padres da Igreja e comentários clássicos. Você abre o trecho e lê o texto original.</p></li>
</ol>
<section aria-labelledby="t-acervo">
  <h2 id="t-acervo">O acervo</h2>
  <p>Só entram textos livres: obras em domínio público ou com licença que permite o uso, e Bíblias também livres, como a Almeida de 1911. Cada fonte guarda a licença e a origem. Hoje são {len(site.disponiveis)} tradições; {esc(juntar([t["nome"] for t in site.em_breve]))} entram quando o acervo delas estiver pronto.</p>
</section>
<section aria-labelledby="t-estudos">
  <h2 id="t-estudos">Como um estudo é feito</h2>
  <p>Para cada texto, o sistema reúne os trechos das fontes de cada tradição que comentam ou citam aquela passagem. Um modelo de linguagem escreve o estudo só com esses trechos. Antes de publicar, cada estudo passa por conferências automáticas:</p>
  <ul class="principios">
    <li><p><strong>Toda frase tem fonte.</strong> Frase sem trecho de origem sai do estudo.</p></li>
    <li><p><strong>Citação é literal.</strong> Todo texto entre aspas existe, letra por letra, no trecho citado.</p></li>
    <li><p><strong>Cada tradição fala por si.</strong> A seção de uma tradição só cita fontes dessa tradição.</p></li>
    <li><p><strong>Teste do fiel.</strong> Um segundo modelo, diferente do que escreveu, avalia se um membro daquela tradição reconheceria a descrição.</p></li>
    <li><p><strong>Equilíbrio.</strong> As seções têm tamanho e número de fontes parecidos, sem linguagem polêmica ou de juízo.</p></li>
    <li><p><strong>Sem preencher lacunas.</strong> Quando o acervo não tem material suficiente de uma tradição, a seção diz “acervo em construção”.</p></li>
  </ul>
  <p>Estudo que não passa é corrigido e conferido de novo, ou não é publicado.</p>
</section>
<section aria-labelledby="t-rotulos">
  <h2 id="t-rotulos">Os rótulos</h2>
  <dl class="rotulos">
    <dt>Fonte no acervo</dt><dd>A frase relata o que um trecho diz.</dd>
    <dt>{ROTULO_SINTESE}</dt><dd>A frase junta dois ou mais trechos numa formulação própria, como nas concordâncias e divergências.</dd>
    <dt>Leitura da IA, não verificada</dt><dd>Só nas perguntas que você faz depois de ler um estudo; nunca no estudo publicado.</dd>
  </dl>
</section>
<section aria-labelledby="t-nunca">
  <h2 id="t-nunca">O que o Entendes não faz</h2>
  <p>Não diz qual tradição está certa e não faz ranking. Não completa uma tradição com texto genérico. E não usa traduções modernas da Bíblia sem licença.</p>
</section>
<div class="convite-final"><p>Veja um estudo publicado.</p><a class="botao" href="/estudos/">Ver os estudos</a></div>
</div>"""
    return pagina("/como-funciona/", "Como funciona",
                  "Como o Entendes compara as tradições cristãs: acervo de textos livres, estudos com fonte em cada frase e conferências automáticas antes de publicar.",
                  corpo)


def pagina_sobre(site: Site) -> str:
    creditos = "".join(f'<li><a href="{esc(c["url"])}">{esc(c["texto"])}</a> — {esc(c["licenca"])}, {esc(c["origem"])}.</li>' for c in CREDITOS)
    corpo = f"""<div class="largura pagina">
{migalhas(("Início", "/"), ("Sobre", None))}
<div class="nome-grade">
  <figure class="obra">
    <img src="/imagens/rembrandt-batismo-eunuco-960.webp" srcset="/imagens/rembrandt-batismo-eunuco-600.webp 600w, /imagens/rembrandt-batismo-eunuco-960.webp 960w" sizes="(min-width: 860px) 400px, (min-width: 560px) 480px, 100vw" width="960" height="1269" loading="lazy" decoding="async" alt="Pintura de Rembrandt: o eunuco etíope, ajoelhado e com as mãos no peito, diante de Filipe, que estende a mão. Atrás, um servo segura o livro aberto; ao fundo estão a carruagem, os cavalos e a comitiva.">
    <figcaption>Rembrandt, <cite>O batismo do eunuco</cite>, 1626. Museum Catharijneconvent, Utrecht. Domínio público.</figcaption>
  </figure>
  <div class="nome-texto">
    <h1>Sobre o Entendes</h1>
    <h2>O nome</h2>
    <p>Na estrada para Gaza, um oficial etíope voltava de Jerusalém lendo o profeta Isaías. Filipe se aproximou e perguntou se ele entendia o que lia. A resposta foi simples e honesta.</p>
    <figure class="citacao">
      <blockquote>“Entendes tu o que lês?” … “Como o poderei eu, se alguem me não ensinar?”</blockquote>
      <figcaption>Atos 8.30-31, Almeida 1911 (domínio público), com a grafia original.</figcaption>
    </figure>
    <p>O Entendes quer caminhar ao lado de quem lê. Ele não dá a palavra final. Mostra como a Igreja, em suas tradições, entendeu aquele texto ao longo dos séculos.</p>
  </div>
</div>
<div class="estreita">
<section aria-labelledby="t-principios">
  <h2 id="t-principios">Princípios</h2>
  <ul class="principios">
    <li><p><strong>Nunca dizemos quem está certo.</strong> Mostramos as leituras com respeito, sem ranking.</p></li>
    <li><p><strong>Tudo com fonte.</strong> Cada afirmação aponta para um trecho que você pode abrir e ler.</p></li>
    <li><p><strong>Textos livres.</strong> Bíblias e obras de domínio público ou com licença que permite o uso.</p></li>
    <li><p><strong>Verificação automática antes de publicar.</strong> Cada estudo passa por conferências em código e por uma segunda leitura antes de ir ao ar. <a href="/como-funciona/">Como funciona</a></p></li>
    <li><p><strong>Seus dados no Brasil.</strong> A tradição que você informar é opcional e só é guardada com o seu consentimento.</p></li>
  </ul>
</section>
<section aria-labelledby="t-contato">
  <h2 id="t-contato">Contato</h2>
  <p>Escreva para <a href="mailto:{EMAIL}">{EMAIL}</a> ou fale com a gente no <a href="{INSTAGRAM}" rel="noopener">Instagram @entendes.app</a>.</p>
</section>
<section id="creditos" aria-labelledby="t-creditos">
  <h2 id="t-creditos">Créditos das imagens</h2>
  <p>Todas as imagens do site são de domínio público, com a licença conferida na página de cada arquivo. Nenhuma foi gerada por IA, e nenhuma representa Deus ou Cristo.</p>
  <ul class="lista-creditos">{creditos}</ul>
  <p class="nota">Fontes tipográficas: Cormorant Garamond e Source Sans 3, licença SIL Open Font License.</p>
</section>
</div>
</div>"""
    return pagina("/sobre/", "Sobre",
                  "Por que Entendes: o nome vem de Atos 8.30. Os princípios do app, o contato e os créditos das imagens, todas em domínio público.",
                  corpo)


def pagina_404() -> str:
    corpo = """<div class="estreita pagina centro">
<h1>Página não encontrada</h1>
<p class="lead">O endereço pode ter mudado.</p>
<div class="acoes"><a class="botao" href="/estudos/">Ver os estudos</a><a href="/">Voltar ao início</a></div>
</div>"""
    return pagina("/404.html", "Página não encontrada", "Página não encontrada no site do Entendes. Veja os estudos ou volte ao início.", corpo, noindex=True)


def sitemap(paginas: dict[str, str], datas: dict[str, str], padrao: str) -> str:
    urls = []
    for caminho in sorted(paginas, key=lambda c: (c.count("/"), c)):
        if caminho == "/404.html":
            continue
        urls.append(f"  <url>\n    <loc>{SITE}{caminho}</loc>\n    <lastmod>{datas.get(caminho, padrao)}</lastmod>\n  </url>")
    return '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' + "\n".join(urls) + "\n</urlset>\n"


# ------------------------------------------------------------------ montagem

def montar(dados: dict) -> dict[str, str]:
    """Caminho público → conteúdo. 'sitemap.xml' vai junto."""
    site = Site(dados)
    paginas: dict[str, str] = {
        "/": pagina_inicio(site),
        "/estudos/": pagina_estudos(site),
        "/tradicoes/": pagina_tradicoes(site),
        "/como-funciona/": pagina_como_funciona(site),
        "/sobre/": pagina_sobre(site),
        "/404.html": pagina_404(),
    }
    datas: dict[str, str] = {}
    for e in site.estudos:
        paginas[f"/estudos/{e['slug']}/"] = pagina_estudo(site, e)
        datas[f"/estudos/{e['slug']}/"] = e["publicado_em"]
    for t in site.disponiveis:
        paginas[f"/tradicoes/{t['id']}/"] = pagina_tradicao(site, t)
    ultimo = max([e["publicado_em"] for e in site.estudos] or [site.gerado_em])
    for c in ["/", "/estudos/", "/tradicoes/"] + [f"/tradicoes/{t['id']}/" for t in site.disponiveis]:
        datas[c] = ultimo
    saida = dict(paginas)
    saida["sitemap.xml"] = sitemap(paginas, datas, site.gerado_em)
    return saida


def arquivo_de(caminho: str) -> Path:
    if caminho == "sitemap.xml":
        return Path("sitemap.xml")
    if caminho.endswith(".html"):
        return Path(caminho.lstrip("/"))
    return Path(caminho.lstrip("/")) / "index.html"


def escrever(saida: dict[str, str], destino: Path = RAIZ) -> list[Path]:
    for pasta in PASTAS_GERADAS:
        shutil.rmtree(destino / pasta, ignore_errors=True)
    escritos = []
    for caminho, conteudo in saida.items():
        arq = destino / arquivo_de(caminho)
        arq.parent.mkdir(parents=True, exist_ok=True)
        arq.write_text(conteudo, encoding="utf-8")
        escritos.append(arq)
    return escritos


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sem-banco", action="store_true", help="usa dados/site.json, sem ler o banco")
    args = ap.parse_args()
    if args.sem_banco:
        dados = json.loads(DADOS.read_text(encoding="utf-8"))
    else:
        dados = ler_banco()
        DADOS.parent.mkdir(exist_ok=True)
        DADOS.write_text(json.dumps(dados, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    escritos = escrever(montar(dados))
    site = Site(dados)
    print(f"{len(escritos)} arquivos: {len(site.estudos)} estudos, {len(site.disponiveis)} tradições "
          f"({len(site.em_breve)} em breve); dados de {dados['gerado_em']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
