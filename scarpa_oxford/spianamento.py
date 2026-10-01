"""Sviluppo in piano (spianamento) delle camicie dei pezzi.

LSCM (mappa conforme ai minimi quadrati) come partenza, poi ARAP
(as-rigid-as-possible, locale/globale) per conservare le lunghezze:
e' il comportamento che serve per un cartamodello di pelle.
"""

import numpy as np
import scipy.sparse as sp
import scipy.sparse.linalg as spla
import trimesh


def pulisci(m):
    """Fonde vertici quasi coincidenti, toglie triangoli degeneri e frammenti."""
    m = trimesh.Trimesh(m.vertices.copy(), m.faces.copy(), process=False)
    m.merge_vertices(digits_vertex=2)
    m.update_faces(m.nondegenerate_faces(height=1e-4))
    m.remove_unreferenced_vertices()
    parti = m.split(only_watertight=False)
    if len(parti) > 1:
        m = max(parti, key=lambda p: p.area)
    return m


def _locali(V, F):
    """Coordinate 2D isometriche di ogni triangolo nel suo piano (3 x 2)."""
    p0, p1, p2 = V[F[:, 0]], V[F[:, 1]], V[F[:, 2]]
    e1, e2 = p1 - p0, p2 - p0
    l1 = np.linalg.norm(e1, axis=1)
    ex = e1 / l1[:, None]
    n = np.cross(e1, e2)
    n /= np.linalg.norm(n, axis=1, keepdims=True)
    ey = np.cross(n, ex)
    X = np.zeros((len(F), 3, 2))
    X[:, 1, 0] = l1
    X[:, 2, 0] = (e2 * ex).sum(1)
    X[:, 2, 1] = (e2 * ey).sum(1)
    return X


def lscm(V, F, bordo):
    n = len(V)
    X = _locali(V, F)
    z = X[..., 0] + 1j * X[..., 1]
    W = np.stack([z[:, 2] - z[:, 1], z[:, 0] - z[:, 2], z[:, 1] - z[:, 0]], 1)
    dT = np.abs((W[:, 2].conj() * -W[:, 1]).imag)  # doppia area
    W = W / np.sqrt(np.maximum(dT, 1e-12))[:, None]
    righe = np.repeat(np.arange(len(F)), 3)
    Mr = sp.csr_matrix((W.real.ravel(), (righe, F.ravel())), shape=(len(F), n))
    Mi = sp.csr_matrix((W.imag.ravel(), (righe, F.ravel())), shape=(len(F), n))
    A = sp.vstack([sp.hstack([Mr, -Mi]), sp.hstack([Mi, Mr])]).tocsc()
    # due vertici di bordo lontani fissati
    B = V[bordo]
    d = np.linalg.norm(B[:, None] - B[None], axis=2)
    i, j = np.unravel_index(np.argmax(d), d.shape)
    a, b = bordo[i], bordo[j]
    fissi = np.array([a, b, a + n, b + n])
    valori = np.array([0.0, d[i, j], 0.0, 0.0])
    liberi = np.setdiff1d(np.arange(2 * n), fissi)
    Af, Ap = A[:, liberi], A[:, fissi]
    x = spla.spsolve((Af.T @ Af).tocsc(), -(Af.T @ (Ap @ valori)))
    out = np.zeros(2 * n)
    out[liberi], out[fissi] = x, valori
    return np.column_stack([out[:n], out[n:]])


