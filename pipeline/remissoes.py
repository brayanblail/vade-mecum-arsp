"""Etapa 3 - Encontra remissões nos textos e resolve para o dispositivo citado.

Reconhece cadeias como:
  "§4º do artigo 9 da Resolução ARSP 046/2021"   -> res-arsp-046-2021 art9_par4
  "art. 49, inciso I, alínea "o""                 -> mesmo ato, art49_cpt_inc1_ali-o
  "incisos III e XIII do artigo 7º ... da LC 827" -> lc-827-2016 art7_cpt_inc3 / inc13
  "nos termos do § 2º" (sem artigo)               -> mesmo artigo, § 2º
  "Resolução ARSP nº 061/2023" (sem artigo)       -> o ato inteiro

Cada remissão fica gravada no próprio dispositivo de origem (posição no texto e alvo)
e numa lista de arestas (quem cita quem), usada para gerar os "citado por".

Depois da detecção, aplica as decisões da revisão humana (pipeline/revisoes.csv; ver revisoes.py).

Saída: dados/<id>.estrutura.json atualizado + dados/remissoes.json + dados/nao_resolvidas.csv
       + dados/revisoes_aplicadas.json
"""
import csv
import json
import re

import revisoes
from comum import romano_para_int

N_ART = r"\d{1,3}(?:\s?[º°o](?!\w))?(?:-[A-Z]\b)?"
N_PAR = r"\d{1,2}(?!\d)(?:\s?[º°o](?!\w))?"     # (?!\d): em "§ 2º, 173", o 173 não é parágrafo
ROM = r"[IVXLC]{1,7}\b"     # 7 letras: XXXVIII
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
    ("res", rf"(?P<res>(?:Resolu[çc][ãa]o\s+|Res\.\s*)(?:Normativa\s+)?(?P<res_org>[Aa][Rr][Ss][Pp]|[Aa][Ss][Pp][Ee])(?:\s*[/\-]\s*[A-Z]{{2,6}})?\s*"
            rf"(?:N\s*[º°o]\.?|n\.?\s*[º°o]\.?|No\.?)?\s*0*(?P<res_num>\d{{1,3}})"
            rf"(?:\s*[/\-_]\s*(?P<res_ano>\d{{4}})|{DATA}(?P<res_ano2>\d{{4}}))?)"),
    ("dec", r"(?P<dec>Decis[ãa]o\s+ARSP\s*/\s*DG\s*(?:[Nn]\.?\s*[º°o]\.?\s*)?0*(?P<dec_num>\d{1,3})\s*[/.]\s*(?P<dec_ano>\d{4}))"),
    ("lc", rf"(?P<lc>(?:Lei\s+Complementar|LC)(?:\s+(?:Estadual|Federal))?\s*(?:[Nn]\.?\s*[º°o]\.?\s*)?(?P<lc_num>\d{{1,2}}\.?\d{{3}}|\d{{3}})"
           rf"(?:\s*/\s*(?P<lc_ano>\d{{4}})|{DATA}(?P<lc_ano2>\d{{4}})|,?\s+de\s+(?P<lc_ano3>\d{{4}}))?)"),
    ("lei", rf"(?P<lei>Lei(?:\s+(?P<lei_esf>Estadual|Federal))?\s*(?:[Nn]\.?\s*[º°o]\.?\s*)?(?P<lei_num>\d{{1,2}}\.\d{{3}}|\d{{4,5}})"
            rf"(?:\s*/\s*(?P<lei_ano>\d{{4}})|{DATA}(?P<lei_ano2>\d{{4}})|,?\s+de\s+(?P<lei_ano3>\d{{4}}))?)"),
    ("decreto", rf"(?P<decreto>Decreto(?:\s+(?:Federal|Estadual))?\s*(?:[Nn]\.?\s*[º°o]\.?\s*)?(?P<dc_num>\d{{1,2}}\.?\d{{3}}(?:-R)?)"
                rf"(?:\s*/\s*(?P<dc_ano>\d{{4}})|{DATA}(?P<dc_ano2>\d{{4}})|,?\s+de\s+(?P<dc_ano3>\d{{4}}))?)"),
    ("cf", r"(?P<cf>[Cc]onstitui[çc][ãa]o\s+(?:[Ff]ederal|da\s+Rep[úu]blica)|CF/88)"),
    ("ce", r"(?P<ce>Constitui[çc][ãa]o\s+(?:do\s+Estado|Estadual)(?:\s+do\s+Esp[íi]rito\s+Santo)?)"),
    ("cc", r"(?P<cc>C[óo]digo\s+Civil(?:\s+Brasileiro)?)"),
    ("cdc", r"(?P<cdc>C[óo]digo\s+de\s+Defesa\s+do\s+Consumidor)"),
    ("concessao", r"(?P<concessao>(?:[Cc]ontrato|CONTRATO)\s+(?:de|DE)\s+(?:[Cc]oncess[ãa]o|CONCESS[ÃA]O))"),
    ("codigo", r"(?P<codigo>C[óo]digo\s+(?:Penal|de\s+Processo\s+Civil|Tribut[áa]rio\s+Nacional|Comercial))"),
]

