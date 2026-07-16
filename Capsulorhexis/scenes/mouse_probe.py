"""Minimal probe: does SofaImGui deliver mouse events to a Python controller?

This decides whether a PBD (position-based) rewrite -- where the mouse KINEMATICALLY moves a
node instead of a penalty spring (so it can never explode) -- is feasible in this GUI.
SofaImGui was known to swallow the keyboard; if it swallows the mouse too, we use the JS demo
(demo_remesh_attached.html) for interactive tearing instead.

Run:  runSofa -l SofaPython3 -g imgui -a scenes\mouse_probe.py   (or the launcher below)
Then MOVE the mouse over the 3D viewport and CLICK. Watch the terminal:
  - if you see [MOUSE] move/click lines -> SofaImGui delivers mouse events -> PBD rewrite OK
  - if NOTHING prints on mouse move/click -> it swallows the mouse -> use the JS demo
"""
import os
import sys

SOFA_ROOT = os.environ.get("SOFA_ROOT", r"C:\SOFA\SOFA_v25.12.00_Win64")
os.environ["SOFA_ROOT"] = SOFA_ROOT
sys.path.insert(0, os.path.join(SOFA_ROOT, "plugins", "SofaPython3", "lib", "python3", "site-packages"))
for _p in (os.path.join(SOFA_ROOT, "bin"),):
    if os.path.isdir(_p):
        os.add_dll_directory(_p)


def _controller():
    import Sofa

    class _P(Sofa.Core.Controller):
        def __init__(self, *a, **k):
            Sofa.Core.Controller.__init__(self, *a, **k)
            self.n = 0

        def onMouseEvent(self, event):
            self.n += 1
            st = event.get('State', -1)
            # print EVERY event (throttled only for pure moves so it does not flood), so we
            # can tell if MOVE (State 0) events fire during a HOLD-DRAG (needed for a smooth
            # drag). HOLD the left button and drag slowly.
            if st == 0:
                if self.n % 5 == 0:
                    print(f"[MOUSE] MOVE  x={event.get('mouseX')} y={event.get('mouseY')}  (#{self.n})")
            elif st == 1:
                print(f"[MOUSE] LEFT DOWN  x={event.get('mouseX')} y={event.get('mouseY')}")
            elif st == 2:
                print("[MOUSE] left up")
            else:
                print(f"[MOUSE] state={st} {event}")

    return _P(name="MouseProbe")


def createScene(root):
    import Sofa  # noqa: F401
    root.dt = 0.02
    for name in ("Sofa.Component.Visual", "Sofa.Component.AnimationLoop",
                 "Sofa.Component.Setting", "Sofa.GL.Component.Rendering3D",
                 "Sofa.Component.StateContainer"):
        root.addObject("RequiredPlugin", name=name)
    root.addObject("DefaultAnimationLoop")
    root.addObject("DefaultVisualManagerLoop")
    root.addObject("VisualStyle", displayFlags="showBehaviorModels")
    root.addObject("BackgroundSetting", color=[0.06, 0.09, 0.12, 1.0])
    root.addObject("InteractiveCamera", position=[0, 0, 10], lookAt=[0, 0, 0])
    root.addObject("MechanicalObject", name="pts", position=[[0, 0, 0], [1, 1, 0], [-1, 1, 0]],
                   showObject=True, showObjectScale=0.5, drawMode=1)
    root.addObject(_controller())
    print("=" * 60)
    print(" MOUSE PROBE: move the mouse over the viewport and click.")
    print(" See [MOUSE] lines here -> mouse works. Nothing -> swallowed.")
    print("=" * 60)
    return root


def main():
    import Sofa
    import Sofa.Gui
    import SofaRuntime
    SofaRuntime.importPlugin("Sofa.Component")
    SofaRuntime.importPlugin("Sofa.GL.Component.Rendering3D")
    SofaRuntime.importPlugin("SofaImGui")
    root = Sofa.Core.Node("root")
    createScene(root)
    Sofa.Simulation.init(root)
    Sofa.Gui.GUIManager.Init("mouse_probe", "imgui")
    Sofa.Gui.GUIManager.createGUI(root, __file__)
    Sofa.Gui.GUIManager.SetDimension(900, 700)
    Sofa.Gui.GUIManager.MainLoop(root)
    Sofa.Gui.GUIManager.closeGUI()


try:
    import Sofa  # noqa: F401
except Exception:  # noqa: BLE001
    pass

if __name__ == "__main__":
    main()
