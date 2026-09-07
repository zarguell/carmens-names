#!/usr/bin/env python3
"""Generate engine/static/og-image.png — the branded preview image used by
the og:image / twitter:image tags (link unfurls need a real PNG/JPEG;
iMessage in particular shows a bare link with no image).

Pure stdlib (struct + zlib): draws the three gelati scoops (red, blue,
green) on the site cream with confetti dots. No text — names travel in
og:title/og:description, which ARE per-page. Run once and commit the PNG;
the SSG copies it to the site root as og-image.png.
"""
import os
import random
import struct
import zlib

W, H = 1200, 630
CREAM = (255, 246, 236)
NAVY = (20, 33, 61)
SCOOPS = [(212, 66, 42), (45, 148, 207), (140, 198, 63)]      # red blue green
CONFETTI = [(255, 104, 99), (247, 148, 29), (45, 148, 207),   # coral orange blue
            (140, 198, 63), (20, 33, 61)]                      # green navy


def circle(px, py, cx, cy, r):
    return (px - cx) ** 2 + (py - cy) ** 2 <= r * r


def main():
    rng = random.Random(20260907)          # deterministic confetti
    dots = [(rng.randrange(W), rng.randrange(H), rng.randrange(6, 16),
             rng.choice(CONFETTI)) for _ in range(90)]
    scoops = [(W // 2 - 260, H // 2 - 20, 130),
              (W // 2, H // 2 - 60, 150),
              (W // 2 + 260, H // 2 - 20, 130)]
    rows = bytearray()
    for y in range(H):
        rows.append(0)                     # filter byte: none
        for x in range(W):
            r, g, b = CREAM
            for dx, dy, dr, col in dots:
                if circle(x, y, dx, dy, dr):
                    r, g, b = col
                    break
            else:
                for i, (cx, cy, cr) in enumerate(scoops):
                    if circle(x, y, cx, cy, cr):
                        # overlap shadow: later scoops shade earlier ones
                        f = 1.0
                        for j in range(i + 1, len(scoops)):
                            ocx, ocy, ocr = scoops[j]
                            if circle(x, y, ocx, ocy, ocr + 6):
                                f = 0.82
                        sr, sg, sb = SCOOPS[i]
                        r, g, b = int(sr * f), int(sg * f), int(sb * f)
            rows += bytes((r, g, b))
    # navy footer strip
    for y in range(H - 90, H):
        off = y * (W * 3 + 1)
        for x in range(W):
            rows[off + 1 + x * 3:off + 1 + x * 3 + 3] = bytes(NAVY)

    def chunk(typ, data):
        c = struct.pack(">I", len(data)) + typ + data
        return c + struct.pack(">I", zlib.crc32(typ + data) & 0xFFFFFFFF)

    png = (b"\x89PNG\r\n\x1a\n"
           + chunk(b"IHDR", struct.pack(">IIBBBBB", W, H, 8, 2, 0, 0, 0))
           + chunk(b"IDAT", zlib.compress(bytes(rows), 6))
           + chunk(b"IEND", b""))
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "static", "og-image.png")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "wb") as f:
        f.write(png)
    print(f"wrote {out} ({len(png) / 1024:.0f} KB, {W}x{H})")


if __name__ == "__main__":
    main()
