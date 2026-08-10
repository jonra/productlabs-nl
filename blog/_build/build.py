#!/usr/bin/env python3
"""
ProductLabs content build.

Renders markdown sources in _build/articles/ into static HTML under /blog/,
generates the blog landing page, topic hubs, and a sitemap fragment.

Usage:
    python3 blog/_build/build.py          # build everything
    python3 blog/_build/build.py --check  # build to a temp dir and report only

Adding a new article: drop a .md file in _build/articles/ with front matter,
then re-run. Nothing else needs editing.

Adding a new content type (case studies, tools, notes): add an entry to
CONTENT_TYPES below and set `type:` in the front matter. The build will route
it to its own directory and give it its own index page.
"""

from __future__ import annotations

import argparse
import html
import json
import re

import sys
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

try:
    import markdown
except ImportError:
    sys.exit("Missing dependency. Run: pip install markdown")

ROOT = Path(__file__).resolve().parents[2]
BLOG = ROOT / "blog"
SRC = Path(__file__).resolve().parent / "articles"
SITE = "https://www.productlabs.nl"

# ── Content types ────────────────────────────────────────────────────────────
# Add new types here as the site grows. `dir` is relative to /blog.
CONTENT_TYPES = {
    "article": {
        "dir": "",
        "label": "Article",
        "plural": "Articles",
    },
    # Scaffolded for future use — no sources yet, so nothing is generated.
    "case-study": {
        "dir": "case-studies",
        "label": "Case study",
        "plural": "Case studies",
    },
    "tool": {
        "dir": "tools",
        "label": "Tool",
        "plural": "Tools",
    },
    "note": {
        "dir": "notes",
        "label": "Note",
        "plural": "Notes",
    },
}

# ── Topics ───────────────────────────────────────────────────────────────────
# Ordered. Add new topics here; the topic bar and hub pages follow automatically.
TOPICS = {
    "mcp": {
        "label": "MCP",
        "title": "Model Context Protocol",
        "blurb": "Building, securing and shipping MCP servers — the protocol that "
                 "connects Claude to real systems.",
    },
    "claude-api": {
        "label": "Claude API",
        "title": "Claude API engineering",
        "blurb": "Cost, latency and reliability when Claude is in your production path.",
    },
    "security": {
        "label": "Security",
        "title": "Agent security",
        "blurb": "What changes when a language model holds tools that can act on your systems.",
    },
    "compliance": {
        "label": "Compliance",
        "title": "EU compliance",
        "blurb": "The AI Act, GDPR, and what actually applies to a company deploying AI in Europe.",
    },
}

MD_EXTENSIONS = ["fenced_code", "tables", "attr_list", "sane_lists", "footnotes", "md_in_html"]


# ── Front matter ─────────────────────────────────────────────────────────────
@dataclass
class Doc:
    meta: dict
    body_md: str
    source: Path

    # convenience accessors
    @property
    def slug(self) -> str: return self.meta["slug"]
    @property
    def title(self) -> str: return self.meta["title"]
    @property
    def dek(self) -> str: return self.meta["dek"]
    @property
    def ctype(self) -> str: return self.meta.get("type", "article")
    @property
    def topic(self) -> str: return self.meta.get("topic", "")
    @property
    def sources(self) -> list: return self.meta.get("sources", [])
    @property
    def related(self) -> list: return self.meta.get("related", [])

    @property
    def url(self) -> str:
        d = CONTENT_TYPES[self.ctype]["dir"]
        return f"/blog/{d}/{self.slug}/" if d else f"/blog/{self.slug}/"

    @property
    def outdir(self) -> Path:
        d = CONTENT_TYPES[self.ctype]["dir"]
        return (BLOG / d / self.slug) if d else (BLOG / self.slug)


