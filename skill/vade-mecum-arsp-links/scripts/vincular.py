#!/usr/bin/env python3
"""Liga as citações de normas num documento Word (.docx) ao Vade-mécum ARSP Gás.

Cada citação reconhecida ("art. 43, § 7º, da Resolução ARSP nº 46/2021", "Cláusula IX do
Contrato de Concessão", "item 23 do Anexo I da Resolução ARSP nº 84/2025") vira hyperlink
para o dispositivo no site, com dica de tela (ScreenTip) que mostra o texto do artigo,
parágrafo, inciso, alínea, cláusula ou item citado. O detector de citações é o mesmo do site
(remissoes.py), copiado do pipeline junto com a base de dispositivos (../dados/base.json).

Uso:
  python vincular.py entrada.docx saida.docx [opções]
  python vincular.py --texto "art. 43, § 7º, da Resolução ARSP nº 46/2021"   (testa uma frase)
  python vincular.py --atos                                                  (lista os atos da base)

Opções:
  --padrao ID      ato das citações que não dizem o ato ("o art. 43"), ex.: res-arsp-046-2021
  --sem-contrato   não liga "Cláusula IX" sem o nome do contrato ao contrato de concessão
  --sem-externos   não liga leis federais e a Constituição ao LexML
  --limite N       tamanho máximo da dica de tela (padrão 255, o limite do Word)
  --offline        não tenta baixar a base mais nova do site
  --json ARQ       grava também o relatório em JSON

Só usa a biblioteca padrão do Python. Processa o corpo, as notas de rodapé e as notas de fim;
não mexe em links que já existem (pode rodar de novo sobre a saída).
"""
import argparse
import json
import re
import sys
import urllib.request
import zipfile
from pathlib import Path
from xml.dom import minidom

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))

import indice  # noqa: E402
import remissoes  # noqa: E402

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PKG = "http://schemas.openxmlformats.org/package/2006/relationships"
CT = "http://schemas.openxmlformats.org/package/2006/content-types"
XML_NS = "http://www.w3.org/XML/1998/namespace"
TIPO_LINK = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink"
COR_LINK = "0563C1"
FORMATO = 1
CTX = "__word__"           # o documento Word faz o papel de "ato de origem" para o detector
PARTES = [("word/document.xml", "texto"), ("word/footnotes.xml", "nota de rodapé"), ("word/endnotes.xml", "nota de fim")]
# "cláusula 5.3.1 do CUSD": não é cláusula do contrato de concessão
RE_OUTRO_CONTRATO = re.compile(r"\bCUSD\b|Contrato\s+de\s+Uso\s+do\s+Servi[çc]o", re.I)
# ordem dos elementos de w:rPr (o Word recusa fora de ordem)
ORDEM_RPR = ["rStyle", "rFonts", "b", "bCs", "i", "iCs", "caps", "smallCaps", "strike", "dstrike", "outline", "shadow",
             "emboss", "imprint", "noProof", "snapToGrid", "vanish", "webHidden", "color", "spacing", "w", "kern",
             "position", "sz", "szCs", "highlight", "u", "effect", "bdr", "shd", "fitText", "vertAlign", "rtl", "cs",
             "em", "lang", "eastAsianLayout", "specVanish", "oMath", "rPrChange"]


# ------------------------------------------------------------------ base de dispositivos

def carregar_base(offline=False):
    """A cópia da skill; se o site responder com uma base do mesmo formato, usa a do site (mais nova)."""
    base = json.loads((AQUI.parent / "dados" / "base.json").read_text(encoding="utf-8"))
    origem = f"cópia da skill (versão {base['versao']})"
    if not offline:
        try:
            with urllib.request.urlopen(base["site"] + "vinculos.json", timeout=6) as r:
                remota = json.loads(r.read().decode("utf-8"))
            if remota.get("formato") == FORMATO and remota.get("docs"):
                igual = remota["versao"] == base["versao"]
                base = remota
                origem = f"site (versão {base['versao']}{', igual à cópia da skill' if igual else ', mais nova que a cópia da skill'})"
        except Exception as e:  # sem rede, domínio bloqueado etc.
            origem += f"; o site não respondeu ({type(e).__name__})"
    return base, origem


