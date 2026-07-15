"""Generate a LENS-like flattened ellipsoid base + a circular membrane cap that lies
EXACTLY on its top surface.

Both meshes come from the SAME analytic surface, so the membrane sits perfectly flush
on the base (no floating gap). The base is an OBLATE ellipsoid (a bit flattened, like
the lens), not a full sphere:

    x^2/A^2 + y^2/A^2 + (z - Z0)^2 / C^2 = 1      with C < A  (flattened)

The membrane covers the top out to planar radius R (< A). Its surface is

    z(r) = C * sqrt(1 - r^2/A^2) + Z0 ,   Z0 = -C * sqrt(1 - R^2/A^2)   (rim at z = 0)

so the cap rim sits at z = 0 and the cap centre bulges up by CAP_HEIGHT.

Run:  py -3.12 scenes/generate_cap.py   ->  cap.obj (membrane) + lens.obj (base)
"""
import math
import os

# --- base ellipsoid (the "ball", flattened like a lens) ---------------------
A = 7.0       # semi-axis in x and y
C = 3.5       # semi-axis in z  -> C < A = oblate/flattened. Lower C = flatter.

# --- membrane cap -----------------------------------------------------------
R = 5.0       # membrane radius in the xy-plane (must be < A)
N = 10        # concentric rings (0.5 mm pitch, like the capsule fibers)
M = 60        # angular divisions -> ~1200 triangles

# base mesh tessellation (fine, so the cap sits flush on it, no faceting gap)
BASE_U = 96   # azimuth divisions
BASE_V = 48   # polar divisions

Z0 = -C * math.sqrt(1.0 - (R * R) / (A * A))   # so the cap rim lands at z = 0
CAP_HEIGHT = C + Z0                            # centre bulge above the rim


def z_of_r(r):
    """Height of the ellipsoid surface at planar radius r (same surface for both)."""
    s = 1.0 - (r * r) / (A * A)
    return C * math.sqrt(max(s, 0.0)) + Z0


def build_cap():
    verts = [(0.0, 0.0, z_of_r(0.0))]                 # index 0 = cap centre
    for i in range(1, N + 1):
        r = R * i / N
        z = z_of_r(r)
        for j in range(M):
            a = 2.0 * math.pi * j / M
            verts.append((r * math.cos(a), r * math.sin(a), z))

    def idx(ring, j):
        return 1 + (ring - 1) * M + (j % M)

    faces = []
    for j in range(M):                                # fan: centre -> ring 1
        faces.append((0, idx(1, j), idx(1, j + 1)))
    for ring in range(1, N):
        for j in range(M):
            a, b = idx(ring, j), idx(ring, j + 1)
            c, d = idx(ring + 1, j), idx(ring + 1, j + 1)
            faces.append((a, c, d))
            faces.append((a, d, b))
    return verts, faces


def build_lens():
    """Full oblate ellipsoid, finely tessellated (UV sphere scaled to A, A, C)."""
    verts = []
    for iv in range(BASE_V + 1):
        v = math.pi * iv / BASE_V                     # polar angle 0..pi
        for iu in range(BASE_U):
            u = 2.0 * math.pi * iu / BASE_U
            verts.append((A * math.sin(v) * math.cos(u),
                          A * math.sin(v) * math.sin(u),
                          C * math.cos(v) + Z0))

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
               "membrane cap on oblate lens: R=%g A=%g C=%g capH=%.3f Z0=%.3f"
               % (R, A, C, CAP_HEIGHT, Z0))
    lv, lf = build_lens()
    _write_obj(os.path.join(here, "lens.obj"), lv, lf,
               "oblate lens base: A=%g C=%g Z0=%.3f" % (A, C, Z0))
    print("cap.obj : %d verts %d tris (R=%g, capHeight=%.3f)" % (len(cv), len(cf), R, CAP_HEIGHT))
    print("lens.obj: %d verts %d tris (oblate A=%g C=%g, flatness C/A=%.2f, Z0=%.3f)"
          % (len(lv), len(lf), A, C, C / A, Z0))


if __name__ == "__main__":
    main()