def parse_front_matter(text: str, source: Path) -> Doc:
    if not text.startswith("---"):
        raise ValueError(f"{source.name}: missing front matter")
    _, fm, body = text.split("---", 2)

    meta: dict = {}
    current_list: str | None = None
    for raw in fm.strip().splitlines():
        if not raw.strip() or raw.strip().startswith("#"):
            continue
        if raw.startswith((" ", "\t")) and raw.strip().startswith("- "):
            if current_list is None:
                raise ValueError(f"{source.name}: list item outside a key")
            meta[current_list].append(raw.strip()[2:].strip())
            continue
        if ":" not in raw:
            raise ValueError(f"{source.name}: cannot parse front-matter line: {raw!r}")
        key, _, value = raw.partition(":")
        key, value = key.strip(), value.strip()
        if not value:
            meta[key] = []
            current_list = key
            continue
        current_list = None
        if value.startswith("[") and value.endswith("]"):
            inner = value[1:-1].strip()
            meta[key] = [v.strip() for v in inner.split(",") if v.strip()] if inner else []
        elif value.lower() in ("true", "false"):
            meta[key] = value.lower() == "true"
        elif value.isdigit():
            meta[key] = int(value)
        else:
            if len(value) >= 2 and value[0] == value[-1] and value[0] in ("\"", "'"):
                value = value[1:-1]
            meta[key] = value

    for required in ("title", "slug", "dek", "date"):
        if required not in meta:
            raise ValueError(f"{source.name}: missing required front-matter key '{required}'")
    if meta.get("type", "article") not in CONTENT_TYPES:
        raise ValueError(f"{source.name}: unknown type '{meta['type']}'")
    if meta.get("topic") and meta["topic"] not in TOPICS:
        raise ValueError(f"{source.name}: unknown topic '{meta['topic']}'")

    return Doc(meta=meta, body_md=body.strip(), source=source)


def publish_today() -> str:
    """Today's date in Europe/Amsterdam (the publish-gate clock), ISO format."""
    return datetime.now(ZoneInfo("Europe/Amsterdam")).date().isoformat()


def is_live(doc: Doc, today: str) -> bool:
    """A doc is live iff its publish date has arrived and it is not a draft."""
    if doc.meta.get("draft", False):
        return False
    return str(doc.meta["date"]) <= today


def select_live(docs: list, today: str, preview: bool) -> list:
    """Docs to write: all of them in preview mode, else only live ones."""
    if preview:
        return list(docs)
    return [d for d in docs if is_live(d, today)]


# ── Shared chrome ────────────────────────────────────────────────────────────
def head(title: str, description: str, canonical: str, *,
         extra: str = "", robots: str = "") -> str:
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <meta name="theme-color" content="#f5f3ee" />
  <title>{html.escape(title)}</title>
  <meta name="description" content="{html.escape(description)}" />
  <link rel="canonical" href="{canonical}" />
  {robots}
  <meta property="og:title" content="{html.escape(title)}" />
  <meta property="og:description" content="{html.escape(description)}" />
  <meta property="og:url" content="{canonical}" />
  <meta property="og:type" content="website" />
  <meta property="og:locale" content="en_NL" />
  <meta property="og:site_name" content="ProductLabs" />
  <meta name="twitter:card" content="summary_large_image" />
  <meta name="twitter:title" content="{html.escape(title)}" />
  <meta name="twitter:description" content="{html.escape(description)}" />
  <link rel="preconnect" href="https://fonts.googleapis.com" />
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
  <link href="https://fonts.googleapis.com/css2?family=Syne:wght@400;600;700;800&family=DM+Sans:ital,opsz,wght@0,9..40,300;0,9..40,400;0,9..40,500;0,9..40,600;1,9..40,300&display=swap" rel="stylesheet" />
  <link rel="stylesheet" href="/blog/assets/blog.css" />
{extra}</head>
<body>
"""


def nav(active: str = "") -> str:
    def mark(name): return ' aria-current="page"' if active == name else ""
    return f"""  <nav>
    <a href="/" class="logo">Product<span>Labs</span></a>
    <div class="nav-links">
      <a href="/#services">Services</a>
      <a href="/#ecosystem">Anthropic ecosystem</a>
      <a href="/#use-cases">Use cases</a>
      <a href="/blog/"{mark('blog')}>Blog</a>
    </div>
    <a href="/#contact" class="cta-nav">Get in touch</a>
  </nav>
"""


def footer() -> str:
    return """  <footer>
    <span>&copy; 2026 Product Labs B.V. &middot; Amsterdam, The Netherlands</span>
    <span><a href="/blog/">Blog</a> &middot; <a href="mailto:jon@productlabs.nl">jon@productlabs.nl</a></span>
  </footer>
</body>
</html>
"""


def topic_bar(active: str = "", counts: dict | None = None) -> str:
    counts = counts or {}
    all_cur = ' aria-current="page"' if active == "" else ""
    chips = [f'      <a href="/blog/" class="topic-chip"{all_cur}>All</a>']
    for key, t in TOPICS.items():
        n = counts.get(key, 0)
        if not n:
            continue
        cur = ' aria-current="page"' if active == key else ""
        chips.append(f'      <a href="/blog/topics/{key}/" class="topic-chip"{cur}>'
                     f'{html.escape(t["label"])}<span class="count">{n}</span></a>')
    return f"""  <div class="topic-bar">
    <div class="wrap">
{chr(10).join(chips)}
    </div>
  </div>
