import requests, json

h = {"User-Agent": "Mozilla/5.0"}
u = "https://kaikki.org/dictionary/downloads/zh/zh-extract.jsonl.gz"

n = 0
bg = []
langs = {}
with requests.get(u, headers=h, timeout=300, stream=True) as r:
    import gzip, io
    gz = gzip.GzipFile(fileobj=r.raw)
    reader = io.TextIOWrapper(gz, encoding="utf-8")
    for line in reader:
        n += 1
        if n <= 2:
            d = json.loads(line)
            print("KEYS:", sorted(d.keys()))
            print("word:", d.get("word"), "lang:", d.get("lang"))
            print(json.dumps(d, ensure_ascii=False)[:900])
        else:
            try:
                d = json.loads(line)
            except Exception:
                continue
            for s in d.get("senses", []) or []:
                for t in s.get("translations", []) or []:
                    code = t.get("code")
                    langs[code] = langs.get(code, 0) + 1
                    if code == "bg":
                        bg.append((d.get("word"), d.get("pos"), t.get("word"), t.get("sense")))
                        break
        if len(bg) > 60 or n >= 120000:
            break
    r.close()

print("scanned", n)
print("bg hits:", len(bg))
print("translation codes seen:", sorted(langs.items(), key=lambda kv: -kv[1])[:15])
for b in bg[:20]:
    print("   ", b)
