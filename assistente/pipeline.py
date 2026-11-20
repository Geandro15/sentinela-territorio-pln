# Sentinela do Território, Global Solution CitizenTech
# GEANDRO (RM 562316) | LUCAS VERO (RM 564202) | ROBERTO EDUARDO (RM 564537)

"""Fluxo completo de um turno: áudio -> STT -> RAG -> LLM -> adaptação -> TTS."""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from config import CONFIG, Config

from . import prompts
from .adaptacao import adaptar_para_fala
from .latencia import Cronometro, registrar
from .llm import ErroLLM, conversar
from .memoria import Memoria
from .rag import BaseConhecimento, montar_contexto, tokenizar

log = logging.getLogger("assistente.pipeline")


@dataclass
class Resultado:
    transcricao: str = ""
    resposta: str = ""        # texto exibido na tela
    fala: str = ""            # texto adaptado, enviado ao TTS
    audio: str | None = None  # caminho do áudio da resposta
    fontes: list[str] = field(default_factory=list)
    tempos: dict = field(default_factory=dict)
    emergencia: bool = False
    erro: str = ""


def detectar_emergencia(texto: str) -> bool:
    texto = texto.lower()
    return any(termo in texto for termo in prompts.TERMOS_EMERGENCIA)


class Assistente:
    """Mantém a memória de uma conversa e responde turno a turno."""

    def __init__(self, cfg: Config = CONFIG, base: BaseConhecimento | None = None):
        self.cfg = cfg
        self.base = base or BaseConhecimento(cfg.corpus_texto)
        self.memoria = Memoria(cfg.max_turnos_memoria)
        self.conversa = uuid.uuid4().hex[:8]
        self.turno = 0

    def nova_conversa(self) -> None:
        self.memoria.limpar()
        self.conversa = uuid.uuid4().hex[:8]
        self.turno = 0

    # ----------------------------------------------------------------- etapas
    def _buscar(self, pergunta: str):
        """Busca trechos. Perguntas de continuação usam também a pergunta anterior."""
        cfg = self.cfg
        anterior = self.memoria.ultima_pergunta()
        inicio = pergunta.lower().lstrip()
        continuacao = len(tokenizar(pergunta)) <= 3 or inicio.startswith(("e ", "e, ", "mas ", "então ", "entao "))
        if anterior and continuacao:
            return self.base.buscar(f"{anterior} {pergunta}", cfg.rag_top_k, cfg.rag_score_minimo)
        trechos = self.base.buscar(pergunta, cfg.rag_top_k, cfg.rag_score_minimo)
        return trechos

    def _gerar(self, pergunta: str, trechos) -> str:
        mensagens = [
            {"role": "system", "content": prompts.SYSTEM_PROMPT},
            *self.memoria.mensagens(),
            {"role": "user", "content": f"TRECHOS:\n{montar_contexto(trechos)}\n\nPERGUNTA: {pergunta}"},
        ]
        return conversar(mensagens, self.cfg)

    # ---------------------------------------------------------------- públicas
    def responder_texto(self, pergunta: str, cron: Cronometro | None = None, falar: bool = True,
                        transcricao: str | None = None) -> Resultado:
        cron = cron or Cronometro()
        pergunta = (pergunta or "").strip()
        resultado = Resultado(transcricao=transcricao if transcricao is not None else pergunta)
        self.turno += 1

        if not pergunta:
            resultado.resposta = prompts.RESPOSTA_NAO_ENTENDI
        else:
            resultado.emergencia = detectar_emergencia(pergunta)
            with cron.etapa("rag"):
                trechos = self._buscar(pergunta)
            resultado.fontes = sorted({t.fonte for t in trechos if t.fonte})

            if not trechos:
                # Sem trechos relevantes: nem chamamos o LLM. Isso cobre tanto
                # perguntas fora do tema quanto perguntas do tema sem dados na
                # base, com uma resposta fixa que nunca alucina e nunca sugere
                # sites ou buscas, um modelo pequeno nem sempre obedece essa
                # regra só pelo texto do prompt, então a trava fica no código.
                resposta = prompts.RESPOSTA_SEM_CONTEXTO
            else:
                try:
                    with cron.etapa("llm"):
                        resposta = self._gerar(pergunta, trechos)
                except ErroLLM as exc:
                    log.error("LLM indisponível: %s", exc)
                    resultado.erro = "llm"
                    resposta = prompts.RESPOSTA_FALHA

            if resultado.emergencia and "193" not in resposta:
                resposta = f"{prompts.PREFIXO_EMERGENCIA} {resposta}"
            self.memoria.adicionar(pergunta, resposta)
            resultado.resposta = resposta

        with cron.etapa("adaptacao"):
            resultado.fala = adaptar_para_fala(resultado.resposta, self.cfg.max_frases_fala)

        if falar:
            from .tts import ErroTTS, sintetizar

            try:
                with cron.etapa("tts"):
                    resultado.audio = str(sintetizar(resultado.fala, self.cfg))
            except ErroTTS as exc:  # a resposta em texto continua disponível
                log.error("TTS indisponível: %s", exc)
                resultado.erro = resultado.erro or "tts"

        resultado.tempos = {**cron.linha()}
        try:
            registrar(self.cfg.pasta_logs, self.conversa, self.turno, cron,
                      {"llm": self.cfg.llm_provider, "stt_modelo": self.cfg.stt_model, "tts": self.cfg.tts_engine})
        except OSError as exc:
            log.warning("Não foi possível gravar a latência: %s", exc)
        return resultado

    def responder_audio(self, caminho_audio: str | Path, falar: bool = True) -> Resultado:
        """Recebe o áudio do cidadão, transcreve, apaga o áudio e responde."""
        from .stt import ErroSTT, apagar_audio, transcrever

        cron = Cronometro()
        try:
            with cron.etapa("stt"):
                texto = transcrever(caminho_audio, self.cfg.stt_model, self.cfg.stt_device)
        except ErroSTT as exc:
            log.error("STT falhou: %s", exc)
            resultado = self.responder_texto("", cron, falar, transcricao="")
            resultado.erro = "stt"
            return resultado
        finally:
            apagar_audio(caminho_audio)  # retenção mínima: o áudio não fica guardado
        return self.responder_texto(texto, cron, falar, transcricao=texto)
