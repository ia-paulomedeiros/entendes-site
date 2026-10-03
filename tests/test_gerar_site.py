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


if __name__ == "__main__":
    unittest.main()
