"""Generate a LENS-like flattened ellipsoid + a circular membrane covering its UPPER
HALF, both from the SAME analytic surface (so the membrane lies exactly flush).

    x^2/A^2 + y^2/A^2 + z^2/C^2 = 1        C < A  (oblate = flattened, like the lens)

The membrane is built with ADAPTIVE concentric rings: ring i sits at polar angle v_i and
its segment count M_i is proportional to that ring's radius, so every triangle is roughly
TARGET_EDGE across.

Why not a fixed M for every ring (the obvious way)? Because near the pole the ring radius
goes to 0, so a fixed M crams all M triangles into a vanishing circle and produces
SLIVERS: measured aspect ratio 11.5 and edges 0.08 vs a 0.63 median. Sliver triangles
wreck the conditioning of the stiffness matrix, the CG solver stops converging, and the
membrane explodes when you yank it with the mouse. Refining a fixed-M mesh makes the pole
slivers twice as bad. Scaling M with radius keeps triangles near-equilateral everywhere
and removes the pole singularity.

Run:  py -3.12 scenes/generate_cap.py   ->  cap.obj (membrane) + lens.obj (base)
"""
import math
import os

# --- base ellipsoid (the lens) ----------------------------------------------
A = 7.0        # semi-axis in x and y
C = 1.5       # semi-axis in z (smaller = flatter lens)

# --- membrane ---------------------------------------------------------------
CAP_ANGLE_DEG = 80.0   # 90 = cover the WHOLE upper half (rim on the equator, z=0)
TARGET_EDGE = 0.30     # desired triangle edge length -> THE resolution knob.
                       # 0.60 = the old coarse mesh; 0.30 = ~4x the triangles.
MIN_SEG = 6            # minimum segments on the innermost ring

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
    """Arc length along the ellipse meridian from the pole to the cap rim."""
    n, s, prev = 2000, 0.0, None
    for i in range(n + 1):
        v = CAP_ANGLE * i / n
        p = (A * math.sin(v), C * math.cos(v))
        if prev is not None:
            s += math.hypot(p[0] - prev[0], p[1] - prev[1])
        prev = p
    return s


N = max(4, int(round(_meridian_arc() / TARGET_EDGE)))     # number of rings
RING_V = [CAP_ANGLE * i / N for i in range(N + 1)]         # ring polar angles
RING_M = [max(MIN_SEG, int(round(2.0 * math.pi * A * math.sin(v) / TARGET_EDGE)))
          for v in RING_V]                                 # segments per ring (adaptive)
RING_M[0] = 1                                              # the pole is a single vertex

R = A * math.sin(CAP_ANGLE)          # planar radius the rim reaches
RIM_Z = C * math.cos(CAP_ANGLE) + Z0
CAP_HEIGHT = (C + Z0) - RIM_Z
EDGE_LEN = TARGET_EDGE               # nominal edge; scenes size collision proximity off this


def build_cap():
    verts = [surface(0.0, 0.0)]      # index 0 = pole
    ring_base = [0]                  # first vertex index of each ring
    for i in range(1, N + 1):
        ring_base.append(len(verts))
        v, mi = RING_V[i], RING_M[i]
        for j in range(mi):
            verts.append(surface(v, 2.0 * math.pi * j / mi))

    faces = []
    # fan: pole -> ring 1
    m1 = RING_M[1]
    for j in range(m1):
        faces.append((0, ring_base[1] + j, ring_base[1] + (j + 1) % m1))

    # zipper between consecutive rings that may have different segment counts
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
    return verts, faces, ring_base


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


def rim_indices():
    """0-based vertex ids of the membrane's outer ring."""
    _, _, ring_base = build_cap()
    return list(range(ring_base[N], ring_base[N] + RING_M[N]))


def _write_obj(path, verts, faces, header):
    with open(path, "w") as f:
        f.write("# %s\n" % header)
        for v in verts:
            f.write("v %.6f %.6f %.6f\n" % v)
        for t in faces:
            f.write("f %d %d %d\n" % (t[0] + 1, t[1] + 1, t[2] + 1))


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    cv, cf, _ = build_cap()
    _write_obj(os.path.join(here, "cap.obj"), cv, cf,
               "adaptive-ring membrane on oblate lens: A=%g C=%g R=%.3f targetEdge=%g"
               % (A, C, R, TARGET_EDGE))
    lv, lf = build_lens()
    _write_obj(os.path.join(here, "lens.obj"), lv, lf,
               "oblate lens: A=%g C=%g (flatness %.2f)" % (A, C, C / A))
    print("cap.obj : %d verts %d tris | rings=%d targetEdge=%g segs/ring: %d..%d"
          % (len(cv), len(cf), N, TARGET_EDGE, min(RING_M[1:]), max(RING_M)))
    print("lens.obj: %d verts %d tris | oblate A=%g C=%g" % (len(lv), len(lf), A, C))


if __name__ == "__main__":
    main()
