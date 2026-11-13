"""Scan the kaikki Chinese Wiktionary extract for POS + pinyin for Chinese words.

Wiktionary records carry an explicit `pos` field ("noun", "verb", ...) for
Chinese headwords, which CC-CEDICT lacks. This produces a side file
data/raw/wiktionary_pos.json: {"<hanzi>": {"pos": [...], "pinyin": "..."}}
"""
import gzip
import io
import json
import os
import sys
import time

import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pinyin_utils import is_hanzi  # noqa: E402

# The repository root, derived from this file: the script used to
# carry the original developer's absolute path, which is dead on any
# other machine.
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

URL = "https://kaikki.org/dictionary/Chinese/kaikki.org-dictionary-Chinese.jsonl"
OUT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "data", "raw", "wiktionary_pos.json")

h = {"User-Agent": "Mozilla/5.0"}
result = {}
n = 0
t0 = time.time()

with requests.get(URL, headers=h, timeout=900, stream=True) as r:
    r.raise_for_status()
    reader = io.TextIOWrapper(gzip.GzipFile(fileobj=r.raw), encoding="utf-8")
    for line in reader:
        n += 1
        if n % 100000 == 0:
            print(f"  scanned {n} lines, hanzi words {len(result)}, {time.time()-t0:.0f}s", flush=True)
        if '"lang_code": "zh"' not in line:
            continue
        try:
            d = json.loads(line)
        except Exception:
            continue
        word = d.get("word")
        if not word or len(word) > 8:
            continue
        if not all(is_hanzi(c) for c in word):
            continue
        pos = d.get("pos")
        if not pos:
            continue
        py = ""
        for s in d.get("sounds", []) or []:
            zh_pron = s.get("zh_pron")
            if zh_pron and (not py or "Pinyin" in (s.get("tags") or [])):
                py = zh_pron
                if "Pinyin" in (s.get("tags") or []):
                    break
        rec = result.setdefault(word, {"pos": [], "pinyin": ""})
        if pos not in rec["pos"]:
            rec["pos"].append(pos)
        if py and not rec["pinyin"]:
            rec["pinyin"] = py

os.makedirs(os.path.dirname(OUT), exist_ok=True)
with open(OUT, "w", encoding="utf-8") as f:
    json.dump(result, f, ensure_ascii=False, indent=0, sort_keys=True)

print(f"SCAN DONE lines={n} hanzi_words={len(result)} secs={time.time()-t0:.0f}")
for k, v in list(result.items())[:15]:
    print("   ", k, v)
print("WROTE", OUT)
