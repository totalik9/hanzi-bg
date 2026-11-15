"""Fetch the Chinese Grammar Wiki from the Wayback Machine.

Why this exists
---------------
The Grammar Wiki is behind a Cloudflare rule that answers every request
with an interstitial challenge:

    HTTP/2 403
    cf-mitigated: challenge
    server: cloudflare

That includes api.php, Special:Export, the rendered pages and the
browser User-Agents -- a headless Chromium gets the same "Just a moment..."
page. The site itself is alive (robots.txt answers 200), so this is a
bot-mitigation rule and not an outage, but the pipeline cannot get
through it with plain HTTP.

The Internet Archive has snapshots of the wiki, and those snapshots are
the SAME pages the pipeline was written for: the level index pages with
their tables of grammar points, and the grammar point pages with their
``<div class="liju">`` example blocks. The markup is identical, so the
extractors in 04_build_grammar.py work on them unchanged.

What is different in a snapshot
-------------------------------
* The links inside a snapshot are rewritten to point at the archive:
  ``/web/<timestamp>/https://resources.allsetlearning.com/...``. The
  helpers here undo that, so the slugs come out the same as they do
  from the live site.
* A snapshot is the RENDERED page, not the wikitext. The examples are
  therefore in the HTML (``<span class="pinyin">`` and
  ``<span class="trans">``) instead of in the wiki markup. The extractor
  reads the same two spans the wikitext extractor reads, so the output
  is the same shape.

The licence travels with the content
------------------------------------
The wiki is licensed CC BY-NC-SA 3.0: it may be reused with attribution
but NOT commercially, and the wiki's own copyright page says so in
those words ("may not be used for commercial purposes"). The archive
serves the content under the same terms -- it is a mirror of the
original, and the licence belongs to the content, not to the host. The
attribution and the licence string that go into the database are
therefore the same ones the live scrape records.
"""

from __future__ import annotations

import re
import time
from xml.etree import ElementTree

import requests

# The Internet Archive rewrites every link inside a snapshot to point at
# the archive. These patterns cover the forms it uses.
_WAYBACK_PREFIX = re.compile(r"^/web/\d+[a-z_]*/")
_ORIGIN = "https://resources.allsetlearning.com"

# The MediaWiki export namespace.
_MW_NS = "{http://www.mediawiki.org/xml/export-0.10/}"

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)

# The archive's own answer for "I do not have this page".
_NOT_FOUND_MARKERS = (
    "Hrmm. This page doesn't exist",
    "has not been archived",
    "Got an HTTP 302 response at crawl time",
)

# The archive answers 429 when it is asked for too much at once. The
# pipeline fetches several hundred pages, so it has to go slowly, and
# it has to back off when the archive says no rather than give up:
# without the backoff the run collected zero pages and the content
# database could not be built at all.
_DELAY_SECONDS = 3.0
_MAX_DELAY_SECONDS = 60.0

# The pause between requests. It is shared by every request in the run
# and it grows when the archive answers 429, so the whole run slows
# down rather than only the request that was refused.
_CURRENT_DELAY = _DELAY_SECONDS


def _get(url: str, timeout: int = 90, attempts: int = 5) -> str | None:
    """GET a URL and return the body, or None when it is not usable.

    The archive answers 429 when it is asked for too much at once. That
    is a "come back later", not a "no": the request is retried with a
    growing pause, and the pause is shared by every request so the
    whole run slows down rather than only the one that was refused.
    """
    global _CURRENT_DELAY

    for attempt in range(attempts):
        try:
            r = requests.get(url, headers={"User-Agent": _UA}, timeout=timeout)
        except Exception as exc:  # noqa: BLE001
            print(f"   WAYBACK: could not fetch {url}: {exc}")
            return None

        if r.status_code == 200:
            text = r.text
            for marker in _NOT_FOUND_MARKERS:
                if marker in text:
                    print(f"   WAYBACK: no snapshot for {url}")
                    return None
            # A successful request means the archive is keeping up
            # again, so the shared pause goes back to its floor.
            _CURRENT_DELAY = _DELAY_SECONDS
            return text

        if r.status_code == 429:
            _CURRENT_DELAY = min(_MAX_DELAY_SECONDS, max(_CURRENT_DELAY * 2, _DELAY_SECONDS))
            wait = _CURRENT_DELAY
            print(f"   WAYBACK: 429 (rate limited); waiting {wait:.0f}s "
                  f"[attempt {attempt + 1}/{attempts}]")
            time.sleep(wait)
            continue

        print(f"   WAYBACK: {r.status_code} for {url}")
        return None

    print(f"   WAYBACK: gave up on {url} after {attempts} attempts")
    return None


def polite_sleep() -> None:
    """Wait between requests so the archive does not answer 429."""
    time.sleep(_CURRENT_DELAY)


def _slug_from_href(href: str) -> str:
    """The page slug out of a link, with the archive's rewriting undone.

    >>> _slug_from_href("/chinese/grammar/ASG04ZCI")
    'ASG04ZCI'
    >>> _slug_from_href("/web/20260930135804/https://resources.allsetlearning.com/chinese/grammar/ASG04ZCI")
    'ASG04ZCI'
    >>> _slug_from_href("/web/20260930135804id_/https://resources.allsetlearning.com/chinese/grammar/A1_grammar_points")
    'A1_grammar_points'
    """
    href = _WAYBACK_PREFIX.sub("", href)
    marker = "/chinese/grammar/"
    if marker in href:
        href = href.split(marker, 1)[1]
    href = href.split("#", 1)[0]
    href = href.split("?", 1)[0]
    return href.strip("/")


