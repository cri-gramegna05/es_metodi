#!/usr/bin/env python3
"""Piani di taglio 2D dell'Oxford tg 42 (scala 1:1, mm).

Per ogni pezzo: sviluppo in piano della camicia, margini di taglio per tipo di
bordo, file di cucitura, linee di scarnitura, linee di sovrapposizione degli
altri pezzi, asse, tacche, fori occhielli, verso del tiro e cartiglio.

Uscite in output/piani_2d/:
  dxf/<pezzo>.dxf, svg/<pezzo>.svg   un file per pezzo, 1:1
  tutti_i_pezzi.dxf                  tutti i cartamodelli in un unico disegno
  piani_taglio_oxford_42.pdf         tavola riassuntiva + un foglio A3 1:1 per pezzo
  riepilogo.json                     aree, consumi, distorsione, controllo cuciture
"""

import json
import os
import re
import sys

import ezdxf
import matplotlib
import numpy as np
import trimesh
from ezdxf.enums import TextEntityAlignment
from shapely.geometry import LineString, Point, Polygon, box
from shapely.ops import linemerge, unary_union

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.backends.backend_pdf import PdfPages  # noqa: E402

QUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(QUI, "..", "forma_3d"))
import genera_forma as gf  # noqa: E402

from genera_oxford import SCARNITURA, X_TACCO  # noqa: E402
from spianamento import distorsione, jacobiani, mappa, spiana  # noqa: E402

OUT = os.path.join(QUI, "output")
DEST = os.path.join(OUT, "piani_2d")

# ---------------------------------------------------------------------------
# Regole di modelleria
# ---------------------------------------------------------------------------

MARGINE_MONTAGGIO = {"puntale": 16, "mascherina": 16, "quartiere_esterno": 16,
                     "quartiere_interno": 16, "bacchetta": 16, "fodera_avampiede": 14,
                     "fodera_quartiere_esterno": 14, "fodera_quartiere_interno": 14,
                     "contrafforte": 14, "rinforzo_puntale": 10}
RIFILATURA_FODERA = 3.0   # fodere quartiere: abbondanza su bocca e occhielleria
LATERALI = {"quartiere_esterno", "quartiere_interno", "fodera_quartiere_esterno",
            "fodera_quartiere_interno", "bacchetta", "contrafforte"}
CON_ASSE = {"puntale", "mascherina", "linguetta", "fodera_avampiede", "rinforzo_puntale",
            "sottopiede", "contrafforte", "bacchetta"}
# pezzo -> [(pezzo sovrapposto, tipo del suo bordo)]: linee di sovrapposizione
RIFERIMENTI = {
    "quartiere_esterno": [("mascherina", "mascherina"), ("bacchetta", "bacchetta")],
    "quartiere_interno": [("mascherina", "mascherina"), ("bacchetta", "bacchetta")],
    "mascherina": [("puntale", "puntale")],
    "linguetta": [("mascherina", "mascherina"), ("quartiere_esterno", "occhielleria"),
                  ("quartiere_interno", "occhielleria")],
    "fodera_avampiede": [("fodera_quartiere_esterno", "fodera_cucitura"),
                         ("fodera_quartiere_interno", "fodera_cucitura")],
}
SCARTO = {"vitello box": 0.20, "pelle fodera": 0.15}   # sfrido stimato per materiale
SCARTO_ALTRO = 0.10

STILI = {  # layer: (colore, spessore pt, tratteggio matplotlib, colore DXF, linetype DXF)
    "TAGLIO": ("#111111", 0.9, "-", 7, "CONTINUOUS"),
    "MONTAGGIO": ("#1f5fae", 0.5, (0, (1, 2)), 5, "DOT"),
    "CUCITURA": ("#b03a2e", 0.5, (0, (4, 2)), 1, "DASHED"),
    "SCARNITURA": ("#7d7d7d", 0.45, (0, (6, 2, 1, 2)), 8, "DASHDOT"),
    "RIFERIMENTO": ("#1e8449", 0.6, "-", 3, "CONTINUOUS"),
    "ASSE": ("#7d3c98", 0.5, (0, (8, 2, 2, 2)), 6, "CENTER"),
    "FORI": ("#111111", 0.6, "-", 7, "CONTINUOUS"),
    "TACCHE": ("#111111", 0.9, "-", 7, "CONTINUOUS"),
    "TESTO": ("#222222", 0.5, "-", 7, "CONTINUOUS"),
}


# ---------------------------------------------------------------------------
# Geometria 2D di supporto
# ---------------------------------------------------------------------------

def lunghezza(p):
    p = np.asarray(p)
    return float(np.linalg.norm(np.diff(p, axis=0), axis=1).sum()) if len(p) > 1 else 0.0


def normali_sinistra(p):
    """Normale a sinistra (verso l'interno per un contorno antiorario)."""
    t = np.gradient(p, axis=0)
    t /= np.maximum(np.linalg.norm(t, axis=1, keepdims=True), 1e-9)
    return np.column_stack([-t[:, 1], t[:, 0]])


def ricampiona(p, passo=0.8):
    L = np.concatenate([[0], np.cumsum(np.linalg.norm(np.diff(p, axis=0), axis=1))])
    if L[-1] < passo:
        return p
    s = np.linspace(0, L[-1], max(3, int(L[-1] / passo) + 1))
    return np.column_stack([np.interp(s, L, p[:, 0]), np.interp(s, L, p[:, 1])])


