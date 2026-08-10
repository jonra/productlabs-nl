# Scheduled publishing for /blog — design

**Date:** 2026-08-10
**Status:** Approved (pending spec review)

## Problem

The blog build (`blog/_build/build.py`) renders every markdown source immediately,
regardless of its `date` field. Publishing N articles therefore makes N pages appear
in a single crawl, which:

1. Contradicts spread-out byline dates (the crawl pattern gives away a bulk dump).
2. Prevents an editorial calendar — you cannot write ahead and have pieces go live
   later on their own.

The goal: author many articles now (each with a future `date`), and have them go live
one at a time on their publish date, with everything Google sees — page, sitemap
entry, first-crawl date — consistent and truthful.

## Scope boundary (important)

This system solves **publishing cadence and crawl timing**. It does **not** make
content volume safe. Google's scaled-content-abuse policy is content-based and
domain-wide; dripping low-value pages slowly does not remove them from scope and can
demote the whole domain. This design assumes each scheduled article is a genuinely
researched piece at the quality bar of the existing ten. That assumption is the
project's load-bearing constraint, not an implementation detail.

## Architecture decisions

- **Public repo, sources visible.** Drafts live as tracked markdown in this public
  repo. Build-time gating hides the rendered page and sitemap entry until the publish
  date; the raw markdown is readable by anyone who clones the repo. Acceptable because
  the content is destined for publication anyway. (Rejected: private-sources /
  public-output split — cleaner secrecy, but two repos + a deploy token + more failure
  modes, for secrecy not needed here.)
- **GitHub Pages built by a scheduled GitHub Action.** Sources are the single source
  of truth; generated HTML is not committed. A daily cron rebuild deploys whatever has
  become due. (Rejected: committing generated HTML via a bot cron — clutters history
  with automated commits; and a local-only publish script — nothing goes live unless a
  human runs it that day, which defeats scheduling.)

## Components

### 1. Date gate in `build.py`

- Compute `today` in `Europe/Amsterdam` via `zoneinfo`.
- An article is **live** iff `date <= today` **and** `draft` is not `true`.
- Non-live documents are excluded from: rendered article pages, the landing page,
  topic hubs, and `sitemap.xml`.
- `related:` links are filtered to live articles only at render time, so a published
  page never links to a not-yet-live URL (no 404s / soft-404s).
- `--check` cross-reference validation continues to run against **all** sources (a
  future article referenced by `related:` still exists as a source, so references
  remain valid); only rendering applies the live filter.
- Topic-hub cleanup already unlinks stale topic pages; it must also unlink a topic hub
  that has zero *live* articles (e.g. a topic whose only article is still scheduled).

### 2. Authoring affordances

- **`draft: true`** front-matter flag — excludes an article regardless of date. Remove
  it (or set false) to let the date gate take over.
- **`build.py --preview`** — builds everything, ignoring the gate (future + drafts),
  for local review. Output is for local viewing only; production is always built by the
  Action with the gate on, so preview output is never deployed.

### 3. GitHub Action `.github/workflows/publish.yml`

- **Triggers:**
  - `push` to `main` (deploy editorial changes immediately),
  - `schedule` daily cron `0 6 * * *` UTC (~08:00 Europe/Amsterdam; flips due articles
    live each morning),
  - `workflow_dispatch` (manual run).
- **Steps:** checkout → setup Python → `pip install -r blog/_build/requirements.txt`
  → `python blog/_build/build.py` → **package `_site/`** (see below) → upload `_site/`
  as a Pages artifact → deploy to Pages.
- **Packaging `_site/` (critical):** the Action does not upload the repo root. Under
  Actions-built Pages there is no Jekyll, so the `_build/` underscore no longer hides
  anything — uploading root would serve `blog/_build/` sources and `docs/` specs at
  public URLs. Instead, a packaging step copies **only the publishable set** into
  `_site/`: `index.html`, `CNAME`, `robots.txt`, `sitemap.xml`, and `blog/` **excluding
  `blog/_build/`**. Everything else (`docs/`, `.github/`, `.git/`, build sources) is
  omitted. Only `_site/` is uploaded.
