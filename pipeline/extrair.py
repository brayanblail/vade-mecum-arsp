"""Etapa 1 - Extrai as linhas de texto de cada PDF, com o número da página.

- Remove cabeçalhos e rodapés repetidos (E-DOCS, endereço da ARSP, "PÁGINA x / y" etc.).
- Remove texto tachado (redações anteriores nos textos consolidados da Assembleia).
- Para PDFs com camada de texto corrompida (coluna ocr=sim), usa o texto de OCR
  salvo em ocr/<prefixo>-NN.txt (gerado com Tesseract, idioma por).
- Para PDFs escaneados que já trazem uma camada de OCR boa (o contrato de concessão),
  AJUSTES[...]["camada_ocr"] agrupa as linhas da página inteira e corrige os erros típicos;
  fórmulas e tabelas escaneadas viram um aviso com a página do PDF.
- Fórmulas e tabelas que viram texto quebrado em PDFs com texto (Res. 084/2025) também
  viram aviso (AJUSTES[...]["ver_pdf"]); as letras matemáticas do Word viram letras comuns.
- Para na página de assinaturas do E-DOCS.

Saída: dados/<id>.linhas.json  ->  [{"pag": 1, "texto": "..."}, ...]
"""
import json
import re
import unicodedata
from pathlib import Path

import pymupdf

RAIZ = Path(__file__).resolve().parent.parent

# Linhas de ruído (cabeçalho/rodapé), testadas depois de normalizar espaços.
RUIDO = [
    r"^P[ÁA]GINA \d+ ?/ ?\d+$",
    r"^\d{2}/\d{2}/\d{4},? \d{2}:\d{2}$",
    r"E-DOCS - (DOCUMENTO ORIGINAL|C[ÓO]PIA SIMPLES)",
    r"^arsp\.es(\.gov\.br)?$",
    r"^gabinete@arsp\.es\.gov\.br$",
    r"^\+55 27",
    r"^Av\. (Cezar Hilal|Nossa S)",
    r"^Tel\.: ",
    r"^Tel: \d{4}-\d{4}",                 # "Tel: 3636-8500" (cabeçalho das resoluções de 2021 e 2025)
    r"^P[áa]gina \d+ de \d+$",
    r"^P[áa]g\. \d+ de \d+$",
    r"^\d+ of \d+$",
    r"^https://www3?\.al\.es\.gov\.br",
    r"^Firefox\b",
    r"^Este texto não substitui o publicado",
    r"^arsp\.es\.gov\.br \+55",
]
RUIDO_RE = [re.compile(p) for p in RUIDO]

# Onde o texto útil termina (página de assinaturas do E-DOCS etc.).
FIM_GERAL = re.compile(r"^(Documento original assinado eletronicamente|INFORMAÇÕES DO DOCUMENTO)")

