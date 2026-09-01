"""Contract tests for the Carmen's Names of the Day static site generator.

Run: python3 engine/test_ssg.py   (runs standalone — every test_* function
executes; also collectable by pytest)
"""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ssg


def _write(root, rel, content):
    p = os.path.join(root, rel)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w") as f:
        f.write(content)


def test_parse_day_text_blocks():
    text = "# Names of the Day: 2026-08-31\nPEREZ & LYNN\n\n# comment\nLUCAS & EILEEN\n"
    assert ssg.parse_day_text(text) == {"closed": False,
                                        "blocks": [["PEREZ", "LYNN"], ["LUCAS", "EILEEN"]]}


def test_parse_day_text_single_name_and_case():
    assert ssg.parse_day_text("SOLO\n")["blocks"] == [["SOLO"]]
    assert ssg.parse_day_text("ann & bob\n")["blocks"] == [["ANN", "BOB"]]


def test_slugify_deterministic_and_safe():
    assert ssg.slugify("PEREZ") == "perez"
    assert ssg.slugify("O'BRIEN") == "o-brien"
    assert ssg.slugify("ANN MARIE") == "ann-marie"


def test_split_fresh_style_dedup_in_parse():
    text = "PEREZ & LYNN\nPEREZ & LYNN\nPEREZ  &  LYNN\n"
    assert ssg.parse_day_text(text)["blocks"] == [["PEREZ", "LYNN"]] * 3  # blocks kept; dedup is at file level


def test_build_end_to_end():
    with tempfile.TemporaryDirectory() as tmp:
        _write(tmp, "data/days/2026-01-02.txt", "# Names of the Day: 2026-01-02\nJESSIE & PEREZ\n")
        _write(tmp, "data/days/2026-01-03.txt", "# Names of the Day: 2026-01-03\nPEREZ & LYNN\n")
        _write(tmp, "data/master-names.csv", "name,years_in_top1000,total_share\nJESSIE,250,9.9\nMARY,258,12.0\nNOTACALLEDNAME,200,5.0\n")
        out = os.path.join(tmp, "_site")
        written = ssg.build(repo_root=tmp, out_dir=out)
        rel = {os.path.relpath(p, out) for p in written}
        for expected in ("index.html", "rss.xml", "names.json", "style.css",
                         "history/index.html", "history/2026-01/index.html",
                         "about/index.html", "stats/index.html", "names/index.html",
                         "day/2026-01-03/index.html", "name/perez/index.html",
                         "name/jessie/index.html", "name/lynn/index.html"):
            assert expected in rel, f"missing {expected}; got {sorted(rel)}"
        idx = open(os.path.join(out, "index.html")).read()
        assert "PEREZ" in idx and "LYNN" in idx and "2026-01-03" in idx
        rss = open(os.path.join(out, "rss.xml")).read()
        assert "Names of the Day: PEREZ &amp; LYNN" in rss and "Jan 3, 2026" in rss
        perez = open(os.path.join(out, "name/perez/index.html")).read()
        assert "2" in perez and "Jan 2, 2026" in perez  # count + first date
        stats = open(os.path.join(out, "stats/index.html")).read()
        assert "MARY" in stats and "NOTACALLEDNAME" in stats  # never-called from master list
        assert "6" in stats  # MARY rank line appears? (rank numbers) — stats page rendered
        nj = json.load(open(os.path.join(out, "names.json")))
        assert nj["latest_date"] == "2026-01-03" and nj["days"][-1]["names"] == ["PEREZ", "LYNN"]


def test_rebuild_prunes_stale_outputs():
    with tempfile.TemporaryDirectory() as tmp:
        _write(tmp, "data/days/2026-01-02.txt", "# Names of the Day: 2026-01-02\nJESSIE & PEREZ\n")
        _write(tmp, "data/master-names.csv", "name,years_in_top1000,total_share\nMARY,258,12.0\n")
        out = os.path.join(tmp, "_site")
        ssg.build(repo_root=tmp, out_dir=out)
        assert os.path.exists(os.path.join(out, "name/perez/index.html"))
        assert os.path.exists(os.path.join(out, "day/2026-01-02/index.html"))
        # the day disappears from the data: its page must not survive the rebuild
        os.unlink(os.path.join(tmp, "data/days/2026-01-02.txt"))
        _write(tmp, "data/days/2026-01-03.txt", "# Names of the Day: 2026-01-03\nLYNN & MARY\n")
        ssg.build(repo_root=tmp, out_dir=out)
        assert not os.path.exists(os.path.join(out, "name/perez/index.html"))
        assert not os.path.exists(os.path.join(out, "day/2026-01-02"))  # pruned, dir removed
        assert os.path.exists(os.path.join(out, "name/lynn/index.html"))
        assert os.path.exists(os.path.join(out, "rss.xml"))             # untouched outputs stay