- **Permissions:** `pages: write`, `id-token: write`; standard `actions/deploy-pages`.
- **One-time manual step (user):** repo **Settings → Pages → Source = GitHub Actions**.

### 4. Repo/model change

- Un-gitignore `blog/_build/` so sources are tracked. Keep `.docx`, `.idea/`,
  `.DS_Store` ignored.
- Stop tracking generated output: `git rm --cached` the generated blog HTML and
  `sitemap.xml`, and add them to `.gitignore`. They are rebuilt fresh on every deploy.
- Keep tracked: `index.html`, `CNAME`, `robots.txt`, `blog/assets/blog.css`.
- Add `blog/_build/requirements.txt` pinning `markdown`.

### 5. Rewrite `blog/_build/README.md`

- Remove the "Publishing dates" / backdating section entirely. Going forward dates are
  honest and sources are public; that rationale should not exist, least of all in a
  public repo.
- Document: the date gate, `draft`, `--preview`, and the Action-driven deploy flow.

## Data flow

```
author writes articles/<slug>.md (date = future)   →  git push (source only)
                                                       │
GitHub Action (push + daily cron)                      ▼
  build.py  →  gate: date <= today(Amsterdam) & !draft
             →  renders only live articles + landing + topic hubs + sitemap
             →  deploy to GitHub Pages
                                                       │
                                                       ▼
             a future article first becomes a live URL + sitemap entry
             on its publish date; 404 before then
```

## Existing content

All ten current articles are past-dated, so they remain live through the gate — no
disruption. Their existing (backdated) dates are left as-is; re-dating already-published
pages serves nothing. The system is honest from here forward.

## Error handling / edge cases

- **Timezone:** `zoneinfo("Europe/Amsterdam")`; Python 3.9+ (host has 3.14).
- **`related:` → unpublished slug:** filtered out of the rendered related list; never
  produces a link to a non-existent page.
- **Topic with only scheduled articles:** hub not generated; a previously-generated hub
  that now has zero live articles is unlinked.
- **Nothing newly due on a cron run:** build output is identical; Pages redeploys the
  same site harmlessly (idempotent).
- **Guessed future URL:** returns 404 (the page genuinely does not exist yet) — correct.
- **Source/spec leak via Pages:** prevented by the `_site/` allowlist packaging — only
  published output is uploaded, never `blog/_build/` or `docs/`. A regression here would
  expose sources on the live domain, so the packaging step is load-bearing.
- **Cron vs. midnight:** a `date: today` article goes live at ~08:00 Amsterdam, not
  00:00. Acceptable; adjust the cron expression if sharper timing is wanted.

## Testing

- **Gate unit check:** add a temp future-dated article; assert it is absent from the
  build output and from `sitemap.xml`, and present under `--preview`; then remove it.
- **Regression:** confirm the current ten still build and appear in the sitemap.
- **Draft flag:** an article with `draft: true` and a past date is excluded; present
  under `--preview`.
- **Related filtering:** a live article whose `related:` points to a scheduled slug
  renders without that link and without error.
- **Packaging exclusion:** assert the assembled `_site/` contains `index.html`,
  `sitemap.xml`, `robots.txt`, `CNAME`, and `blog/index.html`, and does **not** contain
  `blog/_build/` or `docs/`. This can be checked locally by running the same packaging
  commands the workflow uses.
- **Workflow:** YAML validated; `build.py` runs clean in CI. The cron schedule itself
  only proves out on the real timer (and via `workflow_dispatch`).

## Out of scope (YAGNI)

RSS/Atom feed, an article-scaffolding helper, the private-source split. Each is easy to
add later if wanted; none is needed for scheduled publishing.
