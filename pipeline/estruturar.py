"""Etapa 2 - Transforma as linhas extraídas em estrutura normativa.

Hierarquia: parte (corpo / anexo) > títulos (capítulo, seção) > artigo >
caput | parágrafo > inciso > alínea.

Para documentos não articulados (nota técnica) usa seções numeradas (1., 1.1., ...).
Para o modelo de contrato (anexo do CUSD) usa cláusulas e itens numerados.
Anexo de resolução sem artigos (Res. 084/2025): itens numerados "1." a "114." no lugar dos
artigos (anx1_it23), sob seções "V. DO CUSTO DE CAPITAL"; anexo que é só uma lista de
incisos (definições) vira um bloco com o id do anexo (anx2 > anx2_cpt > anx2_cpt_inc18).

Cada dispositivo recebe um identificador estável no estilo LexML:
  art9, art9_cpt, art9_par4, art9_par4_inc1, art9_cpt_inc3_ali-a
  e, em anexo, o prefixo anx1_ (anx1_art49_cpt_inc1_ali-o).

Saída: dados/<id>.estrutura.json
"""
import json
import re

from comum import int_para_romano, ordinal, romano_para_int

RE_TITULO = re.compile(
    r"^(T[ÍI]TULO|CAP[ÍI]TULO|Cap[íi]tulo|SE[ÇC][ÃA]O|Se[çc][ãa]o|SUBSE[ÇC][ÃA]O|Subse[çc][ãa]o|LIVRO)"
    r"\s+([IVXLC]+|[ÚU]NIC[OA])\b\s*[-–—.:]?\s*(.*)$")
RE_ANEXO = re.compile(r"^(ANEXO|Anexo)(?:\s+([IVXLC]+|[ÚU]NICO))?\s*[-–—.:]?\s*(.*)$")
RE_ART = re.compile(r"^Art(?:igo)?\.?\s*(\d{1,3})\s*[º°o]?\s?(?:-([A-Z])(?=[\s.:º°]))?\s*[.:\-–—]?\s*(.*)$")
RE_PAR = re.compile(r"^(?:§\s*(\d{1,2})\s*[º°o]?\s*[.:\-–—]?|Par[áa]grafo\s+[úu]nico\s*[.:\-–—]?)\s*(.*)$")
RE_INC = re.compile(r"^([IVXLC]{1,7})\s*[-–—.)]\s*(.*)$")     # 7 letras: XXXVIII
RE_ALI = re.compile(r"^([a-z])\s*\)\s*(.*)$")
RE_FECHO = re.compile(r"^(Pal[áa]cio Anchieta|Vit[óo]ria\s*[/(]?\s*ES\)?,?\s+(?:em\s+)?\d{1,2}|Vit[óo]ria,\s+\d{1,2}|Bras[íi]lia,\s+\d{1,2})")
RE_CLAUSULA = re.compile(r"^CL[ÁA]USULA\s+([IVXLC]+)\b\.?\s*[-–—.:]?\s*(.*)$")
RE_ITEM = re.compile(r"^(\d{1,2}(?:\.\d{1,2}){1,3})\.?\s+(\S.*)$")
RE_SECAO_NT = re.compile(r"^(\d{1,2}(?:\.\d{1,2}){0,2})\.?\s+([A-ZÁÉÍÓÚÂÊÔÃÕÇ][A-ZÁÉÍÓÚÂÊÔÃÕÇ0-9 \-–,/()º°ª]{2,})$")
# Anexo de itens numerados (Res. 084/2025, Anexo I): seção "V. DO CUSTO DE CAPITAL",
# subseção "VII.1 Avaliação Qualitativa" e itens "1." a "114." (numeração única no anexo)
RE_ITEM_ANX = re.compile(r"^(\d{1,3})\.(?:\s+|(?=[A-ZÁÉÍÓÚ]))(\S.*)$")    # "11.Tributos" (sem espaço) também
RE_TABELA = re.compile(r" \| ")       # linha de tabela transcrita no extrair.py (colunas separadas por " | ")
RE_SECAO_ANX = re.compile(r"^([IVXL]{1,6})\.\s+((?:D[AO]S?|DE)\s.+)$")
RE_SUBSECAO_ANX = re.compile(r"^([IVXL]{1,6})\.(\d{1,2})\s+([A-ZÁÉÍÓÚ].{2,90})$")
# Assinaturas sem a linha "Vitória/ES, data" antes (Res. 084/2025): nome e, na linha seguinte, o cargo
RE_NOME = re.compile(r"^[A-ZÁÉÍÓÚ][a-záéíóúâêôãõç]+(?:\s+(?:d[aeo]s?\s+)?[A-ZÁÉÍÓÚ][a-záéíóúâêôãõç]+){1,5}$")
RE_CARGO = re.compile(r"^(Diretor|Diretora|Presidente|Governador|Secret[áa]ri[oa])\b")