def snapshot_url(slug: str, timestamp: str | None = None) -> str:
    """The archive URL for a wiki page.

    Without a timestamp the archive picks the most recent snapshot.
    """
    page = f"{_ORIGIN}/chinese/grammar/{slug}"
    if timestamp:
        return f"http://web.archive.org/web/{timestamp}/{page}"
    return f"http://web.archive.org/web/2026/{page}"


def fetch_page(slug: str, attempts: int = 5) -> str | None:
    """The rendered HTML of one wiki page, from the archive."""
    return _get(snapshot_url(slug), attempts=attempts)


def content_div(html: str) -> str:
    """The part of the page that holds the article.

    The wiki's chrome (navigation, footer, scripts) is not part of the
    content and would poison the link and heading extraction. The
    article starts at the ``mw-content-text`` div and ends where the
    category links start.
    """
    start = re.search(r'<div[^>]*id="mw-content-text"[^>]*>', html)
    if not start:
        return html
    seg = html[start.end():]
    end = re.search(r'<div id="catlinks|<div class="printfooter', seg)
    return seg[: end.start()] if end else seg


def level_index_links(html: str) -> list[tuple[str, str]]:
    """The (title, slug) of every grammar point linked from a level page.

    The level index pages build their tables with Semantic MediaWiki
    queries, so the ASG* list only exists in the rendered HTML -- which
    is exactly what a snapshot holds.
    """
    seg = content_div(html)
    out: list[tuple[str, str]] = []
    seen: set[str] = set()
    for m in re.finditer(
        r'href="([^"]*?/chinese/grammar/(ASG[0-9A-Za-z]+))"[^>]*>(.*?)</a>',
        seg,
        re.S,
    ):
        slug = _slug_from_href(m.group(1))
        if not slug.startswith("ASG") or slug in seen:
            continue
        title = re.sub(r"<[^>]+>", "", m.group(3))
        title = re.sub(r"\s+", " ", title).strip()
        seen.add(slug)
        out.append((title, slug))
    return out


def headings(html: str) -> list[str]:
    """The section headings of a page, in order."""
    seg = content_div(html)
    out = []
    for m in re.finditer(r"<h([2-4])>(.*?)</h\1>", seg, re.S):
        text = re.sub(r"<[^>]+>", "", m.group(2))
        text = re.sub(r"\s+", " ", text).strip()
        if text:
            out.append(text)
    return out


def examples_from_html(html: str) -> list[dict]:
    """The example sentences of a page, from the rendered HTML.

    The wikitext and the rendered page carry the same three fields; the
    rendered form uses inline spans:

        <li>我 家 <em>有</em> 很 多 小 狗。<span class="pinyin">...</span>
            <span class="trans">There are a lot of puppies...</span></li>

    so the same span names are read here as in the wikitext extractor.
    The Chinese part carries <em> tags (they mark the part of the
    sentence the grammar point is about), so it is matched loosely and
    the tags are stripped afterwards.
    """
    seg = content_div(html)
    out: list[dict] = []
    seen: set[tuple[str, str, str]] = set()

    for block in re.finditer(
        r"<li>(?P<body>.*?)</li>", seg, re.S
    ):
        body = block.group("body")
        pm = re.search(
            r'<span\s+class="pinyin"\s*>(?P<pinyin>.*?)</span>', body, re.S
        )
        if not pm:
            continue
        tm = re.search(
            r'<span\s+class="trans"\s*>(?P<en>.*?)</span>', body, re.S
        )
        zh = _clean(body[: pm.start()])
        pinyin = _clean(pm.group("pinyin"))
        en = _clean(tm.group("en")) if tm else ""
        if len(zh) < 2:
            continue
        key = (zh, pinyin, en)
        if key in seen:
            continue
        seen.add(key)
        out.append({"zh": zh, "pinyin": pinyin, "en": en})
    return out


def _clean(text: str) -> str:
    """Strip the wiki's inline markup and collapse the whitespace."""
    text = re.sub(r"<[^>]+>", "", text)
    text = text.replace("&nbsp;", " ").replace("&amp;", "&")
    text = text.replace("&quot;", '"').replace("&#39;", "'")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def summary_from_html(html: str) -> str:
    """The first real paragraph of a page, as a short summary."""
    seg = content_div(html)
    # The page opens with a header block: Level / Similar to / Used for
    # / Keywords. Those are not the summary.
    text = re.sub(r"<[^>]+>", "\n", seg)
    text = text.replace("&nbsp;", " ").replace("&amp;", "&")
    text = text.replace("&quot;", '"').replace("&#39;", "'")
    for para in text.split("\n"):
        p = re.sub(r"\s+", " ", para).strip()
        if len(p) < 20:
            continue
        low = p.lower()
        if low.startswith(("level", "similar to", "used for", "keywords",
                           "contents", "see also", "structure", "examples",
                           "grammar point", "pattern", "source")):
            continue
        return p[:400]
    return ""


def fetch_export(slug: str) -> str | None:
    """The wikitext of a page, if the archive happens to hold the export.

    The archive does not hold the Special:Export responses, so this is
    normally None. It is kept because a future crawl might have one,
    and the wikitext is a better source than the rendered page.
    """
    body = _get(
        f"http://web.archive.org/web/2026id_/{_ORIGIN}/chinese/grammar/"
        f"Special:Export/{slug}?curonly=1&wpDownload=1"
    )
    if not body:
        return None
    try:
        root = ElementTree.fromstring(body)
    except ElementTree.ParseError:
        return None
    text_el = root.find(f"{_MW_NS}page/{_MW_NS}revision/{_MW_NS}text")
    if text_el is None or not text_el.text:
        return None
    return text_el.text
