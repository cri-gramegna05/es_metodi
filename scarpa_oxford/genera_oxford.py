#!/usr/bin/env python3
"""Oxford uomo (cap-toe, allacciatura chiusa) costruita sulla forma tg 42.

Ogni pezzo della tomaia e' una porzione della superficie della forma,
delimitata da linee di modello (isolinee) e poi ispessita. Per ogni pezzo
si esportano:
  - camicie/<pezzo>.obj : superficie sulla forma fino al filo forma
                          (base per lo sviluppo 2D / piani di taglio);
  - oxford_42_dx/sx.glb : scarpa completa, un nodo per pezzo (solidi con
                          spessore e margine di montaggio); --stl per un STL a pezzo;
  - pezzi.json          : materiale, spessore, quantita', tipi di bordo
                          con relativi margini, posizioni occhielli.

Riferimento (mm): X tallone->punta, Y verso l'interno (piede destro), Z alto.
"""

import json
import os
import sys

import numpy as np
import shapely
import trimesh
from shapely.geometry import Polygon, box

QUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(QUI, "..", "forma_3d"))
import genera_forma as gf  # noqa: E402

from geometria import (Superficie, contorno_bordo, distanza_segnata,  # noqa: E402
                       guscio, lastra, ritaglia, spline, tubo)

# --------------------------------------------------------------------------
# Linee di modello (vista laterale X-Z, piede destro, tg 42)
# --------------------------------------------------------------------------

FILO_NZ = -0.70          # filo forma: normale con componente z = -0.70
MARGINE_MONTAGGIO = 16.0  # mm sotto la forma (solo nel 3D e nei piani)
X_GOLA = 156.0           # gola (fine allacciatura, bordo mascherina)
X_TACCO = 76.0           # petto del tacco
X_LATO = 85.0            # dietro: cucitura posteriore; avanti: occhielleria

# Linea bocca (collarino): dal tallone alla sommita' dell'occhielleria.
BOCCA = [(-20, 86), (0, 85), (8, 84), (30, 79), (55, 73), (72, 76),
         (84, 87), (91, 100), (95, 113), (98, 135)]
# Cucitura mascherina/quartieri (oxford: quartieri sotto la mascherina).
MASCHERINA = [(X_GOLA, 140), (X_GOLA, 74), (154.5, 62), (148, 48), (138, 35),
              (126, 23), (119, 12), (116, 0), (114, -40)]
# Linea puntale (retta inclinata).
PUNTALE = [(227.8, 75), (206.4, -15)]
# Contrafforte (bordo superiore), lato esterno e lato interno.
CONTRAFF_EST = [(-20, 78), (0, 77), (25, 74), (48, 62), (62, 44), (70, 26), (72, 0), (73, -40)]
CONTRAFF_INT = [(-20, 78), (0, 77), (28, 74), (55, 62), (71, 44), (79, 26), (82, 0), (83, -40)]

RIPORTO_MASCHERINA = 12.0   # quartieri sotto la mascherina
RIPORTO_PUNTALE = 10.0      # mascherina sotto il puntale
ARRETRA_FODERA = 20.0       # cucitura fodere arretrata rispetto alla mascherina
RIPORTO_FODERA = 8.0
OLTRE_PUNTALE_RINFORZO = 4.0

# Semi-luce allacciatura (sulla superficie, dal centro dorso) e linguetta.
SEMILUCE = [(0, 0.0), (85, 0.0), (92, 4.5), (X_GOLA, 0.3), (400, 0.0)]
LINGUETTA_LARGH = [(0, 52.0), (74, 52.0), (X_GOLA, 44.0), (400, 44.0)]
LINGUETTA_CIMA, LINGUETTA_RAGGIO = 74.0, 14.0
LINGUETTA_SOTTO = 14.0      # sotto la mascherina oltre la gola
BACCHETTA_LARGH = [(-40, 26.0), (25, 26.0), (84, 18.0), (200, 18.0)]  # in funzione di z
OCCHIELLI_X = np.linspace(104, 142, 5)
OCCHIELLI_DAL_BORDO = 9.0
OCCHIELLO_D = 3.6