def _seguem(linhas, k, padrao, valor, n=3):
    """Da linha k até o próximo ANEXO aparecem n números seguidos (1., 2., 3. / I, II, III) no começo da linha."""
    quer = 1
    for l in linhas[k:]:
        t = l["texto"]
        if t.startswith("ANEXO "):
            break
        m = padrao.match(t)
        if m and valor(m.group(1)) == quer:
            quer += 1
            if quer > n:
                return True
    return False


def juntar(a, b):
    """Junta duas linhas de um mesmo parágrafo, desfazendo hifenização."""
    if not a:
        return b
    if a.endswith("-") and b[:1] == "-":          # "matéria-" + "-prima"
        return a + b[1:]
    if a.endswith("-") and b[:1].islower() and not a.endswith(" -"):
        if RE_ENCLITICO.match(b) and not (b.startswith("se") and a[-2:-1] == "s"):
            return a + b                          # "classificando-" + "as", "aplica-" + "se": hífen do pronome
        return a[:-1] + b                         # "re-" + "gulamentação", "clas-" + "se"
    return a + " " + b


RE_ENCLITICO = re.compile(r"(?:se|lo|la|los|las|lhe|lhes|nos|o|a|os|as)\b")


class Construtor:
    def __init__(self, meta):
        self.meta = meta
        self.partes = []
        self.avisos = []
        self.nova_parte("corpo", "Texto da norma")
        self.ultimo = None      # elemento que recebe linhas de continuação

    # ---------- partes e blocos ----------
    def nova_parte(self, pid, rotulo):
        self.parte = {"id": pid, "rotulo": rotulo, "blocos": []}
        self.partes.append(self.parte)
        self.art = None
        self.ult_art = 0
        self.ult_suf = ""
        self.cont = None   # caput ou parágrafo corrente
        self.inc = None
        self.ultimo = None
        self.modo = None    # anexo sem artigos: "itens" (itens numerados) ou "lista" (só incisos)
        self.ult_item = 0
        self.ult_sec = 0

    def prefixo(self):
        return "" if self.parte["id"] == "corpo" else self.parte["id"] + "_"

    def bloco(self, b):
        self.parte["blocos"].append(b)
        return b

    # ---------- elementos ----------
    def add_texto_livre(self, t, pag):
        """Texto fora de artigo (preâmbulo, tabelas de anexo)."""
        blocos = self.parte["blocos"]
        if blocos and blocos[-1]["tipo"] == "texto" and self.ultimo is blocos[-1] and not blocos[-1].get("tabela"):
            b = blocos[-1]
            ant = b["linhas"][-1]
            novo_par = (re.search(r"[.;:]$", ant) and re.match(r"[A-ZÁÉÍÓÚÂÊ\"“(]", t)) or \
                re.match(r"(CONSIDERANDO|Considerando|RESOLVE|O GOVERNADOR|Faço saber|A DIRETORIA)", t)
            # nos anexos cada linha fica (tabelas), menos no fecho (local, data e assinaturas), que junta como no corpo
            if novo_par or (self.parte["id"] != "corpo" and not b.get("fecho")):
                b["linhas"].append(t)
            else:
                b["linhas"][-1] = juntar(ant, t)
        else:
            b = self.bloco({"tipo": "texto", "linhas": [t], "pag": pag})
            self.ultimo = b

    def add_linha_tabela(self, t, pag):
        """Linha de tabela transcrita: fecha o artigo/item aberto e entra num bloco de tabela."""
        self.art = self.cont = self.inc = None
        b = self.parte["blocos"][-1] if self.parte["blocos"] else None
        if b is not None and b.get("tabela") and self.ultimo is b:
            b["linhas"].append(t)
        else:
            self.ultimo = self.bloco({"tipo": "texto", "linhas": [t], "pag": pag, "tabela": True})

    def add_titulo(self, nivel, num, texto, pag):
        b = self.bloco({"tipo": "titulo", "nivel": nivel, "rotulo": f"{nivel} {num}".strip(),
                        "texto": texto, "pag": pag})
        self.ultimo = b
        self.cont = None
        self.inc = None

    def add_artigo(self, num, suf, texto, pag):
        n = f"{num}{('-' + suf) if suf else ''}"
        aid = f"{self.prefixo()}art{num}{suf.lower() if suf else ''}"
        self.art = self.bloco({"tipo": "artigo", "num": n, "rotulo": f"Art. {ordinal(n)}", "id": aid,
                               "pag": pag, "caput": {"id": aid + "_cpt", "texto": texto, "incisos": [], "pag": pag},
                               "paragrafos": []})
        self.ult_art, self.ult_suf = num, suf or ""
        self.cont = self.art["caput"]
        self.inc = None
        self.ultimo = self.cont

    def add_item(self, n, texto, pag):
        """Item numerado de anexo ("23."), no lugar do artigo: anx1_it23 > anx1_it23_cpt > _inc2 > _ali-a.
        Rótulo "item 23" (indice.Mapa), como as seções de nota técnica."""
        iid = f"{self.prefixo()}it{n}"
        self.art = self.bloco({"tipo": "artigo", "num": str(n), "rotulo": f"{n}.", "id": iid, "pag": pag, "secao": True,
                               "caput": {"id": iid + "_cpt", "texto": texto, "incisos": [], "pag": pag},
                               "paragrafos": []})
        self.ult_item = n
        self.cont = self.art["caput"]
        self.inc = None
        self.ultimo = self.cont

    def add_lista(self, pag):
        """Anexo que é só uma lista de incisos (definições): o anexo faz as vezes do artigo
        (anx2 > anx2_cpt > anx2_cpt_inc18). Rótulo "Anexo II, inciso XVIII"."""
        pid = self.parte["id"]
        self.art = self.bloco({"tipo": "artigo", "num": "", "rotulo": "", "id": pid, "pag": pag,
                               "caput": {"id": pid + "_cpt", "texto": "", "incisos": [], "pag": pag},
                               "paragrafos": []})
        self.cont = self.art["caput"]
        self.inc = None
        self.ultimo = self.cont

    def add_paragrafo(self, num, texto, pag):
        unico = num is None
        rot = "Parágrafo único" if unico else f"§ {ordinal(str(num))}"
        pid = f"{self.art['id']}_par{'1u' if unico else num}"
        p = {"id": pid, "rotulo": rot, "num": 0 if unico else num, "texto": texto, "incisos": [], "pag": pag}
        self.art["paragrafos"].append(p)
        self.cont = p
        self.inc = None
        self.ultimo = p

    def add_inciso(self, n, texto, pag, rotulo=None):
        iid = f"{self.cont['id']}_inc{n}"
        i = {"id": iid, "rotulo": rotulo or int_para_romano(n), "num": n, "texto": texto, "alineas": [], "pag": pag}
        self.cont["incisos"].append(i)
        self.inc = i
        self.ultimo = i

    def add_alinea(self, letra, texto, pag):
        alvo = self.inc if self.inc else self.cont
        lid = f"{alvo['id']}_ali-{letra}"
        a = {"id": lid, "rotulo": f"{letra})", "letra": letra, "texto": texto, "pag": pag}
        alvo.setdefault("alineas", []).append(a)
        self.ultimo = a

    def continuar(self, t, pag):
        u = self.ultimo
        if u is None or u.get("tipo") == "texto":
            self.add_texto_livre(t, pag)
        elif u.get("tipo") == "titulo":
            # título em duas linhas: "CAPÍTULO II" + "DOS PRINCÍPIOS"
            if not u["texto"] and len(t) < 120:
                u["texto"] = t
            elif u["texto"] and t.isupper() and len(t) < 80:
                u["texto"] = juntar(u["texto"], t)
            else:
                self.ultimo = None
                self.add_texto_livre(t, pag)
        else:
            u["texto"] = juntar(u["texto"], t)

    # ---------- validações de sequência ----------
    def aceita_artigo(self, num, suf):
        if self.ult_art == 0:
            return num == 1 or num <= 3
        if num == self.ult_art and suf and suf > self.ult_suf:
            return True
        if num == self.ult_art + 1:
            return True
        if self.ult_art < num <= self.ult_art + 4:
            self.avisos.append(f"salto de numeração: art. {self.ult_art} -> art. {num}")
            return True
        return False

    def aceita_paragrafo(self, num):
        if not self.art:
            return False
        ps = self.art["paragrafos"]
        ult = ps[-1]["num"] if ps else 0
        if num is None:
            return not ps
        if num == ult + 1 or (num == 1 and not ps):
            return True
        if ult < num <= ult + 2:
            self.avisos.append(f"{self.art['rotulo']}: salto de parágrafo § {ult} -> § {num}")
            return True
        return False

    def aceita_inciso(self, n, folga=0):
        """folga=1: aceita pular um número (o OCR às vezes perde o marcador), com aviso."""
        if not self.cont:
            return False
        incs = self.cont["incisos"]
        ult = incs[-1]["num"] if incs else 0
        if n == ult + 1 or (n == 1 and ult == 0):
            return True
        if folga and ult and ult + 1 < n <= ult + 1 + folga:
            self.avisos.append(f"{self.art['rotulo']}, {self.cont.get('rotulo') or 'caput'}: "
                               f"salto de inciso {int_para_romano(ult)} -> {int_para_romano(n)}")
            return True
        return False

    def aceita_alinea(self, letra):
        alvo = self.inc if self.inc else self.cont
        if not alvo:
            return False
        als = alvo.get("alineas", [])
        if not als:
            return letra == "a"
        return ord(letra) == ord(als[-1]["letra"]) + 1


