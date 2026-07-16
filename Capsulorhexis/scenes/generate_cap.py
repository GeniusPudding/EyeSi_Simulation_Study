"""Generate a LENS-like flattened ellipsoid + a circular membrane that covers its
UPPER HALF, both from the SAME analytic surface (so the membrane lies exactly flush).

The base is an OBLATE ellipsoid (flattened, like the lens), centred on the origin:

    x^2/A^2 + y^2/A^2 + z^2/C^2 = 1        with C < A   (C = how domed it is)

The membrane is parametrised by POLAR ANGLE v (not planar radius): rings run from the
pole (v = 0) out to CAP_ANGLE_DEG. At CAP_ANGLE_DEG = 90 the rim lands exactly on the
equator (z = 0), i.e. the membrane covers the ENTIRE upper half.

    P(v, u) = ( A sin v cos u , A sin v sin u , C cos v )

Using the polar angle matters: near the equator the surface turns vertical, so spacing
rings by planar radius would give hopelessly stretched triangles there.

Run:  py -3.12 scenes/generate_cap.py   ->  cap.obj (membrane) + lens.obj (base)
"""
import math
import os

# --- base ellipsoid (the lens) ----------------------------------------------
A = 7.0        # semi-axis in x and y
C = 1.75       # semi-axis in z. HALVED (was 3.5) -> half the dome/curvature.
               # Smaller C = flatter lens. C/A is the flatness ratio.

# --- membrane ---------------------------------------------------------------
CAP_ANGLE_DEG = 90.0   # 90 = cover the WHOLE upper half (rim on the equator, z=0)
N = 12         # rings from pole to rim
M = 72         # angular divisions

# base mesh tessellation (fine, so the membrane sits flush with no faceting gap)
BASE_U = 96
BASE_V = 48

Z0 = 0.0                                   # ellipsoid centred on the origin
CAP_ANGLE = math.radians(CAP_ANGLE_DEG)
R = A * math.sin(CAP_ANGLE)                # planar radius the membrane rim reaches
RIM_Z = C * math.cos(CAP_ANGLE) + Z0       # height of the rim (0 when angle = 90)
CAP_HEIGHT = (C + Z0) - RIM_Z              # pole height above the rim


def surface(v, u):
    """A point on the ellipsoid at polar angle v, azimuth u."""
    return (A * math.sin(v) * math.cos(u),
            A * math.sin(v) * math.sin(u),
            C * math.cos(v) + Z0)


def build_cap():
    verts = [surface(0.0, 0.0)]                       # index 0 = pole
    for i in range(1, N + 1):
        v = CAP_ANGLE * i / N                         # rings by POLAR ANGLE
        for j in range(M):
            u = 2.0 * math.pi * j / M
            verts.append(surface(v, u))

    def idx(ring, j):
        return 1 + (ring - 1) * M + (j % M)

    faces = []
    for j in range(M):                                # fan: pole -> ring 1
        faces.append((0, idx(1, j), idx(1, j + 1)))
    for ring in range(1, N):
        for j in range(M):
            a, b = idx(ring, j), idx(ring, j + 1)
            c, d = idx(ring + 1, j), idx(ring + 1, j + 1)
            faces.append((a, c, d))
            faces.append((a, d, b))
    return verts, faces


def build_lens():
    """The full oblate ellipsoid, finely tessellated."""
    verts = []
    for iv in range(BASE_V + 1):
        v = math.pi * iv / BASE_V
        for iu in range(BASE_U):
            u = 2.0 * math.pi * iu / BASE_U
            verts.append(surface(v, u))

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
    return list(range(1 + (N - 1) * M, N * M + 1))


def _write_obj(path, verts, faces, header):
    with open(path, "w") as f:
        f.write("# %s\n" % header)
        for v in verts:
            f.write("v %.6f %.6f %.6f\n" % v)
        for t in faces:
            f.write("f %d %d %d\n" % (t[0] + 1, t[1] + 1, t[2] + 1))


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    cv, cf = build_cap()
    _write_obj(os.path.join(here, "cap.obj"), cv, cf,
               "membrane covering %.0fdeg of an oblate lens: A=%g C=%g R=%.3f capH=%.3f"
               % (CAP_ANGLE_DEG, A, C, R, CAP_HEIGHT))
    lv, lf = build_lens()
    _write_obj(os.path.join(here, "lens.obj"), lv, lf,
               "oblate lens: A=%g C=%g (flatness %.2f)" % (A, C, C / A))
    print("cap.obj : %d verts %d tris | covers %.0f deg -> rim radius R=%.3f at z=%.3f, "
          "pole height=%.3f" % (len(cv), len(cf), CAP_ANGLE_DEG, R, RIM_Z, CAP_HEIGHT))
    print("lens.obj: %d verts %d tris | oblate A=%g C=%g, flatness C/A=%.2f"
          % (len(lv), len(lf), A, C, C / A))


if __name__ == "__main__":
    main()
