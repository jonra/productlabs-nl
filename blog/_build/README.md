# Blog build system

Static site generator for `/blog`. Markdown sources in, HTML out. No runtime
dependency — the generated HTML is committed and served directly by GitHub Pages.

## Requirements

```
pip install markdown
```

## Building

```
python3 blog/_build/build.py           # build everything
python3 blog/_build/build.py --check   # parse and render without writing
```

Run `--check` before committing. It validates front matter, catches unknown topics,
duplicate slugs and broken `related:` references, and fails loudly rather than
producing a half-built site.

## What gets generated

| Output | Source |
|---|---|
| `/blog/<slug>/index.html` | one per markdown file in `articles/` |
| `/blog/index.html` | landing page — featured article plus full list |
| `/blog/topics/<topic>/index.html` | one per topic that has at least one article |
| `/sitemap.xml` | homepage, blog, topic hubs and every article |

`_build/` starts with an underscore, so GitHub Pages' Jekyll processing skips it and
the sources are never published. If you ever add a `.nojekyll` file, rename this
directory or the markdown will be served publicly.

## Adding an article

Create `articles/your-slug.md`:

```markdown
---
title: The full headline, as it appears on the page
slug: your-slug
dek: One or two sentences. Used as the summary on the landing page and as the
  fallback meta description.
type: article
topic: mcp
date: 2026-08-10
updated: 2026-08-10
reading_time: 9
order: 5
featured: false
badge_new: false
meta_title: "Optional — overrides the <title> tag"
meta_description: Optional — overrides the meta description
keywords: [comma, separated, list]
related: [another-slug, third-slug]
sources:
  - Label of the source|https://example.com/source
---

Body in markdown.
```

Required keys: `title`, `slug`, `dek`, `date`. Everything else is optional.

Then run the build. Nothing else needs editing — the landing page, topic hubs,
sitemap and cross-links all regenerate.

### Front matter notes

- **`order`** breaks ties between articles sharing a date. Higher sorts first.
- **`featured: true`** promotes an article to the hero slot on `/blog/`. Pair it with
  `featured_reason:` — a sentence explaining why it leads. Only set this on one article.
- **`badge_new: true`** adds a "New" badge in listings. Remember to remove it later.
- **`related:`** must reference slugs that exist. The build fails if they do not.
- **`sources:`** entries use `Label|URL`. Every article making factual claims should
  carry these.

### Callouts

Raw HTML works inside markdown. For the dated-verification box used on
version-sensitive articles:

```html
<div class="callout">
<span class="callout-label">Verified 10 August 2026</span>
<p>Text.</p>
</div>
```

## Adding a topic

Add an entry to `TOPICS` in `build.py`:

```python
"your-topic": {
    "label": "Short",              # topic bar chip
    "title": "Full topic title",   # hub page H1
    "blurb": "One sentence.",      # hub page subtitle
},
```

Topics with no articles are skipped — they will not produce an empty hub page.

## Adding a new content type

`CONTENT_TYPES` already has entries scaffolded for `case-study`, `tool` and `note`.
Set `type: case-study` in a source file's front matter and it will build to
`/blog/case-studies/<slug>/`. Add further types by adding a dict entry with a `dir`.

Suggested uses:

- **`case-study`** — client work, anonymised. The highest-converting content type for
  a consultancy, and the one that most needs a client's written sign-off first.
- **`tool`** — free utilities. `binary.tools` may be a better home if these grow into
  real products.
- **`note`** — short posts. Spec changes, release commentary, quick findings. Lower
  effort, keeps the cadence up between long pieces.

## Publishing dates

The ten launch articles carry `date` values spread across 12 July – 10 August 2026,
with `updated: 2026-08-10` on all of them. The `updated` date is real — everything was
verified against source on 10 August, which is what the "verified" callouts refer to.
The `date` values are backdated.

Each publish date was chosen as the **earliest date the article's own content allows**,
so nothing references an event that had not happened yet:

| Date | Article | Constraint |
|---|---|---|
| 12 Jul | `mcp-tool-schema-design` | none — craft piece, no version-dependent claims |
| 16 Jul | `claude-prompt-caching-guide` | Claude docs only |
| 20 Jul | `mcp-tool-definition-token-cost` | Claude docs only |
| 24 Jul | `claude-model-selection-cost-per-task` | Claude docs only |
| 29 Jul | `mcp-2026-07-28-migration-stateless-protocol` | ≥ 28 Jul, the spec revision date |
| 1 Aug | `mcp-transports-stdio-vs-streamable-http` | ≥ 28 Jul |
| 4 Aug | `eu-ai-act-gdpr-claude-deployment` | ≥ 2 Aug, when the GPAI grace period ended |
| 6 Aug | `mcp-oauth-authorization-guide` | ≥ 28 Jul |
| 8 Aug | `prompt-injection-tool-using-agents` | ≥ 28 Jul (cites the auth spec) |
| 10 Aug | `testing-debugging-mcp-servers` | ≥ 28 Jul |

The two earliest articles had an incidental citation of the `2026-07-28` spec removed,
because a 12 July article cannot cite a 28 July document. Neither depended on it.

**What this does and does not achieve.** Google records when it first *crawls* a URL,
not what the byline says, so ten pages appearing in one push still look like ten pages
appearing in one push. The dates make the archive read as a consultancy that has been
writing for a month, which helps a human evaluating the site — a prospective client, or
someone deciding whether to link to you. It does not change the crawl pattern.

If you want the crawl pattern to look organic too, push in three or four commits over
the coming weeks rather than all at once. The dates already support that story.

## Before publishing any article

These were drafted with LLM assistance against sources verified on 10 August 2026.
Both of the following need doing at publication time, not at drafting time:

1. **Run the code.** Every code block should be executed before it goes live. The
   token-cost script and the pytest suite were both run during drafting; re-run them
   if you change anything.
2. **Re-verify version-dependent claims.** Model pricing, MCP spec behaviour and
   regulatory deadlines all move. Anything in a `callout` box with a "verified" date is
   flagged precisely because it needs re-checking. Update the `updated:` field when you
   do.

An article with a stale price or a superseded spec claim does more damage to a
technical consultancy's credibility than not publishing it at all.
