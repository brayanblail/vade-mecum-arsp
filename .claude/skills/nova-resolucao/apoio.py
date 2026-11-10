"""Apoio ao comando /nova-resolucao.

    python .claude/skills/nova-resolucao/apoio.py pendentes
        PDFs da pasta principal que ainda não estão no documentos.csv.
    python .claude/skills/nova-resolucao/apoio.py sugerir "<arquivo.pdf>" [...]
        Linha sugerida para o CSV (nome do arquivo + catálogo .xlsx) e checagem da camada de texto.
    python .claude/skills/nova-resolucao/apoio.py validar
        Confere o documentos.csv (16 colunas, ids únicos, PDFs existentes...). Sai com código 1 se houver erro.
    python .claude/skills/nova-resolucao/apoio.py comparar [--rev HEAD]
        Compara as contagens de dados/ com as de uma versão do git: artigos, remissões, novas parciais e inferidas.

Opção comum: --pdfs "D:\\Claude\\Resoluções ARSP"
"""
import argparse
import csv
import io
import json
import re
import shutil
import subprocess
import sys
from collections import Counter
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[3]
PDFS_PADRAO = Path(r"D:\Claude\Resoluções ARSP")
CATALOGO = "_Catalogo_Resolucoes_Gas_ARSP.xlsx"
COLUNAS = ("id;sigla;tipo;orgao;numero;ano;data;grupo;arquivo;titulo;situacao;observacao;"
           "link_oficial;ocr;alvo_padrao;relacoes").split(";")
TIPOS = {"resolucao", "decisao", "lei", "lei-complementar", "minuta", "nota-tecnica"}
GRUPOS = {"Leis", "Resoluções", "Consultas públicas"}
NOME_PDF = re.compile(r"^(?P<data>\d{4}-\d{2}-\d{2}) - (?P<ato>.+?) (?P<num>\d{3})-(?P<ano>\d{4}) - (?P<assunto>.+)\.pdf$", re.I)

sys.stdout.reconfigure(encoding="utf-8")


def git():
    g = shutil.which("git") or r"C:\Program Files\Git\cmd\git.exe"
    if not Path(g).exists() and not shutil.which("git"):
        sys.exit("git não encontrado")
    return g


def ler(rel, rev=None):
    """Texto de um arquivo do projeto, na pasta ou numa versão do git (None se não existir)."""
    if rev is None:
        p = RAIZ / rel
        return p.read_text(encoding="utf-8") if p.exists() else None
    r = subprocess.run([git(), "show", f"{rev}:{rel}"], cwd=RAIZ, capture_output=True)
    return r.stdout.decode("utf-8") if r.returncode == 0 else None


def docs_csv(rev=None):
    return list(csv.DictReader(io.StringIO(ler("pipeline/documentos.csv", rev)), delimiter=";"))


def limpa(s):
    """Texto seguro para o CSV: sem ';', sem quebras de linha, espaços simples."""
    if s is None:
        return ""
    s = re.sub(r"\s+", " ", str(s)).strip()
    s = re.sub(r";\s*(\w)", lambda m: ". " + m.group(1).upper(), s)
    return s.replace(";", ",")


# ---------------------------------------------------------------- pendentes / sugerir

def catalogo(pdfs):
    """Linhas da aba Catalogo indexadas pelo nome do arquivo, com o link oficial (hiperlink da célula)."""
    try:
        import openpyxl
    except ImportError:
        print("  (openpyxl não instalado: sem dados do catálogo)")
        return {}
    arq = pdfs / CATALOGO
    if not arq.exists():
        print(f"  (catálogo não encontrado: {arq})")
        return {}
    ws = openpyxl.load_workbook(arq)["Catalogo"]
    cab = [c.value for c in ws[1]]
    out = {}
    for row in ws.iter_rows(min_row=2):
        v = {cab[i]: c for i, c in enumerate(row)}
        nome = v.get("Arquivo local")
        if not nome or not nome.value:
            continue
        reg = {k: c.value for k, c in v.items()}
        link = v.get("Link oficial")
        reg["_link"] = link.hyperlink.target if link is not None and link.hyperlink else ""
        reg["_situacao"] = next((c.value for k, c in v.items() if k and k.startswith("Situação")), "")
        out[nome.value] = reg
    return out


