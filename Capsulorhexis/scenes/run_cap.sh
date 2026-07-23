#!/bin/bash
# Launch the cap-on-lens capsulorhexis demo in the runSofa GUI (macOS).
# Mirror of run_cap.ps1: regenerates the meshes, then runs the imgui GUI.
#
#   DEFAULT is cap_membrane.py -- the membrane simply SITS on the oblate lens, held
#   down by a breakable adhesion. NOTHING is clamped (FIX_OUTER_RIM=False), so you can
#   Shift+left-drag the RIM, lift it and FOLD IT OVER. Pull gently and the adhesion
#   holds; pull harder and that spot peels off. It prints [Peel]/[ClothToPaper] lines.
#
# Usage:  ./scenes/run_cap.sh              # mass-spring (default, tuned)
#         ./scenes/run_cap.sh --fem        # co-rotational FEM
#         ./scenes/run_cap.sh [scene.py]
set -euo pipefail

# --fem selects the co-rotational FEM membrane; default is the tuned mass-spring one.
# Read by cap_membrane.py via CAP_MODE.
export CAP_MODE="spring"
ARGS=()
for a in "$@"; do
  case "$a" in
    --fem)    export CAP_MODE="fem" ;;
    --spring) export CAP_MODE="spring" ;;
    *)        ARGS+=("$a") ;;
  esac
done
SCENE="${ARGS[0]:-cap_membrane.py}"
SCENES_DIR="$(cd "$(dirname "$0")" && pwd)"

export SOFA_ROOT="${SOFA_ROOT:-$HOME/SOFA/SOFA_v25.12.00_MacOS}"
VENV_PY="$HOME/SOFA/venv/bin/python"
export PYTHONPATH="$SOFA_ROOT/plugins/SofaPython3/lib/python3/site-packages:$HOME/SOFA/venv/lib/python3.12/site-packages${PYTHONPATH:+:$PYTHONPATH}"

# ALWAYS regenerate, so geometry edits (C, CAP_ANGLE_DEG, A, TARGET_EDGE) take effect.
"$VENV_PY" "$SCENES_DIR/generate_cap.py"

RUNSOFA="$SOFA_ROOT/bin/runSofa"
[ -x "$RUNSOFA" ] || { echo "runSofa not found at $RUNSOFA" >&2; exit 1; }

echo "Launching runSofa on $SCENE (console -> $SCENES_DIR/run_last.log) ..."
"$RUNSOFA" -l SofaPython3 -g imgui -a "$SCENES_DIR/$SCENE" 2>&1 | tee "$SCENES_DIR/run_last.log"
