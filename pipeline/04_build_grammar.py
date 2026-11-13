"""Scrape the Chinese Grammar Wiki (AllSet Learning) into data/grammar.json.

Source: https://resources.allsetlearning.com/chinese/grammar/ - Creative Commons
licensed, organised by part of speech and CEFR/HSK difficulty level.

The MediaWiki api.php is behind a Cloudflare rule that rejects api.php requests
(403) from this host, so the raw wikitext is fetched with MediaWiki's
Special:Export endpoint instead, which serves the same revision text as XML.
The script tries api.php first and falls back to Special:Export.

Output: data/grammar.json
    {
      "meta": {...},
      "entries": [ {slug, title, level, category, summary, wiki_text,
                    examples: [{zh, pinyin, en}], source_url}, ... ]
    }

The raw wikitext is kept in every entry so a human can verify the extraction.

Usage:
    python pipeline/04_build_grammar.py
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from xml.etree import ElementTree

import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _guards  # noqa: E402
from pinyin_utils import (  # noqa: E402
    DATA,
    RAW,
    has_hanzi,
    split_pinyin_by_chars,
    split_pinyin_syllables,
    tone_marked_to_number,
)

OUT = os.path.join(DATA, "grammar.json")
CACHE = os.path.join(RAW, "grammar_cache")

# rendered links per level index page, filled in during the run
fetch_rendered_links_cache: dict[str, list[tuple[str, str]]] = {}

WIKI_BASE = "https://resources.allsetlearning.com/chinese/grammar/"
API_URL = WIKI_BASE + "api.php"
EXPORT_URL = WIKI_BASE + "Special:Export"

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36")

LICENSE = (
    "Chinese Grammar Wiki by AllSet Learning (John Pasden), Creative Commons "
    "licensed - see https://resources.allsetlearning.com/chinese/grammar/"
)

# pages that hold the tables of contents / level lists
INDEX_PAGES = [
    "Main_Page",
    "New_Main_Page",
    "Grammar_points_by_level",
    "A1_grammar_points",
    "A2_grammar_points",
    "B1_grammar_points",
    "B2_grammar_points",
    "C1_grammar_points",
    "HSK_1_grammar_points",
    "HSK_2_grammar_points",
    "HSK_3_grammar_points",
]

# level index page -> level label used in the output
LEVEL_PAGES = {
    "A1_grammar_points": "A1",
    "A2_grammar_points": "A2",
    "B1_grammar_points": "B1",
    "B2_grammar_points": "B2",
    "C1_grammar_points": "C1",
    "HSK_1_grammar_points": "HSK1",
    "HSK_2_grammar_points": "HSK2",
    "HSK_3_grammar_points": "HSK3",
}

# pages whose titles encode their level, e.g. "ASG..." pages are reached
# through the level index pages
LEVEL_PATTERNS = [
    (re.compile(r"^A1_"), "A1"),
    (re.compile(r"^A2_"), "A2"),
    (re.compile(r"^B1_"), "B1"),
    (re.compile(r"^B2_"), "B2"),
    (re.compile(r"^C1_"), "C1"),
    (re.compile(r"^HSK_1"), "HSK1"),
    (re.compile(r"^HSK_2"), "HSK2"),
    (re.compile(r"^HSK_3"), "HSK3"),
]

# part-of-speech headings used as categories
CATEGORY_HEADINGS = {
    "adverbs": "Adverb",
    "conjunctions": "Conjunction",
    "numbers": "Number",
    "particles": "Particle",
    "verbs": "Verb",
    "auxiliary verbs": "Auxiliary verb",
    "verb phrases": "Verb phrase",
    "nouns": "Noun",
    "pronouns": "Pronoun",
    "adjectives": "Adjective",
    "prepositions": "Preposition",
    "conjunction words": "Conjunction",
    "phrases": "Phrase",
    "expressions": "Expression",
    "grammar structures": "Grammar structure",
    "basics": "Grammar structure",
    "question forms": "Question form",
    "comparisons of similar grammar points": "Comparison",
    "measure words": "Measure word",
    "time expressions": "Time expression",
}


def cache_path(title: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_.-]", "_", title)
    return os.path.join(CACHE, safe + ".xml")


def fetch_rendered_links(url: str) -> list[tuple[str, str]]:
    """Fetch a rendered wiki page and return its internal links as (text, slug).

    The level index pages build their tables with Semantic MediaWiki queries,
    so the ASG* page list only exists in the rendered HTML, not in the
    wikitext.
    """
    try:
        r = requests.get(url, headers={"User-Agent": UA}, timeout=60)
        r.raise_for_status()
    except Exception as exc:  # noqa: BLE001
        print(f"   WARNING: could not render {url}: {exc}")
        return []
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        _guards.require_import(
            "bs4",
            "beautifulsoup4",
            "04_build_grammar.py",
        )
        return []
    soup = BeautifulSoup(r.text, "html.parser")
    content = soup.find("div", {"id": "mw-content-text"}) or soup
    out = []
    seen = set()
    for a in content.find_all("a", href=True):
        href = a["href"]
        if not href.startswith("/chinese/grammar/"):
            continue
        slug = href.split("/chinese/grammar/", 1)[1]
        if slug in seen or ":" in slug:
            continue
        seen.add(slug)
        out.append((a.get_text(" ", strip=True), slug))
    return out


def fetch_wikitext_titles(titles: list[str]) -> dict[str, str]:
    """Fetch raw wikitext for a list of page titles.

    Tries the MediaWiki api.php first; on failure (Cloudflare blocks api.php
    from this host) it falls back to Special:Export, which returns the same
    revision text inside a MediaWiki XML export.
    """
    result: dict[str, str] = {}

    # ---- try api.php -----------------------------------------------------
    try:
        r = requests.get(
            API_URL,
            params={"action": "parse", "page": "Main_Page", "prop": "wikitext", "format": "json"},
            headers={"User-Agent": UA},
            timeout=30,
        )
        if r.status_code == 200 and "wikitext" in r.text:
            print("   api.php is reachable")
        else:
            print(f"   api.php returned {r.status_code}; using Special:Export")
    except Exception as exc:  # noqa: BLE001
        print(f"   api.php failed ({exc}); using Special/Export")

    # ---- Special:Export (batched) ---------------------------------------
    batch_size = 25
    for start in range(0, len(titles), batch_size):
        batch = titles[start:start + batch_size]
        params = {"pages": "\n".join(batch), "curonly": "1", "wpDownload": "1"}
        try:
            r = requests.get(EXPORT_URL, params=params, headers={"User-Agent": UA}, timeout=90)
            r.raise_for_status()
            root = ElementTree.fromstring(r.text)
            ns = "{http://www.mediawiki.org/xml/export-0.10/}"
            for page in root.findall(f"{ns}page"):
                title = (page.findtext(f"{ns}title") or "").strip()
                text_el = page.find(f"{ns}revision/{ns}text")
                if title and text_el is not None and text_el.text:
                    result[title.replace(" ", "_")] = text_el.text
        except Exception as exc:  # noqa: BLE001
            print(f"   WARNING: export batch {start // batch_size} failed: {exc}")
        time.sleep(0.4)

    # ---- per-page fallback for anything the batch missed ----------------
    for title in titles:
        if title.replace(" ", "_") in result:
            continue
        try:
            r = requests.get(
                f"{EXPORT_URL}/{title}",
                params={"curonly": "1", "wpDownload": "1"},
                headers={"User-Agent": UA},
                timeout=60,
            )
            r.raise_for_status()
            root = ElementTree.fromstring(r.text)
            ns = "{http://www.mediawiki.org/xml/export-0.10/}"
            text_el = root.find(f"{ns}page/{ns}revision/{ns}text")
            if text_el is not None and text_el.text:
                result[title.replace(" ", "_")] = text_el.text
        except Exception as exc:  # noqa: BLE001
            print(f"   WARNING: could not fetch {title}: {exc}")
        time.sleep(0.3)

    return result


def resolve_redirects(texts: dict[str, str]) -> dict[str, str]:
    """Follow MediaWiki #REDIRECT entries to the real page title.

    The grammar point pages use short ASG* identifiers that redirect to a
    human-readable title; the real title is used for the entry, while the
    ASG* slug stays as the stable identifier.

    The space after REDIRECT is OPTIONAL. MediaWiki accepts both
    "#REDIRECT[[Target]]" and "#REDIRECT [[Target]]", and this wiki
    writes the first form. The pattern used to require the space, so
    every redirect was missed: 100 of the 506 grammar points kept
    their raw "ASG..." slug as the title and carried a summary that
    began with the literal text "REDIRECT". The learner saw a card
    titled "ASGOOCVO".

    >>> resolve_redirects({"ASGOOCVO": '#REDIRECT[[Expressing possession with "you"]]'})
    {'ASGOOCVO': 'Exposing_possession_with_"you"'}
    >>> resolve_redirects({"ASG1": '#REDIRECT [[Target page]]'})
    {'ASG1': 'Target_page'}
    >>> resolve_redirects({"ASG1": "A real page with content."})
    {'ASG1': 'ASG1'}
    """
    out: dict[str, str] = {}
    for slug, text in texts.items():
        m = re.match(r"^#REDIRECT\s*\[\[([^\]|]+)", text.strip())
        if m:
            target = m.group(1).strip().replace(" ", "_")
            out[slug] = target
        else:
            out[slug] = slug
    return out


def find_links(wikitext: str) -> list[str]:
    """Extract wiki page titles linked from a wikitext page."""
    out = []
    seen = set()
    for m in re.finditer(r"\[\[([^\]|]+)(?:\|[^\]]*)?\]\]", wikitext):
        target = m.group(1).strip()
        if not target or target.startswith("#"):
            continue
        if ":" in target and not target.startswith("Special:"):
            # skip Category:, File:, Template: namespace links
            head = target.split(":")[0]
            if head in ("Category", "File", "Template", "Help", "Main"):
                continue
        if target.startswith("Special:"):
            continue
        target = target.replace(" ", "_")
        if target in seen:
            continue
        seen.add(target)
        out.append(target)
    return out


def strip_wiki_markup(text: str) -> str:
    """Convert a chunk of wikitext to plain text."""
    text = re.sub(r"<!--.*?-->", "", text, flags=re.S)
    text = re.sub(r"\{\{[^{}]*\}\}", " ", text)
    text = re.sub(r"\{\{[^{}]*\}\}", " ", text)
    text = re.sub(r"''+", "", text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\[\[([^\]|]+)\|([^\]]+)\]\]", r"\2", text)
    text = re.sub(r"\[\[([^\]]+)\]\]", r"\1", text)
    text = re.sub(r"\[https?://\S+\s+([^\]]+)\]", r"\1", text)
    text = re.sub(r"\[https?://\S+\]", " ", text)
    text = re.sub(r"'{2,}", "", text)
    text = re.sub(r"[*#:;]+", " ", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


CJK = r"一-鿿㐀-䶿"
HANZI_RUN = re.compile(f"[{CJK}]+")
# a Chinese line that is a full example sentence (has punctuation or length>1)
EXAMPLE_LINE = re.compile(
    rf"^\s*([{CJK}]{{2,}}[。！？!?，,、；;：:]?)\s*$"
)
PINYIN_LINE = re.compile(
    r"^\s*([A-Za-zāáǎàēéěèīíǐìōóǒòūúǔùǖǘǚǜü\s]+)\s*$"
)
ENGLISH_LINE = re.compile(r"^\s*([A-Za-z][A-Za-z\s,'\"\-\(\):;,.!?]+)\s*$")

# The wiki writes an example on ONE line, with the pinyin and the English
# translation in inline spans:
#
#   *米饭 <em>太</em> 多 <em>了</em> 。<span class="pinyin">Mǐfàn ...</span>
#   <span class="trans">There is too much rice.</span>
#
# so the three-line pattern the older extractor looked for does not occur.
_INLINE_EXAMPLE = re.compile(
    rf"^\s*\*\s*(?P<zh>[{CJK}][^\n]*?)\s*"
    r"<span\s+class=\"pinyin\"\s*>(?P<pinyin>.*?)</span>"
    r"\s*<span\s+class=\"trans\"\s*>(?P<en>.*?)</span>",
    re.DOTALL,
)
_INLINE_PY_ONLY = re.compile(
    rf"^\s*\*\s*(?P<zh>[{CJK}][^\n]*?)\s*"
    r"<span\s+class=\"pinyin\"\s*>(?P<pinyin>.*?)</span>",
    re.DOTALL,
)


def _strip_markup(text: str) -> str:
    """Remove the wiki's inline markup from a run of text.

    <em>太</em> marks the part of the sentence the grammar point is about,
    and it is worth keeping in the plain text -- the emphasis is the
    teaching signal -- but the tags themselves are not.
    """
    text = re.sub(r"<[^>]+>", "", text)
    text = text.replace("&nbsp;", " ").replace("&amp;", "&")
    text = text.replace("&quot;", '"').replace("&#39;", "'")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def extract_examples(wikitext: str, char_readings: dict[str, list[str]]) -> list[dict]:
    """Pull example sentences (Chinese + pinyin + English) out of a page.

    The examples live in a <div class="liju"> block, one per line, with the
    pinyin and the translation in inline spans. Lines that do not follow
    that shape are ignored rather than guessed at.
    """
    examples: list[dict] = []

    for line in wikitext.split("\n"):
        m = _INLINE_EXAMPLE.match(line)
        if m:
            zh = _strip_markup(m.group("zh"))
            pinyin = _strip_markup(m.group("pinyin"))
            en = _strip_markup(m.group("en"))
            if len(zh) >= 2 and has_hanzi(zh):
                examples.append({
                    "zh": zh,
                    "pinyin": pinyin or guess_pinyin(zh, char_readings),
                    "en": en,
                })
            continue

        # A line with the Chinese and the pinyin but no translation.
        m = _INLINE_PY_ONLY.match(line)
        if m:
            zh = _strip_markup(m.group("zh"))
            pinyin = _strip_markup(m.group("pinyin"))
            if len(zh) >= 2 and has_hanzi(zh):
                examples.append({
                    "zh": zh,
                    "pinyin": pinyin or guess_pinyin(zh, char_readings),
                    "en": "",
                })

    # de-duplicate, keeping the first occurrence
    seen = set()
    out = []
    for ex in examples:
        key = (ex["zh"], ex["pinyin"], ex["en"])
        if key in seen:
            continue
        seen.add(key)
        out.append(ex)
    return out


def guess_pinyin(zh: str, char_readings: dict[str, list[str]]) -> str:
    """Build a per-character pinyin string for a Chinese example.

    Only used when the wiki does not supply the pinyin line.
    """
    parts = []
    for ch in zh:
        readings = char_readings.get(ch)
        if readings:
            parts.append(readings[0])
        else:
            parts.append("")
    return " ".join(p for p in parts if p)


def detect_level(title: str, categories: set[str]) -> str:
    for pat, level in LEVEL_PATTERNS:
        if pat.match(title):
            return level
    if "A1" in categories:
        return "A1"
    if "A2" in categories:
        return "A2"
    if "B1" in categories:
        return "B1"
    if "B2" in categories:
        return "B2"
    if "C1" in categories:
        return "C1"
    return ""


def detect_category(wikitext: str, title: str) -> str:
    """Work out the part-of-speech category from the page's headings."""
    text = strip_wiki_markup(wikitext)
    lowered = text.lower()
    # the "Contents" list on a level page names the categories
    for key, label in CATEGORY_HEADINGS.items():
        if key in lowered:
            return label
    # a level index page is itself a category list
    if title in LEVEL_PAGES:
        return "Grammar structure"
    return "Grammar"


