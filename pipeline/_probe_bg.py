import requests, json, sys

h = {"User-Agent": "Mozilla/5.0"}
u = "https://kaikki.org/dictionary/Chinese/kaikki.org-dictionary-Chinese.jsonl"

shown = 0
langs = {}
bg_hits = []
n = 0
with requests.get(u, headers=h, timeout=300, stream=True) as r:
    for line in r.iter_lines(decode_unicode=True):
        if not line:
            continue
        n += 1
        try:
            d = json.loads(line)
        except Exception:
            continue
        lc = d.get("lang_code")
        langs[lc] = langs.get(lc, 0) + 1
        for s in d.get("senses", []) or []:
            tr = s.get("translations") or []
            for t in tr:
                code = t.get("code") or t.get("lang_code")
                if code == "bg":
                    bg_hits.append((d.get("word"), d.get("pos"), t.get("word"), t.get("sense")))
                    break
        if shown < 2 and d.get("lang_code") in ("cmn", "zh", "zh-min-nan"):
            print("EXAMPLE word:", d.get("word"), "lang:", d.get("lang"))
            print(json.dumps(d.get("senses", [])[:1], ensure_ascii=False)[:1200])
            shown += 1
        if n >= 40000:
            break
    r.close()

print("scanned", n)
print("lang_code distribution (top):", sorted(langs.items(), key=lambda kv: -kv[1])[:10])
print("BG translation hits in scan:", len(bg_hits))
for b in bg_hits[:15]:
    print("   ", b)
