"""Fetch the Chinese Grammar Wiki from the ivankra/asg mirror on GitHub.

Why this exists
---------------
The Grammar Wiki is behind a Cloudflare rule that answers every request
with an interstitial challenge:

    HTTP/2 403
    cf-mitigated: challenge
    server: cloudflare

That includes api.php, Special:Export, the rendered pages and every
browser User-Agent -- a headless Chromium gets the same "Just a moment..."
page. The site itself is alive (robots.txt answers 200), so this is
bot mitigation and not an outage, but the pipeline cannot get through
it with plain HTTP.

There is a mirror of the wiki on GitHub: github.com/ivankra/asg. It
holds the RAW WIKITEXT of every grammar point, one file per point:

    wiki/ASG04ZCI.txt
    wiki/index.tsv          the point ids and their titles
    LICENSE                 Creative Commons BY-NC-SA 3.0

The wikitext is the SAME text the live site serves over
Special:Export, so the extractors in 04_build_grammar.py work on it
unchanged -- the examples, the summaries and the level categories all
come out of it exactly as they do from the live site. That was checked
against the shipped content database, point for point.

The licence is the same one the original wiki carries
(CC BY-NC-SA 3.0), and the mirror says so itself, so nothing about the
terms changes by reading the mirror instead of the site. The mirror is
older than the live wiki -- it was last pushed in 2023 -- so the live
site is still preferred when it can be reached, and the mirror is the
fallback.

How the pages are fetched
-------------------------
The whole mirror is ONE tarball, about 750 kB:

    https://codeload.github.com/ivankra/asg/tar.gz/refs/heads/master

That is one request for 506 pages, instead of one request per page.
It is also the reason the mirror is the fallback and not the archive:
the Internet Archive rate-limits hard enough that a 506-page run
collects nothing, while the mirror arrives in a second.
"""

from __future__ import annotations

import io
import os
import re
import tarfile

import requests

# The mirror of the Chinese Grammar Wiki. It is a snapshot of the same
# content, under the same licence.
MIRROR_REPO = "ivankra/asg"
MIRROR_TARBALL = (
    "https://codeload.github.com/ivankra/asg/tar.gz/refs/heads/master"
)

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)

# The name of the directory inside the tarball: "asg-master".
_WIKI_DIR = re.compile(r"^[^/]+/wiki/(?P<name>.+)$")

# The licence the mirror carries, and the one the original wiki
# carries. They are the same: CC BY-NC-SA 3.0.
MIRROR_LICENSE = "Creative Commons BY-NC-SA 3.0"
MIRROR_LICENSE_URL = "https://creativecommons.org/licenses/by-nc-sa/3.0/"


class MirrorError(RuntimeError):
    """The mirror could not be read."""


def fetch_tarball(timeout: int = 180) -> bytes:
    """The mirror's tarball, as bytes."""
    try:
        r = requests.get(
            MIRROR_TARBALL,
            headers={"User-Agent": _UA},
            timeout=timeout,
        )
    except Exception as exc:  # noqa: BLE001
        raise MirrorError(f"could not fetch the mirror: {exc}") from exc
    if r.status_code != 200:
        raise MirrorError(
            f"the mirror answered {r.status_code} for {MIRROR_TARBALL}"
        )
    return r.content


def read_mirror(tarball: bytes | None = None) -> dict[str, str]:
    """The wikitext of every grammar point, keyed by its page title.

    The keys are the wiki page titles ("ASG04ZCI"), which is what the
    rest of the pipeline expects.
    """
    if tarball is None:
        tarball = fetch_tarball()

    pages: dict[str, str] = {}
    try:
        with tarfile.open(fileobj=io.BytesIO(tarball), mode="r:gz") as tf:
            for member in tf.getmembers():
                if not member.isfile():
                    continue
                m = _WIKI_DIR.match(member.name)
                if not m:
                    continue
                name = m.group("name")
                if not name.endswith(".txt"):
                    continue
                handle = tf.extractfile(member)
                if handle is None:
                    continue
                text = handle.read().decode("utf-8", errors="replace")
                pages[name[:-4]] = text
    except tarfile.TarError as exc:
        raise MirrorError(f"the mirror tarball is not readable: {exc}") from exc

    if not pages:
        raise MirrorError("the mirror tarball held no grammar point pages")
    return pages


