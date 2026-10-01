#!/usr/bin/env python3
"""Anteprima PNG (6 viste) di una forma STL, con z-buffer in numpy.

Uso: python3 anteprima.py output/forma_uomo_42_tacco25_dx.stl anteprima.png
"""

import sys

import numpy as np
import trimesh
from PIL import Image, ImageDraw

VISTE = [  # titolo, elevazione, azimut (gradi)
    ("Esterno", 0, -90), ("Interno", 0, 90), ("Pianta", 90, -90),
    ("Fondo", -90, -90), ("Prospettiva", 25, -130), ("Punta", 5, 0),
]
W, H, PX_MM = 520, 300, 1.6
COLORE = np.array([196, 160, 116], float)  # faggio


def ruota(v, el, az):
    el, az = np.radians(el), np.radians(az)
    # camera: guarda verso -d, con d = (cos el cos az, cos el sin az, sin el)
    d = np.array([np.cos(el) * np.cos(az), np.cos(el) * np.sin(az), np.sin(el)])
    up = np.array([0, 0, 1.0]) if abs(d[2]) < 0.99 else np.array([0, np.sign(d[2]), 0])
    r = np.cross(up, d); r /= np.linalg.norm(r)
    u = np.cross(d, r)
    return v @ np.column_stack([r, u, d])


def vista(mesh, el, az):
    v = ruota(mesh.vertices - mesh.bounds.mean(0), el, az)
    n = ruota(mesh.face_normals, el, az)
    luce = np.array([-0.35, 0.55, 0.75]); luce /= np.linalg.norm(luce)
    shade = 0.28 + 0.72 * np.clip(n @ luce, 0, 1)
    p = np.column_stack([W / 2 + v[:, 0] * PX_MM, H / 2 - v[:, 1] * PX_MM, v[:, 2]])
    zbuf = np.full((H, W), -np.inf)
    img = np.full((H, W, 3), 255.0)
    for f, s, nz in zip(mesh.faces, shade, n[:, 2]):
        if nz <= 0:  # faccia rivolta indietro
            continue
        a, b, c = p[f]
        x0, x1 = int(max(min(a[0], b[0], c[0]), 0)), int(min(max(a[0], b[0], c[0]) + 1, W))
        y0, y1 = int(max(min(a[1], b[1], c[1]), 0)), int(min(max(a[1], b[1], c[1]) + 1, H))
        if x0 >= x1 or y0 >= y1:
            continue
        den = (b[1] - c[1]) * (a[0] - c[0]) + (c[0] - b[0]) * (a[1] - c[1])
        if abs(den) < 1e-12:
            continue
        xx, yy = np.meshgrid(np.arange(x0, x1) + 0.5, np.arange(y0, y1) + 0.5)
        l1 = ((b[1] - c[1]) * (xx - c[0]) + (c[0] - b[0]) * (yy - c[1])) / den
        l2 = ((c[1] - a[1]) * (xx - c[0]) + (a[0] - c[0]) * (yy - c[1])) / den
        l3 = 1 - l1 - l2
        m = (l1 >= 0) & (l2 >= 0) & (l3 >= 0)
        z = l1 * a[2] + l2 * b[2] + l3 * c[2]
        zb = zbuf[y0:y1, x0:x1]
        m &= z > zb
        zb[m] = z[m]
        img[y0:y1, x0:x1][m] = COLORE * s
    return Image.fromarray(img.astype(np.uint8))


def main():
    mesh = trimesh.load(sys.argv[1])
    out = sys.argv[2] if len(sys.argv) > 2 else "anteprima.png"
    tav = Image.new("RGB", (W * 3, (H + 28) * 2), "white")
    for i, (titolo, el, az) in enumerate(VISTE):
        x, y = (i % 3) * W, (i // 3) * (H + 28)
        tav.paste(vista(mesh, el, az), (x, y + 28))
        ImageDraw.Draw(tav).text((x + 12, y + 8), titolo, fill=(40, 40, 40))
    tav.save(out)


if __name__ == "__main__":
    main()
