"""Decisões da revisão humana das remissões (pipeline/revisoes.csv).

Cada linha diz o que fazer com uma remissão detectada:
  aceitar   o link fica como está e sai da lista "A conferir";
  sem_link  o trecho fica como texto simples e sai do "citado por";
  corrigir  o link passa a ir para novo_alvo, no formato do endereço do site
            (res-arsp-046-2021--art43-par7, ou só res-arsp-046-2021 para o ato inteiro).

A remissão é achada pelo ato e dispositivo de origem e pelo texto exato da citação,
não pela posição no texto. O texto da norma nunca muda: só o link.

A etapa 3 (remissoes.py) aplica as decisões e grava dados/revisoes_aplicadas.json.

Uso pelo comando /revisar:
    python pipeline/revisoes.py mesclar <arquivo>   grava no revisoes.csv as linhas copiadas do site
    python pipeline/revisoes.py validar             confere o revisoes.csv contra dados/
"""
import csv
import io
import json
import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
ARQ = RAIZ / "pipeline" / "revisoes.csv"
DADOS = RAIZ / "dados"
COLUNAS = ["doc", "dispositivo", "citacao", "decisao", "novo_alvo", "nota", "data"]
DECISOES = ("aceitar", "sem_link", "corrigir")


# ---------------------------------------------------------------- leitura e escrita

def ler_linhas(texto):
    """Linhas do CSV (lista de dicts). Ignora o cabeçalho, a linha '/revisar' e linhas vazias."""
    out = []
    for n, c in enumerate(csv.reader(io.StringIO(texto), delimiter=";"), start=1):
        if not c or not "".join(c).strip() or c[0].strip().startswith("/") or c[:2] == COLUNAS[:2]:
            continue
        out.append((n, c))
    return out


def carregar(caminho=ARQ):
    if not caminho.exists():
        return []
    linhas = []
    for n, c in ler_linhas(caminho.read_text(encoding="utf-8")):
        if len(c) != len(COLUNAS):
            raise SystemExit(f"{caminho.name}, linha {n}: {len(c)} colunas (esperado {len(COLUNAS)})")
        linhas.append(dict(zip(COLUNAS, (x.strip() for x in c))))
    return linhas


def gravar(linhas, caminho=ARQ):
    linhas = sorted(linhas, key=lambda l: (l["doc"], l["dispositivo"], l["citacao"]))
    with open(caminho, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, delimiter=";", lineterminator="\n")
        w.writerow(COLUNAS)
        for l in linhas:
            w.writerow([l.get(k, "") for k in COLUNAS])


def chave(l):
    return (l["doc"], l["dispositivo"], l["citacao"])


# ---------------------------------------------------------------- destinos

def dispositivos(doc):
    """(id do dispositivo, id do artigo) de todos os dispositivos de um ato."""
    for p in doc["partes"]:
        for b in p["blocos"]:
            if b["tipo"] != "artigo":
                continue
            yield b["id"], b["id"]
            for c in [b["caput"]] + b["paragrafos"]:
                yield c["id"], b["id"]
                for i in c["incisos"]:
                    yield i["id"], b["id"]
                    for a in i.get("alineas", []):
                        yield a["id"], b["id"]
                for a in c.get("alineas", []):
                    yield a["id"], b["id"]


class Alvos:
    """Resolve o endereço do site ('res-arsp-046-2021--art43-par7') para o dispositivo."""

    def __init__(self, docs):
        self.docs = {d["id"] for d in docs}
        self.m = {}
        for d in docs:
            for disp, art in dispositivos(d):
                self.m[(d["id"], disp)] = (disp, art)
                self.m.setdefault((d["id"], disp.replace("_", "-")), (disp, art))

    def resolver(self, texto):
        """-> (doc, dispositivo|None, artigo|None), ou None se não existir."""
        t = (texto or "").strip()
        if "#" in t:
            t = t.rsplit("#", 1)[1]
        doc, _, disp = t.partition("--")
        if doc not in self.docs:
            return None
        if not disp:
            return doc, None, None
        x = self.m.get((doc, disp))
        return (doc, x[0], x[1]) if x else None