def test_rebuild_without_manifest_is_harmless():
    with tempfile.TemporaryDirectory() as tmp:
        _write(tmp, "data/days/2026-01-02.txt", "SOLO\n")
        out = os.path.join(tmp, "_site")
        ssg.build(repo_root=tmp, out_dir=out)
        ssg.build(repo_root=tmp, out_dir=out)  # manifest now exists; still fine
        assert os.path.exists(os.path.join(out, "index.html"))


def test_prune_never_escapes_out():
    with tempfile.TemporaryDirectory() as tmp:
        out = os.path.join(tmp, "_site")
        os.makedirs(out)
        manifest = os.path.join(out, ssg.MANIFEST_NAME)
        with open(manifest, "w") as f:
            f.write("../../outside.html\n")
        outside = os.path.join(tmp, "outside.html")
        with open(outside, "w") as f:
            f.write("x")
        assert ssg.prune_stale(out, manifest, []) == 0
        assert os.path.exists(outside)  # path escape refused


def test_closed_day_renders_closed_and_skips_rss():
    with tempfile.TemporaryDirectory() as tmp:
        _write(tmp, "data/days/2026-01-01.txt", "# Names of the Day: 2026-01-01\nJESSIE & PEREZ\n")
        _write(tmp, "data/days/2026-01-02.txt", "# Names of the Day: 2026-01-02\nCLOSED\n")
        _write(tmp, "data/master-names.csv", "name,years_in_top1000,total_share\nMARY,258,12.0\n")
        out = os.path.join(tmp, "_site")
        ssg.build(repo_root=tmp, out_dir=out)
        # latest tracked day is the closure: hero says so, and no stale
        # big-chip names are promoted before the recent list (the freebie's
        # "last called" mention is intentional)
        idx = open(os.path.join(out, "index.html")).read()
        assert "The shop is closed" in idx and "big-chips" not in idx.split("Recently called")[0]
        day = open(os.path.join(out, "day/2026-01-02/index.html")).read()
        assert "The shop is closed" in day
        hist = open(os.path.join(out, "history/index.html")).read()
        assert "Closed" in hist
        rss = open(os.path.join(out, "rss.xml")).read()
        assert "2026-01-02" not in rss  # closures are not feed items
        assert "2026-01-01" in rss
        nj = json.load(open(os.path.join(out, "names.json")))
        closed = [d for d in nj["days"] if d["closed"]]
        assert len(closed) == 1 and closed[0]["date"] == "2026-01-02"


def test_build_skips_invalid_day_files():
    with tempfile.TemporaryDirectory() as tmp:
        _write(tmp, "data/days/not-a-date.txt", "GARBAGE\n")
        _write(tmp, "data/days/2026-05-05.txt", "SOLO\n")
        out = os.path.join(tmp, "_site")
        ssg.build(repo_root=tmp, out_dir=out)
        assert os.path.exists(os.path.join(out, "day/2026-05-05/index.html"))
        assert not os.path.exists(os.path.join(out, "day/not-a-date"))


def test_history_calendar_pages_and_nav():
    with tempfile.TemporaryDirectory() as tmp:
        _write(tmp, "data/days/2025-12-15.txt", "MARY\n")
        _write(tmp, "data/days/2026-01-01.txt", "# c\nCLOSED\n")
        _write(tmp, "data/days/2026-01-02.txt", "JESSIE & PEREZ\n")
        _write(tmp, "data/master-names.csv", "name,years_in_top1000,total_share\nMARY,258,12.0\n")
        out = os.path.join(tmp, "_site")
        ssg.build(repo_root=tmp, out_dir=out)
        # latest month lives at /history/, every tracked month gets a page
        hist = open(os.path.join(out, "history/index.html")).read()
        assert "January 2026" in hist and "cal-grid" in hist
        dec = open(os.path.join(out, "history/2025-12/index.html")).read()
        jan = open(os.path.join(out, "history/2026-01/index.html")).read()
        assert "December 2025" in dec and "MARY" in dec
        assert 'href="../../history/2025-12/"' in jan          # prev-month link
        assert 'href="../../history/2026-01/"' in dec          # next-month link
        assert "Closed" in jan                                 # closure cell
        assert "2025" in jan and "2026" in jan                 # year tabs
        # a day with no data renders as an empty cell, not a link
        assert 'class="cal-cell none"' in jan and "cal-cell pad" in jan


