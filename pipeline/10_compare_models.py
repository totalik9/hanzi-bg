"""Compare NLLB-200 with M2M-100 on the same Bulgarian senses.

The project translates the English glosses into Bulgarian with
facebook/nllb-200-distilled-600M. This script puts the same senses
through facebook/m2m100_418M and writes the two outputs side by side,
so the choice of model can be made on evidence instead of on the model
card.

Usage:
    python pipeline/10_compare_models.py --limit 200 --out data/model_compare.json
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "data" / "bg_sense_cache.json"
TRANSLATIONS = ROOT / "data" / "bg_translations.json"
OUT = ROOT / "data" / "model_compare.json"

NLLB_MODEL = "facebook/nllb-200-distilled-600M"
M2M_MODEL = "facebook/m2m100_418M"

NLLB_SRC = "eng_Latn"
NLLB_TGT = "bul_Cyrl"
M2M_SRC = "en"
M2M_TGT = "bg"


def load_senses(limit: int) -> list[str]:
    """The English senses that the project actually needs translated.

    The cache holds every sense ever seen; the translations file holds
    the ones the vocabulary uses. Taking the senses from the latter
    keeps the comparison honest: it is the same work the pipeline does.
    """
    senses: list[str] = []
    if TRANSLATIONS.exists():
        with TRANSLATIONS.open(encoding="utf-8") as fh:
            translations = json.load(fh)
        for value in translations.values():
            english = value.get("gloss_en")
            if not english:
                continue
            for part in english.split("/"):
                part = part.strip()
                if part:
                    senses.append(part)
    if not senses and CACHE.exists():
        with CACHE.open(encoding="utf-8") as fh:
            senses = list(json.load(fh))
    # Keep the order but drop the repeats.
    seen: set[str] = set()
    unique: list[str] = []
    for sense in senses:
        if sense not in seen:
            seen.add(sense)
            unique.append(sense)
    return unique[:limit]


def run_nllb(senses: list[str], batch_size: int = 8) -> list[str]:
    from transformers import AutoTokenizer, AutoModelForSeq2SeqLM

    tokenizer = AutoTokenizer.from_pretrained(NLLB_MODEL)
    model = AutoModelForSeq2SeqLM.from_pretrained(NLLB_MODEL)
    tokenizer.src_lang = NLLB_SRC

    out: list[str] = []
    for i in range(0, len(senses), batch_size):
        chunk = senses[i : i + batch_size]
        batch = tokenizer(chunk, return_tensors="pt", padding=True, truncation=True)
        forced = tokenizer.convert_tokens_to_ids(NLLB_TGT)
        generated = model.generate(**batch, forced_bos_token_id=forced, max_new_tokens=96)
        out.extend(tokenizer.batch_decode(generated, skip_special_tokens=True))
    return out


def run_m2m(senses: list[str], batch_size: int = 8) -> list[str]:
    from transformers import M2M100ForConditionalGeneration, M2M100Tokenizer

    tokenizer = M2M100Tokenizer.from_pretrained(M2M_MODEL)
    model = M2M100ForConditionalGeneration.from_pretrained(M2M_MODEL)

    out: list[str] = []
    for i in range(0, len(senses), batch_size):
        chunk = senses[i : i + batch_size]
        batch = tokenizer(chunk, return_tensors="pt", padding=True, truncation=True)
        generated = model.generate(
            **batch, forced_bos_token_id=tokenizer.get_lang_id(M2M_TGT), max_new_tokens=96
        )
        out.extend(tokenizer.batch_decode(generated, skip_special_tokens=True))
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=200)
    ap.add_argument("--out", type=Path, default=OUT)
    args = ap.parse_args()

    senses = load_senses(args.limit)
    print(f"comparing {len(senses)} senses")

    started = time.time()
    nllb = run_nllb(senses)
    nllb_time = time.time() - started
    print(f"nllb done in {nllb_time:.0f}s")

    started = time.time()
    m2m = run_m2m(senses)
    m2m_time = time.time() - started
    print(f"m2m done in {m2m_time:.0f}s")

    rows = []
    for sense, a, b in zip(senses, nllb, m2m):
        rows.append({"sense": sense, "nllb": a.strip(), "m2m100": b.strip()})

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8") as fh:
        json.dump(
            {
                "nllb_model": NLLB_MODEL,
                "m2m_model": M2M_MODEL,
                "nllb_seconds": round(nllb_time, 1),
                "m2m_seconds": round(m2m_time, 1),
                "count": len(rows),
                "rows": rows,
            },
            fh,
            ensure_ascii=False,
            indent=1,
        )
    print(f"written to {args.out}")


if __name__ == "__main__":
    main()