def parallela(p, d, accorcia=1.5):
    """Linea interna parallela al bordo p (contorno antiorario) a distanza d."""
    p = ricampiona(p)
    if lunghezza(p) < 2 * accorcia + 2:
        return None
    q = p + normali_sinistra(p) * d
    L = np.concatenate([[0], np.cumsum(np.linalg.norm(np.diff(q, axis=0), axis=1))])
    m = (L > accorcia) & (L < L[-1] - accorcia)
    return q[m] if m.sum() > 1 else None


def tangente_estremo(p, inizio, tratto=3.0):
    p = np.asarray(p)
    if inizio:
        L = np.cumsum(np.linalg.norm(np.diff(p, axis=0), axis=1))
        k = min(int(np.searchsorted(L, tratto)) + 1, len(p) - 1)
        t = p[k] - p[0]
    else:
        L = np.cumsum(np.linalg.norm(np.diff(p[::-1], axis=0), axis=1))
        k = min(int(np.searchsorted(L, tratto)) + 1, len(p) - 1)
        t = p[-1] - p[::-1][k]
    return t / max(np.linalg.norm(t), 1e-9)


def semipiano_fuori(A, t, r):
    """Zona da togliere vicino allo spigolo A: lato esterno (destra) della retta A+t."""
    n = np.array([t[1], -t[0]])
    big = 4 * r
    P = [A - t * big, A + t * big, A + t * big + n * big, A - t * big + n * big]
    return Polygon(P).intersection(Point(A).buffer(r))


def contorno_taglio(segmenti):
    """Poligono di taglio: base + margini per bordo, chiusi sulle prolunghe dei bordi adiacenti."""
    anello = np.vstack([s["p"][:-1] for s in segmenti])
    base = Polygon(anello).buffer(0)
    parti = [base]
    n = len(segmenti)
    for i, s in enumerate(segmenti):
        m = s["margine"]
        if m <= 0 or len(s["p"]) < 2:
            continue
        p = s["p"]
        t0, t1 = tangente_estremo(p, True), tangente_estremo(p, False)
        prec, succ = segmenti[(i - 1) % n], segmenti[(i + 1) % n]
        # all'estremo verso un bordo senza margine: prolunga e chiudi sulla sua retta;
        # verso un bordo con margine: raccordo tondo
        a = [p[0] - t0 * 2 * m] if prec["margine"] <= 0 else []
        b = [p[-1] + t1 * 2 * m] if succ["margine"] <= 0 else []
        # fascia solo verso l'esterno (destra di un contorno antiorario)
        fascia = LineString(np.vstack(a + [p] + b)).buffer(-m, single_sided=True, cap_style=2,
                                                           join_style=1)
        if prec["margine"] <= 0:
            fascia = fascia.difference(semipiano_fuori(p[0], tangente_estremo(prec["p"], False), 3 * m))
        else:
            fascia = fascia.union(Point(p[0]).buffer(m))
        if succ["margine"] <= 0:
            fascia = fascia.difference(semipiano_fuori(p[-1], tangente_estremo(succ["p"], True), 3 * m))
        else:
            fascia = fascia.union(Point(p[-1]).buffer(m))
        parti.append(fascia)
    tot = unary_union(parti).buffer(0.01).buffer(-0.01)
    if tot.geom_type == "MultiPolygon":
        tot = max(tot.geoms, key=lambda g: g.area)
    return Polygon(tot.exterior).simplify(0.03), base


def tratti(punti, tieni):
    """Spezza una polilinea nei tratti consecutivi dove tieni e' vero."""
    out, cur = [], []
    for p, k in zip(punti, tieni):
        if k:
            cur.append(p)
        elif len(cur) > 1:
            out.append(np.array(cur))
            cur = []
        else:
            cur = []
    if len(cur) > 1:
        out.append(np.array(cur))
    return out


def isolinea(m, uv, f):
    """Isolinea f=0 sulla mesh, restituita nel piano come polilinee."""
    v = f(m.vertices)
    v = np.where(np.abs(v) < 1e-9, 1e-9, v)
    segs = []
    for tri in m.faces:
        s = v[tri]
        if (s > 0).all() or (s < 0).all():
            continue
        pts = []
        for a, b in ((0, 1), (1, 2), (2, 0)):
            if s[a] * s[b] < 0:
                t = s[a] / (s[a] - s[b])
                pts.append(uv[tri[a]] + t * (uv[tri[b]] - uv[tri[a]]))
        if len(pts) == 2:
            segs.append(LineString(pts))
    if not segs:
        return []
    g = linemerge(segs)
    geoms = getattr(g, "geoms", [g])
    return [np.array(x.coords) for x in geoms if x.length > 5]


# ---------------------------------------------------------------------------
# Costruzione dei cartamodelli
# ---------------------------------------------------------------------------

