#!/usr/bin/env python3
"""Mock link-unfurl check (stands in for iMessage / Slack / X previews).

iMessage renders a rich preview only if the *shared URL itself* serves
crawler-readable OG tags: it does a plain GET (no JS) and needs at least
og:title, og:description, a self-consistent absolute og:url, and an
absolute og:image that fetches as a real image (no image -> bare link,
which is what we shipped first).

Usage:
  python3 engine/check_og.py https://zarguell.github.io/carmens-names/ \\
      https://zarguell.github.io/carmens-names/day/2026-09-06/
  # or against a local build (tags stay production-absolute; only the
  # fetch target is remapped onto the test server):
  #   python3 -m http.server 8124 &
  #   python3 engine/check_og.py --map https://zarguell.github.io/carmens-names=http://localhost:8124 \
  #       https://zarguell.github.io/carmens-names/ \
  #       https://zarguell.github.io/carmens-names/day/2026-09-06/

Exits 0 when every page passes, 1 otherwise.
"""
import struct
import sys
import urllib.request
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse


class MetaParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tags = {}

    def handle_starttag(self, tag, attrs):
        if tag != "meta":
            return
        d = dict(attrs)
        key = d.get("property") or d.get("name")
        if key and d.get("content"):
            self.tags.setdefault(key, d["content"])


def fetch(url):
    req = urllib.request.Request(
        url, headers={"User-Agent": "carmens-og-check/1.0 (link-unfurl mock)"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.status, r.headers.get("Content-Type", ""), r.read()


def image_size(data, ctype):
    """(width, height) for PNG/JPEG/GIF without Pillow; None if unknown."""
    try:
        if data[:8] == b"\x89PNG\r\n\x1a\n":
            w, h = struct.unpack(">II", data[16:24])
            return w, h
        if data[:6] in (b"GIF87a", b"GIF89a"):
            w, h = struct.unpack("<HH", data[6:10])
            return w, h
        if data[:2] == b"\xff\xd8":
            i = 2
            while i < len(data):
                if data[i] != 0xFF:
                    break
                marker = data[i + 1]
                if marker in (0xC0, 0xC1, 0xC2):      # SOF: height, width
                    h, w = struct.unpack(">HH", data[i + 5:i + 9])
                    return w, h
                ln = struct.unpack(">H", data[i + 2:i + 4])[0]
                i += 2 + ln
    except Exception:
        pass
    return None


def norm(u):
    return u.rstrip("/")


def check_page(url, host_map=()):
    """Validate one page. `url` is the logical (production) URL used for
    og:url self-consistency; `host_map` rewrites only the FETCH target,
    e.g. production -> localhost, so absolute tags resolve locally."""
    errors, notes = [], []

    def get(logical):
        target = logical
        for src, dst in host_map:
            if target.startswith(src):
                target = dst + target[len(src):]
                break
        return fetch(target)

    try:
        status, ctype, body = get(url)
    except Exception as e:  # noqa: BLE001
        return False, [f"GET failed: {e}"], []
    if status != 200:
        errors.append(f"GET status {status} (want 200)")
    if "text/html" not in ctype:
        errors.append(f"content-type {ctype!r} (want text/html)")
    p = MetaParser()
    try:
        p.feed(body.decode("utf-8", errors="replace"))
    except Exception as e:  # noqa: BLE001
        errors.append(f"HTML parse failed: {e}")
    t = p.tags
    for key in ("og:title", "og:description", "og:url", "og:image"):
        if not t.get(key):
            errors.append(f"missing {key}")
    if t.get("og:title"):
        notes.append(f"title={t['og:title'][:80]!r}")
    og_url = t.get("og:url", "")
    if og_url and urlparse(og_url).scheme != "https":
        errors.append(f"og:url not absolute https: {og_url!r}")
    if og_url and norm(og_url) != norm(url):
        errors.append(f"og:url {og_url!r} != page {url!r} (crawler shows stale/dupe preview)")
    img = t.get("og:image", "")
    if img:
        full = urljoin(url, img)
        if urlparse(full).scheme != "https":
            errors.append(f"og:image not absolute https: {img!r}")
        else:
            try:
                st, ictype, idata = get(full)
                if st != 200:
                    errors.append(f"og:image GET status {st}")
                elif not ictype.startswith("image/"):
                    errors.append(f"og:image content-type {ictype!r} (want image/*)")
                else:
                    size = image_size(idata, ictype)
                    notes.append(f"image={len(idata) // 1024}KB {ictype}"
                                 + (f" {size[0]}x{size[1]}" if size else " (size unknown)"))
                    if size and (size[0] < 200 or size[1] < 200):
                        errors.append(f"og:image too small: {size[0]}x{size[1]} (min 200x200)")
            except Exception as e:  # noqa: BLE001
                errors.append(f"og:image fetch failed: {e}")
    return not errors, errors, notes


def main(argv):
    host_map = []
    urls = []
    args = argv[1:]
    while args:
        a = args.pop(0)
        if a == "--map" and args:
            src, _, dst = args.pop(0).partition("=")
            host_map.append((src, dst))
        else:
            urls.append(a)
    if not urls:
        print(__doc__)
        return 2
    failed = 0
    bad_pages = 0
    for url in urls:
        ok, errors, notes = check_page(url, host_map)
        print(f"{'PASS' if ok else 'FAIL'}  {url}")
        for n in notes:
            print(f"      {n}")
        for e in errors:
            print(f"      ! {e}")
            failed += 1
        if not ok:
            bad_pages += 1
    print(f"{len(urls) - bad_pages}/{len(urls)} pages passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
