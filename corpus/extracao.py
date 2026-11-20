# Sentinela do Território, Global Solution CitizenTech
# GEANDRO (RM 562316) | LUCAS VERO (RM 564202) | ROBERTO EDUARDO (RM 564537)

"""Extração de texto de vários tipos de arquivo.

Cada tipo tem a própria função. Um arquivo que falha é registrado em log e
devolvido com o campo ``erro`` preenchido, sem interromper os demais.
"""
from __future__ import annotations

import csv
import logging
from dataclasses import dataclass, field
from pathlib import Path

log = logging.getLogger("corpus.extracao")

EXTENSOES = {".pdf", ".docx", ".txt", ".md", ".html", ".htm", ".csv"}


@dataclass
class Documento:
    nome: str
    texto: str = ""
    fonte: str = ""
    erro: str = ""
    metadados: dict = field(default_factory=dict)


def _ler_texto(caminho: Path) -> str:
    dados = caminho.read_bytes()
    for codificacao in ("utf-8", "utf-8-sig", "cp1252", "latin-1"):
        try:
            return dados.decode(codificacao)
        except UnicodeDecodeError:
            continue
    return dados.decode("utf-8", errors="replace")


def _ler_pdf(caminho: Path) -> str:
    from pypdf import PdfReader

    leitor = PdfReader(str(caminho))
    # \f marca a quebra de página; a limpeza usa essa marca para achar
    # cabeçalhos e rodapés repetidos.
    return "\f".join((pagina.extract_text() or "") for pagina in leitor.pages)


def _ler_docx(caminho: Path) -> str:
    import docx

    documento = docx.Document(str(caminho))
    partes = [p.text for p in documento.paragraphs]
    for tabela in documento.tables:
        for linha in tabela.rows:
            partes.append(" | ".join(celula.text.strip() for celula in linha.cells))
    return "\n".join(partes)


def _ler_html(caminho: Path) -> str:
    from bs4 import BeautifulSoup

    sopa = BeautifulSoup(_ler_texto(caminho), "html.parser")
    for tag in sopa(["script", "style", "nav", "footer", "header", "noscript"]):
        tag.decompose()
    return sopa.get_text("\n")


def _ler_csv(caminho: Path) -> str:
    texto = _ler_texto(caminho)
    try:
        dialeto = csv.Sniffer().sniff(texto[:2000])
    except csv.Error:
        dialeto = csv.excel
    linhas = csv.reader(texto.splitlines(), dialeto)
    return "\n".join(". ".join(c.strip() for c in linha if c.strip()) for linha in linhas)


LEITORES = {
    ".pdf": _ler_pdf,
    ".docx": _ler_docx,
    ".txt": _ler_texto,
    ".md": _ler_texto,
    ".html": _ler_html,
    ".htm": _ler_html,
    ".csv": _ler_csv,
}


def extrair_arquivo(caminho: str | Path, fonte: str = "") -> Documento:
    """Extrai o texto de um arquivo. Nunca levanta exceção."""
    caminho = Path(caminho)
    doc = Documento(nome=caminho.name, fonte=fonte or caminho.name)
    extensao = caminho.suffix.lower()
    if not caminho.exists():
        doc.erro = "arquivo não encontrado"
    elif extensao not in LEITORES:
        doc.erro = f"tipo de arquivo não suportado: {extensao or 'sem extensão'}"
    else:
        try:
            doc.texto = LEITORES[extensao](caminho)
            if not doc.texto.strip():
                doc.erro = "nenhum texto extraído (o arquivo pode ser uma imagem digitalizada)"
        except Exception as exc:  # falha isolada, registrada em log
            doc.erro = f"falha na extração: {exc}"
    if doc.erro:
        log.warning("%s: %s", doc.nome, doc.erro)
    else:
        log.info("%s: %d caracteres extraídos", doc.nome, len(doc.texto))
    return doc


def extrair_texto_colado(texto: str, nome: str = "texto_colado", fonte: str = "") -> Documento:
    doc = Documento(nome=nome, texto=texto or "", fonte=fonte or nome)
    if not doc.texto.strip():
        doc.erro = "texto vazio"
    return doc