class Cartamodello:
    def __init__(self, nome, titolo, materiale, spessore, quantita):
        self.nome, self.titolo, self.materiale = nome, titolo, materiale
        self.spessore, self.quantita = spessore, quantita
        self.linee = {k: [] for k in STILI}   # layer -> [polilinee]
        self.fori = []                          # (centro, diametro, layer)
        self.testi = []                         # (pos, testo, altezza mm)
        self.freccia = None
        self.note = {}
        self.rif = {}                           # pezzo sovrapposto -> linee

    def trasla(self, d):
        d = np.asarray(d, float)
        self.linee = {k: [np.asarray(p) + d for p in v] for k, v in self.linee.items()}
        self.fori = [(c + d, dm, ly) for c, dm, ly in self.fori]
        self.testi = [(np.asarray(p) + d, t, h) for p, t, h in self.testi]
        self.taglio = Polygon(np.asarray(self.taglio.exterior.coords) + d)
        self.base = Polygon(np.asarray(self.base.exterior.coords) + d)
        self.segmenti = [dict(sg, p=np.asarray(sg["p"]) + d) for sg in self.segmenti]

    def limiti(self):
        return np.array(self.taglio.bounds)


def orientamento(m, uv, laterale, tiro_verticale=False):
    """Rotazione 2x2: tallone a sinistra/punta a destra, o alto in alto per i laterali."""
    J, A = jacobiani(m, uv)
    dx = (J @ np.array([1.0, 0, 0]) * A[:, None]).sum(0)
    dz = (J @ np.array([0, 0, 1.0]) * A[:, None]).sum(0)
    if laterale:
        ang = np.arctan2(dz[1], dz[0]) - np.pi / 2
    else:
        ang = np.arctan2(dx[1], dx[0])
    c, s = np.cos(-ang), np.sin(-ang)
    R = np.array([[c, -s], [s, c]])
    tiro = R @ (dz if tiro_verticale else dx)
    return R, tiro / np.linalg.norm(tiro)


def cartamodello_tomaia(info, dati, cache):
    nome = info["nome"]
    m3 = trimesh.load(os.path.join(OUT, info["camicia"]), process=False)
    cuciture = [q for b in info["bordi"] if b["tipo"] != "filo_forma" for q in b["punti"]]
    m, uv = spiana(m3, cuciture)
    dist = distorsione(m, uv)
    R, tiro = orientamento(m, uv, nome in LATERALI, nome == "bacchetta")
    sopra = nome == "sottopiede"   # vista dall'alto (lato piede)

    def T(p):
        q = np.asarray(p) @ R.T
        if sopra:
            q = q * [1, -1]
        return q

    uv2 = T(uv)
    if sopra:
        tiro = tiro * [1, -1]
    cache[nome] = (m, uv2)

    # bordi tipizzati nel piano
    segmenti = []
    for b in info["bordi"]:
        p2, _ = mappa(m, uv2, b["punti"])
        marg = 0.0
        if b["tipo"] == "filo_forma":
            marg = MARGINE_MONTAGGIO.get(nome, 0.0)
        elif nome.startswith("fodera_quartiere") and b["tipo"] in ("bocca", "occhielleria"):
            marg = RIFILATURA_FODERA
        segmenti.append({"tipo": b["tipo"], "p": p2, "margine": marg, "p3": np.array(b["punti"])})
    anello = np.vstack([s["p"][:-1] for s in segmenti])
    x, y = anello[:, 0], anello[:, 1]
    if 0.5 * np.sum(x * np.roll(y, -1) - np.roll(x, -1) * y) < 0:   # antiorario
        segmenti = [dict(s, p=s["p"][::-1], p3=s["p3"][::-1]) for s in segmenti[::-1]]

    taglio, base = contorno_taglio(segmenti)
    c = Cartamodello(nome, info["descrizione"], info["materiale"], info["spessore_mm"],
                     info["quantita_paio"])
    c.taglio, c.base = taglio, base
    c.segmenti = segmenti
    c.linee["TAGLIO"].append(np.asarray(taglio.exterior.coords))
    c.note["distorsione"] = dist

    # linea del filo forma (dove il margine di montaggio inizia)
    for s in segmenti:
        if s["margine"] > 0:
            c.linee["MONTAGGIO"].append(s["p"])
    # cuciture
    for cu in info.get("cuciture", []):
        for s in segmenti:
            if s["tipo"] != cu["bordo"]:
                continue
            for d in cu["distanze_dal_bordo_mm"]:
                q = parallela(s["p"], d)
                if q is not None:
                    c.linee["CUCITURA"].append(q)
    # scarniture
    for s in segmenti:
        if s["tipo"] in SCARNITURA:
            q = parallela(s["p"], SCARNITURA[s["tipo"]], accorcia=2.0)
            if q is not None:
                c.linee["SCARNITURA"].append(q)
                k = len(q) // 2
                c.testi.append((q[k], f"scarnire {SCARNITURA[s['tipo']]:.0f}", 2.2))
    # linee di sovrapposizione degli altri pezzi
    interno = base.buffer(-0.15)
    for altro, tipo in RIFERIMENTI.get(nome, []):
        pa = next(p for p in dati["pezzi"] if p["nome"] == altro)
        for b in pa["bordi"]:
            if b["tipo"] != tipo:
                continue
            q, dd = mappa(m, uv2, b["punti"])
            dentro = [(d < 0.4) and interno.contains(Point(p)) for p, d in zip(q, dd)]
            for t in tratti(q, dentro):
                if lunghezza(t) > 4:
                    c.linee["RIFERIMENTO"].append(t)
                    c.rif.setdefault(altro, []).append(t)
    # asse (linea di centro della forma)
    if nome in CON_ASSE:
        for a in isolinea(m, uv2, lambda V: V[:, 1] - gf.pchip(gf.CENTRO, V[:, 0])):
            c.linee["ASSE"].append(a)
    # occhielli
    for o in dati["occhielli"]:
        if nome.endswith(o["lato"]) and ("quartiere" in nome):
            q, d = mappa(m, uv2, [o["centro_su_forma"]])
            if d[0] < 1.0:
                c.fori.append((q[0], o["diametro_mm"], "FORI" if nome.startswith("quartiere") else "RIFERIMENTO"))
    tacche(c)
    c.freccia = (None, tiro)
    return c


