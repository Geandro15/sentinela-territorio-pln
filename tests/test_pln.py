# Sentinela do Território, Global Solution CitizenTech
# GEANDRO (RM 562316) | LUCAS VERO (RM 564202) | ROBERTO EDUARDO (RM 564537)

"""Testes automáticos que rodam sem rede, sem GPU e sem modelo (LLM simulado).

    python -m pytest -q
"""
import dataclasses
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from assistente.adaptacao import adaptar_para_fala  # noqa: E402
from assistente.llm import ErroLLM, conversar, extrair_json  # noqa: E402
from assistente.memoria import Memoria  # noqa: E402
from assistente.pipeline import Assistente, detectar_emergencia  # noqa: E402
from assistente.rag import BaseConhecimento  # noqa: E402
from config import CONFIG  # noqa: E402
from corpus.exportacao import dividir, exportar  # noqa: E402
from corpus.extracao import extrair_arquivo, extrair_texto_colado  # noqa: E402
from corpus.geracao import dialogos_de_recusa, gerar_corpus, resposta_sustentada  # noqa: E402
from corpus.limpeza import Estatisticas, limpar_texto, mascarar_dados_pessoais, segmentar  # noqa: E402
from corpus.pipeline import processar  # noqa: E402

MOCK = dataclasses.replace(CONFIG, llm_provider="mock")
TEXTO = ("Ao ver fogo no mato, afaste-se e ligue 193. Não tente apagar sozinho.\n\n"
         "A Defesa Civil atende pelo telefone 199. Para receber alertas, envie o CEP para 40199.")


# ------------------------------------------------------------------- limpeza
def test_une_palavra_quebrada_por_hifen():
    est = Estatisticas()
    assert "prevenção" in limpar_texto("A preven-\nção evita queimadas.", est)
    assert est.hifens_unidos == 1


def test_mascara_dados_pessoais_e_preserva_numero_de_emergencia():
    texto = mascarar_dados_pessoais("CPF 123.456.789-09, maria@email.com, (11) 91234-5678. Ligue 193.")
    assert "[CPF]" in texto and "[EMAIL]" in texto and "[TELEFONE]" in texto
    assert "193" in texto and "123.456" not in texto


def test_remove_cabecalho_repetido_entre_paginas():
    paginas = "\f".join(
        f"Prefeitura Municipal\nManual de prevenção\nConteúdo da página {i} com texto próprio.\n"
        f"Mais uma linha de conteúdo, número {i}.\nOutra linha do miolo.\nDefesa Civil\nPágina {i}"
        for i in range(1, 6))
    limpo = limpar_texto(paginas)
    assert "Prefeitura Municipal" not in limpo and "Conteúdo da página 3" in limpo


def test_segmentacao_remove_paragrafo_duplicado():
    est = Estatisticas()
    paragrafo = "Feche portas e janelas quando houver fumaça de queimada perto de casa."
    trechos = segmentar(f"{paragrafo}\n\n{paragrafo}\n\nOutro parágrafo, diferente do primeiro, com mais de quarenta letras.", est)
    assert est.duplicatas_removidas == 1
    assert sum(t.count("Feche portas") for t in trechos) == 1


def test_arquivo_ausente_ou_nao_suportado_nao_interrompe(tmp_path):
    assert extrair_arquivo(tmp_path / "nao_existe.pdf").erro
    estranho = tmp_path / "dados.xyz"
    estranho.write_text("x")
    assert "não suportado" in extrair_arquivo(estranho).erro
    registros, _, resumo = processar([extrair_arquivo(estranho), extrair_texto_colado(TEXTO, fonte="teste")])
    assert registros and resumo[0]["erro"] and not resumo[1]["erro"]


# ----------------------------------------------------------- geração e exportação
def test_resposta_sustentada_barra_invencao():
    trecho = "A Defesa Civil atende pelo telefone 199."
    assert resposta_sustentada("A Defesa Civil atende pelo 199.", trecho)
    assert not resposta_sustentada("O prefeito inaugura a ponte amanhã cedo.", trecho)


def test_extrair_json_com_texto_em_volta():
    assert extrair_json('Claro! ```json\n{"itens": [{"pergunta": "a", "resposta": "b"}]}\n``` Pronto.')["itens"]
    assert extrair_json("sem json") is None


