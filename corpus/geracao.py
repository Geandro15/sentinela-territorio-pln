# Sentinela do Território, Global Solution CitizenTech
# GEANDRO (RM 562316) | LUCAS VERO (RM 564202) | ROBERTO EDUARDO (RM 564537)

"""Geração dos três tipos de corpus a partir dos trechos limpos.

1. Texto puro: sai direto da limpeza.
2. Perguntas e respostas: geradas pelo LLM, uma chamada por trecho.
3. Conversacional: diálogos de vários turnos gerados pelo LLM, mais diálogos
   de recusa e de falta de informação montados por regra.

Tudo o que o LLM gera é validado. Itens inválidos são descartados e contados.
"""
from __future__ import annotations

import logging
import random
from dataclasses import dataclass

from assistente import prompts
from assistente.llm import ErroLLM, conversar, extrair_json
from assistente.rag import tokenizar
from config import CONFIG, Config

log = logging.getLogger("corpus.geracao")

PROMPT_QA = """Você cria dados de treino em português do Brasil.
Leia o TRECHO e escreva {n} perguntas que um cidadão faria em linguagem simples, com a resposta.
Regras:
- A resposta deve usar SOMENTE informações do TRECHO.
- A resposta tem no máximo duas frases curtas, próprias para serem faladas.
- Não cite "o trecho" nem "o texto" na pergunta ou na resposta.
Responda apenas com JSON neste formato:
{{"itens": [{{"pergunta": "...", "resposta": "..."}}]}}

TRECHO:
{trecho}"""

PROMPT_DIALOGO = """Você cria dados de treino em português do Brasil.
Leia o TRECHO e escreva um diálogo curto entre um cidadão e um assistente de voz.
Regras:
- O diálogo tem {turnos} perguntas do cidadão e {turnos} respostas do assistente, alternadas.
- A segunda pergunta do cidadão deve ser uma continuação da primeira, como "e onde eu faço isso?".
- O assistente usa SOMENTE informações do TRECHO, em no máximo duas frases curtas por resposta.
Responda apenas com JSON neste formato:
{{"turnos": [{{"cidadao": "...", "assistente": "..."}}]}}

TRECHO:
{trecho}"""

# Perguntas fora do tema: ensinam o modelo a recusar.
PERGUNTAS_FORA_DO_TEMA = [
    "Qual é a previsão do jogo de futebol de hoje?",
    "Me passa uma receita de bolo de cenoura.",
    "Em quem eu devo votar na próxima eleição?",
    "Quanto está o dólar hoje?",
    "Escreve uma redação sobre as férias para mim.",
    "Qual remédio eu tomo para dor de cabeça?",
    "Me conta uma piada.",
    "Como eu faço para investir na bolsa?",
    "Qual é o melhor celular para comprar?",
    "Posso processar o meu vizinho por barulho?",
]

RECUSAS = [
    f"Eu só oriento sobre {prompts.TEMA}. Sobre esse assunto eu não consigo ajudar.",
    f"Esse assunto está fora do que eu sei. Posso ajudar com {prompts.TEMA}.",
]

RECUSA_SAUDE_JURIDICO = "Para esse assunto, procure um profissional ou o órgão responsável. Eu só oriento sobre " + prompts.TEMA + "."

# Perguntas do tema que a base não responde: ensinam o modelo a dizer que não sabe.
PERGUNTAS_SEM_RESPOSTA = [
    "Qual é o nome do chefe da Defesa Civil da minha cidade?",
    "Quantos focos de queimada tiveram ontem no meu bairro?",
    "Que horas a equipe da prefeitura vai chegar na minha rua?",
    "Qual é o valor da multa que o meu vizinho vai pagar pela queimada?",
    "Quando vai chover na minha região?",
]

NAO_SEI = "Não tenho essa informação. Procure a Defesa Civil ou a prefeitura da sua cidade."


@dataclass
class ResultadoGeracao:
    qa: list[dict]
    dialogos: list[dict]
    descartados: int = 0
    falhas_llm: int = 0


def resposta_sustentada(resposta: str, trecho: str, minimo: float = 0.5) -> bool:
    """Verifica se a maior parte das palavras da resposta aparece no trecho.

    É uma barreira simples contra respostas inventadas pelo LLM.
    """
    palavras = set(tokenizar(resposta))
    if not palavras:
        return False
    base = set(tokenizar(trecho))
    return len(palavras & base) / len(palavras) >= minimo


def _qa_simulado(trecho: str) -> list[dict]:
    frase = trecho.split(". ")[0].strip().rstrip(".") + "."
    return [{"pergunta": "O que eu preciso saber sobre isso?", "resposta": frase}]


