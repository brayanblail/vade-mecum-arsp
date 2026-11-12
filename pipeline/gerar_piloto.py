"""Etapa 5 - Gera o site do piloto: uma página HTML só, com os dados embutidos.

Usa os mesmos dados do Quartz (dados/*.estrutura.json + remissoes.json).
Saída: site-piloto/index.html e site-piloto/pdf/<id>.pdf
"""
import json
import shutil
from pathlib import Path

from indice import Mapa

AQUI = Path(__file__).resolve().parent


def ref_compacta(r):
    o = {"i": r["ini"], "f": r["fim"], "c": r.get("conf", "")}
    if r.get("conf") == "sem_link":
        pass
    elif r.get("disp"):
        o["d"], o["s"] = r["doc"], r["disp"]
        if r.get("alvos"):
            o["S"] = r["alvos"]
    elif r.get("doc"):
        o["d"] = r["doc"]
    else:
        o["x"] = r.get("externo", "")
        if r.get("url"):
            o["u"] = r["url"]
    # revisão humana: "v" = link conferido e mantido; "o" = destino antes da correção; "n" = nota
    if r.get("rev") == "aceitar":
        o["v"] = 1
    if r.get("orig"):
        x = r["orig"]
        o["o"] = {"d": x.get("doc"), "s": x.get("disp")} if x.get("doc") else {"x": x.get("externo") or ""}
    if r.get("nota"):
        o["n"] = r["nota"]
    return o


def revisao_compacta(r):
    o = {"a": r["doc"], "b": r["dispositivo"], "x": r["citacao"], "k": r["decisao"], "h": r.get("trecho", ""),
         "o": [{"d": x.get("para_doc"), "e": x.get("para"), "g": x.get("conf"), "x": x.get("externo")} for x in r.get("antes", [])]}
    if r.get("depois"):
        o["p"] = {"d": r["depois"]["para_doc"], "e": r["depois"]["para"]}
    if r.get("nota"):
        o["n"] = r["nota"]
    if r.get("data"):
        o["dt"] = r["data"]
    return o


def unidade(u, tem_alineas=True):
    o = {"id": u["id"], "r": u.get("rotulo", ""), "t": u.get("texto", ""), "p": u.get("pag")}
    if u.get("refs"):
        o["R"] = [ref_compacta(r) for r in u["refs"]]
    if u.get("incisos"):
        o["I"] = [unidade(i) for i in u["incisos"]]
    if u.get("alineas"):
        o["A"] = [unidade(a) for a in u["alineas"]]
    return o


def bloco(b):
    if b["tipo"] == "titulo":
        return {"k": "h", "r": b["rotulo"], "t": b["texto"]}
    if b["tipo"] == "texto":
        o = {"k": "x", "L": b["linhas"], "p": b.get("pag")}
        if b.get("refs_linhas"):
            o["RL"] = {k: [ref_compacta(r) for r in v] for k, v in b["refs_linhas"].items() if v}
        if b.get("fecho"):
            o["fecho"] = 1
        return o
    o = {"k": "a", "id": b["id"], "r": b["rotulo"], "n": b["num"], "p": b["pag"],
         "C": unidade(b["caput"]), "P": [unidade(p) for p in b["paragrafos"]]}
    if b.get("titulo"):
        o["tt"] = b["titulo"]
    if b.get("secao"):
        o["sec"] = 1
    return o


def executar(docs, arestas, pasta_out, pasta_pdfs, revisoes=()):
    m = Mapa(docs)
    if pasta_out.exists():
        shutil.rmtree(pasta_out)
    (pasta_out / "pdf").mkdir(parents=True)
    dados_docs = []
    for d in docs:
        dados_docs.append({
            "id": d["id"], "sigla": d["sigla"], "num": int(d["numero"] or 0),"tipo": d["tipo"], "grupo": d["grupo"], "data": d["data"],
            "titulo": d["titulo"], "situacao": d["situacao"], "obs": d.get("observacao", ""),
            "link": d.get("link_oficial", ""), "rel": d.get("relacoes", ""), "padrao": d.get("alvo_padrao", ""),
            "partes": [{"id": p["id"], "r": p["rotulo"], "B": [bloco(b) for b in p["blocos"]]} for p in d["partes"]],
        })
        shutil.copy(pasta_pdfs / d["arquivo"], pasta_out / "pdf" / f"{d['id']}.pdf")
    rotulos = {f"{k[0]}|{k[1]}": v["rotulo"] for k, v in m.disp.items()}
    ar = [{"a": a["de_doc"], "b": a["de"], "c": a["de_art"], "d": a["para_doc"], "e": a["para"], "f": a["para_art"],
           "g": a["conf"], "t": a.get("tipo", "documento"), "h": a["trecho"].strip()[:220], "x": a.get("citacao", "")}
          for a in arestas]
    dados = {"docs": dados_docs, "arestas": ar, "rotulos": rotulos, "revisoes": [revisao_compacta(r) for r in revisoes]}
    js = json.dumps(dados, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    html = (AQUI / "piloto_template.html").read_text(encoding="utf-8").replace("/*__DADOS__*/{}", js)
    (pasta_out / "index.html").write_text(html, encoding="utf-8")
    print(f"  site-piloto/index.html: {len(html) / 1e6:.2f} MB, {len(dados_docs)} documentos, {len(ar)} remissões")
