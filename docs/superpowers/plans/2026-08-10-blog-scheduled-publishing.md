# Scheduled Publishing for /blog — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let articles carry a future `date` and go live one at a time on that date, driven by a daily GitHub Action, with page + sitemap + crawl date all consistent.

**Architecture:** A build-time date gate in `build.py` renders only articles whose publish date has arrived (Europe/Amsterdam) and that are not drafts. GitHub Pages is built and deployed by a scheduled GitHub Action from tracked markdown sources; generated HTML is no longer committed. A `_site/` allowlist keeps sources and specs off the public domain.

**Tech Stack:** Python 3.12 (stdlib `zoneinfo`, `datetime`), `markdown`, GitHub Actions, GitHub Pages, pytest (dev only).

## Global Constraints

- Publish-gate clock is **Europe/Amsterdam**; dates compared as ISO strings (`YYYY-MM-DD`).
- Cron runs daily at **`0 6 * * *` UTC** (~08:00 Amsterdam).
- Python **3.9+** required (`zoneinfo`); CI pins **3.12**.
- Only build dependency is **`markdown`** (`markdown>=3.5,<4`).
- Deployed `_site/` contains **only** `index.html`, `CNAME`, `robots.txt`, `sitemap.xml`, and `blog/` **excluding `blog/_build/`**. Never `docs/` or build sources.
- Dates are honest going forward. No backdating language in tracked files.
- No downtime during cutover: sources tracked before the Action runs; committed HTML removed only after Pages Source = GitHub Actions is verified.

---

### Task 1: Date gate, draft flag, and `--preview` in `build.py`

**Files:**
- Modify: `blog/_build/build.py` (imports at line 29; add helpers after `parse_front_matter`; rewrite `main()` at lines 542–625)
- Test: `blog/_build/test_build.py` (create)

**Interfaces:**
- Produces: `publish_today() -> str`, `is_live(doc: Doc, today: str) -> bool`, `select_live(docs: list, today: str, preview: bool) -> list`. Existing `Doc`, `render_sitemap(docs, counts)`, `render_article(doc, by_slug)` unchanged.

- [ ] **Step 1: Create the dev virtualenv and install deps**

The host Python is externally managed; use a venv.

Run:
```bash
cd /Users/jon/repo/productlabs-nl
python3 -m venv .venv
.venv/bin/pip install --quiet "markdown>=3.5,<4" pytest
```
Expected: installs without error. (`.venv/` will be gitignored in Task 4; add it locally now — it must never be committed.)

- [ ] **Step 2: Write the failing tests**

Create `blog/_build/test_build.py`:
```python
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
```

- [ ] **Step 3: Run tests to verify they fail**

Run:
```bash
cd /Users/jon/repo/productlabs-nl
.venv/bin/python -m pytest blog/_build/test_build.py -q
```
Expected: FAIL — `AttributeError: module 'build' has no attribute 'is_live'` (and `select_live`).

- [ ] **Step 4: Add imports**

In `blog/_build/build.py`, change line 29 `from datetime import date` to:
```python
from datetime import date, datetime
from zoneinfo import ZoneInfo
```

- [ ] **Step 5: Add the gate helpers**

Immediately after the `parse_front_matter` function (before the first `render_*`/`head` function), add:
```python
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
```

- [ ] **Step 6: Run tests to verify they pass**

Run:
```bash
cd /Users/jon/repo/productlabs-nl
.venv/bin/python -m pytest blog/_build/test_build.py -q
```
Expected: PASS (8 passed).

- [ ] **Step 7: Wire the gate into `main()`**

Replace the body of `main()` from the line `by_slug = {d.slug: d for d in docs}` (line 559) through the end of the function with:
```python
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
```

- [ ] **Step 8: Add the `--preview` CLI flag**

In `main()`, right after the existing `--check` argument definition (line 544-545), add:
```python
    ap.add_argument("--preview", action="store_true",
                    help="build ALL articles incl. scheduled/draft (local review only)")
```

- [ ] **Step 9: Verify the current site still builds unchanged**

Run:
```bash
cd /Users/jon/repo/productlabs-nl
.venv/bin/python blog/_build/build.py --check
.venv/bin/python blog/_build/build.py
```
Expected: `--check` prints `OK 10 document(s) ...`; the build prints `... 10 live document(s), 4 topic(s).` (all ten current articles are past-dated, so they remain live).

- [ ] **Step 10: Prove the gate with a temporary future article**

Run:
```bash
cd /Users/jon/repo/productlabs-nl
cat > blog/_build/articles/_gate-test.md <<'EOF'
---
title: Gate test
slug: gate-test
dek: temp
date: 2099-01-01
topic: mcp
---
Body.
EOF
.venv/bin/python blog/_build/build.py >/dev/null
test ! -e blog/gate-test/index.html && echo "PASS: future article not written"
grep -q "/blog/gate-test/" sitemap.xml && echo "FAIL: in sitemap" || echo "PASS: not in sitemap"
.venv/bin/python blog/_build/build.py --preview >/dev/null
test -e blog/gate-test/index.html && echo "PASS: preview wrote it"
rm -rf blog/_build/articles/_gate-test.md blog/gate-test
.venv/bin/python blog/_build/build.py >/dev/null   # restore clean state
```
Expected: three `PASS` lines.