# Dispositivos de contrato: "cláusula XII", "cláusula 12.12.1", "item 4.2.2 da cláusula 4ª",
# "cláusula I, item XXXVII" (item em romano = inciso), "cláusula IV do anexo I".
# Só entram no texto do próprio contrato e nos trechos que citam o contrato de concessão
# (cadeias(..., contrato=True)): nas resoluções, "Anexo I" e "item" seguem como antes.
ORDINAIS = {"primeira": 1, "segunda": 2, "terceira": 3, "quarta": 4, "quinta": 5, "sexta": 6, "sétima": 7,
            "setima": 7, "oitava": 8, "nona": 9, "décima": 10, "decima": 10, "vigésima": 20, "vigesima": 20,
            "trigésima": 30, "trigesima": 30}
ORD_EXT = (r"(?:(?:d[ée]cima|vig[ée]sima|trig[ée]sima)(?:\s+(?:primeira|segunda|terceira|quarta|quinta|sexta|s[ée]tima|oitava|nona))?"
           r"|primeira|segunda|terceira|quarta|quinta|sexta|s[ée]tima|oitava|nona)\b")
NUM_ITEM = r"\d{1,2}(?:\.\d{1,2}){1,3}(?![\d])"
CL_VAL = rf"(?:{NUM_ITEM}|{ROM}|\d{{1,2}}\s?[ªº°a]?(?![\w.])|{ORD_EXT})"
TOKENS_CONTRATO = [
    ("cl", rf"\b(?P<cl>(?:[Ss]ub)?[Cc][Ll][ÁáAa][Uu][Ss][Uu][Ll][Aa][Ss]?\s+{CL_VAL}(?:{LIG}{CL_VAL})*)"),
    ("item", rf"\b(?P<item>(?:[Ss]ub)?(?:[Ii]tem|[Ii]tens|ITEM|ITENS)\s+(?:{NUM_ITEM}|{ROM})(?:{LIG}(?:{NUM_ITEM}|{ROM}))*)"),
    ("anexo", rf"\b(?P<anexo>(?:[Aa]nexo|ANEXO)\s+(?P<anexo_n>{ROM}))"),
]
# Itens numerados de anexo de resolução ("item 108", "item 46 da seção V do Anexo I": Res. 084/2025).
# Só entram no texto de um ato que tem esses itens e nos trechos que citam um ato assim.
TOKENS_ITEM = [
    ("itm", r"\b(?P<itm>(?:[Ii]te(?:m|ns)|ITE(?:M|NS))\s+\d{1,3}(?![\d.,]\d)(?:\s*(?:,|e|a)\s*\d{1,3}(?![\d.,]\d))*)"),
]
RE_TOKS = {(c, i): re.compile("|".join(f"(?P<T_{k}>{p})" for k, p in (TOKENS_CONTRATO if c else [])
                                       + (TOKENS_ITEM if i else []) + TOKENS))
           for c in (False, True) for i in (False, True)}