# Ajustes por documento: início e fim do trecho útil (ex.: página do Diário Oficial
# que traz outros atos além da lei).
#   inicio / fim   regex da primeira linha útil / da linha onde o texto termina
#   pular          regex de linhas descartadas
#   camada_ocr     PDF escaneado com camada de OCR: agrupa as linhas da página inteira pela altura
#                  (o OCR quebra linhas justificadas em blocos soltos), descarta o que estiver além de
#                  `margem_dir` (fração da largura: carimbos e rubricas) e corrige erros típicos (corrigir_camada)
#   omitir         [(de, ate)]: mantém a linha `de` e descarta as seguintes até antes de `ate`
#   tabelas        [(de, ate)]: troca as linhas de `de` até antes de `ate` por um aviso com a página do PDF
#                  (tabelas escaneadas saem com números trocados de coluna ou faltando)
#   formulas       troca as linhas entre a frase que apresenta a fórmula e o "onde:" por um aviso
#   corrigir       [(regex, troca)]: correções pontuais conferidas no PDF (o OCR perdeu o marcador)
#   ver_pdf        [(de, ate, tipo)]: mantém a linha `de` e troca as seguintes, até antes de `ate`, por
#                  "[<tipo>: ver o PDF, p. N.]" (fórmulas e tabelas que viram texto quebrado)
#   transcrever    [{"tirar": (de, ate|None), "depois_de": regex, "linhas": [...]}]: tira as linhas de `de`
#                  até antes de `ate` (None: até o fim) e põe a transcrição depois da linha `depois_de`.
#                  Tabela conferida no PDF, colunas separadas por " | " (o site mostra como tabela)
AJUSTES = {
    "lei-11173-2020": {"inicio": r"^LEI N[º°] 11\.173", "fim": r"^(RENATO CASAGRANDE|JOSÉ RENATO CASAGRANDE)"},
    "res-arsp-053-2021": {"pular": r"\.{6,}\s*\d+\s*$"},  # linhas do índice com pontilhado
    "contrato-concessao-2020": {
        "camada_ocr": True,
        "margem_dir": 0.95,
        "fim": r"^CAPTURADO POR$",                     # página de captura do E-DOCS
        "omitir": [(r"^Vitória, 22 de julho de 2020", r"^ANEXO I - ")],   # assinaturas e cartório
        "tabelas": [(r"^Denominação Valor Novo", r"^\* A descrição dos ativos"),          # Anexo III
                    (r"^Segmento Residencial - Medição Individual", r"^\* Os valores serão")],  # Anexo IV
        "formulas": True,
        "corrigir": [(r"^taxa de regulação e fiscalização dos SERVI", r"II - \g<0>"),      # Anexo I, 2.1, p. 34
                     (r"^arcar integralmente com o custo da construção", r"III - \g<0>"),  # 5.2.1, p. 8
                     (r"^IV arcar parcialmente o custo da construção$", "IV - arcar parcialmente com o custo da construção"),
                     (r"^- com de gasodutos e instalações pela$", "de gasodutos e instalações pela"),
                     (r"^proporcionar o auxílio que seja solicitado", r"II - \g<0>"),     # 8.11, p. 11
                     (r"^executar, direta ou indiretamente, os serviços", r"III - \g<0>"),  # 16.2, p. 21
                     (r"^VIII estimular o aumento", "VIII - estimular o aumento"),        # 15.1, p. 21
                     (r"sóC10\(S\)", "SÓCIO(S)"),                                         # título da Cláusula XXIX
                     (r"art\. 207, SIO da", "art. 207, §1º da"),                          # 4.2, p. 6
                     (r"do art\. 60 da Lei Federal", "do art. 6º da Lei Federal"),        # 8.2.1, p. 9
                     (r"do art\. 70 da Lei Estadual", "do art. 7º da Lei Estadual"),
                     (r"\bCO CESSIONÁRIA", "CONCESSIONÁRIA")],                            # 1.1, XVIII, p. 2
    },
    "res-arsp-084-2025": {
        # equações do Anexo I (a 1 é imagem; as outras saem com índices e frações desmontados) e tabelas
        "ver_pdf": [(r"^Equação 1: ", r"^onde:$", "Fórmula"),                       # item 8, p. 3
                    (r"fórmula apresentada a seguir:$", r"^onde:$", "Fórmula"),     # item 44 (WACC), p. 6
                    (r"^Equação 2: ", r"^Onde:$", "Fórmula"),                       # item 52, p. 7
                    (r"^Equação 3: ", r"^Onde:$", "Fórmula"),
                    (r"^Equação 4: ", r"^Onde:$", "Fórmula"),                       # item 53
                    (r"^Equação 5: ", r"^Onde$", "Fórmula"),                        # item 80, p. 9
                    (r"^Equação 6: ", r"^Onde:$", "Fórmula"),                       # item 97, p. 11
                    (r"^Equação 7: ", r"^98\. ", "Fórmula"),
                    (r"^Tabela 1: ", r"^99\. ", "Tabela"),                          # item 98
                    (r"^Equação 8: ", r"^100\. ", "Fórmula"),                       # item 99
                    (r"^ANEXO III ", r"^Nota: A aplicabilidade", "Tabela")],        # Anexo III, p. 16
    },
    "res-arsp-101-2026": {
        # tabela do Anexo I (p. 2): sai no fim e desmontada; fica logo abaixo do título, como no PDF.
        # A PUC (0,05) é uma célula só para as quatro classes.
        "transcrever": [{"tirar": (r"^Classe$", None), "depois_de": r"^VÁLIDA A PARTIR DE 16/03/2026$",
                         "linhas": ["Classe | CDC mínimo (m³/dia) | CDC máximo (m³/dia) | "
                                    "Parcela de Reserva de Capacidade – PRC (R$/m³) | Parcela de Uso de Capacidade – PUC (R$/m³)",
                                    "1 | - | 1.000.000 | 0,0200 | 0,05",
                                    "2 | 1.000.001 | 2.000.000 | 0,0100 | 0,05",
                                    "3 | 2.000.001 | 4.000.000 | 0,0085 | 0,05",
                                    "4 | 4.000.001 | ∞ | 0,0050 | 0,05"]}],
    },
}