class Vinculador:
    """Acha as citações de um texto e devolve os links (posição, endereço, dica de tela)."""

    def __init__(self, base, padrao="", contrato=True, externos=True, limite=255):
        self.site = base["site"]
        docs = base["docs"]
        self.docs = {d["id"]: d for d in docs}
        if padrao and padrao not in self.docs:
            raise SystemExit(f"--padrao {padrao}: ato fora da base. Veja os ids com --atos.")
        self.idx = remissoes.Indice(docs)
        self.mapa = indice.Mapa(docs)
        self.ctx = {"id": CTX, "alvo_padrao": padrao}
        self.contrato = contrato and bool(self.idx.contrato)
        self.externos = externos
        self.limite = limite
        self.unid = {}
        for d in docs:
            for p in d["partes"]:
                for b in p["blocos"]:
                    self.unid[(d["id"], b["id"])] = b
                    for c in [b["caput"]] + b["paragrafos"]:
                        self.unid[(d["id"], c["id"])] = c
                        for i in c["incisos"]:
                            self.unid[(d["id"], i["id"])] = i
                            for a in i.get("alineas", []):
                                self.unid[(d["id"], a["id"])] = a
                        for a in c.get("alineas", []):
                            self.unid[(d["id"], a["id"])] = a

    def documento_cita_contrato(self, sim):
        """Como no site: num texto que cita o contrato de concessão, "Cláusula IX" sozinha é do contrato."""
        if self.contrato and sim:
            self.idx.citam_contrato.add(CTX)
        else:
            self.idx.citam_contrato.discard(CTX)

    def links(self, texto):
        """[(link | None, pendência | None)]: links sem sobreposição, em ordem, e o que não ligou."""
        cita = CTX in self.idx.citam_contrato
        if cita and RE_OUTRO_CONTRATO.search(texto):
            self.idx.citam_contrato.discard(CTX)
        try:
            refs, _, pend = remissoes.resolver_documento(self.idx, self.ctx, "corpo", None, {"texto": texto}, ("texto",))
        finally:
            if cita:
                self.idx.citam_contrato.add(CTX)
        out, falhas = [], []
        for r in refs:
            if r.get("conf") == "externo" and not r.get("url"):
                falhas.append({"citacao": texto[r["ini"]:r["fim"]], "motivo": f"{r.get('externo')}: ato fora da base do site"})
                continue
            out += self.partir(texto, r)
        for p in pend:
            if p["alvo_doc"] == CTX:
                motivo = "a citação não diz o ato (use --padrao com o id do ato)"
            else:
                motivo = f"dispositivo não encontrado em {self.docs[p['alvo_doc']]['sigla']}"
            falhas.append({"citacao": p["texto"], "motivo": motivo})
        return sorted(out, key=lambda x: x["ini"]), falhas

    def partir(self, texto, r):
        """Uma remissão vira um ou mais links ("artigos 37 a 39": um link para cada número com posição)."""
        if r.get("disp"):
            com_pos = sorted((s, a) for s, a in zip(r.get("spans") or [], r.get("alvos") or []) if s)
            if len(com_pos) >= 2:
                partes = [(r["ini"], com_pos[0][0][1], com_pos[0][1])]
                partes += [(s[0], s[1], a) for s, a in com_pos[1:-1]]
                partes.append((com_pos[-1][0][0], r["fim"], com_pos[-1][1]))
                return [self.link_disp(texto, a0, a1, r["doc"], alvo, r["conf"]) for a0, a1, alvo in partes]
            outros = [a for a in (r.get("alvos") or []) if a != r["disp"]]
            return [self.link_disp(texto, r["ini"], r["fim"], r["doc"], r["disp"], r["conf"], outros)]
        if r.get("doc"):
            d = self.docs[r["doc"]]
            return [self.novo(texto, r["ini"], r["fim"], f"{self.site}#{r['doc']}", f"{d['sigla']}: {d['titulo']}",
                              d["sigla"], r["conf"])]
        if r.get("url") and self.externos:
            return [self.novo(texto, r["ini"], r["fim"], r["url"], f"{r['externo']} (abre no LexML)", r["externo"], "externo")]
        return []

    def link_disp(self, texto, a, b, doc, disp, conf, outros=()):
        rot = self.mapa.rotulo_completo(doc, disp)
        aviso = {"inferido": "Vínculo inferido. ", "parcial": "O dispositivo citado não existe; link para o mais próximo. "}
        mais = ""
        if outros:
            mais = " (e " + ", ".join(self.mapa.disp[(doc, o)]["rotulo"] for o in outros if (doc, o) in self.mapa.disp) + ")"
        dica = f"{aviso.get(conf, '')}{rot}{mais}: {self.texto_disp(doc, disp)}"
        return self.novo(texto, a, b, f"{self.site}#{doc}--{disp.replace('_', '-')}", dica, rot, conf)

    def texto_disp(self, doc, disp):
        u = self.unid.get((doc, disp))
        if u is None:
            return ""
        if "caput" not in u:
            return u.get("texto", "")
        t = u["caput"]["texto"]                      # artigo, cláusula ou item: o caput
        if not t and u["paragrafos"]:                # cláusula sem caput: o primeiro item
            p = u["paragrafos"][0]
            t = f"{p['rotulo']} {p['texto']}"
        if not t and u["caput"]["incisos"]:          # anexo que é só lista de incisos
            i = u["caput"]["incisos"][0]
            t = f"{i['rotulo']} – {i['texto']}"
        return f"{u['titulo']}. {t}" if u.get("titulo") else t

    def novo(self, texto, a, b, url, dica, rotulo, conf):
        return {"ini": a, "fim": b, "url": url, "dica": self.corta(dica), "rotulo": rotulo, "conf": conf,
                "citacao": texto[a:b]}

    def corta(self, s):
        s = re.sub(r"\s+", " ", s).strip()
        if len(s) <= self.limite:
            return s
        s = s[:self.limite - 1]
        if " " in s[-25:]:
            s = s[:s.rfind(" ")]
        return s.rstrip(" ,;:–-") + "…"