def estruturar_norma(meta, linhas):
    """Normas articuladas. Contratos (tipo 'contrato') usam cláusulas também no corpo:
    Cláusula > item numerado (12.12.1) > inciso > alínea."""
    c = Construtor(meta)
    contrato = meta.get("tipo") == "contrato"
    em_clausulas = False
    n_anexo = 0
    for k, l in enumerate(linhas):
        t, pag = l["texto"], l["pag"]

        m = RE_ANEXO.match(t)
        if contrato and m and not re.match(r"^ANEXO\s+[IVX]+\s+[-–—]\s+[A-ZÁÉÍÓÚÂÊÔÃÕÇ]", t):
            m = None    # no contrato, "ANEXO I e no REGULAMENTO" em começo de linha não abre anexo
        if m and (m.group(1) == "ANEXO" or len(t) <= 40) and not re.search(r"\b(desta|deste|da presente)\b", t):
            n_anexo += 1
            num = m.group(2) or ""
            rot = f"Anexo {num}".strip()
            pid = f"anx{romano_para_int(num) or n_anexo}" if num and num.upper() not in ("ÚNICO", "UNICO") else f"anx{n_anexo}"
            if any(p["id"] == pid for p in c.partes):
                pid = f"{pid}b"
            c.nova_parte(pid, rot + (f" – {m.group(3)}" if m.group(3) else ""))
            c.parte["titulo_pendente"] = not m.group(3)
            em_clausulas = False
            continue
        if c.parte.get("titulo_pendente") and not RE_ART.match(t) and not RE_TITULO.match(t) \
                and not RE_CLAUSULA.match(t) and len(t) < 140:
            c.parte["rotulo"] += " – " + t
            c.parte["titulo_pendente"] = False
            continue
        c.parte["titulo_pendente"] = False
        if contrato and c.parte["id"] != "corpo" and not c.parte["blocos"] and len(t.split()) <= 4 \
                and t.upper() == t and not RE_CLAUSULA.match(t):
            # fim do título do anexo na linha seguinte ("... DE GÁS" + "CANALIZADO")
            c.parte["rotulo"] += " " + t
            continue

        if c.parte["id"] != "corpo" and RE_TABELA.search(t):
            c.add_linha_tabela(t, pag)
            continue

        if not contrato and c.parte["id"] != "corpo" and not em_clausulas:
            # anexo que começa por itens numerados (1., 2. e 3. a seguir) ou por uma lista de incisos;
            # uma lista depois de uma tabela (LC 827, Anexo II) segue como texto
            vazio = not c.parte["blocos"]
            # itens: pode haver antes um subtítulo curto e tabelas transcritas ("VÁLIDA A PARTIR DE 16/03/2026")
            inicio = all(b["tipo"] == "texto" for b in c.parte["blocos"]) and \
                sum(len(b["linhas"]) for b in c.parte["blocos"] if not b.get("tabela")) <= 2
            if c.modo == "itens" or (c.modo is None and inicio):
                m = RE_SECAO_ANX.match(t)
                if m and t.upper() == t and romano_para_int(m.group(1)) == c.ult_sec + 1 \
                        and (c.modo == "itens" or _seguem(linhas, k + 1, RE_ITEM_ANX, int)):
                    c.modo = "itens"
                    c.ult_sec += 1
                    c.add_titulo("Seção", m.group(1), m.group(2), pag)
                    continue
                m = RE_SUBSECAO_ANX.match(t) if c.modo == "itens" else None
                if m and romano_para_int(m.group(1)) == c.ult_sec:
                    c.add_titulo("Subseção", f"{m.group(1)}.{m.group(2)}", m.group(3), pag)
                    continue
                m = RE_ITEM_ANX.match(t)
                if m and ((c.modo == "itens" and int(m.group(1)) == c.ult_item + 1)
                          or (c.modo is None and m.group(1) == "1" and _seguem(linhas, k, RE_ITEM_ANX, int))):
                    c.modo = "itens"
                    c.add_item(int(m.group(1)), m.group(2), pag)
                    continue
            # anexo que é só uma lista de incisos (definições); o inciso I entra logo abaixo
            if c.modo is None and vazio:
                m = RE_INC.match(t)
                if m and m.group(1) == "I" and _seguem(linhas, k, RE_INC, romano_para_int):
                    c.modo = "lista"
                    c.add_lista(pag)

        m = RE_CLAUSULA.match(t)
        n = romano_para_int(m.group(1)) if m else None
        ult_cl = int(c.art["num"]) if (em_clausulas and c.art) else 0
        if contrato:
            # sem sumário a descartar; o OCR pode perder um título de cláusula (aceita pular um, com aviso)
            ok = m and n and ult_cl < n <= ult_cl + 2
            if ok and n != ult_cl + 1:
                c.avisos.append(f"{c.parte['rotulo']}: salto de cláusula {ult_cl} -> {n}")
        else:
            ok = m and c.parte["id"] != "corpo" and n and (n == ult_cl + 1 or n == 1)
        if ok:
            if n == 1 and ult_cl and not contrato:
                # a sequência anterior era o índice (sumário) do contrato: descarta
                sobra = [b["caput"]["texto"] for b in c.parte["blocos"] if b["tipo"] == "artigo" and b["caput"]["texto"]]
                c.parte["blocos"] = [b for b in c.parte["blocos"] if b["tipo"] != "artigo"]
                if sobra:
                    c.bloco({"tipo": "texto", "linhas": sobra, "pag": pag})
            em_clausulas = True
            cid = f"{c.prefixo()}cl{n}"
            c.art = c.bloco({"tipo": "artigo", "num": str(n), "rotulo": f"Cláusula {m.group(1)}", "id": cid,
                             "pag": pag, "titulo": m.group(2) or "",
                             "caput": {"id": cid + "_cpt", "texto": "", "incisos": [], "pag": pag},
                             "paragrafos": []})
            c.cont = c.art["caput"]
            c.inc = None
            c.ultimo = None if not m.group(2) else c.cont
            c.art["_titulo_aberto"] = not m.group(2)
            continue
        if em_clausulas and c.art:
            if c.art.get("_titulo_aberto"):
                c.art["titulo"] = t
                c.art["_titulo_aberto"] = False
                c.ultimo = c.cont
                continue
            if not c.art["paragrafos"] and not c.art["caput"]["texto"] and t.isupper() and len(t) < 90:
                c.art["titulo"] = juntar(c.art.get("titulo", ""), t)
                continue
            if contrato and (RE_FECHO.match(t) or re.match(r"^E,? por estarem", t)):
                # "E por estarem assim justas e contratadas..." / "Vitória, 22 de julho de 2020."
                em_clausulas = False
                c.art = c.cont = c.inc = None
                c.ultimo = c.bloco({"tipo": "texto", "linhas": [t], "pag": pag, "fecho": True})
                continue
            m = RE_ITEM.match(t)
            if m and contrato and m.group(1).split(".")[0] != c.art["num"]:
                m = None    # item de outra cláusula: número mal lido ou texto que começa com número
            if m and c.art["paragrafos"]:
                ant = tuple(int(x) for x in c.art["paragrafos"][-1]["num"].split("."))
                if tuple(int(x) for x in m.group(1).split(".")) < ant:
                    m = None    # número para trás: é quebra de linha ("nos itens 4.3 e" + "4.8 sejam ..."), não item
            if m:
                num = m.group(1)
                pid = f"{c.art['id']}_it{num.replace('.', '-')}"
                if any(x["id"] == pid for x in c.art["paragrafos"]):
                    # número repetido no próprio contrato (dois itens 6.5): o segundo ganha sufixo no endereço
                    c.avisos.append(f"{c.parte['rotulo'] if c.parte['id'] != 'corpo' else 'Corpo'}, "
                                    f"{c.art['rotulo']}: item {num} repetido no original; o segundo fica com o endereço {pid}b")
                    pid += "b"
                p = {"id": pid, "rotulo": num, "num": num,
                     "texto": m.group(2), "incisos": [], "pag": pag, "nivel": num.count(".")}
                c.art["paragrafos"].append(p)
                c.cont = p
                c.inc = None
                c.ultimo = p
                continue
            if contrato:
                m = RE_INC.match(t)
                if m:
                    n = romano_para_int(m.group(1))
                    if n and c.aceita_inciso(n, folga=1):
                        c.add_inciso(n, m.group(2), pag)
                        continue
                    ult = c.cont["incisos"][-1]["num"] if c.cont and c.cont["incisos"] else 0
                    if n and 1 < n <= ult:
                        # erro de numeração do próprio contrato ("XL" depois do "XLIX"): o texto não muda;
                        # o inciso entra como o próximo da sequência, com o número impresso
                        c.avisos.append(f"{c.art['rotulo']}, {c.cont.get('rotulo') or 'caput'}: inciso "
                                        f"{m.group(1)} impresso depois do {int_para_romano(ult)}; tratado como o {ult + 1}º")
                        c.add_inciso(ult + 1, m.group(2), pag, rotulo=m.group(1))
                        continue
                m = RE_ALI.match(t)
                if m and c.aceita_alinea(m.group(1)):
                    c.add_alinea(m.group(1), m.group(2), pag)
                    continue
            c.continuar(t, pag)
            continue

        if c.art is not None and c.parte["id"] == "corpo" and RE_NOME.match(t) and k + 1 < len(linhas) \
                and RE_CARGO.match(linhas[k + 1]["texto"]):
            # assinaturas sem local e data antes ("Alexandre Careta Ventorim" + "Diretor-Geral"): encerra o artigo
            c.art = None
            c.cont = c.inc = None
            c.ultimo = c.bloco({"tipo": "texto", "linhas": [t], "pag": pag, "fecho": True})
            continue

        if RE_FECHO.match(t) and c.art is not None:
            # local e data / assinaturas: encerra o último artigo
            c.art = None
            c.cont = c.inc = None
            c.ultimo = c.bloco({"tipo": "texto", "linhas": [t], "pag": pag, "fecho": True})
            continue

        m = RE_TITULO.match(t)
        # "Seção IV deste regulamento e na forma a seguir:" é fim de frase quebrada, não título
        if m and (m.group(1).isupper() or len(t) < 60) and not re.match(r"[a-zà-ú]", m.group(3)):
            nivel = m.group(1).capitalize().replace("Capitulo", "Capítulo").replace("Titulo", "Título")
            c.add_titulo(nivel, m.group(2), m.group(3), pag)
            continue

        m = RE_ART.match(t)
        if m and t.startswith("Art"):
            num, suf, resto = int(m.group(1)), m.group(2) or "", m.group(3)
            # numeração recomeça sem marcador de anexo -> nova parte
            if num == 1 and c.ult_art >= 1 and not suf:
                n_anexo += 1
                c.nova_parte(f"anx{n_anexo}", f"Anexo {int_para_romano(n_anexo)}")
            if c.aceita_artigo(num, suf):
                c.add_artigo(num, suf, resto, pag)
                continue

        m = RE_PAR.match(t)
        if m and c.art:
            num = int(m.group(1)) if m.group(1) else None
            if c.aceita_paragrafo(num):
                c.add_paragrafo(num, m.group(2), pag)
                continue

        m = RE_INC.match(t)
        if m and c.art:
            n = romano_para_int(m.group(1))
            if n and c.aceita_inciso(n):
                c.add_inciso(n, m.group(2), pag)
                continue

        m = RE_ALI.match(t)
        if m and c.art and c.aceita_alinea(m.group(1)):
            c.add_alinea(m.group(1), m.group(2), pag)
            continue

        if c.art is None:
            c.add_texto_livre(t, pag)
        else:
            c.continuar(t, pag)

    # partes vazias saem
    partes = [p for p in c.partes if p["blocos"]]
    for p in partes:
        p.pop("titulo_pendente", None)
        for b in p["blocos"]:
            b.pop("_titulo_aberto", None)
            if p["id"] != "corpo" and b["tipo"] == "texto" and not b.get("fecho") and not b.get("tabela") \
                    and eh_prosa(b["linhas"]):
                b["linhas"] = em_paragrafos(b["linhas"])
                b["prosa"] = True
    return partes, c.avisos