def test_gera_e_exporta_os_tres_corpus(tmp_path):
    registros, est, resumo = processar([extrair_texto_colado(TEXTO, fonte="teste")], tamanho_max=120)
    geracao = gerar_corpus(registros, cfg=MOCK)
    assert geracao.qa and len(geracao.dialogos) >= len(dialogos_de_recusa())
    saida = exportar(tmp_path, registros, geracao.qa, geracao.dialogos, est, resumo)
    assert (tmp_path / "texto_puro.jsonl").exists() and (tmp_path / "relatorio_corpus.md").exists()
    for nome in ("perguntas_respostas", "conversacional"):
        assert sum(saida["contagem"][f"{nome}_{parte}"] for parte in ("treino", "validacao", "teste")) > 0
    primeira = json.loads((tmp_path / "conversacional_treino.jsonl").read_text(encoding="utf-8").splitlines()[0])
    assert primeira["messages"][0]["role"] == "system"


def test_divisao_nao_repete_exemplo_entre_treino_e_teste():
    partes = dividir(list(range(50)))
    assert not set(partes["treino"]) & set(partes["teste"])
    assert sum(len(p) for p in partes.values()) == 50


# ------------------------------------------------------------------ assistente
def test_adaptacao_para_fala():
    fala = adaptar_para_fala("**Ligue 193** agora! Veja https://exemplo.gov.br 😀")
    assert "um nove três" in fala and "*" not in fala and "http" not in fala and "😀" not in fala
    assert "dez de novembro" in adaptar_para_fala("A vistoria é em 10/11/2026.")
    assert "por cento" in adaptar_para_fala("Aumento de 12%.")
    assert len(adaptar_para_fala("Um. Dois. Três. Quatro. Cinco. Seis.", max_frases=3).split(". ")) == 3


def test_memoria_guarda_so_os_ultimos_turnos():
    memoria = Memoria(max_turnos=2)
    for i in range(4):
        memoria.adicionar(f"p{i}", f"r{i}")
    assert len(memoria) == 2 and memoria.ultima_pergunta() == "p3"
    assert [m["role"] for m in memoria.mensagens()] == ["user", "assistant", "user", "assistant"]


def _assistente(tmp_path) -> Assistente:
    registros, est, resumo = processar([extrair_texto_colado(TEXTO, fonte="fonte-teste")], tamanho_max=120)
    exportar(tmp_path, registros, [], [], est, resumo)
    cfg = dataclasses.replace(MOCK, pasta_logs=tmp_path / "logs")
    return Assistente(cfg, BaseConhecimento(tmp_path / "texto_puro.jsonl"))


def test_responde_com_fonte_e_registra_latencia(tmp_path):
    assistente = _assistente(tmp_path)
    resultado = assistente.responder_texto("Vi fogo no mato, o que faço?", falar=False)
    assert "193" in resultado.resposta and resultado.fontes == ["fonte-teste"]
    assert "um nove três" in resultado.fala
    assert (tmp_path / "logs" / "latencia.csv").exists()


def test_sem_evidencia_o_assistente_nao_inventa(tmp_path):
    resultado = _assistente(tmp_path).responder_texto("Qual o resultado do jogo de ontem?", falar=False)
    assert not resultado.fontes and "Não tenho essa informação" in resultado.resposta


def test_emergencia_sempre_traz_o_193(tmp_path):
    assert detectar_emergencia("Socorro, a casa está pegando fogo")
    resultado = _assistente(tmp_path).responder_texto("Socorro, tem alguém preso aqui", falar=False)
    assert resultado.emergencia and "193" in resultado.resposta


def test_llm_fora_do_ar_tem_caminho_seguro(tmp_path):
    assistente = _assistente(tmp_path)
    assistente.cfg = dataclasses.replace(assistente.cfg, llm_provider="ollama", ollama_url="http://127.0.0.1:9", llm_timeout=1)
    import assistente.llm as llm
    llm.time.sleep = lambda _s: None  # sem espera entre as tentativas durante o teste
    resultado = assistente.responder_texto("Qual é o telefone da Defesa Civil?", falar=False)
    assert resultado.erro == "llm" and "193" in resultado.resposta


def test_provedor_invalido_gera_erro_claro():
    try:
        conversar([{"role": "user", "content": "oi"}], dataclasses.replace(CONFIG, llm_provider="xyz"))
    except ErroLLM as exc:
        assert "LLM_PROVIDER" in str(exc)
    else:
        raise AssertionError("deveria falhar")
