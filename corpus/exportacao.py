# Sentinela do Território, Global Solution CitizenTech
# GEANDRO (RM 562316) | LUCAS VERO (RM 564202) | ROBERTO EDUARDO (RM 564537)

"""Exportação dos corpus em JSONL, com divisão em treino, validação e teste."""
from __future__ import annotations

import json
import random
from datetime import date
from pathlib import Path

from .limpeza import Estatisticas


def dividir(itens: list, semente: int = 42, treino: float = 0.8, validacao: float = 0.1) -> dict[str, list]:
    """Divide em treino, validação e teste, sempre da mesma forma (semente fixa).

    O conjunto de teste nunca entra no fine-tuning.
    """
    itens = list(itens)
    random.Random(semente).shuffle(itens)
    n = len(itens)
    if n < 5:  # corpus muito pequeno: tudo em treino
        return {"treino": itens, "validacao": [], "teste": []}
    n_teste = max(1, round(n * (1 - treino - validacao)))
    n_validacao = max(1, round(n * validacao))
    return {
        "teste": itens[:n_teste],
        "validacao": itens[n_teste:n_teste + n_validacao],
        "treino": itens[n_teste + n_validacao:],
    }


def gravar_jsonl(itens: list[dict], caminho: Path) -> Path:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    with caminho.open("w", encoding="utf-8") as arquivo:
        for item in itens:
            arquivo.write(json.dumps(item, ensure_ascii=False) + "\n")
    return caminho


def exportar(pasta: str | Path, texto_puro: list[dict], qa: list[dict], dialogos: list[dict],
             estatisticas: Estatisticas, documentos: list[dict], descartados: int = 0,
             falhas_llm: int = 0) -> dict:
    """Grava os três corpus e o relatório. Devolve o resumo usado na interface."""
    pasta = Path(pasta)
    arquivos = [gravar_jsonl(texto_puro, pasta / "texto_puro.jsonl")]
    contagem = {"texto_puro": len(texto_puro)}
    for nome, itens in (("perguntas_respostas", qa), ("conversacional", dialogos)):
        partes = dividir(itens)
        for parte, conteudo in partes.items():
            arquivos.append(gravar_jsonl(conteudo, pasta / f"{nome}_{parte}.jsonl"))
            contagem[f"{nome}_{parte}"] = len(conteudo)

    resumo = {
        "data": date.today().isoformat(),
        "documentos": documentos,
        "contagem": contagem,
        "limpeza": {
            "caracteres_antes": estatisticas.caracteres_antes,
            "caracteres_depois": estatisticas.caracteres_depois,
            "linhas_repetidas_removidas": estatisticas.linhas_repetidas_removidas,
            "hifens_unidos": estatisticas.hifens_unidos,
            "trechos_curtos_descartados": estatisticas.trechos_curtos_descartados,
            "duplicatas_removidas": estatisticas.duplicatas_removidas,
            "dados_mascarados": estatisticas.dados_mascarados,
        },
        "geracao": {"itens_descartados_na_validacao": descartados, "falhas_do_llm": falhas_llm},
        "arquivos": [a.name for a in arquivos],
    }
    (pasta / "relatorio_corpus.json").write_text(json.dumps(resumo, ensure_ascii=False, indent=2), encoding="utf-8")
    (pasta / "relatorio_corpus.md").write_text(relatorio_markdown(resumo, qa, dialogos, texto_puro), encoding="utf-8")
    return resumo


def relatorio_markdown(resumo: dict, qa: list[dict], dialogos: list[dict], texto_puro: list[dict]) -> str:
    limpeza, contagem = resumo["limpeza"], resumo["contagem"]
    linhas = [
        "# Relatório do corpus", "",
        f"Gerado em {resumo['data']}.", "",
        "## Documentos processados", "",
        "| Documento | Fonte | Situação | Trechos |", "| --- | --- | --- | --- |",
    ]
    for doc in resumo["documentos"]:
        linhas.append(f"| {doc['nome']} | {doc.get('fonte', '')} | {doc.get('erro') or 'ok'} | {doc.get('trechos', 0)} |")
    linhas += [
        "", "## Limpeza", "",
        "| Indicador | Valor |", "| --- | --- |",
        f"| Caracteres antes | {limpeza['caracteres_antes']} |",
        f"| Caracteres depois | {limpeza['caracteres_depois']} |",
        f"| Linhas de cabeçalho e rodapé removidas | {limpeza['linhas_repetidas_removidas']} |",
        f"| Palavras unidas (hífen no fim da linha) | {limpeza['hifens_unidos']} |",
        f"| Trechos curtos descartados | {limpeza['trechos_curtos_descartados']} |",
        f"| Trechos duplicados removidos | {limpeza['duplicatas_removidas']} |",
        f"| CPFs mascarados | {limpeza['dados_mascarados']['cpf']} |",
        f"| E-mails mascarados | {limpeza['dados_mascarados']['email']} |",
        f"| Telefones mascarados | {limpeza['dados_mascarados']['telefone']} |",
        "", "## Tamanho dos corpus", "",
        "| Arquivo | Exemplos |", "| --- | --- |",
    ]
    linhas += [f"| {nome} | {valor} |" for nome, valor in contagem.items()]
    geracao = resumo["geracao"]
    linhas += [
        "", "## Geração", "",
        f"- Itens descartados na validação: {geracao['itens_descartados_na_validacao']}",
        f"- Falhas do LLM: {geracao['falhas_do_llm']}",
        "", "## Exemplos", "",
    ]
    if texto_puro:
        linhas += ["Texto puro:", "", "```json", json.dumps(texto_puro[0], ensure_ascii=False), "```", ""]
    if qa:
        linhas += ["Perguntas e respostas:", "", "```json", json.dumps(qa[0], ensure_ascii=False), "```", ""]
    if dialogos:
        linhas += ["Conversacional:", "", "```json", json.dumps(dialogos[0], ensure_ascii=False), "```", ""]
    return "\n".join(linhas)
