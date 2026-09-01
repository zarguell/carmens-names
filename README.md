# Carmen's Names of the Day

An unofficial fan tracker of the **Names of the Day** posted by
[Carmen's Italian Ice](https://carmensitalianice.com/) on their public
[Facebook page](https://www.facebook.com/CarmensItalianIce/). If it's your
name, free gelati.

**Live site:** https://zarguell.github.io/carmens-names/

## What's inside

- **Today's names**: the latest tracked day, front and center
- **RSS feed**: [`rss.xml`](https://zarguell.github.io/carmens-names/rss.xml)
- **Full history**: every day since December 2025, grouped by year and month
- **Name pages**: "when was this name last the Name of the Day?" for all
  ~500 names (plus an A-Z directory with search)
- **Stats**: most common names, longest absences, classic duos, and the
  most popular names that have *never* been called (checked against a master
  list of first names) — plus **name families**, where nicknames and spellings
  are grouped (Margaret, Peggy and Meg count as one crowd)

## How it works

```
Facebook (public page) --> daily scraper --> data/days/*.txt --> GitHub --> GitHub Actions --> GitHub Pages
```

1. **Scrape.** A private automation renders the public Facebook page daily,
   extracts the "Names of the Day" block(s), and commits one plain-text file
   per day to `data/days/`.
2. **Commit.** The data *is* the store. One human-readable file per day:
   ```
   # Names of the Day: 2026-08-31
   PEREZ & LYNN
   ```
   Every day is a diff, so the archive is auditable git history.
3. **Build.** On every push (and a nightly rebuild), a GitHub Action runs
   `engine/ssg.py`, a small dependency-light static site generator,
   contract-tests first, then renders HTML/CSS/RSS/JSON into the repo root.
4. **Publish.** The rendered root is deployed to GitHub Pages.

## Building locally

```bash
pip install jinja2
python engine/test_ssg.py    # contract tests
python engine/ssg.py         # renders the site into the repo root
python -m http.server        # browse http://localhost:8000
```

## Data format

`data/days/YYYY-MM-DD.txt`: lines starting with `#` are comments; every
other line is one Name-of-the-Day block (one or more names, joined with `&`).
A day file whose only body line is `CLOSED` records a closure (the shop was
closed; no names served):

`data/master-names.csv`: the "never called" reference list. First names
distilled from the [US SSA national baby-names dataset](https://www.ssa.gov/oact/babynames/backs.html)
(public domain), with longevity rank.

## Credits and disclaimer

Names of the Day are chosen and posted by Carmen's Italian Ice. This site is
an unofficial fan project, not affiliated with or endorsed by Carmen's Italian
Ice & More. All names belong to the lovely people who order gelati.
