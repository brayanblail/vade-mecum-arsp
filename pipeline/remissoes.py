"""Etapa 3 - Encontra remissões nos textos e resolve para o dispositivo citado.

Reconhece cadeias como:
  "§4º do artigo 9 da Resolução ARSP 046/2021"   -> res-arsp-046-2021 art9_par4
  "art. 49, inciso I, alínea "o""                 -> mesmo ato, art49_cpt_inc1_ali-o
  "incisos III e XIII do artigo 7º ... da LC 827" -> lc-827-2016 art7_cpt_inc3 / inc13
  "nos termos do § 2º" (sem artigo)               -> mesmo artigo, § 2º
  "Resolução ARSP nº 061/2023" (sem artigo)       -> o ato inteiro

Cada remissão fica gravada no próprio dispositivo de origem (posição no texto e alvo)
e numa lista de arestas (quem cita quem), usada para gerar os "citado por".

Saída: dados/<id>.estrutura.json atualizado + dados/remissoes.json + dados/nao_resolvidas.csv
"""
import csv
import json
import re

from comum import romano_para_int

N_ART = r"\d{1,3}(?:\s?[º°o](?!\w))?(?:-[A-Z]\b)?"
N_PAR = r"\d{1,2}(?:\s?[º°o](?!\w))?"
ROM = r"[IVXLC]{1,6}\b"
LET = r"[\"“”'‘’]?[a-z](?:\)|[\"“”'‘’])?(?!\w)"
LIG = r"\s*(?:,|e|ou|a|ao|até)\s*"
MES = r"(?:janeiro|fevereiro|março|marco|abril|maio|junho|julho|agosto|setembro|outubro|novembro|dezembro)"
DATA = rf"(?:\s*,?\s*de\s+\d{{1,2}}[º°]?\s*(?:de\s+)?{MES}\s+de\s+)"

