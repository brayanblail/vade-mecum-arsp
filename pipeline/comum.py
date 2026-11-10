"""Funções compartilhadas entre as etapas."""
import csv
import re
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent

ROMANOS = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100}


def romano_para_int(s):
    s = s.upper()
    if not s or any(c not in ROMANOS for c in s):
        return None
    total, ant = 0, 0
    for c in reversed(s):
        v = ROMANOS[c]
        total = total - v if v < ant else total + v
        ant = max(ant, v)
    return total


def int_para_romano(n):
    tab = [(100, "C"), (90, "XC"), (50, "L"), (40, "XL"), (10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I")]
    out = ""
    for v, r in tab:
        while n >= v:
            out += r
            n -= v
    return out


def ordinal(n):
    """Rótulo de artigo/parágrafo: 1º..9º, 10, 11..."""
    base = re.match(r"\d+", n).group(0)
    suf = n[len(base):]
    return (f"{base}º" if int(base) < 10 else base) + suf


def carregar_documentos(caminho=None):
    caminho = caminho or RAIZ / "pipeline" / "documentos.csv"
    with open(caminho, encoding="utf-8") as f:
        return list(csv.DictReader(f, delimiter=";"))


def slug(s):
    import unicodedata
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")
