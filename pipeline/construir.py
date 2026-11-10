"""Roda o pipeline inteiro.

Uso (na pasta do kit):
    python pipeline/construir.py --pdfs "D:\\Claude\\Resoluções ARSP"

Etapas: extrair -> estruturar -> remissoes -> quartz -> piloto
  --so quartz            roda só a geração do content/ (usa dados/ já existentes)
  --sem-piloto           não gera o site-piloto/index.html
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import comum  # noqa: E402
import estruturar  # noqa: E402
import extrair  # noqa: E402
import gerar_piloto  # noqa: E402
import gerar_quartz  # noqa: E402
import indice  # noqa: E402
import remissoes  # noqa: E402

ETAPAS = ["extrair", "estruturar", "remissoes", "quartz", "piloto"]


def main():
    ap = argparse.ArgumentParser(description="Gera o vade-mécum ARSP (Quartz + piloto)")
    ap.add_argument("--pdfs", required=True, help="pasta 'Resoluções ARSP' com os PDFs (caminhos do documentos.csv)")
    ap.add_argument("--csv", default=str(comum.RAIZ / "pipeline" / "documentos.csv"))
    ap.add_argument("--so", choices=ETAPAS, help="rodar apenas uma etapa")
    ap.add_argument("--sem-piloto", action="store_true")
    a = ap.parse_args()

    pdfs = Path(a.pdfs)
    dados = comum.RAIZ / "dados"
    docs = comum.carregar_documentos(Path(a.csv))
    faltando = [d["arquivo"] for d in docs if not (pdfs / d["arquivo"]).exists()]
    if faltando:
        print("PDFs não encontrados (confira a coluna 'arquivo' do CSV):")
        for f in faltando:
            print("   ", f)
        sys.exit(1)

    etapas = [a.so] if a.so else [e for e in ETAPAS if not (a.sem_piloto and e == "piloto")]
    if "extrair" in etapas:
        print("1/5 Extraindo texto dos PDFs")
        extrair.executar(docs, pdfs, dados)
    if "estruturar" in etapas:
        print("2/5 Identificando artigos, parágrafos, incisos e alíneas")
        estruturar.executar(docs, dados)
    if "remissoes" in etapas:
        print("3/5 Ligando remissões")
        remissoes.executar(docs, dados)
    if "quartz" in etapas or "piloto" in etapas:
        est, arestas = indice.carregar(docs, dados)
        if "quartz" in etapas:
            print("4/5 Gerando content/ para o Quartz e o Obsidian")
            gerar_quartz.executar(est, arestas, comum.RAIZ / "content", pdfs)
        if "piloto" in etapas:
            print("5/5 Gerando site-piloto/index.html")
            gerar_piloto.executar(est, arestas, comum.RAIZ / "site-piloto", pdfs)
    print("Pronto. Revise dados/nao_resolvidas.csv e content/revisao.md.")


if __name__ == "__main__":
    main()
