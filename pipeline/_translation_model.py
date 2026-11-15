"""The translation model, in one place, used the same way by every step.

WHY THIS EXISTS

The three translation steps (07 vocabulary, 11 grammar, 12 sentences)
each had their own copy of the model plumbing, and each copy hard-coded
``facebook/nllb-200-distilled-600M``. That model is licensed
CC-BY-NC-4.0: NON-COMMERCIAL. The pipeline did not care -- the
docstring said "fine for this non-commercial project", and that
assumption is exactly what breaks the moment anybody sells the app or
puts it on a store that takes a cut.

So the model is now a choice, the choice is written down, and the
DEFAULT is a permissive one:

    facebook/m2m100_418M      MIT      <- the default
    facebook/m2m100_1.2B      MIT
    facebook/nllb-200-distilled-600M   CC-BY-NC-4.0 (non-commercial)

The licences are not a guess. They are what the Hugging Face model
cards say, and the test in ``pipeline/test_translation_model.py`` reads
the licence straight from the API so a silent change upstream is caught.

THE CACHES ARE PER MODEL

The cached translations are the model's OUTPUT, so they belong to the
model that produced them. A cache shared between two models would hand
out NLLB's Bulgarian for an M2M run and quietly mix two translation
styles in one word list. Every cache file therefore carries the model
name in its file name:

    data/bg_sense_cache.json
    data/bg_sense_cache.m2m100_418M.json
    data/bg_sense_cache.nllb-200-distilled-600M.json

Switching models does not throw the other model's work away, and it does
not reuse it either.

Usage:
    from _translation_model import Translator, cache_path, resolve_model

    spec = resolve_model("m2m100_418M")
    translator = Translator(spec)
    bulgarian = translator.translate(["water", "to eat"], max_new_tokens=32)
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass

# The model the pipeline uses when nobody says otherwise. Permissive
# licence on purpose: the translations are baked into the APK and
# shipped to anyone who installs it.
DEFAULT_MODEL = "m2m100_418M"


@dataclass(frozen=True)
class ModelSpec:
    """Everything that is different between one translation model and another."""

    name: str
    """The short name: used on the command line and in the cache file names."""

    model_id: str
    """The Hugging Face id the model is loaded from."""

    family: str
    """``m2m`` or ``nllb`` -- the two tokenizers take different arguments."""

    source_lang: str
    """The source language code, in the spelling THIS tokenizer wants."""

    target_lang: str
    """The target language code, in the spelling THIS tokenizer wants."""

    license: str
    """The licence of the model weights, as the model card states it."""

    license_url: str
    """Where the licence can be read."""

    note: str = ""


MODELS: dict[str, ModelSpec] = {
    "m2m100_418M": ModelSpec(
        name="m2m100_418M",
        model_id="facebook/m2m100_418M",
        family="m2m",
        source_lang="en",
        target_lang="bg",
        license="MIT",
        license_url="https://huggingface.co/facebook/m2m100_418M",
        note="the default -- a permissive licence",
    ),
    "m2m100_1.2B": ModelSpec(
        name="m2m100_1.2B",
        model_id="facebook/m2m100_1.2B",
        family="m2m",
        source_lang="en",
        target_lang="bg",
        license="MIT",
        license_url="https://huggingface.co/facebook/m2m100_1.2B",
        note="the same licence as the default, about three times the size",
    ),
    "nllb-200-distilled-600M": ModelSpec(
        name="nllb-200-distilled-600M",
        model_id="facebook/nllb-200-distilled-600M",
        family="nllb",
        source_lang="eng_Latn",
        target_lang="bul_Cyrl",
        license="CC-BY-NC-4.0",
        license_url="https://huggingface.co/facebook/nllb-200-distilled-600M",
        note="NON-COMMERCIAL -- only for a project that cannot be sold",
    ),
}


def resolve_model(name: str | None) -> ModelSpec:
    """The model spec for a short name, a full Hugging Face id, or nothing.

    Nothing means the default, which is the permissive one.

    >>> resolve_model(None).name
    'm2m100_418M'
    >>> resolve_model("facebook/m2m100_418M").name
    'm2m100_418M'
    >>> resolve_model("m2m100_418M").license
    'MIT'
    """
    if not name:
        name = DEFAULT_MODEL
    if name in MODELS:
        return MODELS[name]
    # A full model id: match on the part after the slash.
    for spec in MODELS.values():
        if spec.model_id == name or name.split("/")[-1] == spec.name:
            return spec
    known = ", ".join(sorted(MODELS))
    raise SystemExit(
        f"ERROR: unknown translation model '{name}'\n"
        f"       known models: {known}\n"
        f"       (or a full id like facebook/{DEFAULT_MODEL})"
    )


def is_non_commercial(spec: ModelSpec) -> bool:
    """True when the licence forbids commercial use."""
    return "NC" in spec.license.upper() or "NONCOMMERCIAL" in spec.license.upper()


def cache_path(base: str, spec: ModelSpec) -> str:
    """The cache file that belongs to this model.

    >>> resolve_model("m2m100_418M")
    ModelSpec(name='m2m100_418M', ...)
    >>> cache_path("data/bg_sense_cache.json", resolve_model("m2m100_418M"))
    'data/bg_sense_cache.m2m100_418M.json'
    >>> cache_path("data/bg_sense_cache.json", resolve_model("nllb-200-distilled-600M"))
    'data/bg_sense_cache.nllb-200-distilled-600M.json'
    """
    root, ext = os.path.splitext(base)
    return f"{root}.{spec.name}{ext}"


def load_cache(path: str) -> dict[str, str]:
    """Read a translation cache. A missing or broken file is an empty cache."""
    if not os.path.exists(path):
        return {}
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    return {str(k): str(v) for k, v in data.items()}


def save_cache(path: str, cache: dict[str, str]) -> None:
    """Write the cache atomically: a killed run must not corrupt it."""
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(cache, fh, ensure_ascii=False, indent=1, sort_keys=True)
    os.replace(tmp, path)


class Translator:
    """One translation model, loaded once and used for many texts."""

    def __init__(self, spec: ModelSpec):
        self.spec = spec
        import torch
        from transformers import (
            AutoModelForSeq2SeqLM,
            AutoTokenizer,
            M2M100ForConditionalGeneration,
            M2M100Tokenizer,
        )

        if spec.family == "m2m":
            self.tokenizer = M2M100Tokenizer.from_pretrained(spec.model_id)
            self.model = M2M100ForConditionalGeneration.from_pretrained(spec.model_id)
            self._forced_bos = self.tokenizer.get_lang_id(spec.target_lang)
        elif spec.family == "nllb":
            self.tokenizer = AutoTokenizer.from_pretrained(spec.model_id)
            self.model = AutoModelForSeq2SeqLM.from_pretrained(spec.model_id)
            self._forced_bos = self.tokenizer.convert_tokens_to_ids(spec.target_lang)
        else:
            raise SystemExit(f"ERROR: unknown model family '{spec.family}'")

        self.model.eval()
        self._torch = torch

    @property
    def threads(self) -> int:
        return self._torch.get_num_threads()

    def translate(
        self,
        texts: list[str],
        *,
        max_new_tokens: int = 64,
        num_beams: int = 2,
        batch_size: int = 16,
    ) -> list[str]:
        """Translate the texts into Bulgarian. One output per input."""
        out: list[str] = []
        for i in range(0, len(texts), batch_size):
            chunk = texts[i : i + batch_size]
            self.tokenizer.src_lang = self.spec.source_lang
            encoded = self.tokenizer(
                chunk, return_tensors="pt", padding=True, truncation=True
            )
            with self._torch.no_grad():
                generated = self.model.generate(
                    **encoded,
                    forced_bos_token_id=self._forced_bos,
                    max_new_tokens=max_new_tokens,
                    num_beams=num_beams,
                )
            out.extend(self.tokenizer.batch_decode(generated, skip_special_tokens=True))
        return [text.strip() for text in out]


# Where the provenance of the shipped translations is recorded. It is a
# JSON file so that it can be read without the pipeline's code, and it
# is written by the translation steps themselves, so it cannot drift
# from what actually happened.
PROVENANCE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data",
    "translation_provenance.json",
)


def read_provenance(path: str = PROVENANCE_PATH) -> dict:
    """What is known about the provenance of the translations."""
    if not os.path.exists(path):
        return {}
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def record_provenance(
    dataset: str,
    spec: ModelSpec,
    count: int,
    path: str = PROVENANCE_PATH,
) -> None:
    """Record which model produced the translations of one dataset.

    The shipped content is the app's licence, not just the model's.
    A file that says which model wrote every dataset makes the
    question answerable without archaeology.
    """
    data = read_provenance(path)
    data[dataset] = {
        "model_id": spec.model_id,
        "license": spec.license,
        "license_url": spec.license_url,
        "commercial_use_allowed": not is_non_commercial(spec),
        "items": count,
    }
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=1, sort_keys=True)
    os.replace(tmp, path)


def load_or_migrate_cache(base: str, spec: ModelSpec) -> tuple[dict[str, str], bool]:
    """The cache for this model, adopting the old un-suffixed file if it fits.

    Before the model became a choice there was ONE cache file, and it
    was written by NLLB-200. When the default changed to the MIT
    model, that file could not be adopted -- its contents are NLLB's
    output, not the default model's -- so the default starts empty and
    says so. For NLLB itself the old file IS its cache, and it is moved
    to the suffixed name so the old path cannot be written again by
    accident.

    Returns (cache, adopted_from_the_old_file).
    """
    old = load_cache(base)
    if not old:
        return {}, False

    existing = load_cache(cache_path(base, spec))
    if existing:
        return existing, False

    if spec.family == "nllb":
        # The old cache was NLLB's work.
        save_cache(cache_path(base, spec), old)
        return old, True
    return {}, False
