#!/usr/bin/env python3
"""Generatore parametrico di forma (last) 3D da montaggio per calzatura uomo.

Riferimento: taglia 42 francese (punto Paris 6,67 mm), tacco 25 mm.
Sistema di riferimento (mm): X dal tallone verso la punta, Y verso il lato
interno (mediale) della forma destra, Z verso l'alto. Il piano Z=0 e' quello
d'appoggio della pianta (battuta).

Uso:
    python3 genera_forma.py                       # 42, tacco 25 mm
    python3 genera_forma.py --taglia 43 --tacco 30
"""

import argparse
import json
import os

import numpy as np

PUNTO_PARIS = 20.0 / 3.0  # mm per numero
TAGLIA_BASE = 42
LUNGHEZZA_BASE = 280.0     # lunghezza forma (42 x 6,67)
TACCO_BASE = 25.0          # altezza tacco di riferimento
CRESCITA_CALZATA = 5.0     # mm di giro pianta per numero


# --------------------------------------------------------------------------
# Profili di controllo (forma destra, taglia 42, tacco 25)
# --------------------------------------------------------------------------

# Profilo inferiore (fondo forma): seggetta, enfranchimento, battuta, punta.
FONDO = [(0, 25.0), (40, 25.0), (70, 23.6), (100, 19.5), (130, 12.0),
         (160, 4.8), (185, 0.8), (198, 0.0), (215, 0.6), (240, 3.4),
         (262, 7.6), (280, 12.0)]

# Profilo superiore: cono, collo piede, dorso, mascherina, punta.
DORSO = [(0, 118.0), (25, 121.0), (55, 120.0), (85, 115.0), (110, 104.0),
         (135, 89.0), (160, 71.0), (185, 53.0), (205, 44.0), (225, 38.5),
         (245, 34.0), (262, 31.0), (280, 27.0)]

# Semilarghezza massima della sezione.
SEMILARGHEZZA = [(0, 32.0), (30, 33.0), (60, 33.2), (100, 33.5), (130, 37.5),
                 (160, 43.0), (180, 46.2), (200, 47.0), (225, 43.0),
                 (245, 36.5), (262, 28.5), (280, 22.0)]

# Spostamento del centro sezione verso l'interno (asse forma / punta).
CENTRO = [(0, 0.0), (30, -0.5), (60, -1.3), (100, -3.0), (130, -3.0),
          (160, -1.5), (180, -0.5), (200, 2.5), (225, 4.5), (245, 5.8),
          (262, 6.5), (280, 7.0)]

# Rastremazione verso l'alto della sezione (0 = pareti verticali).
RASTREMAZIONE = [(0, 0.52), (60, 0.50), (100, 0.42), (140, 0.24),
                 (190, 0.12), (240, 0.10), (280, 0.10)]

# Esponente superellisse parte superiore (2 = ellisse, >2 = piu' squadrata).
ESP_SUPERIORE = [(0, 2.8), (80, 2.7), (120, 2.4), (190, 2.3), (280, 2.4)]

ESP_INFERIORE = 3.6       # fondo piatto con spigolo (filo) arrotondato
Z_SPERONE = 55.0          # quota del punto piu' arretrato del tallone
Z_PUNTA = 18.0            # quota del vertice della punta

# Chiusure alle estremita': (lunghezza mm, esponente superellisse)
CHIUSURA_TALLONE_FONDO = (30.0, 2.0)
CHIUSURA_TALLONE_DORSO = (30.0, 1.6)
CHIUSURA_TALLONE_PIANTA = (34.0, 2.0)
CHIUSURA_PUNTA_ALTEZZA = (13.0, 2.0)
CHIUSURA_PUNTA_PIANTA = (24.0, 2.2)

# Foro per il perno (bussola) della macchina da montaggio.
FORO_X, FORO_DIAMETRO, FORO_PROFONDITA = 30.0, 11.0, 45.0


# --------------------------------------------------------------------------
# Utilita'
# --------------------------------------------------------------------------

def pchip(punti, x):
    """Interpolazione cubica monotona (Fritsch-Carlson) senza scipy."""
    xs = np.array([p[0] for p in punti], float)
    ys = np.array([p[1] for p in punti], float)
    h = np.diff(xs)
    d = np.diff(ys) / h
    m = np.zeros_like(ys)
    for k in range(1, len(xs) - 1):
        if d[k - 1] * d[k] > 0:
            w1, w2 = 2 * h[k] + h[k - 1], h[k] + 2 * h[k - 1]
            m[k] = (w1 + w2) / (w1 / d[k - 1] + w2 / d[k])
    m[0], m[-1] = d[0], d[-1]
    x = np.clip(np.asarray(x, float), xs[0], xs[-1])
    k = np.clip(np.searchsorted(xs, x) - 1, 0, len(h) - 1)
    t = (x - xs[k]) / h[k]
    h00 = (1 + 2 * t) * (1 - t) ** 2
    h10 = t * (1 - t) ** 2
    h01 = t ** 2 * (3 - 2 * t)
    h11 = t ** 2 * (t - 1)
    return h00 * ys[k] + h10 * h[k] * m[k] + h01 * ys[k + 1] + h11 * h[k] * m[k + 1]


