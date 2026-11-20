# Sentinela do Território, Global Solution CitizenTech
# GEANDRO (RM 562316) | LUCAS VERO (RM 564202) | ROBERTO EDUARDO (RM 564537)

"""Linha de comando da ferramenta de corpus.

Exemplo:
    python -m corpus --entrada dados/exemplos --saida dados/corpus
    python -m corpus --entrada dados/base --saida dados/corpus --sem-llm
"""
from __future__ import annotations

import argparse
import logging
import sys

from config import CONFIG

from .exportacao import exportar
from .geracao import ResultadoGeracao, dialogos_de_recusa, gerar_corpus
from .pipeline import processar_pasta


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m corpus", description="Gera os três corpus a partir de documentos.")
    parser.add_argument("--entrada", default="dados/exemplos", help="arquivo ou pasta com os documentos")
    parser.add_argument("--saida", default="dados/corpus", help="pasta onde os corpus serão gravados")
    parser.add_argument("--tamanho-trecho", type=int, default=500, help="tamanho máximo do trecho, em caracteres")
    parser.add_argument("--qa-por-trecho", type=int, default=2, help="perguntas geradas por trecho")
    parser.add_argument("--max-trechos", type=int, default=None, help="limita os trechos enviados ao LLM")
    parser.add_argument("--sem-llm", action="store_true", help="gera só o texto puro e os diálogos de recusa")
    parser.add_argument("--sem-mascarar", action="store_true", help="não mascara CPF, e-mail e telefone")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    log = logging.getLogger("corpus")

    registros, estatisticas, documentos = processar_pasta(
        args.entrada, tamanho_max=args.tamanho_trecho, mascarar=not args.sem_mascarar)
    if not registros:
        log.error("Nenhum trecho gerado. Verifique a pasta de entrada: %s", args.entrada)
        return 1
    log.info("%d trechos de texto puro a partir de %d documentos.", len(registros), len(documentos))

    if args.sem_llm:
        geracao = ResultadoGeracao(qa=[], dialogos=dialogos_de_recusa())
    else:
        log.info("Gerando perguntas e diálogos com o LLM (%s).", CONFIG.llm_provider)
        geracao = gerar_corpus(
            registros, qa_por_trecho=args.qa_por_trecho, max_trechos=args.max_trechos,
            progresso=lambda i, n: log.info("Trecho %d de %d", i, n))

    resumo = exportar(args.saida, registros, geracao.qa, geracao.dialogos, estatisticas, documentos,
                      geracao.descartados, geracao.falhas_llm)
    for nome, valor in resumo["contagem"].items():
        log.info("%s: %d exemplos", nome, valor)
    log.info("Corpus gravados em %s. Veja relatorio_corpus.md.", args.saida)
    return 0


if __name__ == "__main__":
    sys.exit(main())