"""


def cta_block() -> str:
    return """      <div class="cta-block">
        <div>
          <h2>Working on something like this?</h2>
          <p>We build Claude integrations, MCP servers and agentic workflows for
             startups and SMBs in the Netherlands and across the EU.</p>
        </div>
        <a href="/#contact" class="btn btn-primary">Book a free consult</a>
      </div>
"""


def fmt_date(iso: str) -> str:
    y, m, d = (int(x) for x in str(iso).split("-"))
    return date(y, m, d).strftime("%-d %B %Y")


# ── Rendering ────────────────────────────────────────────────────────────────
def render_body(md_text: str) -> str:
    md = markdown.Markdown(extensions=MD_EXTENSIONS, output_format="html5")
    out = md.convert(md_text)
    # Make wide tables scrollable on mobile.
    out = re.sub(r"(<table>.*?</table>)", r'<div class="table-scroll">\1</div>',
                 out, flags=re.DOTALL)
    return out


def article_schema(doc: Doc) -> str:
    data = {
        "@context": "https://schema.org",
        "@type": "TechArticle",
        "headline": doc.title,
        "description": doc.dek,
        "datePublished": str(doc.meta["date"]),
        "dateModified": str(doc.meta.get("updated", doc.meta["date"])),
        "author": {"@type": "Organization", "name": "ProductLabs", "url": SITE},
        "publisher": {"@type": "Organization", "name": "ProductLabs", "url": SITE},
        "mainEntityOfPage": {"@type": "WebPage", "@id": SITE + doc.url},
        "inLanguage": "en",
    }
    if doc.meta.get("keywords"):
        data["keywords"] = ", ".join(doc.meta["keywords"])
    crumbs = {
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "Home", "item": SITE + "/"},
            {"@type": "ListItem", "position": 2, "name": "Blog", "item": SITE + "/blog/"},
            {"@type": "ListItem", "position": 3, "name": doc.title, "item": SITE + doc.url},
        ],
    }
    return ('  <script type="application/ld+json">\n'
            + json.dumps(data, indent=2) + "\n  </script>\n"
            + '  <script type="application/ld+json">\n'
            + json.dumps(crumbs, indent=2) + "\n  </script>\n")


def render_article(doc: Doc, by_slug: dict) -> str:
    t = TOPICS.get(doc.topic, {})
    updated = doc.meta.get("updated")
    meta_bits = [f'<span>{fmt_date(doc.meta["date"])}</span>']
    if updated and str(updated) != str(doc.meta["date"]):
        meta_bits.append(f'<span>Updated {fmt_date(updated)}</span>')
    if doc.meta.get("reading_time"):
        meta_bits.append(f'<span>{doc.meta["reading_time"]} min read</span>')
    if t:
        meta_bits.append(f'<a class="topic-tag" href="/blog/topics/{doc.topic}/">'
                         f'{html.escape(t["label"])}</a>')

    related_html = ""
    rel = [by_slug[s] for s in doc.related if s in by_slug]
    if rel:
        items = "\n".join(
            f'          <li><a href="{r.url}">{html.escape(r.title)}</a>'
            f'<div class="rel-dek">{html.escape(r.dek)}</div></li>' for r in rel)
        related_html = f"""      <div class="related">
        <h2>Related reading</h2>
        <ul>
{items}
        </ul>
      </div>
"""

    sources_html = ""
    if doc.sources:
        items = []
        for s in doc.sources:
            label, _, url = s.partition("|")
            items.append(f'          <li><a href="{url.strip()}" rel="noopener">'
                         f'{html.escape(label.strip())}</a></li>')
        sources_html = f"""      <div class="sources">
        <h2>Sources</h2>
        <ul>
{chr(10).join(items)}
        </ul>
      </div>
"""

    return (
        head(doc.meta.get("meta_title", doc.title + " | ProductLabs"),
             doc.meta.get("meta_description", doc.dek),
             SITE + doc.url,
             extra=article_schema(doc))
        + nav("blog")
        + f"""  <article>
  <header class="article-head">
    <div class="wrap">
      <div class="breadcrumb">
        <a href="/">Home</a><span class="sep">/</span><a href="/blog/">Blog</a>"""
        + (f'<span class="sep">/</span><a href="/blog/topics/{doc.topic}/">'
           f'{html.escape(t["label"])}</a>' if t else "")
        + f"""
      </div>
      <h1>{html.escape(doc.title)}</h1>
      <p class="dek">{html.escape(doc.dek)}</p>
      <div class="article-meta">
        {chr(10).join("        " + b for b in meta_bits).strip()}
      </div>
    </div>
  </header>

  <div class="article-body">
    <div class="wrap">
{render_body(doc.body_md)}
    </div>
  </div>

  <div class="article-foot">
    <div class="wrap">
{related_html}{sources_html}{cta_block()}    </div>
  </div>
  </article>