# Fondo
SPESS_SOTTOPIEDE = 2.5
QUOTA_SUOLA = 5.0           # suola sotto il fondo forma (sottopiede + montaggio)
SPESS_SUOLA = 5.0
SPESS_GUARDOLO = 3.0
SPESS_SOPRATACCO = 6.0
N_ALZI = 4
SPORGENZA = [(-50, 4.0), (60, 4.0), (100, 4.8), (150, 5.8), (190, 6.5), (400, 6.5)]

COL_PELLE = (62, 36, 22)
COL_FODERA = (214, 190, 150)
COL_RINFORZO = (150, 150, 150)
COL_CUOIO = (150, 100, 58)
COL_BORDO_SUOLA = (40, 26, 18)
COL_GOMMA = (25, 25, 25)

# nome, descrizione, materiale, spessore, rango (ordine di stratificazione),
# colore, quantita' per paio
PEZZI = [
    ("sottopiede", "Sottopiede", "cuoio/cartone fibra 2,5 mm", SPESS_SOTTOPIEDE, -1, (176, 140, 96), 2),
    ("fodera_avampiede", "Fodera avampiede", "pelle fodera (vitello) 0,8 mm", 0.8, 0, COL_FODERA, 2),
    ("linguetta", "Linguetta", "vitello box 1,4 mm", 1.4, 1, COL_PELLE, 2),
    ("fodera_quartiere_esterno", "Fodera quartiere esterno", "pelle fodera (vitello) 0,8 mm", 0.8, 2, COL_FODERA, 2),
    ("fodera_quartiere_interno", "Fodera quartiere interno", "pelle fodera (vitello) 0,8 mm", 0.8, 2, COL_FODERA, 2),
    ("contrafforte", "Contrafforte", "termoplastico / cuoio 1,6 mm", 1.6, 3, COL_RINFORZO, 2),
    ("rinforzo_puntale", "Rinforzo puntale", "termoadesivo 1,0 mm", 1.0, 3, COL_RINFORZO, 2),
    ("quartiere_esterno", "Quartiere esterno", "vitello box 1,3 mm", 1.3, 4, COL_PELLE, 2),
    ("quartiere_interno", "Quartiere interno", "vitello box 1,3 mm", 1.3, 4, COL_PELLE, 2),
    ("mascherina", "Mascherina (avampiede)", "vitello box 1,3 mm", 1.3, 5, COL_PELLE, 2),
    ("puntale", "Puntale", "vitello box 1,3 mm", 1.3, 6, COL_PELLE, 2),
    ("bacchetta", "Bacchetta posteriore", "vitello box 1,3 mm", 1.3, 6, COL_PELLE, 2),
]

# Cuciture a vista: pezzo -> [(tipo bordo, distanze dal bordo in mm)]
CUCITURE = {
    "puntale": [("puntale", (1.6, 3.6))],
    "mascherina": [("mascherina", (1.6, 3.6))],
    "quartiere_esterno": [("bocca", (2.0,)), ("occhielleria", (2.0,))],
    "quartiere_interno": [("bocca", (2.0,)), ("occhielleria", (2.0,))],
    "bacchetta": [("bacchetta", (1.5,))],
}
PASSO_PUNTO, LUNGH_PUNTO = 3.2, 2.3   # ~3 punti/cm
COL_FILO = (120, 80, 50)

# Bordi scarniti (mm di rampa): lo spessore si annulla verso il bordo.
SCARNITURA = {"riporto_mascherina": 8.0, "riporto_puntale": 8.0, "fodera_cucitura": 6.0,
              "fodera_riporto": 6.0, "contrafforte": 10.0, "rinforzo_puntale": 10.0,
              "linguetta": 4.0, "linguetta_attacco": 4.0}

