"""Download and decompress all upstream content sources for the hanzi-bg pipeline.

Sources are downloaded into data/raw/ and recorded in data/raw/manifest.json with
filename, url, license, retrieval timestamp, sha256 and byte size.

The script is RESUMABLE: a file that already exists and is non-empty is never
re-downloaded, so re-running after a partial failure only fetches what is missing.

Usage:
    python pipeline/01_fetch_sources.py
"""

from __future__ import annotations

import bz2
import gzip
import hashlib
import json
import os
import shutil
import sys
import tarfile
import time
import zipfile

import requests

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
RAW = os.path.join(ROOT, "data", "raw")
MANIFEST = os.path.join(RAW, "manifest.json")

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0 Safari/537.36"

# Each entry: (local_name, url, license, kind)
# kind: "plain" (no decompression) | "zip" | "gz" | "bz2" | "tar.bz2"
SOURCES = [
    # --- Dictionary -------------------------------------------------------
    (
        "cedict_1_0_ts_utf-8_mdbg.txt",
        "https://www.mdbg.net/chinese/export/cedict/cedict_1_0_ts_utf-8_mdbg.zip",
        "CC BY-SA 4.0 (CC-CEDICT)",
        "zip",
    ),
    # --- Make Me a Hanzi (stroke order + decomposition) -------------------
    (
        "mmah_dictionary.txt",
        "https://raw.githubusercontent.com/skishore/makemeahanzi/master/dictionary.txt",
        "Arphic Public License (permissive)",
        "plain",
    ),
    (
        "mmah_graphics.txt",
        "https://raw.githubusercontent.com/skishore/makemeahanzi/master/graphics.txt",
        "Arphic Public License (permissive)",
        "plain",
    ),
    # --- Pinyin data ------------------------------------------------------
    (
        "pinyin_data.txt",
        "https://raw.githubusercontent.com/mozillazg/pinyin-data/master/pinyin.txt",
        "MIT (mozillazg/pinyin-data)",
        "plain",
    ),
    (
        "pinyin_kMandarin_8105.txt",
        "https://raw.githubusercontent.com/mozillazg/pinyin-data/master/kMandarin_8105.txt",
        "MIT (mozillazg/pinyin-data)",
        "plain",
    ),
    (
        "pinyin_kXHC1983.txt",
        "https://raw.githubusercontent.com/mozillazg/pinyin-data/master/kXHC1983.txt",
        "MIT (mozillazg/pinyin-data)",
        "plain",
    ),
    (
        "pinyin_kHanyuPinyin.txt",
        "https://raw.githubusercontent.com/mozillazg/pinyin-data/master/kHanyuPinyin.txt",
        "MIT (mozillazg/pinyin-data)",
        "plain",
    ),
    (
        "phrase_pinyin.txt",
        "https://raw.githubusercontent.com/mozillazg/phrase-pinyin-data/master/pinyin.txt",
        "MIT (mozillazg/phrase-pinyin-data)",
        "plain",
    ),
    # --- Tatoeba (Chinese) ------------------------------------------------
    (
        "cmn_sentences.tsv",
        "https://downloads.tatoeba.org/exports/per_language/cmn/cmn_sentences.tsv.bz2",
        "CC BY 2.0 FR (Tatoeba)",
        "bz2",
    ),
    (
        "cmn_links_eng.tsv",
        "https://downloads.tatoeba.org/exports/per_language/cmn/cmn-eng_links.tsv.bz2",
        "CC BY 2.0 FR (Tatoeba)",
        "bz2",
    ),
    (
        "cmn_links_bul.tsv",
        "https://downloads.tatoeba.org/exports/per_language/cmn/cmn-bul_links.tsv.bz2",
        "CC BY 2.0 FR (Tatoeba)",
        "bz2",
    ),
    (
        "cmn_tags.tsv",
        "https://downloads.tatoeba.org/exports/per_language/cmn/cmn_tags.tsv.bz2",
        "CC BY 2.0 FR (Tatoeba)",
        "bz2",
    ),
    (
        "cmn_sentences_with_audio.tsv",
        "https://downloads.tatoeba.org/exports/per_language/cmn/cmn_sentences_with_audio.tsv.bz2",
        "CC BY 2.0 FR (Tatoeba) - audio carries per-contributor licenses",
        "bz2",
    ),
    (
        "cmn_transcriptions.tsv",
        "https://downloads.tatoeba.org/exports/per_language/cmn/cmn_transcriptions.tsv.bz2",
        "CC BY 2.0 FR (Tatoeba)",
        "bz2",
    ),
    # --- Tatoeba (Bulgarian) - real Bulgarian sentence translations -------
    (
        "bul_sentences.tsv",
        "https://downloads.tatoeba.org/exports/per_language/bul/bul_sentences.tsv.bz2",
        "CC BY 2.0 FR (Tatoeba)",
        "bz2",
    ),
    # --- Tatoeba global audio index (audio file -> sentence id) ------------
    (
        "sentences_with_audio.csv",
        "https://downloads.tatoeba.org/exports/sentences_with_audio.tar.bz2",
        "CC BY 2.0 FR (Tatoeba) - audio carries per-contributor licenses",
        "tar.bz2",
    ),
    # --- HSK 3.0 vocabulary (official new syllabus, Nov 2025) -------------
    (
        "hsk_3_0_level_1.csv",
        "https://literatelanguages.com/chinese/hsk-vocabulary/hsk-1.csv",
        "Free download from literatelanguages.com (HSK 3.0 word lists)",
        "plain",
    ),
    (
        "hsk_3_0_level_2.csv",
        "https://literatelanguages.com/chinese/hsk-vocabulary/hsk-2.csv",
        "Free download from literatelanguages.com (HSK 3.0 word lists)",
        "plain",
    ),
    (
        "hsk_3_0_level_3.csv",
        "https://literatelanguages.com/chinese/hsk-vocabulary/hsk-3.csv",
        "Free download from literatelanguages.com (HSK 3.0 word lists)",
        "plain",
    ),
    (
        "hsk_3_0_level_4.csv",
        "https://literatelanguages.com/chinese/hsk-vocabulary/hsk-4.csv",
        "Free download from literatelanguages.com (HSK 3.0 word lists)",
        "plain",
    ),
    (
        "hsk_3_0_level_5.csv",
        "https://literatelanguages.com/chinese/hsk-vocabulary/hsk-5.csv",
        "Free download from literatelanguages.com (HSK 3.0 word lists)",
        "plain",
    ),
    (
        "hsk_3_0_level_6.csv",
        "https://literatelanguages.com/chinese/hsk-vocabulary/hsk-6.csv",
        "Free download from literatelanguages.com (HSK 3.0 word lists)",
        "plain",
    ),
    (
        "hsk_3_0_level_7_9.csv",
        "https://literatelanguages.com/chinese/hsk-vocabulary/hsk-7-9.csv",
        "Free download from literatelanguages.com (HSK 3.0 word lists)",
        "plain",
    ),
]


