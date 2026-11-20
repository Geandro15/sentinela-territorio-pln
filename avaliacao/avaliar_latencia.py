# Sentinela do Território, Global Solution CitizenTech
# GEANDRO (RM 562316) | LUCAS VERO (RM 564202) | ROBERTO EDUARDO (RM 564537)

"""Avaliação de ponta a ponta: latência média por etapa e total.

Lê logs/latencia.csv, que o assistente preenche a cada turno. Para o teste
do enunciado, faça 10 conversas com pelo menos 3 turnos na interface (use
"Nova conversa" entre elas) e rode:
    python -m avaliacao.avaliar_latencia
"""
from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from pathlib import Path

ETAPAS = [("stt_s", "STT"), ("rag_s", "RAG"), ("llm_s", "LLM"), ("adaptacao_s", "Adaptação"),
          ("tts_s", "TTS"), ("total_s", "Total até o início da fala")]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Resume a latência registrada.")
    parser.add_argument("--log", default="logs/latencia.csv")
    parser.add_argument("--min-turnos", type=int, default=3)
    parser.add_argument("--saida", default="testes/resultados/latencia_resumo.md")
    args = parser.parse_args(argv)

    caminho = Path(args.log)
    if not caminho.exists():
        print(f"Log não encontrado: {caminho}. Use o assistente antes de rodar este script.")
        return 1
    with caminho.open(encoding="utf-8", newline="") as arquivo:
        linhas = list(csv.DictReader(arquivo))
    conversas = defaultdict(list)
    for linha in linhas:
        conversas[linha["conversa"]].append(linha)
    validas = {c: t for c, t in conversas.items() if len(t) >= args.min_turnos}
    if not validas:
        print(f"Nenhuma conversa com {args.min_turnos} turnos ou mais no log.")
        return 1

    turnos = [t for lista in validas.values() for t in lista]
    configuracoes = sorted({f"LLM {t.get('llm', '')}, Whisper {t.get('stt_modelo', '')}, TTS {t.get('tts', '')}" for t in turnos})
    md = ["# Resultado de ponta a ponta", "",
          f"Conversas com {args.min_turnos} turnos ou mais: {len(validas)}. Turnos medidos: {len(turnos)}.", "",
          "Configurações presentes no log: " + "; ".join(configuracoes) + ".", "",
          "| Etapa | Média (s) | Mínimo (s) | Máximo (s) |", "| --- | --- | --- | --- |"]
    for chave, rotulo in ETAPAS:
        valores = [float(t.get(chave) or 0) for t in turnos]
        md.append(f"| {rotulo} | {sum(valores) / len(valores):.2f} | {min(valores):.2f} | {max(valores):.2f} |")
    md += ["", "| Conversa | Turnos | Total médio por turno (s) |", "| --- | --- | --- |"]
    for conversa, lista in validas.items():
        totais = [float(t.get("total_s") or 0) for t in lista]
        md.append(f"| {conversa} | {len(lista)} | {sum(totais) / len(totais):.2f} |")
    destino = Path(args.saida)
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text("\n".join(md) + "\n", encoding="utf-8")
    print("\n".join(md))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
