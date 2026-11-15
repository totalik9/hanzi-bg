"""Tests for the translation model plumbing.

The point of the module is that the pipeline's licence assumption is
wrong. NLLB-200 is CC-BY-NC: non-commercial. The default model has to
be one whose licence permits shipping the result, and the licence has
to be read from the model card rather than remembered.

These tests check the model registry, the per-model cache names, and --
when the network is available -- that the licences in the registry are
the licences the Hugging Face API actually reports.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.request

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _translation_model import (  # noqa: E402
    DEFAULT_MODEL,
    MODELS,
    cache_path,
    is_non_commercial,
    load_cache,
    load_or_migrate_cache,
    resolve_model,
    save_cache,
)


def test_the_default_model_is_permissive():
    """The default must be usable in something that is sold.

    The old default was facebook/nllb-200-distilled-600M, which is
    CC-BY-NC-4.0. The translations end up in the APK, so a
    non-commercial licence on the model is a non-commercial licence on
    the app.
    """
    spec = resolve_model(None)
    assert spec.name == DEFAULT_MODEL
    assert not is_non_commercial(spec), (
        f"the default model {spec.name} is licensed {spec.license} -- "
        "that forbids commercial use"
    )


def test_every_registered_model_has_a_licence_and_a_url():
    for spec in MODELS.values():
        assert spec.license, f"{spec.name} has no licence"
        assert spec.license_url.startswith("https://huggingface.co/")
        assert spec.model_id.startswith("facebook/")


def test_the_non_commercial_model_is_still_available_but_not_the_default():
    """The old model is not removed -- it is just no longer the default."""
    spec = resolve_model("nllb-200-distilled-600M")
    assert is_non_commercial(spec)
    assert resolve_model(None).name != spec.name


def test_a_model_can_be_named_by_its_short_name_or_its_full_id():
    assert resolve_model("m2m100_418M").model_id == "facebook/m2m100_418M"
    assert resolve_model("facebook/m2m100_418M").name == "m2m100_418M"


def test_an_unknown_model_is_an_error_not_a_silent_fallback():
    with pytest.raises(SystemExit):
        resolve_model("some/model-that-does-not-exist")


def test_each_model_gets_its_own_cache_file():
    """Two models must not share a cache.

    The cached translations are the model's own output. A shared file
    would hand out one model's Bulgarian in the other's run, and the
    two translation styles would end up mixed inside a single word
    list.
    """
    a = cache_path("data/bg_sense_cache.json", resolve_model("m2m100_418M"))
    b = cache_path("data/bg_sense_cache.json", resolve_model("nllb-200-distilled-600M"))
    assert a != b
    assert a.endswith(".m2m100_418M.json")
    assert b.endswith(".nllb-200-distilled-600M.json")


def test_the_cache_survives_a_killed_run(tmp_path):
    path = str(tmp_path / "cache.json")
    save_cache(path, {"water": "вода"})
    assert load_cache(path) == {"water": "вода"}
    # No temporary file left behind.
    assert not os.path.exists(path + ".tmp")


def test_a_broken_cache_is_an_empty_cache_not_a_crash(tmp_path):
    path = tmp_path / "cache.json"
    path.write_text("{not json", encoding="utf-8")
    assert load_cache(str(path)) == {}


def test_the_old_nllb_cache_is_adopted_by_nllb_and_not_by_another_model(tmp_path):
    """The old un-suffixed cache was NLLB's work.

    It has to move to NLLB's own file, so no work is thrown away. It
    must NOT be adopted by the default model: its contents are NLLB's
    output, and reusing them would ship NLLB's Bulgarian under the
    MIT model's name.
    """
    base = str(tmp_path / "bg_sense_cache.json")
    save_cache(base, {"water": "вода"})

    nllb = resolve_model("nllb-200-distilled-600M")
    cache, adopted = load_or_migrate_cache(base, nllb)
    assert adopted is True
    assert cache["water"] == "вода"
    assert os.path.exists(cache_path(base, nllb))

    other = resolve_model("m2m100_418M")
    cache, adopted = load_or_migrate_cache(base, other)
    assert adopted is False
    assert cache == {}


@pytest.mark.parametrize("model_id", sorted(MODELS))
def test_the_registered_licence_is_the_licence_the_model_card_reports(model_id):
    """The licence in the registry has to be the real one.

    A model can be relicensed upstream. The pipeline would keep
    believing the old terms, so the terms are read back from the
    Hugging Face API and compared.
    """
    spec = MODELS[model_id]
    url = f"https://huggingface.co/api/models/{spec.model_id}"
    try:
        with urllib.request.urlopen(url, timeout=30) as response:
            data = json.load(response)
    except Exception as exc:  # pragma: no cover - the network is optional
        pytest.skip(f"the Hugging Face API is not reachable: {exc}")

    reported = (data.get("cardData") or {}).get("license")
    assert reported, f"{spec.model_id} reports no licence at all"
    assert reported.lower() == spec.license.lower(), (
        f"{spec.model_id} is licensed {reported} now, but the pipeline "
        f"believes {spec.license}"
    )
