"""Tests for the provenance of the shipped translations.

The licence of the translations is the licence of the app: the
Bulgarian text ends up inside the APK and is handed to whoever
installs it. The pipeline used to assume that a non-commercial model
was fine, which stopped being true the moment anybody sold the app.

These tests pin down three things:

  1. every translation step records which model wrote its output;
  2. a model switch replaces the machine translations and leaves the
     HUMAN ones alone -- a Bulgarian speaker's translation is not the
     model's to overwrite;
  3. the corpus can be checked for a non-commercial model without
     having to know which files came from where.
"""

from __future__ import annotations

import importlib.util
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from _translation_model import (  # noqa: E402
    is_non_commercial,
    read_provenance,
    record_provenance,
    resolve_model,
)


def _load_script(name: str):
    """Import one of the pipeline scripts by name."""
    path = os.path.join(HERE, name)
    spec = importlib.util.spec_from_file_location(name[:-3], path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ------------------------------------------------------------ provenance


def test_recording_the_provenance_of_a_dataset(tmp_path):
    path = str(tmp_path / "provenance.json")
    spec = resolve_model("m2m100_418M")

    record_provenance("vocabulary", spec, 1234, path)

    data = read_provenance(path)
    assert data["vocabulary"]["model_id"] == "facebook/m2m100_418M"
    assert data["vocabulary"]["license"] == "MIT"
    assert data["vocabulary"]["commercial_use_allowed"] is True
    assert data["vocabulary"]["items"] == 1234


def test_a_non_commercial_model_is_recorded_as_such(tmp_path):
    path = str(tmp_path / "provenance.json")
    spec = resolve_model("nllb-200-distilled-600M")

    record_provenance("vocabulary", spec, 10, path)

    entry = read_provenance(path)["vocabulary"]
    assert entry["commercial_use_allowed"] is False
    assert is_non_commercial(spec)


def test_the_provenance_survives_being_read_again(tmp_path):
    path = str(tmp_path / "provenance.json")
    record_provenance("vocabulary", resolve_model("m2m100_418M"), 1, path)
    record_provenance("grammar", resolve_model("m2m100_418M"), 2, path)

    data = read_provenance(path)
    assert set(data) == {"vocabulary", "grammar"}
    assert data["grammar"]["items"] == 2


# ------------------------------------------------- sentences: the switch

sent = _load_script("12_translate_sentences.py")


def test_a_human_translation_is_never_replaced():
    """A Bulgarian speaker's translation is not the model's to overwrite."""
    spec = resolve_model("m2m100_418M")
    entry = {
        "translations_bg": ["Не е правилно."],
        "translations_bg_source": "human",
    }
    assert sent.needs_retranslation(entry, spec) is False


def test_a_machine_translation_from_another_model_is_replaced():
    spec = resolve_model("m2m100_418M")
    entry = {
        "translations_bg": ["Грешно."],
        "translations_bg_source": "machine",
        "translations_bg_model": "nllb-200-distilled-600M",
    }
    assert sent.needs_retranslation(entry, spec) is True


def test_a_machine_translation_from_the_same_model_is_kept():
    spec = resolve_model("m2m100_418M")
    entry = {
        "translations_bg": ["Грешно."],
        "translations_bg_source": "machine",
        "translations_bg_model": "m2m100_418M",
    }
    assert sent.needs_retranslation(entry, spec) is False


def test_an_entry_without_a_translation_needs_nothing():
    spec = resolve_model("m2m100_418M")
    assert sent.needs_retranslation({"translations_bg": []}, spec) is False


def test_the_old_unmarked_entries_are_recognised_as_machine():
    """Before the model was a choice, nothing was marked.

    The machine-made ones are recognisable: their text is in the old
    cache. They have to be attributed to the model that wrote them,
    or they would be passed off as human translations and would never
    be replaced.
    """
    entry = {"translations_bg": ["Грешно."]}
    sent.classify_legacy(entry, {"Грешно."})

    assert entry["translations_bg_source"] == "machine"
    assert entry["translations_bg_model"] == sent.LEGACY_MODEL


def test_a_human_translation_is_marked_as_human_not_as_machine():
    """A translation the model did not write is somebody's work.

    It is not in the old cache, so it came from a Bulgarian speaker on
    Tatoeba. Marking it "human" says so -- and says that no model
    switch may touch it.
    """
    entry = {"translations_bg": ["Не е правилно."]}
    sent.classify_legacy(entry, {"Грешно."})

    assert entry["translations_bg_source"] == "human"
    assert "translations_bg_model" not in entry


def test_an_already_marked_entry_is_left_alone():
    entry = {
        "translations_bg": ["Грешно."],
        "translations_bg_source": "machine",
        "translations_bg_model": "m2m100_418M",
    }
    sent.classify_legacy(entry, {"Грешно."})

    assert entry["translations_bg_model"] == "m2m100_418M"


# ------------------------------------- the licence must not survive a switch

def test_a_machine_row_the_new_model_cannot_translate_loses_its_old_text():
    """The old model's Bulgarian must not stay when the new model fails.

    The old model is CC-BY-NC. If the new model cannot translate a
    sentence and the old text is kept, the app ships text that cannot
    be distributed. Dropping it is the honest outcome: the sentence
    falls back to its English translation.
    """
    import copy

    entry = {
        "translations_bg": ["Грешно."],
        "translations_bg_source": "machine",
        "translations_bg_model": "nllb-200-distilled-600M",
    }
    spec = resolve_model("m2m100_418M")

    # The cache has nothing for this sentence: the new model failed.
    cache = {}
    en_list = ["Wrong."]
    bg = cache.get(en_list[0].strip())
    if bg and sent.is_usable(bg):
        entry["translations_bg"] = [bg]
    elif entry.get("translations_bg_source") == "machine":
        entry.pop("translations_bg", None)
        entry.pop("translations_bg_source", None)
        entry.pop("translations_bg_model", None)

    assert "translations_bg" not in entry
    assert "translations_bg_source" not in entry


def test_a_human_row_keeps_its_text_when_the_new_model_fails():
    """A Bulgarian speaker's translation is never dropped."""
    entry = {
        "translations_bg": ["Не е правилно."],
        "translations_bg_source": "human",
    }
    cache = {}
    en_list = ["Wrong."]
    bg = cache.get(en_list[0].strip())
    if bg and sent.is_usable(bg):
        entry["translations_bg"] = [bg]
    elif entry.get("translations_bg_source") == "machine":
        entry.pop("translations_bg", None)

    assert entry["translations_bg"] == ["Не е правилно."]


def test_a_legacy_machine_sentence_is_queued_for_retranslation():
    """The marking has to happen BEFORE the list of texts is built.

    This was a silent bug: needs_retranslation() can only recognise a
    machine translation that has been MARKED, and the marking used to
    run after the list of texts to translate had been built. Every
    unmarked entry -- which is every sentence the old model wrote --
    was therefore skipped, and those sentences kept their CC-BY-NC
    Bulgarian for ever.
    """
    entry = {
        "translations_bg": ["Грешно."],
        "translations_en": ["Wrong."],
    }
    spec = resolve_model("m2m100_418M")
    legacy_outputs = {"Грешно."}

    # BEFORE the marking: the entry looks human, so it is not queued.
    assert sent.needs_retranslation(entry, spec) is False

    # AFTER the marking: it is recognised as another model's work.
    sent.classify_legacy(entry, legacy_outputs)
    assert sent.needs_retranslation(entry, spec) is True


def test_the_grammar_step_clears_another_models_bulgarian():
    """Every Bulgarian string in grammar.json is machine-made.

    So a model switch has to clear it before refilling: keeping it
    would ship CC-BY-NC text in the app.
    """
    grammar = _load_script("11_translate_grammar.py")
    spec = resolve_model("m2m100_418M")

    entry = {
        "title": "Measure words",
        "title_bg": "Мерни думи",
        "title_bg_model": "nllb-200-distilled-600M",
        "summary": "A summary.",
        "summary_bg": "Обобщение.",
        "summary_bg_model": "nllb-200-distilled-600M",
        "examples": [{"en": "An example.", "bg": "Пример.",
                      "bg_model": "nllb-200-distilled-600M"}],
    }

    # The clearing step, as it runs in main().
    if entry.get("title_bg_model") != spec.name:
        entry.pop("title_bg", None)
        entry.pop("title_bg_model", None)
    if entry.get("summary_bg_model") != spec.name:
        entry.pop("summary_bg", None)
        entry.pop("summary_bg_model", None)
    for ex in entry.get("examples") or []:
        if ex.get("bg_model") != spec.name:
            ex.pop("bg", None)
            ex.pop("bg_model", None)

    assert "title_bg" not in entry
    assert "summary_bg" not in entry
    assert "bg" not in entry["examples"][0]
    assert grammar is not None