RE_TOK = RE_TOKS[(False, False)]
NIVEL = {"art": 4, "par": 3, "inc": 2, "ali": 1, "caput": 3, "neste": 4, "anexo": 7, "cl": 6, "item": 3, "itm": 4}
KINDS_CONTRATO = {"cl", "item", "anexo"}
DOC_KINDS = {"self", "res", "dec", "lc", "lei", "decreto", "cf", "ce", "cc", "cdc", "concessao", "codigo"}
RE_CITA_CONTRATO = re.compile(r"contrato\s+de\s+concess[ãa]o", re.I)
# "Cláusula IX" num ato sem cláusulas próprias que cita o contrato em outro trecho (Res. 084/2025, item 26)
RE_CLAUSULA_N = re.compile(r"\b[Cc][Ll][ÁáAa][Uu][Ss][Uu][Ll][Aa]\s+(?:[IVXLC]+\b|\d)")
# Atos que falam de "contrato de concessão" em geral (todos os setores da ARSP), e não do contrato da ES Gás
CONTRATO_GENERICO = {"lc-827-2016"}
LIGA_CADEIA = re.compile(r"^(?:[\s,(]|\b(?:d[oa]s?|n[oa]s?|ao|à|e|ou|bem\s+como|combinado\s+com|c/c|em|seu|sua)\b)*$")
# "item 23, inciso II, do Anexo I da Resolução ...", "art. 49 do Anexo I da Resolução ...": o anexo entre a cadeia e o
# ato (fora do contrato, onde "anexo" já é token); a cadeia liga ao ato e procura primeiro nesse anexo
LIGA_ANEXO = re.compile(r"^[\s,]*(?:d[oa]\s+se[çc][ãa]o\s+[IVXL]+\s*,?\s*)?d[oa]\s+[Aa]nexo\s+(?P<anx>[IVXLC]+|[ÚU]nico)\s*,?\s*"
                        r"(?:d[oa]s?|n[oa]s?)?\s*$")
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
    elif tipo == "itm":
        out = re.findall(r"\d{1,3}", s)
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
    if tipo in ("art", "par", "itm") and re.search(r"\d\s*(?:a|até)\s*(?:[Aa]rt\.?\s*)?\d", s) and len(out) == 2 \
            and out[0].isdigit() and out[1].isdigit() and 0 < int(out[1]) - int(out[0]) < 15:
        out = [str(i) for i in range(int(out[0]), int(out[1]) + 1)]
    return out