def chiusura(s, n):
    """Quarto di superellisse: 0 in s=0 (tangente verticale), 1 per s>=1."""
    s = np.clip(s, 0.0, 1.0)
    return (1.0 - (1.0 - s) ** n) ** (1.0 / n)


# --------------------------------------------------------------------------
# Costruzione forma
# --------------------------------------------------------------------------

def profili(x):
    """Restituisce i parametri di sezione alla stazione x (forma base)."""
    L = LUNGHEZZA_BASE
    zb0, zt0 = pchip(FONDO, x), pchip(DORSO, x)
    hw = pchip(SEMILARGHEZZA, x)
    yc = pchip(CENTRO, x)

    # Tallone: curva posteriore e arrotondamento in pianta.
    a, n = CHIUSURA_TALLONE_FONDO
    zb = Z_SPERONE - (Z_SPERONE - zb0) * chiusura(x / a, n)
    a, n = CHIUSURA_TALLONE_DORSO
    zt = Z_SPERONE + (zt0 - Z_SPERONE) * chiusura(x / a, n)
    a, n = CHIUSURA_TALLONE_PIANTA
    hw = hw * chiusura(x / a, n)

    # Punta: chiusura in altezza (verso Z_PUNTA) e in pianta.
    a, n = CHIUSURA_PUNTA_ALTEZZA
    e = chiusura((L - x) / a, n)
    zb = Z_PUNTA - (Z_PUNTA - zb) * e
    zt = Z_PUNTA + (zt - Z_PUNTA) * e
    a, n = CHIUSURA_PUNTA_PIANTA
    hw = hw * chiusura((L - x) / a, n)

    return dict(zb=zb, zt=zt, hw=hw, yc=yc,
                k=pchip(RASTREMAZIONE, x), nu=pchip(ESP_SUPERIORE, x))


def anello(p, n_punti):
    """Punti (y, z) di una sezione trasversale."""
    th = np.linspace(0, 2 * np.pi, n_punti, endpoint=False)
    c, s = np.cos(th), np.sin(th)
    H = p["zt"] - p["zb"]
    hl = min(0.30 * H, 26.0)          # semialtezza inferiore (quota max larghezza)
    hu = H - hl
    zc = p["zb"] + hl
    n = np.where(s < 0, ESP_INFERIORE, p["nu"])
    yu = np.sign(c) * np.abs(c) ** (2 / n)
    zu = np.sign(s) * np.abs(s) ** (2 / n)
    tap = 1 - p["k"] * np.clip(zu, 0, 1) ** 1.5
    y = p["yc"] + p["hw"] * yu * tap
    z = zc + np.where(s < 0, hl, hu) * zu
    return y, z


def genera(n_stazioni=220, n_punti=128, uniformita=0.0):
    """uniformita' 0 = stazioni a coseno (fitte alle estremita'), 1 = uniformi."""
    L = LUNGHEZZA_BASE
    t = np.linspace(0, 1, n_stazioni + 2)[1:-1]
    xs = L * ((1 - uniformita) * (1 - np.cos(np.pi * t)) / 2 + uniformita * t)

    vert = [[0.0, pchip(CENTRO, 0.0), Z_SPERONE]]
    for x in xs:
        y, z = anello(profili(x), n_punti)
        vert.extend(np.column_stack([np.full_like(y, x), y, z]))
    vert.append([L, pchip(CENTRO, L), Z_PUNTA])
    vert = np.array(vert)

    facce = []
    ultimo = len(vert) - 1
    idx = lambda i, j: 1 + i * n_punti + (j % n_punti)
    for j in range(n_punti):                  # calotta tallone
        facce.append([0, idx(0, j + 1), idx(0, j)])
    for i in range(n_stazioni - 1):
        for j in range(n_punti):
            a, b = idx(i, j), idx(i, j + 1)
            c, d = idx(i + 1, j + 1), idx(i + 1, j)
            facce += [[a, b, c], [a, c, d]]
    for j in range(n_punti):                  # calotta punta
        i = n_stazioni - 1
        facce.append([ultimo, idx(i, j), idx(i, j + 1)])
    return vert, np.array(facce)


