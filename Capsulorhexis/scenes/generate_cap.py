"""Generate a LENS-like flattened ellipsoid + a circular membrane covering its upper part,
both from the SAME analytic surface (so the membrane lies exactly flush).

    x^2/A^2 + y^2/A^2 + z^2/C^2 = 1        C < A  (oblate = flattened, like the lens)

The membrane uses ADAPTIVE concentric rings: ring i sits at polar angle v_i and its
segment count M_i is proportional to that ring's radius, so every triangle is roughly
TARGET_EDGE across and there is no sliver singularity at the pole (a fixed M would cram
all M triangles into a vanishing circle -> aspect ratio 11+).

PRE-SLIT for tearing (rung 1 of the tear ladder): if TEAR_ENABLE, the ring whose radius is
closest to TEAR_RADIUS is DOUBLED -- an inner copy used by the triangles inside the circle
(the central disc / capsulorhexis flap) and an outer copy used by the triangles outside
(the anchored rim). The two copies are coincident, so the mesh still looks continuous; the
scene stitches them with breakable springs. "Tearing the circle" = disabling those stitches
-> the central disc separates and can be lifted, deforming with the SAME physics as before.
This tears only the pre-designed circle; runtime splitting along an arbitrary path is a
later rung.

Run:  py -3.12 scenes/generate_cap.py   ->  cap.obj (membrane) + lens.obj (base)
"""
import math
import os

# --- base ellipsoid (the lens) ----------------------------------------------
A = 7.0        # semi-axis in x and y
C = 1.5        # semi-axis in z (smaller = flatter lens)

# --- membrane ---------------------------------------------------------------
CAP_ANGLE_DEG = 80.0   # 90 = cover the WHOLE upper half (rim on the equator, z=0)
import os as _os
# Desired triangle edge length -- THE resolution knob. Dequidt 2013 s4.3 notes that a
# linear element's stress does not represent the material "unless very fine meshes are
# used", so this is the parameter their own prescription points at.
TARGET_EDGE = float(_os.environ.get('CAP_EDGE', '0.30'))
MIN_SEG = 6            # minimum segments on the innermost ring

# --- pre-slit tear circle ---------------------------------------------------
# OFF by default: the doubled-vertex ring at TEAR_RADIUS is a pre-designed capsulorhexis
# tear circle, but its coincident copies read as a visible seam/crack in the membrane and
# show up as a spurious stress ring near r=TEAR_RADIUS in the heatmap. Re-enable with
# CAP_PRESLIT=1 when working on the scripted-tear rung (SCRIPTED_TEAR in cap_membrane.py).
TEAR_ENABLE = os.environ.get("CAP_PRESLIT", "0") == "1"
TEAR_RADIUS = 5.0      # the ring nearest this planar radius becomes the tear circle

# base mesh tessellation (fine, so the membrane sits flush with no faceting gap)
BASE_U = 128
BASE_V = 64

Z0 = 0.0
CAP_ANGLE = math.radians(CAP_ANGLE_DEG)


def surface(v, u):
    return (A * math.sin(v) * math.cos(u),
            A * math.sin(v) * math.sin(u),
            C * math.cos(v) + Z0)


def _meridian_arc():
    n, s, prev = 2000, 0.0, None
    for i in range(n + 1):
        v = CAP_ANGLE * i / n
        p = (A * math.sin(v), C * math.cos(v))
        if prev is not None:
            s += math.hypot(p[0] - prev[0], p[1] - prev[1])
        prev = p
    return s


N = max(4, int(round(_meridian_arc() / TARGET_EDGE)))     # number of rings
RING_V = [CAP_ANGLE * i / N for i in range(N + 1)]
RING_M = [max(MIN_SEG, int(round(2.0 * math.pi * A * math.sin(v) / TARGET_EDGE)))
          for v in RING_V]
RING_M[0] = 1                                              # the pole is a single vertex

# ring whose radius is closest to TEAR_RADIUS (kept strictly interior so an outer rim
# exists and a couple of rings inside it exist too)
_ring_radius = [A * math.sin(v) for v in RING_V]
TEAR_RING = min(range(2, N - 1), key=lambda i: abs(_ring_radius[i] - TEAR_RADIUS))
TEAR_RING_RADIUS = _ring_radius[TEAR_RING]

R = A * math.sin(CAP_ANGLE)          # planar radius the rim reaches
CAP_HEIGHT = (C + Z0) - (C * math.cos(CAP_ANGLE) + Z0)
EDGE_LEN = TARGET_EDGE
Z = Z0                               # legacy alias used by the scene


