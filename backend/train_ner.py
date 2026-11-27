"""
Fine-tune DistilBERT for FieldScribe clinical NER (token classification, BIO tags).

    pip install -r requirements-ml.txt
    python train_ner.py                       # distilbert-base-uncased, ~10-25 min on a laptop CPU
    python train_ner.py --epochs 2 --train-n 4000   # quicker
    python train_ner.py --tiny                # 1-minute smoke test with a tiny model, no download

The model is saved to models/ner-distilbert/ together with metrics.json. FieldScribe
loads it automatically on the next start and runs it alongside the rule engine.
"""
from __future__ import annotations

import argparse
import json
import random
import sys
import time
from pathlib import Path

import torch
from torch.utils.data import DataLoader

sys.path.insert(0, str(Path(__file__).resolve().parent))
from app.nlp.ner_data import LABELS, L2I, generate_corpus  # noqa: E402

HERE = Path(__file__).resolve().parent


def build_tiny(texts, out: Path):
    from tokenizers import Tokenizer, models, normalizers, pre_tokenizers, trainers
    from transformers import DistilBertConfig, PreTrainedTokenizerFast, AutoModelForTokenClassification
    tok = Tokenizer(models.WordPiece(unk_token="[UNK]"))
    tok.normalizer = normalizers.BertNormalizer(lowercase=True)
    tok.pre_tokenizer = pre_tokenizers.Sequence([pre_tokenizers.BertPreTokenizer(), pre_tokenizers.Digits(individual_digits=False)])
    tok.train_from_iterator(texts, trainers.WordPieceTrainer(vocab_size=3000, special_tokens=["[PAD]", "[UNK]", "[CLS]", "[SEP]", "[MASK]"]))
    from tokenizers import processors
    tok.post_processor = processors.TemplateProcessing(single="[CLS] $A [SEP]", special_tokens=[("[CLS]", tok.token_to_id("[CLS]")), ("[SEP]", tok.token_to_id("[SEP]"))])
    hf = PreTrainedTokenizerFast(tokenizer_object=tok, unk_token="[UNK]", pad_token="[PAD]", cls_token="[CLS]", sep_token="[SEP]", mask_token="[MASK]")
    cfg = DistilBertConfig(vocab_size=hf.vocab_size, dim=128, hidden_dim=256, n_layers=2, n_heads=2, max_position_embeddings=128,
                           num_labels=len(LABELS), id2label=dict(enumerate(LABELS)), label2id=L2I)
    model = AutoModelForTokenClassification.from_config(cfg)
    return hf, model


def encode(tok, examples, max_len):
    enc = tok([e["text"] for e in examples], truncation=True, max_length=max_len, padding="max_length", return_offsets_mapping=True)
    labels = []
    for i, ex in enumerate(examples):
        lab = []
        for (s, e), tid in zip(enc["offset_mapping"][i], enc["input_ids"][i]):
            if s == e:  # special / padding
                lab.append(-100)
                continue
            tag = "O"
            for ss, se, l in ex["spans"]:
                if s >= ss and e <= se:
                    tag = ("B-" if s == ss else "I-") + l
                    break
                if s < se and e > ss:  # partial overlap: treat as inside
                    tag = ("B-" if s <= ss else "I-") + l
                    break
            lab.append(L2I[tag])
        labels.append(lab)
    return torch.tensor(enc["input_ids"]), torch.tensor(enc["attention_mask"]), torch.tensor(labels), enc["offset_mapping"]


def spans_from_tags(tags, offsets):
    spans, cur = [], None
    for t, (s, e) in zip(tags, offsets):
        if s == e:
            continue
        lab = LABELS[t]
        if lab == "O":
            if cur:
                spans.append(tuple(cur)); cur = None
            continue
        typ = lab[2:]
        if lab.startswith("B-") or not cur or cur[2] != typ:
            if cur:
                spans.append(tuple(cur))
            cur = [s, e, typ]
        else:
            cur[1] = e
    if cur:
        spans.append(tuple(cur))
    return spans