def tacche(c):
    """Tacche sul contorno di taglio agli estremi di asse e linee di sovrapposizione."""
    bordo = c.base.exterior
    for layer in ("ASSE", "RIFERIMENTO"):
        for linea in c.linee[layer]:
            for e in (linea[0], linea[-1]):
                if bordo.distance(Point(e)) > 1.0:
                    continue
                # margine del bordo piu' vicino
                seg = min(c.segmenti, key=lambda s: LineString(s["p"]).distance(Point(e)))
                pb = np.array(bordo.interpolate(bordo.project(Point(e))).coords[0])
                ps = ricampiona(seg["p"], 0.5)
                n = normali_sinistra(ps)[int(np.argmin(np.linalg.norm(ps - pb, axis=1)))]
                p0 = pb - n * seg["margine"]
                c.linee["TACCHE"].append(np.array([p0, p0 + n * 3.0]))


def cartamodello_piano(nome, titolo, materiale, spessore, quantita, poligono, asse=None,
                       linee_extra=()):
    """Pezzi del fondo: contorno piano gia' noto (nessuno spianamento)."""
    c = Cartamodello(nome, titolo, materiale, spessore, quantita)
    pol = Polygon(poligono).buffer(0)
    c.taglio = c.base = Polygon(pol.exterior)
    c.segmenti = [{"tipo": "contorno", "p": np.asarray(pol.exterior.coords), "margine": 0.0}]
    c.linee["TAGLIO"].append(np.asarray(pol.exterior.coords))
    if asse is not None:
        c.linee["ASSE"].append(asse)
    for layer, l in linee_extra:
        c.linee[layer].append(l)
    c.freccia = (None, np.array([1.0, 0.0]))
    c.note["distorsione"] = None
    tacche(c)
    return c


def fondo(dati, cartamodelli):
    f = {x["nome"]: np.array(x["contorno_pianta"]) for x in dati["fondo"]}
    # suola: sviluppo lungo la curva del fondo (punta e enfranchimento)
    xs = np.linspace(-20, 300, 3201)
    z = gf.pchip(gf.FONDO, xs)
    s = np.concatenate([[0], np.cumsum(np.sqrt(np.diff(xs) ** 2 + np.diff(z) ** 2))])
    svil = lambda x: np.interp(x, xs, s)  # noqa: E731
    suola = f["suola"]
    S = np.column_stack([svil(suola[:, 0]), suola[:, 1]])
    xa = np.linspace(suola[:, 0].min() + 3, suola[:, 0].max() - 3, 200)
    asse = np.column_stack([svil(xa), gf.pchip(gf.CENTRO, xa)])
    ps = Polygon(suola)
    yb = ps.intersection(LineString([(X_TACCO, -200), (X_TACCO, 200)])).bounds
    petto = np.array([[svil(X_TACCO), yb[1]], [svil(X_TACCO), yb[3]]])
    cartamodelli.append(cartamodello_piano(
        "suola", "Suola", "cuoio da suola 5 mm", 5.0, 2, S, asse, [("RIFERIMENTO", petto)]))
    cartamodelli[-1].testi.append((petto.mean(0) + [4, 0], "petto tacco", 2.5))
    tacco = f["tacco_alzo"]
    cartamodelli.append(cartamodello_piano(
        "tacco_alzo", "Alzo tacco", "cuoio da suola 4,5-5 mm", 4.75, 8, tacco,
        np.column_stack([np.linspace(tacco[:, 0].min() + 3, X_TACCO - 1, 50),
                         gf.pchip(gf.CENTRO, np.linspace(tacco[:, 0].min() + 3, X_TACCO - 1, 50))])))
    cartamodelli[-1].note["nota"] = "4 alzi per tacco; il primo (sotto la suola) a cuneo"
    cartamodelli.append(cartamodello_piano(
        "sopratacco", "Sopratacco", "gomma 6 mm", 6.0, 2, f["sopratacco"]))
    # guardolo: striscia
    Lg = Polygon(suola).buffer(-6).length + 10
    rett = np.array([[0, 0], [Lg, 0], [Lg, 12], [0, 12], [0, 0]])
    g = cartamodello_piano("guardolo", "Guardolo 360°", "cuoio per guardolo 3 mm", 3.0, 2, rett)
    g.note["nota"] = f"striscia 12 x {Lg:.0f} mm (giunta 10 mm al tallone)"
    cartamodelli.append(g)