def _riscado(span_bbox, linhas_h):
    """True se uma linha horizontal cruza o meio do trecho (tachado)."""
    x0, y0, x1, y1 = span_bbox
    h = y1 - y0
    if h <= 0:
        return False
    for (ly, lx0, lx1) in linhas_h:
        if y0 + 0.30 * h <= ly <= y0 + 0.72 * h:
            sobre = min(x1, lx1) - max(x0, lx0)
            if sobre > 0.6 * (x1 - x0):
                return True
    return False


def _linhas_horizontais(pagina):
    hs = []
    for d in pagina.get_drawings():
        for it in d["items"]:
            if it[0] == "l":
                a, b = it[1], it[2]
                if abs(a.y - b.y) < 0.6 and abs(b.x - a.x) > 4:
                    hs.append((a.y, min(a.x, b.x), max(a.x, b.x)))
            elif it[0] == "re":
                r = it[1]
                if r.height < 1.6 and r.width > 4:
                    hs.append(((r.y0 + r.y1) / 2, r.x0, r.x1))
    return hs


def _eh_ruido(t):
    return any(p.search(t) for p in RUIDO_RE)


# Letras matemáticas do Word (U+1D400 a U+1D7FF: "𝑊𝐴𝐶𝐶", "𝛽𝑒") viram letras comuns ("WACC", "βe"),
# para a busca achar o texto. Só esse bloco: o NFKC no texto todo trocaria "º" por "o".
MATEMATICAS = {cp: unicodedata.normalize("NFKC", chr(cp)) for cp in range(0x1D400, 0x1D800)
               if unicodedata.normalize("NFKC", chr(cp)) != chr(cp)}


RE_MARCADOR = re.compile(r"^(Art\.?\s*\d+\s*[º°]?(?:-[A-Z])?|§\s*\d+\s*[º°]?|Par[áa]grafo [úu]nico|[IVXLC]{1,6}\s*[-–—]|[a-z]\))")
RE_REVOGADO = re.compile(r"^\((Dispositivo|Artigo|Inciso|Parágrafo|Alínea)?\s*revogad", re.I)


def _linhas_visuais(bloco):
    """Agrupa as 'linhas' do PyMuPDF que estão na mesma altura (texto justificado
    em colunas do Diário Oficial sai palavra por palavra)."""
    grupos = []
    for linha in bloco.get("lines", []):
        y0, y1 = linha["bbox"][1], linha["bbox"][3]
        if grupos and abs(grupos[-1]["y0"] - y0) < 2.5 and abs(grupos[-1]["y1"] - y1) < 2.5:
            grupos[-1]["spans"] += linha["spans"]
        else:
            grupos.append({"y0": y0, "y1": y1, "spans": list(linha["spans"])})
    for g in grupos:
        g["spans"].sort(key=lambda s: s["bbox"][0])
    return grupos


def _linhas_pagina(pagina, margem_dir):
    """Como _linhas_visuais, mas para a página inteira: junta as linhas de todos os blocos que estão
    na mesma altura. Serve para PDFs escaneados, em que o OCR separa palavras de uma linha
    justificada (e o "I" de "I - ...") em blocos diferentes."""
    largura = pagina.rect.width
    ls = [l for b in pagina.get_text("dict")["blocks"] for l in b.get("lines", [])
          if l["bbox"][0] <= margem_dir * largura]
    ls.sort(key=lambda l: (l["bbox"][1] + l["bbox"][3]) / 2)
    grupos = []
    for l in ls:
        y0, y1 = l["bbox"][1], l["bbox"][3]
        ym = (y0 + y1) / 2
        if grupos and abs(grupos[-1]["ym"] - ym) < 0.45 * min(y1 - y0, grupos[-1]["h"]):
            grupos[-1]["spans"] += l["spans"]
        else:
            grupos.append({"ym": ym, "h": y1 - y0, "y0": y0, "y1": y1, "spans": list(l["spans"])})
    for g in grupos:
        g["spans"].sort(key=lambda s: s["bbox"][0])
    return grupos


