#!/usr/bin/env python3
"""Carmen's Names of the Day — static site generator.

Architecture twin of tia-n-list's engine/ssg.py: all markup lives in
templates/, this file is logic only. Reads the text store
(data/days/<date>.txt + data/master-names.csv), builds the render context,
and renders the Jinja2 templates into the repository root (GitHub Pages
serves the root via the site-deploy workflow).

Text store:
  data/days/<YYYY-MM-DD>.txt   one file per day; lines not starting with '#'
                               are name blocks ("PEREZ & LYNN"); a block may
                               also be a single name.
  data/master-names.csv        popularity reference (name,years_in_top1000,
                               total_share), distilled from the SSA national
                               baby-names dataset (public domain).

Outputs:
  index.html               today's (latest tracked) names + recent days
  style.css                Carmen's-flavored theme
  history/index.html       every day, grouped by year and month
  day/<date>/index.html    permalink per day (RSS target)
  name/<slug>/index.html   per-name page: last called, times, all dates
  names/index.html         A-Z directory with client-side filter
  stats/index.html         most common, longest absent, never called, fun facts
  rss.xml                  feed of the latest days
  names.json               machine-readable dump of all days
  404.html, robots.txt

Usage: python3 engine/ssg.py   (from the repo root; also importable —
       build(repo_root, out_dir) is used by engine/test_ssg.py)
"""
import collections
import csv
import html
import json
import os
import re
import sys
from datetime import date, datetime

from jinja2 import Environment, FileSystemLoader, select_autoescape

ENGINE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(ENGINE)                       # repo root = Pages root
TMPL_DIR = os.path.join(ENGINE, "templates")
DAYS_DIR = os.path.join(ENGINE, "data", "days")
MASTER_CSV = os.path.join(ENGINE, "data", "master-names.csv")

BASE_URL = "https://zarguell.github.io/carmens-names"
SITE_NAME = "Carmen's Names of the Day"
FACEBOOK_PAGE = "https://www.facebook.com/CarmensItalianIce/"
CARMENS_SITE = "https://carmensitalianice.com/"
RSS_MAX_ITEMS = 60
RECENT_ON_INDEX = 14
DORMANT_TOP = 25
NEVER_CALLED_TOP = 50

BLOCK_SPLIT = re.compile(r"\s*&\s*|\s+and\s+", re.IGNORECASE)
DAY_LINE = re.compile(r"^[A-Z][A-Z '&\-]*$")


# ── store ────────────────────────────────────────────────────────────────────
def parse_day_text(text):
    """Return the name blocks from one day file's body.

    Lines starting with '#' (and blanks) are comments. Every other line is a
    block: one or more names joined by '&' (e.g. "PEREZ & LYNN").
    """
    blocks = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        names = [n.strip() for n in BLOCK_SPLIT.split(line.upper()) if n.strip()]
        if names:
            blocks.append(names)
    return blocks


def load_days(days_dir=None):
    """Load every day file; returns a list of dicts sorted by date ascending."""
    days_dir = days_dir or DAYS_DIR
    days = []
    for fn in sorted(os.listdir(days_dir)):
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}\.txt", fn):
            continue
        d = fn[:10]
        date.fromisoformat(d)  # validates
        blocks = parse_day_text(open(os.path.join(days_dir, fn)).read())
        if blocks:
            days.append({"date": d, "blocks": blocks,
                         "names": [n for b in blocks for n in b]})
    days.sort(key=lambda d: d["date"])
    return days


def slugify(name):
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


# ── aggregation ──────────────────────────────────────────────────────────────
def build_name_stats(days):
    """name -> {count, dates, first, last} across all tracked days."""
    stats = collections.defaultdict(lambda: {"count": 0, "dates": []})
    for day in days:
        for name in day["names"]:
            s = stats[name]
            s["count"] += 1
            s["dates"].append(day["date"])
    for name, s in stats.items():
        s["first"] = s["dates"][0]
        s["last"] = s["dates"][-1]
    return dict(stats)


def load_master(path=None):
    """Master first-name list -> {name: rank} (rank 1 = most enduringly popular)."""
    path = path or MASTER_CSV
    ranks = {}
    if not os.path.exists(path):
        return ranks
    with open(path) as f:
        next(f)  # header
        for i, row in enumerate(csv.reader(f), start=1):
            if row and row[0]:
                ranks[row[0].strip().upper()] = i
    return ranks


def days_between(later_iso, earlier_iso):
    return (date.fromisoformat(later_iso) - date.fromisoformat(earlier_iso)).days


# ── presentation helpers (exposed to templates) ─────────────────────────────
def fmt_date(iso, fmt="%B %-d, %Y"):
    return datetime.strptime(iso, "%Y-%m-%d").strftime(fmt) if iso else ""


def fmt_short(iso):
    return fmt_date(iso, "%b %-d")


def fmt_weekday(iso):
    return fmt_date(iso, "%A")


def chip_class(name):
    """Stable playful color per name (Carmen's flavor palette)."""
    palette = ["red", "blue", "green", "coral", "orange"]
    return palette[sum(ord(c) for c in name) % len(palette)]


def pl(n, word):
    if n is None:
        return ""
    return f"{n} {word}" + ("" if n == 1 else "s")


def esc(s):
    return html.escape(s, quote=True)