RE_MARCA_PROSA = re.compile(r"^(?:[a-z]\)|\d{1,2}[.)]\s|[IVXLC]{1,7}\s*[-–.)]\s|[•▪◦-]\s|\(?[ivx]{1,4}\)\s)")


def eh_prosa(linhas):
    """Texto de anexo que é texto corrido (a maioria das linhas cheias), e não tabela (Res. 080/2024, Anexo V)."""
    # tabelas dos anexos: média de até 48 caracteres e até 11% de linhas cheias; texto corrido: média de 50 ou mais
    if len(linhas) < 4:
        return False
    cheias = sum(1 for t in linhas if len(t) >= 70) / len(linhas)
    return cheias >= 0.3 and sum(map(len, linhas)) / len(linhas) >= 50


def em_paragrafos(linhas):
    """Junta as linhas quebradas pelo PDF. Uma linha começa parágrafo novo se tem marcador (a), 1., •),
    se é um título em maiúsculas ou se a anterior é curta ou termina a frase; minúscula no começo continua."""
    out, ant = [], None          # ant: a linha anterior do PDF (não o parágrafo já juntado)
    for t in linhas:
        if out:
            titulo = t.upper() == t and len(t) < 80
            continua = not RE_MARCA_PROSA.match(t) and not titulo and (
                t[:1].islower() or (len(ant) >= 70 and not re.search(r"[.:;]$", ant)))
            if continua and not (ant.upper() == ant and len(ant) < 80):
                out[-1] = juntar(out[-1], t)
                ant = t
                continue
        out.append(t)
        ant = t
    return out


