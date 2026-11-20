# Sentinela do Território, Global Solution CitizenTech
# GEANDRO (RM 562316) | LUCAS VERO (RM 564202) | ROBERTO EDUARDO (RM 564537)

"""Avaliação do LLM com as 30 perguntas de teste.

Passo 1, gerar as respostas (rode uma vez para cada configuração comparada):
    python -m avaliacao.avaliar_llm --rotulo base
Passo 2, o grupo abre o CSV gerado e preenche a coluna "julgamento" com:
    correta | incorreta | recusa_adequada | recusa_indevida
Passo 3, calcular os percentuais:
    python -m avaliacao.avaliar_llm --resumir testes/resultados/llm_base.csv

O julgamento é humano de propósito: comparar texto automaticamente não mede
se a resposta está certa.
"""
from __future__ import annotations

import argparse
import csv
import time
from pathlib import Path

from assistente.pipeline import Assistente
from assistente.rag import BaseConhecimento
from config import CONFIG

MARCAS_DE_RECUSA = ("só oriento", "so oriento", "não tenho essa informação", "nao tenho essa informacao",
                    "fora do que eu sei", "não consigo ajudar", "procure um profissional")
JULGAMENTOS = {"correta", "incorreta", "recusa_adequada", "recusa_indevida"}


def ler_csv(caminho: Path) -> list[dict]:
    with caminho.open(encoding="utf-8-sig", newline="") as arquivo:
        return list(csv.DictReader(arquivo))


def gerar(args) -> int:
    perguntas = ler_csv(Path(args.perguntas))
    por_id = {p["id"]: p for p in perguntas}
    base = BaseConhecimento(CONFIG.corpus_texto)
    saida = Path(args.saida) / f"llm_{args.rotulo}.csv"
    saida.parent.mkdir(parents=True, exist_ok=True)
    linhas = []
    for pergunta in perguntas:
        assistente = Assistente(base=base)  # cada pergunta começa uma conversa nova
        anterior = por_id.get((pergunta.get("anterior_id") or "").strip())
        if anterior:  # pergunta de continuação: faz antes a pergunta anterior, na mesma conversa
            assistente.responder_texto(anterior["pergunta"], falar=False)
        inicio = time.perf_counter()
        resultado = assistente.responder_texto(pergunta["pergunta"], falar=False)
        duracao = time.perf_counter() - inicio
        recusou = any(marca in resultado.resposta.lower() for marca in MARCAS_DE_RECUSA)
        linhas.append({**pergunta, "resposta_obtida": resultado.resposta, "trechos_usados": len(resultado.fontes),
                       "recusou_auto": "sim" if recusou else "nao", "tempo_s": round(duracao, 2),
                       "erro": resultado.erro, "julgamento": ""})
        print(f"{pergunta['id']} [{pergunta['tipo']}] {duracao:.1f}s -> {resultado.resposta[:90]}")
    with saida.open("w", newline="", encoding="utf-8") as arquivo:
        escritor = csv.DictWriter(arquivo, fieldnames=list(linhas[0].keys()))
        escritor.writeheader()
        escritor.writerows(linhas)
    print(f"\nRespostas gravadas em {saida}. Preencha a coluna 'julgamento' e rode com --resumir.")
    return 0


def resumir(caminho: Path) -> int:
    linhas = ler_csv(caminho)
    pendentes = [l["id"] for l in linhas if (l.get("julgamento") or "").strip().lower() not in JULGAMENTOS]
    if pendentes:
        print(f"Faltam julgamentos válidos em {len(pendentes)} pergunta(s): {', '.join(pendentes)}")
        print(f"Valores aceitos: {', '.join(sorted(JULGAMENTOS))}")
        return 1

    def taxa(tipos: tuple[str, ...], alvo: str) -> tuple[int, int]:
        grupo = [l for l in linhas if l["tipo"] in tipos]
        return sum(l["julgamento"].strip().lower() == alvo for l in grupo), len(grupo)

    blocos = [("Perguntas do tema", ("tema",), "correta"),
              ("Perguntas de continuação", ("continuacao",), "correta"),
              ("Respostas corretas (tema e continuação)", ("tema", "continuacao"), "correta"),
              ("Recusas adequadas (fora do escopo)", ("fora_escopo",), "recusa_adequada")]
    tempo = sum(float(l.get("tempo_s") or 0) for l in linhas) / len(linhas)
    md = [f"# Resultado do LLM ({caminho.stem})", "", "| Indicador | Acertos | Total | Percentual |", "| --- | --- | --- | --- |"]
    for rotulo, tipos, alvo in blocos:
        certos, total = taxa(tipos, alvo)
        md.append(f"| {rotulo} | {certos} | {total} | {certos / total:.0%} |" if total else f"| {rotulo} | 0 | 0 | sem dados |")
    indevidas = sum(l["julgamento"].strip().lower() == "recusa_indevida" for l in linhas)
    md += ["", f"- Recusas indevidas (o assistente recusou o que devia responder): {indevidas}",
           f"- Tempo médio por resposta: {tempo:.2f} s"]
    destino = caminho.with_name(caminho.stem + "_resumo.md")
    destino.write_text("\n".join(md) + "\n", encoding="utf-8")
    print("\n".join(md))
    print(f"\nResumo gravado em {destino}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Avalia o LLM com as perguntas de teste.")
    parser.add_argument("--perguntas", default="testes/perguntas.csv")
    parser.add_argument("--saida", default="testes/resultados")
    parser.add_argument("--rotulo", default="base", help="nome da configuração, por exemplo: base ou ajustado")
    parser.add_argument("--resumir", help="CSV já julgado; calcula os percentuais")
    args = parser.parse_args(argv)
    return resumir(Path(args.resumir)) if args.resumir else gerar(args)


if __name__ == "__main__":
    raise SystemExit(main())