# ── build ────────────────────────────────────────────────────────────────────
def build(repo_root=None, out_dir=None):
    repo_root = repo_root or ROOT
    out = os.path.abspath(out_dir or repo_root)
    days_dir = os.path.join(repo_root, "data", "days")
    master_path = os.path.join(repo_root, "data", "master-names.csv")
    env = Environment(
        loader=FileSystemLoader(TMPL_DIR),
        autoescape=select_autoescape(["html", "xml"]),
    )
    env.globals.update(
        site_name=SITE_NAME, base_url=BASE_URL,
        facebook_page=FACEBOOK_PAGE, carmens_site=CARMENS_SITE,
        fmt_date=fmt_date, fmt_short=fmt_short, fmt_weekday=fmt_weekday,
        chip_class=chip_class, pl=pl, slugify=slugify, generated=iso_now(),
        rss_pubdate=rss_pubdate,
    )

    days = load_days(days_dir)
    if not days:
        raise SystemExit("no day data found — nothing to build")
    latest = days[-1]
    stats = build_name_stats(days)
    master = load_master(master_path)

    def url(rel):
        return f"{BASE_URL}/{rel}"

    # name pages, A-Z
    by_name = {}
    for name in sorted(stats):
        s = stats[name]
        rank_all = sorted(stats, key=lambda n: (-stats[n]["count"], n)).index(name) + 1
        by_name[name] = {
            "name": name, "slug": slugify(name), **s,
            "days_since": days_between(latest["date"], s["last"]),
            "rank": rank_all, "total_names": len(stats),
            "master_rank": master.get(name),
        }

    never = [
        {"name": n, "master_rank": r}
        for n, r in sorted(master.items(), key=lambda kv: kv[1])
        if n not in stats
    ]
    dormant = sorted(by_name.values(), key=lambda v: (-v["days_since"], v["name"]))
    duos = collections.Counter(
        tuple(sorted(b)) for d in days for b in d["blocks"] if len(b) == 2)
    year = latest["date"][:4]
    # history grouped by year -> month for the archive page
    years = []
    for d in reversed(days):
        y, m = d["date"][:4], d["date"][5:7]
        ybox = next((y_ for y_ in years if y_["year"] == y), None)
        if ybox is None:
            ybox = {"year": y, "months": []}
            years.append(ybox)
        mbox = next((m_ for m_ in ybox["months"] if m_["num"] == m), None)
        if mbox is None:
            mbox = {"num": m, "label": fmt_date(d["date"], "%B"), "days": []}
            ybox["months"].append(mbox)
        mbox["days"].append(d)
    # prev/next day permalinks
    day_nav = {}
    for i, d in enumerate(days):
        day_nav[d["date"]] = (days[i - 1]["date"] if i > 0 else None,
                              days[i + 1]["date"] if i + 1 < len(days) else None)
    this_year_counts = collections.Counter(
        n for d in days if d["date"].startswith(year) for n in d["names"])
    ctx = {
        "r": "",                                   # root-relative prefix (set per page)
        "latest": latest,
        "recent": list(reversed(days[-RECENT_ON_INDEX:])),
        "days": days,
        "by_name": by_name,
        "names_sorted": sorted(by_name.values(), key=lambda v: v["name"]),
        "years": years,
        "day_nav": day_nav,
        "most_common": sorted(by_name.values(), key=lambda v: (-v["count"], v["name"])),
        "this_year": [{"name": n, "slug": slugify(n), "count": c}
                      for n, c in this_year_counts.most_common(15)],
        "dormant": dormant[:DORMANT_TOP],
        "never": never[:NEVER_CALLED_TOP],
        "never_total": len(never),
        "master_total": len(master),
        "duos": [{"names": list(k), "count": c} for k, c in duos.most_common(5)],
        "total_days": len(days),
        "total_slots": sum(len(d["names"]) for d in days),
        "year": year,
    }

    def render(template, path, **extra):
        c = dict(ctx)
        c["r"] = "../" * path.count("/")
        c.update(extra)
        dest = os.path.join(out, path)
        os.makedirs(os.path.dirname(dest) or out, exist_ok=True)
        with open(dest, "w") as f:
            f.write(env.get_template(template).render(**c))
        return dest

    written = []
    written.append(render("index.html", "index.html"))
    written.append(render("style.css", "style.css"))
    written.append(render("404.html", "404.html"))
    written.append(render("robots.txt", "robots.txt"))
    written.append(render("names.json", "names.json"))
    written.append(render("history.html", os.path.join("history", "index.html")))
    written.append(render("names_dir.html", os.path.join("names", "index.html")))
    written.append(render("stats.html", os.path.join("stats", "index.html")))
    for d in days:
        written.append(render("day.html", os.path.join("day", d["date"], "index.html"), day=d))
    for v in by_name.values():
        written.append(render("name.html", os.path.join("name", v["slug"], "index.html"), name=v))

    # RSS (absolute URLs; pubDate anchored to the scrape time, 12:45 US/Eastern)
    rss_days = list(reversed(days[-RSS_MAX_ITEMS:]))
    c = dict(ctx, r="", rss_days=rss_days, rss_url=url("rss.xml"))
    dest = os.path.join(out, "rss.xml")
    with open(dest, "w") as f:
        f.write(env.get_template("rss.xml").render(**c))
    written.append(dest)

    print(f"rendered {len(written)} files "
          f"({len(days)} days, {len(by_name)} names) -> {out}")
    return written


def iso_now():
    from email.utils import format_datetime
    from zoneinfo import ZoneInfo
    return format_datetime(datetime.now(ZoneInfo("America/New_York")))


def rss_pubdate(date_iso):
    """RFC-822 pubDate anchored to the daily scrape, 12:45 US/Eastern."""
    from email.utils import format_datetime
    from zoneinfo import ZoneInfo
    et = ZoneInfo("America/New_York")
    dt = datetime.strptime(date_iso, "%Y-%m-%d").replace(hour=12, minute=45, tzinfo=et)
    return format_datetime(dt)


def main():
    return build()


if __name__ == "__main__":
    sys.exit(main())
