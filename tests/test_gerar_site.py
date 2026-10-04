"""Testes do gerador do site. Rodar: python3 -m unittest discover -s tests

Usam o retrato em dados/site.json (sem banco) e um caso pequeno escrito aqui.
"""
from __future__ import annotations

import copy
import json
import re
import sys
import tempfile
import unittest
from html.parser import HTMLParser
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "scripts"))
import gerar_site as g  # noqa: E402

DADOS = json.loads((RAIZ / "dados" / "site.json").read_text(encoding="utf-8"))


class Coletor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links: list[str] = []
        self.title = ""
        self.meta: dict[str, str] = {}
        self.canonical = None
        self.h1 = 0
        self._no_title = False

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "a" and a.get("href"):
            self.links.append(a["href"])
        if tag in ("img", "source"):
            for src in (a.get("src") or "", *(s.strip().split(" ")[0] for s in (a.get("srcset") or "").split(","))):
                if src:
                    self.links.append(src)
        if tag == "link" and a.get("rel") == "canonical":
            self.canonical = a.get("href")
        if tag == "meta" and a.get("name"):
            self.meta[a["name"]] = a.get("content", "")
        if tag == "title":
            self._no_title = True
        if tag == "h1":
            self.h1 += 1

    def handle_endtag(self, tag):
        if tag == "title":
            self._no_title = False

    def handle_data(self, data):
        if self._no_title:
            self.title += data


def ler(conteudo: str) -> Coletor:
    c = Coletor()
    c.feed(conteudo)
    return c


