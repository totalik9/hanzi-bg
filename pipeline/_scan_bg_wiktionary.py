"""Scan the Chinese Wiktionary wiktextract extract for Chinese->Bulgarian word translations.

Outputs JSON: {"word": ["bulgarian translation", ...]} to data/raw/bg_zh_wiktionary.json
Only genuine Bulgarian translation entries found in the source are kept.
"""
import gzip
import io
import json
import os
import sys
import time

import requests

# The repository root, derived from this file: the script used to
# carry the original developer's absolute path, which is dead on any
# other machine.
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

URL = "https://kaikki.org/dictionary/downloads/zh/zh-extract.jsonl.gz"
OUT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "data", "raw", "bg_zh_wiktionary.json")

h = {"User-Agent": "Mozilla/5.0"}
result = {}
codes = {}
n = 0
t0 = time.time()

with requests.get(URL, headers=h, timeout=600, stream=True) as r:
    r.raise_for_status()
    gz = gzip.GzipFile(fileobj=r.raw)
    reader = io.TextIOWrapper(gz, encoding="utf-8")
    for line in reader:
        n += 1
        if n % 200000 == 0:
            print(f"  scanned {n} lines, bg hits {len(result)}, {time.time()-t0:.0f}s", flush=True)
        if '"translations"' not in line:
            continue
        try:
            d = json.loads(line)
        except Exception:
            continue
        if d.get("lang_code") != "zh":
            continue
        word = d.get("word")
        for t in d.get("translations") or []:
            code = t.get("code") or t.get("lang_code")
            codes[code] = codes.get(code, 0) + 1
            if code == "bg":
                tw = (t.get("word") or "").strip()
                if tw and word:
                    result.setdefault(word, [])
                    if tw not in result[word]:
                        result[word].append(tw)
                break

os.makedirs(os.path.dirname(OUT), exist_ok=True)
with open(OUT, "w", encoding="utf-8") as f:
    json.dump(result, f, ensure_ascii=False, indent=0, sort_keys=True)

print(f"SCAN DONE lines={n} bg_words={len(result)} secs={time.time()-t0:.0f}")
print("top translation codes:", sorted(codes.items(), key=lambda kv: -kv[1])[:12])
sample = list(result.items())[:15]
for k, v in sample:
    print("   ", k, "->", v)
print("WROTE", OUT)
