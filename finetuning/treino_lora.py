# Sentinela do Território, Global Solution CitizenTech
# GEANDRO (RM 562316) | LUCAS VERO (RM 564202) | ROBERTO EDUARDO (RM 564537)

"""Ajuste (fine-tuning) de um LLM pequeno com LoRA, usando os corpus gerados.

Feito para o Google Colab com GPU T4. Exemplo:
    pip install -r requirements-finetuning.txt
    python finetuning/treino_lora.py --corpus dados/corpus --saida finetuning/saida --epocas 3

Entrada: perguntas_respostas_{treino,validacao}.jsonl e conversacional_{treino,validacao}.jsonl
Saída:   adaptador LoRA em --saida. Para usar no assistente, defina no .env:
    LLM_PROVIDER=hf
    HF_MODEL=<mesmo modelo base>
    HF_LORA=finetuning/saida

Os arquivos *_teste.jsonl NÃO são lidos aqui. Eles ficam reservados para a avaliação.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from assistente import prompts  # noqa: E402

SEM_TRECHO = "(nenhum trecho encontrado na base)"


def _usuario(contexto: str, pergunta: str) -> str:
    """Mesmo formato que o assistente usa na hora de responder."""
    trechos = f"[1] {contexto}" if contexto else SEM_TRECHO
    return f"TRECHOS:\n{trechos}\n\nPERGUNTA: {pergunta}"


def carregar(pasta: Path, parte: str) -> list[list[dict]]:
    """Lê os dois corpus de uma parte (treino ou validacao) como listas de mensagens."""
    conversas: list[list[dict]] = []
    qa = pasta / f"perguntas_respostas_{parte}.jsonl"
    if qa.exists():
        for linha in qa.read_text(encoding="utf-8").splitlines():
            item = json.loads(linha)
            conversas.append([
                {"role": "system", "content": prompts.SYSTEM_PROMPT},
                {"role": "user", "content": _usuario(item.get("contexto", ""), item["pergunta"])},
                {"role": "assistant", "content": item["resposta"]},
            ])
    dialogos = pasta / f"conversacional_{parte}.jsonl"
    if dialogos.exists():
        for linha in dialogos.read_text(encoding="utf-8").splitlines():
            item = json.loads(linha)
            mensagens = []
            for mensagem in item["messages"]:
                if mensagem["role"] == "user":
                    mensagens.append({"role": "user", "content": _usuario(item.get("contexto", ""), mensagem["content"])})
                else:
                    mensagens.append(mensagem)
            conversas.append(mensagens)
    return conversas


def main() -> int:
    parser = argparse.ArgumentParser(description="Ajusta um LLM pequeno com LoRA.")
    parser.add_argument("--corpus", default="dados/corpus")
    parser.add_argument("--saida", default="finetuning/saida")
    parser.add_argument("--modelo", default="Qwen/Qwen2.5-0.5B-Instruct")
    parser.add_argument("--epocas", type=float, default=3.0)
    parser.add_argument("--lote", type=int, default=4)
    parser.add_argument("--taxa", type=float, default=2e-4)
    parser.add_argument("--max-tokens", type=int, default=1024)
    args = parser.parse_args()

    import torch
    from datasets import Dataset
    from peft import LoraConfig, get_peft_model
    from transformers import (AutoModelForCausalLM, AutoTokenizer, DataCollatorForLanguageModeling,
                              Trainer, TrainingArguments)

    pasta = Path(args.corpus)
    treino, validacao = carregar(pasta, "treino"), carregar(pasta, "validacao")
    if not treino:
        print(f"Nenhum exemplo de treino em {pasta}. Rode antes a ferramenta de corpus.")
        return 1
    print(f"Exemplos de treino: {len(treino)}. Exemplos de validação: {len(validacao)}.")

    tokenizador = AutoTokenizer.from_pretrained(args.modelo)
    if tokenizador.pad_token is None:
        tokenizador.pad_token = tokenizador.eos_token
    tem_gpu = torch.cuda.is_available()
    modelo = AutoModelForCausalLM.from_pretrained(
        args.modelo, torch_dtype=torch.float16 if tem_gpu else torch.float32,
        device_map="auto" if tem_gpu else None)
    modelo = get_peft_model(modelo, LoraConfig(
        r=16, lora_alpha=32, lora_dropout=0.05, task_type="CAUSAL_LM",
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj"]))
    modelo.print_trainable_parameters()

    def preparar(conversas: list[list[dict]]) -> Dataset:
        textos = [tokenizador.apply_chat_template(c, tokenize=False) for c in conversas]
        dados = Dataset.from_dict({"text": textos})
        return dados.map(lambda lote: tokenizador(lote["text"], truncation=True, max_length=args.max_tokens),
                         batched=True, remove_columns=["text"])

    argumentos = TrainingArguments(
        output_dir=args.saida, num_train_epochs=args.epocas, per_device_train_batch_size=args.lote,
        gradient_accumulation_steps=4, learning_rate=args.taxa, logging_steps=5, save_strategy="no",
        eval_strategy="epoch" if validacao else "no", fp16=tem_gpu, report_to="none")
    treinador = Trainer(
        model=modelo, args=argumentos, train_dataset=preparar(treino),
        eval_dataset=preparar(validacao) if validacao else None,
        data_collator=DataCollatorForLanguageModeling(tokenizador, mlm=False))
    resultado = treinador.train()

    modelo.save_pretrained(args.saida)
    tokenizador.save_pretrained(args.saida)
    registro = {"modelo_base": args.modelo, "epocas": args.epocas, "lote": args.lote, "taxa_de_aprendizado": args.taxa,
                "lora": {"r": 16, "alpha": 32, "dropout": 0.05}, "exemplos_treino": len(treino),
                "exemplos_validacao": len(validacao), "perda_final_treino": resultado.training_loss}
    if validacao:
        registro["perda_validacao"] = treinador.evaluate().get("eval_loss")
    Path(args.saida, "registro_do_treino.json").write_text(json.dumps(registro, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(registro, ensure_ascii=False, indent=2))
    print(f"Adaptador gravado em {args.saida}. Copie os números de registro_do_treino.json para o relatório.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