def read_index(tarball: bytes | None = None) -> dict[str, str]:
    """The title of every grammar point, keyed by its page title.

    The index is a TSV: the point id, then the title. The titles are
    quoted the way TSV quotes them, so they are unquoted here.
    """
    if tarball is None:
        tarball = fetch_tarball()

    out: dict[str, str] = {}
    try:
        with tarfile.open(fileobj=io.BytesIO(tarball), mode="r:gz") as tf:
            for member in tf.getmembers():
                if not member.isfile():
                    continue
                if not member.name.endswith("/wiki/index.tsv"):
                    continue
                handle = tf.extractfile(member)
                if handle is None:
                    continue
                text = handle.read().decode("utf-8", errors="replace")
                for line in text.splitlines()[1:]:
                    if "\t" not in line:
                        continue
                    point_id, title = line.split("\t", 1)
                    out[point_id.strip()] = _unquote(title.strip())
    except tarfile.TarError as exc:
        raise MirrorError(f"the mirror tarball is not readable: {exc}") from exc
    return out


def _unquote(value: str) -> str:
    """A TSV field, with the TSV quoting undone.

    >>> _unquote('"plain"')
    'plain'
    >>> _unquote('"a ""quoted"" word"')
    'a "quoted" word'
    """
    if len(value) >= 2 and value.startswith('"') and value.endswith('"'):
        value = value[1:-1].replace('""', '"')
    return value


def categories_of(wikitext: str) -> set[str]:
    """The wiki categories of a page.

    >>> categories_of("x [[Category:A1 grammar points]] y")
    {'A1 grammar points'}
    """
    out: set[str] = set()
    for m in re.finditer(r"\[\[Category:([^\]|]+)", wikitext):
        out.add(m.group(1).strip())
    return out


def level_of(wikitext: str) -> str:
    """The level of a grammar point, from its categories.

    The mirror writes the category with a leading space in some files
    ("[[Category: B2 grammar points]]") and without it in others, so
    the name is stripped before it is matched.

    >>> level_of("[[Category:A1 grammar points]]")
    'A1'
    >>> level_of("[[Category: B2 grammar points]]")
    'B2'
    >>> level_of("[[Category:C1 grammar points]]")
    'C1'
    >>> level_of("[[Category:Adverbs]]")
    ''
    """
    for name in categories_of(wikitext):
        clean = name.strip()
        m = re.match(r"^(A1|A2|B1|B2|C1|HSK[123])\b", clean)
        if m:
            return m.group(1)
    return ""


def title_of(wikitext: str) -> str:
    """The title of a grammar point, from the comment at the top.

    The mirror's files start with the title in an HTML comment:

        <!-- Expressing existence with "you" -->

    >>> title_of('<!-- Expressing existence with "you" -->\\nbody')
    'Expressing existence with "you"'
    """
    m = re.match(r"<!--\s*(.*?)\s*-->", wikitext.strip())
    if m:
        return m.group(1).strip()
    return ""


def save_mirror(pages: dict[str, str], out_dir: str) -> str:
    """Write the mirror's pages to a directory, for the cache.

    The live source caches every page it fetches under
    data/raw/grammar_cache/. The mirror is cached the same way, so a
    second run does not download the tarball again.
    """
    os.makedirs(out_dir, exist_ok=True)
    for name, text in pages.items():
        safe = re.sub(r"[^A-Za-z0-9_.-]", "_", name)
        with open(os.path.join(out_dir, safe + ".txt"), "w", encoding="utf-8") as fh:
            fh.write(text)
    return out_dir
