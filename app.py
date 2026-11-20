# Sentinela do Território, Global Solution CitizenTech
# GEANDRO (RM 562316) | LUCAS VERO (RM 564202) | ROBERTO EDUARDO (RM 564537)

"""Interface do módulo de PLN do Sentinela do Território.

Duas abas:
  1. Assistente de voz: microfone ou upload -> STT -> RAG -> LLM -> TTS.
  2. Ferramenta de corpus: upload, limpeza, três corpus, revisão e exportação.

Como rodar:  python app.py
No celular:  defina GRADIO_SHARE=1 no .env e abra o link https que aparece no terminal.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

import gradio as gr

from assistente import prompts
from assistente.pipeline import Assistente
from assistente.rag import BaseConhecimento
from config import CONFIG
from corpus.exportacao import exportar
from corpus.extracao import extrair_arquivo, extrair_texto_colado
from corpus.geracao import gerar_corpus
from corpus.pipeline import processar

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("app")

BASE = BaseConhecimento(CONFIG.corpus_texto)
PASTA_CORPUS = Path(CONFIG.corpus_texto).parent


# ============================================================ assistente de voz
def _tabela_latencia(tempos: dict) -> str:
    if not tempos:
        return ""
    nomes = {"stt_s": "Ouvir (STT)", "rag_s": "Buscar (RAG)", "llm_s": "Pensar (LLM)",
             "adaptacao_s": "Adaptar para fala", "tts_s": "Falar (TTS)", "total_s": "**Total**"}
    linhas = ["| Etapa | Segundos |", "| --- | --- |"]
    linhas += [f"| {rotulo} | {tempos.get(chave, 0):.2f} |" for chave, rotulo in nomes.items()]
    return "\n".join(linhas)


def responder(aceite: bool, audio: str | None, texto: str, assistente: Assistente | None, historico: list):
    historico = historico or []
    if not aceite:
        gr.Warning("Marque a caixa de consentimento antes de usar o assistente.")
        return historico, None, "", "", "", assistente, audio, texto
    if not audio and not (texto or "").strip():
        gr.Warning("Grave um áudio, envie um arquivo ou escreva a pergunta.")
        return historico, None, "", "", "", assistente, audio, texto
    if assistente is None:
        assistente = Assistente(base=BASE)

    try:
        if audio:
            resultado = assistente.responder_audio(audio)
        else:
            resultado = assistente.responder_texto(texto)
    except Exception:  # o cidadão nunca vê erro técnico
        log.exception("Falha inesperada no turno.")
        gr.Warning("Algo deu errado. Tente de novo em instantes.")
        return historico, None, "", "", "", assistente, None, ""

    if resultado.erro == "tts":
        gr.Info("A voz não está disponível agora. A resposta aparece em texto.")
    elif resultado.erro == "llm":
        gr.Warning("O assistente está fora do ar. Tente de novo em instantes.")

    historico = historico + [
        {"role": "user", "content": resultado.transcricao or "(não foi possível entender o áudio)"},
        {"role": "assistant", "content": resultado.resposta},
    ]
    fontes = ""
    if resultado.fontes:
        fontes = "**Fontes consultadas:** " + "; ".join(resultado.fontes)
    elif not resultado.erro:
        fontes = "Nenhum trecho da base foi usado nesta resposta."
    return (historico, resultado.audio, resultado.fala, fontes,
            _tabela_latencia(resultado.tempos), assistente, None, "")


def nova_conversa(assistente: Assistente | None):
    if assistente is not None:
        assistente.nova_conversa()
    return [], None, "", "", "", assistente


# ========================================================== ferramenta de corpus
def etapa_limpar(arquivos: list | None, colado: str, fonte: str, tamanho: int, mascarar: bool):
    documentos = [extrair_arquivo(caminho, fonte) for caminho in (arquivos or [])]
    if (colado or "").strip():
        documentos.append(extrair_texto_colado(colado, fonte=fonte))
    if not documentos:
        gr.Warning("Envie pelo menos um arquivo ou cole um texto.")
        return None, "", []
    registros, est, resumo = processar(documentos, tamanho_max=int(tamanho), mascarar=mascarar)
    estado = {"registros": registros, "estatisticas": est, "documentos": resumo, "qa": [], "dialogos": [],
              "descartados": 0, "falhas": 0}
    falhas = [d for d in resumo if d["erro"]]
    texto = [
        f"**{len(registros)} trechos** gerados a partir de {len(resumo) - len(falhas)} documento(s).",
        "",
        "| Indicador | Valor |", "| --- | --- |",
        f"| Caracteres antes e depois | {est.caracteres_antes} e {est.caracteres_depois} |",
        f"| Linhas de cabeçalho e rodapé removidas | {est.linhas_repetidas_removidas} |",
        f"| Palavras unidas (hífen no fim da linha) | {est.hifens_unidos} |",
        f"| Trechos duplicados removidos | {est.duplicatas_removidas} |",
        f"| Trechos curtos descartados | {est.trechos_curtos_descartados} |",
        f"| Dados pessoais mascarados | {sum(est.dados_mascarados.values())} |",
    ]
    if falhas:
        texto += ["", "**Arquivos com problema:**"] + [f"- {d['nome']}: {d['erro']}" for d in falhas]
    previa = [[r["documento"], r["text"]] for r in registros[:50]]
    return estado, "\n".join(texto), previa


def etapa_gerar(estado: dict | None, qa_por_trecho: int, max_trechos: int, com_dialogos: bool,
                progresso=gr.Progress()):
    if not estado or not estado.get("registros"):
        gr.Warning("Faça primeiro a etapa 1 (extrair e limpar).")
        return estado, [], ""
    resultado = gerar_corpus(
        estado["registros"], qa_por_trecho=int(qa_por_trecho), dialogos=com_dialogos,
        max_trechos=int(max_trechos) or None,
        progresso=lambda i, n: progresso(i / n, desc=f"Trecho {i} de {n}"))
    estado.update(qa=resultado.qa, dialogos=resultado.dialogos,
                  descartados=resultado.descartados, falhas=resultado.falhas_llm)
    tabela = [[True, item["pergunta"], item["resposta"], item["fonte"]] for item in resultado.qa]
    aviso = (f"**{len(resultado.qa)} perguntas** e **{len(resultado.dialogos)} diálogos** gerados. "
             f"{resultado.descartados} item(ns) descartado(s) na validação.")
    if resultado.falhas_llm:
        aviso += (f" O LLM falhou em {resultado.falhas_llm} trecho(s). "
                  "Confira se o Ollama está aberto ou se a chave da API está no arquivo .env.")
    return estado, tabela, aviso


def etapa_exportar(estado: dict | None, tabela: list | None):
    global BASE
    if not estado or not estado.get("registros"):
        gr.Warning("Faça primeiro a etapa 1 (extrair e limpar).")
        return "", None
    aprovados = []
    linhas = tabela or []
    for indice, item in enumerate(estado.get("qa", [])):
        if indice >= len(linhas):
            break
        aprovar, pergunta, resposta = linhas[indice][0], str(linhas[indice][1]).strip(), str(linhas[indice][2]).strip()
        if str(aprovar).lower() in ("true", "1") and pergunta and resposta:
            aprovados.append({**item, "pergunta": pergunta, "resposta": resposta})  # mantém a correção humana
    resumo = exportar(PASTA_CORPUS, estado["registros"], aprovados, estado.get("dialogos", []),
                      estado["estatisticas"], estado["documentos"], estado.get("descartados", 0),
                      estado.get("falhas", 0))
    BASE.carregar()  # o assistente passa a usar a nova base na hora
    arquivos = [str(PASTA_CORPUS / nome) for nome in resumo["arquivos"]] + [str(PASTA_CORPUS / "relatorio_corpus.md")]
    rejeitados = len(estado.get("qa", [])) - len(aprovados)
    texto = (f"Corpus gravados em `{PASTA_CORPUS}`. {len(aprovados)} perguntas aprovadas e {rejeitados} rejeitadas "
             "na revisão. A base do assistente foi atualizada.\n\n"
             + "\n".join(f"- {nome}: {valor}" for nome, valor in resumo["contagem"].items()))
    return texto, arquivos


# ===================================================================== interface
def construir() -> gr.Blocks:
    with gr.Blocks(title="Sentinela do Território") as demo:
        gr.Markdown("# Sentinela do Território\nOrientação por voz sobre queimadas, alertas e riscos em construções.")

        with gr.Tab("Assistente de voz"):
            gr.Markdown(prompts.AVISO_CONSENTIMENTO + ("\n\n" + prompts.AVISO_NUVEM if CONFIG.usa_nuvem else ""))
            aceite = gr.Checkbox(label="Li o aviso e concordo em usar o assistente", value=False)
            audio_entrada = gr.Audio(sources=["microphone", "upload"], type="filepath",
                                     label="Aperte para falar ou envie um áudio")
            texto_entrada = gr.Textbox(label="Ou escreva a sua pergunta", placeholder="Exemplo: vi fogo no mato, o que eu faço?")
            with gr.Row():
                enviar = gr.Button("Enviar", variant="primary")
                limpar = gr.Button("Nova conversa")
            audio_saida = gr.Audio(label="Resposta falada", autoplay=True, interactive=False)
            conversa = gr.Chatbot(label="Conversa em texto (transcrição e resposta)", height=320)
            fontes = gr.Markdown()
            with gr.Accordion("Detalhes técnicos: texto enviado para a voz e latência", open=False):
                fala = gr.Textbox(label="Texto adaptado para fala", interactive=False)
                latencia = gr.Markdown()
            estado_assistente = gr.State(None)

            saidas = [conversa, audio_saida, fala, fontes, latencia, estado_assistente, audio_entrada, texto_entrada]
            entradas = [aceite, audio_entrada, texto_entrada, estado_assistente, conversa]
            enviar.click(responder, entradas, saidas)
            texto_entrada.submit(responder, entradas, saidas)
            limpar.click(nova_conversa, [estado_assistente],
                         [conversa, audio_saida, fala, fontes, latencia, estado_assistente])

        with gr.Tab("Consulta às fontes (INPE e web)"):
            # Assistente conversacional com RAG (Generative AI). O índice só é carregado na primeira pergunta.
            from genai.aba import construir_aba_genai

            construir_aba_genai()

        with gr.Tab("Ferramenta de corpus"):
            gr.Markdown("Transforma documentos em três corpus: texto puro, perguntas e respostas, e conversacional. "
                        "Use somente documentos públicos. CPF, e-mail e telefone são mascarados.")
            estado_corpus = gr.State(None)

            gr.Markdown("### 1. Enviar, extrair e limpar")
            arquivos = gr.File(label="Documentos (PDF, DOCX, TXT, MD, HTML, CSV)", file_count="multiple", type="filepath")
            colado = gr.Textbox(label="Ou cole um texto", lines=4)
            fonte = gr.Textbox(label="Fonte dos documentos (endereço da página oficial)")
            with gr.Row():
                tamanho = gr.Slider(300, 1500, value=500, step=50, label="Tamanho máximo do trecho (caracteres)")
                mascarar = gr.Checkbox(label="Mascarar dados pessoais", value=True)
            botao_limpar = gr.Button("Extrair e limpar", variant="primary")
            resumo_limpeza = gr.Markdown()
            previa = gr.Dataframe(headers=["Documento", "Trecho"], label="Prévia dos trechos (até 50)",
                                  interactive=False, wrap=True, type="array")

            gr.Markdown("### 2. Gerar perguntas e diálogos com o LLM")
            with gr.Row():
                qa_por_trecho = gr.Slider(1, 5, value=2, step=1, label="Perguntas por trecho")
                max_trechos = gr.Number(value=20, precision=0, label="Máximo de trechos (0 = todos)")
                com_dialogos = gr.Checkbox(label="Gerar também os diálogos", value=True)
            botao_gerar = gr.Button("Gerar", variant="primary")
            resumo_geracao = gr.Markdown()

            gr.Markdown("### 3. Revisar e exportar\nDesmarque o que estiver errado ou corrija o texto direto na tabela.")
            revisao = gr.Dataframe(headers=["Aprovar", "Pergunta", "Resposta", "Fonte"],
                                   datatype=["bool", "str", "str", "str"], interactive=True, wrap=True,
                                   type="array", label="Revisão humana das perguntas e respostas")
            botao_exportar = gr.Button("Exportar os três corpus", variant="primary")
            resumo_exportacao = gr.Markdown()
            downloads = gr.File(label="Arquivos gerados", file_count="multiple", interactive=False)

            botao_limpar.click(etapa_limpar, [arquivos, colado, fonte, tamanho, mascarar],
                               [estado_corpus, resumo_limpeza, previa])
            botao_gerar.click(etapa_gerar, [estado_corpus, qa_por_trecho, max_trechos, com_dialogos],
                              [estado_corpus, revisao, resumo_geracao])
            botao_exportar.click(etapa_exportar, [estado_corpus, revisao], [resumo_exportacao, downloads])

        with gr.Tab("Sobre e privacidade"):
            gr.Markdown(
                "### O que este assistente faz\n"
                f"Orienta sobre {prompts.TEMA}, com base em documentos carregados pela ferramenta de corpus.\n\n"
                "### O que ele não faz\n"
                "- Não substitui o 193, o 199 nem outro serviço de emergência.\n"
                "- Não responde sobre saúde, questões jurídicas ou assuntos fora do tema.\n"
                "- Não inventa: quando a base não traz a resposta, ele diz que não sabe.\n\n"
                "### Seus dados\n"
                "- O áudio é apagado logo depois da transcrição.\n"
                "- O registro de latência guarda só tempos, sem o conteúdo da conversa.\n"
                "- A voz da resposta é sintética. Não há clonagem de voz.\n\n"
                "### Configuração atual\n"
                f"- LLM: `{CONFIG.llm_provider}`\n- STT: Whisper `{CONFIG.stt_model}`\n- TTS: `{CONFIG.tts_engine}`\n"
                f"- Trechos na base: {len(BASE.registros)}\n"
            )
    return demo


if __name__ == "__main__":
    construir().launch(
        server_name=os.getenv("GRADIO_HOST", "127.0.0.1"),
        server_port=int(os.getenv("GRADIO_PORT", "7860")),
        share=os.getenv("GRADIO_SHARE", "0") == "1",
    )
