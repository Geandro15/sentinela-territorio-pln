# Sentinela do Território, Global Solution CitizenTech
# GEANDRO (RM 562316) | LUCAS VERO (RM 564202) | ROBERTO EDUARDO (RM 564537)

"""Adaptação do texto para fala, aplicada antes do TTS.

O sintetizador lê melhor frases curtas, sem markdown e sem emojis, com
números, siglas e datas escritos de forma pronunciável.
"""
from __future__ import annotations

import re
import unicodedata

try:
    from num2words import num2words
except Exception:  # pragma: no cover - sem a biblioteca, os números ficam como estão
    num2words = None

MESES = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho",
         "agosto", "setembro", "outubro", "novembro", "dezembro"]

DIGITOS = ["zero", "um", "dois", "três", "quatro", "cinco", "seis", "sete", "oito", "nove"]

# Números de serviço são falados dígito a dígito.
NUMEROS_DE_SERVICO = {"100", "153", "156", "180", "181", "188", "190", "192", "193", "197", "198", "199"}

# Siglas soletradas ou trocadas pelo nome falado.
SIGLAS = {
    "CPF": "cê pê efe",
    "RG": "erre gê",
    "CEP": "cep",
    "LGPD": "ele gê pê dê",
    "ONG": "ongue",
    "SUS": "sus",
    "SAMU": "samu",
    "INPE": "inpe",
    "INMET": "inmet",
    "IBAMA": "ibama",
    "PM": "polícia militar",
    "km": "quilômetros",
    "kg": "quilos",
    "m²": "metros quadrados",
    "nº": "número",
    "Nº": "número",
}


def _extenso(numero: int) -> str:
    if num2words is None:
        return str(numero)
    return num2words(numero, lang="pt_BR")


def _numero_para_fala(achado: re.Match) -> str:
    bruto = achado.group(0)
    if bruto in NUMEROS_DE_SERVICO:
        return " ".join(DIGITOS[int(d)] for d in bruto)
    if re.fullmatch(r"\d{1,3}(?:\.\d{3})+", bruto):  # milhar com ponto: 1.500
        return _extenso(int(bruto.replace(".", "")))
    if "," in bruto:  # decimal: 2,5
        inteiro, decimal = bruto.split(",")
        return f"{_extenso(int(inteiro))} vírgula {' '.join(DIGITOS[int(d)] for d in decimal)}"
    if len(bruto) >= 5:  # CEP, protocolos e números curtos de SMS: dígito a dígito
        return " ".join(DIGITOS[int(d)] for d in bruto)
    return _extenso(int(bruto))


def _data_para_fala(achado: re.Match) -> str:
    dia, mes, ano = int(achado.group(1)), int(achado.group(2)), achado.group(3)
    if not (1 <= dia <= 31 and 1 <= mes <= 12):
        return achado.group(0)
    dia_falado = "primeiro" if dia == 1 else _extenso(dia)
    texto = f"{dia_falado} de {MESES[mes - 1]}"
    if ano:
        ano_int = int(ano) + (2000 if len(ano) == 2 else 0)
        texto += f" de {_extenso(ano_int)}"
    return texto


def _hora_para_fala(achado: re.Match) -> str:
    hora, minuto = int(achado.group(1)), int(achado.group(2) or 0)
    if hora > 23 or minuto > 59:
        return achado.group(0)
    texto = f"{_extenso(hora)} hora" + ("" if hora == 1 else "s")
    if minuto:
        texto += f" e {_extenso(minuto)} minuto" + ("" if minuto == 1 else "s")
    return texto


def remover_marcacao(texto: str) -> str:
    """Tira markdown, links, endereços de internet e emojis."""
    texto = re.sub(r"```.*?```", " ", texto, flags=re.S)
    texto = re.sub(r"\[([^\]]+)\]\((?:[^)]+)\)", r"\1", texto)  # [texto](link) -> texto
    texto = re.sub(r"https?://\S+|www\.\S+", "", texto)
    texto = re.sub(r"\[\d+\]", "", texto)  # marcas de citação [1]
    texto = re.sub(r"(?m)^\s*(?:[-*•]|\d+[.)])\s+", "", texto)  # marcadores de lista
    texto = re.sub(r"(?m)^\s*#+\s*", "", texto)  # títulos
    texto = re.sub(r"[*_`~>|]", "", texto)
    texto = "".join(c for c in texto if unicodedata.category(c) not in ("So", "Sk", "Cs", "Co"))
    texto = texto.replace("️", "").replace("‍", "")
    return texto


def adaptar_para_fala(texto: str, max_frases: int = 4) -> str:
    """Converte a resposta do LLM em texto pronto para o sintetizador."""
    texto = remover_marcacao(texto)
    texto = re.sub(r"\s*\n+\s*", ". ", texto)  # quebras de linha viram pausas
    texto = re.sub(r"R\$\s?(\d+(?:\.\d{3})*)(?:,(\d{2}))?",
                   lambda m: f"{m.group(1)} reais" + (f" e {int(m.group(2))} centavos" if m.group(2) and int(m.group(2)) else ""),
                   texto)
    texto = re.sub(r"(\d)\s?%", r"\1 por cento", texto)
    texto = re.sub(r"(\d)\s?°\s?C\b", r"\1 graus", texto)
    texto = re.sub(r"\b(\d{1,2})/(\d{1,2})(?:/(\d{4}|\d{2}))?\b", _data_para_fala, texto)
    texto = re.sub(r"\b(\d{1,2})(?:h|:)(\d{2})?\b(?!\d)", lambda m: _hora_para_fala(m) if (m.group(2) or "h" in m.group(0)) else m.group(0), texto)
    for sigla, falado in SIGLAS.items():
        texto = re.sub(rf"(?<![\w]){re.escape(sigla)}(?![\w])", falado, texto)
    texto = re.sub(r"\d+(?:\.\d{3})+|\d+,\d+|\d+", _numero_para_fala, texto)
    texto = re.sub(r"\s*[;:]\s*", ". ", texto)
    texto = re.sub(r"\s*[()\[\]{}]\s*", ", ", texto)
    texto = re.sub(r"\s+", " ", texto)
    texto = re.sub(r"\s+([,.!?])", r"\1", texto)
    texto = re.sub(r"([,.!?])(?:\s*[,.])+", r"\1", texto).strip(" ,")
    frases = [f[0].upper() + f[1:] for f in (p.strip() for p in re.split(r"(?<=[.!?])\s+", texto)) if f]
    if max_frases and len(frases) > max_frases:
        frases = frases[:max_frases]
    texto = " ".join(frases)
    if texto and texto[-1] not in ".!?":
        texto += "."
    return texto
