"""Regression test for TopologySplitEngine.

Run:  runSofa -l SofaPython3 -g batch -n 1 Capsulorhexis/tests/test_topology_split.py
      (with SOFA_PLUGIN_PATH pointing at Capsulorhexis/build)

Checks the one property the component exists for: after opening the mesh at a vertex, the
container's EDGE list still matches the triangles exactly. Writing topo.triangles directly --
what the scene used to do -- leaves that list stale, and the stale entries become springs
stapling the cut shut."""
import Sofa, Sofa.Core, Sofa.Simulation, numpy as np
root = Sofa.Core.Node("root")
root.addObject("RequiredPlugin", name="Capsulorhexis")
root.addObject("DefaultAnimationLoop")
root.addObject("EulerImplicitSolver"); root.addObject("CGLinearSolver", iterations=25,
                                                      tolerance=1e-5, threshold=1e-5)
n = root.addChild("m")
# a small fan: centre vertex 0 surrounded by a ring, so vertex 0 has several triangles
import math
pos=[[0,0,0]]; tris=[]
K=6
for i in range(K):
    a=2*math.pi*i/K; pos.append([math.cos(a), math.sin(a), 0.0])
for i in range(K):
    tris.append([0, 1+i, 1+((i+1)%K)])
n.addObject("MechanicalObject", name="mo", position=pos)
n.addObject("TriangleSetTopologyContainer", name="topo", triangles=tris)
n.addObject("TriangleSetTopologyModifier")
n.addObject("TriangleSetGeometryAlgorithms", template="Vec3d")
n.addObject("DiagonalMass", massDensity=1.0)
n.addObject("MeshSpringForceField", name="spr", linesStiffness=100, linesDamping=1.0)
eng = n.addObject("TopologySplitEngine", name="split")
Sofa.Simulation.init(root)

def edges_ok(tag):
    T=np.array(n.topo.triangles.value); E=np.array(n.topo.edges.value)
    te=set()
    for a,b,c in T.tolist():
        for u,v in ((a,b),(b,c),(c,a)): te.add((min(u,v),max(u,v)))
    ce=set((int(min(a,b)),int(max(a,b))) for a,b in E) if len(E) else set()
    i1=np.array(n.spr.springsIndices1.value).ravel(); i2=np.array(n.spr.springsIndices2.value).ravel()
    sp=set((int(min(a,b)),int(max(a,b))) for a,b in zip(i1,i2))
    print(f"{tag}: pts={n.topo.nbPoints.value} tris={len(T)} "
          f"topo.edges={len(ce)} triEdges={len(te)} stale={len(ce-te)} missing={len(te-ce)} "
          f"| springs={len(sp)} springStale={len(sp-te)}")

Sofa.Simulation.animate(root, 0.01)
edges_ok("before   ")
# split vertex 0, moving half its fan onto the duplicate
eng.splitPoint.value = 0
eng.movedTriangles.value = [0,1,2]
eng.request.value = 1
Sofa.Simulation.animate(root, 0.01)
print(f"served={eng.served.value}  newPoint={eng.newPoint.value}")
edges_ok("after    ")
T=np.array(n.topo.triangles.value)
nv=eng.newPoint.value
print("triangles now:", T.tolist())
print("vertex 0 still in:", [i for i,t in enumerate(T.tolist()) if 0 in t])
print("duplicate %d in :" % nv, [i for i,t in enumerate(T.tolist()) if nv in t])
P=np.array(n.mo.position.value)
print(f"duplicate position {P[nv]} vs original {P[0]}  (should match)")