def problemas(linhas, alvos):
    """Erros de formato e destinos inexistentes."""
    erros, vistos = [], {}
    for i, l in enumerate(linhas, start=2):
        rot = f"linha {i} ({l['doc']} {l['dispositivo']})"
        if l["doc"] not in alvos.docs:
            erros.append(f"{rot}: ato '{l['doc']}' não está no documentos.csv")
        if not l["dispositivo"] or not l["citacao"]:
            erros.append(f"{rot}: dispositivo e citacao são obrigatórios")
        if l["decisao"] not in DECISOES:
            erros.append(f"{rot}: decisao '{l['decisao']}' inválida (use {', '.join(DECISOES)})")
        if l["decisao"] == "corrigir":
            if not l["novo_alvo"]:
                erros.append(f"{rot}: corrigir sem novo_alvo")
            elif alvos.resolver(l["novo_alvo"]) is None:
                erros.append(f"{rot}: novo_alvo '{l['novo_alvo']}' não existe")
        elif l["novo_alvo"]:
            erros.append(f"{rot}: novo_alvo só vale para corrigir")
        if l["data"] and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", l["data"]):
            erros.append(f"{rot}: data '{l['data']}' fora do formato AAAA-MM-DD")
        k = chave(l)
        if k in vistos:
            erros.append(f"{rot}: mesma remissão da linha {vistos[k]}")
        vistos[k] = i
    return erros


# ---------------------------------------------------------------- aplicação (etapa 3)

class Aplicador:
    def __init__(self, linhas, docs):
        self.alvos = Alvos(docs)
        self.decs = []
        self.por_origem = {}   # (doc, dispositivo) -> {citação: decisão}
        for l in linhas:
            dec = dict(l, antes=[], usada=False)
            if l["decisao"] == "corrigir":
                dec["_alvo"] = self.alvos.resolver(l["novo_alvo"])
                if dec["_alvo"]:
                    dec["depois"] = {"para_doc": dec["_alvo"][0], "para": dec["_alvo"][1]}
            self.decs.append(dec)
            if l["decisao"] in DECISOES and (l["decisao"] != "corrigir" or dec["_alvo"]):
                self.por_origem.setdefault((l["doc"], l["dispositivo"]), {})[l["citacao"]] = dec

    def aplicar(self, doc_id, de, art_origem, texto, refs, arestas):
        """Aplica as decisões às remissões de um dispositivo. Devolve (refs, arestas)."""
        decs = self.por_origem.get((doc_id, de))
        if not decs:
            return refs, arestas
        novas_ar = [a for a in arestas if a.get("citacao") not in decs]
        novas_refs, aceitas = [], set()
        for r in refs:
            cit = texto[r["ini"]:r["fim"]]
            dec = decs.get(cit)
            if dec is None:
                novas_refs.append(r)
                continue
            minhas = [a for a in arestas if a.get("citacao") == cit]
            if not dec["usada"]:
                dec["usada"] = True
                dec["trecho"] = texto[max(0, r["ini"] - 60):r["fim"] + 40].strip()
                for a in minhas:
                    x = {"para_doc": a["para_doc"], "para": a["para"], "conf": a["conf"]}
                    if x not in dec["antes"]:
                        dec["antes"].append(x)
                if not minhas:
                    dec["antes"].append({"para_doc": r.get("doc"), "para": r.get("disp"), "conf": r.get("conf"),
                                         "externo": r.get("externo")})
            k = dec["decisao"]
            if k == "aceitar":
                novas_refs.append(dict(r, rev="aceitar", nota=dec["nota"]))
                if cit not in aceitas:   # a mesma citação duas vezes no dispositivo: arestas uma vez só
                    aceitas.add(cit)
                    novas_ar += [dict(a, revisao="aceitar") for a in minhas]
            elif k == "sem_link":
                novas_refs.append({"ini": r["ini"], "fim": r["fim"], "conf": "sem_link", "nota": dec["nota"]})
            else:
                ndoc, ndisp, nart = dec["_alvo"]
                orig = {"doc": r.get("doc"), "disp": r.get("disp"), "conf": r.get("conf")}
                if r.get("externo"):
                    orig["externo"] = r["externo"]
                novas_refs.append({"ini": r["ini"], "fim": r["fim"], "doc": ndoc, "disp": ndisp, "art": nart,
                                   "conf": "corrigido", "nota": dec["nota"], "orig": orig})
                a = {"de_doc": doc_id, "de": de, "de_art": art_origem["id"] if art_origem else None,
                     "para_doc": ndoc, "para": ndisp, "para_art": nart, "conf": "corrigido",
                     "trecho": texto[max(0, r["ini"] - 60):r["fim"] + 40], "citacao": cit}
                if ndisp:
                    if ndoc == doc_id and art_origem and nart == art_origem["id"]:
                        a["tipo"] = "interna-mesmo-artigo"
                    else:
                        a["tipo"] = "interna" if ndoc == doc_id else "externa"
                novas_ar.append(a)
        return novas_refs, novas_ar

    def gravar(self, caminho):
        limpa = lambda d: {k: v for k, v in d.items() if not k.startswith("_") and k != "usada"}
        aplicadas = [limpa(d) for d in self.decs if d["usada"]]
        orfas = [limpa(d) for d in self.decs if not d["usada"]]
        caminho.write_text(json.dumps({"aplicadas": aplicadas, "orfas": orfas}, ensure_ascii=False, indent=1),
                           encoding="utf-8")
        if self.decs:
            from collections import Counter
            c = Counter(d["decisao"] for d in aplicadas)
            print(f"  revisões aplicadas: {len(aplicadas)} ({', '.join(f'{k} {c[k]}' for k in DECISOES if c[k]) or 'nenhuma'})"
                  f"  |  sem correspondência: {len(orfas)}")
            for d in orfas:
                motivo = "novo_alvo inexistente" if d["decisao"] == "corrigir" and self.alvos.resolver(d["novo_alvo"]) is None \
                    else "a remissão não foi encontrada (o texto mudou?)"
                print(f"  ATENÇÃO: decisão não aplicada, {motivo}: {d['doc']} {d['dispositivo']} “{d['citacao']}”")