TOKENS = [
    ("art", rf"\b[Aa]rt(?:igo)?s?\.?\s*(?P<art>{N_ART}(?:{LIG}(?:[Aa]rt(?:igo)?s?\.?\s*)?{N_ART})*)"),
    ("par", rf"(?P<par>§\s?§?\s*{N_PAR}(?:{LIG}(?:§\s*)?{N_PAR})*|[Pp]ar[áa]grafo\s+[úu]nico|[Pp]ar[áa]grafos?\s+{N_PAR}(?:{LIG}{N_PAR})*)"),
    ("inc", rf"\b(?P<inc>[Ii]ncisos?\s+{ROM}(?:{LIG}{ROM})*)"),
    ("ali", rf"\b(?P<ali>[Aa]l[íi]neas?\s+{LET}(?:{LIG}{LET})*)"),
    ("caput", r"\b(?P<caput>caput)\b"),
    ("neste", r"\b(?P<neste>(?:neste|deste|nesse|desse)\s+[Aa]rtigo)\b"),
    ("self", r"\b(?P<self>(?:desta|da\s+presente|nesta|na\s+presente|dessa|nessa)\s*(?:Resolu[çc][ãa]o|Lei(?:\s+Complementar)?|Decis[ãa]o|Norma|Minuta)"
             r"|(?:deste|neste|do\s+presente)\s+(?:Anexo|[Rr]egulamento|[Cc]ontrato|CONTRATO))\b"),
    ("res", rf"(?P<res>Resolu[çc][ãa]o\s+(?:Normativa\s+)?(?P<res_org>[Aa][Rr][Ss][Pp]|[Aa][Ss][Pp][Ee])(?:\s*[/\-]\s*[A-Z]{{2,6}})?\s*"
            rf"(?:N\s*[º°o]\.?|n\.?\s*[º°o]\.?|No\.?)?\s*0*(?P<res_num>\d{{1,3}})"
            rf"(?:\s*[/\-_]\s*(?P<res_ano>\d{{4}})|{DATA}(?P<res_ano2>\d{{4}}))?)"),
    ("dec", r"(?P<dec>Decis[ãa]o\s+ARSP\s*/\s*DG\s*(?:N\s*[º°o]\s*)?0*(?P<dec_num>\d{1,3})\s*[/.]\s*(?P<dec_ano>\d{4}))"),
    ("lc", rf"(?P<lc>(?:Lei\s+Complementar|LC)(?:\s+(?:Estadual|Federal))?\s*(?:[Nn]\.?\s*[º°o]\.?\s*)?(?P<lc_num>\d{{1,2}}\.?\d{{3}}|\d{{3}})"
           rf"(?:\s*/\s*(?P<lc_ano>\d{{4}})|{DATA}(?P<lc_ano2>\d{{4}})|,?\s+de\s+(?P<lc_ano3>\d{{4}}))?)"),
    ("lei", rf"(?P<lei>Lei(?:\s+(?P<lei_esf>Estadual|Federal))?\s*(?:[Nn]\.?\s*[º°o]\.?\s*)?(?P<lei_num>\d{{1,2}}\.\d{{3}}|\d{{4,5}})"
            rf"(?:\s*/\s*(?P<lei_ano>\d{{4}})|{DATA}(?P<lei_ano2>\d{{4}})|,?\s+de\s+(?P<lei_ano3>\d{{4}}))?)"),
    ("decreto", rf"(?P<decreto>Decreto(?:\s+(?:Federal|Estadual))?\s*(?:[Nn]\.?\s*[º°o]\.?\s*)?(?P<dc_num>\d{{1,2}}\.?\d{{3}}(?:-R)?)"
                rf"(?:\s*/\s*(?P<dc_ano>\d{{4}})|{DATA}(?P<dc_ano2>\d{{4}})|,?\s+de\s+(?P<dc_ano3>\d{{4}}))?)"),
    ("cf", r"(?P<cf>Constitui[çc][ãa]o\s+(?:Federal|da\s+Rep[úu]blica)|CF/88)"),
    ("ce", r"(?P<ce>Constitui[çc][ãa]o\s+(?:do\s+Estado|Estadual)(?:\s+do\s+Esp[íi]rito\s+Santo)?)"),
    ("cc", r"(?P<cc>C[óo]digo\s+Civil(?:\s+Brasileiro)?)"),
    ("cdc", r"(?P<cdc>C[óo]digo\s+de\s+Defesa\s+do\s+Consumidor)"),
    ("concessao", r"(?P<concessao>[Cc]ontrato\s+de\s+[Cc]oncess[ãa]o)"),
    ("codigo", r"(?P<codigo>C[óo]digo\s+(?:Penal|de\s+Processo\s+Civil|Tribut[áa]rio\s+Nacional|Comercial))"),
]
RE_TOK = re.compile("|".join(f"(?P<T_{k}>{p})" for k, p in TOKENS))
NIVEL = {"art": 4, "par": 3, "inc": 2, "ali": 1, "caput": 3, "neste": 4}
DOC_KINDS = {"self", "res", "dec", "lc", "lei", "decreto", "cf", "ce", "cc", "cdc", "concessao", "codigo"}
LIGA_CADEIA = re.compile(r"^(?:[\s,(]|\b(?:d[oa]s?|n[oa]s?|ao|à|e|ou|bem\s+como|combinado\s+com|c/c|em|seu|sua)\b)*$")
LIGA_DOC = re.compile(r"^[\s,]*(?:e\s+(?:em\s+)?seu\s+par[áa]grafo\s+[úu]nico\s+)?(?:caput\s*,?\s*)?(?:d[oa]s?|n[oa]s?|,|\(|todos\s+d[oa]s?|ambos\s+d[oa]s?)?[\s,]*$")

# Leis federais conhecidas (para link externo ao LexML)
FEDERAIS = {"8078": ("1990", "Código de Defesa do Consumidor"), "8987": ("1995", "Lei de Concessões"),
            "9478": ("1997", "Lei do Petróleo"), "14134": ("2021", "Nova Lei do Gás"),
            "10406": ("2002", "Código Civil"), "11445": ("2007", "Saneamento"), "9074": ("1995", ""),
            "11909": ("2009", "Lei do Gás (revogada)"), "12527": ("2011", "LAI"), "13848": ("2019", "Lei das Agências"),
            "13874": ("2019", "Liberdade Econômica"), "9784": ("1999", "Processo Administrativo"),
            "13709": ("2018", "LGPD"), "14133": ("2021", "Licitações"), "8666": ("1993", "Licitações (revogada)")}


def lexml(urn):
    return "https://www.lexml.gov.br/urn/" + urn