class Indice:
    def __init__(self, docs):
        self.docs = {d["id"]: d for d in docs}
        self.por_chave = {}
        self.contrato = None        # o contrato de concessão (tipo 'contrato'), se estiver no cadastro
        for d in docs:
            if d["tipo"] == "contrato":
                self.contrato = d["id"]
                self.por_chave[("concessao",)] = d["id"]
                continue
            num, ano = str(int(d["numero"])), d["ano"]
            if d["tipo"] == "resolucao":
                self.por_chave[("res", "ARSP", num)] = d["id"]
            elif d["tipo"] == "decisao":
                self.por_chave[("dec", num, ano)] = d["id"]
            elif d["tipo"] == "lei-complementar":
                self.por_chave[("lc", num)] = d["id"]
            elif d["tipo"] == "lei":
                self.por_chave[("lei", num)] = d["id"]
        # artigos por documento e parte (as cláusulas do contrato ficam à parte: "art. 9" não é a Cláusula IX;
        # os itens de anexo também: "art. 2" não é o item 2)
        self.arts = {}
        self.cls = {}
        self.itens = {}
        com_clausulas = set()
        for d in docs:
            for p in d["partes"]:
                for b in p["blocos"]:
                    if b["tipo"] != "artigo":
                        continue
                    if d["tipo"] == "contrato":
                        self.cls.setdefault(d["id"], {}).setdefault(p["id"], {})[b["num"]] = b
                    elif b.get("secao"):
                        self.itens.setdefault(d["id"], {}).setdefault(p["id"], {})[b["num"]] = b
                    else:               # anexo que é só lista de incisos: fica com o número "" ("inciso XVIII do Anexo II")
                        self.arts.setdefault(d["id"], {}).setdefault(p["id"], {})[b["num"]] = b
                    if b["rotulo"].startswith("Cláusula"):
                        com_clausulas.add(d["id"])
        # atos sem cláusulas próprias que citam o contrato de concessão: neles, "Cláusula IX" é do contrato
        self.citam_contrato = {d["id"] for d in docs if self.contrato and d["id"] != self.contrato
                               and d["id"] not in CONTRATO_GENERICO and d["id"] not in com_clausulas
                               and any(RE_CITA_CONTRATO.search(texto_de(u, ch)) for _, _, u, ch in unidades(d))}

    def eh_contrato(self, doc_id):
        return doc_id is not None and doc_id in self.cls

    def tem_itens(self, doc_id):
        return doc_id is not None and doc_id in self.itens

    def cita_ato_com_itens(self, texto):
        """O trecho cita outro ato que tem itens de anexo ("item 46 do Anexo I da Resolução ARSP nº 84/2025")."""
        for m in RE_TOK.finditer(texto):
            kind = next(k[2:] for k, v in m.groupdict().items() if k.startswith("T_") and v)
            if kind in DOC_KINDS and kind != "self" and self.tem_itens(self.doc_do_token(kind, m)[0]):
                return True
        return False

    def achar_item(self, doc_id, parte_pref, item, inc=None, ali=None):
        """Item de anexo > inciso > alínea. Procura na parte de origem e depois nas outras."""
        partes = self.itens.get(doc_id, {})
        ordem = ([parte_pref] if parte_pref in partes else []) + [p for p in partes if p != parte_pref]
        b = next((partes[p][item] for p in ordem if item in partes[p]), None)
        if b is None:
            return None, None, None
        alvo, cont = b["id"], b["caput"]
        if inc:
            ii = [x for x in cont["incisos"] if str(x["num"]) == inc]
            if not ii:
                return alvo, b["id"], "parcial"
            cont, alvo = ii[0], ii[0]["id"]
        if ali:
            aa = [x for x in cont.get("alineas", []) if x["letra"] == ali]
            if not aa:
                return alvo, b["id"], "parcial"
            alvo = aa[0]["id"]
        return alvo, b["id"], "exato"

    def achar_clausula(self, doc_id, parte_pref, anexo, cl, item, inc, ali, origem=None):
        """Cláusula > item > inciso > alínea num contrato. Devolve (id_dispositivo, id_cláusula, confiança).
        Sem anexo, procura na parte de origem (citação interna) ou no corpo; se o item não existir lá
        mas existir num anexo ("cláusula 4.1.1 do contrato", que é do Anexo I), liga ao anexo como 'inferido'.
        Item com número repetido no original (dois 6.5): vale o último antes do dispositivo de origem."""
        partes = self.cls.get(doc_id, {})
        if cl and "." in cl:                    # "cláusula 12.12.1" = item 12.12.1 da Cláusula XII
            item, cl = item or cl, cl.split(".")[0]
        if not cl and item:
            cl = item.split(".")[0]
        if not cl:
            return None, None, None
        if anexo:
            ordem = [f"anx{anexo}"]
        else:
            ordem = [parte_pref or "corpo"] + [p for p in partes if p != (parte_pref or "corpo")]

        def desce(b):
            alvo, cont = b["id"], None
            if item:
                ps = [x for x in b["paragrafos"] if x["num"] == item]
                if not ps:
                    return b["id"], "parcial"
                cont = ps[0]
                if len(ps) > 1 and origem:
                    ordem_ids = [x["id"] for x in b["paragrafos"]]
                    pos = next((k for k, x in enumerate(ordem_ids) if origem == x or origem.startswith(x + "_")), None)
                    antes = [x for x in ps if pos is not None and ordem_ids.index(x["id"]) < pos]
                    if antes:
                        cont = antes[-1]
                alvo = cont["id"]
            if inc:
                onde = [cont] if cont else [b["caput"]] + b["paragrafos"]
                ii = [i for c in onde for i in c["incisos"] if str(i["num"]) == inc]
                if not ii:
                    return alvo, "parcial"
                cont = ii[0]
                alvo = cont["id"]
            if ali:
                aa = [a for a in (cont or b["caput"]).get("alineas", []) if a["letra"] == ali]
                if not aa:
                    return alvo, "parcial"
                alvo = aa[0]["id"]
            return alvo, "exato"

        primeira = None
        for i, p in enumerate(ordem):
            b = partes.get(p, {}).get(cl)
            if b is None:
                continue
            alvo, conf = desce(b)
            if conf == "exato":
                # achou fora da parte esperada (outra parte que não a de origem/corpo): só vale como inferido
                inferido = i > 0 and not anexo and parte_pref is None
                return alvo, b["id"], "inferido" if inferido else "exato"
            if primeira is None:
                primeira = (alvo, b["id"], conf)
            if anexo or parte_pref:
                break
        return primeira or (None, None, None)

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
            return self.por_chave.get(("concessao",)), "Contrato de Concessão", None
        if kind == "codigo":
            return None, m.group("codigo"), None
        return None, None, None

    def achar(self, doc_id, parte_pref, art, par=None, inc=None, ali=None, prefere_anexo=False):
        """Desce na hierarquia e devolve (id_dispositivo, id_artigo, confiança)."""
        partes = self.arts.get(doc_id, {})
        ordem = list(partes)
        if parte_pref in partes:
            ordem = [parte_pref] + [p for p in ordem if p != parte_pref]
        elif prefere_anexo and len(partes.get("corpo", {})) <= 10:
            # ato cujo regulamento está no anexo (corpo de poucos artigos): "art. 49 da Resolução X" é do anexo.
            # Com o regulamento no corpo (Res. 080/2024: 90 artigos), "seu art. 19" é do corpo.
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


