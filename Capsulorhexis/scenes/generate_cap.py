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
TARGET_EDGE = 0.30     # desired triangle edge length -> THE resolution knob
MIN_SEG = 6            # minimum segments on the innermost ring

# --- pre-slit tear circle ---------------------------------------------------
TEAR_ENABLE = True
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


def _build_slit():
    """Raw cap, then duplicate the TEAR_RING vertices and route outer faces to the copies.

    Returns verts, faces, plus:
      stitch  : list of (inner_vid, outer_vid) coincident pairs -> stitch springs
      central : sorted vertex ids of the central disc (rings 0..TEAR_RING inner side)
    """
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
               "cap on oblate lens A=%g C=%g R=%.3f targetEdge=%g tearRing=%d r=%.2f "
               "stitches=%d central=%d"
               % (A, C, R, TARGET_EDGE, TEAR_RING, TEAR_RING_RADIUS, len(stitch), len(central)))
    lv, lf = build_lens()
    _write_obj(os.path.join(here, "lens.obj"), lv, lf,
               "oblate lens: A=%g C=%g (flatness %.2f)" % (A, C, C / A))
    print("cap.obj : %d verts %d tris | tearRing=%d at r=%.2f, %d stitches, "
          "%d central-disc nodes" % (len(cv), len(cf), TEAR_RING, TEAR_RING_RADIUS,
                                     len(stitch), len(central)))
    print("lens.obj: %d verts %d tris | oblate A=%g C=%g" % (len(lv), len(lf), A, C))


if __name__ == "__main__":
    main()