def nums_lista(s, tipo):
    """'12, 13, 14 e 15' -> ['12','13','14','15']; '37 a 39' -> ['37','38','39']."""
    if tipo == "art":
        vals = re.findall(r"(\d{1,3})(?:\s?[º°o])?(?:-([A-Z]))?", s)
        out = [n + (f"-{x}" if x else "") for n, x in vals]
    elif tipo == "par":
        if re.search(r"[úu]nico", s):
            return ["único"]
        out = re.findall(r"(\d{1,2})", s)
    elif tipo == "inc":
        out = [str(romano_para_int(r)) for r in re.findall(ROM, re.sub(r"^[Ii]ncisos?\s+", "", s))]
    elif tipo == "ali":
        out = re.findall(r"(?<![a-zà-ú])([a-z])(?![a-zà-ú])", re.sub(r"^[Aa]l[íi]neas?\s+", "", s))
    else:
        out = []
    # intervalos "37 a 39"
    if tipo in ("art", "par") and re.search(r"\d\s*(?:a|até)\s*(?:[Aa]rt\.?\s*)?\d", s) and len(out) == 2 \
            and out[0].isdigit() and out[1].isdigit() and 0 < int(out[1]) - int(out[0]) < 15:
        out = [str(i) for i in range(int(out[0]), int(out[1]) + 1)]
    return out


class Indice:
    def __init__(self, docs):
        self.docs = {d["id"]: d for d in docs}
        self.por_chave = {}
        for d in docs:
            num, ano = str(int(d["numero"])), d["ano"]
            if d["tipo"] == "resolucao":
                self.por_chave[("res", "ARSP", num)] = d["id"]
            elif d["tipo"] == "decisao":
                self.por_chave[("dec", num, ano)] = d["id"]
            elif d["tipo"] == "lei-complementar":
                self.por_chave[("lc", num)] = d["id"]
            elif d["tipo"] == "lei":
                self.por_chave[("lei", num)] = d["id"]
        # artigos por documento e parte
        self.arts = {}
        for d in docs:
            for p in d["partes"]:
                for b in p["blocos"]:
                    if b["tipo"] == "artigo":
                        self.arts.setdefault(d["id"], {}).setdefault(p["id"], {})[b["num"]] = b

    def doc_do_token(self, kind, m):
        """Retorna (doc_id_ou_None, rótulo, url_externa)."""
        g = m.groupdict()
        if kind == "res":
            org, num = g["res_org"].upper(), str(int(g["res_num"]))
            ano = g.get("res_ano") or g.get("res_ano2")
            if org == "ARSP" and ("res", "ARSP", num) in self.por_chave:
                did = self.por_chave[("res", "ARSP", num)]
                if not ano or ano == self.docs[did]["ano"]:
                    return did, None, None
            return None, f"Res. {org} {int(num):03d}/{ano or '?'}", None
        if kind == "dec":
            k = ("dec", str(int(g["dec_num"])), g["dec_ano"])
            return self.por_chave.get(k), f"Decisão ARSP/DG {g['dec_num']}/{g['dec_ano']}", None
        if kind == "lc":
            num = g["lc_num"].replace(".", "")
            ano = g.get("lc_ano") or g.get("lc_ano2") or g.get("lc_ano3")
            if ("lc", num) in self.por_chave:
                return self.por_chave[("lc", num)], None, None
            return None, f"LC {g['lc_num']}/{ano or '?'}", None
        if kind == "lei":
            num = g["lei_num"].replace(".", "")
            ano = g.get("lei_ano") or g.get("lei_ano2") or g.get("lei_ano3")
            if ("lei", num) in self.por_chave and g.get("lei_esf") != "Federal":
                return self.por_chave[("lei", num)], None, None
            if num in FEDERAIS and (g.get("lei_esf") == "Federal" or not ano or ano == FEDERAIS[num][0]):
                a = ano or FEDERAIS[num][0]
                return None, f"Lei {g['lei_num']}/{a}", lexml(f"urn:lex:br:federal:lei:{a};{num}")
            if g.get("lei_esf") == "Federal" and ano:
                return None, f"Lei {g['lei_num']}/{ano}", lexml(f"urn:lex:br:federal:lei:{ano};{num}")
            return None, f"Lei {g['lei_num']}/{ano or '?'}", None
        if kind == "decreto":
            ano = g.get("dc_ano") or g.get("dc_ano2") or g.get("dc_ano3")
            return None, f"Decreto {g['dc_num']}/{ano or '?'}", None
        if kind == "cf":
            return None, "Constituição Federal", lexml("urn:lex:br:federal:constituicao:1988-10-05;1988")
        if kind == "ce":
            return None, "Constituição do Estado do ES", None
        if kind == "cc":
            return None, "Código Civil", lexml("urn:lex:br:federal:lei:2002-01-10;10406")
        if kind == "cdc":
            return None, "Código de Defesa do Consumidor", lexml("urn:lex:br:federal:lei:1990-09-11;8078")
        if kind == "concessao":
            return None, "Contrato de Concessão", None
        if kind == "codigo":
            return None, m.group("codigo"), None
        return None, None, None

    def achar(self, doc_id, parte_pref, art, par=None, inc=None, ali=None, prefere_anexo=False):
        """Desce na hierarquia e devolve (id_dispositivo, id_artigo, confiança)."""
        partes = self.arts.get(doc_id, {})
        ordem = list(partes)
        if parte_pref in partes:
            ordem = [parte_pref] + [p for p in ordem if p != parte_pref]
        elif prefere_anexo:
            ordem = [p for p in ordem if p != "corpo"] + (["corpo"] if "corpo" in partes else [])
        ordem = [p for p in ordem if partes[p]]  # partes sem artigos não servem
        b = None
        for p in ordem:
            if art in partes[p]:
                b = partes[p][art]
                break
        if b is None:
            return None, None, None
        alvo, conf = b["id"], "exato"
        cont = b["caput"]
        if par:
            ps = [x for x in b["paragrafos"] if (par == "único" and x["num"] == 0) or str(x["num"]) == par]
            if ps:
                cont = ps[0]
                alvo = cont["id"]
            else:
                return b["id"], b["id"], "parcial"
        if inc:
            ii = [x for x in cont["incisos"] if str(x["num"]) == inc]
            if ii:
                cont = ii[0]
                alvo = cont["id"]
            else:
                return alvo, b["id"], "parcial"
        if ali:
            aa = [x for x in cont.get("alineas", []) if x["letra"] == ali]
            if aa:
                alvo = aa[0]["id"]
            else:
                return alvo, b["id"], "parcial"
        return alvo, b["id"], conf