def extrair_pdf(caminho, doc_id):
    aj = AJUSTES.get(doc_id, {})
    doc = pymupdf.open(caminho)
    brutas, tachados = [], 0
    for n, pag in enumerate(doc, start=1):
        hs = _linhas_horizontais(pag)
        altura = pag.rect.height
        if aj.get("camada_ocr"):
            visuais = _linhas_pagina(pag, aj.get("margem_dir", 1.0))
        else:
            visuais = [g for bloco in pag.get_text("dict")["blocks"] for g in _linhas_visuais(bloco)]
        for g in visuais:
            vivos, mortos = [], []
            ant_x1 = None
            for s in g["spans"]:
                sep = " " if ant_x1 is not None and s["bbox"][0] - ant_x1 > 1.0 else ""
                ant_x1 = s["bbox"][2]
                if hs and _riscado(s["bbox"], hs):
                    tachados += 1
                    mortos.append(sep + s["text"])
                else:
                    vivos.append(sep + s["text"])
            t = re.sub(r"\s+", " ", "".join(vivos).translate(MATEMATICAS)).strip()
            tm = re.sub(r"\s+", " ", "".join(mortos)).strip()
            if not t and not tm:
                continue
            y = g["y0"]
            if t and re.fullmatch(r"\d{1,3}", t) and (y < altura * 0.08 or y > altura * 0.90):
                continue
            if t and _eh_ruido(t):
                continue
            if t and aj.get("camada_ocr"):
                t = corrigir_camada(t)
                if not t and not tm:
                    continue
            brutas.append({"pag": n, "texto": t, "tachado": tm})
    # Dispositivo inteiro tachado seguido de "(Dispositivo revogado ...)":
    # mantém o número com a marca (Revogado) para não quebrar a sequência.
    saida, run = [], []
    for b in brutas:
        if not b["texto"]:
            run.append(b)
            continue
        if run and RE_REVOGADO.match(b["texto"]):
            m = RE_MARCADOR.match(run[0]["tachado"])
            if m:
                saida.append({"pag": run[0]["pag"], "texto": f"{m.group(1)} (Revogado) {b['texto']}"})
                run = []
                continue
        run = []
        saida.append({"pag": b["pag"], "texto": b["texto"]})
    return saida, tachados


def extrair_ocr(prefixo):
    saida = []
    for f in sorted((RAIZ / "ocr").glob(f"{prefixo}-*.txt")):
        n = int(re.search(r"-(\d+)\.txt$", f.name).group(1))
        for t in f.read_text(encoding="utf-8").splitlines():
            t = re.sub(r"\s+", " ", t).strip()
            if t and not _eh_ruido(t):
                saida.append({"pag": n, "texto": corrigir_ocr(t)})
    return saida


def corrigir_ocr(t):
    """Erros típicos do Tesseract em textos normativos."""
    t = re.sub(r"^8\s?(\d{1,2}\s?[º°o])", r"§ \1", t)          # "8 1º" -> "§ 1º"
    t = re.sub(r"^\$\s?(\d)", r"§ \1", t)
    t = re.sub(r"(?<!\w)8\s?(\d{1,2}\s?[º°])", r"§ \1", t)       # "do 8 2º" no meio da frase
    t = re.sub(r"\b(Ill|IIl|lll|lIl)\b", "III", t)
    t = re.sub(r"\b(Il|lI)\b", "II", t)
    t = re.sub(r"\b(Seç[ãa]o|Cap[íi]tulo|CAP[ÍI]TULO)\s+\|", r"\1 I", t)
    t = re.sub(r"\b(Seç[ãa]o|Cap[íi]tulo|CAP[ÍI]TULO)\s+Il\b", r"\1 II", t)
    t = re.sub(r"\b(Seç[ãa]o|Cap[íi]tulo|CAP[ÍI]TULO)\s+IlI\b", r"\1 III", t)
    # algarismos romanos no início de inciso: "|-", "H —", "HI —", "Il -"
    m = re.match(r"^(\||l|Il|IlI|H|HI|1|ll|lll|lI|V\||\|V|X\||I\|)\s*([\-–—.])\s*", t)
    if m:
        mapa = {"|": "I", "l": "I", "1": "I", "Il": "II", "ll": "II", "lI": "II", "H": "II",
                "IlI": "III", "lll": "III", "HI": "III", "V|": "VI", "|V": "IV", "X|": "XI", "I|": "II"}
        t = mapa[m.group(1)] + " " + m.group(2) + " " + t[m.end():]
    return t