def cmd_pendentes(a):
    pdfs = Path(a.pdfs)
    cadastrados = {Path(d["arquivo"]).name for d in docs_csv()}
    cat = catalogo(pdfs)
    faltam = sorted(p.name for p in pdfs.glob("*.pdf") if p.name not in cadastrados)
    if not faltam:
        print("Todos os PDFs da pasta principal já estão no documentos.csv.")
        return
    print(f"PDFs da pasta principal fora do documentos.csv ({len(faltam)}):")
    for n in faltam:
        sit = (cat.get(n) or {}).get("_situacao") or "?"
        aviso = "  [ASPE: o pipeline ainda não suporta]" if "ASPE" in n.upper() else ""
        print(f"  {n}   (catálogo: {sit}){aviso}")


def checa_texto(pdf):
    """Diagnóstico rápido da camada de texto das 3 primeiras páginas."""
    try:
        import pymupdf
    except ImportError:
        return "não verificado (PyMuPDF não instalado)"
    with pymupdf.open(pdf) as doc:
        txt = "\n".join(doc[i].get_text() for i in range(min(3, doc.page_count)))
        paginas = doc.page_count
    palavras = re.findall(r"\w{6,}", txt)
    dobradas = sum(1 for w in palavras if re.fullmatch(r"(?:(\w)\1)+", w))
    longas = sum(1 for w in palavras if len(w) > 25)
    arts = len(re.findall(r"\bArt\.?\s*\d", txt))
    if len(txt.strip()) < 200:
        return f"SEM TEXTO nas primeiras páginas ({paginas} p.): provável PDF escaneado, precisa de OCR"
    if palavras and (dobradas / len(palavras) > 0.05 or longas / len(palavras) > 0.05):
        return (f"SUSPEITO: {dobradas} palavras com letras dobradas e {longas} palavras grudadas "
                f"em {len(palavras)}: provável camada corrompida, precisa de OCR")
    return f"ok ({paginas} p., {arts} 'Art.' nas 3 primeiras páginas)"


def cmd_sugerir(a):
    pdfs = Path(a.pdfs)
    cat = catalogo(pdfs)
    ids = {d["id"] for d in docs_csv()}
    erro = False
    for nome in a.arquivos:
        print(f"== {nome}")
        caminho = pdfs / nome
        if not caminho.exists():
            print(f"  ERRO: não existe {caminho}")
            erro = True
            continue
        m = NOME_PDF.match(Path(nome).name)
        if not m:
            print("  ERRO: nome fora do padrão 'AAAA-MM-DD - RES ARSP NNN-AAAA - Assunto.pdf'; preencha a linha à mão")
            erro = True
            continue
        ato = m["ato"].upper()
        num, ano = m["num"], m["ano"]
        if "ASPE" in ato:
            print("  NÃO SUPORTADO: o remissoes.py registra toda resolução como ARSP (Indice.por_chave).\n"
                  "  Incluir ato da ASPE exige mudar o pipeline antes.")
            erro = True
            continue
        if ato == "RES ARSP":
            tipo, orgao, did, sigla = "resolucao", "ARSP", f"res-arsp-{num}-{ano}", f"Res. ARSP {num}/{ano}"
        elif ato == "DEC ARSP-DG":
            tipo, orgao, did, sigla = "decisao", "ARSP/DG", f"dec-arsp-dg-{num}-{ano}", f"Decisão ARSP/DG {num}/{ano}"
        else:
            print(f"  ERRO: tipo de ato '{m['ato']}' não previsto; preencha a linha à mão")
            erro = True
            continue
        if did in ids:
            print(f"  já está no CSV como {did}")
            continue
        c = cat.get(Path(nome).name, {})
        if not c:
            print("  aviso: arquivo não encontrado no catálogo; título, situação, observação e link ficam vazios")
        rel = Path(nome).as_posix()
        linha = {
            "id": did, "sigla": sigla, "tipo": tipo, "orgao": orgao, "numero": str(int(num)), "ano": ano,
            "data": m["data"], "grupo": "Resoluções", "arquivo": rel,
            "titulo": limpa(c.get("Ementa (site)")), "situacao": limpa(c.get("_situacao")) or "Vigente",
            "observacao": limpa(c.get("Observações")), "link_oficial": c.get("_link", ""),
            "ocr": "nao", "alvo_padrao": "", "relacoes": "",
        }
        print("  linha sugerida:")
        print("  " + ";".join(linha[k] for k in COLUNAS))
        print(f"  texto do PDF: {checa_texto(caminho)}")
        for k in ("Relação com outros atos (citada na ementa)", "Revogada / alterada por"):
            if c.get(k):
                print(f"  catálogo, {k}: {c[k]}")
    sys.exit(1 if erro else 0)