def unidades(doc):
    """Percorre os textos do documento: (parte_id, artigo|None, dispositivo, chave_texto)."""
    for p in doc["partes"]:
        for b in p["blocos"]:
            if b["tipo"] == "texto":
                for i in range(len(b["linhas"])):
                    yield p["id"], None, b, ("linhas", i)
            elif b["tipo"] == "artigo":
                for cont in [b["caput"]] + b["paragrafos"]:
                    yield p["id"], b, cont, ("texto",)
                    for inc in cont["incisos"]:
                        yield p["id"], b, inc, ("texto",)
                        for a in inc.get("alineas", []):
                            yield p["id"], b, a, ("texto",)
                    for a in cont.get("alineas", []):
                        yield p["id"], b, a, ("texto",)


def texto_de(disp, chave):
    return disp["linhas"][chave[1]] if chave[0] == "linhas" else disp["texto"]


RE_APOS_DOC = re.compile(r"[\s,]*(?:exceto|salvo|inclusive|especialmente)\s+(?:o|a|os|as|no|na|nos|nas|em\s+seu|em\s+sua|seu|sua)?\s*")
RE_NOTA = re.compile(r"\((?:Reda[çc][ãa]o dada|Inclu[íi]d[oa]|Acrescid[oa]|Par[áa]grafo [úu]nico transformado|Dispositivo revogado|Revogad[oa]|Vide|Vetad[oa]|Renumerad[oa])[^)]*\)", re.I)


def mascarar(texto):
    """Notas editoriais "(Redação dada pela ...)" não são remissões normativas."""
    return RE_NOTA.sub(lambda m: " " * len(m.group(0)), texto)