def carregar_aplicadas(pasta=DADOS):
    p = pasta / "revisoes_aplicadas.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {"aplicadas": [], "orfas": []}


# ---------------------------------------------------------------- linha de comando

def docs_atuais():
    sys.path.insert(0, str(RAIZ / "pipeline"))
    from comum import carregar_documentos
    out = []
    for d in carregar_documentos():
        p = DADOS / f"{d['id']}.estrutura.json"
        if p.exists():
            out.append(json.loads(p.read_text(encoding="utf-8")))
    return out


def cmd_mesclar(arquivo):
    """Grava no revisoes.csv as linhas copiadas da aba "A conferir"."""
    texto = Path(arquivo).read_text(encoding="utf-8-sig")
    docs = docs_atuais()
    alvos = Alvos(docs)
    atuais = {chave(l): l for l in carregar()}
    arestas = json.loads((DADOS / "remissoes.json").read_text(encoding="utf-8"))
    existentes = {(a["de_doc"], a["de"], a.get("citacao")) for a in arestas}
    erros, mud = [], {"incluídas": [], "trocadas": [], "desfeitas": [], "iguais": []}
    for n, c in ler_linhas(texto):
        if len(c) != len(COLUNAS):
            erros.append(f"linha {n}: {len(c)} colunas (esperado {len(COLUNAS)}): {';'.join(c)[:120]}")
            continue
        l = dict(zip(COLUNAS, (x.strip() for x in c)))
        l["nota"] = re.sub(r"\s*[;\r\n]+\s*", ", ", l["nota"]).strip(", ")
        k = chave(l)
        rot = f"{l['doc']} {l['dispositivo']} “{l['citacao']}”"
        if l["decisao"] == "desfazer":
            if k in atuais:
                del atuais[k]
                mud["desfeitas"].append(rot)
            else:
                erros.append(f"desfazer: {rot} não está no revisoes.csv")
            continue
        p = problemas([l], alvos)
        if p:
            erros += [x.replace("linha 2 ", "") for x in p]
            continue
        if k not in atuais and k not in existentes:
            erros.append(f"{rot}: essa remissão não existe nos dados atuais")
            continue
        if k in atuais:
            if all(atuais[k][x] == l[x] for x in ("decisao", "novo_alvo", "nota")):
                mud["iguais"].append(rot)
                continue
            mud["trocadas"].append(f"{rot}: {atuais[k]['decisao']} -> {l['decisao']}")
        else:
            mud["incluídas"].append(f"{rot}: {l['decisao']}{' -> ' + l['novo_alvo'] if l['novo_alvo'] else ''}")
        atuais[k] = l
    for x in erros:
        print("ERRO:", x)
    if erros:
        print("Nada foi gravado: corrija as linhas acima e cole de novo.")
        sys.exit(1)
    gravar(list(atuais.values()))
    for k, v in mud.items():
        if v:
            print(f"{k} ({len(v)}):")
            for x in v:
                print("  " + x)
    print(f"revisoes.csv: {len(atuais)} decisões")


def cmd_validar():
    linhas = carregar()
    erros = problemas(linhas, Alvos(docs_atuais()))
    ap = carregar_aplicadas()
    for d in ap["orfas"]:
        erros.append(f"decisão sem correspondência na última execução: {d['doc']} {d['dispositivo']} “{d['citacao']}”")
    for x in erros:
        print("ERRO:", x)
    print(f"{len(linhas)} decisões; {len(ap['aplicadas'])} aplicadas na última execução; {len(erros)} erros")
    sys.exit(1 if erros else 0)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    if len(sys.argv) >= 3 and sys.argv[1] == "mesclar":
        cmd_mesclar(sys.argv[2])
    elif len(sys.argv) == 2 and sys.argv[1] == "validar":
        cmd_validar()
    else:
        print(__doc__)
        sys.exit(2)