# Margini da aggiungere nello sviluppo 2D, per tipo di bordo.
TIPI_BORDO = {
    "filo_forma": ("margine di montaggio", MARGINE_MONTAGGIO),
    "bocca": ("bordo a vista (bocca)", 0.0),
    "cucitura_posteriore": ("cucitura posteriore accostata (zig-zag)", 0.0),
    "occhielleria": ("bordo a vista (occhielleria)", 0.0),
    "centro_sotto_mascherina": ("incontro quartieri sotto mascherina (già incluso)", 0.0),
    "mascherina": ("bordo a vista sopra i quartieri", 0.0),
    "riporto_mascherina": ("riporto sotto mascherina (già incluso)", 0.0),
    "puntale": ("bordo a vista sopra la mascherina", 0.0),
    "riporto_puntale": ("riporto sotto puntale (già incluso)", 0.0),
    "bacchetta": ("bordo a vista sopra i quartieri", 0.0),
    "linguetta": ("bordo libero linguetta", 0.0),
    "linguetta_attacco": ("attacco sotto mascherina (già incluso)", 0.0),
    "fodera_cucitura": ("cucitura fodere (sormonto gia' incluso)", 0.0),
    "fodera_riporto": ("riporto fodera avampiede (già incluso)", 0.0),
    "contrafforte": ("bordo scarnito contrafforte", 0.0),
    "rinforzo_puntale": ("bordo scarnito rinforzo", 0.0),
    "sottopiede": ("contorno sottopiede", 0.0),
}


# --------------------------------------------------------------------------
# Forma e campi scalari
# --------------------------------------------------------------------------

