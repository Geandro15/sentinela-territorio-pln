# Sentinela do Território, Global Solution CitizenTech
# GEANDRO (RM 562316) | LUCAS VERO (RM 564202) | ROBERTO EDUARDO (RM 564537)

"""Memória da conversa: guarda os últimos turnos para perguntas de continuação."""
from __future__ import annotations


class Memoria:
    def __init__(self, max_turnos: int = 6):
        self.max_turnos = max_turnos
        self._turnos: list[tuple[str, str]] = []  # (pergunta, resposta)

    def adicionar(self, pergunta: str, resposta: str) -> None:
        self._turnos.append((pergunta, resposta))
        self._turnos = self._turnos[-self.max_turnos:]

    def mensagens(self) -> list[dict]:
        """Histórico no formato de mensagens do LLM."""
        saida: list[dict] = []
        for pergunta, resposta in self._turnos:
            saida.append({"role": "user", "content": pergunta})
            saida.append({"role": "assistant", "content": resposta})
        return saida

    def ultima_pergunta(self) -> str:
        return self._turnos[-1][0] if self._turnos else ""

    def limpar(self) -> None:
        self._turnos.clear()

    def __len__(self) -> int:
        return len(self._turnos)