# ---------------------------------------------------------------------------
# Uscite: DXF, SVG, PDF
# ---------------------------------------------------------------------------

def cartiglio(c):
    """Testi del pezzo, posizionati nel punto piu' interno."""
    pl = c.base.buffer(-2)
    if pl.is_empty:
        pl = c.base
    from shapely.ops import polylabel
    poly = max(getattr(pl, "geoms", [pl]), key=lambda g: g.area)
    centro = np.array(polylabel(poly, tolerance=0.5).coords[0])
    righe = [(c.titolo.upper(), 4.0), ("Oxford cap-toe tg 42 - destra", 2.6),
             (f"{c.materiale}", 2.6), (f"tagliare {c.quantita} per paio (dx + sx speculare)"
                                       if c.nome not in ("tacco_alzo",) else f"tagliare {c.quantita} per paio", 2.6)]
    if "nota" in c.note:
        righe.append((c.note["nota"], 2.4))
    out, y = [], centro[1] + 7
    for t, h in righe:
        out.append((np.array([centro[0], y]), t, h))
        y -= h * 1.7
    return out, centro


def freccia_tiro(c, centro):
    d = c.freccia[1]
    a = centro + np.array([0, -18]) - d * 15
    b = a + d * 30
    n = np.array([-d[1], d[0]])
    punta = [b - d * 4 + n * 2, b, b - d * 4 - n * 2]
    return [np.array([a, b]), np.array(punta)], (a + b) / 2 + n * 3


def disegna_dxf(msp, c, d=(0, 0)):
    d = np.asarray(d, float)
    for layer, linee in c.linee.items():
        for l in linee:
            msp.add_lwpolyline((np.asarray(l) + d).tolist(), dxfattribs={"layer": layer})
    for centro, dm, layer in c.fori:
        msp.add_circle((centro + d).tolist(), dm / 2, dxfattribs={"layer": layer})
    testi, centro = cartiglio(c)
    for p, t, h in testi + c.testi:
        msp.add_text(t, height=h, dxfattribs={"layer": "TESTO"}).set_placement(
            tuple(np.asarray(p) + d), align=TextEntityAlignment.MIDDLE_CENTER)
    fr, pt = freccia_tiro(c, centro)
    for l in fr:
        msp.add_lwpolyline((l + d).tolist(), dxfattribs={"layer": "TESTO"})
    msp.add_text("verso del tiro", height=2.2, dxfattribs={"layer": "TESTO"}).set_placement(
        tuple(pt + d), align=TextEntityAlignment.MIDDLE_CENTER)


def nuovo_dxf():
    doc = ezdxf.new("R2010", setup=True)
    doc.header["$INSUNITS"] = 4
    doc.header["$MEASUREMENT"] = 1
    for nome, (_, _, _, col, lt) in STILI.items():
        doc.layers.add(nome, color=col, linetype=lt)
    return doc


def scrivi_svg(c, path):
    x0, y0, x1, y1 = c.limiti()
    pad = 10
    W, H = x1 - x0 + 2 * pad, y1 - y0 + 2 * pad
    tr = lambda p: (p[0] - x0 + pad, H - (p[1] - y0 + pad))  # noqa: E731
    dash = {"MONTAGGIO": "0.6 1.2", "CUCITURA": "2.5 1.2", "SCARNITURA": "3 1 0.6 1",
            "ASSE": "5 1.2 1.2 1.2"}
    righe = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W:.1f}mm" height="{H:.1f}mm" '
             f'viewBox="0 0 {W:.2f} {H:.2f}">',
             f'<title>{c.titolo} - Oxford tg 42</title>']
    for layer, linee in c.linee.items():
        col, lw = STILI[layer][0], STILI[layer][1] * 0.3528
        da = f' stroke-dasharray="{dash[layer]}"' if layer in dash else ""
        righe.append(f'<g id="{layer}" fill="none" stroke="{col}" stroke-width="{lw:.2f}"{da}>')
        for l in linee:
            pts = " ".join(f"{a:.2f},{b:.2f}" for a, b in map(tr, l))
            righe.append(f'<polyline points="{pts}"/>')
        righe.append("</g>")
    righe.append('<g id="FORI" fill="none" stroke="#111" stroke-width="0.2">')
    for centro, dm, _ in c.fori:
        a, b = tr(centro)
        righe.append(f'<circle cx="{a:.2f}" cy="{b:.2f}" r="{dm / 2:.2f}"/>')
    righe.append("</g>")
    testi, centro = cartiglio(c)
    righe.append('<g id="TESTO" font-family="Helvetica, Arial, sans-serif" text-anchor="middle" fill="#222">')
    for p, t, h in testi + c.testi:
        a, b = tr(p)
        righe.append(f'<text x="{a:.2f}" y="{b + h * 0.35:.2f}" font-size="{h:.2f}">{t}</text>')
    fr, pt = freccia_tiro(c, centro)
    for l in fr:
        pts = " ".join(f"{a:.2f},{b:.2f}" for a, b in map(tr, l))
        righe.append(f'<polyline points="{pts}" fill="none" stroke="#222" stroke-width="0.3"/>')
    a, b = tr(pt)
    righe.append(f'<text x="{a:.2f}" y="{b:.2f}" font-size="2.2">verso del tiro</text>')
    righe.append("</g></svg>")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(righe))


