# Sentinela do Território, Global Solution CitizenTech
# GEANDRO (RM 562316) | LUCAS VERO (RM 564202) | ROBERTO EDUARDO (RM 564537)

"""Orquestra a ferramenta de corpus: extração -> limpeza -> trechos."""
from __future__ import annotations

import hashlib
from datetime import date
from pathlib import Path

from .extracao import EXTENSOES, Documento, extrair_arquivo, extrair_texto_colado
from .limpeza import Estatisticas, limpar_texto, segmentar


def listar_arquivos(entrada: str | Path) -> list[Path]:
    entrada = Path(entrada)
    if entrada.is_file():
        return [entrada]
    return sorted(p for p in entrada.rglob("*")
                  if p.is_file() and p.suffix.lower() in EXTENSOES and p.name.lower() != "fontes.csv")


def ler_fontes(pasta: str | Path) -> dict[str, str]:
    """Lê o arquivo opcional fontes.csv (colunas: arquivo, fonte) da pasta de entrada.

    Serve para registrar a URL oficial de cada documento.
    """
    caminho = Path(pasta) / "fontes.csv"
    fontes: dict[str, str] = {}
    if caminho.is_file():
        import csv

        with caminho.open(encoding="utf-8-sig", newline="") as arquivo:
            for linha in csv.DictReader(arquivo):
                if linha.get("arquivo") and linha.get("fonte"):
                    fontes[linha["arquivo"].strip()] = linha["fonte"].strip()
    return fontes


def processar(documentos: list[Documento], tamanho_max: int = 500, mascarar: bool = True,
              data_consulta: str | None = None) -> tuple[list[dict], Estatisticas, list[dict]]:
    """Limpa e segmenta os documentos.

    Devolve (registros de texto puro, estatísticas, resumo por documento).
    Documentos com erro entram no resumo e não interrompem os demais.
    """
    data_consulta = data_consulta or date.today().isoformat()
    total = Estatisticas()
    vistos: set[str] = set()
    registros: list[dict] = []
    resumo: list[dict] = []
    for doc in documentos:
        item = {"nome": doc.nome, "fonte": doc.fonte, "erro": doc.erro, "trechos": 0}
        if not doc.erro:
            est = Estatisticas()
            texto = limpar_texto(doc.texto, est, mascarar=mascarar)
            trechos = segmentar(texto, est, tamanho_max=tamanho_max, vistos=vistos)
            for trecho in trechos:
                registros.append({
                    "id": hashlib.md5(trecho.encode("utf-8")).hexdigest()[:10],
                    "text": trecho,
                    "documento": doc.nome,
                    "fonte": doc.fonte,
                    "data_consulta": data_consulta,
                })
            item["trechos"] = len(trechos)
            total.somar(est)
        resumo.append(item)
    return registros, total, resumo


def processar_pasta(entrada: str | Path, **opcoes) -> tuple[list[dict], Estatisticas, list[dict]]:
    fontes = ler_fontes(entrada) if Path(entrada).is_dir() else {}
    documentos = [extrair_arquivo(c, fontes.get(c.name, "")) for c in listar_arquivos(entrada) if c.name != "fontes.csv"]
    return processar(documentos, **opcoes)


__all__ = ["processar", "processar_pasta", "extrair_arquivo", "extrair_texto_colado", "listar_arquivos"]