def _build_raw():
    """Build the un-slit cap: verts, faces, ring_base, ring_of (ring index per vertex)."""
    verts = [surface(0.0, 0.0)]
    ring_of = [0]
    ring_base = [0]
    for i in range(1, N + 1):
        ring_base.append(len(verts))
        v, mi = RING_V[i], RING_M[i]
        for j in range(mi):
            verts.append(surface(v, 2.0 * math.pi * j / mi))
            ring_of.append(i)

    faces = []
    m1 = RING_M[1]
    for j in range(m1):
        faces.append((0, ring_base[1] + j, ring_base[1] + (j + 1) % m1))
    for i in range(1, N):
        b0, n0 = ring_base[i], RING_M[i]
        b1, n1 = ring_base[i + 1], RING_M[i + 1]
        i0 = i1 = 0
        while i0 < n0 or i1 < n1:
            take_inner = (i1 >= n1) or (i0 < n0 and (i0 + 1) / n0 <= (i1 + 1) / n1)
            if take_inner:
                faces.append((b0 + i0 % n0, b1 + i1 % n1, b0 + (i0 + 1) % n0))
                i0 += 1
            else:
                faces.append((b0 + i0 % n0, b1 + i1 % n1, b1 + (i1 + 1) % n1))
                i1 += 1
    return verts, faces, ring_base, ring_of


# --- irregular triangulation ------------------------------------------------
# WHY THIS EXISTS. The concentric-ring mesh above numbers its vertices ring by ring, and
# every vertex of a ring sits at EXACTLY one radius. That hands a crack restricted to mesh
# edges a closed circular path at every radius, and it takes it: read out of a real session,
# 65% of the crack's steps were +-1 in vertex index (= the next vertex around the same ring)
# and one run of 37 vertices held radius 3.85 +- 0.000 while sweeping 356 degrees. A tear
# that traces a circle to three decimal places is not modelling anything -- it is reading the
# mesh's own symmetry back to us. Dequidt 2013 s4.3 names exactly this failure mode: the
# simple restrict-to-edges strategy makes propagation "highly dependent on the original mesh".
#
# The fix is to take the preferred direction away. Blue-noise (Poisson-disc) sample points in
# the planar disc, Delaunay them, then lift onto the ellipsoid: same target edge length, same
# roughly-equilateral elements, but no vertex numbering that follows a circle and no ring of
# co-radial edges to fall into. The rim stays an exact circle so the zonular anchoring is
# unchanged.
MESH_KIND = _os.environ.get("CAP_MESH", "irregular")
# Measured: Delaunay edges average 1/0.695 x the Poisson spacing (0.30 -> 0.432).
POISSON_CALIB = float(_os.environ.get("CAP_POISSON_CALIB", "0.695"))


def _poisson_disc(radius, spacing, rng):
    """Bridson blue-noise sampling of a disc of the given radius."""
    cell = spacing / math.sqrt(2.0)
    n = int(math.ceil(2.0 * radius / cell))
    grid = {}
    pts, active = [], []

    def add(p):
        pts.append(p); active.append(len(pts) - 1)
        grid[(int((p[0] + radius) / cell), int((p[1] + radius) / cell))] = len(pts) - 1

    def ok(p):
        if p[0] * p[0] + p[1] * p[1] > radius * radius:
            return False
        gx, gy = int((p[0] + radius) / cell), int((p[1] + radius) / cell)
        for dx in range(-2, 3):
            for dy in range(-2, 3):
                q = grid.get((gx + dx, gy + dy))
                if q is not None:
                    o = pts[q]
                    if (o[0] - p[0]) ** 2 + (o[1] - p[1]) ** 2 < spacing * spacing:
                        return False
        return True

    add((0.0, 0.0))
    while active:
        k = active[rng.randrange(len(active))]
        base, placed = pts[k], False
        for _ in range(30):
            a = rng.random() * 2.0 * math.pi
            d = spacing * (1.0 + rng.random())
            p = (base[0] + d * math.cos(a), base[1] + d * math.sin(a))
            if ok(p):
                add(p); placed = True; break
        if not placed:
            active.remove(k)
    return pts


