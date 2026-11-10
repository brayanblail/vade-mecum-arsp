"""Etapa 4 - Gera a pasta content/ para o Quartz (e que também abre no Obsidian).

Estrutura:
  content/index.md                          página inicial
  content/revisao.md                        remissões a conferir (parciais, inferidas)
  content/<grupo>/<doc>/index.md            ficha do ato + texto integral
  content/<grupo>/<doc>/<artigo>.md         uma nota por artigo (é o que aparece na
                                            caixinha ao passar o mouse) + "Citado por"
  content/pdf/<doc>.pdf                     PDF original (link com #page=N)

Links: [[resolucoes/res-arsp-046-2021/art-43#^par7|§ 7º do art. 43 ...]]
Parágrafos, incisos e alíneas têm id de bloco do Obsidian (^par7, ^cpt-inc3-ali-a).
"""
import re
import shutil
from collections import defaultdict
from datetime import date

from indice import Mapa, nome_parte

GRUPOS = ["Leis", "Resoluções", "Consultas públicas"]


def esc(t):
    """Escapa o que o Markdown interpretaria por engano."""
    t = t.replace("\\", "\\\\")
    for ch in ["*", "_", "`", "[", "]", "<", ">", "|", "#", "$", "^", "=="]:
        t = t.replace(ch, "\\" + ch)
    return t


def alias(t):
    return re.sub(r"[\[\]|#^]", "", t).strip()


