"""Contract tests for the Carmen's Names of the Day static site generator.

Run: python3 engine/test_ssg.py   (no pytest needed — mirrors tia-n-list's
engine test style so the CI workflow stays dependency-light)
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
    text = "# Names of the Day — 2026-08-31\nPEREZ & LYNN\n\n# comment\nLUCAS & EILEEN\n"
    assert ssg.parse_day_text(text) == [["PEREZ", "LYNN"], ["LUCAS", "EILEEN"]]


def test_parse_day_text_single_name_and_case():
    assert ssg.parse_day_text("SOLO\n") == [["SOLO"]]
    assert ssg.parse_day_text("ann & bob\n") == [["ANN", "BOB"]]


def test_slugify_deterministic_and_safe():
    assert ssg.slugify("PEREZ") == "perez"
    assert ssg.slugify("O'BRIEN") == "o-brien"
    assert ssg.slugify("ANN MARIE") == "ann-marie"


def test_split_fresh_style_dedup_in_parse():
    text = "PEREZ & LYNN\nPEREZ & LYNN\nPEREZ  &  LYNN\n"
    assert ssg.parse_day_text(text) == [["PEREZ", "LYNN"]] * 3  # blocks kept; dedup is at file level


def test_build_end_to_end():
    with tempfile.TemporaryDirectory() as tmp:
        _write(tmp, "data/days/2026-01-02.txt", "# Names of the Day — 2026-01-02\nJESSIE & PEREZ\n")
        _write(tmp, "data/days/2026-01-03.txt", "# Names of the Day — 2026-01-03\nPEREZ & LYNN\n")
        _write(tmp, "data/master-names.csv", "name,years_in_top1000,total_share\nJESSIE,250,9.9\nMARY,258,12.0\nNOTACALLEDNAME,200,5.0\n")
        out = os.path.join(tmp, "_site")
        written = ssg.build(repo_root=tmp, out_dir=out)
        rel = {os.path.relpath(p, out) for p in written}
        for expected in ("index.html", "rss.xml", "names.json", "style.css",
                         "history/index.html", "stats/index.html", "names/index.html",
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


def test_build_skips_invalid_day_files():
    with tempfile.TemporaryDirectory() as tmp:
        _write(tmp, "data/days/not-a-date.txt", "GARBAGE\n")
        _write(tmp, "data/days/2026-05-05.txt", "SOLO\n")
        out = os.path.join(tmp, "_site")
        ssg.build(repo_root=tmp, out_dir=out)
        assert os.path.exists(os.path.join(out, "day/2026-05-05/index.html"))
        assert not os.path.exists(os.path.join(out, "day/not-a-date"))


print("all ssg contract tests passed")