def sha256_of(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def download(url: str, dest: str, attempts: int = 3) -> bool:
    """Download url to dest. Returns True on success."""
    tmp = dest + ".part"
    for attempt in range(1, attempts + 1):
        try:
            with requests.get(url, headers={"User-Agent": UA}, stream=True, timeout=120) as r:
                r.raise_for_status()
                with open(tmp, "wb") as fh:
                    for chunk in r.iter_content(chunk_size=1 << 20):
                        if chunk:
                            fh.write(chunk)
            os.replace(tmp, dest)
            return True
        except Exception as exc:  # noqa: BLE001 - we want to keep going
            print(f"    attempt {attempt}/{attempts} failed for {url}: {exc}")
            if os.path.exists(tmp):
                os.remove(tmp)
            time.sleep(2 * attempt)
    return False


def decompress(kind: str, src: str, dest: str) -> None:
    """Decompress src into dest according to kind."""
    if kind == "plain":
        shutil.copyfile(src, dest)
    elif kind == "zip":
        with zipfile.ZipFile(src) as zf:
            names = [n for n in zf.namelist() if not n.endswith("/")]
            # prefer the file whose name matches the requested dest
            pick = None
            for n in names:
                if os.path.basename(n) == os.path.basename(dest):
                    pick = n
                    break
            pick = pick or names[0]
            with zf.open(pick) as src_f, open(dest, "wb") as out:
                shutil.copyfileobj(src_f, out)
    elif kind == "gz":
        with gzip.open(src, "rb") as src_f, open(dest, "wb") as out:
            shutil.copyfileobj(src_f, out)
    elif kind == "bz2":
        with bz2.open(src, "rb") as src_f, open(dest, "wb") as out:
            shutil.copyfileobj(src_f, out)
    elif kind == "tar.bz2":
        with tarfile.open(src, "r:bz2") as tf:
            members = [m for m in tf.getmembers() if m.isfile()]
            pick = None
            for m in members:
                if os.path.basename(m.name) == os.path.basename(dest):
                    pick = m
                    break
            pick = pick or (members[0] if members else None)
            if pick is None:
                raise RuntimeError(f"no file member in {src}")
            f = tf.extractfile(pick)
            with f, open(dest, "wb") as out:
                shutil.copyfileobj(f, out)
    else:
        raise ValueError(f"unknown kind {kind}")


def main() -> int:
    os.makedirs(RAW, exist_ok=True)
    manifest = {}
    if os.path.exists(MANIFEST):
        try:
            with open(MANIFEST, encoding="utf-8") as fh:
                manifest = json.load(fh)
        except Exception:
            manifest = {}

    results = {"downloaded": 0, "skipped": 0, "failed": 0}
    failures = []

    for name, url, license_name, kind in SOURCES:
        dest = os.path.join(RAW, name)
        if os.path.exists(dest) and os.path.getsize(dest) > 0:
            print(f"[skip] {name} (exists, {os.path.getsize(dest):,} bytes)")
            results["skipped"] += 1
            entry = manifest.get(name)
            if not entry or entry.get("sha256") is None:
                manifest[name] = {
                    "filename": name,
                    "url": url,
                    "license": license_name,
                    "retrieved_at": entry.get("retrieved_at") if entry else None,
                    "sha256": sha256_of(dest),
                    "bytes": os.path.getsize(dest),
                }
            continue

        # compressed twin is downloaded first, then decompressed into dest
        if kind == "plain":
            tmp_src = dest + ".dl"
            tmp_kind = "plain"
        else:
            tmp_src = os.path.join(RAW, name + ".archive")
            tmp_kind = kind

        print(f"[get ] {name}\n       <- {url}")
        t0 = time.time()
        if not download(url, tmp_src):
            print(f"    FAILED to download {url}")
            failures.append({"filename": name, "url": url, "stage": "download"})
            results["failed"] += 1
            if os.path.exists(tmp_src):
                os.remove(tmp_src)
            continue
        try:
            if kind == "plain":
                os.replace(tmp_src, dest)
            else:
                decompress(kind, tmp_src, dest)
                os.remove(tmp_src)
        except Exception as exc:  # noqa: BLE001
            print(f"    FAILED to decompress {name}: {exc}")
            failures.append({"filename": name, "url": url, "stage": "decompress", "error": str(exc)})
            results["failed"] += 1
            continue

        size = os.path.getsize(dest)
        digest = sha256_of(dest)
        manifest[name] = {
            "filename": name,
            "url": url,
            "license": license_name,
            "retrieved_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "sha256": digest,
            "bytes": size,
        }
        results["downloaded"] += 1
        print(f"    ok  {size:,} bytes  sha256={digest[:16]}...  ({time.time()-t0:.1f}s)")

    manifest["_meta"] = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "results": results,
        "failures": failures,
    }
    with open(MANIFEST, "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, ensure_ascii=False, indent=2)

    total = sum(1 for k in manifest if not k.startswith("_"))
    print()
    print(f"SUMMARY 01_fetch_sources: downloaded={results['downloaded']} "
          f"skipped={results['skipped']} failed={results['failed']} "
          f"manifest_entries={total} -> {MANIFEST}")
    if failures:
        print("FAILURES:")
        for f in failures:
            print(f"   {f['filename']}: {f['stage']} {f.get('error','')}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