# ---------------------------------------------------------------- validar

def cmd_validar(a):
    pdfs = Path(a.pdfs)
    erros, avisos = [], []
    linhas = (RAIZ / "pipeline" / "documentos.csv").read_text(encoding="utf-8").splitlines()
    if linhas[0].split(";") != COLUNAS:
        erros.append("cabeçalho diferente do esperado")
    vistos, nums_res = {}, {}
    for i, l in enumerate(linhas[1:], start=2):
        if not l.strip():
            continue
        c = l.split(";")
        if len(c) != len(COLUNAS):
            erros.append(f"linha {i}: {len(c)} colunas (esperado {len(COLUNAS)}); há ';' dentro de algum texto?")
            continue
        d = dict(zip(COLUNAS, c))
        rot = f"linha {i} ({d['id']})"
        if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", d["id"]):
            erros.append(f"{rot}: id fora do padrão")
        if d["id"] in vistos:
            erros.append(f"{rot}: id repetido (linha {vistos[d['id']]})")
        vistos[d["id"]] = i
        if d["tipo"] not in TIPOS:
            erros.append(f"{rot}: tipo '{d['tipo']}' inválido")
        if d["grupo"] not in GRUPOS:
            erros.append(f"{rot}: grupo '{d['grupo']}' inválido")
        if not d["numero"].isdigit():
            erros.append(f"{rot}: numero '{d['numero']}' não é inteiro")
        if not re.fullmatch(r"\d{4}", d["ano"]):
            erros.append(f"{rot}: ano '{d['ano']}' inválido")
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", d["data"]):
            erros.append(f"{rot}: data '{d['data']}' fora do formato AAAA-MM-DD")
        if not (pdfs / d["arquivo"]).exists():
            erros.append(f"{rot}: PDF não encontrado: {d['arquivo']}")
        if d["ocr"] not in ("sim", "nao"):
            erros.append(f"{rot}: ocr deve ser 'sim' ou 'nao'")
        elif d["ocr"] == "sim":
            pref = "p" + d["id"].split("-")[2]
            if not list((RAIZ / "ocr").glob(f"{pref}-*.txt")):
                erros.append(f"{rot}: ocr=sim mas não há ocr/{pref}-NN.txt")
        if d["tipo"] == "resolucao":
            if d["orgao"] != "ARSP":
                erros.append(f"{rot}: resolução de '{d['orgao']}': o pipeline só reconhece resoluções ARSP")
            n = d["numero"].lstrip("0")
            if n in nums_res:
                erros.append(f"{rot}: outra resolução com o número {n} ({nums_res[n]})")
            nums_res[n] = d["id"]
        if not d["titulo"]:
            avisos.append(f"{rot}: título vazio")
        if d["tipo"] in ("resolucao", "decisao") and not d["link_oficial"]:
            avisos.append(f"{rot}: sem link_oficial")
    for i, l in enumerate(linhas[1:], start=2):
        c = l.split(";")
        if len(c) != len(COLUNAS):
            continue
        d = dict(zip(COLUNAS, c))
        if d["alvo_padrao"] and d["alvo_padrao"] not in vistos:
            erros.append(f"linha {i} ({d['id']}): alvo_padrao '{d['alvo_padrao']}' não existe")
        for r in filter(None, d["relacoes"].split(",")):
            alvo = r.split(":", 1)[-1]
            if alvo not in vistos:
                erros.append(f"linha {i} ({d['id']}): relação para '{alvo}', que não existe")
    for x in avisos:
        print("aviso:", x)
    for x in erros:
        print("ERRO:", x)
    print(f"{len(vistos)} documentos; {len(erros)} erros; {len(avisos)} avisos")
    sys.exit(1 if erros else 0)


# ---------------------------------------------------------------- comparar

