"""Smoke test: confirm the built Capsulorhexis.dll loads into SOFA and exports
its module entry points. Run with Python 3.12 (SofaPython3 here is cp312):

    py -3.12 scripts/load_test.py
"""
import os
import sys

SOFA_ROOT = os.environ.get("SOFA_ROOT", r"C:\SOFA\SOFA_v25.12.00_Win64")
os.environ["SOFA_ROOT"] = SOFA_ROOT
sys.path.insert(0, os.path.join(SOFA_ROOT, "plugins", "SofaPython3", "lib", "python3", "site-packages"))

os.add_dll_directory(os.path.join(SOFA_ROOT, "bin"))
for plugin in ("SofaPython3", "Tearing", "Sofa.Component.SolidMechanics.FEM.Elastic"):
    d = os.path.join(SOFA_ROOT, "plugins", plugin, "bin")
    if os.path.isdir(d):
        os.add_dll_directory(d)

# our freshly built plugin
BUILD_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "build")
os.add_dll_directory(BUILD_DIR)

import SofaRuntime  # noqa: E402

SofaRuntime.PluginRepository.addFirstPath(BUILD_DIR)
ok = SofaRuntime.importPlugin("Capsulorhexis")
print("importPlugin('Capsulorhexis') ->", ok)

# Confirm the plugin registered (module known to the plugin manager).
import Sofa  # noqa: E402

# Confirm the FiberFractureEngine component registered in the object factory by
# instantiating it in a tiny scene.
SofaRuntime.importPlugin("Sofa.Component")   # register the standard components
registered = False
try:
    root = Sofa.Core.Node("root")
    root.addObject("RequiredPlugin", name="Capsulorhexis")
    root.addObject("MechanicalObject", template="Vec3d")
    ff = root.addObject("FiberFractureEngine", sigmaBarF=8.0, sigmaBarT=2.0, alpha=4.0, thetaP=60.0)
    registered = ff is not None
    print("FiberFractureEngine: instantiated (sigmaBarF=8, sigmaBarT=2, alpha=4, thetaP=60)")
except Exception as e:  # noqa: BLE001
    print("FiberFractureEngine instantiation FAILED:", e)

print("Capsulorhexis.dll load: SUCCESS" if ok else "Capsulorhexis.dll load: FAILED")
print("Component registration:", "SUCCESS" if registered else "FAILED")
sys.exit(0 if (ok and registered) else 1)