def cadeias(texto):
    toks = []
    for m in RE_TOK.finditer(mascarar(texto)):
        kind = next(k[2:] for k, v in m.groupdict().items() if k.startswith("T_") and v)
        toks.append((kind, m))
    grupos, atual, grupo = [], None, None

    def fecha():
        nonlocal atual
        if atual and atual["itens"]:
            grupo["cadeias"].append(atual)
        atual = None

    for i, (kind, m) in enumerate(toks):
        prev_end = toks[i - 1][1].end() if i else None
        gap = texto[prev_end:m.start()] if prev_end is not None else None
        if kind in DOC_KINDS:
            if grupo and (atual or grupo["cadeias"]) and grupo["doc"] is None and gap is not None \
                    and len(gap) <= 30 and LIGA_DOC.match(gap):
                fecha()
                grupo["doc"] = (kind, m)
                grupo["fim"] = m.end()
                grupos.append(grupo)
                grupo = None
            else:
                fecha()
                if grupo:
                    grupos.append(grupo)
                grupo = {"cadeias": [], "doc": None, "doc_antes": (kind, m), "ini": m.start(), "fim": m.end(),
                         "so_doc": True}
            continue
        nv = NIVEL[kind]
        continua = gap is not None and len(gap) <= 18 and LIGA_CADEIA.match(gap) and grupo is not None
        if not continua:
            fecha()
            if grupo:
                grupos.append(grupo)
            # documento citado logo antes, entre parênteses: "Resolução X (§4º do artigo 9)"
            antes = None
            gap_doc = texto[toks[i - 1][1].end():m.start()] if i else ""
            if i and toks[i - 1][0] in DOC_KINDS and toks[i - 1][0] != "self" and (len(gap_doc) <= 3 or (
                    len(gap_doc) <= 18 and RE_APOS_DOC.fullmatch(gap_doc))):
                antes = toks[i - 1]
                if grupos and grupos[-1].get("so_doc") and grupos[-1]["doc_antes"] is antes:
                    grupos.pop()
            # "... Contrato de Concessão ..., especialmente o disposto em seu art. 19"
            elif re.search(r"\b(?:em\s+)?(?:seu|sua)\s*$", texto[max(0, m.start() - 12):m.start()]):
                anteriores = [t for t in toks[:i] if t[0] in DOC_KINDS and t[0] != "self"]
                antes = anteriores[-1] if anteriores else ("orfao", None)
            grupo = {"cadeias": [], "doc": None, "doc_antes": antes, "ini": m.start(), "fim": m.end()}
            atual = {"itens": [], "dir": None}
        if atual is None:
            atual = {"itens": [], "dir": None}
        if atual["itens"]:
            ult = NIVEL[atual["itens"][-1][0]]
            nova = nv == ult or (atual["dir"] == "asc" and nv < ult) or (atual["dir"] == "desc" and nv > ult)
            if nova:
                fecha()
                atual = {"itens": [], "dir": None}
            elif atual["dir"] is None:
                atual["dir"] = "asc" if nv > ult else "desc"
        atual["itens"].append((kind, m))
        grupo["fim"] = m.end()
    fecha()
    if grupo:
        grupos.append(grupo)
    return grupos


def posicoes_valores(kind, m):
    """Onde cada valor de uma lista aparece no texto: {'37': (ini, fim), '39': (...)}.
    Valores só implícitos num intervalo ("37 a 39" -> 38) não têm posição."""
    s, base, out = m.group(kind), m.start(kind), {}
    if kind == "art":
        for mm in re.finditer(r"(\d{1,3})(?:\s?[º°o](?!\w))?(?:-([A-Z])\b)?", s):
            v = mm.group(1) + (f"-{mm.group(2)}" if mm.group(2) else "")
            out.setdefault(v, (base + mm.start(), base + mm.end()))
    elif kind == "par":
        if re.search(r"[úu]nico", s):
            out["único"] = (base, base + len(s))
        for mm in re.finditer(r"(\d{1,2})(?:\s?[º°o](?!\w))?", s):
            out.setdefault(mm.group(1), (base + mm.start(), base + mm.end()))
    elif kind == "inc":
        for mm in re.finditer(ROM, s):
            n = romano_para_int(mm.group(0))
            if n:
                out.setdefault(str(n), (base + mm.start(), base + mm.end()))
    elif kind == "ali":
        pref = re.match(r"[Aa]l[íi]neas?\s+", s)
        p0 = pref.end() if pref else 0
        for mm in re.finditer(r"(?<![a-zà-ú])([a-z])(?![a-zà-ú])", s[p0:]):
            out.setdefault(mm.group(1), (base + p0 + mm.start(), base + p0 + mm.end()))
    return out


def contexto_origem(uid):
    m_par = re.search(r"_par(\d+|1u)(?=_|$)", uid)
    m_inc = re.search(r"_inc(\d+)(?=_|$)", uid)
    par = None
    if m_par:
        par = "único" if m_par.group(1) == "1u" else m_par.group(1)
    return {"par": par, "inc": m_inc.group(1) if m_inc else None}


