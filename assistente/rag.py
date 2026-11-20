# Sentinela do Território, Global Solution CitizenTech
# GEANDRO (RM 562316) | LUCAS VERO (RM 564202) | ROBERTO EDUARDO (RM 564537)

"""Base de conhecimento: busca lexical (BM25) no corpus de texto puro.

O arquivo lido é o ``texto_puro.jsonl`` produzido pela ferramenta de corpus.
Cada linha tem ``text``, ``fonte`` e ``data_consulta``.
"""
from __future__ import annotations

import json
import logging
import math
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger("assistente.rag")

STOPWORDS = set(
    "a o as os um uma uns umas de do da dos das em no na nos nas por para com sem e ou que se "
    "eu tu ele ela nos eles elas me te lhe meu minha seu sua isso isto aquilo esse essa este esta "
    "ao aos como mais mas foi ser sao esta estao tem ter ha onde quando qual quais quem porque "
    "sobre entre ate ja nao sim muito pouco tambem so eh pra pro la aqui ai faco fazer devo posso".split()
)


def tokenizar(texto: str) -> list[str]:
    texto = unicodedata.normalize("NFD", texto.lower())
    texto = "".join(c for c in texto if unicodedata.category(c) != "Mn")
    return [t for t in re.findall(r"[a-z0-9]+", texto) if t not in STOPWORDS and len(t) > 1]


@dataclass
class Trecho:
    texto: str
    fonte: str
    pontuacao: float


class BM25:
    """BM25 escrito à mão, com o IDF da variante Lucene (sempre positivo).

    A fórmula clássica zera o peso de um termo que aparece em metade dos
    documentos, o que atrapalha em bases pequenas como a deste projeto.
    """

    def __init__(self, documentos: list[list[str]], k1: float = 1.5, b: float = 0.75):
        self.k1, self.b = k1, b
        self.frequencias = [Counter(doc) for doc in documentos]
        self.tamanhos = [len(doc) for doc in documentos]
        self.media = (sum(self.tamanhos) / len(documentos)) or 1.0
        presenca: Counter[str] = Counter()
        for doc in documentos:
            presenca.update(set(doc))
        n = len(documentos)
        self.idf = {termo: math.log(1 + (n - df + 0.5) / (df + 0.5)) for termo, df in presenca.items()}

    def pontuar(self, termos: list[str]) -> list[float]:
        pontos = []
        for frequencia, tamanho in zip(self.frequencias, self.tamanhos):
            norma = self.k1 * (1 - self.b + self.b * tamanho / self.media)
            pontos.append(sum(self.idf[t] * frequencia[t] * (self.k1 + 1) / (frequencia[t] + norma)
                              for t in set(termos) if t in frequencia))
        return pontos


class BaseConhecimento:
    def __init__(self, caminho: str | Path):
        self.caminho = Path(caminho)
        self.registros: list[dict] = []
        self._bm25: BM25 | None = None
        self.carregar()

    def carregar(self) -> None:
        self.registros = []
        if not self.caminho.exists():
            log.warning("Base de conhecimento não encontrada em %s. Rode a ferramenta de corpus.", self.caminho)
            self._bm25 = None
            return
        with self.caminho.open(encoding="utf-8") as arquivo:
            for numero, linha in enumerate(arquivo, 1):
                linha = linha.strip()
                if not linha:
                    continue
                try:
                    registro = json.loads(linha)
                    if registro.get("text"):
                        self.registros.append(registro)
                except json.JSONDecodeError:
                    log.warning("Linha %d inválida em %s, ignorada.", numero, self.caminho.name)
        tokens = [tokenizar(r["text"]) for r in self.registros]
        self._bm25 = BM25(tokens) if any(tokens) else None
        log.info("Base de conhecimento carregada: %d trechos.", len(self.registros))

    @property
    def vazia(self) -> bool:
        return self._bm25 is None

    def buscar(self, consulta: str, k: int = 3, pontuacao_minima: float = 1.0) -> list[Trecho]:
        """Devolve até ``k`` trechos com pontuação acima do mínimo.

        Lista vazia significa falta de evidência: o assistente deve dizer que
        não sabe em vez de inventar.
        """
        termos = tokenizar(consulta)
        if self.vazia or not termos:
            return []
        pontuacoes = self._bm25.pontuar(termos)
        ordem = sorted(range(len(pontuacoes)), key=lambda i: pontuacoes[i], reverse=True)[:k]
        return [
            Trecho(self.registros[i]["text"], self.registros[i].get("fonte", ""), float(pontuacoes[i]))
            for i in ordem
            if pontuacoes[i] >= pontuacao_minima
        ]


def montar_contexto(trechos: list[Trecho]) -> str:
    if not trechos:
        return "(nenhum trecho encontrado na base)"
    return "\n".join(f"[{i}] {t.texto}" for i, t in enumerate(trechos, 1))