class TestSite(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.saida = g.montar(DADOS)
        cls.site = g.Site(DADOS)
        cls.paginas = {k: v for k, v in cls.saida.items() if k != "sitemap.xml"}

    def test_paginas_esperadas(self):
        esperadas = {"/", "/estudos/", "/tradicoes/", "/como-funciona/", "/sobre/", "/404.html"}
        esperadas |= {f"/estudos/{e['slug']}/" for e in self.site.estudos}
        esperadas |= {f"/tradicoes/{t['id']}/" for t in self.site.disponiveis}
        self.assertEqual(set(self.paginas), esperadas)

    def test_tradicoes_em_breve_sem_pagina(self):
        for t in self.site.em_breve:
            self.assertNotIn(f"/tradicoes/{t['id']}/", self.paginas)
            self.assertIn(t["nome"], self.paginas["/tradicoes/"])
            self.assertNotIn(f'href="/tradicoes/{t["id"]}/"', "".join(self.paginas.values()))

    def test_titulo_descricao_canonico_unicos(self):
        titulos, descricoes = set(), set()
        for caminho, html in self.paginas.items():
            c = ler(html)
            self.assertEqual(c.h1, 1, f"{caminho}: um h1 só")
            self.assertTrue(c.title.strip(), caminho)
            d = c.meta.get("description", "")
            self.assertTrue(30 <= len(d) <= 160, f"{caminho}: descrição com {len(d)} caracteres")
            if caminho != "/404.html":
                self.assertEqual(c.canonical, g.SITE + caminho)
                self.assertNotIn(c.title, titulos, caminho)
                self.assertNotIn(d, descricoes, caminho)
            titulos.add(c.title)
            descricoes.add(d)

    def test_links_internos_existem(self):
        arquivos = {g.arquivo_de(c).as_posix() for c in self.saida}
        estaticos = {p.relative_to(RAIZ).as_posix() for p in RAIZ.rglob("*") if p.is_file() and ".git" not in p.parts}
        for caminho, html in self.paginas.items():
            for href in ler(html).links:
                if not href.startswith("/"):
                    continue
                alvo = href.split("#")[0]
                rel = (alvo.lstrip("/") + "index.html") if alvo.endswith("/") else alvo.lstrip("/")
                self.assertTrue(rel in arquivos or rel in estaticos, f"{caminho}: link quebrado {href}")

    def test_sitemap(self):
        sm = self.saida["sitemap.xml"]
        locs = re.findall(r"<loc>(.*?)</loc>", sm)
        self.assertEqual(set(locs), {g.SITE + c for c in self.paginas if c != "/404.html"})
        self.assertTrue(all(re.fullmatch(r"\d{4}-\d{2}-\d{2}", d) for d in re.findall(r"<lastmod>(.*?)</lastmod>", sm)))

    def test_estudo_leva_ao_app_e_nao_copia_o_estudo(self):
        for e in self.site.estudos:
            html = self.paginas[f"/estudos/{e['slug']}/"]
            self.assertIn(f'href="{g.APP}/estudos/{e["slug"]}"', html)
            self.assertIn("Ler o estudo completo no app", html)
            for tipo in ("concordancias", "divergencias"):
                self.assertLessEqual(len(self.site.bloco(e, tipo)), g.AFIRMACOES_POR_BLOCO)
            if self.site.bloco(e, "concordancias"):
                self.assertIn(g.ROTULO_SINTESE, html)

    def test_rotulos_e_textos_proibidos(self):
        tudo = "\n".join(self.paginas.values()).lower()
        for proibido in ("revisado", "validado", "nova versão internacional", "ccel.org", "newadvent", "jw.org"):
            self.assertNotIn(proibido, tudo, proibido)

    def test_dados_so_com_o_necessario(self):
        """O retrato guarda no máximo 2 afirmações por bloco e nenhum texto de trecho."""
        for e in DADOS["estudos"]:
            for s in e["secoes"]:
                self.assertLessEqual(len(s["afirmacoes"]), g.AFIRMACOES_POR_BLOCO)
                if s["tipo"] == "tradicao":
                    self.assertEqual(s["afirmacoes"], [])
        self.assertNotIn("texto", {k for f in DADOS["fontes"] for k in f})

    def test_escapa_html(self):
        d = copy.deepcopy(DADOS)
        e = d["estudos"][0]
        e["titulo"] = 'Título <script>alert("x")</script> & cia'
        for s in e["secoes"]:
            if s["tipo"] == "concordancias":
                s["afirmacoes"] = ['Diz "x" <b>y</b>']
        saida = g.montar(d)
        html = saida[f"/estudos/{e['slug']}/"]
        self.assertNotIn("<script>alert", html)
        self.assertIn("&lt;script&gt;", html)
        self.assertIn("Diz &quot;x&quot; &lt;b&gt;y&lt;/b&gt;", html)

    def test_resumo_sem_material(self):
        d = copy.deepcopy(DADOS)
        e = d["estudos"][0]
        e["resumo"] = None
        secs = [s for s in e["secoes"] if s["tipo"] == "tradicao"]
        secs[-1]["sem_material"] = True
        site = g.Site(d)
        r = site.resumo(site.estudos[0])
        self.assertIn("ainda não tem material suficiente", r)
        self.assertIn(site.trad[secs[-1]["tradicao_id"]]["nome"], r.split("Para ")[1])

    def test_escrever_apaga_paginas_antigas(self):
        with tempfile.TemporaryDirectory() as tmp:
            destino = Path(tmp)
            velho = destino / "estudos" / "estudo-que-saiu" / "index.html"
            velho.parent.mkdir(parents=True)
            velho.write_text("antigo")
            g.escrever(self.saida, destino)
            self.assertFalse(velho.exists())
            self.assertTrue((destino / "estudos" / "index.html").exists())
            self.assertTrue((destino / "sitemap.xml").exists())

    def test_utilitarios(self):
        self.assertEqual(g.juntar(["a"]), "a")
        self.assertEqual(g.juntar(["a", "b", "c"]), "a, b e c")
        self.assertEqual(g.data_br("2026-10-03"), "03/10/2026")
        self.assertTrue(len(g.cortar("palavra " * 40)) <= 158)
        self.assertEqual(self.site.ref_extenso("ROM.9.16"), "Romanos 9.16")
        self.assertEqual(self.site.ref_extenso("ROM.9"), "Romanos 9")


    def test_toda_imagem_tem_credito(self):
        prefixos = [c["arquivos"] for c in g.CREDITOS]
        for arq in (RAIZ / "imagens").iterdir():
            self.assertTrue(any(arq.name.startswith(p) for p in prefixos), f"imagem sem crédito: {arq.name}")
        for c in g.CREDITOS:
            self.assertRegex(c["url"], r"^https://(commons\.wikimedia\.org/wiki/File:|www\.flickr\.com/photos/|www\.artic\.edu/artworks/\d+$)")
            self.assertNotRegex(c["licenca"], r"(?i)\bNC\b|não comercial")
            self.assertIn(c["origem"], {"Wikimedia Commons", "Flickr", "Art Institute of Chicago"})
            self.assertIn(c["texto"], self.paginas["/sobre/"].replace("&#x27;", "'"))

    def test_foto_da_ortodoxa(self):
        html = self.paginas["/tradicoes/ortodoxa/"]
        self.assertIn("/imagens/igreja-zlatari-bucareste-768.webp", html)
        self.assertIn("Public Domain Mark 1.0", html)
        self.assertIn("M. Cristian-Ioan", html)
        self.assertIn("https://www.flickr.com/photos/sky-clouds/55404283986/", html)
        self.assertNotIn("igreja-zlatari", self.paginas["/tradicoes/catolica/"])

    def test_imagens_das_paginas(self):
        self.assertEqual(set(g.IMAGENS), {c["id"] for c in g.CREDITOS if c["id"] in g.IMAGENS})
        for chave in [*g.IMAGEM_TRADICAO.values(), *g.IMAGEM_ESTUDO.values(), *g.IMAGEM_PAGINA.values()]:
            img = g.IMAGENS[chave]
            for w in img["larguras"]:
                self.assertTrue((RAIZ / f"{img['base'].lstrip('/')}-{w}.webp").exists(), f"{chave} {w}")
        self.assertIn("/imagens/salomao-rainha-saba-768.webp", self.paginas["/como-funciona/"])
        if "/estudos/pecado-original/" in self.paginas:
            self.assertIn("lucas-van-leyden-expulsao", self.paginas["/estudos/pecado-original/"])
        # São Jerônimo (crucifixo com Cristo) fica de fora
        self.assertNotIn("jeronimo", "".join(self.paginas.values()).lower())


class TestLeituraAnon(unittest.TestCase):
    """ler_banco_anon com respostas simuladas da API pública (sem rede)."""

    def setUp(self):
        self.pedidos = []
        trechos = [{"id": f"A-001:{i:04d}", "fonte_id": "A-001", "tradicao_id": "catolica"} for i in range(1000)]
        trechos += [{"id": "B-001:0001", "fonte_id": "B-001", "tradicao_id": "luterana"},
                    {"id": "BIB-007:1", "fonte_id": "BIB-007", "tradicao_id": "catolica"},
                    {"id": "FORA-01:1", "fonte_id": "FORA-01", "tradicao_id": "catolica"}]

        def falsa(caminho, chave):
            self.pedidos.append(caminho)
            self.assertEqual(chave, "anon-de-teste")
            if caminho.startswith("fontes?"):
                return [
                    {"id": "A-001", "titulo": "A", "autor": None, "tipo_autoridade": "oficial", "papel_no_app": "confissao", "liberada": True},
                    {"id": "B-001", "titulo": "B", "autor": "X", "tipo_autoridade": "oficial", "papel_no_app": "obra", "liberada": True},
                    {"id": "BIB-007", "titulo": "Bíblia", "autor": None, "tipo_autoridade": "biblia", "papel_no_app": "biblia", "liberada": True},
                    {"id": "FORA-01", "titulo": "F", "autor": None, "tipo_autoridade": "oficial", "papel_no_app": "obra", "liberada": True},
                    {"id": "NAO-001", "titulo": "N", "autor": None, "tipo_autoridade": "oficial", "papel_no_app": "obra", "liberada": False},
                ]
            if caminho.startswith("fontes_fora_da_busca"):
                return [{"fonte_id": "FORA-01"}]
            if caminho.startswith("fontes_fora_da_comparacao"):
                return []
            if caminho.startswith("trechos?"):
                return trechos[1000:] if "id=gt." in caminho else trechos[:1000]
            if caminho.startswith("estudos?"):
                af = lambda o, f: {"ordem": o, "texto": f"af{o}", "citacoes": [{"trechos": {"fonte_id": f}}]}
                return [{"slug": "s", "versao": 1, "tipo": "tema", "titulo": "T", "tema": "T", "referencias": ["ROM.1.1"],
                         "resumo": None, "publicado_em": "2026-10-04T05:00:00+00:00", "atribuicoes": [], "licencas_derivadas": [],
                         "estudo_secoes": [
                             {"ordem": 2, "tipo": "concordancias", "tradicao_id": None, "subtradicao_id": None,
                              "sem_material_suficiente": False, "estudo_afirmacoes": [af(3, "A-001"), af(1, "B-001"), af(2, "A-001")]},
                             {"ordem": 1, "tipo": "tradicao", "tradicao_id": "catolica", "subtradicao_id": None,
                              "sem_material_suficiente": False, "estudo_afirmacoes": [af(1, "A-001"), af(2, "A-001")]},
                         ]}]
            return [{"tabela": caminho.split("?")[0]}]

        self.original = g._publica
        g._publica = falsa

    def tearDown(self):
        g._publica = self.original

    def test_transforma_como_a_consulta_sql(self):
        d = g.ler_banco_anon("anon-de-teste")
        self.assertEqual([f["id"] for f in d["fontes"]], ["A-001", "B-001", "BIB-007", "FORA-01"])
        self.assertNotIn("liberada", d["fontes"][0])
        # sem Bíblia, sem fonte fora da busca; contagem pelas duas páginas de trechos
        self.assertEqual(d["obras_por_tradicao"], [
            {"tradicao_id": "catolica", "fonte_id": "A-001", "trechos": 1000},
            {"tradicao_id": "luterana", "fonte_id": "B-001", "trechos": 1},
        ])
        self.assertEqual(sum(p.startswith("trechos?") for p in self.pedidos), 2)
        self.assertIn("id=gt.A-001%3A0999", [p for p in self.pedidos if "id=gt." in p][0])
        e = d["estudos"][0]
        self.assertEqual(e["publicado_em"], "2026-10-04")
        self.assertEqual([s["tipo"] for s in e["secoes"]], ["tradicao", "concordancias"])
        self.assertEqual(e["secoes"][0]["afirmacoes"], [])  # texto das seções de tradição não vem
        self.assertEqual(e["secoes"][1]["afirmacoes"], ["af1", "af2"])  # só as duas primeiras
        self.assertEqual(e["secoes"][1]["fontes"], ["A-001", "B-001"])
        self.assertTrue(all("status=eq.publicado" in p for p in self.pedidos if p.startswith("estudos?")))

    def test_data_so_muda_quando_os_dados_mudam(self):
        dados = {"estudos": [1], "tradicoes": [2]}
        anterior = {**dados, "gerado_em": "2026-10-01"}
        self.assertEqual(g.com_data(dados, anterior)["gerado_em"], "2026-10-01")
        self.assertNotEqual(g.com_data({**dados, "estudos": [1, 3]}, anterior)["gerado_em"], "2026-10-01")
        self.assertEqual(len(g.com_data(dados, None)["gerado_em"]), 10)


if __name__ == "__main__":
    unittest.main()
