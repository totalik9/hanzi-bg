"""Scrape the Chinese Grammar Wiki (AllSet Learning) into data/grammar.json.

Source: https://resources.allsetlearning.com/chinese/grammar/ - Creative Commons
BY-NC-SA 3.0 licensed, organised by part of speech and CEFR/HSK difficulty
level. See the LICENCE note below: the wiki may not be used commercially.

The MediaWiki api.php is behind a Cloudflare rule that rejects api.php requests
(403) from this host, so the raw wikitext is fetched with MediaWiki's
Special:Export endpoint instead, which serves the same revision text as XML.
The script tries api.php first and falls back to Special:Export.

Cloudflare now challenges the WHOLE site, not just api.php: the rendered
pages answer 403 with "cf-mitigated: challenge" too, for every User-Agent,
including a headless browser. The site is alive (robots.txt answers 200),
so this is bot mitigation rather than an outage -- but the pipeline cannot
get through it with plain HTTP.

So there is a second source: the Internet Archive. The archive holds
snapshots of the level index pages and of the grammar point pages, with the
same markup, and _grammar_wayback.py reads them. The live site is tried
first and the archive is the fallback, so the pipeline keeps working when
Cloudflare's rule changes and when the archive has a fresher snapshot.

Output: data/grammar.json
    {
      "meta": {...},
      "entries": [ {slug, title, level, category, summary, wiki_text,
                    examples: [{zh, pinyin, en}], source_url}, ... ]
    }

The raw wikitext is kept in every entry so a human can verify the extraction.

Usage:
    python pipeline/04_build_grammar.py
    python pipeline/04_build_grammar.py --source wayback   # force the archive
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
    "Chinese Grammar Wiki by AllSet Learning (John Pasden), "
    "Creative Commons BY-NC-SA 3.0 licensed - non-commercial, attribution "
    "required - see https://resources.allsetlearning.com/chinese/grammar/"
)

# The licence is not a formality: the wiki's own copyright page says the
# content "may not be used for commercial purposes or without
# attribution", and it asks for a link to
# https://resources.allsetlearning.com/chinese/grammar/ on every page where
# the content appears. The app ships the grammar inside the APK, so the
# attribution has to travel with it -- it is in sources.json, in the
# content database manifest, and on the app's "about the content" screen.
#
# The non-commercial half is the reason the licence is recorded in full
# rather than as "Creative Commons": it is the same constraint that
# blocked the translation model until it was replaced with the MIT
# licensed M2M-100.
LICENSE_SPDX = "CC-BY-NC-SA-3.0"

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


# The per-character readings, for the pinyin fallback in the example
# extractor. They are loaded once, before the pages are read, because
# both sources need them.
CHAR_READINGS: dict[str, list[str]] = {}


# --- the two sources -----------------------------------------------------
#
# A "source" knows how to fetch a wiki page and how to read the grammar
# points out of it. The live site serves the wikitext; the archive serves
# the rendered page. Both are reduced to the same shape by the code
# below, so the rest of the script does not know which one it used.


class LiveSource:
    """The wiki itself: wikitext over Special:Export, links over HTML."""

    name = "live"
    retrieval_method = (
        "MediaWiki Special:Export (api.php is blocked by Cloudflare from this "
        "host and returns HTTP 403)"
    )

    def index_pages(self) -> dict[str, str]:
        return fetch_wikitext_titles(INDEX_PAGES)

    def rendered_links(self, page: str) -> list[tuple[str, str]]:
        return fetch_rendered_links(WIKI_BASE + page)

    def point_pages(self, slugs: list[str]) -> dict[str, str]:
        return fetch_wikitext_titles(slugs)

    def extract(self, slug: str, body: str) -> tuple[str, list[dict]]:
        """The summary and the examples of a page, from its wikitext."""
        return make_summary(body), extract_examples(body, CHAR_READINGS)


class WaybackSource:
    """The Internet Archive: rendered HTML instead of wikitext.

    Cloudflare challenges every request to the live site, so this is
    one of the sources that can work from a plain HTTP client. The
    snapshots are the same pages with the same markup, so the
    extraction produces the same output.

    The archive is the SLOWEST of the fallbacks: it answers 429 when
    it is asked for too much at once, and a run that fetches 506
    pages one at a time collects almost nothing before it gives up.
    The mirror is the one that works in practice, and the archive is
    kept for the level index pages, which the mirror does not have.
    """

    name = "wayback"
    retrieval_method = (
        "Internet Archive snapshots of the Chinese Grammar Wiki "
        "(the live site is behind a Cloudflare challenge that answers "
        "every request with HTTP 403)"
    )

    def __init__(self) -> None:
        import _grammar_wayback

        self._w = _grammar_wayback

    def index_pages(self) -> dict[str, str]:
        """The index pages, as their rendered HTML.

        The archive has no Special:Export snapshot, so the index pages
        come back as HTML. They are only used for the table of contents
        and the meta block, so HTML is enough.
        """
        out: dict[str, str] = {}
        for page in INDEX_PAGES:
            html = self._w.fetch_page(page)
            if html:
                out[page.replace(" ", "_")] = html
            self._w.polite_sleep()
        return out

    def rendered_links(self, page: str) -> list[tuple[str, str]]:
        html = self._w.fetch_page(page)
        if not html:
            return []
        self._w.polite_sleep()
        return self._w.level_index_links(html)

    def point_pages(self, slugs: list[str]) -> dict[str, str]:
        out: dict[str, str] = {}
        for slug in slugs:
            html = self._w.fetch_page(slug)
            if html:
                out[slug] = html
            self._w.polite_sleep()
        return out

    def extract(self, slug: str, body: str) -> tuple[str, list[dict]]:
        """The summary and the examples of a page, from its HTML."""
        return (
            self._w.summary_from_html(body),
            self._w.examples_from_html(body),
        )


class MirrorSource:
    """The ivankra/asg mirror on GitHub: the raw wikitext.

    This is the source that works. The mirror holds the wikitext of
    every grammar point, one file per point, and the whole mirror
    arrives in ONE request of about 750 kB -- so the pipeline fetches
    506 pages in a single download instead of 506 requests that the
    archive would rate-limit into nothing.

    The wikitext is the same text the live site serves over
    Special:Export, so the extractors work on it unchanged. That was
    checked against the shipped content database: 489 of the 489
    grammar points that the shipped database and the mirror have in
    common agree on their level AND on their category, point for
    point.

    The level index pages are not in the mirror, so they come from the
    archive (eight requests) or from the live site. They carry the
    level of the points whose own wikitext does not have a level
    category -- 63 of the 506.
    """

    name = "mirror"
    retrieval_method = (
        "GitHub mirror of the Chinese Grammar Wiki (ivankra/asg), which "
        "holds the raw wikitext of every grammar point; the live site is "
        "behind a Cloudflare challenge that answers every request with "
        "HTTP 403"
    )

    def __init__(self) -> None:
        import _grammar_mirror

        self._m = _grammar_mirror
        self._tarball: bytes | None = None
        self._pages: dict[str, str] = {}
        self._titles: dict[str, str] = {}
        self._level_map: dict[str, list[str]] | None = None

    def _load(self) -> None:
        if self._pages:
            return
        self._tarball = self._m.fetch_tarball()
        self._pages = self._m.read_mirror(self._tarball)
        self._titles = self._m.read_index(self._tarball)

    def index_pages(self) -> dict[str, str]:
        """The level index pages.

        They are not in the mirror, and they are not needed: the level
        of every point is in the checked-in mapping
        (pipeline/reference/grammar_levels.json), which was read from the
        index pages and is kept in version control.

        The index pages are still fetched when they can be, because
        they are the authority on the level and a fresh copy is newer
        than the checked-in one. But the pipeline does not depend on
        them: the Internet Archive rate-limits hard enough that a fresh
        clone cannot count on getting eight pages out of it.
        """
        self._load()
        out: dict[str, str] = {}
        for page in INDEX_PAGES:
            # Only the level index pages matter here: they carry the
            # grammar points. Main_Page and New_Main_Page are the
            # wiki's front doors, and they hold no points -- so they
            # are not worth a request the archive will rate-limit.
            if page not in LEVEL_PAGES:
                continue
            html = fetch_rendered_page(page, attempts=1)
            if html:
                out[page.replace(" ", "_")] = html
        return out

    def rendered_links(self, page: str) -> list[tuple[str, str]]:
        """The grammar points of a level.

        The checked-in mapping is the authority: it was read from the
        level index pages themselves. The mirror's own level
        categories are the fallback, and the two agree for every point
        that has both.
        """
        self._load()
        level = LEVEL_PAGES.get(page, "")
        if not level:
            return []
        out = []
        for slug, text in sorted(self._pages.items()):
            if self.level_of(slug) == level:
                out.append((self._m.title_of(text) or slug, slug))
        return out

    def level_of(self, slug: str) -> str:
        """The level of a grammar point.

        The checked-in mapping first, then the point's own category.
        """
        if self._level_map is None:
            self._level_map = self._m.read_levels()
        mapped = self._m.level_from_map(slug, self._level_map)
        if mapped:
            return mapped
        return self._m.level_of(self._pages.get(slug, ""))

    def point_pages(self, slugs: list[str]) -> dict[str, str]:
        self._load()
        return {slug: self._pages[slug] for slug in slugs if slug in self._pages}

    def title_of(self, slug: str) -> str:
        """The title of a grammar point."""
        self._load()
        return self._m.title_of(self._pages.get(slug, "")) or self._titles.get(slug, "")

    def extract(self, slug: str, body: str) -> tuple[str, list[dict]]:
        """The summary and the examples of a page, from its wikitext."""
        return make_summary(body), extract_examples(body, CHAR_READINGS)



def _links_from_index_html(html: str) -> list[tuple[str, str]]:
    """The (title, slug) of the grammar points linked from an index page.

    The level index pages build their tables with Semantic MediaWiki
    queries, so the ASG* list only exists in the rendered HTML. The
    links are read out of the HTML directly, whether the HTML came
    from the live site or from an archive snapshot -- the archive
    rewrites the hrefs, and the slugs are taken from the tail of the
    link either way.
    """
    out: list[tuple[str, str]] = []
    seen: set[str] = set()
    for m in re.finditer(
        r'href="([^"]*?/chinese/grammar/(ASG[0-9A-Za-z]+))"[^>]*>(.*?)</a>',
        html,
        re.S,
    ):
        href = m.group(1)
        slug = href.split("/chinese/grammar/", 1)[1].split("#", 1)[0]
        slug = slug.split("?", 1)[0].strip("/")
        if not slug.startswith("ASG") or slug in seen:
            continue
        title = re.sub(r"<[^>]+>", "", m.group(3))
        title = re.sub(r"\s+", " ", title).strip()
        seen.add(slug)
        out.append((title, slug))
    return out


def fetch_rendered_page(page: str, attempts: int = 1) -> str | None:
    """The rendered HTML of a level index page.

    The live site is tried first and the Internet Archive is the
    fallback. The archive holds a snapshot of every level index page,
    and there are only eight of them, so the rate limiting does not
    bite -- but the archive is slow to answer for a page it has not
    served recently, so the answer is cached on disk. The index pages
    change a few times a year, and a cached copy is better than a
    pipeline that takes ten minutes to start.

    The cache is keyed by the page name and holds the body of a
    successful fetch, so a run that has the cache does not talk to
    the archive at all.

    The archive is given a limited number of attempts on purpose. A
    page that the archive will not serve is not worth waiting for:
    the level index pages are what matters, and they are eight
    requests, not twenty.
    """
    cache_file = os.path.join(CACHE, f"index_{page}.html")
    if os.path.exists(cache_file):
        with open(cache_file, encoding="utf-8") as fh:
            body = fh.read()
        if body.strip():
            return body

    body = None
    try:
        r = requests.get(WIKI_BASE + page, headers={"User-Agent": UA}, timeout=60)
        if r.status_code == 200 and "mw-content-text" in r.text:
            body = r.text
    except Exception as exc:  # noqa: BLE001
        print(f"   the live page {page} failed: {exc}")

    if body is None:
        try:
            import _grammar_wayback

            body = _grammar_wayback.fetch_page(page, attempts=attempts)
        except Exception as exc:  # noqa: BLE001
            print(f"   the archived page {page} failed: {exc}")
            return None

    if body:
        os.makedirs(CACHE, exist_ok=True)
        with open(cache_file, "w", encoding="utf-8") as fh:
            fh.write(body)
    return body


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


def load_char_readings() -> dict[str, list[str]]:
    """The per-character readings, for the pinyin fallback."""
    cr_path = os.path.join(RAW, "char_readings.json")
    if os.path.exists(cr_path):
        with open(cr_path, encoding="utf-8") as fh:
            return json.load(fh)
    return {}


def _title_from_rendered(body: str) -> str:
    """The title of a rendered grammar point page.

    The live source gets the title from the #REDIRECT the ASG* slug
    carries; the archive serves the rendered page, which has no
    redirect but does have the title as the first heading:

        <h1><span class="mw-headline" id="Expressing_possession_with_...">

    The heading text is the human-readable title, with the underscores
    the wiki uses turned back into spaces.
    """
    m = re.search(
        r'<h1[^>]*>\s*<span[^>]*id="([^"]+)"', body
    )
    if m:
        title = m.group(1).replace("_", " ").strip()
        if title:
            return title
    # Some pages put the title in a plain <h1>.
    m = re.search(r"<h1[^>]*>(.*?)</h1>", body, re.S)
    if m:
        title = re.sub(r"<[^>]+>", "", m.group(1))
        title = re.sub(r"\s+", " ", title).strip()
        if title:
            return title.replace("_", " ")
    return ""


def collect(source, pages: list[str]) -> tuple[dict[str, str], dict[str, str]]:
    """Fetch the index pages and the grammar points from a source.

    Returns (index_pages, point_pages).
    """
    index_pages = source.index_pages()
    print(f"  got {len(index_pages)} index pages")

    # The level index pages build their tables with Semantic MediaWiki
    # queries, so the ASG* list only exists in the rendered HTML. The
    # index pages are read separately from the source's own point
    # listing, because they are the authority on which point belongs
    # to which level: 63 of the 506 points carry no level category of
    # their own, and the index pages are the only place their level
    # is written down.
    targets: set[str] = set()
    titles_by_slug: dict[str, str] = {}
    for page in LEVEL_PAGES:
        html = index_pages.get(page)
        links = _links_from_index_html(html) if html else []
        if links:
            fetch_rendered_links_cache[page] = links
        else:
            links = source.rendered_links(page)
            fetch_rendered_links_cache[page] = links
        found = 0
        for text, slug in links:
            if slug.startswith("ASG"):
                targets.add(slug)
                titles_by_slug[slug] = text
                found += 1
        print(f"  {page}: {found} grammar points")
    print(f"  discovered {len(targets)} grammar point pages")

    point_pages = source.point_pages(sorted(targets))
    print(f"  got {len(point_pages)} pages")
    return index_pages, point_pages


def main() -> int:
    ap = argparse.ArgumentParser(description="Scrape the Chinese Grammar Wiki")
    ap.add_argument(
        "--allow-degraded",
        action="store_true",
        help="carry on when an input is missing, with a warning "
             "(the output is then NOT fit for the app)",
    )
    ap.add_argument(
        "--source",
        choices=["auto", "live", "mirror", "wayback"],
        default="auto",
        help="where to read the wiki from: the live site, the GitHub "
             "mirror, the Internet Archive, or the live site with the "
             "mirror and the archive as fallbacks (the default)",
    )
    args = ap.parse_args()
    if args.allow_degraded:
        _guards.set_allow_degraded()

    os.makedirs(CACHE, exist_ok=True)
    os.makedirs(DATA, exist_ok=True)

    global CHAR_READINGS
    CHAR_READINGS = load_char_readings()

    # The live site is tried first: it has the newest content and it is
    # the source the licence names. It is behind a Cloudflare challenge
    # at the moment, so the archive is the fallback -- and it is not a
    # degraded source: the snapshots are the same pages, and the
    # attribution and the licence are identical.
    if args.source == "wayback":
        sources = [WaybackSource()]
    elif args.source == "live":
        sources = [LiveSource()]
    elif args.source == "mirror":
        sources = [MirrorSource()]
    else:
        # The live site first: it has the newest content and it is the
        # source the licence names. Then the mirror, which holds the
        # same wikitext in one download. Then the archive, which holds
        # the same pages but one request at a time and rate-limits
        # hard enough to collect nothing.
        sources = [LiveSource(), MirrorSource(), WaybackSource()]

    source = None
    index_pages: dict[str, str] = {}
    point_pages: dict[str, str] = {}
    targets: set[str] = set()

    for candidate in sources:
        print(f"fetching index pages from {candidate.name} ...")
        index_pages, point_pages = collect(candidate, INDEX_PAGES)
        targets = {
            slug
            for page in LEVEL_PAGES
            for _t, slug in fetch_rendered_links_cache.get(page, [])
            if slug.startswith("ASG")
        }
        if targets and point_pages:
            source = candidate
            break
        print(f"  the {candidate.name} source did not deliver; trying the next one")

    if source is None:
        print("ERROR: no grammar source delivered the wiki")
        _guards.require_ok(
            False,
            "the grammar wiki could not be read from either the live site "
            "or the Internet Archive",
            "python pipeline/04_build_grammar.py",
        )
        return 1

    print(f"using the {source.name} source")

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

    # The live source serves the wikitext, where the ASG* slugs are
    # redirects to human-readable titles; the redirect target has the
    # real content, so it is fetched too. The archive serves the
    # rendered page, where the slug page IS the content, so there is
    # nothing to follow.
    point_text = point_pages
    real_text: dict[str, str] = {}
    redirects: dict[str, str] = {}
    if isinstance(source, LiveSource):
        redirects = resolve_redirects(point_text)
        real_titles = {t for slug, t in redirects.items() if t != slug}
        if real_titles:
            print(f"fetching {len(real_titles)} redirect target pages ...")
            real_text = fetch_wikitext_titles(sorted(real_titles))
            print(f"  got {len(real_text)} pages")
    else:
        # The rendered page carries the real title in its heading, so
        # the title is taken from there rather than from a redirect.
        redirects = {
            slug: _title_from_rendered(body) or slug
            for slug, body in point_text.items()
        }
        if isinstance(source, MirrorSource):
            # The mirror's own index holds the titles.
            redirects = {
                slug: source.title_of(slug) or slug
                for slug in point_text
            }

    char_readings = CHAR_READINGS

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
        if not level and isinstance(source, MirrorSource):
            # The mirror knows the level from the checked-in mapping,
            # which was read from the level index pages.
            level = source.level_of(slug)
        if not level:
            # record the level whose index page links to this point
            for page in LEVEL_PAGES:
                links = fetch_rendered_links_cache.get(page, [])
                if any(s == slug for _t, s in links):
                    level = LEVEL_PAGES[page]
                    break
        category = detect_category(body, slug)
        summary, examples = source.extract(slug, body)
        entries.append({
            "slug": slug,
            "title": target.replace("_", " ") if target != slug else slug.replace("_", " "),
            "level": level,
            "category": category,
            "summary": summary,
            "wiki_text": body,
            "examples": examples,
            "source_url": source_url,
        })

    # also record the level index pages themselves
    for title, text in index_pages.items():
        slug = title.replace(" ", "_")
        summary, examples = source.extract(slug, text)
        entries.append({
            "slug": slug,
            "title": slug.replace("_", " "),
            "level": LEVEL_PAGES.get(title, ""),
            "category": "Grammar index",
            "summary": summary,
            "wiki_text": text,
            "examples": examples,
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
        "license_spdx": LICENSE_SPDX,
        "license_url": "https://creativecommons.org/licenses/by-nc-sa/3.0/",
        "retrieval_method": source.retrieval_method,
        "retrieval_source": source.name,
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
    print(f"   source={source.name}  license={LICENSE_SPDX}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
