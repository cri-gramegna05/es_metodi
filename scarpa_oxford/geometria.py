"""Strumenti geometrici per costruire la calzatura sulla forma.

- Superficie: mesh triangolare con attributi per vertice (normale, girth).
- taglia_iso: ritaglio esatto di una superficie lungo l'isolinea f=0.
- guscio: solido a spessore variabile da una porzione di superficie.
- lastra: solido tra due superfici z(x, y) su un contorno piano.
- tubo: solido tubolare lungo una polilinea (lacci).
"""

import numpy as np
import shapely
import trimesh
from shapely.geometry import Polygon


class Superficie:
    """Mesh con normali e coordinata di girth per vertice."""

    def __init__(self, V, F, N, G):
        self.V = np.asarray(V, float)
        self.F = np.asarray(F, np.int64)
        self.N = np.asarray(N, float)
        self.G = np.asarray(G, float)

    def copia(self):
        return Superficie(self.V.copy(), self.F.copy(), self.N.copy(), self.G.copy())

    def trimesh(self):
        return trimesh.Trimesh(self.V, self.F, process=False)

    def compatta(self):
        usati = np.unique(self.F)
        mappa = -np.ones(len(self.V), np.int64)
        mappa[usati] = np.arange(len(usati))
        return Superficie(self.V[usati], mappa[self.F], self.N[usati], self.G[usati])

    def bordi(self):
        """Spigoli di bordo (usati da una sola faccia), orientati come le facce."""
        e = np.concatenate([self.F[:, [0, 1]], self.F[:, [1, 2]], self.F[:, [2, 0]]])
        k = np.sort(e, axis=1)
        _, inv, cnt = np.unique(k, axis=0, return_inverse=True, return_counts=True)
        return e[cnt[inv.ravel()] == 1]


def taglia_iso(S, s):
    """Tiene la parte di S con s>0, tagliando i triangoli lungo s=0."""
    s = np.where(np.abs(s) < 1e-4, 1e-4, s)  # evita vertici coincidenti
    pos = s > 0
    F = S.F
    n_pos = pos[F].sum(1)
    tieni = F[n_pos == 3]
    split = n_pos[(n_pos == 1) | (n_pos == 2)]
    Fs = F[(n_pos == 1) | (n_pos == 2)]
    if len(Fs) == 0:
        return Superficie(S.V, tieni, S.N, S.G).compatta()

    # Ruota ogni faccia mettendo per primo il vertice "dispari".
    dispari = np.where(split[:, None] == 1, pos[Fs], ~pos[Fs])
    k = np.argmax(dispari, axis=1)
    idx = (k[:, None] + np.arange(3)) % 3
    R = np.take_along_axis(Fs, idx, axis=1)
    a, b, c = R[:, 0], R[:, 1], R[:, 2]

    # Nuovi vertici sugli spigoli a-b e a-c (condivisi tra facce adiacenti).
    spigoli = np.concatenate([np.stack([a, b], 1), np.stack([a, c], 1)])
    chiavi = np.sort(spigoli, axis=1)
    uniche, inv = np.unique(chiavi, axis=0, return_inverse=True)
    inv = inv.ravel()
    p, q = uniche[:, 0], uniche[:, 1]
    t = (s[p] / (s[p] - s[q]))[:, None]
    nV = S.V[p] + t * (S.V[q] - S.V[p])
    nN = S.N[p] + t * (S.N[q] - S.N[p])
    nN /= np.linalg.norm(nN, axis=1, keepdims=True)
    nG = S.G[p] + t[:, 0] * (S.G[q] - S.G[p])
    base = len(S.V)
    pab = base + inv[: len(a)]
    pac = base + inv[len(a):]

    uno = split == 1
    t1 = np.stack([a, pab, pac], 1)[uno]
    due = ~uno
    t2 = np.stack([pab, b, c], 1)[due]
    t3 = np.stack([pab, c, pac], 1)[due]
    out = Superficie(np.vstack([S.V, nV]), np.vstack([tieni, t1, t2, t3]),
                     np.vstack([S.N, nN]), np.concatenate([S.G, nG]))
    return out.compatta()


def ritaglia(S, campi):
    """Applica in sequenza i campi (funzioni S -> valori); tiene f>0 per tutti."""
    for f in campi:
        S = taglia_iso(S, f(S))
        if len(S.F) == 0:
            break
    return S


def guscio(S, interno, esterno):
    """Solido chiuso tra S + interno*N e S + esterno*N (offset per vertice)."""
    Vi = S.V + S.N * interno[:, None]
    Ve = S.V + S.N * esterno[:, None]
    n = len(S.V)
    facce = [S.F + n, S.F[:, ::-1]]
    b = S.bordi()
    facce.append(np.stack([b[:, 0], b[:, 1], b[:, 1] + n], 1))
    facce.append(np.stack([b[:, 0], b[:, 1] + n, b[:, 0] + n], 1))
    return trimesh.Trimesh(np.vstack([Vi, Ve]), np.vstack(facce), process=True)