def disegna_mpl(ax, c, d=(0, 0), scala_testo=1.0, testi=True):
    d = np.asarray(d, float)
    for layer, linee in c.linee.items():
        col, lw, ls = STILI[layer][:3]
        for l in linee:
            l = np.asarray(l) + d
            ax.plot(l[:, 0], l[:, 1], color=col, lw=lw * scala_testo ** 0.3, ls=ls,
                    solid_capstyle="butt")
    for centro, dm, layer in c.fori:
        ax.add_patch(plt.Circle(centro + d, dm / 2, fill=False, lw=0.6, color=STILI[layer][0]))
    if not testi:
        return
    tt, centro = cartiglio(c)
    pt_mm = 72 / 25.4 * scala_testo
    for p, t, h in tt + c.testi:
        ax.text(*(np.asarray(p) + d), t, ha="center", va="center", fontsize=h * pt_mm,
                color=STILI["TESTO"][0])
    fr, pt = freccia_tiro(c, centro)
    for l in fr:
        ax.plot(*(l + d).T, color="#222", lw=0.6)
    ax.text(*(pt + d), "verso del tiro", ha="center", va="center", fontsize=2.2 * pt_mm, color="#222")


def legenda(ax, x, y, h=4.2):
    voci = [("TAGLIO", "linea di taglio"), ("MONTAGGIO", "filo forma (inizio margine di montaggio)"),
            ("CUCITURA", "cucitura"), ("SCARNITURA", "limite scarnitura"),
            ("RIFERIMENTO", "linea di sovrapposizione / fori fodera"), ("ASSE", "asse della forma"),
            ("TACCHE", "tacche")]
    for i, (k, t) in enumerate(voci):
        col, lw, ls = STILI[k][:3]
        yy = y - i * h
        ax.plot([x, x + 12], [yy, yy], color=col, lw=lw, ls=ls)
        ax.text(x + 15, yy, t, va="center", fontsize=7, color="#333")


def pagina_pezzo(pdf, c):
    A3 = (420.0, 297.0)
    fig = plt.figure(figsize=(A3[0] / 25.4, A3[1] / 25.4))
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, A3[0]); ax.set_ylim(0, A3[1]); ax.set_aspect("equal"); ax.axis("off")
    x0, y0, x1, y1 = c.limiti()
    w, h = x1 - x0, y1 - y0
    zona = (10, 30, 305, 285)  # area di disegno (mm)
    k = min(1.0, (zona[2] - zona[0]) / w, (zona[3] - zona[1]) / h)
    if k < 1:  # pezzo piu' grande del foglio (guardolo): disegno ridotto
        sub = fig.add_axes([zona[0] / A3[0], zona[1] / A3[1], (zona[2] - zona[0]) / A3[0],
                            (zona[3] - zona[1]) / A3[1]])
        disegna_mpl(sub, c, testi=False)
        sub.set_aspect("equal"); sub.axis("off"); sub.autoscale_view()
        ax.text(zona[0], zona[1] - 8, f"NON IN SCALA ({w:.0f} x {h:.0f} mm): usare il DXF o l'SVG 1:1",
                fontsize=9, weight="bold", color="#b03a2e")
    else:
        d = np.array([zona[0] + (zona[2] - zona[0] - w) / 2 - x0,
                      zona[1] + (zona[3] - zona[1] - h) / 2 - y0])
        disegna_mpl(ax, c, d)
    # colonna informazioni
    xi = 315
    ax.text(xi, 280, c.titolo, fontsize=16, weight="bold", va="top")
    info = [f"Modello: Oxford cap-toe, tg 42 (forma uomo, tacco 25 mm)",
            f"Materiale: {c.materiale}", f"Spessore: {c.spessore:g} mm",
            f"Quantità per paio: {c.quantita}",
            f"Area cartamodello: {c.taglio.area / 100:.1f} cm²",
            f"Ingombro: {w:.0f} x {h:.0f} mm"]
    if c.note.get("distorsione"):
        dd = c.note["distorsione"]
        info.append(f"Sviluppo: errore lunghezze medio {dd['errore_lunghezze_medio_pct']:.1f}%")
    if "nota" in c.note:
        info.append(c.note["nota"])
    margini = sorted({(s["tipo"], s["margine"]) for s in c.segmenti if s["margine"] > 0})
    for t, mm in margini:
        info.append(f"Margine {t.replace('_', ' ')}: {mm:g} mm")
    for i, t in enumerate(info):
        ax.text(xi, 268 - i * 6.2, t, fontsize=7.5, va="top", wrap=True)
    legenda(ax, xi, 150)
    # quadrato di controllo scala
    ax.add_patch(plt.Rectangle((xi, 20), 50, 50, fill=False, lw=0.8))
    ax.text(xi + 25, 45, "50 x 50 mm", ha="center", va="center", fontsize=8)
    ax.text(xi, 14, "Stampare al 100% (A3, senza adattamento)", fontsize=7)
    ax.text(10, 8, "Vista dal lato esterno della scarpa destra. Sinistra: cartamodello rovesciato.",
            fontsize=7, color="#444")
    pdf.savefig(fig)
    plt.close(fig)