class Gerador:
    def __init__(self, docs, arestas, pasta_out, pasta_pdfs):
        self.docs = docs
        self.m = Mapa(docs)
        self.arestas = arestas
        self.out = pasta_out
        self.pdfs = pasta_pdfs
        self.citado_por = defaultdict(list)   # (doc, art_id) -> arestas
        self.doc_cita = defaultdict(lambda: defaultdict(int))
        self.doc_citado = defaultdict(lambda: defaultdict(int))
        for a in arestas:
            if a["para_doc"] != a["de_doc"]:
                self.doc_cita[a["de_doc"]][a["para_doc"]] += 1
                self.doc_citado[a["para_doc"]][a["de_doc"]] += 1
            if a.get("para_art") and a.get("tipo") != "interna-mesmo-artigo":
                self.citado_por[(a["para_doc"], a["para_art"])].append(a)

    # ------------------------------------------------------------ links
    def link_disp(self, doc_id, disp_id, texto):
        info = self.m.disp.get((doc_id, disp_id))
        if not info:
            return esc(texto)
        alvo = f"{self.m.pasta(doc_id)}/{info['arquivo']}"
        if info["bloco"]:
            alvo += f"#^{info['bloco']}"
        return f"[[{alvo}|{alias(texto)}]]"

    def link_doc(self, doc_id, texto=None):
        d = self.m.docs[doc_id]
        return f"[[{self.m.pasta(doc_id)}/index|{alias(texto or d['sigla'])}]]"

    def link_origem(self, a):
        """Link para o dispositivo que cita (usado no 'Citado por')."""
        if a["de"] in (None, "preambulo") or (a["de_doc"], a["de"]) not in self.m.disp:
            return self.link_doc(a["de_doc"], self.m.docs[a["de_doc"]]["sigla"] + " · preâmbulo")
        return self.link_disp(a["de_doc"], a["de"], self.m.rotulo_completo(a["de_doc"], a["de"]))

    def com_links(self, texto, refs):
        out, pos = [], 0
        for r in sorted(refs or [], key=lambda r: r["ini"]):
            out.append(esc(texto[pos:r["ini"]]))
            trecho = texto[r["ini"]:r["fim"]]
            com_pos = [(s, alvo) for s, alvo in zip(r.get("spans") or [], r.get("alvos") or []) if s]
            if r.get("disp") and len(com_pos) >= 2:
                # "artigos 37 a 39": cada número aponta para o seu dispositivo
                com_pos.sort()
                partes = [(r["ini"], com_pos[0][0][1], com_pos[0][1])]
                partes += [(s[0], s[1], alvo) for s, alvo in com_pos[1:-1]]
                partes.append((com_pos[-1][0][0], r["fim"], com_pos[-1][1]))
                p = r["ini"]
                for a0, a1, alvo in partes:
                    out.append(esc(texto[p:a0]))
                    out.append(self.link_disp(r["doc"], alvo, texto[a0:a1]))
                    p = a1
            elif r.get("disp"):
                out.append(self.link_disp(r["doc"], r["disp"], trecho))
            elif r.get("conf") == "documento":
                out.append(self.link_doc(r["doc"], trecho))
            elif r.get("url"):
                out.append(f"[{alias(trecho)}]({r['url']})")
            else:
                out.append(esc(trecho))
            pos = r["fim"]
        out.append(esc(texto[pos:]))
        return "".join(out)

    # ------------------------------------------------------------ artigo
    def md_artigo(self, d, parte_id, b, com_ids=True):
        L = []
        bid = (lambda x: f" ^{self.m.bloco(b['id'], x)}") if com_ids else (lambda x: "")
        cab = b["rotulo"] + (f" – {b['titulo']}" if b.get("titulo") else "")
        cap = b["caput"]
        txt = self.com_links(cap["texto"], cap.get("refs"))
        L.append(f"**{esc(cab)}** {txt}".rstrip() + bid(cap["id"]))
        L.append("")
        L += self.md_incisos(cap, bid)
        for p in b["paragrafos"]:
            rot = f"**{esc(p['rotulo'])}**" if p["rotulo"] else ""
            L.append(f"{rot} {self.com_links(p['texto'], p.get('refs'))}".strip() + bid(p["id"]))
            L.append("")
            L += self.md_incisos(p, bid)
        return L

    def md_incisos(self, cont, bid):
        L = []
        for i in cont["incisos"]:
            L.append(f"- **{i['rotulo']} –** {self.com_links(i['texto'], i.get('refs'))}{bid(i['id'])}")
            for a in i.get("alineas", []):
                L.append(f"    - **{a['rotulo']}** {self.com_links(a['texto'], a.get('refs'))}{bid(a['id'])}")
        for a in cont.get("alineas", []):
            L.append(f"- **{a['rotulo']}** {self.com_links(a['texto'], a.get('refs'))}{bid(a['id'])}")
        if L:
            L.append("")
        return L

    def nota_artigo(self, d, parte_id, b):
        info = self.m.disp[(d["id"], b["id"])]
        titulo = f"{d['sigla']} · {info['rotulo']}"
        L = ["---", f'title: "{titulo}"', "tags:", "  - dispositivo", f"  - {d['id']}",
             f"documento: {d['id']}", f"pagina_pdf: {b['pag']}", "---", ""]
        L += self.md_artigo(d, parte_id, b)
        L.append("---")
        L.append(f"{self.link_doc(d['id'])} · [PDF, pág. {b['pag']}](../../pdf/{d['id']}.pdf#page={b['pag']})")
        L.append("")
        cits = self.citado_por.get((d["id"], b["id"]), [])
        if cits:
            L.append(f"## Citado por ({len(cits)})")
            L.append("")
            vistos = set()
            for a in sorted(cits, key=lambda a: (a["de_doc"] != d["id"], a["de_doc"], str(a["de"]))):
                chave = (a["de_doc"], a["de"], a["para"])
                if chave in vistos:
                    continue
                vistos.add(chave)
                alvo = self.m.disp.get((a["para_doc"], a["para"]), {}).get("rotulo", "")
                marca = " *(vínculo inferido)*" if a["conf"] == "inferido" else ""
                marca += " *(dispositivo citado não existe; ligado ao artigo)*" if a["conf"] == "parcial" else ""
                L.append(f"- {self.link_origem(a)} → {esc(alvo)}{marca}")
            L.append("")
        return "\n".join(L)

    # ------------------------------------------------------------ documento
    def nota_documento(self, d):
        L = ["---", f'title: "{d["sigla"]}"', "tags:", "  - documento", f"  - {d['tipo']}",
             f"data: {d['data']}", f"situacao: {d['situacao']}", "---", ""]
        L.append(f"> [!info] {esc(d['titulo'])}")
        L.append(f"> **Situação:** {esc(d['situacao'])} · **Data:** {d['data'][8:10]}/{d['data'][5:7]}/{d['data'][:4]}")
        if d.get("observacao"):
            L.append(f"> ")
            L.append(f"> {esc(d['observacao'])}")
        links = [f"[PDF](../../pdf/{d['id']}.pdf)"]
        if d.get("link_oficial"):
            links.append(f"[página oficial da ARSP]({d['link_oficial']})")
        L.append("> ")
        L.append("> " + " · ".join(links))
        L.append("")
        for rel in filter(None, (d.get("relacoes") or "").split(",")):
            tipo, alvo = rel.split(":")
            if alvo in self.m.docs:
                L.append(f"**{tipo.capitalize()}:** {self.link_doc(alvo)}  ")
        cita, citado = self.doc_cita[d["id"]], self.doc_citado[d["id"]]
        if cita or citado:
            L.append("")
            L.append("## Linhagem")
            L.append("")
            if cita:
                L.append("**Cita:** " + " · ".join(f"{self.link_doc(k)} ({v})" for k, v in sorted(cita.items())))
                L.append("")
            if citado:
                L.append("**Citado por:** " + " · ".join(f"{self.link_doc(k)} ({v})" for k, v in sorted(citado.items())))
                L.append("")
        L.append("## Texto")
        L.append("")
        for p in d["partes"]:
            if p["id"] != "corpo":
                L.append(f"### {esc(p['rotulo'])}")
                L.append("")
            for b in p["blocos"]:
                if b["tipo"] == "titulo":
                    L.append(f"#### {esc(b['rotulo'])}{(' – ' + esc(b['texto'])) if b['texto'] else ''}")
                    L.append("")
                elif b["tipo"] == "texto":
                    refs_l = b.get("refs_linhas", {})
                    if p["id"] != "corpo" and not b.get("fecho"):
                        L.append("```text")
                        L += b["linhas"]
                        L.append("```")
                    else:
                        for i, linha in enumerate(b["linhas"]):
                            L.append(self.com_links(linha, refs_l.get(str(i))))
                            L.append("")
                    L.append("")
                elif b["tipo"] == "artigo":
                    arq = self.m.disp[(d["id"], b["id"])]["arquivo"]
                    n = len(self.citado_por.get((d["id"], b["id"]), []))
                    extra = f" · citado {n}×" if n else ""
                    L += self.md_artigo(d, p["id"], b, com_ids=False)
                    L.append(f"<small>[[{self.m.pasta(d['id'])}/{arq}|abrir {esc(b['rotulo'])}]]{extra}</small>")
                    L.append("")
        return "\n".join(L)

    # ------------------------------------------------------------ páginas gerais
    def home(self):
        L = ["---", "title: Normas de gás canalizado – ARSP/ES", "---", "",
             "Resoluções, leis e consultas públicas da ARSP com **link direto para cada artigo, "
             "parágrafo, inciso e alínea**. Passe o mouse sobre uma remissão para ver o dispositivo; "
             "no fim de cada artigo aparece quem o cita.", "",
             "> [!warning] Piloto",
             f"> {len(self.docs)} documentos, {len(self.arestas)} remissões detectadas automaticamente em "
             f"{date.today():%d/%m/%Y}. Em caso de dúvida, vale o PDF original. Veja [[revisao|o que conferir]].", ""]
        for g in GRUPOS:
            ds = [d for d in self.docs if d["grupo"] == g]
            if not ds:
                continue
            L.append(f"## {g}")
            L.append("")
            for d in sorted(ds, key=lambda d: d["data"], reverse=True):
                n = sum(1 for p in d["partes"] for b in p["blocos"] if b["tipo"] == "artigo")
                c = sum(self.doc_citado[d["id"]].values())
                L.append(f"- {self.link_doc(d['id'])} – {esc(d['titulo'][:140])} *({n} dispositivos"
                         + (f", citado {c}× por outros atos" if c else "") + ")*")
            L.append("")
        L += ["## Como citar no Word", "",
              "Cada artigo tem um endereço fixo, por exemplo `resolucoes/res-arsp-046-2021/art-43`. "
              "Para ir direto a um parágrafo, acrescente `#^par7` (parágrafo 7º), `#^cpt-inc3` (inciso III do caput) "
              "ou `#^cpt-inc1-ali-a` (alínea a do inciso I).", ""]
        return "\n".join(L)

    def revisao(self):
        L = ["---", "title: Remissões a conferir", "---", "",
             "Lista gerada automaticamente. **Parcial**: o dispositivo citado não existe no ato de destino "
             "(possível erro na norma ou numeração alterada); o link vai para o artigo. "
             "**Inferido**: o texto não diz de qual ato é o artigo; foi usado o ato padrão do documento.", ""]
        for conf, titulo in [("parcial", "Parciais"), ("inferido", "Inferidas")]:
            xs = [a for a in self.arestas if a["conf"] == conf]
            L.append(f"## {titulo} ({len(xs)})")
            L.append("")
            for a in xs:
                L.append(f"- {self.link_origem(a)} → {self.link_disp(a['para_doc'], a['para'], self.m.rotulo_completo(a['para_doc'], a['para']))}"
                         f" — “…{esc(a['trecho'].strip()[:160])}…”")
            L.append("")
        return "\n".join(L)

    def executar(self):
        if self.out.exists():
            shutil.rmtree(self.out)
        (self.out / "pdf").mkdir(parents=True)
        n = 0
        for d in self.docs:
            pasta = self.out / self.m.pasta(d["id"])
            pasta.mkdir(parents=True, exist_ok=True)
            (pasta / "index.md").write_text(self.nota_documento(d), encoding="utf-8")
            for p in d["partes"]:
                for b in p["blocos"]:
                    if b["tipo"] == "artigo":
                        arq = self.m.disp[(d["id"], b["id"])]["arquivo"]
                        (pasta / f"{arq}.md").write_text(self.nota_artigo(d, p["id"], b), encoding="utf-8")
                        n += 1
            shutil.copy(self.pdfs / d["arquivo"], self.out / "pdf" / f"{d['id']}.pdf")
        (self.out / "index.md").write_text(self.home(), encoding="utf-8")
        (self.out / "revisao.md").write_text(self.revisao(), encoding="utf-8")
        print(f"  content/: {len(self.docs)} documentos, {n} notas de artigo")


def executar(docs, arestas, pasta_out, pasta_pdfs):
    Gerador(docs, arestas, pasta_out, pasta_pdfs).executar()