def contagens(rev=None):
    docs = docs_csv(rev)
    arestas = json.loads(ler("dados/remissoes.json", rev) or "[]")
    por_doc = {}
    for d in docs:
        t = ler(f"dados/{d['id']}.estrutura.json", rev)
        e = json.loads(t) if t else {"partes": [], "avisos": []}
        por_doc[d["id"]] = {
            "sigla": d["sigla"],
            "artigos": sum(1 for p in e["partes"] for b in p["blocos"] if b["tipo"] == "artigo"),
            "avisos": len(e.get("avisos", [])),
            "saem": 0, "citado": 0,
        }
    for x in arestas:
        if x["de_doc"] in por_doc:
            por_doc[x["de_doc"]]["saem"] += 1
        if x["para_doc"] != x["de_doc"] and x["para_doc"] in por_doc:
            por_doc[x["para_doc"]]["citado"] += 1
    nr = ler("dados/nao_resolvidas.csv", rev) or ""
    n_nr = max(0, sum(1 for _ in csv.reader(io.StringIO(nr), delimiter=";")) - 1)
    return por_doc, arestas, n_nr


def chave(x):
    return (x["de_doc"], x["de"], x["para_doc"], x["para"], x["conf"])


def cmd_comparar(a):
    antes, ar_a, nr_a = contagens(a.rev)
    depois, ar_d, nr_d = contagens(None)
    print(f"Comparação: {a.rev} -> pasta atual\n")
    print(f"{'documento':24} {'artigos':>13} {'remissões':>13} {'citado por':>13} {'avisos':>8}")
    for did, v in depois.items():
        o = antes.get(did)
        def col(k, larg=13):
            if o is None:
                return f"{'novo ' + str(v[k]):>{larg}}"
            s = f"{o[k]}" if o[k] == v[k] else f"{o[k]} -> {v[k]}"
            return f"{s:>{larg}}"
        marca = "+" if o is None else ("*" if any(o[k] != v[k] for k in ("artigos", "saem", "citado", "avisos")) else " ")
        print(f"{marca} {did:22} {col('artigos')} {col('saem')} {col('citado')} {col('avisos', 8)}")
    for did in antes:
        if did not in depois:
            print(f"- {did:22} (saiu do CSV)")
    tot = lambda c: (len(c[0]), sum(v["artigos"] for v in c[0].values()), len(c[1]), c[2])
    ta, td = tot((antes, ar_a, nr_a)), tot((depois, ar_d, nr_d))
    print(f"\nTOTAL  documentos {ta[0]} -> {td[0]} | artigos {ta[1]} -> {td[1]} | "
          f"remissões {ta[2]} -> {td[2]} | não resolvidas {ta[3]} -> {td[3]}")
    ca, cd = Counter(x["conf"] for x in ar_a), Counter(x["conf"] for x in ar_d)
    print("por nível: " + ", ".join(f"{k} {ca[k]} -> {cd[k]}" for k in sorted(set(ca) | set(cd))))

    ka = {chave(x) for x in ar_a}
    kd = {chave(x) for x in ar_d}
    novas = [x for x in ar_d if chave(x) not in ka]
    sumiram = [x for x in ar_a if chave(x) not in kd and x["de_doc"] in depois]
    for nivel in ("parcial", "inferido"):
        lst = [x for x in novas if x["conf"] == nivel]
        if lst:
            print(f"\nNovas remissões '{nivel}' ({len(lst)}):")
            for x in lst[:30]:
                print(f"  {x['de_doc']} {x['de']} -> {x['para_doc']} {x['para']}: …{x['trecho'][:100]}…")
    externas = [x for x in novas if x["de_doc"] in antes and x["para_doc"] not in antes]
    if externas:
        print(f"\nCitações de atos que já existiam para os atos novos ({len(externas)}):")
        for x in externas[:30]:
            print(f"  {x['de_doc']} {x['de']} -> {x['para_doc']} {x['para']} ({x['conf']})")
    if sumiram:
        print(f"\nATENÇÃO: {len(sumiram)} remissões de atos que já existiam sumiram (possível regressão):")
        for x in sumiram[:30]:
            print(f"  {x['de_doc']} {x['de']} -> {x['para_doc']} {x['para']} ({x['conf']}): …{x['trecho'][:80]}…")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pdfs", default=str(PDFS_PADRAO))
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("pendentes")
    s = sub.add_parser("sugerir")
    s.add_argument("arquivos", nargs="+")
    sub.add_parser("validar")
    c = sub.add_parser("comparar")
    c.add_argument("--rev", default="HEAD")
    a = ap.parse_args()
    {"pendentes": cmd_pendentes, "sugerir": cmd_sugerir, "validar": cmd_validar, "comparar": cmd_comparar}[a.cmd](a)


if __name__ == "__main__":
    main()
