# Sentinela do Território, Global Solution CitizenTech
# GEANDRO (RM 562316) | LUCAS VERO (RM 564202) | ROBERTO EDUARDO (RM 564537)

"""Acesso ao modelo de linguagem, com quatro provedores trocáveis.

LLM_PROVIDER=ollama  modelo local servido pelo Ollama (padrão, sem chave)
LLM_PROVIDER=openai  qualquer API compatível com OpenAI (nuvem, exige chave)
LLM_PROVIDER=hf      modelo local via transformers, com adaptador LoRA opcional
LLM_PROVIDER=mock    resposta simulada, para testes sem rede e sem modelo

Toda chamada tem timeout, novas tentativas com espera e tratamento de resposta
vazia. Em caso de falha, levanta ``ErroLLM`` e quem chamou decide o caminho
seguro.
"""
from __future__ import annotations

import json
import logging
import re
import time

import requests

from config import CONFIG, Config

log = logging.getLogger("assistente.llm")


class ErroLLM(RuntimeError):
    """Falha ao obter resposta do modelo de linguagem."""


# ------------------------------------------------------------------ provedores
def _ollama(mensagens: list[dict], cfg: Config, temperatura: float, formato_json: bool) -> str:
    corpo = {
        "model": cfg.ollama_model,
        "messages": mensagens,
        "stream": False,
        "options": {"temperature": temperatura},
    }
    if formato_json:
        corpo["format"] = "json"
    resposta = requests.post(f"{cfg.ollama_url.rstrip('/')}/api/chat", json=corpo, timeout=cfg.llm_timeout)
    resposta.raise_for_status()
    return resposta.json().get("message", {}).get("content", "")


def _openai(mensagens: list[dict], cfg: Config, temperatura: float, formato_json: bool) -> str:
    if not (cfg.openai_base_url and cfg.openai_api_key and cfg.openai_model):
        raise ErroLLM("Defina OPENAI_BASE_URL, OPENAI_API_KEY e OPENAI_MODEL no arquivo .env.")
    resposta = requests.post(
        f"{cfg.openai_base_url.rstrip('/')}/chat/completions",
        headers={"Authorization": f"Bearer {cfg.openai_api_key}"},
        json={"model": cfg.openai_model, "messages": mensagens, "temperature": temperatura},
        timeout=cfg.llm_timeout,
    )
    resposta.raise_for_status()
    opcoes = resposta.json().get("choices") or [{}]
    return (opcoes[0].get("message") or {}).get("content") or ""


_HF_CACHE: dict = {}


def _hf(mensagens: list[dict], cfg: Config, temperatura: float, formato_json: bool) -> str:
    chave = (cfg.hf_model, cfg.hf_lora)
    if chave not in _HF_CACHE:
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer

        tokenizador = AutoTokenizer.from_pretrained(cfg.hf_model)
        modelo = AutoModelForCausalLM.from_pretrained(
            cfg.hf_model,
            torch_dtype=torch.float16 if torch.cuda.is_available() else torch.float32,
            device_map="auto" if torch.cuda.is_available() else None,
        )
        if cfg.hf_lora:
            from peft import PeftModel

            modelo = PeftModel.from_pretrained(modelo, cfg.hf_lora)
        modelo.eval()
        _HF_CACHE[chave] = (tokenizador, modelo)
    tokenizador, modelo = _HF_CACHE[chave]
    entradas = tokenizador.apply_chat_template(
        mensagens, add_generation_prompt=True, return_tensors="pt", return_dict=True
    ).to(modelo.device)
    saida = modelo.generate(
        **entradas,
        max_new_tokens=300,
        do_sample=temperatura > 0,
        temperature=max(temperatura, 0.01),
        pad_token_id=tokenizador.eos_token_id,
    )
    novos = saida[0][entradas["input_ids"].shape[1]:]
    return tokenizador.decode(novos, skip_special_tokens=True)


def _mock(mensagens: list[dict], cfg: Config, temperatura: float, formato_json: bool) -> str:
    """Resposta simulada e determinística: devolve a primeira frase do contexto."""
    ultima = mensagens[-1]["content"]
    achado = re.search(r"\[1\]\s*(.+?)(?:\n|$)", ultima)
    if not achado:
        return "Não tenho essa informação. Eu só oriento sobre queimadas, alertas e riscos em construções."
    frase = re.split(r"(?<=[.!?])\s", achado.group(1).strip())[0]
    return frase


PROVEDORES = {"ollama": _ollama, "openai": _openai, "hf": _hf, "mock": _mock}


# --------------------------------------------------------------------- pública
def conversar(mensagens: list[dict], cfg: Config = CONFIG, temperatura: float | None = None,
              formato_json: bool = False, tentativas: int = 3) -> str:
    """Envia as mensagens ao LLM configurado e devolve o texto da resposta."""
    provedor = PROVEDORES.get(cfg.llm_provider)
    if provedor is None:
        raise ErroLLM(f"LLM_PROVIDER inválido: {cfg.llm_provider}. Use ollama, openai, hf ou mock.")
    temperatura = cfg.llm_temperature if temperatura is None else temperatura
    ultimo_erro: Exception | None = None
    for tentativa in range(1, tentativas + 1):
        try:
            texto = (provedor(mensagens, cfg, temperatura, formato_json) or "").strip()
            if texto:
                return texto
            ultimo_erro = ErroLLM("o modelo devolveu resposta vazia")
        except ErroLLM:
            raise
        except Exception as exc:  # rede, timeout, HTTP, modelo ausente
            ultimo_erro = exc
        log.warning("LLM falhou (tentativa %d de %d): %s", tentativa, tentativas, ultimo_erro)
        if tentativa < tentativas:
            time.sleep(2 * tentativa)
    raise ErroLLM(f"sem resposta do LLM após {tentativas} tentativas: {ultimo_erro}")


def extrair_json(texto: str):
    """Extrai o primeiro objeto ou lista JSON de uma resposta do LLM.

    Modelos pequenos costumam cercar o JSON com texto ou com blocos de código.
    Devolve ``None`` quando não há JSON válido.
    """
    texto = re.sub(r"```(?:json)?", "", texto).strip()
    try:
        return json.loads(texto)
    except json.JSONDecodeError:
        pass
    for abre, fecha in (("{", "}"), ("[", "]")):
        inicio, fim = texto.find(abre), texto.rfind(fecha)
        if 0 <= inicio < fim:
            try:
                return json.loads(texto[inicio:fim + 1])
            except json.JSONDecodeError:
                continue
    return None