def test_about_page_renders():
    with tempfile.TemporaryDirectory() as tmp:
        _write(tmp, "data/days/2026-01-02.txt", "JESSIE & PEREZ\n")
        _write(tmp, "data/master-names.csv", "name,years_in_top1000,total_share\nMARY,258,12.0\n")
        out = os.path.join(tmp, "_site")
        ssg.build(repo_root=tmp, out_dir=out)
        about = open(os.path.join(out, "about/index.html")).read()
        assert "launched in 2026" in about and "backfill" in about.lower()
        assert "Jan 2, 2026" in about                          # first tracked date, with year


def test_name_and_index_dates_carry_year():
    with tempfile.TemporaryDirectory() as tmp:
        _write(tmp, "data/days/2026-01-02.txt", "JESSIE & PEREZ\n")
        _write(tmp, "data/days/2026-01-03.txt", "PEREZ & LYNN\n")
        _write(tmp, "data/master-names.csv", "name,years_in_top1000,total_share\nMARY,258,12.0\n")
        out = os.path.join(tmp, "_site")
        ssg.build(repo_root=tmp, out_dir=out)
        perez = open(os.path.join(out, "name/perez/index.html")).read()
        assert "Jan 2, 2026" in perez and "Jan 3, 2026" in perez   # first/last called
        idx = open(os.path.join(out, "index.html")).read()
        assert "first date tracked" in idx and "Jan 2, 2026" in idx
        assert "closed days" not in idx and "names served" not in idx  # only the 4 asked-for stats


def test_name_families():
    with tempfile.TemporaryDirectory() as tmp:
        _write(tmp, "data/days/2026-01-02.txt", "TED & MARGARET\n")
        _write(tmp, "data/days/2026-01-03.txt", "PEGGY\n")
        _write(tmp, "data/days/2026-01-04.txt", "LYNN\n")
        _write(tmp, "data/master-names.csv",
               "name,years_in_top1000,total_share\n"
               "EDWARD,100,9.0\nTHEODORE,150,8.0\nPEG,300,4.0\nDICK,400,3.0\n")
        _write(tmp, "data/name-families.csv",
               "family,variant\n"
               "EDWARD,ED\nTHEODORE,ED\n"      # shared variant merges both
               "EDWARD,TED\nTHEODORE,TED\n"
               "MARGARET,PEGGY\nMARGARET,PEG\n")
        # union-find: ED/TED merge EDWARD+THEODORE into one component
        master = {"EDWARD": 100, "THEODORE": 150, "PEG": 300, "DICK": 400}
        fam = ssg.load_families("/nonexistent.csv", master)
        assert fam == {}                                       # missing file is fine
        fam = ssg.load_families(os.path.join(tmp, "data", "name-families.csv"), master)
        assert fam["EDWARD"] == fam["THEODORE"] == fam["TED"]
        assert fam["MARGARET"] == fam["PEGGY"] == fam["PEG"]

        out = os.path.join(tmp, "_site")
        ssg.build(repo_root=tmp, out_dir=out)
        stats = open(os.path.join(out, "stats/index.html")).read()
        assert "Name families" in stats
        assert "×2 total · 2 variants" in stats                 # margaret family row
        # never-called flips: PEG covered by called PEGGY; DICK stays shut out
        assert "partial credit" in stats and "→ MARGARET" in stats and "→ DICK" not in stats
        # family card on a member page links its kin, with the family day history
        margaret = open(os.path.join(out, "name/margaret/index.html")).read()
        assert "The MARGARET family" in margaret and "name/peggy/" in margaret
        assert "family was selected" in margaret
        assert "Jan 3, 2026" in margaret and "name/peggy/" in margaret  # PEGGY's day
        # a day with two family members shows both on one row
        assert "2026-01-02" in margaret  # margaret's own day, from TED & MARGARET
        # TED's merge with EDWARD/THEODORE surfaces in the flips (TED is the
        # only *called* member, so the family itself gets no stats card)
        assert "EDWARD → TED" in stats and "THEODORE → TED" in stats
        ted = open(os.path.join(out, "name/ted/index.html")).read()
        assert "The TED family" not in ted
        # a name with no family renders no family card
        solo = open(os.path.join(out, "name/lynn/index.html")).read()
        assert "The LYNN family" not in solo


def main():
    tests = [v for k, v in sorted(globals().items())
             if k.startswith("test_") and callable(v)]
    for t in tests:
        t()
    print(f"all {len(tests)} ssg contract tests passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
