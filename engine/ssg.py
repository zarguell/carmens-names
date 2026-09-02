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
  history/index.html       calendar for the latest tracked month
  history/<YYYY-MM>/       calendar for one month (year tabs + month tabs)
  about/index.html         methodology, in website form
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
import calendar as calmod
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
DAYS_DIR = os.path.join(ROOT, "data", "days")
MASTER_CSV = os.path.join(ENGINE, "data", "master-names.csv")

BASE_URL = "https://zarguell.github.io/carmens-names"
SITE_NAME = "Carmen's Names of the Day"
FACEBOOK_PAGE = "https://www.facebook.com/CarmensItalianIce/"
CARMENS_SITE = "https://carmensitalianice.com/"
RSS_MAX_ITEMS = 60
RECENT_ON_INDEX = 14
DORMANT_TOP = 25
NEVER_CALLED_TOP = 50
MANIFEST_NAME = ".build-manifest"          # rendered-path ledger for stale pruning
CLOSED_MARKER = "CLOSED"                   # sole body line marking a closure day

BLOCK_SPLIT = re.compile(r"\s*&\s*|\s+and\s+", re.IGNORECASE)
DAY_LINE = re.compile(r"^[A-Z][A-Z '&\-]*$")


# ── store ────────────────────────────────────────────────────────────────────
def parse_day_text(text):
    """Parse one day file's body -> {"closed": bool, "blocks": [[names], ...]}.

    Lines starting with '#' (and blanks) are comments. A non-comment line
    equal to CLOSED marks the day as a shop closure (no names served).
    Every other non-comment line is a block: one or more names joined by
    '&' (e.g. "PEREZ & LYNN").
    """
    closed = False
    blocks = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.upper() == CLOSED_MARKER:
            closed = True
            continue
        names = [n.strip() for n in BLOCK_SPLIT.split(line.upper()) if n.strip()]
        if names:
            blocks.append(names)
    return {"closed": closed, "blocks": blocks}


def load_days(days_dir=None):
    """Load every day file; returns a list of dicts sorted by date ascending."""
    days_dir = days_dir or DAYS_DIR
    days = []
    for fn in sorted(os.listdir(days_dir)):
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}\.txt", fn):
            continue
        d = fn[:10]
        date.fromisoformat(d)  # validates
        parsed = parse_day_text(open(os.path.join(days_dir, fn)).read())
        if parsed["blocks"] or parsed["closed"]:
            days.append({"date": d, "closed": parsed["closed"],
                         "blocks": parsed["blocks"],
                         "names": [n for b in parsed["blocks"] for n in b]})
    days.sort(key=lambda d: d["date"])
    return days


def build_month_index(days):
    """Every tracked month -> list of dicts (ascending) for the calendar UI.

    Each month carries a Sunday-first grid of weeks; every cell is None
    (padding), or {"num": day-of-month, "day": day-dict-or-None} where a
    missing day dict means "tracked nowhere — no data for that date".
    prev/next are the adjacent *tracked* month keys (YYYY-MM).
    """
    by_ym = collections.defaultdict(dict)
    for d in days:
        by_ym[d["date"][:7]][d["date"]] = d
    keys = sorted(by_ym)
    months = []
    for i, key in enumerate(keys):
        y, m = int(key[:4]), int(key[5:7])
        weeks = []
        for week in calmod.Calendar(firstweekday=6).monthdayscalendar(y, m):
            weeks.append([
                None if dd == 0 else
                {"num": dd, "day": by_ym[key].get(f"{y:04d}-{m:02d}-{dd:02d}")}
                for dd in week
            ])
        months.append({
            "key": key, "year": str(y), "num": m,
            "label": calmod.month_name[m],
            "days": list(by_ym[key].values()),
            "weeks": weeks,
            "prev": keys[i - 1] if i > 0 else None,
            "next": keys[i + 1] if i + 1 < len(keys) else None,
        })
    return months


def year_links_of(months):
    """[{"year": "2023", "first": "2023-01"}, …] — one tab per tracked year."""
    links = []
    for m in months:
        if not links or links[-1]["year"] != m["year"]:
            links.append({"year": m["year"], "first": m["key"]})
    return links


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


