"""Índice comum às saídas: onde fica cada dispositivo e como chamá-lo."""
import json
import re

from comum import int_para_romano

PASTA_GRUPO = {"Leis": "leis", "Resoluções": "resolucoes", "Consultas públicas": "consultas"}


def carregar(docs_meta, pasta_dados):
    docs = [json.loads((pasta_dados / f"{d['id']}.estrutura.json").read_text(encoding="utf-8")) for d in docs_meta]
    arestas = json.loads((pasta_dados / "remissoes.json").read_text(encoding="utf-8"))
    return docs, arestas


def nome_parte(pid):
    """corpo -> '' ; anx1 -> 'Anexo I'"""
    if pid == "corpo":
        return ""
    m = re.match(r"anx(\d+)(b?)$", pid)
    return f"Anexo {int_para_romano(int(m.group(1)))}" if m else pid


def arquivo_artigo(doc, parte_id, art):
    """Nome do arquivo .md (sem extensão) da nota do artigo."""
    if art.get("secao"):
        base = "secao-" + art["num"].replace(".", "-")
    elif art["rotulo"].startswith("Cláusula"):
        base = "clausula-" + art["rotulo"].split()[-1].lower()
    else:
        base = "art-" + art["num"].lower()
    if parte_id != "corpo":
        base = re.sub(r"[^a-z0-9]+", "-", nome_parte(parte_id).lower()) + "-" + base
    return base


class Mapa:
    """Para cada dispositivo: documento, artigo, parte, rótulo legível."""

    def __init__(self, docs):
        self.docs = {d["id"]: d for d in docs}
        self.disp = {}      # (doc, disp_id) -> info
        self.art = {}       # (doc, art_id) -> (parte_id, bloco)
        for d in docs:
            for p in d["partes"]:
                for b in p["blocos"]:
                    if b["tipo"] != "artigo":
                        continue
                    self.art[(d["id"], b["id"])] = (p["id"], b)
                    arq = arquivo_artigo(d, p["id"], b)
                    base = {"doc": d["id"], "art": b["id"], "parte": p["id"], "arquivo": arq}
                    self.disp[(d["id"], b["id"])] = dict(base, rotulo=self.rot_art(p["id"], b), bloco=None)
                    for c in [b["caput"]] + b["paragrafos"]:
                        rc = "" if c is b["caput"] else c["rotulo"]
                        self.disp[(d["id"], c["id"])] = dict(base, rotulo=self.junta(self.rot_art(p["id"], b), rc),
                                                             bloco=self.bloco(b["id"], c["id"]))
                        for i in c["incisos"]:
                            ri = self.junta(rc, f"inciso {i['rotulo']}")
                            self.disp[(d["id"], i["id"])] = dict(base, rotulo=self.junta(self.rot_art(p["id"], b), ri),
                                                                 bloco=self.bloco(b["id"], i["id"]))
                            for a in i.get("alineas", []):
                                self.disp[(d["id"], a["id"])] = dict(
                                    base, rotulo=self.junta(self.rot_art(p["id"], b), ri, f"alínea {a['rotulo']}"),
                                    bloco=self.bloco(b["id"], a["id"]))
                        for a in c.get("alineas", []):
                            self.disp[(d["id"], a["id"])] = dict(
                                base, rotulo=self.junta(self.rot_art(p["id"], b), rc, f"alínea {a['rotulo']}"),
                                bloco=self.bloco(b["id"], a["id"]))

    @staticmethod
    def junta(*partes):
        return ", ".join(p for p in partes if p)

    @staticmethod
    def rot_art(pid, b):
        r = b["rotulo"] if not b.get("secao") else f"item {b['num']}"
        return f"{nome_parte(pid)}, {r}" if pid != "corpo" else r

    @staticmethod
    def bloco(art_id, disp_id):
        """art9_par4_inc1 -> par4-inc1 (id de bloco do Obsidian)."""
        resto = disp_id[len(art_id) + 1:] if disp_id.startswith(art_id + "_") else disp_id
        return re.sub(r"[^a-zA-Z0-9-]", "-", resto)

    def pasta(self, doc_id):
        d = self.docs[doc_id]
        return f"{PASTA_GRUPO.get(d['grupo'], 'outros')}/{doc_id}"

    def rotulo_completo(self, doc_id, disp_id):
        info = self.disp.get((doc_id, disp_id))
        sig = self.docs[doc_id]["sigla"]
        return f"{sig} · {info['rotulo']}" if info else sig
