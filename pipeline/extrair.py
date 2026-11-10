"""Etapa 1 - Extrai as linhas de texto de cada PDF, com o número da página.

- Remove cabeçalhos e rodapés repetidos (E-DOCS, endereço da ARSP, "PÁGINA x / y" etc.).
- Remove texto tachado (redações anteriores nos textos consolidados da Assembleia).
- Para PDFs com camada de texto corrompida (coluna ocr=sim), usa o texto de OCR
  salvo em ocr/<prefixo>-NN.txt (gerado com Tesseract, idioma por).
- Para na página de assinaturas do E-DOCS.

Saída: dados/<id>.linhas.json  ->  [{"pag": 1, "texto": "..."}, ...]
"""
import json
import re
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
    r"^P[áa]gina \d+ de \d+$",
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
AJUSTES = {
    "lei-11173-2020": {"inicio": r"^LEI N[º°] 11\.173", "fim": r"^(RENATO CASAGRANDE|JOSÉ RENATO CASAGRANDE)"},
    "res-arsp-053-2021": {"pular": r"\.{6,}\s*\d+\s*$"},  # linhas do índice com pontilhado
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


def extrair_pdf(caminho, doc_id):
    doc = pymupdf.open(caminho)
    brutas, tachados = [], 0
    for n, pag in enumerate(doc, start=1):
        hs = _linhas_horizontais(pag)
        altura = pag.rect.height
        for bloco in pag.get_text("dict")["blocks"]:
            for g in _linhas_visuais(bloco):
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
                t = re.sub(r"\s+", " ", "".join(vivos)).strip()
                tm = re.sub(r"\s+", " ", "".join(mortos)).strip()
                if not t and not tm:
                    continue
                y = g["y0"]
                if t and re.fullmatch(r"\d{1,3}", t) and (y < altura * 0.08 or y > altura * 0.90):
                    continue
                if t and _eh_ruido(t):
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
    out = []
    for l in linhas:
        if FIM_GERAL.search(l["texto"]) or (fim and fim.search(l["texto"])):
            break
        if pular and pular.search(l["texto"]):
            continue
        out.append(l)
    return out


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