def cadeias(texto, contrato=False, itens=False):
    """Agrupa os tokens em cadeias ("§ 4º do art. 9") e grupos (cadeias ligadas ao mesmo ato).
    contrato=True também reconhece cláusula, item e anexo (texto do contrato ou que o cita);
    itens=True, "item 108" (ato com itens de anexo ou trecho que cita um ato assim)."""
    toks = []
    for m in RE_TOKS[(contrato, itens)].finditer(mascarar(texto)):
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
            m_anx = LIGA_ANEXO.match(gap) if gap is not None and len(gap) <= 50 else None
            if grupo and (atual or grupo["cadeias"]) and grupo["doc"] is None and gap is not None \
                    and ((len(gap) <= 30 and LIGA_DOC.match(gap)) or m_anx):
                fecha()
                if m_anx:
                    a = m_anx.group("anx")
                    grupo["anexo"] = "1" if a.upper() in ("ÚNICO", "UNICO") else str(romano_para_int(a))
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
        if continua and grupo.get("so_doc") and grupo["doc_antes"][0] != "self" and re.fullmatch(r"\s*[,(]\s*", gap):
            # "Resolução ARSP nº 46/2021, art. 43": o ato fica com o link dele e o artigo é desse ato
            fecha()
            grupos.append(grupo)
            grupo = {"cadeias": [], "doc": None, "doc_antes": grupo["doc_antes"], "ini": m.start(), "fim": m.end()}
            atual = {"itens": [], "dir": None}
        elif not continua:
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
    if kind == "itm":
        for mm in re.finditer(r"\d{1,3}", s):
            out.setdefault(mm.group(0), (base + mm.start(), base + mm.end()))
    elif kind == "art":
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