def load_families(path, master):
    """name-families.csv (family,variant rows) -> {name: component_key}.

    Rows sharing any name are unioned into one family (e.g. TED under both
    EDWARD and THEODORE merges the two). The component key is just the
    union-find root — the display head is chosen later, among the family's
    *called* members, by master rank. Missing file -> no families.
    """
    if not os.path.exists(path):
        return {}
    parent = {}

    def find(x):
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    with open(path) as f:
        next(f)  # header
        for row in csv.reader(f):
            if len(row) >= 2 and row[0].strip() and row[1].strip():
                a, b = row[0].strip().upper(), row[1].strip().upper()
                ra, rb = find(a), find(b)
                if ra != rb:
                    parent[rb] = ra
    return {n: find(n) for n in parent}


def days_between(later_iso, earlier_iso):
    return (date.fromisoformat(later_iso) - date.fromisoformat(earlier_iso)).days


def prune_stale(out, manifest_path, current):
    """Delete files the previous build rendered but this one didn't.

    The manifest (.build-manifest) lists every file the last build wrote.
    Anything listed there but absent from `current` is a stale artifact
    (e.g. a name page whose slug changed, or a day page whose source file
    was removed). Empty parent directories are removed up to `out`.
    First build after adoption has no manifest, so this is a no-op.
    """
    try:
        with open(manifest_path) as f:
            previous = [ln.strip() for ln in f if ln.strip()]
    except FileNotFoundError:
        return 0
    current_set = set(current)
    out_abs = os.path.abspath(out)
    removed = 0
    for rel in previous:
        if rel in current_set:
            continue
        p = os.path.abspath(os.path.join(out_abs, rel))
        if not p.startswith(out_abs + os.sep):
            continue                      # path escape guard, never touch outside out
        if os.path.isfile(p):
            os.unlink(p)
            removed += 1
        d = os.path.dirname(p)
        while d != out_abs and d.startswith(out_abs + os.sep):
            try:
                os.rmdir(d)               # succeeds only when empty
            except OSError:
                break
            d = os.path.dirname(d)
    return removed


# ── presentation helpers (exposed to templates) ─────────────────────────────
def fmt_date(iso, fmt="%B %-d, %Y"):
    return datetime.strptime(iso, "%Y-%m-%d").strftime(fmt) if iso else ""


def fmt_short(iso):
    return fmt_date(iso, "%b %-d")