"""
        + footer()
    )


def post_item(doc: Doc, n: int, by_slug: dict) -> str:
    t = TOPICS.get(doc.topic, {})
    new = ' <span class="badge-new">New</span>' if doc.meta.get("badge_new") else ""
    topic_line = (f'<span class="topic-tag">{html.escape(t["label"])}</span>'
                  if t else "")
    rt = f'{doc.meta["reading_time"]} min read' if doc.meta.get("reading_time") else ""
    return f"""        <div class="post-item">
          <div class="post-num">{n:02d}</div>
          <div>
            <h3 class="post-title"><a href="{doc.url}">{html.escape(doc.title)}</a>{new}</h3>
            <p class="post-dek">{html.escape(doc.dek)}</p>
          </div>
          <div class="post-meta">
            {topic_line}
            <span>{fmt_date(doc.meta["date"])}</span><br />
            <span>{rt}</span>
          </div>
        </div>
"""


def render_index(docs: list, counts: dict) -> str:
    featured = next((d for d in docs if d.meta.get("featured")), docs[0])
    rest = [d for d in docs if d is not featured]

    schema = {
        "@context": "https://schema.org",
        "@type": "Blog",
        "name": "ProductLabs Blog",
        "description": "Field notes on building with Claude — MCP servers, agentic "
                       "workflows, API economics, and EU AI compliance.",
        "url": SITE + "/blog/",
        "publisher": {"@type": "Organization", "name": "ProductLabs", "url": SITE},
        "blogPost": [
            {"@type": "BlogPosting", "headline": d.title, "url": SITE + d.url,
             "datePublished": str(d.meta["date"]), "description": d.dek}
            for d in docs
        ],
    }
    extra = ('  <script type="application/ld+json">\n'
             + json.dumps(schema, indent=2) + "\n  </script>\n")

    items = "".join(post_item(d, i, {}) for i, d in enumerate(rest, start=2))

    return (
        head("Blog — Claude, MCP & AI Engineering Notes | ProductLabs",
             "Field notes from building with Anthropic's Claude: MCP server "
             "engineering, agent security, API cost control, and EU AI Act compliance.",
             SITE + "/blog/", extra=extra)
        + nav("blog")
        + f"""  <header class="blog-hero">
    <div class="wrap">
      <div class="eyebrow">Field notes</div>
      <h1>Notes from <em>building</em> with Claude</h1>
      <p class="sub">Specifics, not overviews. What the current MCP specification
        actually requires, what a request really costs, where agents break, and what
        the EU AI Act means for a company shipping this quarter.</p>
    </div>
  </header>

"""
        + topic_bar("", counts)
        + f"""  <div class="section">
    <div class="wrap">
      <div class="featured">
        <div class="featured-main">
          <div class="section-label">Start here</div>
          <h2><a href="{featured.url}">{html.escape(featured.title)}</a></h2>
          <p class="dek">{html.escape(featured.dek)}</p>
          <a href="{featured.url}" class="btn btn-ghost">Read it</a>
        </div>
        <div class="featured-side">
          <div class="section-label">Why this one</div>
          <p>{html.escape(featured.meta.get('featured_reason', ''))}</p>
        </div>
      </div>

      <h2 class="section-title">Everything else</h2>
      <p class="section-sub">Written for the person doing the work. Every code sample
        is executed before publishing, and anything version-dependent carries the date
        it was verified.</p>

      <div class="post-list">
{items}      </div>
    </div>
  </div>

  <div class="section">
    <div class="wrap">
{cta_block()}    </div>
  </div>

"""
        + footer()
    )


def render_topic(key: str, t: dict, docs: list, counts: dict) -> str:
    items = "".join(post_item(d, i, {}) for i, d in enumerate(docs, start=1))
    return (
        head(f"{t['title']} — ProductLabs Blog",
             t["blurb"],
             f"{SITE}/blog/topics/{key}/")
        + nav("blog")
        + f"""  <header class="blog-hero">
    <div class="wrap">
      <div class="breadcrumb" style="margin-bottom:1.25rem">
        <a href="/">Home</a><span class="sep">/</span><a href="/blog/">Blog</a>
        <span class="sep">/</span>{html.escape(t['label'])}
      </div>
      <h1>{html.escape(t['title'])}</h1>
      <p class="sub">{html.escape(t['blurb'])}</p>
    </div>
  </header>