def disponi(cartamodelli, larghezza=900, spazio=25):
    """Disposizione a ripiani per tavola riassuntiva e DXF complessivo."""
    pos, x, y, riga_h = {}, 0.0, 0.0, 0.0
    for c in sorted(cartamodelli, key=lambda c: -(c.limiti()[3] - c.limiti()[1])):
        x0, y0, x1, y1 = c.limiti()
        w, h = x1 - x0, y1 - y0
        if x + w > larghezza and x > 0:
            x, y, riga_h = 0.0, y - riga_h - spazio, 0.0
        pos[c.nome] = np.array([x - x0, y - y1])
        x += w + spazio
        riga_h = max(riga_h, h)
    return pos


def tavola_riassuntiva(pdf, cartamodelli, riepilogo):
    A3 = (420.0, 297.0)
    fig = plt.figure(figsize=(A3[0] / 25.4, A3[1] / 25.4))
    ax = fig.add_axes([0.02, 0.36, 0.96, 0.58])
    pos = disponi(cartamodelli, larghezza=1400, spazio=30)
    for c in cartamodelli:
        disegna_mpl(ax, c, pos[c.nome], scala_testo=0.25, testi=False)
        x0, y0, x1, y1 = c.limiti()
        ax.text(*(pos[c.nome] + [(x0 + x1) / 2, y0 - 9]), c.titolo, ha="center", fontsize=6.5)
    ax.set_aspect("equal"); ax.axis("off"); ax.autoscale_view()
    fig.text(0.02, 0.965, "Oxford cap-toe tg 42 - piani di taglio", fontsize=15, weight="bold")
    fig.text(0.02, 0.945, "Tavola riassuntiva (non in scala). Fogli successivi: un cartamodello per pagina al 100%.",
             fontsize=8, color="#444")
    # tabella
    tx = fig.add_axes([0.02, 0.02, 0.96, 0.32]); tx.axis("off")
    righe = [[r["titolo"], r["materiale"], f'{r["spessore_mm"]:g}', str(r["quantita_paio"]),
              f'{r["area_cm2"]:.1f}', f'{r["area_paio_dm2"]:.2f}',
              "-" if r["errore_sviluppo_pct"] is None else f'{r["errore_sviluppo_pct"]:.1f}']
             for r in riepilogo["pezzi"]]
    t = tx.table(cellText=righe, colLabels=["Pezzo", "Materiale", "mm", "Q.tà/paio", "Area cm²",
                                            "dm²/paio", "Err. sviluppo %"],
                 loc="upper left", colLoc="left", cellLoc="left",
                 colWidths=[0.17, 0.27, 0.05, 0.07, 0.08, 0.08, 0.1])
    t.auto_set_font_size(False); t.set_fontsize(6.5); t.scale(1, 1.05)
    y = 0.98
    tx.text(0.86, y, "Consumo stimato per paio", fontsize=8, weight="bold", va="top")
    for mat, v in riepilogo["consumi_per_materiale"].items():
        y -= 0.075
        tx.text(0.86, y, f"{mat}: {v['netto_dm2']:.1f} dm² netti, {v['lordo_dm2']:.1f} con sfrido",
                fontsize=6.5, va="top", wrap=True)
    pdf.savefig(fig)
    fig.savefig(os.path.join(DEST, "tavola_riassuntiva.png"), dpi=110)
    plt.close(fig)


# ---------------------------------------------------------------------------
# Controlli e riepilogo
# ---------------------------------------------------------------------------

def lunghezza_tipo(c, tipo):
    return sum(lunghezza(s["p"]) for s in c.segmenti if s["tipo"] == tipo)


def controlli(cm):
    """Confronta le lunghezze dei bordi che vanno cuciti insieme (nel piano)."""
    def rif(nome, fonte):
        return sum(lunghezza(l) for l in cm[nome].rif.get(fonte, []))
    q_e, q_i = cm["quartiere_esterno"], cm["quartiere_interno"]
    fq_e, fq_i = cm["fodera_quartiere_esterno"], cm["fodera_quartiere_interno"]
    righe = [
        ("cucitura posteriore quartieri (esterno / interno)",
         lunghezza_tipo(q_e, "cucitura_posteriore"), lunghezza_tipo(q_i, "cucitura_posteriore")),
        ("cucitura posteriore fodere (esterno / interno)",
         lunghezza_tipo(fq_e, "cucitura_posteriore"), lunghezza_tipo(fq_i, "cucitura_posteriore")),
        ("bordo mascherina / linea mascherina sui quartieri",
         lunghezza_tipo(cm["mascherina"], "mascherina"),
         rif("quartiere_esterno", "mascherina") + rif("quartiere_interno", "mascherina")),
        ("bordo puntale / linea puntale sulla mascherina",
         lunghezza_tipo(cm["puntale"], "puntale"), rif("mascherina", "puntale")),
        ("cucitura fodere quartiere / linea sulla fodera avampiede",
         lunghezza_tipo(fq_e, "fodera_cucitura") + lunghezza_tipo(fq_i, "fodera_cucitura"),
         rif("fodera_avampiede", "fodera_quartiere_esterno") + rif("fodera_avampiede", "fodera_quartiere_interno")),
    ]
    return [{"controllo": n, "a_mm": round(a, 1), "b_mm": round(b, 1),
             "differenza_mm": round(a - b, 1), "differenza_pct": round(100 * (a - b) / b, 1)}
            for n, a, b in righe]