def fmt_med(iso):
    """Short date that always carries the year: 'Jan 3, 2026'."""
    return fmt_date(iso, "%b %-d, %Y")


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
        fmt_date=fmt_date, fmt_short=fmt_short, fmt_med=fmt_med, fmt_weekday=fmt_weekday,
        chip_class=chip_class, pl=pl, slugify=slugify, generated=iso_now(),
        rss_pubdate=rss_pubdate,
    )

    days = load_days(days_dir)
    if not days:
        raise SystemExit("no day data found — nothing to build")
    latest = days[-1]
    latest_names_day = next((d for d in reversed(days) if not d["closed"]), None)
    closed_days = sum(1 for d in days if d["closed"])
    stats = build_name_stats(days)
    master = load_master(master_path)
    fam = load_families(os.path.join(repo_root, "data", "name-families.csv"), master)

    # family aggregates over *called* names; the display head is the called
    # member with the best master rank, so every head links to a real page
    fam_members = collections.defaultdict(dict)
    for n, s in stats.items():
        fam_members[fam.get(n, n)][n] = s["count"]

    def fam_head(comp):
        return min(fam_members[comp], key=lambda m: (master.get(m, 10**9), m))

    def url(rel):
        return f"{BASE_URL}/{rel}"

    # name pages, A-Z
    by_name = {}
    for name in sorted(stats):
        s = stats[name]
        rank_all = sorted(stats, key=lambda n: (-stats[n]["count"], n)).index(name) + 1
        entry = {
            "name": name, "slug": slugify(name), **s,
            "days_since": days_between(latest_names_day["date"], s["last"]) if latest_names_day else 0,
            "rank": rank_all, "total_names": len(stats),
            "master_rank": master.get(name),
        }
        comp = fam.get(name, name)
        if len(fam_members.get(comp, {})) >= 2:
            day_names = collections.defaultdict(list)
            for n in fam_members[comp]:
                for iso in stats[n]["dates"]:
                    day_names[iso].append(n)
            entry["family"] = {
                "head": fam_head(comp),
                "others": [{"name": n, "slug": slugify(n), "count": c}
                           for n, c in sorted(fam_members[comp].items(),
                                              key=lambda kv: (-kv[1], kv[0]))
                           if n != name],
                # every day any family variant was called; chips show who
                "dates": [{"date": iso, "names": sorted(ns)}
                          for iso, ns in sorted(day_names.items())],
            }
        by_name[name] = entry

    never = [
        {"name": n, "master_rank": r}
        for n, r in sorted(master.items(), key=lambda kv: kv[1])
        if n not in stats
    ]
    # master names never posted themselves, but a family member was called
    never_flipped = sorted(
        ({"name": v["name"], "family": fam_head(fam[v["name"]]),
          "slug": slugify(fam_head(fam[v["name"]]))}
         for v in never if v["name"] in fam and fam_members.get(fam[v["name"]])),
        key=lambda v: (v["family"], v["name"]))
    families = []
    for comp, members in fam_members.items():
        if len(members) < 2:
            continue
        families.append({
            "head": fam_head(comp), "slug": slugify(fam_head(comp)),
            "total": sum(members.values()), "variants": len(members),
            "members": [{"name": n, "slug": slugify(n), "count": c}
                        for n, c in sorted(members.items(),
                                           key=lambda kv: (-kv[1], kv[0]))],
        })
    families.sort(key=lambda f: (-f["total"], f["head"]))
    dormant = sorted(by_name.values(), key=lambda v: (-v["days_since"], v["name"]))
    duos = collections.Counter(
        tuple(sorted(b)) for d in days for b in d["blocks"] if len(b) == 2)
    year = latest["date"][:4]
    # calendar UI: one page per tracked month, plus tabs data
    months = build_month_index(days)
    month_keys = {m["key"] for m in months}
    year_links = year_links_of(months)
    # prev/next day permalinks
    day_nav = {}
    for i, d in enumerate(days):
        day_nav[d["date"]] = (days[i - 1]["date"] if i > 0 else None,
                              days[i + 1]["date"] if i + 1 < len(days) else None)
    this_year_counts = collections.Counter(
        n for d in days if d["date"].startswith(year) for n in d["names"])

    # ── predictions ──────────────────────────────────────────────────────────
    # Compute cycling patterns for names called 2+ times
    LATEST_ISO = latest_names_day["date"] if latest_names_day else latest["date"]
    LATEST_DT = date.fromisoformat(LATEST_ISO)

    def avg_interval(isos):
        """Average days between consecutive calls."""
        if len(isos) < 2:
            return None
        dates = sorted(date.fromisoformat(d) for d in isos)
        diffs = [(dates[i+1] - dates[i]).days for i in range(len(dates)-1)]
        return round(sum(diffs) / len(diffs))

    # Overdue: 365+ days, sorted by days since
    overdue = sorted(
        (v for v in by_name.values() if v["days_since"] >= 365 and v["count"] >= 2),
        key=lambda v: (-v["days_since"], v["name"]))
    overdue_ctx = []
    for v in overdue[:25]:
        ai = avg_interval(v["dates"])
        overdue_ctx.append({
            "name": v["name"], "slug": v["slug"],
            "last": v["last"], "days_since": v["days_since"],
            "avg_interval": ai,
        })

    # On the clock: names with 2+ calls, within 30 days past their expected return
    on_clock = []
    for v in by_name.values():
        if v["count"] < 2:
            continue
        ai = avg_interval(v["dates"])
        if ai is None or ai > 400:  # skip very irregular names
            continue
        last_dt = date.fromisoformat(v["last"])
        expected = last_dt.fromordinal(last_dt.toordinal() + ai)
        days_until = (expected - LATEST_DT).days
        if -60 <= days_until <= 30:  # overdue by up to 60 days or coming in 30
            on_clock.append({
                "name": v["name"], "slug": v["slug"],
                "last": v["last"], "days_since": v["days_since"],
                "avg_interval": ai, "days_until": days_until,
            })
    on_clock.sort(key=lambda v: v["days_until"])  # most due first
    on_clock = on_clock[:25]

    # This time last year: names called within ±7 days of this date last year
    def this_time_window(target_date, years_back):
        """Return days from years_back whose date is within 7 days of target."""
        center = target_date.replace(year=target_date.year - years_back)
        window_start = center.fromordinal(center.toordinal() - 7)
        window_end = center.fromordinal(center.toordinal() + 7)
        results = []
        for d in days:
            dd = date.fromisoformat(d["date"])
            if window_start <= dd <= window_end and d["names"]:
                results.append({"date": d["date"], "names": d["names"]})
        return results

    this_week_last_year = this_time_window(LATEST_DT, 1)
    two_years = this_time_window(LATEST_DT, 2)

    ctx = {
        "r": "",                                   # root-relative prefix (set per page)
        "latest": latest,
        "latest_closed": latest["closed"],
        "latest_names": latest_names_day,
        "closed_days": closed_days,
        "recent": list(reversed(days[-RECENT_ON_INDEX:])),
        "days": days,
        "by_name": by_name,
        "names_sorted": sorted(by_name.values(), key=lambda v: v["name"]),
        "months": months,
        "month_keys": month_keys,
        "year_links": year_links,
        "day_nav": day_nav,
        "most_common": sorted(by_name.values(), key=lambda v: (-v["count"], v["name"])),
        "this_year": [{"name": n, "slug": slugify(n), "count": c}
                      for n, c in this_year_counts.most_common(15)],
        "dormant": dormant[:DORMANT_TOP],
        "never": never[:NEVER_CALLED_TOP],
        "never_total": len(never),
        "never_flipped": never_flipped,
        "never_flipped_total": len(never_flipped),
        "families": families[:15],
        "families_total": len(families),
        "master_total": len(master),
        "duos": [{"names": list(k), "count": c} for k, c in duos.most_common(5)],
        "overdue": overdue_ctx,
        "on_clock": on_clock,
        "this_week_last_year": this_week_last_year,
        "two_years": two_years,
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
    written.append(render("about.html", os.path.join("about", "index.html")))
    # history: calendar for the latest month at /history/, one page per month
    written.append(render("history.html", os.path.join("history", "index.html"), hm=months[-1]))
    for hm in months:
        written.append(render("history.html",
                              os.path.join("history", hm["key"], "index.html"), hm=hm))
    written.append(render("names_dir.html", os.path.join("names", "index.html")))
    written.append(render("stats.html", os.path.join("stats", "index.html")))
    written.append(render("predictions.html", os.path.join("predictions", "index.html")))
    for d in days:
        written.append(render("day.html", os.path.join("day", d["date"], "index.html"), day=d))
    for v in by_name.values():
        written.append(render("name.html", os.path.join("name", v["slug"], "index.html"), name=v))

    # RSS (absolute URLs; pubDate anchored to the scrape time, 12:45 US/Eastern)
    # RSS covers name days only; closures are not feed items
    rss_days = [d for d in reversed(days[-RSS_MAX_ITEMS:]) if not d["closed"]]
    c = dict(ctx, r="", rss_days=rss_days, rss_url=url("rss.xml"))
    dest = os.path.join(out, "rss.xml")
    with open(dest, "w") as f:
        f.write(env.get_template("rss.xml").render(**c))
    written.append(dest)

    # Prune artifacts of previous builds that this one didn't render, then
    # record this build's manifest for the next run.
    rel_written = sorted(os.path.relpath(p, out) for p in written)
    pruned = prune_stale(out, os.path.join(out, MANIFEST_NAME), rel_written)
    with open(os.path.join(out, MANIFEST_NAME), "w") as f:
        f.write("\n".join(rel_written) + "\n")

    print(f"rendered {len(written)} files, pruned {pruned} stale "
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
    build()
    return 0


if __name__ == "__main__":
    sys.exit(main())
