# Sentinela do Território, Global Solution CitizenTech
# GEANDRO (RM 562316) | LUCAS VERO (RM 564202) | ROBERTO EDUARDO (RM 564537)

"""STT: transcrição de fala em português com faster-whisper (local)."""
from __future__ import annotations

import logging
import os
from pathlib import Path

log = logging.getLogger("assistente.stt")

_MODELOS: dict = {}


class ErroSTT(RuntimeError):
    """Falha na transcrição do áudio."""


def carregar_modelo(tamanho: str = "small", dispositivo: str = "auto"):
    """Carrega o modelo uma vez e reaproveita nas chamadas seguintes."""
    chave = (tamanho, dispositivo)
    if chave not in _MODELOS:
        from faster_whisper import WhisperModel

        if dispositivo == "auto":
            try:
                import torch

                dispositivo = "cuda" if torch.cuda.is_available() else "cpu"
            except Exception:
                dispositivo = "cpu"
        tipo = "float16" if dispositivo == "cuda" else "int8"
        log.info("Carregando Whisper %s em %s (%s).", tamanho, dispositivo, tipo)
        _MODELOS[chave] = WhisperModel(tamanho, device=dispositivo, compute_type=tipo)
    return _MODELOS[chave]


def _transcrever_uma_vez(modelo, caminho_audio: str, usar_vad: bool) -> tuple[str, float]:
    segmentos, info = modelo.transcribe(
        caminho_audio, language="pt", vad_filter=usar_vad, beam_size=5,
        vad_parameters={"min_silence_duration_ms": 500} if usar_vad else None,
    )
    texto = " ".join(s.text.strip() for s in segmentos).strip()
    duracao = getattr(info, "duration", 0.0) or 0.0
    return texto, duracao


def transcrever(caminho_audio: str | Path, tamanho: str = "small", dispositivo: str = "auto") -> str:
    """Transcreve um arquivo de áudio em português e devolve o texto.

    Primeiro tenta com o filtro de silêncio (VAD), que é mais rápido. Se o
    resultado vier vazio, tenta de novo sem o filtro antes de desistir: em
    alguns microfones e gravações curtas, o filtro descarta a fala por engano.
    """
    caminho_audio = Path(caminho_audio)
    if not caminho_audio.exists():
        raise ErroSTT("arquivo de áudio não encontrado")
    try:
        modelo = carregar_modelo(tamanho, dispositivo)
        texto, duracao = _transcrever_uma_vez(modelo, str(caminho_audio), usar_vad=True)
        log.info("STT (com filtro de silêncio): %.1fs de áudio, %d caractere(s) transcrito(s).",
                 duracao, len(texto))
        if not texto:
            log.warning("Nada reconhecido com o filtro de silêncio. Tentando sem o filtro...")
            texto, duracao = _transcrever_uma_vez(modelo, str(caminho_audio), usar_vad=False)
            log.info("STT (sem filtro de silêncio): %.1fs de áudio, %d caractere(s) transcrito(s): %r",
                     duracao, len(texto), texto)
        if not texto:
            log.warning("Áudio de %.1fs não gerou nenhum texto, mesmo sem o filtro de silêncio. "
                       "O arquivo pode estar mudo, cortado ou em outro idioma.", duracao)
        return texto
    except ErroSTT:
        raise
    except Exception as exc:
        raise ErroSTT(f"falha na transcrição: {exc}") from exc


def apagar_audio(caminho_audio: str | Path | None) -> None:
    """Retenção mínima (LGPD): apaga o áudio do cidadão depois da transcrição."""
    if not caminho_audio:
        return
    try:
        os.remove(caminho_audio)
    except OSError:
        pass