def main():
    with open(os.path.join(OUT, "pezzi.json"), encoding="utf-8") as f:
        dati = json.load(f)
    os.makedirs(os.path.join(DEST, "dxf"), exist_ok=True)
    os.makedirs(os.path.join(DEST, "svg"), exist_ok=True)

    cache, cartamodelli = {}, []
    for info in dati["pezzi"]:
        print("sviluppo", info["nome"])
        cartamodelli.append(cartamodello_tomaia(info, dati, cache))
    # fodera linguetta: stesso contorno della linguetta
    lg = next(c for c in cartamodelli if c.nome == "linguetta")
    fl = Cartamodello("fodera_linguetta", "Fodera linguetta", "pelle fodera (vitello) 0,8 mm", 0.8, 2)
    fl.taglio, fl.base, fl.segmenti = lg.taglio, lg.base, lg.segmenti
    fl.linee["TAGLIO"] = list(lg.linee["TAGLIO"])
    fl.linee["ASSE"] = list(lg.linee["ASSE"])
    fl.linee["RIFERIMENTO"] = [l for l in lg.linee["RIFERIMENTO"]]
    fl.freccia, fl.note = lg.freccia, {"distorsione": lg.note["distorsione"],
                                       "nota": "stesso contorno della linguetta"}
    tacche(fl)
    cartamodelli.append(fl)
    fondo(dati, cartamodelli)

    # origine di ogni cartamodello in (0, 0)
    for c in cartamodelli:
        x0, y0, _, _ = c.limiti()
        c.trasla([-x0, -y0])

    # file per pezzo
    for c in cartamodelli:
        doc = nuovo_dxf()
        disegna_dxf(doc.modelspace(), c)
        doc.saveas(os.path.join(DEST, "dxf", f"{c.nome}.dxf"))
        scrivi_svg(c, os.path.join(DEST, "svg", f"{c.nome}.svg"))
    doc = nuovo_dxf()
    pos = disponi(cartamodelli)
    for c in cartamodelli:
        disegna_dxf(doc.modelspace(), c, pos[c.nome])
    doc.saveas(os.path.join(DEST, "tutti_i_pezzi.dxf"))

    # riepilogo e consumi
    pezzi, consumi = [], {}
    for c in cartamodelli:
        area = c.taglio.area / 100
        dm2 = area * c.quantita / 100
        chiave = next((k for k in SCARTO if k in c.materiale),
                      re.sub(r"\s+[\d,.\-]+\s*mm$", "", c.materiale))
        v = consumi.setdefault(chiave, {"netto_dm2": 0.0, "lordo_dm2": 0.0})
        v["netto_dm2"] += dm2
        v["lordo_dm2"] += dm2 * (1 + SCARTO.get(chiave, SCARTO_ALTRO))
        d = c.note.get("distorsione")
        x0, y0, x1, y1 = c.limiti()
        pezzi.append({"nome": c.nome, "titolo": c.titolo, "materiale": c.materiale,
                      "spessore_mm": c.spessore, "quantita_paio": c.quantita,
                      "area_cm2": round(area, 1), "area_paio_dm2": round(dm2, 2),
                      "ingombro_mm": [round(x1 - x0, 1), round(y1 - y0, 1)],
                      "perimetro_taglio_mm": round(c.taglio.length, 1),
                      "errore_sviluppo_pct": None if d is None else d["errore_lunghezze_medio_pct"],
                      "distorsione": d, "dxf": f"dxf/{c.nome}.dxf", "svg": f"svg/{c.nome}.svg"})
    for v in consumi.values():
        v["netto_dm2"], v["lordo_dm2"] = round(v["netto_dm2"], 2), round(v["lordo_dm2"], 2)
    cm = {c.nome: c for c in cartamodelli}
    riepilogo = {"modello": dati["modello"], "taglia": 42, "unita": "mm",
                 "margini_montaggio_mm": MARGINE_MONTAGGIO,
                 "rifilatura_fodere_mm": RIFILATURA_FODERA,
                 "sfrido_stimato": {**SCARTO, "altri": SCARTO_ALTRO},
                 "pezzi": pezzi, "consumi_per_materiale": consumi,
                 "controllo_cuciture": controlli(cm)}
    with open(os.path.join(DEST, "riepilogo.json"), "w", encoding="utf-8") as f:
        json.dump(riepilogo, f, indent=1, ensure_ascii=False)

    with PdfPages(os.path.join(DEST, "piani_taglio_oxford_42.pdf")) as pdf:
        tavola_riassuntiva(pdf, cartamodelli, riepilogo)
        for c in cartamodelli:
            pagina_pezzo(pdf, c)

    for p in pezzi:
        print(f'{p["titolo"]:28s} {p["ingombro_mm"][0]:6.1f} x {p["ingombro_mm"][1]:6.1f} mm  '
              f'{p["area_cm2"]:7.1f} cm2  err {p["errore_sviluppo_pct"]}')
    for k in riepilogo["controllo_cuciture"]:
        print(k)
    print(consumi)


if __name__ == "__main__":
    main()
