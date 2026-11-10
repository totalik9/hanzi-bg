import csv, collections, glob, os
os.chdir(os.environ.get("TMPDIR", "."))
for f in sorted(glob.glob("hs-*.csv")):
    rr = list(csv.DictReader(open(f, encoding="utf-8-sig")))
    c26 = collections.Counter(r["hsk2026_level"] for r in rr)
    c21 = collections.Counter(r["hsk2021_level"] for r in rr)
    print(f, len(rr), "hsk2026:", dict(list(c26.items())[:8]), "hsk2021:", dict(list(c21.items())[:6]))