# ------------------------------------------------------------------ Word (OOXML)

def prefixo(el, ns):
    for k, v in el.attributes.items():
        if v == ns and k.startswith("xmlns:"):
            return k[6:]
        if v == ns and k == "xmlns":
            return ""
    return None


def filhos(no):
    return [c for c in no.childNodes if c.nodeType == c.ELEMENT_NODE]


def eh(no, nome, ns=W):
    return no.nodeType == no.ELEMENT_NODE and no.namespaceURI == ns and no.localName == nome


def texto_de(no):
    return "".join(c.data for c in no.childNodes if c.nodeType == c.TEXT_NODE)


class ParteWord:
    """Um XML do pacote (corpo ou notas) e o arquivo de relações dele."""

    def __init__(self, zin, nome, onde):
        self.nome, self.onde = nome, onde
        self.xml = minidom.parseString(zin.read(nome))
        self.rels_nome = f"word/_rels/{nome.rsplit('/', 1)[1]}.rels"
        if self.rels_nome in zin.namelist():
            self.rels = minidom.parseString(zin.read(self.rels_nome))
        else:
            self.rels = minidom.parseString(f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                                            f'<Relationships xmlns="{PKG}"/>'.encode())
        self.ids = {r.getAttribute("Id") for r in self.rels.getElementsByTagNameNS(PKG, "Relationship")}
        raiz = self.xml.documentElement
        self.pw = prefixo(raiz, W)
        if self.pw is None:
            self.pw = "w"
            raiz.setAttribute("xmlns:w", W)
        self.pr = prefixo(raiz, R)
        if not self.pr:
            self.pr = "r" if not raiz.hasAttribute("xmlns:r") else "rvm"
            raiz.setAttribute(f"xmlns:{self.pr}", R)
        self.n = 0
        self.feitos = []
        self.ja_ligados = 0

    def q(self, nome):
        return f"{self.pw}:{nome}" if self.pw else nome

    def nova_relacao(self, url):
        while True:
            self.n += 1
            rid = f"rIdVM{self.n}"
            if rid not in self.ids:
                break
        self.ids.add(rid)
        el = self.rels.createElementNS(PKG, "Relationship")
        el.setAttribute("Id", rid)
        el.setAttribute("Type", TIPO_LINK)
        el.setAttribute("Target", url)
        el.setAttribute("TargetMode", "External")
        self.rels.documentElement.appendChild(el)
        return rid

    # ---- texto do parágrafo
    def segmentos(self, p):
        """[(texto, run, motivo)] na ordem do parágrafo. motivo None = ligável: run simples (só w:rPr e w:t),
        filho direto do parágrafo e fora de campos. O resto entra no texto, mas não vira link; o motivo diz
        por quê ("link" = já está num link)."""
        segs, campo = [], [0]

        def run(r, motivo):
            kids = filhos(r)
            for k in kids:
                if eh(k, "fldChar"):
                    tipo = k.getAttributeNS(W, "fldCharType")
                    campo[0] += 1 if tipo == "begin" else -1 if tipo == "end" else 0
            ts = [k for k in kids if eh(k, "t")]
            simples = ts and all(eh(k, "rPr") or eh(k, "t") for k in kids)
            if simples and motivo is None and campo[0] == 0:
                if len(ts) > 1:                     # junta os w:t do run num só
                    self.poe_texto(r, "".join(texto_de(t) for t in ts), ts)
                segs.append((texto_de(filhos_t(r)[0]), r, None))
                return
            partes = []
            for k in kids:
                if eh(k, "t"):
                    partes.append(texto_de(k))
                elif eh(k, "tab"):
                    partes.append("\t")
                elif eh(k, "br") or eh(k, "cr"):
                    partes.append("\n")
                elif eh(k, "noBreakHyphen"):
                    partes.append("-")
                elif not (eh(k, "rPr") or eh(k, "fldChar") or eh(k, "instrText") or eh(k, "lastRenderedPageBreak")):
                    partes.append("￼")         # desenho, símbolo, nota etc.: barreira
            segs.append(("".join(partes), r, motivo or ("campo" if campo[0] else "formato")))

        def coleta(no, motivo):
            for c in filhos(no):
                if c.namespaceURI != W:
                    continue
                n = c.localName
                if n == "r":
                    run(c, motivo)
                elif n in ("hyperlink", "fldSimple"):
                    coleta(c, motivo or "link")     # link que já existe: fica como está
                elif n in ("ins", "moveTo"):
                    coleta(c, motivo or "revisão")
                elif n in ("smartTag", "sdt", "sdtContent", "customXml", "dir", "bdo"):
                    coleta(c, motivo or "controle")

        coleta(p, None)
        return segs

    def poe_texto(self, r, txt, ts=None):
        ts = ts or filhos_t(r)
        t = ts[0]
        for k in ts[1:]:
            r.removeChild(k)
        while t.firstChild:
            t.removeChild(t.firstChild)
        t.appendChild(self.xml.createTextNode(txt))
        t.setAttributeNS(XML_NS, "xml:space", "preserve")

    # ---- links
    def processar(self, p, v, falhas):
        segs = self.segmentos(p)
        texto = "".join(s[0] for s in segs)
        if not texto.strip():
            return
        links, ruins = v.links(texto)
        for f in ruins:
            falhas.append(dict(f, onde=self.onde, trecho=trecho(texto, f["citacao"])))
        if not links:
            return
        pos, posicoes, feitos = 0, [], []
        for t, r, motivo in segs:
            posicoes.append([pos, pos + len(t), r, motivo is None, motivo])
            pos += len(t)
        for ln in reversed(links):          # de trás para a frente: dividir runs não muda as posições anteriores
            a, b = ln["ini"], ln["fim"]
            dentro = [s for s in posicoes if (s[0] < b and s[1] > a) or (s[0] == s[1] and a < s[0] < b)]
            if not dentro or not all(s[3] for s in dentro):
                motivos = {s[4] for s in dentro if not s[3]}
                if motivos == {"link"}:
                    self.ja_ligados += 1        # já tem link (o documento já passou pelo script)
                    continue
                txt = {"revisão": "o trecho está numa revisão controlada do Word (aceite ou rejeite e rode de novo)",
                       "campo": "o trecho está num campo do Word", "link": "parte do trecho já está num link",
                       "controle": "o trecho está num controle de conteúdo do Word",
                       "formato": "o trecho tem tabulação, quebra de linha ou outro elemento no meio"}
                falhas.append({"citacao": ln["citacao"], "motivo": "; ".join(txt.get(m, m) for m in sorted(motivos)),
                               "onde": self.onde, "trecho": trecho(texto, ln["citacao"])})
                continue
            self.dividir(posicoes, a)
            self.dividir(posicoes, b)
            runs = [s[2] for s in posicoes if s[3] and s[0] >= a and s[1] <= b and s[1] > s[0]]
            self.embrulhar(p, runs, ln)
            for s in posicoes:
                if s[2] in runs:
                    s[3], s[4] = False, "link"      # já está dentro de um link
            feitos.append(dict(ln, onde=self.onde, trecho=trecho(texto, ln["citacao"])))
        self.feitos += reversed(feitos)

    def dividir(self, posicoes, k):
        for i, (s, e, r, ok, motivo) in enumerate(posicoes):
            if ok and s < k < e:
                t = texto_de(filhos_t(r)[0])
                novo = r.cloneNode(True)
                self.poe_texto(r, t[:k - s])
                self.poe_texto(novo, t[k - s:])
                r.parentNode.insertBefore(novo, r.nextSibling)
                posicoes[i:i + 1] = [[s, k, r, ok, motivo], [k, e, novo, ok, motivo]]
                return

    def embrulhar(self, p, runs, ln):
        h = self.xml.createElementNS(W, self.q("hyperlink"))
        h.setAttributeNS(R, f"{self.pr}:id", self.nova_relacao(ln["url"]))
        h.setAttributeNS(W, self.q("tooltip"), ln["dica"])
        h.setAttributeNS(W, self.q("history"), "1")
        p.insertBefore(h, runs[0])
        no = runs[0]
        while True:
            prox = no.nextSibling
            h.appendChild(no)
            if no is runs[-1]:
                break
            no = prox
        for r in runs:
            self.formata(r)

    def formata(self, r):
        """Azul e sublinhado (formatação direta: funciona mesmo sem o estilo Hyperlink no documento)."""
        rpr = next((k for k in filhos(r) if eh(k, "rPr")), None)
        if rpr is None:
            rpr = self.xml.createElementNS(W, self.q("rPr"))
            r.insertBefore(rpr, r.firstChild)
        for nome, attrs in (("color", {"val": COR_LINK}), ("u", {"val": "single"})):
            for k in filhos(rpr):
                if eh(k, nome):
                    rpr.removeChild(k)
            el = self.xml.createElementNS(W, self.q(nome))
            for a, val in attrs.items():
                el.setAttributeNS(W, self.q(a), val)
            ordem = ORDEM_RPR.index(nome)
            depois = next((k for k in filhos(rpr) if k.namespaceURI == W and k.localName in ORDEM_RPR
                           and ORDEM_RPR.index(k.localName) > ordem), None)
            rpr.insertBefore(el, depois)


