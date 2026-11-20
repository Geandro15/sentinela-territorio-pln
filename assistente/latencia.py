# Sentinela do Território, Global Solution CitizenTech
# GEANDRO (RM 562316) | LUCAS VERO (RM 564202) | ROBERTO EDUARDO (RM 564537)

"""Registro de latência por etapa e do total até o início da resposta falada."""
from __future__ import annotations

import csv
import time
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

ETAPAS = ["stt", "rag", "llm", "adaptacao", "tts"]
COLUNAS = ["data_hora", "conversa", "turno", *[f"{e}_s" for e in ETAPAS], "total_s", "llm", "stt_modelo", "tts"]


class Cronometro:
    """Mede o tempo de cada etapa de um turno da conversa."""

    def __init__(self) -> None:
        self.tempos: dict[str, float] = {}

    @contextmanager
    def etapa(self, nome: str):
        inicio = time.perf_counter()
        try:
            yield
        finally:
            self.tempos[nome] = self.tempos.get(nome, 0.0) + time.perf_counter() - inicio

    @property
    def total(self) -> float:
        return sum(self.tempos.values())

    def linha(self) -> dict:
        dados = {f"{e}_s": round(self.tempos.get(e, 0.0), 3) for e in ETAPAS}
        dados["total_s"] = round(self.total, 3)
        return dados


def registrar(pasta_logs: Path, conversa: str, turno: int, cron: Cronometro, extras: dict | None = None) -> Path:
    """Acrescenta uma linha em logs/latencia.csv. Não guarda o conteúdo da conversa."""
    pasta_logs.mkdir(parents=True, exist_ok=True)
    caminho = pasta_logs / "latencia.csv"
    novo = not caminho.exists()
    linha = {"data_hora": datetime.now().isoformat(timespec="seconds"), "conversa": conversa, "turno": turno,
             **cron.linha(), **(extras or {})}
    with caminho.open("a", newline="", encoding="utf-8") as arquivo:
        escritor = csv.DictWriter(arquivo, fieldnames=COLUNAS, extrasaction="ignore")
        if novo:
            escritor.writeheader()
        escritor.writerow(linha)
    return caminho