def valores_contrato(kind, m):
    """Valores de um token de contrato, com a posição de cada um no texto: [(chave, valor, (ini, fim))].
    chave: 'cl' (número da cláusula ou '12.12.1'), 'item' ('4.2.2'), 'item_inc' (item em romano =
    inciso: "cláusula I, item XXXVII") ou 'anexo'."""
    if kind == "anexo":
        n = romano_para_int(m.group("anexo_n"))
        return [("anexo", str(n), (m.start("anexo_n"), m.end("anexo_n")))] if n else []
    s, base = m.group(kind), m.start(kind)
    p0 = re.match(r"\S+\s+", s).end()          # pula a palavra "cláusula" / "item"
    pad = rf"{NUM_ITEM}|{ROM}|\d{{1,2}}\s?[ªº°a]?(?![\w.])|{ORD_EXT}" if kind == "cl" else rf"{NUM_ITEM}|{ROM}"
    out = []
    for mm in re.finditer(pad, s[p0:]):
        v, pos = mm.group(0), (base + p0 + mm.start(), base + p0 + mm.end())
        if re.fullmatch(NUM_ITEM, v):
            out.append(("cl" if kind == "cl" else "item", v, pos))
        elif re.fullmatch(ROM, v):
            n = romano_para_int(v)
            if n:
                out.append(("cl" if kind == "cl" else "item_inc", str(n), pos))
        elif v[0].isdigit():
            out.append(("cl", str(int(re.match(r"\d+", v).group(0))), pos))
        else:
            n = sum(ORDINAIS.get(w, 0) for w in v.lower().split())
            if n:
                out.append(("cl", str(n), pos))
    return out


def contexto_origem(uid):
    m_par = re.search(r"_par(\d+|1u)(?=_|$)", uid)
    m_inc = re.search(r"_inc(\d+)(?=_|$)", uid)
    par = None
    if m_par:
        par = "único" if m_par.group(1) == "1u" else m_par.group(1)
    return {"par": par, "inc": m_inc.group(1) if m_inc else None}


def registrar(refs, arestas, d, art_origem, unidade, texto, ini, fim, alvo_doc, inferido, alvos, pos_val, chaves):
    """Grava uma cadeia resolvida: a remissão no texto (refs) e uma aresta por destino.
    alvos: [(dispositivo, artigo/cláusula, confiança, {chave: valor citado})]."""
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
        return
    conf_txt = "inferido" if inferido else alvos[0][2]
    ref = {"ini": ini, "fim": fim, "doc": alvo_doc, "disp": alvos[0][0], "art": alvos[0][1], "conf": conf_txt}
    if len(alvos) > 1:
        # "artigos 37 a 39", "§§ 2º e 3º", "incisos III e XIII": todos os destinos ficam na remissão
        ref["alvos"] = [x[0] for x in alvos]
        ref["arts"] = [x[1] for x in alvos]
        variam = [k for k in chaves if len({x[3][k] for x in alvos}) > 1]
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
                        "trecho": texto[max(0, ini - 60):fim + 40], "citacao": texto[ini:fim]})