- [ ] **Step 11: Commit**

```bash
cd /Users/jon/repo/productlabs-nl
git add blog/_build/build.py blog/_build/test_build.py
git commit -m "feat(blog): build-time publish gate, draft flag, and --preview"
```

---

### Task 2: Track build sources + pin dependency

**Files:**
- Modify: `.gitignore` (remove the `blog/_build/` ignore; add `__pycache__/`, `*.pyc`, `.venv/`)
- Create: `blog/_build/requirements.txt`

**Interfaces:** none (repo hygiene). Leaves generated HTML still committed for now — cutover happens in Task 4.

- [ ] **Step 1: Create the pinned requirements file**

Create `blog/_build/requirements.txt`:
```
markdown>=3.5,<4
```

- [ ] **Step 2: Un-ignore sources; ignore Python cruft and the venv**

Replace `.gitignore` with:
```
# OS / editor cruft
.DS_Store
.idea/
__pycache__/
*.pyc
.venv/

# Internal / strategy docs — not for the public repo
*.docx
```
(Note: `blog/_build/` line removed so sources become trackable. Generated-output ignores are added in Task 4, at cutover.)

- [ ] **Step 3: Stage sources and confirm the exclusions**

Run:
```bash
cd /Users/jon/repo/productlabs-nl
git add .gitignore blog/_build/requirements.txt blog/_build/build.py blog/_build/README.md blog/_build/articles blog/_build/test_build.py
git status --short
git diff --cached --name-only | grep -E "__pycache__|\.venv|\.pyc" && echo "LEAK" || echo "clean: no cruft staged"
```
Expected: the ten markdown sources, `build.py`, `README.md`, `requirements.txt`, `test_build.py`, `.gitignore` staged; `clean: no cruft staged`.

- [ ] **Step 4: Commit**

```bash
cd /Users/jon/repo/productlabs-nl
git commit -m "chore(blog): track build sources; pin markdown; ignore venv/pycache"
```

---

### Task 3: GitHub Action to build and deploy Pages

**Files:**
- Create: `.github/workflows/publish.yml`

**Interfaces:**
- Consumes: `blog/_build/build.py`, `blog/_build/requirements.txt` (Task 1/2). Produces the deployed site.

- [ ] **Step 1: Write the workflow**

Create `.github/workflows/publish.yml`:
```yaml
name: Build and deploy site

on:
  push:
    branches: [main]
  schedule:
    - cron: "0 6 * * *"   # daily 06:00 UTC (~08:00 Europe/Amsterdam): publish due articles
  workflow_dispatch:

permissions:
  contents: read
  pages: write
  id-token: write

concurrency:
  group: pages
  cancel-in-progress: false

jobs:
  build-deploy:
    runs-on: ubuntu-latest
    environment:
      name: github-pages
      url: ${{ steps.deploy.outputs.page_url }}
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Install build deps
        run: pip install -r blog/_build/requirements.txt

      - name: Build site
        run: python blog/_build/build.py

      - name: Package _site (publishable files only)
        run: |
          mkdir -p _site
          cp index.html CNAME robots.txt sitemap.xml _site/
          rsync -a --exclude '_build' blog/ _site/blog/
          touch _site/.nojekyll

      - name: Upload Pages artifact
        uses: actions/upload-pages-artifact@v3
        with:
          path: _site

      - name: Deploy to GitHub Pages
        id: deploy
        uses: actions/deploy-pages@v4
```

- [ ] **Step 2: Verify the packaging step locally (no leaks)**

