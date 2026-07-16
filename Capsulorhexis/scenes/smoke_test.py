"""Headless smoke test: the CCC scene LOADS, the engine initializes Valid, and the
capsule DEFORMS under the scripted pull. Tearing itself is NOT exercised here --
a manual animate loop mis-propagates topology changes (verify tearing in the GUI,
via scenes/run.ps1). So we raise stressThreshold sky-high to keep the mesh intact
and just validate the deformation + component wiring.

    py -3.12 scenes/smoke_test.py
"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
import capsule_ccc  # noqa: E402  (bootstraps SOFA DLL paths on import)

import Sofa  # noqa: E402
import Sofa.Simulation  # noqa: E402
import SofaRuntime  # noqa: E402

SofaRuntime.PluginRepository.addFirstPath(capsule_ccc._PLUGIN_BUILD)
SofaRuntime.importPlugin("Sofa.Component")
SofaRuntime.importPlugin("Tearing")
SofaRuntime.importPlugin("Capsulorhexis")

root = Sofa.Core.Node("root")
capsule_ccc.createScene(root)
# Disable tearing for the headless run (keep topology static).
root.Capsule.tearing.stressThreshold.value = 1.0e12

Sofa.Simulation.init(root)

engine = root.Capsule.tearing
state = str(engine.componentState.value) if hasattr(engine, "componentState") else "?"
print("FiberFractureEngine componentState:", state)

dofs = root.Capsule.dofs
p0 = [list(p) for p in dofs.position.value]

STEPS = 60   # 1.2 s > pull onset (0.5 s), so the peel is active
for _ in range(STEPS):
    Sofa.Simulation.animate(root, root.dt.value)

p1 = [list(p) for p in dofs.position.value]
max_disp = max((sum((a - b) ** 2 for a, b in zip(q, r))) ** 0.5 for q, r in zip(p0, p1))
print("max nodal displacement after %d steps: %.4f mm" % (STEPS, max_disp))

ok = ("Valid" in state) and (max_disp > 1e-3)
print("SMOKE TEST:", "PASS" if ok else "FAIL")
sys.exit(0 if ok else 1)