def arap(V, F, uv0, iterazioni=60, vincolati=None, peso_bordo=300.0):
    """ARAP con pesi cotangenti. Gli spigoli di bordo tra vertici 'vincolati'
    (bordi da cucire) pesano molto di piu': la loro lunghezza si conserva e la
    distorsione va verso l'interno e verso il margine di montaggio."""
    n = len(V)
    X = _locali(V, F)
    lati = [(1, 2, 0), (2, 0, 1), (0, 1, 2)]  # (i, j, opposto)
    w = np.zeros((len(F), 3))
    chiavi = np.sort(np.concatenate([F[:, [i, j]] for i, j, _ in lati]), axis=1)
    _, inv, cnt = np.unique(chiavi, axis=0, return_inverse=True, return_counts=True)
    di_bordo = (cnt[inv.ravel()] == 1).reshape(3, len(F)).T
    for e, (i, j, k) in enumerate(lati):
        a, b = X[:, i] - X[:, k], X[:, j] - X[:, k]
        cr = np.abs(a[:, 0] * b[:, 1] - a[:, 1] * b[:, 0])
        w[:, e] = np.clip((a * b).sum(1) / np.maximum(cr, 1e-12), 1e-2, 50.0)
    if vincolati is not None:
        for e, (i, j, _) in enumerate(lati):
            forte = di_bordo[:, e] & vincolati[F[:, i]] & vincolati[F[:, j]]
            w[forte, e] = w[forte, e] * peso_bordo + 1.0
    I, J, D = [], [], []
    for e, (i, j, _) in enumerate(lati):
        vi, vj = F[:, i], F[:, j]
        I += [vi, vj, vi, vj]
        J += [vi, vj, vj, vi]
        D += [w[:, e], w[:, e], -w[:, e], -w[:, e]]
    L = sp.csr_matrix((np.concatenate(D), (np.concatenate(I), np.concatenate(J))), shape=(n, n))
    fisso = 0
    liberi = np.arange(1, n)
    risolvi = spla.factorized(L[liberi][:, liberi].tocsc())
    Lfp = L[liberi][:, [fisso]]
    uv = uv0.copy()
    for _ in range(iterazioni):
        # locale: rotazione ottimale per triangolo
        S = np.zeros((len(F), 2, 2))
        for e, (i, j, _) in enumerate(lati):
            du = uv[F[:, i]] - uv[F[:, j]]
            dx = X[:, i] - X[:, j]
            S += w[:, e, None, None] * du[:, :, None] * dx[:, None, :]
        U, _, Vt = np.linalg.svd(S)
        R = U @ Vt
        neg = np.linalg.det(R) < 0
        U[neg, :, 1] *= -1
        R = U @ Vt
        # globale
        b = np.zeros((n, 2))
        for e, (i, j, _) in enumerate(lati):
            r = np.einsum("tab,tb->ta", R, X[:, i] - X[:, j]) * w[:, e, None]
            np.add.at(b, F[:, i], r)
            np.add.at(b, F[:, j], -r)
        bl = b[liberi] - Lfp @ uv[[fisso]]
        uv[liberi, 0] = risolvi(bl[:, 0])
        uv[liberi, 1] = risolvi(bl[:, 1])
    return uv


def spiana(m, punti_cuciture=None):
    """Restituisce (mesh pulita, coordinate 2D) con orientamento conservato.
    punti_cuciture: punti 3D dei bordi di cui conservare la lunghezza."""
    from scipy.spatial import cKDTree
    m = pulisci(m)
    bordo = np.unique(m.edges[trimesh.grouping.group_rows(m.edges_sorted, require_count=1)])
    vincolati = None
    if punti_cuciture is not None and len(punti_cuciture):
        d, j = cKDTree(np.asarray(punti_cuciture)).query(m.vertices)
        vincolati = d < 0.05
    uv = lscm(m.vertices, m.faces, bordo)
    uv = arap(m.vertices, m.faces, uv, vincolati=vincolati)
    a = uv[m.faces]
    area = ((a[:, 1, 0] - a[:, 0, 0]) * (a[:, 2, 1] - a[:, 0, 1])
            - (a[:, 2, 0] - a[:, 0, 0]) * (a[:, 1, 1] - a[:, 0, 1])).sum()
    if area < 0:  # deve restare la vista dal lato esterno della forma
        uv[:, 1] *= -1
    return m, uv


def distorsione(m, uv):
    """Errore di lunghezza sugli spigoli e rapporto d'area 2D/3D."""
    e = m.edges_unique
    l3 = np.linalg.norm(m.vertices[e[:, 0]] - m.vertices[e[:, 1]], axis=1)
    l2 = np.linalg.norm(uv[e[:, 0]] - uv[e[:, 1]], axis=1)
    ok = l3 > 0.3
    err = np.abs(l2[ok] - l3[ok]) / l3[ok]
    a = uv[m.faces]
    a2 = 0.5 * np.abs((a[:, 1, 0] - a[:, 0, 0]) * (a[:, 2, 1] - a[:, 0, 1])
                      - (a[:, 2, 0] - a[:, 0, 0]) * (a[:, 1, 1] - a[:, 0, 1])).sum()
    return {"errore_lunghezze_medio_pct": round(100 * float(np.average(err, weights=l3[ok])), 2),
            "errore_lunghezze_p95_pct": round(100 * float(np.percentile(err, 95)), 2),
            "rapporto_area_2d_3d": round(float(a2 / m.area), 4)}


def mappa(m, uv, punti):
    """Porta punti 3D (sulla camicia) nel piano: punto piu' vicino + baricentriche."""
    punti = np.asarray(punti, float)
    cp, dist, tri = trimesh.proximity.closest_point(m, punti)
    bc = trimesh.triangles.points_to_barycentric(m.triangles[tri], cp)
    return np.einsum("ij,ijk->ik", bc, uv[m.faces[tri]]), dist


def jacobiani(m, uv):
    """Per faccia: matrice 2x3 che porta direzioni 3D tangenti nel piano."""
    P = m.vertices[m.faces]
    Q = uv[m.faces]
    E = np.stack([P[:, 1] - P[:, 0], P[:, 2] - P[:, 0]], 2)   # 3x2
    G = np.stack([Q[:, 1] - Q[:, 0], Q[:, 2] - Q[:, 0]], 2)   # 2x2
    Ep = np.linalg.pinv(E)                                      # 2x3
    return G @ Ep, m.area_faces