def make_summary(wikitext: str) -> str:
    """First paragraph of the page, as a short summary."""
    text = strip_wiki_markup(wikitext)
    # skip the "Level / Similar to / Used for / Keywords" header block
    for para in text.split("\n"):
        p = para.strip()
        if len(p) < 20:
            continue
        if p.lower().startswith(("level", "similar to", "used for", "keywords",
                                  "contents", "see also", "structure", "examples")):
            continue
        # A page that is only a redirect has no summary of its own. Its
        # text is "#REDIRECT[[Target]]", and stripping the markup leaves
        # "REDIRECTExpressing possession with 'you'" -- which is what
        # 100 of the grammar points showed. The real page is fetched
        # separately, so an entry that falls back to the redirect text
        # gets no summary at all rather than a broken one.
        if p.upper().startswith("REDIRECT"):
            return ""
        return p[:400]
    return text[:400]


def main() -> int:
    ap = argparse.ArgumentParser(description="Scrape the Chinese Grammar Wiki")
    ap.add_argument(
        "--allow-degraded",
        action="store_true",
        help="carry on when an input is missing, with a warning "
             "(the output is then NOT fit for the app)",
    )
    args = ap.parse_args()
    if args.allow_degraded:
        _guards.set_allow_degraded()

    os.makedirs(CACHE, exist_ok=True)
    os.makedirs(DATA, exist_ok=True)

    print("fetching index pages ...")
    wikitext = fetch_wikitext_titles(INDEX_PAGES)
    print(f"  got {len(wikitext)} index pages")
    if not wikitext:
        print("ERROR: no wikitext retrieved")
        return 1

    # discover the grammar point pages: the level index pages build their
    # tables with Semantic MediaWiki queries, so the ASG* list only exists
    # in the rendered HTML
    targets: set[str] = set()
    titles_by_slug: dict[str, str] = {}
    for page in LEVEL_PAGES:
        links = fetch_rendered_links(WIKI_BASE + page)
        fetch_rendered_links_cache[page] = links
        found = 0
        for text, slug in links:
            if slug.startswith("ASG"):
                targets.add(slug)
                titles_by_slug[slug] = text
                found += 1
        print(f"  {page}: {found} grammar points")
    print(f"  discovered {len(targets)} grammar point pages")
    # Zero discovered points is the signature of a failed scrape, not of an
    # empty wiki: the level index pages build their tables with Semantic
    # MediaWiki queries, so without BeautifulSoup (or with a blocked
    # request) the ASG* list simply is not in the HTML. Carrying on here
    # produced a grammar.json with 11 points instead of 506, and that
    # degraded file is what shipped.
    if not targets:
        _guards.require_ok(
            False,
            "no grammar point pages were discovered (this is a failed scrape, "
            "not an empty wiki)",
            "python pipeline/04_build_grammar.py",
        )

    print("fetching grammar point pages ...")
    point_text = fetch_wikitext_titles(sorted(targets))
    print(f"  got {len(point_text)} pages")

    # the ASG* slugs redirect to human-readable titles; fetch those too
    redirects = resolve_redirects(point_text)
    real_titles = {t for t in redirects.values() if t != t.replace(" ", "_")}
    real_titles = {t for slug, t in redirects.items() if t != slug}
    if real_titles:
        print(f"fetching {len(real_titles)} redirect target pages ...")
        real_text = fetch_wikitext_titles(sorted(real_titles))
        print(f"  got {len(real_text)} pages")
    else:
        real_text = {}

    # load the per-character readings for the pinyin fallback
    char_readings: dict[str, list[str]] = {}
    cr_path = os.path.join(RAW, "char_readings.json")
    if os.path.exists(cr_path):
        with open(cr_path, encoding="utf-8") as fh:
            char_readings = json.load(fh)

    entries = []
    for slug, text in point_text.items():
        target = redirects.get(slug, slug)
        body = real_text.get(target, text)
        if len(body.strip()) < 200 and target in real_text:
            body = real_text[target]
        source_url = WIKI_BASE + slug
        categories = set()
        for m in re.finditer(r"\[\[Category:([^\]|]+)", body):
            categories.add(m.group(1).strip())
        level = detect_level(slug, categories)
        if not level:
            # record the level whose index page links to this point
            for page in LEVEL_PAGES:
                links = fetch_rendered_links_cache.get(page, [])
                if any(s == slug for _t, s in links):
                    level = LEVEL_PAGES[page]
                    break
        category = detect_category(body, slug)
        examples = extract_examples(body, char_readings)
        entries.append({
            "slug": slug,
            "title": target.replace("_", " ") if target != slug else slug.replace("_", " "),
            "level": level,
            "category": category,
            "summary": make_summary(body),
            "wiki_text": body,
            "examples": examples,
            "source_url": source_url,
        })

    # also record the level index pages themselves
    for title, text in wikitext.items():
        slug = title.replace(" ", "_")
        entries.append({
            "slug": slug,
            "title": slug.replace("_", " "),
            "level": LEVEL_PAGES.get(title, ""),
            "category": "Grammar index",
            "summary": make_summary(text),
            "wiki_text": text,
            "examples": extract_examples(text, char_readings),
            "source_url": WIKI_BASE + slug,
        })

    # sort: level, then category, then title
    def sort_key(e):
        lv = e["level"] or "ZZ"
        return (lv, e["category"], e["title"])

    entries.sort(key=sort_key)

    meta = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "source": "Chinese Grammar Wiki (AllSet Learning)",
        "source_url": WIKI_BASE,
        "license": LICENSE,
        "retrieval_method": (
            "MediaWiki Special:Export (api.php is blocked by Cloudflare from this "
            "host and returns HTTP 403)"
        ),
        "entry_count": len(entries),
        "example_count": sum(len(e["examples"]) for e in entries),
        "levels": sorted({e["level"] for e in entries if e["level"]}),
        "categories": sorted({e["category"] for e in entries}),
    }

    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump({"meta": meta, "entries": entries}, fh, ensure_ascii=False, indent=1)

    print("\nsample entries:")
    for e in entries[:4]:
        print(f"   {e['slug']}  level={e['level']}  cat={e['category']}  "
              f"examples={len(e['examples'])}")
        for ex in e["examples"][:2]:
            print(f"       {ex['zh']} | {ex['pinyin']} | {ex['en'][:50]}")

    print()
    print(f"SUMMARY 04_build_grammar: entries={len(entries)} out={OUT}")
    print(f"   examples={meta['example_count']}  levels={meta['levels']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