def gerar_qa(registro: dict, n: int = 2, cfg: Config = CONFIG) -> tuple[list[dict], int]:
    """Gera até ``n`` pares de pergunta e resposta para um trecho.

    Devolve (itens válidos, quantidade descartada). Levanta ErroLLM se o
    modelo estiver indisponível.
    """
    trecho = registro["text"]
    if cfg.llm_provider == "mock":
        brutos = _qa_simulado(trecho)
    else:
        saida = conversar([{"role": "user", "content": PROMPT_QA.format(n=n, trecho=trecho)}],
                          cfg, temperatura=0.4, formato_json=True)
        dados = extrair_json(saida)
        brutos = dados.get("itens", []) if isinstance(dados, dict) else (dados if isinstance(dados, list) else [])
    validos, descartados = [], 0
    for item in brutos[:n]:
        pergunta = str(item.get("pergunta", "")).strip() if isinstance(item, dict) else ""
        resposta = str(item.get("resposta", "")).strip() if isinstance(item, dict) else ""
        if len(pergunta) < 8 or len(resposta) < 8 or not resposta_sustentada(resposta, trecho):
            descartados += 1
            continue
        validos.append({"pergunta": pergunta, "resposta": resposta, "contexto": trecho,
                        "fonte": registro.get("fonte", ""), "tipo": "tema"})
    return validos, descartados


def _mensagens(turnos: list[tuple[str, str]]) -> list[dict]:
    mensagens = [{"role": "system", "content": prompts.SYSTEM_PROMPT}]
    for cidadao, assistente in turnos:
        mensagens.append({"role": "user", "content": cidadao})
        mensagens.append({"role": "assistant", "content": assistente})
    return mensagens


def gerar_dialogo(registro: dict, turnos: int = 2, cfg: Config = CONFIG) -> dict | None:
    """Gera um diálogo com pergunta de continuação. Devolve None se inválido."""
    trecho = registro["text"]
    if cfg.llm_provider == "mock":
        frases = [f.strip().rstrip(".") + "." for f in trecho.split(". ") if f.strip()]
        pares = [("O que eu preciso saber sobre isso?", frases[0]),
                 ("E o que mais?", frases[1] if len(frases) > 1 else frases[0])]
    else:
        saida = conversar([{"role": "user", "content": PROMPT_DIALOGO.format(turnos=turnos, trecho=trecho)}],
                          cfg, temperatura=0.5, formato_json=True)
        dados = extrair_json(saida)
        lista = dados.get("turnos", []) if isinstance(dados, dict) else []
        pares = [(str(t.get("cidadao", "")).strip(), str(t.get("assistente", "")).strip())
                 for t in lista if isinstance(t, dict)]
    pares = [(c, a) for c, a in pares if len(c) >= 5 and len(a) >= 8]
    if len(pares) < 2 or not all(resposta_sustentada(a, trecho) for _, a in pares):
        return None
    return {"messages": _mensagens(pares), "contexto": trecho, "fonte": registro.get("fonte", ""),
            "tipo": "continuacao"}


def dialogos_de_recusa(semente: int = 42) -> list[dict]:
    """Diálogos montados por regra: fora do tema e sem resposta na base."""
    sorteio = random.Random(semente)
    saida = []
    for pergunta in PERGUNTAS_FORA_DO_TEMA:
        if any(p in pergunta.lower() for p in ("remédio", "processar")):
            resposta = RECUSA_SAUDE_JURIDICO
        else:
            resposta = sorteio.choice(RECUSAS)
        saida.append({"messages": _mensagens([(pergunta, resposta)]), "contexto": "", "fonte": "regra",
                      "tipo": "fora_do_tema"})
    for pergunta in PERGUNTAS_SEM_RESPOSTA:
        saida.append({"messages": _mensagens([(pergunta, NAO_SEI)]), "contexto": "", "fonte": "regra",
                      "tipo": "sem_resposta"})
    return saida


def gerar_corpus(registros: list[dict], qa_por_trecho: int = 2, dialogos: bool = True,
                 max_trechos: int | None = None, cfg: Config = CONFIG, progresso=None) -> ResultadoGeracao:
    """Gera os corpus de perguntas e respostas e conversacional.

    Uma falha do LLM em um trecho é registrada e o processo continua com o
    próximo. Depois de três falhas seguidas, a geração para e devolve o que
    já foi produzido.
    """
    resultado = ResultadoGeracao(qa=[], dialogos=[])
    alvo = registros[:max_trechos] if max_trechos else registros
    falhas_seguidas = 0
    for indice, registro in enumerate(alvo, 1):
        if progresso:
            progresso(indice, len(alvo))
        try:
            itens, descartados = gerar_qa(registro, qa_por_trecho, cfg)
            resultado.qa.extend(itens)
            resultado.descartados += descartados
            if dialogos:
                dialogo = gerar_dialogo(registro, cfg=cfg)
                if dialogo:
                    resultado.dialogos.append(dialogo)
                else:
                    resultado.descartados += 1
            falhas_seguidas = 0
        except ErroLLM as exc:
            resultado.falhas_llm += 1
            falhas_seguidas += 1
            log.error("Trecho %d: LLM indisponível (%s).", indice, exc)
            if falhas_seguidas >= 3:
                log.error("Três falhas seguidas do LLM. Geração interrompida com resultado parcial.")
                break
    if dialogos:
        resultado.dialogos.extend(dialogos_de_recusa())
    return resultado