Run the same packaging commands and assert exclusions:
```bash
cd /Users/jon/repo/productlabs-nl
.venv/bin/python blog/_build/build.py >/dev/null
rm -rf _site && mkdir -p _site
cp index.html CNAME robots.txt sitemap.xml _site/
rsync -a --exclude '_build' blog/ _site/blog/
touch _site/.nojekyll
test -e _site/index.html && test -e _site/sitemap.xml && test -e _site/blog/index.html && echo "PASS: published files present"
test ! -e _site/blog/_build && echo "PASS: _build excluded"
test ! -e _site/docs && echo "PASS: docs excluded"
rm -rf _site
```
Expected: three `PASS` lines. (`rsync` is preinstalled on GitHub's `ubuntu-latest` runners and macOS.)

- [ ] **Step 3: Commit and push**

```bash
cd /Users/jon/repo/productlabs-nl
git add .github/workflows/publish.yml
git commit -m "ci(blog): daily build + deploy to GitHub Pages"
git push
```

- [ ] **Step 4: MANUAL — switch Pages source and verify (user)**

The Action deploy has no effect until Pages is switched to Actions. In the GitHub UI:
1. **Settings → Pages → Build and deployment → Source → GitHub Actions.**
2. Actions tab → run **"Build and deploy site"** (via `workflow_dispatch`) or wait for the push run; confirm it succeeds.
3. Load `https://www.productlabs.nl/` and `https://www.productlabs.nl/blog/` — both serve correctly.
4. Confirm `https://www.productlabs.nl/blog/_build/build.py` returns **404** (sources not served).

Do not proceed to Task 4 until step 3 shows the site served by the Action.

---

### Task 4: Cutover — stop committing generated HTML

**Files:**
- Modify: `.gitignore` (add generated-output ignores)

**Interfaces:** none. Removes generated artifacts from git now that the Action is the source of truth.

- [ ] **Step 1: Add generated-output ignores**

Append to `.gitignore`:
```

# Generated blog output — rebuilt by CI, never committed
/sitemap.xml
/blog/index.html
/blog/*/index.html
/blog/topics/*/index.html
/_site/
```

- [ ] **Step 2: Untrack the generated files (keep them on disk)**

Run (`git ls-files` matches only tracked files; its `*` spans `/`, so one pattern covers both article and topic pages):
```bash
cd /Users/jon/repo/productlabs-nl
git rm --cached sitemap.xml blog/index.html
git rm --cached $(git ls-files 'blog/*/index.html')
git status --short
```
Expected: those files shown as deleted-from-index (`D`); `blog/assets/blog.css` remains tracked; local files still present on disk.

- [ ] **Step 3: Confirm sources and CSS remain tracked**

Run:
```bash
cd /Users/jon/repo/productlabs-nl
git ls-files blog | grep -E "_build/build.py|_build/articles/|assets/blog.css" | head
git ls-files 'blog/*/index.html' | grep . && echo "STILL TRACKED (bad)" || echo "clean: no generated HTML tracked"
```
Expected: sources + `assets/blog.css` listed; `clean: no generated HTML tracked`.

- [ ] **Step 4: Commit and push, then verify the live site is unaffected**

```bash
cd /Users/jon/repo/productlabs-nl
git add .gitignore
git commit -m "chore(blog): stop committing generated HTML; CI rebuilds on deploy"
git push
```
Then confirm the push-triggered Action run succeeds and `https://www.productlabs.nl/blog/` still serves (now purely from the Action). Expected: site intact.

---

### Task 5: Rewrite the build README (honest, no backdating)

**Files:**
- Modify: `blog/_build/README.md`

**Interfaces:** none (documentation).

- [ ] **Step 1: Remove the backdating content and document the new flow**

In `blog/_build/README.md`:
1. Delete the entire **"Publishing dates"** section (the dated table and the paragraphs about making the archive "read as a consultancy that has been writing for a month").
2. Under "Adding an article", document the gate and flags with this block:
```markdown
## Scheduling

`date` is a publish gate, evaluated in Europe/Amsterdam:

- An article with a **future `date`** is not rendered, not linked, and not in the
  sitemap. It first appears — as a page and a sitemap entry — on its publish date,
  when the daily GitHub Action next runs. Before then its URL 404s.
- `draft: true` holds an article back regardless of date. Remove it to let the date
  gate decide.
- `python blog/_build/build.py --preview` builds everything, including scheduled and
  draft articles, for local review. Preview output is never deployed — production is
  always built by the Action with the gate on.

Dates are honest: byline date, first-live date, and first-crawl date all coincide.
```
3. Replace any "generated HTML is committed and served directly" wording with:
```markdown
Generated HTML is **not** committed. The GitHub Action (`.github/workflows/publish.yml`)
runs `build.py` on every push to `main`, daily at 06:00 UTC, and on manual dispatch,
then deploys the packaged `_site/` to GitHub Pages. `_site/` contains only the
published output (`index.html`, `CNAME`, `robots.txt`, `sitemap.xml`, and `blog/`
without `_build/`) — sources and `docs/` are never served.
```

- [ ] **Step 2: Confirm no backdating language remains**

Run:
```bash
cd /Users/jon/repo/productlabs-nl
grep -niE "backdat|read as a consultancy|earliest date the article" blog/_build/README.md && echo "STILL PRESENT" || echo "clean"
```
Expected: `clean`.

- [ ] **Step 3: Commit**

```bash
cd /Users/jon/repo/productlabs-nl
git add blog/_build/README.md
git commit -m "docs(blog): document scheduling; remove backdating rationale"
```

---

## Notes for the executor

- **Task order matters** (no-downtime cutover): 1 → 2 → 3 (incl. the manual Pages toggle + live verify) → 4 → 5. Do not run Task 4 before Task 3 step 4 confirms the Action serves the site, or `/blog/` will 404 until the toggle.
- Run all Python via `.venv/bin/python` (host Python is externally managed).
- The cron schedule can only be fully verified on the real timer; `workflow_dispatch` exercises the same job immediately.
