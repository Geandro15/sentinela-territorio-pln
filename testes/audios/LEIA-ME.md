# Áudios de teste do STT

O enunciado pede 20 áudios gravados pelo grupo, com pelo menos 3 vozes diferentes e 5 com ruído de fundo.

1. Grave cada áudio em WAV, MP3 ou M4A e salve nesta pasta (exemplo: `a01.wav`).
2. Preencha uma linha por áudio em `manifesto.csv`:

| Coluna | O que escrever |
| --- | --- |
| arquivo | nome do arquivo, como `a01.wav` |
| referencia | a frase exata que foi falada |
| locutor | apelido de quem falou, sem nome completo |
| grupo | perfil da voz, como `homem_adulto`, `mulher_adulta`, `pessoa_idosa` |
| ruido | `sim` ou `nao` |

A coluna `grupo` alimenta a análise de viés do STT, que está no barema. Inclua vozes de perfis diferentes
(sexo, idade, sotaque). Peça consentimento a quem gravar e não use nomes completos.

Sugestão de frases: use as perguntas de `testes/perguntas.csv`, que são as frases que o cidadão falaria.
