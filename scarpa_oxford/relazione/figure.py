"""Figure della relazione (PNG in relazione/figure/), ricavate dai file prodotti."""

import json
import os
import sys

import ezdxf
import matplotlib
import numpy as np
import trimesh

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.collections import PolyCollection  # noqa: E402

QUI = os.path.dirname(os.path.abspath(__file__))
RADICE = os.path.join(QUI, "..")
sys.path.insert(0, RADICE)
sys.path.insert(0, os.path.join(RADICE, "..", "forma_3d"))
import genera_forma as gf  # noqa: E402

OUT = os.path.join(RADICE, "output")
FIG = os.path.join(QUI, "figure")
DXF = os.path.join(OUT, "piani_2d", "dxf")

STILE = {"TAGLIO": ("#111111", 1.1, "-"), "MONTAGGIO": ("#1f5fae", 0.8, (0, (1, 2))),
         "CUCITURA": ("#b03a2e", 0.7, (0, (4, 2))), "SCARNITURA": ("#7d7d7d", 0.7, (0, (6, 2, 1, 2))),
         "RIFERIMENTO": ("#1e8449", 0.9, "-"), "ASSE": ("#7d3c98", 0.7, (0, (8, 2, 2, 2))),
         "TACCHE": ("#111111", 1.1, "-")}
NOMI = {"puntale": "Puntale", "mascherina": "Mascherina", "quartiere_esterno": "Quartiere esterno",
        "quartiere_interno": "Quartiere interno", "bacchetta": "Bacchetta", "linguetta": "Linguetta",
        "fodera_avampiede": "Fodera avampiede", "fodera_quartiere_esterno": "Fodera quart. esterno",
        "fodera_quartiere_interno": "Fodera quart. interno", "fodera_linguetta": "Fodera linguetta",
        "contrafforte": "Contrafforte", "rinforzo_puntale": "Rinforzo puntale", "sottopiede": "Sottopiede",
        "suola": "Suola", "tacco_alzo": "Alzo tacco", "sopratacco": "Sopratacco", "guardolo": "Guardolo"}
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 9})


def leggi_dxf(nome):
    doc = ezdxf.readfile(os.path.join(DXF, f"{nome}.dxf"))
    linee, fori = {}, []
    for e in doc.modelspace():
        if e.dxftype() == "LWPOLYLINE" and e.dxf.layer in STILE:
            linee.setdefault(e.dxf.layer, []).append(np.array([p[:2] for p in e.get_points()]))
        elif e.dxftype() == "CIRCLE":
            fori.append((np.array([e.dxf.center.x, e.dxf.center.y]), e.dxf.radius))
    return linee, fori


def disegna(ax, nome, d=(0, 0), lw=1.0, livelli=None):
    linee, fori = leggi_dxf(nome)
    for layer, ll in linee.items():
        if livelli and layer not in livelli:
            continue
        c, w, ls = STILE[layer]
        for p in ll:
            ax.plot(p[:, 0] + d[0], p[:, 1] + d[1], color=c, lw=w * lw, ls=ls, solid_capstyle="butt")
    for c, r in fori:
        ax.add_patch(plt.Circle(c + d, r, fill=False, lw=0.7 * lw, color="#111"))
    return linee, fori