def _romano_ocr(s):
    """Algarismo romano lido pelo OCR: 'xxvii' -> 'XXVII', 'l' -> 'I', 'Il' -> 'II'.
    Devolve None se não parece romano."""
    if s == "l":
        return "I"
    if any(c.isupper() for c in s):
        s = s.replace("l", "I")
    elif "l" not in s:
        s = s.upper()
    return s if re.fullmatch(r"[IVXLC]+", s) else None


def corrigir_camada(t):
    """Erros típicos da camada de OCR de contratos escaneados (E-DOCS)."""
    if re.fullmatch(r"[-–—•.]+", t):
        return ""                         # travessão de inciso que o OCR pôs numa linha própria
    if t == "l.":
        return "I."                       # fim de "... ANEXO" + "I." na linha seguinte
    t = re.sub(r"\bCLA[ÚU]SULA", "CLÁUSULA", t)                                   # "CLAÚSULA XVIII"
    # romanos em minúscula ou com l no lugar de I: no início de inciso e depois de CLÁUSULA/ANEXO
    m = re.match(r"^([IVXLCivxlc]{1,7})(\s*[-–—]\s)", t)
    if m and _romano_ocr(m.group(1)):
        t = _romano_ocr(m.group(1)) + m.group(2) + t[m.end():]
    t = re.sub(r"\b(CL[ÁA]USULAS?|[Cc]l[áa]usulas?|ANEXO|[Aa]nexo)\s+([IVXLCivxlc]{1,7})\b",
               lambda m: f"{m.group(1)} {_romano_ocr(m.group(2)) or m.group(2)}", t)
    t = re.sub(r"(?<![\d.,])1 1\.(?=\d)", "11.", t)                                    # "1 1.2." -> "11.2."
    # "0" no lugar de "o"
    t = re.sub(r"^(\d{1,2}(?:\.\d{1,2}){1,3}\.?) 0 (?=[A-ZÀ-Ú])", r"\1 O ", t)      # "12.10 0 REGULADOR"
    t = re.sub(r"^0 (?=[A-ZÀ-Ú]{2})", "O ", t)
    t = re.sub(r"(?<=[A-Za-zÀ-ú,;] )0(?= [A-Za-zÀ-ú])", "o", t)                       # "observado 0 disposto"
    t = re.sub(r"(?<!\w)S (\d)0(?=,| do art)", r"§ \1º", t)                             # "S 20 do art. 25", "arts. 25, S 20,"
    t = re.sub(r"(?<=[A-ZÁÉÍÓÚÂÊÔÃÕÇ])l(?=[A-ZÁÉÍÓÚÂÊÔÃÕÇ])", "I", t)                  # "ESPíRlTO"
    t = re.sub(r"(?<=[A-ZÁÉÓÚÂÊÔÃÕÇ])í(?=[A-ZÁÉÍÓÚÂÊÔÃÕÇ])", "Í", t)
    t = re.sub(r"\belou\b", "e/ou", t)
    t = re.sub(r"\bno (?=\d)", "nº ", t)                                               # "Lei Estadual no 10.955/2018"
    t = re.sub(r"(?<=[\s/(])m3\b", "m³", t)
    return t


def _formulas(linhas):
    """Fórmulas escaneadas viram texto ilegível: troca as linhas entre a frase que apresenta a
    fórmula ("...seguinte fórmula:", "...fórmula abaixo.", "...a seguir:") e o "onde:" por um aviso."""
    out, i = [], 0
    abre = re.compile(r"(f[óo]rmula|abaixo|a seguir)\s*[:.]?\s*$", re.I)
    estrutura = re.compile(r"^(\d{1,2}\.\d|CL[ÁA]USULA|ANEXO|[IVXLC]+ [-–—] |[a-z]\) )")
    while i < len(linhas):
        out.append(linhas[i])
        if abre.search(linhas[i]["texto"]):
            j = i + 1
            while j < len(linhas) and j - i <= 8 and not re.match(r"^onde\s*:", linhas[j]["texto"]):
                if estrutura.match(linhas[j]["texto"]) or len(linhas[j]["texto"]) > 80:
                    j = len(linhas)     # texto normal antes do "onde:": não é fórmula
                    break
                j += 1
            if j < len(linhas) and j - i <= 8 and j > i + 1:
                out.append({"pag": linhas[i + 1]["pag"], "texto": f"[Fórmula: ver o PDF, p. {linhas[i + 1]['pag']}.]"})
                i = j
                continue
        i += 1
    return out


