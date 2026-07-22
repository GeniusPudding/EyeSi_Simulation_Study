# Capsulorhexis — a faithful SOFA plugin for INRIA fiber-based CCC tearing

A C++ SOFA plugin that reproduces, **strictly following the original papers**, the
fiber-based soft-tissue tearing model used to simulate **continuous curvilinear
capsulorhexis (CCC)** — the circular tear of the lens capsule in cataract surgery.

Primary sources (PDFs in `../papers/`):

- **Allard, Marchal, Cotin 2009** — *Fiber-based Fracture Model for Simulating Soft
  Tissue Tearing* (MMVR 17). The tearing criterion (Eq. 1–6). **This is the core.**
- **Dequidt, Courtecuisse et al. 2013** — *A cataract surgery training system*.
  Reuses the same model for the full capsule + phaco + IOL system.

## Why this exists

The earlier `sofa_ccc/` Python demos leaned on the stock `TearingEngine`, which
implements only the **isotropic** maximum-principal-stress (Rankine) criterion and
a remesh that produces degenerate triangles under multi-crack propagation. That is
*not* the paper's model. This plugin implements the paper's actual technical stack:

| Paper element | Equation | Where implemented |
|---|---|---|
| Transversely-isotropic co-rotational triangular FEM | Marchal Eq.1 | stock `TriangularAnisotropicFEMForceField` (same INRIA lineage) |
| Concentric fiber initialization (every 0.5 mm, Dequidt) | — | `fiberCenter` of the anisotropic FEM |
| **Fiber-based argmax-c tearing criterion** | **Marchal Eq.3–6** | **`FractureCriterion.h` (this plugin)** |
| **Robust remesh avoiding degenerate triangles** | Marchal §2.3 | **`FiberFractureEngine` (this plugin)** |
| Implicit + matrix-free CG | — | stock `EulerImplicitSolver` + `CGLinearSolver` |

The isotropic case of the paper's criterion (`σ̄_F = σ̄_T`, `θ_P = 90°`) provably
reduces to maximum principal stress — this is unit-tested in `tests/` as the
correctness oracle (see below).

## Quick start

```powershell
# one command: fetches Eigen, configures, builds, runs the unit test
./scripts/setup.ps1
```

Then load-test the built DLL in SOFA:

```powershell
py -3.12 scripts/load_test.py     # -> "Capsulorhexis.dll load: SUCCESS"
```

Prerequisites (checked by `setup.ps1`): a SOFA binary SDK (`$env:SOFA_ROOT`,
default `C:\SOFA\SOFA_v25.12.00_Win64`), CMake, Ninja, Visual Studio 2022 Build
Tools, and `curl`+`tar` (bundled with Windows 10/11).

## Layout

```
Capsulorhexis/
  src/Capsulorhexis/
    config.h              export macros + module identity
    FractureCriterion.h   Marchal Eq.3-6, SOFA-free, header-only (the physics core)
    init.cpp              plugin entry points + component registration
    FiberFractureEngine.* argmax-c engine subclassing BaseTearingEngine  (Stage 4)
  tests/
    test_fracture_criterion.cpp   standalone test vs the paper's isotropic oracle
  scenes/                 CCC capsule scenes                               (Stage 6)
  scripts/
    setup.ps1             one-command setup (fetch deps + build + test)
    build.ps1             configure + build against the local SOFA SDK
    load_test.py          confirm the DLL loads into SOFA
  tools/                  fetched Eigen (gitignored)
  build/                  build output (gitignored)
```

## Build details

`build.ps1` imports the MSVC x64 environment via `vswhere`, points
`CMAKE_PREFIX_PATH` at `$env:SOFA_ROOT` and every bundled plugin's `lib/cmake`,
and passes the fetched Eigen via `EIGEN3_INCLUDE_DIR`. Note: the SOFA
`TearingConfig.cmake` omits `find_package` calls for two targets it references
(`Sofa.Component.StateContainer`, `Sofa.Component.Constraint.Projective`); our
`CMakeLists.txt` imports them first so `find_package(Tearing)` resolves.

## Running the CCC scene

```powershell
py -3.12 scenes/generate_capsule.py   # concentric-fiber disc: R=5mm, ring/0.5mm, 1140 tris
py -3.12 scenes/smoke_test.py         # headless: loads, engine Valid, capsule deforms
./scenes/run.ps1                      # runSofa GUI: Shift+drag to pull and tear
```

`smoke_test.py` validates the full pipeline headless (the engine initializes
Valid and the capsule deforms). **Tearing must be validated in the runSofa GUI** —
a manual headless animate loop mis-propagates SOFA topology changes.

## Status

- [x] Stage 1 — buildable + loadable plugin scaffold (toolchain de-risked)
- [x] Stage 2 — Marchal argmax-c criterion (`FractureCriterion.h`) + unit test (14/14)
- [x] Stage 3 — `FiberFractureEngine`: reads stress + fiber → argmax-c, feeds proper
      endpoints + cut-normal into the reused cut machinery. Builds, registers,
      instantiates, initializes Valid, deforms. (GUI tearing validation pending.)
- [x] Stage 5 — concentric-fiber capsule CCC scene + headless smoke test + runSofa launcher
- [ ] Stage 4 — arbitrary-direction remesh with degenerate-triangle avoidance
      (the multi-fracture-stable, mesh-independent path; hardens the reused cut)