def evaluate(model, tok, examples, max_len, device):
    model.eval()
    ids, mask, _, offs = encode(tok, examples, max_len)
    per = {}
    with torch.no_grad():
        for i in range(0, len(examples), 64):
            logits = model(input_ids=ids[i:i + 64].to(device), attention_mask=mask[i:i + 64].to(device)).logits
            pred = logits.argmax(-1).cpu().tolist()
            for j, p in enumerate(pred):
                ex = examples[i + j]
                ps = set(spans_from_tags(p, offs[i + j]))
                gs = {(s, e, l) for s, e, l in ex["spans"]}
                for l in {x[2] for x in ps | gs}:
                    d = per.setdefault(l, [0, 0, 0])
                    d[0] += len({x for x in ps if x[2] == l} & {x for x in gs if x[2] == l})
                    d[1] += len({x for x in ps if x[2] == l} - gs)
                    d[2] += len({x for x in gs if x[2] == l} - ps)
    out = {}
    T = [0, 0, 0]
    for l, (tp, fp, fn) in sorted(per.items()):
        p = tp / (tp + fp) if tp + fp else 0
        r = tp / (tp + fn) if tp + fn else 0
        out[l] = {"precision": round(p, 4), "recall": round(r, 4), "f1": round(2 * p * r / (p + r), 4) if p + r else 0, "support": tp + fn}
        T = [T[0] + tp, T[1] + fp, T[2] + fn]
    p = T[0] / (T[0] + T[1]) if T[0] + T[1] else 0
    r = T[0] / (T[0] + T[2]) if T[0] + T[2] else 0
    out["micro"] = {"precision": round(p, 4), "recall": round(r, 4), "f1": round(2 * p * r / (p + r), 4) if p + r else 0}
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="distilbert-base-uncased")
    ap.add_argument("--tiny", action="store_true", help="tiny local model for a fast offline smoke test")
    ap.add_argument("--train-n", type=int, default=6000)
    ap.add_argument("--test-n", type=int, default=800)
    ap.add_argument("--epochs", type=int, default=3)
    ap.add_argument("--batch", type=int, default=32)
    ap.add_argument("--lr", type=float, default=5e-5)
    ap.add_argument("--max-len", type=int, default=96)
    ap.add_argument("--out", default=str(HERE / "models" / "ner-distilbert"))
    a = ap.parse_args()
    random.seed(13); torch.manual_seed(13)
    train = generate_corpus(a.train_n, "train")
    test = generate_corpus(a.test_n, "test")
    device = "cuda" if torch.cuda.is_available() else "cpu"
    if a.tiny:
        tok, model = build_tiny([e["text"] for e in train], Path(a.out))
        a.lr = max(a.lr, 3e-3)
        base = "tiny-distilbert (local)"
    else:
        from transformers import AutoTokenizer, AutoModelForTokenClassification
        print(f"Downloading / loading {a.base} ...")
        tok = AutoTokenizer.from_pretrained(a.base)
        model = AutoModelForTokenClassification.from_pretrained(a.base, num_labels=len(LABELS), id2label=dict(enumerate(LABELS)), label2id=L2I)
        base = a.base
    model.to(device)
    ids, mask, labels, _ = encode(tok, train, a.max_len)
    dl = DataLoader(list(zip(ids, mask, labels)), batch_size=a.batch, shuffle=True)
    opt = torch.optim.AdamW(model.parameters(), lr=a.lr, weight_decay=0.01)
    steps = len(dl) * a.epochs
    sched = torch.optim.lr_scheduler.LambdaLR(opt, lambda s: min(1.0, (s + 1) / max(1, steps * 0.06)) * max(0.0, (steps - s) / steps))
    print(f"Training {base} on {len(train)} sentences ({steps} steps, device={device})")
    t0 = time.time()
    step = 0
    for ep in range(a.epochs):
        model.train()
        tot = 0.0
        for b_ids, b_mask, b_lab in dl:
            out = model(input_ids=b_ids.to(device), attention_mask=b_mask.to(device), labels=b_lab.to(device))
            out.loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            opt.step(); sched.step(); opt.zero_grad()
            tot += out.loss.item(); step += 1
            if step % 50 == 0:
                print(f"  epoch {ep + 1} step {step}/{steps} loss {out.loss.item():.4f}")
        print(f"epoch {ep + 1}: mean loss {tot / len(dl):.4f} ({time.time() - t0:.0f}s)")
    metrics = evaluate(model, tok, test, a.max_len, device)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    model.save_pretrained(out)
    tok.save_pretrained(out)
    meta = {"base": base, "train_sentences": len(train), "test_sentences": len(test), "epochs": a.epochs,
            "train_seconds": round(time.time() - t0), "labels": LABELS, "test_span_metrics": metrics,
            "max_len": a.max_len, "note": "test split uses a different seed, unseen real brands and harsher corruption"}
    (out / "metrics.json").write_text(json.dumps(meta, indent=2))
    print(json.dumps(metrics["micro"]), "\nSaved to", out)


if __name__ == "__main__":
    main()