def resolver_documento(idx, d, parte_id, art_origem, unidade, chave):
    texto = texto_de(unidade, chave)
    refs, arestas, pendentes = [], [], []
    eh_contrato = idx.eh_contrato(d["id"])
    # trecho que cita o contrato de concessão: "cláusula", "item" e "anexo" passam a ser remissões;
    # num ato sem cláusulas próprias que cita o contrato, "Cláusula IX" sozinha também (vira inferido)
    cita_contrato = bool(idx.contrato) and d["id"] not in CONTRATO_GENERICO and (
        bool(RE_CITA_CONTRATO.search(texto)) or (d["id"] in idx.citam_contrato and bool(RE_CLAUSULA_N.search(texto))))
    # dentro de uma cláusula de outro ato (o CUSD), "Cláusula XVI" é dele, não do contrato de concessão
    em_clausula = art_origem is not None and art_origem["rotulo"].startswith("Cláusula")
    com_itens = idx.tem_itens(d["id"]) or (bool(idx.itens) and idx.cita_ato_com_itens(texto))
    for g in cadeias(texto, contrato=eh_contrato or cita_contrato, itens=com_itens):
        # documento alvo
        dtok = g["doc"] or g.get("doc_antes")
        alvo_doc, rot_ext, url_ext, mesmo = None, None, None, False
        if dtok and dtok[0] == "orfao":
            continue  # "seu art. X" sem saber de qual ato: melhor não ligar
        if dtok:
            if dtok[0] == "self":
                alvo_doc, mesmo = d["id"], True
            elif dtok[0] == "concessao" and d["id"] in CONTRATO_GENERICO:
                rot_ext = "Contrato de Concessão"
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
                                "trecho": texto[max(0, m.start() - 60):m.end() + 40], "citacao": texto[m.start():m.end()]})
            elif rot_ext:
                refs.append({"ini": m.start(), "fim": m.end(), "externo": rot_ext, "url": url_ext, "conf": "externo"})
            continue

        for cad in g["cadeias"]:
            chaves = ("art", "par", "inc", "ali", "cl", "item", "item_inc", "anexo", "itm")
            vals = {k: [] for k in chaves}
            pos_val = {k: {} for k in chaves}   # valor -> posição no texto
            neste = caput = False
            for kind, m in cad["itens"]:
                if kind == "neste":
                    neste = True
                elif kind == "caput":
                    caput = True
                elif kind in KINDS_CONTRATO:
                    for k, v, pos in valores_contrato(kind, m):
                        vals[k].append(v)
                        pos_val[k].setdefault(v, pos)
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

            if vals["itm"]:
                # "item 108", "item 46 da seção V do Anexo I": item de anexo de resolução (Res. 084/2025)
                if not idx.tem_itens(alvo_doc) or vals["art"]:
                    if alvo_doc not in idx.docs:    # texto de fora (Word): "item 23" sem dizer o ato
                        pendentes.append({"doc": d["id"], "origem": unidade.get("id"), "texto": texto[ini:fim],
                                          "alvo_doc": alvo_doc, "art": f"item {vals['itm'][0]}", "par": None,
                                          "inc": None, "ali": None})
                    continue
                parte_pref = parte_id if alvo_doc == d["id"] else None
                if g.get("anexo"):
                    parte_pref = f"anx{g['anexo']}"
                alvos = []
                for it in vals["itm"]:
                    for i in vals["inc"] or [None]:
                        for al in vals["ali"] or [None]:
                            disp, aid, conf = idx.achar_item(alvo_doc, parte_pref, it, i, al)
                            if disp:
                                alvos.append((disp, aid, conf, {"itm": it, "inc": i, "ali": al}))
                            else:
                                pendentes.append({"doc": d["id"], "origem": unidade.get("id"), "texto": texto[ini:fim],
                                                  "alvo_doc": alvo_doc, "art": f"item {it}", "par": None, "inc": i, "ali": al})
                registrar(refs, arestas, d, art_origem, unidade, texto, ini, fim, alvo_doc, inferido,
                          alvos, pos_val, ("itm", "inc", "ali"))
                continue

            de_contrato = bool(vals["cl"] or vals["item"] or vals["item_inc"] or vals["anexo"])
            destino, inf_destino = alvo_doc, inferido
            if de_contrato and not dtok and not eh_contrato and cita_contrato and not em_clausula:
                # "cláusula I, item XXXVII; na cláusula 12.13 ... do Contrato de Concessão": o ato vem da frase
                destino, inf_destino = idx.contrato, True
            if de_contrato and idx.eh_contrato(destino):
                alvos, k_varia = [], ("cl", "item", "inc", "ali")
                anexo = vals["anexo"][0] if vals["anexo"] else None
                if not vals["cl"] and not vals["item"]:
                    # "anexo II do contrato de concessão": os anexos não têm endereço próprio, liga ao ato
                    if destino != d["id"]:
                        refs.append({"ini": ini, "fim": fim, "doc": destino, "disp": None, "conf": "documento"})
                        arestas.append({"de_doc": d["id"], "de": unidade.get("id"),
                                        "de_art": art_origem["id"] if art_origem else None,
                                        "para_doc": destino, "para": None, "para_art": None, "conf": "documento",
                                        "trecho": texto[max(0, ini - 60):fim + 40], "citacao": texto[ini:fim]})
                    continue
                pos_val["inc"].update(pos_val["item_inc"])
                parte_pref = parte_id if destino == d["id"] else None
                if dtok and dtok[0] == "self" and re.search(r"contrato", dtok[1].group(0), re.I):
                    parte_pref = None       # "item 5.2 deste CONTRATO", dito num anexo: é o item do corpo
                for cl in vals["cl"] or [None]:
                    for it in vals["item"] or [None]:
                        for i in (vals["inc"] + vals["item_inc"]) or [None]:
                            for al in vals["ali"] or [None]:
                                disp, aid, conf = idx.achar_clausula(destino, parte_pref, anexo, cl, it, i, al,
                                                                     origem=unidade.get("id"))
                                if disp:
                                    alvos.append((disp, aid, conf, {"cl": cl, "item": it, "inc": i, "ali": al}))
                                else:
                                    pendentes.append({"doc": d["id"], "origem": unidade.get("id"), "texto": texto[ini:fim],
                                                      "alvo_doc": destino, "art": f"cláusula {cl or (it or '').split('.')[0]}",
                                                      "par": it, "inc": i, "ali": al})
                registrar(refs, arestas, d, art_origem, unidade, texto, ini, fim, destino, inf_destino,
                          alvos, pos_val, k_varia)
                continue
            if de_contrato and not vals["art"]:
                continue        # cláusula/item de um ato que não é contrato: sem link
            if idx.eh_contrato(alvo_doc):
                continue        # o contrato não tem artigos: "arts. 25, § 2º, 173 e 175 da CF" é de outra norma

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
                elif g.get("anexo") and vals["inc"] and not vals["par"]:
                    arts = [""]     # "inciso XVIII do Anexo II da Resolução ...": anexo que é só lista de incisos
                else:
                    continue
            par = vals["par"][0] if len(vals["par"]) == 1 else None
            pars = vals["par"] if len(vals["par"]) > 1 else [par]
            incs = vals["inc"] or [None]
            alis = vals["ali"] or [None]
            parte_pref = parte_id if alvo_doc == d["id"] else None
            if vals["anexo"]:
                parte_pref = f"anx{vals['anexo'][0]}"     # "art. 49 do Anexo I" (trecho que cita o contrato)
            elif g.get("anexo"):
                parte_pref = f"anx{g['anexo']}"           # "art. 49 do Anexo I da Resolução ..."
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
            registrar(refs, arestas, d, art_origem, unidade, texto, ini, fim, alvo_doc, inferido,
                      alvos, pos_val, ("art", "par", "inc", "ali"))
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
    rev = revisoes.Aplicador(revisoes.carregar(), docs)   # decisões da revisão humana (revisoes.csv)
    todas, pend = [], []
    for d in docs:
        n_ref = 0
        for parte_id, art, unidade, chave in unidades(d):
            refs, arestas, pendentes = resolver_documento(idx, d, parte_id, art, unidade, chave)
            de = unidade.get("id") or ("preambulo" if parte_id == "corpo" else parte_id)
            if unidade.get("id") is None and art is None:
                for a in arestas:
                    a["de"] = de
            refs, arestas = rev.aplicar(d["id"], de, art, texto_de(unidade, chave), refs, arestas)
            if chave[0] == "linhas":
                unidade.setdefault("refs_linhas", {})[str(chave[1])] = refs
            else:
                unidade["refs"] = refs
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
    rev.gravar(pasta_dados / "revisoes_aplicadas.json")
    return todas, pend
