"""Headless jittery-pull probe. Emulates the GUI's AttachBodyButton: a mouse particle joined
to one capsule node by a k=MOUSE_STIFFNESS spring, dragged along a jittery path. Reports how
far the tear got and the WHY histogram, i.e. exactly what the black box records live."""
import os, sys, math, collections
os.environ.setdefault("SOFA_ROOT", r"C:\SOFA\SOFA_v25.12.00_Win64")
SR = os.environ["SOFA_ROOT"]
sys.path.insert(0, os.path.join(SR, "plugins", "SofaPython3", "lib", "python3", "site-packages"))
if hasattr(os, "add_dll_directory"):
    os.add_dll_directory(os.path.join(SR, "bin"))
SCENES = r"C:\Users\user\Desktop\GitHub\EyeSi_Simulation_Study\Capsulorhexis\scenes"
sys.path.insert(0, SCENES); os.chdir(SCENES)
os.environ["CAP_TEAR"] = "1"; os.environ["CAP_HEATMAP"] = "0"

import numpy as np, Sofa, Sofa.Simulation
import cap_membrane as CM

root = Sofa.Core.Node("root")
CM.createScene(root)

cap = root.getChild("Cap")
mo = cap.getObject("Mo")
P0 = np.array(mo.position.value)
rr = np.hypot(P0[:, 0], P0[:, 1])
GRAB = int(np.argmin(np.abs(rr - float(os.environ.get("PROBE_R", "3.2")))))
start = P0[GRAB].tolist()

m = root.addChild("Mouse")
mmo = m.addObject("MechanicalObject", name="MMO", template="Vec3d", position=[start])
m.addObject("UniformMass", totalMass=1e-6)
m.addObject("FixedProjectiveConstraint", indices=[0])
root.addObject("StiffSpringForceField", name="Grab",
               object1="@Mouse/MMO", object2="@Cap/Mo",
               spring=[[0, GRAB, CM.MOUSE_STIFFNESS, 1.0, 0.0]])

Sofa.Simulation.init(root)

why = collections.Counter(); lens = []; first = [None, None]
STEPS = int(os.environ.get("PROBE_STEPS", "900"))
PULL = np.array([float(x) for x in os.environ.get("PROBE_DIR", "1,0.25,1.6").split(",")])
AMP = float(os.environ.get("PROBE_AMP", "5.0"))
s0 = np.array(start)
for i in range(STEPS):
    a = i / STEPS
    jit = 0.12 * math.sin(i * 0.7) + 0.06 * math.sin(i * 1.9)
    tgt = s0 + PULL * (AMP * a + jit)
    with mmo.position.writeable() as W:
        W[0] = tgt
    Sofa.Simulation.animate(root, root.dt.value)
    st = CM._TEAR_STATE
    why[str(st.get("why", "?"))[:44]] += 1
    L = int(st.get("len", 0) or 0)
    if lens and L > lens[0] and first[0] is None:
        # THE number the user actually feels: how far the instrument had to travel before
        # the membrane gave at all.
        first[0] = float(np.linalg.norm(np.array(mo.position.value)[GRAB] - P0[GRAB]))
        first[1] = i
    lens.append(L)

P = np.array(mo.position.value)
lift = float(P[:, 2].max() - P0[:, 2].max())
# mesh health: worst edge stretch and the degenerate fraction, so "more tearing" can never
# be reported without saying what it cost the mesh.
T = np.array(root.getChild("Cap").getObject("Topo").triangles.value) if False else None
import cap_membrane as _cm
_T = np.array([list(t) for t in root.getChild("Cap").objects[0].getContext().getObject("Container").triangles.value]) if False else None
try:
    topo = [o for o in root.getChild("Cap").objects if hasattr(o, "triangles")][0]
    tri = np.array(topo.triangles.value)
    R = np.array(mo.rest_position.value)
    def area(X, t):
        a, b, c = X[t[:,0]], X[t[:,1]], X[t[:,2]]
        return 0.5*np.linalg.norm(np.cross(b-a, c-a), axis=1)
    ar = area(P, tri)/np.maximum(area(R, tri), 1e-12)
    degen = float(np.mean((ar < 0.25) | (ar > 4.0)))
    e = np.concatenate([tri[:,[0,1]], tri[:,[1,2]], tri[:,[2,0]]])
    L = np.linalg.norm(P[e[:,0]]-P[e[:,1]], axis=1)
    L0 = np.maximum(np.linalg.norm(R[e[:,0]]-R[e[:,1]], axis=1), 1e-12)
    st_ = np.sort(L/L0)
    print("mesh: stretch p50 %.2f p99 %.2f p99.9 %.2f max %.2f (%d edges over 3x)  degen %.1f%%"
          % (st_[len(st_)//2], st_[int(.99*len(st_))], st_[int(.999*len(st_))], st_[-1],
             int((st_ > 3).sum()), 100*degen))
except Exception as ex:
    print("mesh health unavailable:", ex)
print("FIRST TEAR after grab travel %s (step %s of %d)"
      % ("%.2f" % first[0] if first[0] is not None else "never", first[1], STEPS))
print("crack %d -> %d (peak %d)   grab travel %.2f   max lift %.2f"
      % (lens[0], lens[-1], max(lens), float(np.linalg.norm(P[GRAB] - P0[GRAB])), lift))
tearing = sum(v for k, v in why.items() if k.startswith("tearing"))
print("tearing on %.1f%% of steps" % (100 * tearing / STEPS))
for k, v in why.most_common(6):
    print("%6d %5.1f%%  %s" % (v, 100 * v / STEPS, k))