def _build_irregular():
    """Blue-noise points + Delaunay, lifted onto the ellipsoid. Same signature as
    _build_raw(); ring_of is filled with the radial band index so callers that only use it
    to pick 'inner' vertices keep working."""
    from scipy.spatial import Delaunay          # noqa: F401  (setup.ps1 installs scipy)
    import random
    import numpy as np

    R_planar = A * math.sin(CAP_ANGLE)
    rng = random.Random(int(_os.environ.get("CAP_MESH_SEED", "20250825")))
    # The rim first, as an exact circle: the zonular anchoring and the peel rules both key on
    # r >= R_planar, and a blue-noise boundary would be ragged.
    nrim = max(24, int(round(2.0 * math.pi * R_planar / TARGET_EDGE)))
    rim = [(R_planar * math.cos(2.0 * math.pi * j / nrim),
            R_planar * math.sin(2.0 * math.pi * j / nrim)) for j in range(nrim)]
    # Interior points, kept clear of the rim ring so no sliver elements form against it.
    # Poisson-disc spacing is a MINIMUM separation, so the Delaunay edges it produces come
    # out longer than the parameter -- measured, spacing 0.30 gave a mean edge of 0.432.
    # Calibrate so the mesh actually lands on TARGET_EDGE and stays comparable, element for
    # element, with the ring mesh it replaces.
    spacing = TARGET_EDGE * POISSON_CALIB
    inner = [p for p in _poisson_disc(R_planar, spacing, rng)
             if math.hypot(p[0], p[1]) < R_planar - 0.75 * spacing]
    XY = np.array(rim + inner)
    tri = Delaunay(XY)
    faces = [tuple(int(i) for i in t) for t in tri.simplices]
    # Delaunay of a disc is convex, so every simplex is inside; only drop true slivers.
    keep = []
    for t in faces:
        a, b, c = XY[t[0]], XY[t[1]], XY[t[2]]
        if abs(np.cross(b - a, c - a)) > 1e-9:
            keep.append(t)
    faces = keep
    # Lift: planar radius -> polar angle v on the ellipsoid, azimuth preserved.
    verts, ring_of = [], []
    for x, y in XY:
        r = math.hypot(x, y)
        v = math.asin(min(1.0, r / A))
        u = math.atan2(y, x)
        verts.append(surface(v, u))
        ring_of.append(int(min(N, round(N * r / max(R_planar, 1e-9)))))
    ring_base = [0] * (N + 1)                  # meaningless here; kept for the signature
    return verts, faces, ring_base, ring_of


def _build_slit():
    """Raw cap, then duplicate the TEAR_RING vertices and route outer faces to the copies.

    Returns verts, faces, plus:
      stitch  : list of (inner_vid, outer_vid) coincident pairs -> stitch springs
      central : sorted vertex ids of the central disc (rings 0..TEAR_RING inner side)
    """
    if MESH_KIND == "irregular":
        verts, faces, ring_base, ring_of = _build_irregular()
    else:
        verts, faces, ring_base, ring_of = _build_raw()
    if not TEAR_ENABLE:
        return verts, faces, [], sorted(i for i, r in enumerate(ring_of) if r <= N)

    verts = [list(v) for v in verts]
    ring_of = list(ring_of)
    lo = ring_base[TEAR_RING]
    hi = lo + RING_M[TEAR_RING]
    dup = {}
    for v in range(lo, hi):                      # outer copy of each tear-ring vertex
        nv = len(verts)
        verts.append(list(verts[v]))
        ring_of.append(TEAR_RING)
        dup[v] = nv

    new_faces = []
    for f in faces:
        outer = max(ring_of[x] for x in f) > TEAR_RING     # this face is outside the cut
        nf = tuple(dup[x] if (outer and x in dup) else x for x in f)
        new_faces.append(nf)

    stitch = [(v, dup[v]) for v in range(lo, hi)]
    dup_set = set(dup.values())
    central = sorted(i for i in range(len(verts))
                     if ring_of[i] <= TEAR_RING and i not in dup_set)
    return verts, new_faces, stitch, central


def stitch_pairs():
    return _build_slit()[2]


def central_indices():
    return _build_slit()[3]


def build_lens():
    verts = []
    for iv in range(BASE_V + 1):
        v = math.pi * iv / BASE_V
        for iu in range(BASE_U):
            verts.append(surface(v, 2.0 * math.pi * iu / BASE_U))

    def idx(iv, iu):
        return iv * BASE_U + (iu % BASE_U)

    faces = []
    for iv in range(BASE_V):
        for iu in range(BASE_U):
            a, b = idx(iv, iu), idx(iv, iu + 1)
            c, d = idx(iv + 1, iu), idx(iv + 1, iu + 1)
            faces.append((a, c, d))
            faces.append((a, d, b))
    return verts, faces


def _write_obj(path, verts, faces, header):
    with open(path, "w") as f:
        f.write("# %s\n" % header)
        for v in verts:
            f.write("v %.6f %.6f %.6f\n" % tuple(v))
        for t in faces:
            f.write("f %d %d %d\n" % (t[0] + 1, t[1] + 1, t[2] + 1))


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    cv, cf, stitch, central = _build_slit()
    _write_obj(os.path.join(here, "cap.obj"), cv, cf,
               "cap on oblate lens A=%g C=%g R=%.3f targetEdge=%g mesh=%s tearRing=%d r=%.2f "
               "stitches=%d central=%d"
               % (A, C, R, TARGET_EDGE, MESH_KIND, TEAR_RING, TEAR_RING_RADIUS, len(stitch), len(central)))
    lv, lf = build_lens()
    _write_obj(os.path.join(here, "lens.obj"), lv, lf,
               "oblate lens: A=%g C=%g (flatness %.2f)" % (A, C, C / A))
    print("cap.obj : %d verts %d tris | tearRing=%d at r=%.2f, %d stitches, "
          "%d central-disc nodes" % (len(cv), len(cf), TEAR_RING, TEAR_RING_RADIUS,
                                     len(stitch), len(central)))
    print("lens.obj: %d verts %d tris | oblate A=%g C=%g" % (len(lv), len(lf), A, C))


if __name__ == "__main__":
    main()