"""
        + topic_bar(key, counts)
        + f"""  <div class="section">
    <div class="wrap">
      <div class="post-list">
{items}      </div>
    </div>
  </div>

  <div class="section">
    <div class="wrap">
{cta_block()}    </div>
  </div>

"""
        + footer()
    )


def render_sitemap(docs: list, counts: dict) -> str:
    today = date.today().isoformat()
    urls = [("/", today, "monthly", "1.0"), ("/blog/", today, "weekly", "0.9")]
    urls += [(f"/blog/topics/{k}/", today, "weekly", "0.6")
             for k in TOPICS if counts.get(k)]
    urls += [(d.url, str(d.meta.get("updated", d.meta["date"])), "monthly", "0.8")
             for d in docs]
    body = "\n".join(
        f"  <url>\n    <loc>{SITE}{u}</loc>\n    <lastmod>{m}</lastmod>\n"
        f"    <changefreq>{c}</changefreq>\n    <priority>{p}</priority>\n  </url>"
        for u, m, c, p in urls)
    return ('<?xml version="1.0" encoding="UTF-8"?>\n'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
            f"{body}\n</urlset>\n")


# ── Main ─────────────────────────────────────────────────────────────────────
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true",
                    help="parse and render without writing files")
    ap.add_argument("--preview", action="store_true",
                    help="build ALL articles incl. scheduled/draft (local review only)")
    args = ap.parse_args()

    if not SRC.exists():
        sys.exit(f"No source directory at {SRC}")

    docs = [parse_front_matter(p.read_text(encoding="utf-8"), p)
            for p in sorted(SRC.glob("*.md"))]
    if not docs:
        sys.exit("No markdown sources found.")

    # newest first, then by explicit order key if present
    docs.sort(key=lambda d: (str(d.meta["date"]), d.meta.get("order", 0)), reverse=True)

    all_by_slug = {d.slug: d for d in docs}

    # validate cross-references against ALL sources (scheduled articles exist as sources)
    problems = []
    seen = set()
    for d in docs:
        if d.slug in seen:
            problems.append(f"duplicate slug: {d.slug}")
        seen.add(d.slug)
        for r in d.related:
            if r not in all_by_slug:
                problems.append(f"{d.slug}: related slug not found: {r}")
    if problems:
        for p in problems:
            print(f"  ERROR  {p}", file=sys.stderr)
        return 1

    if args.check:
        for d in docs:
            render_article(d, all_by_slug)
        all_counts: dict = {}
        for d in docs:
            if d.topic:
                all_counts[d.topic] = all_counts.get(d.topic, 0) + 1
        render_index([d for d in docs if d.ctype == "article"], all_counts)
        print(f"OK  {len(docs)} document(s) parsed and rendered cleanly.")
        return 0

    # publish gate: only live docs are written and listed
    today = publish_today()
    live = select_live(docs, today, args.preview)
    by_slug = {d.slug: d for d in live}

    counts: dict = {}
    for d in live:
        if d.topic:
            counts[d.topic] = counts.get(d.topic, 0) + 1

    articles = [d for d in live if d.ctype == "article"]

    written = []
    for d in live:
        d.outdir.mkdir(parents=True, exist_ok=True)
        (d.outdir / "index.html").write_text(render_article(d, by_slug), encoding="utf-8")
        written.append(d.outdir / "index.html")

    (BLOG / "index.html").write_text(render_index(articles, counts), encoding="utf-8")
    written.append(BLOG / "index.html")

    topics_dir = BLOG / "topics"
    # Clear stale topic pages without removing directories (some mounts disallow rmdir).
    if topics_dir.exists():
        for stale in topics_dir.glob("*/index.html"):
            if not any(d.topic == stale.parent.name for d in live):
                stale.unlink()
    for key, t in TOPICS.items():
        tdocs = [d for d in live if d.topic == key]
        if not tdocs:
            continue
        out = topics_dir / key
        out.mkdir(parents=True, exist_ok=True)
        (out / "index.html").write_text(render_topic(key, t, tdocs, counts), encoding="utf-8")
        written.append(out / "index.html")

    (ROOT / "sitemap.xml").write_text(render_sitemap(live, counts), encoding="utf-8")
    written.append(ROOT / "sitemap.xml")

    for p in written:
        print(f"  wrote  {p.relative_to(ROOT)}")
    print(f"\n{len(written)} file(s). {len(live)} live document(s), "
          f"{len([k for k in TOPICS if counts.get(k)])} topic(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