def resolver_documento(idx, d, parte_id, art_origem, unidade, chave):
    texto = texto_de(unidade, chave)
    refs, arestas, pendentes = [], [], []
    for g in cadeias(texto):
        # documento alvo
        dtok = g["doc"] or g.get("doc_antes")
        alvo_doc, rot_ext, url_ext, mesmo = None, None, None, False
        if dtok and dtok[0] == "orfao":
            continue  # "seu art. X" sem saber de qual ato: melhor não ligar
        if dtok:
            if dtok[0] == "self":
                alvo_doc, mesmo = d["id"], True
            else:
                alvo_doc, rot_ext, url_ext = idx.doc_do_token(dtok[0], dtok[1])
        else:
            alvo_doc = d.get("alvo_padrao") or d["id"]
            mesmo = alvo_doc == d["id"]
        inferido = not dtok and alvo_doc != d["id"]

        if g.get("so_doc") or not g["cadeias"]:
            # citação do ato inteiro
            m = dtok[1]
            if alvo_doc and alvo_doc != d["id"]:
                refs.append({"ini": m.start(), "fim": m.end(), "doc": alvo_doc, "disp": None, "conf": "documento"})
                arestas.append({"de_doc": d["id"], "de": unidade.get("id"), "de_art": art_origem["id"] if art_origem else None,
                                "para_doc": alvo_doc, "para": None, "para_art": None, "conf": "documento",
                                "trecho": texto[max(0, m.start() - 60):m.end() + 40]})
            elif rot_ext:
                refs.append({"ini": m.start(), "fim": m.end(), "externo": rot_ext, "url": url_ext, "conf": "externo"})
            continue

        for cad in g["cadeias"]:
            vals = {k: [] for k in ("art", "par", "inc", "ali")}
            pos_val = {k: {} for k in ("art", "par", "inc", "ali")}   # valor -> posição no texto
            neste = caput = False
            for kind, m in cad["itens"]:
                if kind == "neste":
                    neste = True
                elif kind == "caput":
                    caput = True
                else:
                    vals[kind] = nums_lista(m.group(kind), kind)
                    pos_val[kind] = posicoes_valores(kind, m)
            ini = cad["itens"][0][1].start()
            fim = cad["itens"][-1][1].end()
            if g["doc"] and cad is g["cadeias"][-1]:
                fim = g["doc"][1].end()

            if rot_ext and not alvo_doc:
                refs.append({"ini": ini, "fim": fim, "externo": rot_ext, "url": url_ext, "conf": "externo"})
                continue
            if alvo_doc is None:
                continue

            arts = vals["art"]
            tentar_sem = None
            if not arts:
                if (neste or vals["par"] or vals["inc"] or vals["ali"] or caput) and art_origem and mesmo:
                    arts = [art_origem["num"]]
                    # "alínea a)" sozinha = mesmo inciso; "inciso II" sozinho = mesmo caput/parágrafo
                    ctx = contexto_origem(unidade.get("id") or "")
                    if vals["ali"] and not vals["inc"] and not vals["par"] and ctx["inc"]:
                        vals["inc"], vals["par"] = [ctx["inc"]], [ctx["par"]] if ctx["par"] else []
                        tentar_sem = "inc"
                    elif vals["inc"] and not vals["par"] and ctx["par"] and not caput and not neste:
                        vals["par"] = [ctx["par"]]
                        tentar_sem = "par"
                else:
                    continue
            par = vals["par"][0] if len(vals["par"]) == 1 else None
            pars = vals["par"] if len(vals["par"]) > 1 else [par]
            incs = vals["inc"] or [None]
            alis = vals["ali"] or [None]
            parte_pref = parte_id if alvo_doc == d["id"] else None
            prefere_anexo = alvo_doc != d["id"]
            alvos = []
            for a in arts:
                for p in pars:
                    for i in incs:
                        for al in alis:
                            disp, aid, conf = idx.achar(alvo_doc, parte_pref, a, p, i, al, prefere_anexo)
                            if conf == "parcial" and tentar_sem == "par":
                                d2 = idx.achar(alvo_doc, parte_pref, a, None, i, al, prefere_anexo)
                                if d2[2] == "exato":
                                    disp, aid, conf = d2
                            elif conf == "parcial" and tentar_sem == "inc":
                                d2 = idx.achar(alvo_doc, parte_pref, a, p, None, al, prefere_anexo)
                                if d2[2] == "exato":
                                    disp, aid, conf = d2
                            if disp:
                                alvos.append((disp, aid, conf, {"art": a, "par": p, "inc": i, "ali": al}))
                            else:
                                pendentes.append({"doc": d["id"], "origem": unidade.get("id"), "texto": texto[ini:fim],
                                                  "alvo_doc": alvo_doc, "art": a, "par": p, "inc": i, "ali": al})
            # "neste artigo" apontando para o próprio artigo não ajuda: não vira link
            if art_origem and alvo_doc == d["id"]:
                alvos = [x for x in alvos if x[0] != art_origem["id"]]
            # o mesmo destino pode aparecer duas vezes (ex.: parcial que caiu no artigo)
            vistos, unicos = set(), []
            for x in alvos:
                if x[0] not in vistos:
                    vistos.add(x[0])
                    unicos.append(x)
            alvos = unicos
            if not alvos:
                continue
            conf_txt = "inferido" if inferido else alvos[0][2]
            ref = {"ini": ini, "fim": fim, "doc": alvo_doc, "disp": alvos[0][0], "art": alvos[0][1], "conf": conf_txt}
            if len(alvos) > 1:
                # "artigos 37 a 39", "§§ 2º e 3º", "incisos III e XIII": todos os destinos ficam na remissão
                ref["alvos"] = [x[0] for x in alvos]
                ref["arts"] = [x[1] for x in alvos]
                variam = [k for k in ("art", "par", "inc", "ali") if len({x[3][k] for x in alvos}) > 1]
                if len(variam) == 1:
                    k = variam[0]
                    ref["spans"] = [list(pos_val[k][x[3][k]]) if x[3][k] in pos_val[k] else None for x in alvos]
            refs.append(ref)
            for disp, aid, conf, _ in alvos:
                if alvo_doc == d["id"] and art_origem and aid == art_origem["id"]:
                    tipo_aresta = "interna-mesmo-artigo"
                elif alvo_doc == d["id"]:
                    tipo_aresta = "interna"
                else:
                    tipo_aresta = "externa"
                arestas.append({"de_doc": d["id"], "de": unidade.get("id"), "de_art": art_origem["id"] if art_origem else None,
                                "para_doc": alvo_doc, "para": disp, "para_art": aid,
                                "conf": "inferido" if inferido else conf, "tipo": tipo_aresta,
                                "trecho": texto[max(0, ini - 60):fim + 40]})
    # remove sobreposições (mantém a primeira)
    refs.sort(key=lambda r: (r["ini"], -r["fim"]))
    limpo, fim_ant = [], -1
    for r in refs:
        if r["ini"] >= fim_ant:
            limpo.append(r)
            fim_ant = r["fim"]
    return limpo, arestas, pendentes