def salva(fig, nome):
    fig.savefig(os.path.join(FIG, nome), dpi=200, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def sagoma_laterale():
    xs = np.linspace(0.05, gf.LUNGHEZZA_BASE - 0.05, 600)
    p = [gf.profili(np.array(x)) for x in xs]
    zb, zt = np.array([q["zb"] for q in p]), np.array([q["zt"] for q in p])
    return np.vstack([np.column_stack([xs, zb]), np.column_stack([xs, zt])[::-1]])


def fig_camicia_piano():
    fig, (a, b) = plt.subplots(1, 2, figsize=(11, 4.2), gridspec_kw={"width_ratios": [1.25, 1]})
    a.fill(*sagoma_laterale().T, color="#e4ded6", ec="#b8afa3", lw=0.8)
    for nome, col in (("mascherina", "#e9b48a"), ("puntale", "#e3a49b"), ("quartiere_esterno", "#2e86c1")):
        m = trimesh.load(os.path.join(OUT, "camicie", f"{nome}.obj"), process=False)
        f = m.faces[m.face_normals[:, 1] < 0.2]   # facce visibili dal lato esterno
        a.add_collection(PolyCollection(m.vertices[f][:, :, [0, 2]], facecolors=col,
                                        edgecolors="none", alpha=0.95 if "quart" in nome else 0.6))
    a.set_aspect("equal"); a.set_xlim(-10, 290); a.set_ylim(-5, 130); a.axis("off")
    a.set_title("Sulla forma (lato esterno)", fontsize=10, loc="left")
    a.text(60, 55, "quartiere\nesterno", color="white", ha="center", fontsize=9, weight="bold")
    disegna(b, "quartiere_esterno")
    b.set_aspect("equal"); b.axis("off")
    b.set_title("In piano: cartamodello del quartiere esterno", fontsize=10, loc="left")
    fig.text(0.555, 0.5, "→", fontsize=28, ha="center", va="center", color="#5a3420")
    salva(fig, "camicia_piano.png")


def fig_quartiere_annotato():
    fig, ax = plt.subplots(figsize=(10, 6.4))
    linee, fori = disegna(ax, "quartiere_esterno", lw=1.2)
    ax.set_aspect("equal"); ax.axis("off")
    T = np.vstack(linee["TAGLIO"])
    x0, y0 = T.min(0); x1, y1 = T.max(0)

    def nota(p, testo, dove):
        ax.annotate(testo, xy=p, xytext=dove, fontsize=8.5, ha="center", va="center",
                    arrowprops=dict(arrowstyle="-", color="#5a3420", lw=0.7, shrinkA=2, shrinkB=1),
                    bbox=dict(boxstyle="round,pad=0.3", fc="white", ec="#c9bfb3", lw=0.6))

    mont = max(linee["MONTAGGIO"], key=lambda p: len(p))
    pm = mont[len(mont) // 2]
    nota(pm, "filo forma", (pm[0] + 10, y0 - 22))
    nota(pm - [25, 8], "margine di montaggio\n16 mm", (pm[0] - 60, y0 - 22))
    rif = sorted(linee["RIFERIMENTO"], key=lambda p: -len(p))
    pr = rif[0][len(rif[0]) // 2]
    nota(pr, "linea della mascherina\n(dove appoggia il suo bordo)", (x1 + 38, pr[1] + 30))
    sc = linee["SCARNITURA"][0]
    ps = sc[len(sc) // 3]
    nota(ps + [3, 0], "riporto sotto la mascherina\n12 mm, scarnito 8 mm", (x1 + 38, ps[1] - 25))
    pb = rif[1][len(rif[1]) // 2]
    nota(pb, "linea della bacchetta", (x0 - 30, pb[1] + 40))
    nota(T[np.argmin(T[:, 0] + 0.2 * np.abs(T[:, 1] - (y0 + y1) / 2))], "cucitura posteriore\n(accostata)",
         (x0 - 30, (y0 + y1) / 2 - 15))
    cuc = sorted(linee["CUCITURA"], key=lambda p: -len(p))
    pc = cuc[0][len(cuc[0]) // 3]
    nota(pc, "bocca: bordo a vista,\ncucitura a 2 mm", (pc[0] - 10, y1 + 18))
    cf = np.array([c for c, _ in fori])
    nota(cf[len(cf) // 2], "5 fori occhielli Ø 3,6 mm\na 9 mm dal bordo", (cf[:, 0].mean() + 40, y1 + 22))
    if "TACCHE" in linee:
        t = linee["TACCHE"][0][0]
        nota(t, "tacca", (t[0] - 22, t[1] - 15))
    ax.set_xlim(x0 - 60, x1 + 75); ax.set_ylim(y0 - 32, y1 + 30)
    salva(fig, "quartiere_annotato.png")


def fig_angolo():
    fig, ax = plt.subplots(figsize=(7.4, 4.8))
    linee, _ = disegna(ax, "mascherina", lw=1.6)
    ax.set_aspect("equal"); ax.set_xlim(-46, 50); ax.set_ylim(150, 211); ax.axis("off")

    def nota(p, t, q):
        ax.annotate(t, xy=p, xytext=q, fontsize=8.5, ha="left", va="center",
                    arrowprops=dict(arrowstyle="-", color="#5a3420", lw=0.7),
                    bbox=dict(boxstyle="round,pad=0.3", fc="white", ec="#c9bfb3", lw=0.6))
    nota((3.0, 196), "il margine si chiude sul\nprolungamento del bordo", (-44, 186))
    nota((25, 187), "filo forma", (30, 194))
    nota((30, 200), "margine di montaggio 16 mm", (14, 207.5))
    nota((15, 165), "bordo a vista della\nmascherina", (24, 158))
    nota((12, 178), "doppia cucitura\n1,6 e 3,6 mm", (26, 176))
    salva(fig, "angolo.png")


def fig_deformazione():
    import piani_2d as P
    with open(os.path.join(OUT, "pezzi.json"), encoding="utf-8") as f:
        dati = json.load(f)
    fig, axs = plt.subplots(1, 2, figsize=(11, 4.6), gridspec_kw={"width_ratios": [1.6, 1]})
    for ax, nome in zip(axs, ("quartiere_esterno", "puntale")):
        info = next(p for p in dati["pezzi"] if p["nome"] == nome)
        cache = {}
        P.cartamodello_tomaia(info, dati, cache)
        m, uv = cache[nome]
        e1, e2 = uv[m.faces[:, 1]] - uv[m.faces[:, 0]], uv[m.faces[:, 2]] - uv[m.faces[:, 0]]
        a2 = 0.5 * np.abs(e1[:, 0] * e2[:, 1] - e1[:, 1] * e2[:, 0])
        r = 100 * (a2 / np.maximum(m.area_faces, 1e-9) - 1)
        ok = m.area_faces > 0.05
        tp = ax.tripcolor(uv[:, 0], uv[:, 1], m.faces[ok], facecolors=np.clip(r[ok], -8, 8),
                          cmap="RdBu_r", vmin=-8, vmax=8, edgecolors="none")
        ax.set_aspect("equal"); ax.axis("off")
        ax.set_title(NOMI[nome], fontsize=10, loc="left")
    cb = fig.colorbar(tp, ax=axs, orientation="horizontal", fraction=0.05, pad=0.04, shrink=0.6)
    cb.set_label("variazione d'area dal 3D al piano (%)\nrosso: in piano è più grande, va ripresa in montaggio · "
                 "blu: in piano è più piccola, va tirata", fontsize=8.5)
    salva(fig, "deformazione.png")


def fig_cartamodelli():
    with open(os.path.join(OUT, "piani_2d", "riepilogo.json"), encoding="utf-8") as f:
        r = json.load(f)
    pezzi = [p for p in r["pezzi"] if p["nome"] != "guardolo"]
    pezzi.sort(key=lambda p: -p["ingombro_mm"][1])
    fig, ax = plt.subplots(figsize=(11, 8.2))
    x = y = riga = 0.0
    for p in pezzi:
        w, h = p["ingombro_mm"]
        if x + w > 900 and x > 0:
            x, y, riga = 0.0, y - riga - 48, 0.0
        disegna(ax, p["nome"], (x, y - h), lw=0.6, livelli={"TAGLIO", "MONTAGGIO", "CUCITURA", "RIFERIMENTO"})
        ax.text(x + w / 2, y - h - 13, f'{NOMI[p["nome"]]}', ha="center", fontsize=7.5, weight="bold")
        ax.text(x + w / 2, y - h - 23, f'{w:.0f} × {h:.0f} mm · {p["quantita_paio"]}/paio',
                ha="center", fontsize=6.5, color="#555")
        x += max(w, 95) + 40
        riga = max(riga, h)
    g = next(p for p in r["pezzi"] if p["nome"] == "guardolo")
    yg = y - riga - 45
    ax.add_patch(plt.Rectangle((0, yg), 900, 12, fill=False, lw=0.6))
    ax.text(450, yg - 10, f'Guardolo 360°: striscia 12 × {g["ingombro_mm"][0]:.0f} mm (qui accorciata)',
            ha="center", fontsize=7.5, weight="bold")
    ax.set_aspect("equal"); ax.axis("off"); ax.autoscale_view()
    salva(fig, "cartamodelli.png")


def fig_suola():
    xs = np.linspace(-1.4, 286.2, 400)
    z = gf.pchip(gf.FONDO, xs) - 10
    fig, ax = plt.subplots(figsize=(9, 2.4))
    ax.plot(xs, z, color="#5a3420", lw=2.2)
    ax.plot([xs[0], xs[-1]], [-14, -14], color="#888", lw=1, ls=(0, (4, 2)))
    ax.annotate("", (xs[0], -18), (xs[-1], -18), arrowprops=dict(arrowstyle="<->", color="#555", lw=0.8))
    ax.text(xs.mean(), -23, "proiezione in pianta: 287,6 mm", ha="center", fontsize=8.5, color="#333")
    ax.text(150, 20, "suola sviluppata lungo la curva del fondo: 291,2 mm", ha="center", fontsize=8.5,
            color="#5a3420")
    ax.text(2, 21, "tallone", fontsize=8, color="#555"); ax.text(268, 9, "punta", fontsize=8, color="#555")
    ax.set_aspect("equal"); ax.axis("off"); ax.set_ylim(-28, 28)
    salva(fig, "suola.png")


if __name__ == "__main__":
    os.makedirs(FIG, exist_ok=True)
    fig_camicia_piano()
    fig_quartiere_annotato()
    fig_angolo()
    fig_deformazione()
    fig_cartamodelli()
    fig_suola()
    print("figure ok")
