"""Etapa 5 (junto com o site) - Gera a skill "vade-mecum-arsp-links" para o Claude.

A skill liga as citações de um documento Word (.docx) aos dispositivos do site, com dica de
tela (ScreenTip) com o texto do dispositivo. Usa o mesmo detector do site: os módulos do
pipeline são copiados para a skill junto com uma base enxuta dos dispositivos.

Saídas (regeneradas a cada execução; não edite à mão):
  skill/vade-mecum-arsp-links/          SKILL.md, scripts/ e dados/base.json
  skill/vade-mecum-arsp-links.zip       para enviar no claude.ai (Configurações > Capacidades > Skills)
  site-piloto/vinculos.json             a mesma base, publicada: a skill baixa a mais nova
  site-piloto/skill/vade-mecum-arsp-links.zip

Fontes: pipeline/skill/SKILL.modelo.md e pipeline/skill/vincular.py.
"""
import hashlib
import json
import shutil
import zipfile
from pathlib import Path

NOME = "vade-mecum-arsp-links"
SITE = "https://brayanblail.github.io/vade-mecum-arsp/"
FORMATO = 1
AQUI = Path(__file__).resolve().parent
MODULOS = ["comum.py", "indice.py", "remissoes.py", "revisoes.py"]
CAMPOS_DOC = ("id", "sigla", "tipo", "orgao", "numero", "ano", "data", "grupo", "titulo", "situacao")
FORA = {"refs", "refs_linhas", "pag", "_titulo_aberto"}


def enxuto(o):
    if isinstance(o, dict):
        return {k: enxuto(v) for k, v in o.items() if k not in FORA}
    if isinstance(o, list):
        return [enxuto(x) for x in o]
    return o


def montar_base(docs):
    """Só os blocos com dispositivos (artigos, cláusulas, itens), sem as remissões já detectadas."""
    out = []
    for d in docs:
        partes = [{"id": p["id"], "rotulo": p["rotulo"], "blocos": [enxuto(b) for b in p["blocos"] if b["tipo"] == "artigo"]}
                  for p in d["partes"]]
        out.append({**{k: d.get(k, "") for k in CAMPOS_DOC}, "partes": [p for p in partes if p["blocos"]]})
    corpo = json.dumps(out, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return {"formato": FORMATO, "versao": hashlib.sha1(corpo.encode("utf-8")).hexdigest()[:8], "site": SITE, "docs": out}


def tabela_atos(docs):
    linhas = ["| id | ato | situação | ementa |", "|---|---|---|---|"]
    for d in docs:
        ementa = d["titulo"].replace("|", "/")
        ementa = ementa if len(ementa) <= 140 else ementa[:139].rsplit(" ", 1)[0] + "…"
        linhas.append(f"| `{d['id']}` | {d['sigla']} | {d['situacao']} | {ementa} |")
    return "\n".join(linhas)


def zipar(pasta, destino):
    """Zip estável (datas fixas, ordem fixa): só muda quando o conteúdo muda."""
    with zipfile.ZipFile(destino, "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted(pasta.rglob("*")):
            if f.is_file() and "__pycache__" not in f.parts:
                info = zipfile.ZipInfo(f"{NOME}/{f.relative_to(pasta).as_posix()}", date_time=(2026, 1, 1, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o644 << 16
                z.writestr(info, f.read_bytes())


def executar(docs, pasta_skill, pasta_site):
    base = montar_base(docs)
    dados = json.dumps(base, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    pasta = pasta_skill / NOME
    if pasta.exists():
        shutil.rmtree(pasta)
    (pasta / "scripts").mkdir(parents=True)
    (pasta / "dados").mkdir()
    for m in MODULOS:
        shutil.copyfile(AQUI / m, pasta / "scripts" / m)
    shutil.copyfile(AQUI / "skill" / "vincular.py", pasta / "scripts" / "vincular.py")
    (pasta / "dados" / "base.json").write_bytes(dados)
    md = (AQUI / "skill" / "SKILL.modelo.md").read_text(encoding="utf-8")
    md = (md.replace("{{SITE}}", SITE).replace("{{VERSAO}}", base["versao"])
          .replace("{{N_ATOS}}", str(len(base["docs"]))).replace("{{ATOS}}", tabela_atos(base["docs"])))
    (pasta / "SKILL.md").write_bytes(md.encode("utf-8"))
    zipar(pasta, pasta_skill / f"{NOME}.zip")
    # no site: a base para a skill baixar e o zip para quem for instalar
    (pasta_site / "vinculos.json").write_bytes(dados)
    (pasta_site / "skill").mkdir(parents=True, exist_ok=True)
    shutil.copyfile(pasta_skill / f"{NOME}.zip", pasta_site / "skill" / f"{NOME}.zip")
    print(f"  skill/{NOME}.zip: {len(base['docs'])} atos, base {len(dados) / 1e3:.0f} KB, versão {base['versao']}")