def scala_taglia(vert, taglia, tacco):
    """Sviluppo taglie: lunghezza a punto Paris, giro +5 mm/numero;
    tacco diverso: rotazione del retropiede attorno alla battuta (semplificata)."""
    v = vert.copy()
    sl = (taglia * PUNTO_PARIS) / LUNGHEZZA_BASE
    giro_base = 2 * (2 * 47.0 + 50.0)          # stima giro pianta per scala
    sg = (giro_base + CRESCITA_CALZATA * (taglia - TAGLIA_BASE)) / giro_base
    v[:, 0] *= sl
    v[:, 1] *= sg
    v[:, 2] *= sg
    if tacco != TACCO_BASE:
        xb = 198.0 * sl
        dz = (tacco - TACCO_BASE) * sg
        w = np.clip((xb - v[:, 0]) / xb, 0, 1)
        v[:, 2] += dz * (3 * w ** 2 - 2 * w ** 3)
    return v


def foro_bussola(mesh):
    """Sottrae il foro per il perno della macchina da montaggio."""
    import trimesh
    x = FORO_X
    p = profili(np.array(x))
    sez = mesh.section(plane_origin=[x, 0, 0], plane_normal=[1, 0, 0])
    z_top = sez.vertices[:, 2].max() if sez is not None else float(p["zt"])
    cil = trimesh.creation.cylinder(radius=FORO_DIAMETRO / 2,
                                    height=2 * FORO_PROFONDITA, sections=48)
    cil.apply_translation([x, float(p["yc"]), z_top])
    return mesh.difference(cil, engine="manifold")


def misure(mesh, taglia):
    """Misure principali della forma ricavate dalla mesh."""
    b = mesh.bounds
    sl = (taglia * PUNTO_PARIS) / LUNGHEZZA_BASE

    def giro(origine, normale):
        s = mesh.section(plane_origin=origine, plane_normal=normale)
        if s is None:
            return 0.0
        return float(max(np.linalg.norm(np.diff(d, axis=0), axis=1).sum()
                         for d in s.discrete))

    # Giro pianta: piano per le articolazioni metatarsali (1a mediale a ~72%,
    # 5a laterale a ~64% della lunghezza), inclinato come il nastro.
    p1 = np.array([0.72 * LUNGHEZZA_BASE * sl, 40.0, 0.0])
    p5 = np.array([0.64 * LUNGHEZZA_BASE * sl, -40.0, 0.0])
    asse = (p1 - p5) / np.linalg.norm(p1 - p5)
    n_pianta = np.cross(asse, [0, 0, 1])
    n_pianta = n_pianta / np.linalg.norm(n_pianta)
    origine = (p1 + p5) / 2
    origine[2] = 20.0

    def larghezza_a(x):
        s = mesh.section(plane_origin=[x, 0, 0], plane_normal=[1, 0, 0])
        return float(np.ptp(s.vertices[:, 1])) if s is not None else 0.0

    larghezze = {x: larghezza_a(x) for x in np.arange(150, 230, 2) * sl}
    tallone = {x: larghezza_a(x) for x in np.arange(15, 60, 2) * sl}
    return {
        "taglia": taglia,
        "lunghezza_mm": round(float(b[1, 0] - b[0, 0]), 1),
        "larghezza_pianta_mm": round(max(larghezze.values()), 1),
        "larghezza_tallone_mm": round(max(tallone.values()), 1),
        "altezza_totale_mm": round(float(b[1, 2] - b[0, 2]), 1),
        "giro_pianta_mm": round(giro(origine, n_pianta), 1),
        # Giro collo: piano perpendicolare al dorso nel punto del collo piede.
        "giro_collo_mm": round(giro([0.48 * LUNGHEZZA_BASE * sl, 0, 60.0],
                                    [np.cos(np.radians(30)), 0,
                                     -np.sin(np.radians(30))]), 1),
        "volume_cm3": round(float(mesh.volume) / 1000, 1),
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--taglia", type=int, default=42, help="taglia EU (punto Paris)")
    ap.add_argument("--tacco", type=float, default=25.0, help="altezza tacco mm")
    ap.add_argument("--senza-foro", action="store_true", help="non forare la bussola")
    ap.add_argument("--out", default=os.path.join(os.path.dirname(__file__), "output"))
    args = ap.parse_args()

    import trimesh

    vert, facce = genera()
    vert = scala_taglia(vert, args.taglia, args.tacco)
    dx = trimesh.Trimesh(vert, facce, process=True)
    trimesh.repair.fix_normals(dx)
    if not args.senza_foro:
        dx = foro_bussola(dx)

    sx = dx.copy()
    sx.apply_transform(np.diag([1, -1, 1, 1]))
    trimesh.repair.fix_normals(sx)

    os.makedirs(args.out, exist_ok=True)
    base = f"forma_uomo_{args.taglia}_tacco{int(args.tacco)}"
    for nome, m in (("dx", dx), ("sx", sx)):
        m.export(os.path.join(args.out, f"{base}_{nome}.stl"))

    info = misure(dx, args.taglia)
    info["tacco_mm"] = args.tacco
    info["watertight"] = bool(dx.is_watertight)
    with open(os.path.join(args.out, f"{base}_misure.json"), "w") as f:
        json.dump(info, f, indent=2)
    print(json.dumps(info, indent=2))


if __name__ == "__main__":
    main()