def recortar(linhas, doc_id):
    aj = AJUSTES.get(doc_id, {})
    if "inicio" in aj:
        r = re.compile(aj["inicio"])
        for i, l in enumerate(linhas):
            if r.search(l["texto"]):
                linhas = linhas[i:]
                break
    fim = re.compile(aj["fim"]) if "fim" in aj else None
    pular = re.compile(aj["pular"]) if "pular" in aj else None
    corrigir = [(re.compile(a), b) for a, b in aj.get("corrigir", [])]
    out = []
    for l in linhas:
        if FIM_GERAL.search(l["texto"]) or (fim and fim.search(l["texto"])):
            break
        if pular and pular.search(l["texto"]):
            continue
        for r, troca in corrigir:
            l = dict(l, texto=r.sub(troca, l["texto"]))
        out.append(l)
    for de, ate in aj.get("omitir", []):
        out = _trecho(out, de, ate, manter_inicio=True)
    for de, ate in aj.get("tabelas", []):
        out = _trecho(out, de, ate, aviso="[Tabela: ver o PDF, {pag}.]")
    if aj.get("formulas"):
        out = _formulas(out)
    for de, ate, tipo in aj.get("ver_pdf", []):
        out = _trecho(out, de, ate, manter_inicio=True, aviso=f"[{tipo}: ver o PDF, {{pag}}.]")
    for t in aj.get("transcrever", []):
        out = _transcrever(out, t["tirar"], t["depois_de"], t["linhas"])
    return out


def _transcrever(linhas, tirar, depois_de, novas):
    de, ate = tirar
    i = next((k for k, l in enumerate(linhas) if re.search(de, l["texto"])), None)
    if i is None:
        raise ValueError(f"AJUSTES: trecho a transcrever não encontrado: {de!r}")
    j = len(linhas) if ate is None else next((k for k in range(i + 1, len(linhas)) if re.search(ate, linhas[k]["texto"])), None)
    if j is None:
        raise ValueError(f"AJUSTES: fim do trecho a transcrever não encontrado: {ate!r}")
    linhas = linhas[:i] + linhas[j:]
    k = next((k for k, l in enumerate(linhas) if re.search(depois_de, l["texto"])), None)
    if k is None:
        raise ValueError(f"AJUSTES: lugar da transcrição não encontrado: {depois_de!r}")
    return linhas[:k + 1] + [{"pag": linhas[k]["pag"], "texto": t} for t in novas] + linhas[k + 1:]


def _trecho(linhas, de, ate, manter_inicio=False, aviso=None):
    """Tira as linhas de `de` até antes de `ate` (o primeiro par encontrado).
    manter_inicio: a linha `de` fica; aviso: entra no lugar das linhas tiradas, com a página."""
    r_de, r_ate = re.compile(de), re.compile(ate)
    i = next((k for k, l in enumerate(linhas) if r_de.search(l["texto"])), None)
    if i is None:
        raise ValueError(f"AJUSTES: trecho não encontrado: {de!r}")
    j = next((k for k in range(i + 1, len(linhas)) if r_ate.search(linhas[k]["texto"])), None)
    if j is None:
        raise ValueError(f"AJUSTES: fim do trecho não encontrado: {ate!r}")
    meio = [linhas[i]] if manter_inicio else []
    if aviso:
        # páginas das linhas tiradas (sem linhas tiradas: a fórmula é imagem, vale a página da linha `de`)
        k0 = i + 1 if manter_inicio and j > i + 1 else i
        p0, p1 = linhas[k0]["pag"], linhas[max(k0, j - 1)]["pag"]
        meio.append({"pag": p0, "texto": aviso.format(pag=f"p. {p0}" if p0 == p1 else f"pp. {p0}–{p1}")})
    return linhas[:i] + meio + linhas[j:]


def executar(docs, pasta_pdfs, pasta_dados):
    pasta_dados.mkdir(parents=True, exist_ok=True)
    for d in docs:
        if d["ocr"] == "sim":
            prefixo = "p" + d["id"].split("-")[2]  # res-arsp-048-2021 -> p048
            linhas, tach = extrair_ocr(prefixo), 0
        else:
            linhas, tach = extrair_pdf(pasta_pdfs / d["arquivo"], d["id"])
        linhas = recortar(linhas, d["id"])
        (pasta_dados / f"{d['id']}.linhas.json").write_text(
            json.dumps(linhas, ensure_ascii=False, indent=0), encoding="utf-8")
        print(f"  extraído {d['id']:22s} {len(linhas):5d} linhas  (trechos tachados removidos: {tach})")
