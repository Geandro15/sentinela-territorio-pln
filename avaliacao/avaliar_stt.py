# Sentinela do Território, Global Solution CitizenTech
# GEANDRO (RM 562316) | LUCAS VERO (RM 564202) | ROBERTO EDUARDO (RM 564537)

"""Avaliação do STT: WER por modelo, por grupo de locutor e por condição de ruído.

Entrada: testes/audios/manifesto.csv com as colunas
    arquivo, referencia, locutor, grupo, ruido
Saída:   testes/resultados/stt_detalhe.csv e testes/resultados/stt_resumo.md

Exemplo (compara dois tamanhos de Whisper):
    python -m avaliacao.avaliar_stt --modelos base small
"""
from __future__ import annotations

import argparse
import csv
import re
import time
from collections import defaultdict
from pathlib import Path

import jiwer

from assistente.stt import transcrever


def normalizar(texto: str) -> str:
    """Minúsculas, sem pontuação e com espaços simples. Aplicada à referência e à transcrição."""
    texto = re.sub(r"[^\w\s]", " ", texto.lower())
    return re.sub(r"\s+", " ", texto).strip()


def wer_conjunto(pares: list[tuple[str, str]]) -> float:
    pares = [(r, h) for r, h in pares if r]
    if not pares:
        return float("nan")
    return jiwer.wer([r for r, _ in pares], [h for _, h in pares])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Calcula o WER do STT.")
    parser.add_argument("--manifesto", default="testes/audios/manifesto.csv")
    parser.add_argument("--modelos", nargs="+", default=["base", "small"], help="tamanhos do Whisper a comparar")
    parser.add_argument("--saida", default="testes/resultados")
    args = parser.parse_args(argv)

    manifesto = Path(args.manifesto)
    if not manifesto.exists():
        print(f"Manifesto não encontrado: {manifesto}. Veja testes/audios/LEIA-ME.md.")
        return 1
    with manifesto.open(encoding="utf-8-sig", newline="") as arquivo:
        linhas = [l for l in csv.DictReader(arquivo) if (l.get("arquivo") or "").strip()]
    if not linhas:
        print("O manifesto está vazio. Grave os áudios e preencha o arquivo.")
        return 1

    saida = Path(args.saida)
    saida.mkdir(parents=True, exist_ok=True)
    detalhe, resumo = [], []
    for modelo in args.modelos:
        pares, por_grupo, por_ruido, tempos = [], defaultdict(list), defaultdict(list), []
        for linha in linhas:
            caminho = manifesto.parent / linha["arquivo"].strip()
            referencia = normalizar(linha.get("referencia", ""))
            inicio = time.perf_counter()
            try:
                hipotese = normalizar(transcrever(caminho, modelo))
                erro = ""
            except Exception as exc:  # um áudio com problema não interrompe a avaliação
                hipotese, erro = "", str(exc)
            duracao = time.perf_counter() - inicio
            wer = jiwer.wer(referencia, hipotese) if referencia else float("nan")
            par = (referencia, hipotese)
            pares.append(par)
            por_grupo[linha.get("grupo", "").strip() or "sem grupo"].append(par)
            por_ruido[linha.get("ruido", "").strip().lower() or "nao"].append(par)
            tempos.append(duracao)
            detalhe.append({"modelo": modelo, "arquivo": linha["arquivo"], "locutor": linha.get("locutor", ""),
                            "grupo": linha.get("grupo", ""), "ruido": linha.get("ruido", ""),
                            "referencia": referencia, "transcricao": hipotese,
                            "wer": round(wer, 4), "tempo_s": round(duracao, 2), "erro": erro})
            print(f"[{modelo}] {linha['arquivo']}: WER {wer:.2%} em {duracao:.1f}s")
        resumo.append({"modelo": modelo, "geral": wer_conjunto(pares), "tempo": sum(tempos) / len(tempos),
                       "grupo": {g: wer_conjunto(p) for g, p in por_grupo.items()},
                       "ruido": {r: wer_conjunto(p) for r, p in por_ruido.items()}})

    with (saida / "stt_detalhe.csv").open("w", newline="", encoding="utf-8") as arquivo:
        escritor = csv.DictWriter(arquivo, fieldnames=list(detalhe[0].keys()))
        escritor.writeheader()
        escritor.writerows(detalhe)

    md = ["# Resultado do STT", "", f"Áudios avaliados: {len(linhas)}", "",
          "## WER geral e tempo médio", "", "| Modelo | WER | Tempo médio por áudio (s) |", "| --- | --- | --- |"]
    md += [f"| {r['modelo']} | {r['geral']:.2%} | {r['tempo']:.2f} |" for r in resumo]
    md += ["", "## WER por condição de ruído", "", "| Modelo | Ruído | WER |", "| --- | --- | --- |"]
    md += [f"| {r['modelo']} | {ruido} | {valor:.2%} |" for r in resumo for ruido, valor in sorted(r["ruido"].items())]
    md += ["", "## WER por grupo de locutor (análise de viés)", "", "| Modelo | Grupo | WER |", "| --- | --- | --- |"]
    md += [f"| {r['modelo']} | {grupo} | {valor:.2%} |" for r in resumo for grupo, valor in sorted(r["grupo"].items())]
    (saida / "stt_resumo.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print(f"\nResumo gravado em {saida / 'stt_resumo.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