def spline(punti, n=300):
    """Catmull-Rom centripeta per una polilinea di controllo 2D/3D."""
    P = np.asarray(punti, float)
    P = np.vstack([2 * P[0] - P[1], P, 2 * P[-1] - P[-2]])
    out = []
    for i in range(1, len(P) - 2):
        p0, p1, p2, p3 = P[i - 1], P[i], P[i + 1], P[i + 2]
        t0 = 0.0
        t1 = t0 + np.linalg.norm(p1 - p0) ** 0.5
        t2 = t1 + np.linalg.norm(p2 - p1) ** 0.5
        t3 = t2 + np.linalg.norm(p3 - p2) ** 0.5
        m = max(2, n // (len(P) - 3))
        for t in np.linspace(t1, t2, m, endpoint=False):
            a1 = (t1 - t) / (t1 - t0) * p0 + (t - t0) / (t1 - t0) * p1
            a2 = (t2 - t) / (t2 - t1) * p1 + (t - t1) / (t2 - t1) * p2
            a3 = (t3 - t) / (t3 - t2) * p2 + (t - t2) / (t3 - t2) * p3
            b1 = (t2 - t) / (t2 - t0) * a1 + (t - t0) / (t2 - t0) * a2
            b2 = (t3 - t) / (t3 - t1) * a2 + (t - t1) / (t3 - t1) * a3
            out.append((t2 - t) / (t2 - t1) * b1 + (t - t1) / (t2 - t1) * b2)
    out.append(P[-2])
    return np.array(out)


def distanza_segnata(P, C):
    """Distanza segnata 2D dei punti P dalla polilinea C (positiva a sinistra)."""
    A, B = C[:-1], C[1:]
    AB = B - A
    L2 = (AB ** 2).sum(1)
    out = np.empty(len(P))
    for i0 in range(0, len(P), 4000):
        Q = P[i0:i0 + 4000]
        AP = Q[:, None, :] - A[None]
        t = np.clip((AP * AB[None]).sum(2) / L2[None], 0, 1)
        D = AP - t[..., None] * AB[None]
        d2 = (D ** 2).sum(2)
        k = np.argmin(d2, axis=1)
        r = np.arange(len(Q))
        cr = AB[k, 0] * AP[r, k, 1] - AB[k, 1] * AP[r, k, 0]
        out[i0:i0 + 4000] = np.sqrt(d2[r, k]) * np.where(cr >= 0, 1, -1)
    return out


def lastra(poligono, z_sopra, z_sotto, area_max=25.0):
    """Solido tra z_sotto(x,y) e z_sopra(x,y) sul contorno piano dato."""
    v2, f = trimesh.creation.triangulate_polygon(
        poligono, triangle_args=f"pq28a{area_max}Y", engine="triangle")
    n = len(v2)
    zs, zi = z_sopra(v2[:, 0], v2[:, 1]), z_sotto(v2[:, 0], v2[:, 1])
    V = np.vstack([np.column_stack([v2, zs]), np.column_stack([v2, zi])])
    S = Superficie(v2, f, v2, v2[:, 0])
    b = S.bordi()
    facce = [f, f[:, ::-1] + n,
             np.stack([b[:, 1], b[:, 0], b[:, 0] + n], 1),
             np.stack([b[:, 1], b[:, 0] + n, b[:, 1] + n], 1)]
    m = trimesh.Trimesh(V, np.vstack(facce), process=True)
    if m.volume < 0:
        m.invert()
    return m


def tubo(punti, raggio, lati=10):
    """Tubo chiuso lungo una polilinea 3D (trasporto parallelo della sezione)."""
    P = np.asarray(punti, float)
    T = np.gradient(P, axis=0)
    T /= np.linalg.norm(T, axis=1, keepdims=True)
    u = np.cross(T[0], [0, 0, 1.0] if abs(T[0, 2]) < 0.9 else [1.0, 0, 0])
    u /= np.linalg.norm(u)
    anelli = []
    a = np.linspace(0, 2 * np.pi, lati, endpoint=False)
    for i in range(len(P)):
        u = u - T[i] * (u @ T[i])
        u /= np.linalg.norm(u)
        w = np.cross(T[i], u)
        anelli.append(P[i] + raggio * (np.cos(a)[:, None] * u + np.sin(a)[:, None] * w))
    V = np.vstack(anelli + [P[:1], P[-1:]])
    F = []
    for i in range(len(P) - 1):
        for j in range(lati):
            p, q = i * lati + j, i * lati + (j + 1) % lati
            F += [[p, q, q + lati], [p, q + lati, p + lati]]
    c0, c1 = len(V) - 2, len(V) - 1
    k = (len(P) - 1) * lati
    for j in range(lati):
        F.append([c0, (j + 1) % lati, j])
        F.append([c1, k + j, k + (j + 1) % lati])
    m = trimesh.Trimesh(V, F, process=True)
    if m.volume < 0:
        m.invert()
    return m


def contorno_bordo(S):
    """Polilinee chiuse (indici vertice) dei bordi di una superficie."""
    b = S.bordi()
    succ = dict(zip(b[:, 0].tolist(), b[:, 1].tolist()))
    anelli, visti = [], set()
    for v0 in succ:
        if v0 in visti:
            continue
        anello, v = [], v0
        while v not in visti and v in succ:
            visti.add(v)
            anello.append(v)
            v = succ[v]
        anelli.append(np.array(anello))
    return anelli


def poligono_xy(punti):
    return shapely.make_valid(Polygon(punti[:, :2])).buffer(0)
