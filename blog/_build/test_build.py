import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import build  # noqa: E402


def mkdoc(slug, date, *, draft=False, topic="mcp", related=None):
    meta = {"slug": slug, "title": slug, "dek": "dek", "date": date, "topic": topic}
    if draft:
        meta["draft"] = True
    if related:
        meta["related"] = related
    return build.Doc(meta=meta, body_md="body", source=Path(f"{slug}.md"))


def test_past_date_is_live():
    assert build.is_live(mkdoc("a", "2000-01-01"), "2026-08-10") is True


def test_today_is_live():
    assert build.is_live(mkdoc("a", "2026-08-10"), "2026-08-10") is True


def test_future_date_is_not_live():
    assert build.is_live(mkdoc("a", "2099-01-01"), "2026-08-10") is False


def test_draft_is_not_live_even_if_past():
    assert build.is_live(mkdoc("a", "2000-01-01", draft=True), "2026-08-10") is False


def test_select_live_filters_future_when_not_preview():
    docs = [mkdoc("live", "2000-01-01"), mkdoc("future", "2099-01-01")]
    live = build.select_live(docs, "2026-08-10", preview=False)
    assert [d.slug for d in live] == ["live"]


def test_select_live_includes_everything_in_preview():
    docs = [mkdoc("live", "2000-01-01"), mkdoc("future", "2099-01-01")]
    live = build.select_live(docs, "2026-08-10", preview=True)
    assert {d.slug for d in live} == {"live", "future"}


def test_sitemap_excludes_non_live_docs():
    live = [mkdoc("live", "2000-01-01")]
    counts = {"mcp": 1}
    xml = build.render_sitemap(live, counts)
    assert "/blog/live/" in xml
    assert "/blog/future/" not in xml


def test_related_links_filtered_to_live_by_slug():
    # render_article resolves related as: [by_slug[s] for s in related if s in by_slug]
    live_doc = mkdoc("live", "2000-01-01", related=["future", "alsolive"])
    also = mkdoc("alsolive", "2000-01-02")
    by_slug = {"live": live_doc, "alsolive": also}  # 'future' absent -> not live
    rel = [by_slug[s] for s in live_doc.related if s in by_slug]
    assert [r.slug for r in rel] == ["alsolive"]
