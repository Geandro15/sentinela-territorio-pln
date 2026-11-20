# Sentinela do Território, Global Solution CitizenTech
# GEANDRO (RM 562316) | LUCAS VERO (RM 564202) | ROBERTO EDUARDO (RM 564537)

"""Limpeza, normalização, mascaramento de dados pessoais e segmentação."""
from __future__ import annotations

import hashlib
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass, field

# ---------------------------------------------------------------- dados pessoais
RE_CPF = re.compile(r"\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b")
RE_EMAIL = re.compile(r"\b[\w.+-]+@[\w-]+(?:\.[\w-]+)+\b")
# Telefones com DDD ou com 8 ou 9 dígitos. Números curtos de emergência
# (193, 199, 190) não são mascarados.
RE_TELEFONE = re.compile(r"(?<!\d)(?:\+?55\s?)?(?:\(?\d{2}\)?[\s-]?)?9?\d{4}[\s-]?\d{4}(?!\d)")


@dataclass
class Estatisticas:
    caracteres_antes: int = 0
    caracteres_depois: int = 0
    linhas_repetidas_removidas: int = 0
    hifens_unidos: int = 0
    dados_mascarados: dict = field(default_factory=lambda: {"cpf": 0, "email": 0, "telefone": 0})
    trechos_gerados: int = 0
    trechos_curtos_descartados: int = 0
    duplicatas_removidas: int = 0

    def somar(self, outra: "Estatisticas") -> None:
        for campo in ("caracteres_antes", "caracteres_depois", "linhas_repetidas_removidas",
                      "hifens_unidos", "trechos_gerados", "trechos_curtos_descartados",
                      "duplicatas_removidas"):
            setattr(self, campo, getattr(self, campo) + getattr(outra, campo))
        for chave, valor in outra.dados_mascarados.items():
            self.dados_mascarados[chave] += valor


def mascarar_dados_pessoais(texto: str, est: Estatisticas | None = None) -> str:
    """Troca CPF, e-mail e telefone por marcadores. Exigência de LGPD."""
    est = est or Estatisticas()

    def _troca(padrao: re.Pattern, marcador: str, chave: str, entrada: str) -> str:
        saida, n = padrao.subn(marcador, entrada)
        est.dados_mascarados[chave] += n
        return saida

    texto = _troca(RE_CPF, "[CPF]", "cpf", texto)
    texto = _troca(RE_EMAIL, "[EMAIL]", "email", texto)
    texto = _troca(RE_TELEFONE, "[TELEFONE]", "telefone", texto)
    return texto


def _remover_linhas_repetidas(texto: str, est: Estatisticas) -> str:
    """Remove cabeçalhos e rodapés: linhas curtas, no topo ou no pé da página,
    que se repetem na maioria das páginas (ignorando os números)."""
    paginas = texto.split("\f")
    if len(paginas) < 3:
        return texto.replace("\f", "\n")
    def _chave(linha: str) -> str:
        return re.sub(r"\d+", "#", linha.strip())

    def _bordas(pagina: str) -> list[int]:
        """Índices das duas primeiras e das duas últimas linhas com texto da página."""
        indices = [i for i, l in enumerate(pagina.splitlines()) if l.strip()]
        return indices[:2] + indices[-2:] if len(indices) > 4 else []

    contagem: Counter[str] = Counter()
    for pagina in paginas:
        linhas = pagina.splitlines()
        contagem.update({_chave(linhas[i]) for i in _bordas(pagina) if len(linhas[i].strip()) <= 80})
    limite = max(3, int(len(paginas) * 0.6))
    repetidas = {l for l, n in contagem.items() if n >= limite}
    saida = []
    for pagina in paginas:
        linhas = pagina.splitlines()
        bordas = set(_bordas(pagina))
        for indice, linha in enumerate(linhas):
            if indice in bordas and _chave(linha) in repetidas:
                est.linhas_repetidas_removidas += 1
                continue
            saida.append(linha)
        saida.append("")
    return "\n".join(saida)


