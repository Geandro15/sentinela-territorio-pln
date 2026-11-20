# Sentinela do Território, Global Solution CitizenTech
# GEANDRO (RM 562316) | LUCAS VERO (RM 564202) | ROBERTO EDUARDO (RM 564537)

"""Configuração central do módulo de PLN do Sentinela do Território.

Todos os valores vêm de variáveis de ambiente (arquivo .env). Nenhuma chave
fica no código. Veja o arquivo .env.example para a lista completa.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

try:  # o projeto funciona mesmo sem python-dotenv instalado
    from dotenv import load_dotenv

    load_dotenv()
except Exception:  # pragma: no cover
    pass

RAIZ = Path(__file__).resolve().parent


def _env(nome: str, padrao: str) -> str:
    valor = os.getenv(nome, "").strip()
    return valor or padrao


@dataclass(frozen=True)
class Config:
    # LLM: "ollama" (local), "openai" (API compatível com OpenAI, na nuvem),
    # "hf" (modelo local via transformers, aceita adaptador LoRA) ou "mock".
    llm_provider: str = _env("LLM_PROVIDER", "ollama")
    ollama_url: str = _env("OLLAMA_URL", "http://localhost:11434")
    ollama_model: str = _env("OLLAMA_MODEL", "qwen2.5:3b")
    openai_base_url: str = _env("OPENAI_BASE_URL", "")
    openai_api_key: str = _env("OPENAI_API_KEY", "")
    openai_model: str = _env("OPENAI_MODEL", "")
    hf_model: str = _env("HF_MODEL", "Qwen/Qwen2.5-0.5B-Instruct")
    hf_lora: str = _env("HF_LORA", "")
    llm_timeout: int = int(_env("LLM_TIMEOUT", "120"))
    llm_temperature: float = float(_env("LLM_TEMPERATURE", "0.2"))

    # STT
    stt_model: str = _env("STT_MODEL", "small")
    stt_device: str = _env("STT_DEVICE", "auto")

    # TTS: "edge" (nuvem, Microsoft Edge TTS) ou "piper" (local)
    tts_engine: str = _env("TTS_ENGINE", "edge")
    edge_voice: str = _env("EDGE_VOICE", "pt-BR-FranciscaNeural")
    piper_model: str = _env("PIPER_MODEL", "")

    # RAG
    corpus_texto: Path = Path(_env("CORPUS_TEXTO", str(RAIZ / "dados" / "corpus" / "texto_puro.jsonl")))
    rag_top_k: int = int(_env("RAG_TOP_K", "3"))
    rag_score_minimo: float = float(_env("RAG_SCORE_MINIMO", "1.0"))

    # Busca na web (genai/busca_web.py): segunda fonte de evidência, usada só
    # quando a base local do INPE não cobre a pergunta. Gratuita, sem chave de API.
    busca_web_ativa: bool = _env("BUSCA_WEB_ATIVA", "true").lower() in ("1", "true", "sim")
    busca_web_max_resultados: int = int(_env("BUSCA_WEB_MAX_RESULTADOS", "3"))

    # Conversa
    max_turnos_memoria: int = int(_env("MAX_TURNOS_MEMORIA", "6"))
    max_frases_fala: int = int(_env("MAX_FRASES_FALA", "4"))

    # Registros
    pasta_logs: Path = RAIZ / "logs"

    @property
    def usa_nuvem(self) -> bool:
        """Indica se algum componente envia dados para fora da máquina."""
        return self.llm_provider == "openai" or self.tts_engine == "edge"


CONFIG = Config()