def filhos_t(r):
    return [k for k in filhos(r) if eh(k, "t")]


def trecho(texto, cit):
    i = texto.find(cit)
    if i < 0:
        return texto[:120]
    return ("…" if i > 50 else "") + texto[max(0, i - 50):i + len(cit) + 40].strip() + ("…" if i + len(cit) + 40 < len(texto) else "")


def texto_docx(zin):
    out = []
    for nome, _ in PARTES:
        if nome in zin.namelist():
            x = minidom.parseString(zin.read(nome))
            out += [texto_de(t) for t in x.getElementsByTagNameNS(W, "t")]
    return " ".join(out)


def vincular_docx(entrada, saida, v):
    zin = zipfile.ZipFile(entrada)
    v.documento_cita_contrato(bool(remissoes.RE_CITA_CONTRATO.search(texto_docx(zin))))
    novos, feitos, falhas, ja = {}, [], [], 0
    for nome, onde in PARTES:
        if nome not in zin.namelist():
            continue
        pt = ParteWord(zin, nome, onde)
        for p in pt.xml.getElementsByTagNameNS(W, "p"):
            pt.processar(p, v, falhas)
        ja += pt.ja_ligados
        if pt.feitos:
            novos[nome] = pt.xml.toxml(encoding="UTF-8")
            novos[pt.rels_nome] = pt.rels.toxml(encoding="UTF-8")
            feitos += pt.feitos
    if any(n not in zin.namelist() for n in novos):          # arquivo de relações novo: precisa do tipo .rels
        ct = minidom.parseString(zin.read("[Content_Types].xml"))
        if not any(d.getAttribute("Extension") == "rels" for d in ct.getElementsByTagNameNS(CT, "Default")):
            el = ct.createElementNS(CT, "Default")
            el.setAttribute("Extension", "rels")
            el.setAttribute("ContentType", "application/vnd.openxmlformats-package.relationships+xml")
            ct.documentElement.insertBefore(el, ct.documentElement.firstChild)
            novos["[Content_Types].xml"] = ct.toxml(encoding="UTF-8")
    tmp = Path(saida).with_suffix(".tmp-vincular")
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            zout.writestr(item, novos.pop(item.filename, None) or zin.read(item.filename))
        for nome, dados in novos.items():
            zout.writestr(nome, dados)
    zin.close()
    tmp.replace(saida)
    return feitos, falhas, ja


