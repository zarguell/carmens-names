# AGENTS.md

Notes for anyone (AI agent or human) changing this repo. Read this first —
it covers the things that cost someone time already.

## What this is

An unofficial fan tracker of Carmen's Italian Ice "Names of the Day". A
private daily scraper commits one text file per day to `data/days/`; the
scraper itself is **not** in this repo — data arrives as git commits.
`engine/ssg.py` (small Jinja2 SSG) renders the entire site into the repo
root; GitHub Actions tests + builds on every push and a nightly cron, then
deploys to GitHub Pages.

## Layout

- `data/days/YYYY-MM-DD.txt` — the data store. Lines starting with `#` are
  comments; each body line is a name block (`PEREZ & LYNN`); a lone `CLOSED`
  marks a shop closure (tracked day, zero names).
- `data/master-names.csv` — SSA first-name reference; drives the
  "never called" stat.
- `engine/ssg.py` — all build logic. **All markup lives in
  `engine/templates/`** — this file should stay logic-only.
- Rendered output sits in the repo ROOT (`index.html`, `day/`, `name/`,
  `history/`, `about/`, `names/`, `stats/`, `rss.xml`, …) and is
  **gitignored build output. Never hand-edit it** — edit templates and rebuild.

## Commands

```bash
.venv/bin/python engine/test_ssg.py   # contract tests (CI gate)
.venv/bin/python engine/ssg.py        # renders site into repo root
python3 -m http.server 8000           # then browse localhost:8000
```

The system python has no jinja2 — use `.venv/` (exists; recreate with
`python3 -m venv .venv && .venv/bin/pip install jinja2` if missing).

## Gotchas

- **Tests really execute now.** `engine/test_ssg.py` once only worked under
  pytest while CI ran it as a plain script — a silent no-op that let four
  broken assertions ship. It now has a `main()` that runs every `test_*`
  function. Keep it dependency-light (no pytest requirement) and make sure
  new tests actually fail when they should.
- **Relative links need the `{{ r }}` prefix** (e.g. `{{ r }}name/x/`). It's
  computed per page from path depth in `render()`. A wrong depth silently
  produces dead links on nested pages.
- **CSS has a global `[hidden] { display: none !important }` guard.**
  Elements with an explicit `display` (like `.dir-item`'s `inline-flex`)
  ignore the HTML `hidden` attribute without it — the names-directory search
  once set `hidden` correctly while nothing disappeared. Any new JS filtering
  depends on this rule; don't remove it.
- **Date helpers** (registered for every template): `fmt_date`
  (January 3, 2026), `fmt_short` (Jan 3 — no year), `fmt_med` (Jan 3, 2026),
  `fmt_weekday`. Site convention: user-facing first/last dates and date chips
  always include the year → use `fmt_med`. (`%-d` is fine on macOS and the
  ubuntu CI; not on Windows.)
- **History is a calendar**: `history/index.html` renders the latest tracked
  month, and every tracked month gets `history/YYYY-MM/index.html` with
  year/month tabs. Grids come from `build_month_index()` in ssg.py. Months
  with no day files get no page on purpose — see data policy below.
- **Stale outputs are pruned** via `.build-manifest` (gitignored): remove a
  day file or rename a slug and the old page vanishes on the next build.
- **Absolute URLs are hardcoded** (`BASE_URL` in ssg.py) for RSS/manifest
  links — update there if the site ever moves.
- **Adding a page**: create `engine/templates/<page>.html`, render it inside
  `build()` (append to `written`), add the output dir to `.gitignore` if it's
  a new top-level one, and add a nav link in `base.html`.

## Data policy

A missing day means the post couldn't be recovered — it is **not** a closure
(closures exist only where the day file says `CLOSED`). Backfill rule:
blanks over incorrect — never guess a name. Keep the one-file-per-day format
exact; git history of `data/` is the audit trail.

Nickname/spelling families live in `data/name-families.csv` (`family,variant`
rows, unioned at build time — rows sharing any name merge into one family).
The display head is the called member with the best master rank, so heads
always link to a real page. Keep modern standalone names out of merges
(LIAM is not WILLIAM, BELLA is not ISABELLA); a family means "variants
seen", never "same person".

## Verify UI changes in a browser

The contract tests check HTML strings, not rendered behavior. Anything
visual or interactive (filters, calendar navigation, layout) must be
rebuild → serve → clicked through in a real browser before you call it done.