def forma(n_stazioni=210, n_punti=128):
    """Superficie della forma con normali e girth (arco dal centro dorso)."""
    V, F = gf.genera(n_stazioni, n_punti, uniformita=0.7)
    N = trimesh.Trimesh(V, F, process=False).vertex_normals.copy()
    G = np.zeros(len(V))
    q = n_punti // 4
    for i in range(n_stazioni):
        anello = V[1 + i * n_punti: 1 + (i + 1) * n_punti]
        g = np.zeros(n_punti)
        # esterno: angolo crescente dal dorso (g<0); interno: decrescente (g>0)
        for verso, segno in ((1, -1.0), (-1, 1.0)):
            acc, prev = 0.0, q
            for k in range(1, n_punti // 2 + (1 if segno < 0 else 0)):
                j = (q + verso * k) % n_punti
                acc += np.linalg.norm(anello[j] - anello[prev])
                g[j] = segno * acc
                prev = j
        G[1 + i * n_punti: 1 + (i + 1) * n_punti] = g
    return Superficie(V, F, N, G)


def yc(x):
    return gf.pchip(gf.CENTRO, x)


def zfondo(x):
    return gf.pchip(gf.FONDO, x)


class Campi:
    """Funzioni campo (S -> valori, positivo = dentro il pezzo)."""

    def __init__(self, poly_filo):
        self.poly_filo = poly_filo
        self.c_bocca = spline(BOCCA)
        self.c_masch = spline(MASCHERINA)
        self.c_punt = np.array(PUNTALE, float)
        self.c_ce = spline(CONTRAFF_EST)
        self.c_ci = spline(CONTRAFF_INT)

    # -- bordo inferiore
    @staticmethod
    def filo(S):
        return S.N[:, 2] - FILO_NZ

    def montaggio(self, S):
        """Positivo sul fianco e fino a MARGINE_MONTAGGIO sotto il fondo."""
        fondo = S.N[:, 2] < FILO_NZ
        d = np.zeros(len(S.V))
        if fondo.any():
            pts = shapely.points(S.V[fondo, 0], S.V[fondo, 1])
            d[fondo] = shapely.distance(self.poly_filo.exterior, pts)
        return MARGINE_MONTAGGIO - d

    @staticmethod
    def sottopiede(S):
        return FILO_NZ - S.N[:, 2]

    # -- linee in vista laterale
    def _sd(self, S, c):
        return distanza_segnata(S.V[:, [0, 2]], c)

    def bocca(self, S):
        return self._sd(S, self.c_bocca) * -1  # sotto la linea bocca

    def mascherina(self, S, spost=0.0):
        return self._sd(S, self.c_masch) + spost

    def puntale(self, S, spost=0.0):
        return self._sd(S, self.c_punt) + spost

    def contrafforte(self, S):
        est = -self._sd(S, self.c_ce)
        inn = -self._sd(S, self.c_ci)
        return np.where(S.V[:, 1] - yc(S.V[:, 0]) < 0, est, inn)

    # -- coordinate trasversali
    @staticmethod
    def lato(S):
        """>0 interno, <0 esterno: cucitura posteriore (x<85) e centro dorso."""
        x = S.V[:, 0]
        return np.where(x < X_LATO, S.V[:, 1] - yc(x), S.G)

    def esterno(self, S):
        return -self.lato(S) - gf.pchip(SEMILUCE, S.V[:, 0])

    def interno(self, S):
        return self.lato(S) - gf.pchip(SEMILUCE, S.V[:, 0])

    @staticmethod
    def bacchetta(S):
        w = gf.pchip(BACCHETTA_LARGH, S.V[:, 2]) / 2
        return np.minimum(w - np.abs(S.V[:, 1] - yc(S.V[:, 0])), 40 - S.V[:, 0])

    @staticmethod
    def linguetta(S):
        x, g = S.V[:, 0], S.G
        w = gf.pchip(LINGUETTA_LARGH, x) / 2
        r = np.clip(np.abs(g) / w, 0, 1)
        cima = x - (LINGUETTA_CIMA + LINGUETTA_RAGGIO * (1 - np.sqrt(1 - r ** 2)))
        return np.minimum(w - np.abs(g), cima)

    @staticmethod
    def linguetta_attacco(S):
        return X_GOLA + LINGUETTA_SOTTO - S.V[:, 0]


def definizioni(C):
    """Pezzo -> lista di (tipo_bordo, campo). 'filo_forma' viene sostituito
    dal filo (camicia) o dal margine di montaggio (solido 3D)."""
    return {
        "sottopiede": [("sottopiede", C.sottopiede)],
        "puntale": [("filo_forma", None), ("puntale", C.puntale)],
        "mascherina": [("filo_forma", None), ("mascherina", C.mascherina),
                       ("riporto_puntale", lambda S: RIPORTO_PUNTALE - C.puntale(S))],
        "quartiere_esterno": [("filo_forma", None), ("bocca", C.bocca),
                              ("riporto_mascherina", lambda S: RIPORTO_MASCHERINA - C.mascherina(S)),
                              ("occhielleria", C.esterno)],
        "quartiere_interno": [("filo_forma", None), ("bocca", C.bocca),
                              ("riporto_mascherina", lambda S: RIPORTO_MASCHERINA - C.mascherina(S)),
                              ("occhielleria", C.interno)],
        "bacchetta": [("filo_forma", None), ("bocca", C.bocca), ("bacchetta", C.bacchetta)],
        "linguetta": [("linguetta", C.linguetta), ("linguetta_attacco", C.linguetta_attacco)],
        "fodera_avampiede": [("filo_forma", None),
                             ("fodera_riporto", lambda S: C.mascherina(S, ARRETRA_FODERA + RIPORTO_FODERA))],
        "fodera_quartiere_esterno": [("filo_forma", None), ("bocca", C.bocca),
                                     ("fodera_cucitura", lambda S: -C.mascherina(S, ARRETRA_FODERA)),
                                     ("occhielleria", C.esterno)],
        "fodera_quartiere_interno": [("filo_forma", None), ("bocca", C.bocca),
                                     ("fodera_cucitura", lambda S: -C.mascherina(S, ARRETRA_FODERA)),
                                     ("occhielleria", C.interno)],
        "contrafforte": [("filo_forma", None), ("contrafforte", C.contrafforte)],
        "rinforzo_puntale": [("filo_forma", None),
                             ("rinforzo_puntale", lambda S: C.puntale(S, OLTRE_PUNTALE_RINFORZO))],
    }


def campi_pezzo(defn, C, camicia):
    out = []
    for tipo, f in defn:
        if tipo == "filo_forma":
            f = C.filo if camicia else C.montaggio
        out.append((tipo, f))
    return out


# --------------------------------------------------------------------------
# Costruzione
# --------------------------------------------------------------------------

def contorno_filo(S):
    """Poligono in pianta del filo forma (contorno del fondo)."""
    fondo = ritaglia(S, [Campi.sottopiede])
    anelli = contorno_bordo(fondo)
    piu_lungo = max(anelli, key=len)
    return Polygon(fondo.V[piu_lungo, :2]).buffer(0), fondo.V[piu_lungo]


def sagoma_suola(n_punti=144):
    """Contorno in pianta della suola: sagoma della forma nella fascia bassa,
    allargata dello spessore tomaia + sporgenza (sporgenza variabile)."""
    lat, med = [], []
    for x in np.linspace(0.3, gf.LUNGHEZZA_BASE - 0.3, 600):
        y, z = gf.anello(gf.profili(np.array(x)), 720)
        m = z < zfondo(x) + 18
        if m.sum() < 2:
            continue
        lat.append((x, y[m].min()))
        med.append((x, y[m].max()))
    pts = np.array(lat + med[::-1])
    P = Polygon(pts).buffer(0).simplify(0.05)
    c = np.array(P.exterior.coords)[:-1]
    t = np.roll(c, -1, 0) - np.roll(c, 1, 0)
    n = np.column_stack([t[:, 1], -t[:, 0]])
    n /= np.linalg.norm(n, axis=1, keepdims=True)
    if Polygon(c + n * 1.0).area < P.area:
        n = -n
    c = c + n * gf.pchip(SPORGENZA, c[:, 0])[:, None]
    return Polygon(c).buffer(0).buffer(1.5).buffer(-1.5).simplify(0.05)


def _rampa(t):
    t = np.clip(t, 0.0, 1.0)
    return t * t * (3 - 2 * t)


def spessore_locale(S, campi, spessore):
    """Spessore del pezzo nei punti di S: pieno all'interno, scarnito a zero
    sui bordi di riporto, nullo fuori dal pezzo (con 1 mm di tolleranza)."""
    w = np.ones(len(S.V))
    for tipo, f in campi:
        v = f(S) * (10.0 if tipo == "sottopiede" else 1.0)
        if tipo in SCARNITURA:
            w *= _rampa(v / SCARNITURA[tipo])
        else:
            w *= _rampa(v + 1.0)
    return spessore * w


def strati(pezzi_vis, ranghi, spessori, campi_vis, nome):
    """Offset interno/esterno per vertice: somma degli spessori dei pezzi
    sottostanti (strato inferiore) piu' lo spessore proprio scarnito."""
    S = pezzi_vis[nome]
    interno = np.zeros(len(S.V))
    for altro, campi in campi_vis.items():
        if ranghi[altro] < ranghi[nome]:
            interno += spessore_locale(S, campi, spessori[altro])
    proprio = spessori[nome] * np.ones(len(S.V))
    for tipo, f in campi_vis[nome]:
        if tipo in SCARNITURA:
            proprio *= _rampa(f(S) / SCARNITURA[tipo])
    return interno, interno + np.maximum(proprio, 0.12)


def bordi_tipizzati(S, campi):
    """Segmenti di bordo della camicia raggruppati per tipo."""
    out = []
    valori = np.column_stack([np.abs(f(S)) for _, f in campi])
    for anello in contorno_bordo(S):
        tipi = []
        for a, b in zip(anello, np.roll(anello, -1)):
            k = int(np.argmin(np.maximum(valori[a], valori[b])))
            if campi[k][0] == "occhielleria":
                xm = S.V[[a, b], 0].mean()
                k = -1 if xm < X_LATO else (-2 if xm > X_GOLA else k)
            tipi.append(k)
        # raggruppa tratti consecutivi dello stesso tipo
        k0 = next((i for i in range(len(tipi)) if tipi[i] != tipi[i - 1]), 0)
        tipi = tipi[k0:] + tipi[:k0]
        idx = list(anello[k0:]) + list(anello[:k0]) + [anello[k0]]
        inizio = 0
        for i in range(1, len(tipi) + 1):
            if i == len(tipi) or tipi[i] != tipi[inizio]:
                nome = {-1: "cucitura_posteriore", -2: "centro_sotto_mascherina"}.get(
                    tipi[inizio], campi[tipi[inizio]][0] if tipi[inizio] >= 0 else "")
                out.append({"tipo": nome,
                            "descrizione": TIPI_BORDO[nome][0],
                            "margine_mm": TIPI_BORDO[nome][1],
                            "punti": np.round(S.V[idx[inizio:i + 1]], 2).tolist()})
                inizio = i
    return out


def quota_esterna(S, nome, ranghi, spessori, campi_vis):
    """Offset della faccia esterna del pezzo nei punti di S."""
    tot = np.zeros(len(S.V))
    for altro, campi in campi_vis.items():
        if ranghi[altro] < ranghi[nome]:
            tot += spessore_locale(S, campi, spessori[altro])
    proprio = spessori[nome] * np.ones(len(S.V))
    for tipo, f in campi_vis[nome]:
        if tipo in SCARNITURA:
            proprio *= _rampa(f(S) / SCARNITURA[tipo])
    return tot + proprio


def cuciture(nome, camicia, bordi, ranghi, spessori, campi_vis):
    """Punti di cucitura (scatolette) lungo i bordi a vista del pezzo."""
    from scipy.spatial import cKDTree
    albero = cKDTree(camicia.V)
    scatole = []
    for tipo, distanze in CUCITURE.get(nome, []):
        for b in (b for b in bordi if b["tipo"] == tipo):
            P = np.array(b["punti"])
            if len(P) < 3:
                continue
            L = np.concatenate([[0], np.cumsum(np.linalg.norm(np.diff(P, axis=0), axis=1))])
            if L[-1] < 8:
                continue
            for d in distanze:
                t = np.arange(PASSO_PUNTO / 2 + 1.0, L[-1] - 1.0, PASSO_PUNTO)
                Q = np.column_stack([np.interp(t, L, P[:, k]) for k in range(3)])
                T = np.column_stack([np.interp(t + 0.3, L, P[:, k]) - np.interp(t - 0.3, L, P[:, k])
                                     for k in range(3)])
                T /= np.linalg.norm(T, axis=1, keepdims=True)
                _, j = albero.query(Q)
                N = camicia.N[j]
                dentro = np.cross(N, T)
                Q = Q + dentro * d
                _, j = albero.query(Q)
                ok = np.linalg.norm(camicia.V[j] - Q, axis=1) < 1.5
                ps = Superficie(Q[ok], np.zeros((0, 3), int), camicia.N[j[ok]], camicia.G[j[ok]])
                h = quota_esterna(ps, nome, ranghi, spessori, campi_vis)
                for q, tt, n, hh in zip(ps.V, T[ok], ps.N, h):
                    u = np.cross(n, tt)
                    c = q + n * (hh + 0.12)
                    R = np.column_stack([tt * LUNGH_PUNTO, u * 0.6, n * 0.35])
                    scatole.append((c, R))
    if not scatole:
        return None
    base = trimesh.creation.box(extents=[1, 1, 1])
    V = np.concatenate([c + base.vertices @ R.T for c, R in scatole])
    F = np.concatenate([base.faces + 8 * i for i in range(len(scatole))])
    return trimesh.Trimesh(V, F, process=False)


def punto_su_anello(x, g, offset):
    """Punto della forma alla stazione x con girth g, spostato lungo la normale."""
    p = gf.profili(np.array(float(x)))
    y, z = gf.anello(p, 4000)
    P = np.column_stack([np.full_like(y, x), y, z])
    seg = np.linalg.norm(np.roll(P, -1, 0) - P, axis=1)
    q = 1000
    if g < 0:
        ordine = np.arange(q, q + 2001) % 4000
    else:
        ordine = np.arange(q, q - 2001, -1) % 4000
    arco = np.concatenate([[0], np.cumsum(seg[np.minimum(ordine[:-1], ordine[1:])])])
    j = ordine[np.searchsorted(arco, abs(g))]
    # normale nel piano della sezione
    t = P[(j + 1) % 4000] - P[j - 1]
    n = np.array([0, t[2], -t[1]])
    n /= np.linalg.norm(n)
    return P[j] + n * offset, n


def occhielli_e_lacci(spessore_sopra):
    """Fori occhielli (dischi scuri) e lacci a barrette dritte."""
    occhielli, lacci, posizioni = [], [], []
    for x in OCCHIELLI_X:
        g0 = gf.pchip(SEMILUCE, x) + OCCHIELLI_DAL_BORDO
        coppia = []
        for segno in (-1, 1):
            c, n = punto_su_anello(x, segno * g0, spessore_sopra)
            cil = trimesh.creation.cylinder(radius=OCCHIELLO_D / 2, height=0.5, sections=20)
            asse = trimesh.geometry.align_vectors([0, 0, 1], n)
            cil.apply_transform(asse)
            cil.apply_translation(c + n * 0.15)
            occhielli.append(cil)
            coppia.append(c)
            posizioni.append({"lato": "esterno" if segno < 0 else "interno",
                              "x": round(float(x), 1), "girth": round(float(segno * g0), 1),
                              "centro_su_forma": np.round(punto_su_anello(x, segno * g0, 0)[0], 2).tolist(),
                              "diametro_mm": OCCHIELLO_D})
        gg = np.linspace(-g0, g0, 25)
        alza = spessore_sopra + 1.3 - 1.6 * (np.abs(gg) / g0) ** 8
        percorso = [punto_su_anello(x, g, a)[0] for g, a in zip(gg, alza)]
        lacci.append(tubo(percorso, 1.1))
    return occhielli, lacci, posizioni


def costruisci():
    S = forma()
    poly_filo, filo3d = contorno_filo(S)
    C = Campi(poly_filo)
    defs = definizioni(C)

    camicie, vis, campi_vis, campi_cam = {}, {}, {}, {}
    for nome, d in defs.items():
        campi_cam[nome] = campi_pezzo(d, C, camicia=True)
        campi_vis[nome] = campi_pezzo(d, C, camicia=False)
        camicie[nome] = ritaglia(S, [f for _, f in campi_cam[nome]])
        vis[nome] = ritaglia(S, [f for _, f in campi_vis[nome]])

    ranghi = {p[0]: p[4] for p in PEZZI}
    spessori = {p[0]: p[3] for p in PEZZI}
    solidi = {}
    for nome in defs:
        a, b = strati(vis, ranghi, spessori, campi_vis, nome)
        solidi[nome] = guscio(vis[nome], a, b)

    filo_cuciture = {}
    for nome in CUCITURE:
        bordi = bordi_tipizzati(camicie[nome], campi_cam[nome])
        m = cuciture(nome, camicie[nome], bordi, ranghi, spessori, campi_vis)
        if m is not None:
            filo_cuciture[f"cuciture_{nome}"] = (m, COL_FILO)

    # Spessore totale sopra la forma nella zona occhielli.
    sopra = spessori["linguetta"] + spessori["fodera_quartiere_esterno"] + spessori["quartiere_esterno"]
    occhielli, lacci, pos_occhielli = occhielli_e_lacci(sopra)

    # Fondo: guardolo, suola, tacco.
    suola_poly = sagoma_suola()
    z_suola_sopra = lambda x, y: zfondo(x) - QUOTA_SUOLA
    z_suola_sotto = lambda x, y: zfondo(x) - QUOTA_SUOLA - SPESS_SUOLA
    suola = lastra(suola_poly, z_suola_sopra, z_suola_sotto)

    guard_poly = suola_poly.difference(poly_filo.buffer(-5))
    guardolo = lastra(guard_poly, lambda x, y: zfondo(x) - QUOTA_SUOLA + SPESS_GUARDOLO,
                      z_suola_sopra)

    z_terra = zfondo(np.linspace(150, 230, 200)).min() - QUOTA_SUOLA - SPESS_SUOLA
    tacco_poly = suola_poly.intersection(box(-100, -200, X_TACCO, 200))
    alzi = []
    for k in range(N_ALZI):
        def zs(x, y, k=k):
            top = z_suola_sotto(x, y)
            base = z_terra + SPESS_SOPRATACCO
            return base + (top - base) * (N_ALZI - k) / N_ALZI

        def zi(x, y, k=k):
            top = z_suola_sotto(x, y)
            base = z_terra + SPESS_SOPRATACCO
            return base + (top - base) * (N_ALZI - k - 1) / N_ALZI
        alzi.append(lastra(tacco_poly, zs, zi))
    sopratacco = lastra(tacco_poly, lambda x, y: np.full_like(x, z_terra + SPESS_SOPRATACCO),
                        lambda x, y: np.full_like(x, z_terra))

    fondo = {"guardolo": (guardolo, COL_BORDO_SUOLA),
             "suola": (suola, COL_BORDO_SUOLA),
             "sopratacco": (sopratacco, COL_GOMMA)}
    for k, a in enumerate(alzi):
        fondo[f"tacco_alzo_{k + 1}"] = (a, (110, 70, 40) if k % 2 else (95, 60, 34))
    accessori = {f"occhiello_{i + 1}": (m, (12, 8, 6)) for i, m in enumerate(occhielli)}
    accessori.update({f"laccio_{i + 1}": (m, (20, 14, 10)) for i, m in enumerate(lacci)})
    accessori.update(filo_cuciture)

    return dict(S=S, C=C, camicie=camicie, campi_cam=campi_cam, solidi=solidi,
                fondo=fondo, accessori=accessori, pos_occhielli=pos_occhielli,
                suola_poly=suola_poly, tacco_poly=tacco_poly, poly_filo=poly_filo,
                guard_poly=guard_poly, z_terra=float(z_terra))


def specchia(m):
    m = m.copy()
    m.apply_transform(np.diag([1, -1, 1, 1]))
    m.invert()
    return m


def scena(R, lato="dx"):
    sc = trimesh.Scene()
    colori = {p[0]: p[5] for p in PEZZI}
    elementi = [(n, m, colori[n]) for n, m in R["solidi"].items()]
    elementi += [(n, m, c) for n, (m, c) in R["fondo"].items()]
    elementi += [(n, m, c) for n, (m, c) in R["accessori"].items()]
    for n, m, c in elementi:
        m = specchia(m) if lato == "sx" else m.copy()
        m.visual = trimesh.visual.ColorVisuals(m, face_colors=list(c) + [255])
        sc.add_geometry(m, node_name=n, geom_name=n)
    return sc


def esporta(R, out, stl=False):
    os.makedirs(os.path.join(out, "camicie"), exist_ok=True)
    if stl:
        os.makedirs(os.path.join(out, "pezzi_3d"), exist_ok=True)
    info = {"modello": "Oxford uomo cap-toe, allacciatura chiusa, 5 occhielli",
            "forma": "forma_uomo_42_tacco25 (forma_3d)", "taglia": 42,
            "unita": "mm", "sistema_riferimento": "X tallone->punta, Y interno (piede destro), Z alto",
            "filo_forma": f"isolinea normale z = {FILO_NZ}",
            "margine_montaggio_mm": MARGINE_MONTAGGIO, "pezzi": [], "fondo": []}
    for nome, descr, mat, sp, rango, col, qta in PEZZI:
        cam = R["camicie"][nome]
        tm = cam.trimesh()
        tm.export(os.path.join(out, "camicie", f"{nome}.obj"))
        if stl:
            R["solidi"][nome].export(os.path.join(out, "pezzi_3d", f"{nome}.stl"))
        info["pezzi"].append({
            "nome": nome, "descrizione": descr, "materiale": mat,
            "spessore_mm": sp, "strato": rango, "quantita_paio": qta,
            "area_superficie_cm2": round(float(tm.area) / 100, 1),
            "camicia": f"camicie/{nome}.obj", "nodo_glb": nome,
            "bordi": bordi_tipizzati(cam, R["campi_cam"][nome]),
            "cuciture": [{"bordo": t, "distanze_dal_bordo_mm": list(d),
                          "punti_per_cm": round(10 / PASSO_PUNTO, 1)}
                         for t, d in CUCITURE.get(nome, [])],
        })
    info["occhielli"] = R["pos_occhielli"]
    for nome, poly, sp in (("suola", R["suola_poly"], SPESS_SUOLA),
                           ("guardolo", R["guard_poly"], SPESS_GUARDOLO),
                           ("tacco_alzo", R["tacco_poly"], None),
                           ("sopratacco", R["tacco_poly"], SPESS_SOPRATACCO)):
        info["fondo"].append({"nome": nome, "spessore_mm": sp,
                              "contorno_pianta": np.round(np.array(poly.exterior.coords), 2).tolist()})
    info["altezza_tacco_mm"] = round(float(zfondo(5.0) - QUOTA_SUOLA - SPESS_SUOLA - R["z_terra"]), 1)
    with open(os.path.join(out, "pezzi.json"), "w") as f:
        json.dump(info, f, indent=1)
    for lato in ("dx", "sx"):
        scena(R, lato).export(os.path.join(out, f"oxford_42_{lato}.glb"))
    return info


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--stl", action="store_true", help="esporta anche un STL per pezzo")
    ap.add_argument("--out", default=os.path.join(QUI, "output"))
    args = ap.parse_args()
    R = costruisci()
    for nome, m in R["solidi"].items():
        assert m.is_watertight and m.is_winding_consistent and m.volume > 0, nome
    info = esporta(R, args.out, stl=args.stl)
    for p in info["pezzi"]:
        tipi = sorted({b["tipo"] for b in p["bordi"]})
        print(f'{p["nome"]:28s} {p["area_superficie_cm2"]:7.1f} cm2  bordi: {", ".join(tipi)}')
    print("altezza tacco", info["altezza_tacco_mm"])