def executar(docs_meta, pasta_dados):
    docs = [json.loads((pasta_dados / f"{d['id']}.estrutura.json").read_text(encoding="utf-8")) for d in docs_meta]
    idx = Indice(docs)
    todas, pend = [], []
    for d in docs:
        n_ref = 0
        for parte_id, art, unidade, chave in unidades(d):
            refs, arestas, pendentes = resolver_documento(idx, d, parte_id, art, unidade, chave)
            if chave[0] == "linhas":
                unidade.setdefault("refs_linhas", {})[str(chave[1])] = refs
            else:
                unidade["refs"] = refs
            if unidade.get("id") is None and art is None:
                for a in arestas:
                    a["de"] = "preambulo" if parte_id == "corpo" else parte_id
            todas += arestas
            pend += pendentes
            n_ref += len(refs)
        (pasta_dados / f"{d['id']}.estrutura.json").write_text(json.dumps(d, ensure_ascii=False, indent=1),
                                                                encoding="utf-8")
        ext = sum(1 for a in todas if a["de_doc"] == d["id"] and a["para_doc"] != d["id"])
        print(f"  {d['id']:22s} remissões no texto={n_ref:4d}  para outros atos={ext:3d}")
    (pasta_dados / "remissoes.json").write_text(json.dumps(todas, ensure_ascii=False, indent=1), encoding="utf-8")
    with open(pasta_dados / "nao_resolvidas.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=["doc", "origem", "texto", "alvo_doc", "art", "par", "inc", "ali"], delimiter=";")
        w.writeheader()
        w.writerows(pend)
    print(f"  total de arestas: {len(todas)}  |  não resolvidas: {len(pend)}")
    return todas, pend