def estruturar_nota(meta, linhas):
    """Nota técnica: seções numeradas com parágrafos corridos."""
    blocos, atual, avisos = [], None, []
    intro = {"tipo": "texto", "linhas": [], "pag": 1}
    blocos.append(intro)
    for l in linhas:
        t, pag = l["texto"], l["pag"]
        m = RE_SECAO_NT.match(t)
        if m:
            num = m.group(1)
            sid = "sec" + num.replace(".", "-")
            atual = {"tipo": "artigo", "num": num, "rotulo": f"{num}.", "titulo": m.group(2).strip(),
                     "id": sid, "pag": pag, "caput": {"id": sid + "_cpt", "texto": "", "incisos": [], "pag": pag},
                     "paragrafos": [], "secao": True}
            blocos.append(atual)
            continue
        alvo = atual["caput"] if atual else None
        if alvo is None:
            intro["linhas"].append(t)
            continue
        # novo parágrafo quando a linha anterior fecha frase e esta começa com maiúscula
        pars = atual["paragrafos"]
        if not alvo["texto"]:
            alvo["texto"] = t
        elif pars and not (re.search(r"[.;:]$", pars[-1]["texto"]) and re.match(r"[A-ZÁÉÍÓÚ\"“•\-]", t)):
            pars[-1]["texto"] = juntar(pars[-1]["texto"], t)
        elif not pars and not (re.search(r"[.;:]$", alvo["texto"]) and re.match(r"[A-ZÁÉÍÓÚ\"“•\-]", t)):
            alvo["texto"] = juntar(alvo["texto"], t)
        else:
            k = len(pars) + 1
            pars.append({"id": f"{atual['id']}_p{k}", "rotulo": "", "num": k, "texto": t, "incisos": [], "pag": pag})
    # junta linhas soltas da introdução
    txt = []
    for t in intro["linhas"]:
        if txt and not (re.search(r"[.;:]$", txt[-1]) and re.match(r"[A-ZÁÉÍÓÚ]", t)):
            txt[-1] = juntar(txt[-1], t)
        else:
            txt.append(t)
    intro["linhas"] = txt
    return [{"id": "corpo", "rotulo": "Nota técnica", "blocos": blocos}], avisos


