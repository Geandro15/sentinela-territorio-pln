# Sentinela do Território, Global Solution CitizenTech
# GEANDRO (RM 562316) | LUCAS VERO (RM 564202) | ROBERTO EDUARDO (RM 564537)

"""Avaliação do TTS: 10 respostas sintetizadas, notas de 1 a 5 de pelo menos 3 pessoas.

Passo 1, gerar os áudios e a planilha em branco:
    python -m avaliacao.avaliar_tts --gerar --avaliadores Geandro Lucas Roberto
Passo 2, cada avaliador ouve os áudios e preenche "naturalidade" e "clareza" (1 a 5).
Passo 3, calcular as médias:
    python -m avaliacao.avaliar_tts --resumir testes/resultados/tts/avaliacao_tts.csv
"""
from __future__ import annotations

import argparse
import csv
import shutil
from collections import defaultdict
from pathlib import Path

from assistente.adaptacao import adaptar_para_fala
from config import CONFIG


def gerar(args) -> int:
    from assistente.tts import ErroTTS, sintetizar

    frases = [f.strip() for f in Path(args.frases).read_text(encoding="utf-8").splitlines() if f.strip()]
    pasta = Path(args.saida)
    pasta.mkdir(parents=True, exist_ok=True)
    linhas = []
    for numero, frase in enumerate(frases, 1):
        fala = adaptar_para_fala(frase)
        try:
            audio = sintetizar(fala, CONFIG, pasta)
            destino = pasta / f"resposta_{numero:02d}{audio.suffix}"
            shutil.move(str(audio), destino)
            print(f"{destino.name}: {fala}")
        except ErroTTS as exc:
            print(f"resposta_{numero:02d}: falhou ({exc})")
            continue
        for avaliador in args.avaliadores:
            linhas.append({"id": f"{numero:02d}", "arquivo": destino.name, "texto_falado": fala,
                           "avaliador": avaliador, "naturalidade": "", "clareza": ""})
    if not linhas:
        print("Nenhum áudio gerado. Confira a configuração do TTS no arquivo .env.")
        return 1
    planilha = pasta / "avaliacao_tts.csv"
    with planilha.open("w", newline="", encoding="utf-8") as arquivo:
        escritor = csv.DictWriter(arquivo, fieldnames=list(linhas[0].keys()))
        escritor.writeheader()
        escritor.writerows(linhas)
    print(f"\nPlanilha em {planilha}. Preencha as notas de 1 a 5 e rode com --resumir.")
    return 0


def resumir(caminho: Path) -> int:
    with caminho.open(encoding="utf-8-sig", newline="") as arquivo:
        linhas = list(csv.DictReader(arquivo))
    notas = defaultdict(lambda: {"naturalidade": [], "clareza": []})
    for linha in linhas:
        for criterio in ("naturalidade", "clareza"):
            valor = (linha.get(criterio) or "").strip().replace(",", ".")
            if not valor:
                continue
            nota = float(valor)
            if not 1 <= nota <= 5:
                print(f"Nota fora da escala de 1 a 5: {linha}")
                return 1
            notas[linha["avaliador"]][criterio].append(nota)
            notas["TODOS"][criterio].append(nota)
    if not notas["TODOS"]["naturalidade"]:
        print("Nenhuma nota preenchida.")
        return 1

    def media(valores: list[float]) -> str:
        return f"{sum(valores) / len(valores):.2f}" if valores else "sem notas"

    md = ["# Resultado do TTS", "", f"Motor: {CONFIG.tts_engine}. Avaliadores: {len(notas) - 1}.", "",
          "| Avaliador | Respostas avaliadas | Naturalidade (1 a 5) | Clareza (1 a 5) |", "| --- | --- | --- | --- |"]
    for avaliador in sorted(notas, key=lambda a: (a == "TODOS", a)):
        dados = notas[avaliador]
        rotulo = "**Média geral**" if avaliador == "TODOS" else avaliador
        md.append(f"| {rotulo} | {len(dados['naturalidade'])} | {media(dados['naturalidade'])} | {media(dados['clareza'])} |")
    destino = caminho.with_name("tts_resumo.md")
    destino.write_text("\n".join(md) + "\n", encoding="utf-8")
    print("\n".join(md))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Avalia o TTS.")
    parser.add_argument("--gerar", action="store_true")
    parser.add_argument("--frases", default="testes/frases_tts.txt")
    parser.add_argument("--saida", default="testes/resultados/tts")
    parser.add_argument("--avaliadores", nargs="+", default=["avaliador_1", "avaliador_2", "avaliador_3"])
    parser.add_argument("--resumir")
    args = parser.parse_args(argv)
    if args.resumir:
        return resumir(Path(args.resumir))
    if args.gerar:
        return gerar(args)
    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
