# Sentinela do Território, Global Solution CitizenTech
# GEANDRO (RM 562316) | LUCAS VERO (RM 564202) | ROBERTO EDUARDO (RM 564537)

"""TTS: síntese de voz em português do Brasil.

TTS_ENGINE=edge   edge-tts (nuvem: o TEXTO da resposta é enviado ao serviço)
TTS_ENGINE=piper  Piper (local, exige o executável piper e um modelo .onnx)

Só vozes sintéticas prontas são usadas. Não há clonagem de voz.
"""
from __future__ import annotations

import asyncio
import logging
import subprocess
import tempfile
from pathlib import Path

from config import CONFIG, Config

log = logging.getLogger("assistente.tts")


class ErroTTS(RuntimeError):
    """Falha na síntese de voz."""


def _edge(texto: str, destino: Path, cfg: Config) -> Path:
    import edge_tts

    async def _gerar() -> None:
        await edge_tts.Communicate(texto, cfg.edge_voice).save(str(destino))

    try:
        asyncio.run(_gerar())
    except RuntimeError:  # já existe um laço de eventos nesta thread
        laco = asyncio.new_event_loop()
        try:
            laco.run_until_complete(_gerar())
        finally:
            laco.close()
    return destino


def _piper(texto: str, destino: Path, cfg: Config) -> Path:
    if not cfg.piper_model:
        raise ErroTTS("Defina PIPER_MODEL com o caminho do modelo .onnx.")
    subprocess.run(
        ["piper", "--model", cfg.piper_model, "--output_file", str(destino)],
        input=texto.encode("utf-8"), check=True, timeout=120, capture_output=True,
    )
    return destino


def sintetizar(texto: str, cfg: Config = CONFIG, pasta: str | Path | None = None) -> Path:
    """Gera um arquivo de áudio com a fala e devolve o caminho."""
    if not texto.strip():
        raise ErroTTS("texto vazio")
    pasta = Path(pasta) if pasta else Path(tempfile.gettempdir())
    pasta.mkdir(parents=True, exist_ok=True)
    sufixo = ".mp3" if cfg.tts_engine == "edge" else ".wav"
    destino = Path(tempfile.NamedTemporaryFile(suffix=sufixo, dir=pasta, delete=False).name)
    try:
        if cfg.tts_engine == "edge":
            return _edge(texto, destino, cfg)
        if cfg.tts_engine == "piper":
            return _piper(texto, destino, cfg)
        raise ErroTTS(f"TTS_ENGINE inválido: {cfg.tts_engine}. Use edge ou piper.")
    except ErroTTS:
        raise
    except Exception as exc:
        raise ErroTTS(f"falha na síntese de voz: {exc}") from exc