def limpar_texto(texto: str, est: Estatisticas | None = None, mascarar: bool = True) -> str:
    """Aplica toda a limpeza e devolve texto com um parágrafo por bloco."""
    est = est or Estatisticas()
    est.caracteres_antes += len(texto)

    texto = unicodedata.normalize("NFC", texto)
    texto = texto.replace("\r\n", "\n").replace("\r", "\n")
    texto = _remover_linhas_repetidas(texto, est)
    # caracteres de controle e espaços especiais
    texto = "".join(c if c in "\n\t" or unicodedata.category(c)[0] != "C" else " " for c in texto)
    texto = texto.replace(" ", " ").replace("​", "")
    # aspas e traços padronizados
    for origem, destino in {"“": '"', "”": '"', "„": '"', "‘": "'", "’": "'", "–": "-", ", ": "-", "…": "..."}.items():
        texto = texto.replace(origem, destino)
    # palavras quebradas por hífen no fim da linha: "preven-\nção" -> "prevenção"
    texto, n = re.subn(r"(\w)-\n(\w)", r"\1\2", texto)
    est.hifens_unidos += n
    # linhas soltas com apenas o número da página
    texto = re.sub(r"(?m)^\s*(?:p[áa]gina\s*)?\d{1,4}(?:\s*(?:/|de)\s*\d{1,4})?\s*$", "", texto, flags=re.I)
    # quebra simples dentro do parágrafo vira espaço; linha em branco separa parágrafos
    texto = re.sub(r"[ \t]+", " ", texto)
    texto = re.sub(r" ?\n ?", "\n", texto)
    texto = re.sub(r"\n{2,}", "\n\n", texto)
    texto = re.sub(r"(?<!\n)\n(?!\n)", " ", texto)
    texto = re.sub(r" {2,}", " ", texto).strip()
    if mascarar:
        texto = mascarar_dados_pessoais(texto, est)

    est.caracteres_depois += len(texto)
    return texto


def _chave_duplicata(trecho: str) -> str:
    base = re.sub(r"\W+", " ", trecho.lower()).strip()
    return hashlib.md5(base.encode("utf-8")).hexdigest()


def segmentar(texto: str, est: Estatisticas | None = None, tamanho_max: int = 500,
              tamanho_min: int = 40, vistos: set[str] | None = None) -> list[str]:
    """Divide o texto limpo em trechos por parágrafo.

    Parágrafos pequenos são agrupados até ``tamanho_max`` caracteres e
    parágrafos grandes são divididos por frase. Parágrafos duplicados (mesmo
    texto, ignorando caixa e pontuação) e trechos muito curtos são descartados.
    """
    est = est or Estatisticas()
    vistos = vistos if vistos is not None else set()
    unidades: list[str] = []
    for paragrafo in (p.strip() for p in texto.split("\n\n")):
        if not paragrafo:
            continue
        # parágrafo repetido (no mesmo documento ou em outro) entra uma vez só
        chave = _chave_duplicata(paragrafo)
        if len(paragrafo) >= tamanho_min and chave in vistos:
            est.duplicatas_removidas += 1
            continue
        vistos.add(chave)
        if len(paragrafo) <= tamanho_max:
            unidades.append(paragrafo)
        else:
            unidades.extend(f.strip() for f in re.split(r"(?<=[.!?])\s+", paragrafo) if f.strip())

    trechos, atual = [], ""
    for unidade in unidades:
        if atual and len(atual) + len(unidade) + 2 > tamanho_max:
            trechos.append(atual)
            atual = unidade
        elif atual:
            # títulos e linhas sem ponto final ganham uma pausa antes do texto seguinte
            atual += (" " if atual[-1] in ".!?:" else ". ") + unidade
        else:
            atual = unidade
    if atual:
        trechos.append(atual)

    saida = []
    for trecho in trechos:
        if len(trecho) < tamanho_min:
            est.trechos_curtos_descartados += 1
            continue
        saida.append(trecho)
    est.trechos_gerados += len(saida)
    return saida