def contar(partes):
    """artigos (cláusulas e itens de anexo incluídos), parágrafos/itens de cláusula, incisos, alíneas."""
    a = p = i = al = 0
    for pt in partes:
        for b in pt["blocos"]:
            if b["tipo"] != "artigo":
                continue
            a += 1
            for cont in [b["caput"]] + b["paragrafos"]:
                p += cont is not b["caput"]
                for inc in cont["incisos"]:
                    i += 1
                    al += len(inc.get("alineas", []))
                al += len(cont.get("alineas", []))
    return a, p, i, al


def executar(docs, pasta_dados):
    for d in docs:
        linhas = json.loads((pasta_dados / f"{d['id']}.linhas.json").read_text(encoding="utf-8"))
        if d["tipo"] == "nota-tecnica":
            partes, avisos = estruturar_nota(d, linhas)
        else:
            partes, avisos = estruturar_norma(d, linhas)
        saida = {k: d[k] for k in d}
        saida["partes"] = partes
        saida["avisos"] = avisos
        (pasta_dados / f"{d['id']}.estrutura.json").write_text(json.dumps(saida, ensure_ascii=False, indent=1),
                                                                encoding="utf-8")
        a, p, i, al = contar(partes)
        print(f"  {d['id']:22s} partes={len(partes)} artigos={a:3d} §={p:3d} incisos={i:3d} alíneas={al:3d}"
              f" avisos={len(avisos)}")
