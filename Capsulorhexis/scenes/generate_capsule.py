"""Generate a triangulated concentric-ring capsule disc (OBJ) at capsule scale.

The concentric-ring layout is deliberate and faithful to the anatomy: the lens
capsule's collagen fibers run concentrically (Dequidt et al. 2013: one concentric
ring every 0.5 mm). Ring edges run circumferentially (the tough, along-fiber
direction); spokes run radially (the weak, transverse direction along which the
capsulorhexis tear propagates).

Dimensions: radius 5 mm, one ring every 0.5 mm (N = 10 rings), which reproduces
Dequidt's fiber spacing. Units are millimetres.

Run:  py -3.12 scenes/generate_capsule.py
Output: capsule.obj (flat disc in the z = 0 plane, centred at the origin).
"""
import math
import os

R = 5.0      # disc radius (mm) -- a ~10 mm capsulorhexis opening
N = 10       # concentric rings -> 0.5 mm spacing (Dequidt fiber pitch)
M = 60       # angular divisions per ring (=> ~1140 triangles, near the paper demo)


def build():
    verts = [(0.0, 0.0, 0.0)]                        # index 0 = centre
    for i in range(1, N + 1):
        r = R * i / N
        for j in range(M):
            a = 2.0 * math.pi * j / M
            verts.append((r * math.cos(a), r * math.sin(a), 0.0))

    def idx(ring, j):                                # ring >= 1, 0-based vertex id
        return 1 + (ring - 1) * M + (j % M)

    faces = []
    for j in range(M):                               # fan: centre -> ring 1
        faces.append((0, idx(1, j), idx(1, j + 1)))
    for ring in range(1, N):                         # quad strips between rings
        for j in range(M):
            a, b = idx(ring, j), idx(ring, j + 1)
            c, d = idx(ring + 1, j), idx(ring + 1, j + 1)
            faces.append((a, c, d))
            faces.append((a, d, b))
    return verts, faces


def rim_indices():
    """0-based vertex ids of the outer ring (pin these to fix the capsule rim)."""
    return list(range(1 + (N - 1) * M, N * M + 1))


def main():
    verts, faces = build()
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "capsule.obj")
    with open(out, "w") as f:
        f.write("# concentric capsule disc: R=%g mm N=%d (0.5mm) M=%d, %d verts %d tris\n"
                % (R, N, M, len(verts), len(faces)))
        for v in verts:
            f.write("v %.6f %.6f %.6f\n" % v)
        for t in faces:                              # OBJ is 1-indexed
            f.write("f %d %d %d\n" % (t[0] + 1, t[1] + 1, t[2] + 1))
    print("wrote %s : %d vertices, %d triangles" % (out, len(verts), len(faces)))
    print("rim (outer ring) indices: %d..%d" % (rim_indices()[0], rim_indices()[-1]))


if __name__ == "__main__":
    main()