# ------------------------------------------------------------------ relatório

def relatorio(feitos, falhas, origem, ja=0):
    print(f"Base: {origem}")
    if ja:
        print(f"Citações que já tinham link (ficaram como estavam): {ja}")
    conta = {}
    for f in feitos:
        conta[f["conf"]] = conta.get(f["conf"], 0) + 1
    nomes = {"exato": "no dispositivo", "documento": "no ato inteiro", "inferido": "inferidos",
             "parcial": "parciais", "externo": "no LexML", "corrigido": "corrigidos"}
    print(f"Links criados: {len(feitos)}" + (" (" + ", ".join(f"{n} {nomes.get(k, k)}" for k, n in conta.items()) + ")" if feitos else ""))
    for f in feitos:
        marca = {"inferido": "  [INFERIDO: confira]", "parcial": "  [PARCIAL: o dispositivo citado não existe]"}.get(f["conf"], "")
        print(f"  - «{f['citacao']}» → {f['rotulo']}{marca}")
    if falhas:
        print(f"Citações sem link: {len(falhas)}")
        for f in falhas:
            print(f"  - «{f['citacao']}» ({f.get('onde', 'texto')}): {f['motivo']}")


def main():
    ap = argparse.ArgumentParser(description="Liga as citações de um .docx ao Vade-mécum ARSP Gás")
    ap.add_argument("entrada", nargs="?")
    ap.add_argument("saida", nargs="?")
    ap.add_argument("--texto")
    ap.add_argument("--atos", action="store_true")
    ap.add_argument("--padrao", default="")
    ap.add_argument("--sem-contrato", action="store_true")
    ap.add_argument("--sem-externos", action="store_true")
    ap.add_argument("--limite", type=int, default=255)
    ap.add_argument("--offline", action="store_true")
    ap.add_argument("--json")
    a = ap.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    base, origem = carregar_base(a.offline)
    if a.atos:
        print(f"Base: {origem}")
        for d in base["docs"]:
            print(f"  {d['id']:26} {d['sigla']:26} {d['situacao']:10} {d['titulo'][:90]}")
        return
    v = Vinculador(base, a.padrao, not a.sem_contrato, not a.sem_externos, a.limite)
    ja = 0
    if a.texto is not None:
        v.documento_cita_contrato(bool(remissoes.RE_CITA_CONTRATO.search(a.texto)))
        links, falhas = v.links(a.texto)
        feitos = [dict(x, onde="texto") for x in links]
    else:
        if not a.entrada or not a.saida:
            ap.error("informe entrada.docx e saida.docx (ou --texto, ou --atos)")
        feitos, falhas, ja = vincular_docx(a.entrada, a.saida, v)
    relatorio(feitos, falhas, origem, ja)
    if a.texto is not None:
        for f in feitos:
            print(f"    {f['url']}\n    dica: {f['dica']}")
    if a.json:
        Path(a.json).write_text(json.dumps({"base": origem, "links": feitos, "sem_link": falhas},
                                           ensure_ascii=False, indent=1), encoding="utf-8")
    if a.texto is None:
        print(f"Arquivo: {a.saida}")


if __name__ == "__main__":
    main()
