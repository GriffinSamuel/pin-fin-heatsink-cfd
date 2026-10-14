"""OpenFOAM 14 conjugate-heat-transfer case generator for the shrouded pin-fin heat sink (T3).

Case layout and dictionary syntax follow the OpenFOAM-14 tutorials
multiRegion/CHT/heatedDuct (snappyHexMesh + splitMeshRegions + foamMultiRun),
multiRegion/CHT/circuitBoardCooling (steady-state fluid + solid settings) and
multiRegion/CHT/coolingSphere/templates (air / aluminium properties, k-omega SST BCs).

Geometry (metres): fluid duct x in [-0.06, 0.18], y in [0, 0.06], z in [0, H], H = base_t + h.
The heat sink base plate sits on the floor as a 4 mm step; the pin tips touch the top wall
(shroud). The chip is the 30 x 30 mm patch of the floor under the centre of the base; it is
its own blockMesh patch and carries a fixed heat flux via a fixedGradient T condition
(constant kappa: dT/dn = q''/kappa). Side walls are symmetry planes.

Usage:  python -m src.make_case --d 3 --pd 2.2 --h 35 --layout staggered --V 4 \
            --mesh coarse --out work/cases/center_coarse [--np 6] [--iters 1500]
"""
from __future__ import annotations

import argparse
import json
import math
import os
import shutil
import stat
import textwrap
from dataclasses import dataclass

from src.geometry import HeatSinkSpec, PlateFinSpec, export_all, export_platefin, metadata, platefin_metadata
from src.analytic import solve as analytic_solve

T_IN = 298.15           # K (25 C)
Q_CHIP = 100.0          # W
KAPPA_AL = 200.0        # W/m-K
P_REF = 1e5             # Pa
RHO_AL = 2700.0         # kg/m^3
BASE_CELL = 0.003       # m, background cell size
CHIP_SIZE = 0.030       # m, chip side of the study (parametric designs)

MATERIALS = {"aluminium": (200.0, 2700.0), "copper": (385.0, 8960.0)}   # (kappa W/m-K, rho kg/m3)


@dataclass
class DomainSpec:
    """Everything the case templates need to know about the duct, the sink envelope and the chip (metres).

    Duct: x in [x_in, x_out], y in [0, W], z in [0, H] with H = base_t + h + tip_gap. The sink base occupies
    x in [0, L]. The chip is the rectangle [chip_x0, chip_x1] x [chip_y0, chip_y1] on the floor under the base."""
    L: float
    W: float
    base_t: float
    h: float
    chip_x0: float
    chip_x1: float
    chip_y0: float
    chip_y1: float
    power_W: float = Q_CHIP
    T_in_K: float = T_IN
    kappa_solid: float = KAPPA_AL
    rho_solid: float = RHO_AL
    x_in: float | None = None
    x_out: float | None = None
    base_cell: float = BASE_CELL
    tip_gap: float = 0.0
    solid_point: tuple | None = None    # snappy inside point of the solid region; default is the base centre

    def __post_init__(self):
        if self.x_in is None:
            self.x_in = -1.0 * self.L          # study: -0.060 for L = 0.060
        if self.x_out is None:
            self.x_out = 3.0 * self.L          # study: 0.180

    @property
    def H(self) -> float:
        return self.base_t + self.h + self.tip_gap

    @property
    def x_splits(self) -> list[float]:
        return [self.x_in, self.chip_x0, self.chip_x1, self.x_out]

    @property
    def y_splits(self) -> list[float]:
        return [0.0, self.chip_y0, self.chip_y1, self.W]

    @property
    def nx(self) -> list[int]:
        X = self.x_splits
        return [max(1, round((X[i + 1] - X[i]) / self.base_cell)) for i in range(3)]

    @property
    def ny(self) -> list[int]:
        Y = self.y_splits
        return [max(1, round((Y[i + 1] - Y[i]) / self.base_cell)) for i in range(3)]

    @property
    def chip_area(self) -> float:
        return (self.chip_x1 - self.chip_x0) * (self.chip_y1 - self.chip_y0)


def domain_for_spec(spec) -> DomainSpec:
    """The study's domain: 30 x 30 mm chip centred under the base, 100 W, aluminium."""
    L, W = spec.base_l * 1e-3, spec.base_w * 1e-3
    cx, cy = L / 2, W / 2
    return DomainSpec(L=L, W=W, base_t=spec.base_t * 1e-3, h=spec.h * 1e-3,
                      chip_x0=cx - CHIP_SIZE / 2, chip_x1=cx + CHIP_SIZE / 2,
                      chip_y0=cy - CHIP_SIZE / 2, chip_y1=cy + CHIP_SIZE / 2)

# surface refinement level, box refinement level, layers (not used yet)
MESH_LEVELS = {
    "coarse": {"surf": 2, "box": 1, "box2": 1},
    "medium": {"surf": 3, "box": 2, "box2": 2},
    "fine":   {"surf": 4, "box": 2, "box2": 3},
}

HEADER = """FoamFile
{{
    version     2.0;
    format      ascii;
    class       {cls};
    {obj}
}}
"""


def hdr(cls: str, obj: str, location: str | None = None) -> str:
    loc = f'location    "{location}";\n    ' if location else ""
    return HEADER.format(cls=cls, obj=f'{loc}object      {obj};')


def w(path: str, text: str, executable: bool = False) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(textwrap.dedent(text).lstrip("\n"))
    if executable:
        os.chmod(path, os.stat(path).st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


# ----------------------------------------------------------------- blockMesh

def block_mesh_dict(dom: DomainSpec) -> str:
    H = dom.H
    X, Y, Z = dom.x_splits, dom.y_splits, [0.0, H]
    NX, NY = dom.nx, dom.ny
    nz = max(4, round(H / dom.base_cell))

    def v(i, j, k):
        return i + 4 * j + 16 * k

    verts = "\n".join(f"    ({X[i]:.4f} {Y[j]:.4f} {Z[k]:.4f})"
                      for k in range(2) for j in range(4) for i in range(4))
    blocks = []
    for j in range(3):
        for i in range(3):
            blocks.append(f"    hex ({v(i,j,0)} {v(i+1,j,0)} {v(i+1,j+1,0)} {v(i,j+1,0)} "
                          f"{v(i,j,1)} {v(i+1,j,1)} {v(i+1,j+1,1)} {v(i,j+1,1)}) "
                          f"({NX[i]} {NY[j]} {nz}) simpleGrading (1 1 1)")
    inlet = "\n".join(f"            ({v(0,j,0)} {v(0,j,1)} {v(0,j+1,1)} {v(0,j+1,0)})" for j in range(3))
    outlet = "\n".join(f"            ({v(3,j,0)} {v(3,j+1,0)} {v(3,j+1,1)} {v(3,j,1)})" for j in range(3))
    sides = "\n".join(f"            ({v(i,0,0)} {v(i+1,0,0)} {v(i+1,0,1)} {v(i,0,1)})" for i in range(3)) + "\n" + \
            "\n".join(f"            ({v(i,3,0)} {v(i,3,1)} {v(i+1,3,1)} {v(i+1,3,0)})" for i in range(3))
    top = "\n".join(f"            ({v(i,j,1)} {v(i+1,j,1)} {v(i+1,j+1,1)} {v(i,j+1,1)})"
                    for j in range(3) for i in range(3))
    floor = "\n".join(f"            ({v(i,j,0)} {v(i,j+1,0)} {v(i+1,j+1,0)} {v(i+1,j,0)})"
                      for j in range(3) for i in range(3) if not (i == 1 and j == 1))
    chip = f"            ({v(1,1,0)} {v(1,2,0)} {v(2,2,0)} {v(2,1,0)})"
    return hdr("dictionary", "blockMeshDict") + f"""
vertices
(
{verts}
);

blocks
(
{chr(10).join(blocks)}
);

edges
(
);

boundary
(
    inlet   {{ type patch;    faces (
{inlet}
    ); }}
    outlet  {{ type patch;    faces (
{outlet}
    ); }}
    sides   {{ type symmetry; faces (
{sides}
    ); }}
    top     {{ type wall;     faces (
{top}
    ); }}
    floor   {{ type wall;     faces (
{floor}
    ); }}
    chip    {{ type wall;     faces (
{chip}
    ); }}
);

mergePatchPairs
(
);
"""


# ----------------------------------------------------------------- snappyHexMesh

def snappy_dict(dom: DomainSpec, level: dict, flavour: str, region: str, n_layers: int = 4) -> str:
    """Per-region snappyHexMesh dictionary. The heat sink surface is a wall patch in both
    regions; the fluid mesh gets prism layers on it; the two region meshes are coupled
    afterwards with createNonConformalCouples (OpenFOAM-14 hotWire tutorial pattern)."""
    inside_key = "insidePoint" if flavour == "org" else "locationInMesh"
    lvl_key = "level" if flavour == "org" else "levels"
    tri_type = "triSurface" if flavour == "org" else "triSurfaceMesh"
    lvl = (lambda n: str(n)) if flavour == "org" else (lambda n: f"((1e15 {n}))")
    quality = ('' if flavour == "org" else
               "meshQualityControls\n{\n    maxNonOrtho 65;\n    maxBoundarySkewness 20;\n    maxInternalSkewness 4;\n"
               "    maxConcave 80;\n    minVol 1e-16;\n    minTetQuality 1e-30;\n    minArea -1;\n    minTwist 0.02;\n"
               "    minDeterminant 0.001;\n    minFaceWeight 0.02;\n    minVolRatio 0.01;\n    minTriangleTwist -1;\n"
               "    nSmoothScale 4;\n    errorReduction 0.75;\n    relaxed\n    {\n        maxNonOrtho 75;\n    }\n}")
    include = '#includeEtc "caseDicts/mesh/generation/snappyHexMeshDict.cfg"' if flavour == "org" else ""
    H, L, W = dom.H, dom.L, dom.W
    hmid = H / 2 + 0.0004          # off the background cell faces
    if region == "fluid":
        inside = f"({dom.x_in / 2 - 0.0005:.4f} {W / 2 + 0.0005:.4f} {hmid:.4f})"
        add_layers = "true" if n_layers > 0 else "false"
        layers = f"        heatsink\n        {{\n            nSurfaceLayers {n_layers};\n        }}"
    else:
        sp = dom.solid_point or (L / 2 + 0.0005, W / 2 + 0.0005, dom.base_t / 2 + 0.0001)
        inside = f"({sp[0]:.4f} {sp[1]:.4f} {sp[2]:.4f})"
        add_layers = "false"
        layers = ""
    return hdr("dictionary", "snappyHexMeshDict", f"system/{region}") + f"""
{include}

castellatedMesh true;
snap            true;
addLayers       {add_layers};

geometry
{{
    heatsink
    {{
        type {tri_type};
        file "heatsink.stl";
    }}
    refinementBox
    {{
        type box;
        min ({-0.2 * L:.6g} -0.001 -0.001);
        max ( {L + max(0.025, 0.4 * L):.6g}  {W + 0.001:.6g}  {H + 0.001:.4f});
    }}
    pinBox
    {{
        type box;
        min (-0.003 -0.001 {dom.base_t - 0.001:.6g});
        max ( {L + 0.006:.6g}  {W + 0.001:.6g}  {H + 0.001:.4f});
    }}
}};

castellatedMeshControls
{{
    maxLocalCells 2000000;
    maxGlobalCells 20000000;
    minRefinementCells 10;
    maxLoadUnbalance 0.10;
    nCellsBetweenLevels 2;
    resolveFeatureAngle 30;
    allowFreeStandingZoneFaces true;

    features
    (
    );

    refinementSurfaces
    {{
        heatsink
        {{
            level ({level['surf']} {level['surf']});
            patchInfo
            {{
                type wall;
            }}
        }}
    }}

    refinementRegions
    {{
        refinementBox
        {{
            mode    inside;
            {lvl_key} {lvl(level['box'])};
        }}
        pinBox
        {{
            mode    inside;
            {lvl_key} {lvl(level['box2'])};
        }}
    }}

    {inside_key} {inside};
}}

snapControls
{{
    nSmoothPatch 3;
    tolerance 2.0;
    nSolveIter 50;
    nRelaxIter 5;
    nFeatureSnapIter 10;
    implicitFeatureSnap true;
    explicitFeatureSnap false;
    multiRegionFeatureSnap false;
}}

addLayersControls
{{
    relativeSizes true;
    layers
    {{
{layers}
    }}
    expansionRatio 1.2;
    finalLayerThickness 0.4;
    minThickness 0.05;
    nGrow 0;
    featureAngle 100;
    slipFeatureAngle 30;
    nRelaxIter 5;
    nSmoothSurfaceNormals 1;
    nSmoothNormals 3;
    nSmoothThickness 10;
    maxFaceThicknessRatio 0.5;
    maxThicknessToMedialRatio 0.3;
    minMedialAxisAngle 90;
    nBufferCellsNoExtrude 0;
    nLayerIter 50;
}}

{quality}

debug 0;
mergeTolerance 1e-6;
"""


NCC_DICT = """
fields          no;

nonConformalCouples
{
    interface
    {
        regions         (solid fluid);
        patches         (heatsink heatsink);
    }
}
"""


# ----------------------------------------------------------------- fields

def field(cls: str, name: str, dims: str, internal: str, body: str, region: str) -> str:
    return hdr(cls, name, f"0/{region}") + f"""
dimensions      {dims};

internalField   {internal};

boundaryField
{{
{body}
}}
"""


def fluid_fields(V: float, k_in: float, omega_in: float, mixing_length: float, T_in: float = T_IN) -> dict:
    sct = '    #includeEtc "caseDicts/setConstraintTypes"'
    return {
        "U": field("volVectorField", "U", "[0 1 -1 0 0 0 0]", f"uniform ({V} 0 0)", f"""
    ".*"            {{ type noSlip; }}
    heatsink        {{ type slip; }}
    inlet           {{ type fixedValue; value uniform ({V} 0 0); }}
    outlet          {{ type pressureInletOutletVelocity; value uniform (0 0 0); }}
{sct}""", "fluid"),
        "T": field("volScalarField", "T", "[0 0 0 1 0 0 0]", f"uniform {T_in}", f"""
    ".*"            {{ type zeroGradient; }}
    inlet           {{ type fixedValue; value uniform {T_in}; }}
    outlet          {{ type inletOutlet; inletValue uniform {T_in}; value uniform {T_in}; }}
    interface_on_heatsink {{ type coupledTemperature; value uniform {T_in}; }}
{sct}""", "fluid"),
        "p": field("volScalarField", "p", "[1 -1 -2 0 0 0 0]", f"uniform {P_REF:g}", f"""
    ".*"            {{ type fixedFluxPressure; value $internalField; }}
    heatsink        {{ type zeroGradient; }}
    outlet          {{ type totalPressure; p0 $internalField; value $internalField; }}
{sct}""", "fluid"),
        "k": field("volScalarField", "k", "[0 2 -2 0 0 0 0]", f"uniform {k_in:.4g}", f"""
    ".*"            {{ type kqRWallFunction; value $internalField; }}
    heatsink        {{ type zeroGradient; }}
    inlet           {{ type turbulentKineticEnergy; intensity 0.05; value $internalField; }}
    outlet          {{ type inletOutlet; inletValue $internalField; value $internalField; }}
{sct}""", "fluid"),
        "omega": field("volScalarField", "omega", "[0 0 -1 0 0 0 0]", f"uniform {omega_in:.4g}", f"""
    ".*"            {{ type omegaWallFunction; blended true; value $internalField; }}
    heatsink        {{ type zeroGradient; }}
    interface_on_heatsink {{ type zeroGradient; }}   // omegaWallFunction diverges on stitched fragment faces (DECISIONS.md D9)
    inlet           {{ type turbulentOmega; mixingLength {mixing_length:.4g}; value $internalField; }}
    outlet          {{ type inletOutlet; inletValue $internalField; value $internalField; }}
{sct}""", "fluid"),
        "nut": field("volScalarField", "nut", "[0 2 -1 0 0 0 0]", "uniform 0", f"""
    ".*"            {{ type nutUSpaldingWallFunction; value uniform 0; }}
    heatsink        {{ type zeroGradient; }}
    inlet           {{ type calculated; value uniform 0; }}
    outlet          {{ type calculated; value uniform 0; }}
{sct}""", "fluid"),
        "alphat": field("volScalarField", "alphat", "[1 -1 -1 0 0 0 0]", "uniform 0", f"""
    ".*"            {{ type compressible::alphatWallFunction; value uniform 0; }}
    heatsink        {{ type zeroGradient; }}
    inlet           {{ type calculated; value uniform 0; }}
    outlet          {{ type calculated; value uniform 0; }}
{sct}""", "fluid"),
    }


def solid_T(q_flux: float, kappa: float = KAPPA_AL, T_in: float = T_IN) -> str:
    grad = q_flux / kappa
    return field("volScalarField", "T", "[0 0 0 1 0 0 0]", f"uniform {T_in + 20}", f"""
    ".*"            {{ type zeroGradient; }}
    chip            {{ type fixedGradient; gradient uniform {grad:.6g}; }}
    interface_on_heatsink {{ type coupledTemperature; value uniform {T_in + 20}; }}
    #includeEtc "caseDicts/setConstraintTypes"
""", "solid")


# ----------------------------------------------------------------- constant

AIR_PROPS = """
thermoType
{
    type            heRhoThermo;
    mixture         pureMixture;
    transport       const;
    thermo          hConst;
    equationOfState perfectGas;
    specie          specie;
    energy          sensibleEnthalpy;
}

mixture
{
    specie
    {
        molWeight   28.96;
    }
    thermodynamics
    {
        Cp          1006;
        hf          0;
    }
    transport
    {
        mu          1.85e-05;
        Pr          0.707;
    }
}
"""

def solid_props(kappa: float = KAPPA_AL, rho: float = RHO_AL) -> str:
    return AL_PROPS_TEMPLATE.format(kappa=f"{kappa:g}", rho=f"{rho:g}")


AL_PROPS_TEMPLATE = """
thermoType
{{
    type            heSolidThermo;
    mixture         pureMixture;
    transport       constIsoSolid;
    thermo          eConst;
    equationOfState rhoConst;
    specie          specie;
    energy          sensibleInternalEnergy;
}}

mixture
{{
    specie
    {{
        molWeight   27;
    }}
    transport
    {{
        kappa       {kappa};
    }}
    thermodynamics
    {{
        hf          0;
        Cv          900;
    }}
    equationOfState
    {{
        rho         {rho};
    }}
}}
"""

FLUID_SCHEMES = """
ddtSchemes
{
    default         steadyState;
}

gradSchemes
{
    default         Gauss linear;
    limited         cellLimited Gauss linear 1;
    grad(U)         $limited;
    grad(k)         $limited;
    grad(omega)     $limited;
}

divSchemes
{
    default         none;
    div(phi,U)      bounded Gauss linearUpwind limited;
    div(phi,K)      bounded Gauss limitedLinear 1;
    div(phi,h)      bounded Gauss limitedLinear 1;
    div(phi,k)      bounded Gauss upwind;
    div(phi,omega)  bounded Gauss upwind;
    div(((rho*nuEff)*dev2(T(grad(U))))) Gauss linear;
}

laplacianSchemes
{
    default         Gauss linear limited corrected 0.5;
}

interpolationSchemes
{
    default         linear;
}

snGradSchemes
{
    default         limited corrected 0.5;
}

wallDist
{
    method meshWave;
}
"""

FLUID_SOLUTION = """
solvers
{
    rho
    {
        solver          diagonal;
    }
    p
    {
        solver          GAMG;
        smoother        GaussSeidel;
        tolerance       1e-7;
        relTol          0.01;
        maxIter         100;
    }
    "(U|h|k|omega)"
    {
        solver          PBiCGStab;
        preconditioner  DILU;
        tolerance       1e-7;
        relTol          0.1;
        minIter         1;
    }
}

PIMPLE
{
    momentumPredictor yes;
    nNonOrthogonalCorrectors 0;
    pRefCell        0;
    pRefValue       1e5;
    residualControl
    {
        p               1e-4;
        U               1e-4;
        h               5e-5;
        "(k|omega)"     1e-3;
    }
}

relaxationFactors
{
    fields
    {
        rho             1.0;
        p               0.7;
        p_rgh           0.7;
    }
    equations
    {
        U               0.3;
        h               0.7;
        "(k|omega)"     0.3;
    }
}
"""

SOLID_SCHEMES = """
ddtSchemes
{
    default         steadyState;
}

gradSchemes
{
    default         Gauss linear;
}

divSchemes
{
    default         none;
}

laplacianSchemes
{
    default         Gauss linear corrected;
}

interpolationSchemes
{
    default         linear;
}

snGradSchemes
{
    default         corrected;
}
"""

SOLID_SOLUTION = """
solvers
{
    e
    {
        solver          PCG;
        preconditioner  DIC;
        tolerance       1e-8;
        relTol          0.01;
    }
}

PIMPLE
{
    nNonOrthogonalCorrectors 1;
    residualControl
    {
        e               1e-5;
    }
}

relaxationFactors
{
    equations
    {
        e               1;
    }
}
"""


def control_dict(n_iter: int) -> str:
    return hdr("dictionary", "controlDict") + f"""
regionSolvers
{{
    fluid           fluid;
    solid           solid;
}}

startFrom       startTime;
startTime       0;
stopAt          endTime;
endTime         {n_iter};
deltaT          1;
writeControl    timeStep;
writeInterval   {n_iter};
purgeWrite      1;
writeFormat     binary;
writePrecision  8;
writeCompression off;
timeFormat      general;
timePrecision   6;
runTimeModifiable true;
"""


FUNCTIONS = """
#includeFunc cellMax(region=solid, T)
#includeFunc cellMin(region=solid, T)
#includeFunc patchAverage(region=solid, patch=chip, T)
#includeFunc patchAverage(region=fluid, patch=inlet, p)
#includeFunc patchAverage(region=fluid, patch=outlet, p)
#includeFunc patchAverage(region=fluid, patch=outlet, T)
#includeFunc patchAverage(region=fluid, patch=inlet, T)
#includeFunc patchFlowRate(region=fluid, patch=inlet, phi)
#includeFunc patchFlowRate(region=fluid, patch=outlet, phi)
#includeFunc cellMax(region=fluid, T)
#includeFunc residuals(region=fluid, p, U, h, k, omega)
#includeFunc residuals(region=solid, e)
#includeFunc wallHeatFlux(region=solid)
#includeFunc wallHeatFlux(region=fluid)
#includeFunc yPlus(region=fluid)
"""


def allmesh(flavour: str) -> str:
    if flavour == "org":
        return """
#!/bin/sh
cd ${0%/*} || exit 1    # Run from this directory

# Source tutorial run functions
. $WM_PROJECT_DIR/bin/tools/RunFunctions

rm -rf constant/polyMesh/sets

runApplication -s fluid blockMesh -region fluid || exit 1
runApplication -s solid blockMesh -region solid || exit 1
runApplication -s fluid snappyHexMesh -region fluid || exit 1
runApplication -s solid snappyHexMesh -region solid || exit 1
runApplication createNonConformalCouples || exit 1
runApplication -s fluid checkMesh -region fluid -constant
runApplication -s solid checkMesh -region solid -constant
"""
    # OpenFOAM v1912 (ESI) flavour, used only for local mesh testing
    return """
#!/bin/sh
cd ${0%/*} || exit 1
. ${WM_PROJECT_DIR:-/usr/share/openfoam}/bin/tools/RunFunctions 2>/dev/null || true
run() { name=$1; log=$2; shift 2; echo "Running $name ($log)"; "$name" "$@" > log.$log 2>&1 || { echo "FAILED: $name (see log.$log)"; exit 1; }; }
run blockMesh blockMesh.fluid -region fluid
run blockMesh blockMesh.solid -region solid
run snappyHexMesh snappyHexMesh.fluid -region fluid -overwrite
run snappyHexMesh snappyHexMesh.solid -region solid -overwrite
checkMesh -region fluid -constant > log.checkMesh.fluid 2>&1
checkMesh -region solid -constant > log.checkMesh.solid 2>&1
echo "esi flavour: no non-conformal coupling available; meshes only"
"""


def allrun(n_proc: int) -> str:
    return f"""
#!/bin/sh
cd ${{0%/*}} || exit 1    # Run from this directory

# Source tutorial run functions
. $WM_PROJECT_DIR/bin/tools/RunFunctions

./Allmesh || exit 1

runApplication decomposePar -allRegions || exit 1
runParallel foamMultiRun || exit 1
runApplication reconstructPar -allRegions -latestTime
rm -rf processor*
"""


def _write_case_files(dom: DomainSpec, V: float, level: dict, out: str, n_proc: int, n_iter: int,
                      flavour: str, n_layers: int, mesh: str) -> dict:
    """Write every OpenFOAM dictionary for the domain. The caller has already put the sink STL in place.
    Returns the quantities derived from the domain for case.json."""
    H = dom.H
    # inlet turbulence: 5 % intensity, mixing length 7 % of the duct hydraulic diameter
    A = dom.W * H
    Dh = 4 * A / (2 * (dom.W + H))
    k_in = 1.5 * (0.05 * V) ** 2
    L_mix = 0.07 * Dh
    omega_in = math.sqrt(k_in) / (0.09 ** 0.25 * L_mix)
    q_flux = dom.power_W / dom.chip_area

    for region in ("fluid", "solid"):
        w(os.path.join(out, "system", region, "blockMeshDict"), block_mesh_dict(dom))
        w(os.path.join(out, "system", region, "snappyHexMeshDict"), snappy_dict(dom, level, flavour, region, n_layers))
    w(os.path.join(out, "system", "createNonConformalCouplesDict"), hdr("dictionary", "createNonConformalCouplesDict") + NCC_DICT)
    w(os.path.join(out, "system", "meshQualityDict"), hdr("dictionary", "meshQualityDict") +
      '\n#includeEtc "caseDicts/mesh/generation/meshQualityDict.cfg"\n')
    w(os.path.join(out, "system", "controlDict"), control_dict(n_iter))
    w(os.path.join(out, "system", "fvSolution"), hdr("dictionary", "fvSolution") + "\nPIMPLE\n{\n    nOuterCorrectors 1;\n}\n")
    w(os.path.join(out, "system", "fvSchemes"), hdr("dictionary", "fvSchemes") +
      "\nddtSchemes { default steadyState; }\ngradSchemes { default Gauss linear; }\ndivSchemes { default none; }\n"
      "laplacianSchemes { default Gauss linear corrected; }\ninterpolationSchemes { default linear; }\n"
      "snGradSchemes { default corrected; }\n")
    w(os.path.join(out, "system", "decomposeParDict"), hdr("dictionary", "decomposeParDict") +
      f"\nnumberOfSubdomains {n_proc};\n\nmethod          scotch;\n")
    w(os.path.join(out, "system", "functions"), hdr("dictionary", "functions", "system") + FUNCTIONS)
    w(os.path.join(out, "system", "fluid", "fvSchemes"), hdr("dictionary", "fvSchemes", "system/fluid") + FLUID_SCHEMES)
    w(os.path.join(out, "system", "fluid", "fvSolution"), hdr("dictionary", "fvSolution", "system/fluid") + FLUID_SOLUTION)
    w(os.path.join(out, "system", "solid", "fvSchemes"), hdr("dictionary", "fvSchemes", "system/solid") + SOLID_SCHEMES)
    w(os.path.join(out, "system", "solid", "fvSolution"), hdr("dictionary", "fvSolution", "system/solid") + SOLID_SOLUTION)

    w(os.path.join(out, "constant", "fluid", "physicalProperties"), hdr("dictionary", "physicalProperties", "constant/fluid") + AIR_PROPS)
    w(os.path.join(out, "constant", "fluid", "momentumTransport"), hdr("dictionary", "momentumTransport", "constant/fluid") +
      "\nsimulationType RAS;\n\nRAS\n{\n    model           kOmegaSST;\n    turbulence      on;\n    printCoeffs     on;\n}\n")
    w(os.path.join(out, "constant", "fluid", "thermophysicalTransport"), hdr("dictionary", "thermophysicalTransport", "constant/fluid") +
      "\nRAS\n{\n    model           eddyDiffusivity;\n    Prt             0.85;\n}\n")
    w(os.path.join(out, "constant", "fluid", "g"), hdr("uniformDimensionedVectorField", "g", "constant/fluid") +
      "\ndimensions      [0 1 -2 0 0 0 0];\nvalue           (0 0 0);\n")
    w(os.path.join(out, "constant", "fluid", "pRef"), hdr("uniformDimensionedScalarField", "pRef", "constant/fluid") +
      f"\ndimensions      [1 -1 -2 0 0 0 0];\nvalue           {P_REF:g};\n")
    w(os.path.join(out, "constant", "solid", "physicalProperties"), hdr("dictionary", "physicalProperties", "constant/solid") +
      solid_props(dom.kappa_solid, dom.rho_solid))

    for name, text in fluid_fields(V, k_in, omega_in, L_mix, dom.T_in_K).items():
        w(os.path.join(out, "0", "fluid", name), text)
    w(os.path.join(out, "0", "solid", "T"), solid_T(q_flux, dom.kappa_solid, dom.T_in_K))

    w(os.path.join(out, "Allmesh"), allmesh(flavour), executable=True)
    w(os.path.join(out, "Allrun"), allrun(n_proc), executable=True)
    return {"duct_height_m": H, "q_flux_W_m2": q_flux, "k_in": k_in, "omega_in": omega_in}


def _place_stl(src_stl: str, out: str, flavour: str) -> None:
    os.makedirs(os.path.join(out, "constant", "geometry"), exist_ok=True)
    shutil.copy(src_stl, os.path.join(out, "constant", "geometry", "heatsink.stl"))
    if flavour == "esi":   # v1912 looks in constant/triSurface
        os.makedirs(os.path.join(out, "constant", "triSurface"), exist_ok=True)
        shutil.copy(src_stl, os.path.join(out, "constant", "triSurface", "heatsink.stl"))


def write_case(spec: HeatSinkSpec, V: float, mesh: str, out: str, n_proc: int = 6,
               n_iter: int = 1500, flavour: str = "org", n_layers: int = 4) -> dict:
    """Parametric designs (pin and plate arrays), exactly as in the study."""
    is_plate = isinstance(spec, PlateFinSpec)
    meta = platefin_metadata(spec) if is_plate else metadata(spec)
    dom = domain_for_spec(spec)
    level = MESH_LEVELS[mesh]
    os.makedirs(out, exist_ok=True)
    geom_dir = os.path.join(out, "geometry")
    (export_platefin if is_plate else export_all)(spec, geom_dir)
    _place_stl(os.path.join(geom_dir, "heatsink_snappy.stl"), out, flavour)
    derived = _write_case_files(dom, V, level, out, n_proc, n_iter, flavour, n_layers, mesh)

    pred = None if is_plate else analytic_solve(meta, V)
    case_meta = {
        "spec": {**meta["spec"], "layout": spec.layout}, "name": spec.name, "V": V, "mesh": mesh, "n_proc": n_proc,
        "n_iter": n_iter, "flavour": flavour, "n_layers": n_layers, "duct_height_m": derived["duct_height_m"],
        "q_flux_W_m2": derived["q_flux_W_m2"],
        "k_in": derived["k_in"], "omega_in": derived["omega_in"], "n_pins": meta.get("n_pins", meta.get("n_fins")),
        "n_rows": meta.get("n_rows"), "fin_mass_g": meta["fin_mass_g"], "kind": "plate" if is_plate else "pin",
        "analytic": {k: pred[k] for k in ("R_total_K_W", "R_conv_K_W", "R_base_K_W", "dP_Pa",
                                           "T_chip_max_C", "Re_max", "h_W_m2K", "eta_fin")} if pred else {},
    }
    with open(os.path.join(out, "case.json"), "w") as f:
        json.dump(case_meta, f, indent=2)
    return case_meta


def cad_mesh_level(min_feature_mm: float, mesh: str, base_cell: float = BASE_CELL, surf_override: int | None = None) -> dict:
    """Surface refinement for an imported sink: the coarse level puts about 2.5 cells across the thinnest
    feature (3 mm background cell, 2 mm pin -> level 2 = 0.75 mm cells; 1.5 mm plate -> level 3). Medium is
    one level finer and fine two (as in MESH_LEVELS); box levels follow the study's table."""
    cell_mm = base_cell * 1e3
    base = max(2, min(4, math.ceil(math.log2(cell_mm / (min_feature_mm / 2.5)))))
    if surf_override is not None:
        base = surf_override
    offs = {"coarse": 0, "medium": 1, "fine": 2}[mesh]
    return {**MESH_LEVELS[mesh], "surf": base + offs}


def find_solid_point(snappy_stl: str, L: float, W: float, base_t: float) -> tuple:
    """A point inside the base slab of the embedded STL (metres). The base centre is tried first; a sink with a
    hole or a pocket there gets the first point of a 7 x 7 grid over the footprint that is inside."""
    import numpy as np
    import trimesh
    mesh = trimesh.load(snappy_stl, force="mesh")
    z = base_t / 2 + 0.0001
    cands = [(L / 2 + 0.0005, W / 2 + 0.0005)]
    cands += [(L * (i + 0.5) / 7 + 0.0005, W * (j + 0.5) / 7 + 0.0005) for i in range(7) for j in range(7)]
    pts = np.array([(x, y, z) for x, y in cands])
    inside = mesh.contains(pts)
    if not inside.any():
        raise RuntimeError("no point inside the base slab was found for the solid region")
    return tuple(float(v) for v in pts[int(np.argmax(inside))])


def domain_from_model(model, chip_mm: tuple, chip_offset_mm: tuple = (0.0, 0.0), power_W: float = Q_CHIP,
                      material: str = "aluminium", base_cell: float = BASE_CELL) -> DomainSpec:
    """DomainSpec for an imported sink (src.cad_import.SinkModel). chip_mm = (size_x, size_y)."""
    from src import cad_import
    x0, y0, x1, y1 = cad_import.chip_rect(model, chip_mm, chip_offset_mm)       # mm, refuses a chip that does not fit
    kappa, rho = MATERIALS[material]
    mm = 1e-3
    dom = DomainSpec(L=model.L * mm, W=model.W * mm, base_t=model.base_t * mm, h=model.h * mm,
                     chip_x0=x0 * mm, chip_x1=x1 * mm, chip_y0=y0 * mm, chip_y1=y1 * mm,
                     power_W=power_W, kappa_solid=kappa, rho_solid=rho, base_cell=base_cell,
                     tip_gap=model.tip_gap_mm * mm)
    dom.solid_point = find_solid_point(model.snappy_stl, dom.L, dom.W, dom.base_t)
    return dom


def write_case_from_model(model, dom: DomainSpec, V: float, mesh: str, out: str, n_proc: int = 6,
                          n_iter: int = 1500, flavour: str = "org", n_layers: int = 4,
                          surf_level: int | None = None) -> dict:
    """An imported heat sink (src.cad_import.SinkModel): its embedded STL is used as is."""
    level = cad_mesh_level(model.min_feature_mm, mesh, dom.base_cell, surf_level)
    os.makedirs(out, exist_ok=True)
    _place_stl(model.snappy_stl, out, flavour)
    derived = _write_case_files(dom, V, level, out, n_proc, n_iter, flavour, n_layers, mesh)
    stem = os.path.splitext(os.path.basename(model.source))[0]
    case_meta = {
        "spec": {"source": model.source}, "name": stem, "V": V, "mesh": mesh, "n_proc": n_proc, "n_iter": n_iter,
        "flavour": flavour, "n_layers": n_layers, "duct_height_m": derived["duct_height_m"],
        "q_flux_W_m2": derived["q_flux_W_m2"], "k_in": derived["k_in"], "omega_in": derived["omega_in"],
        "n_pins": model.n_fins, "n_rows": None, "kind": "cad", "analytic": {},
        "fin_mass_g": model.fin_volume_mm3 * dom.rho_solid * 1e-6,
        "surf_level": level["surf"], "power_W": dom.power_W, "T_in_K": dom.T_in_K,
        "kappa_solid": dom.kappa_solid, "rho_solid": dom.rho_solid,
        "chip_m": [dom.chip_x0, dom.chip_y0, dom.chip_x1, dom.chip_y1], "tip_gap_mm": model.tip_gap_mm,
        "model": model.to_dict(),
    }
    with open(os.path.join(out, "case.json"), "w") as f:
        json.dump(case_meta, f, indent=2)
    return case_meta


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--d", type=float)
    ap.add_argument("--pd", type=float)
    ap.add_argument("--h", type=float, required=True)
    ap.add_argument("--layout", choices=["inline", "staggered", "plate"], required=True)
    ap.add_argument("--plate-t", type=float, default=1.5, help="plate-fin thickness, mm (layout=plate)")
    ap.add_argument("--plate-n", type=int, default=None, help="number of plate fins (layout=plate)")
    ap.add_argument("--match-mass", type=float, default=None, help="plate fins sized to this fin mass, g")
    ap.add_argument("--V", type=float, default=4.0)
    ap.add_argument("--mesh", choices=list(MESH_LEVELS), default="coarse")
    ap.add_argument("--np", type=int, default=6)
    ap.add_argument("--iters", type=int, default=1500)
    ap.add_argument("--flavour", choices=["org", "esi"], default="org")
    ap.add_argument("--layers", type=int, default=4, help="prism layers on the heat sink surface (fluid side)")
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    if a.layout == "plate":
        from src.geometry import platefin_for_mass
        spec = platefin_for_mass(a.match_mass, a.h, a.plate_t) if a.match_mass else PlateFinSpec(a.plate_t, a.plate_n, a.h)
    else:
        spec = HeatSinkSpec(a.d, a.pd, a.h, a.layout)
    m = write_case(spec, a.V, a.mesh, a.out, a.np, a.iters, a.flavour, a.layers)
    an = m["analytic"]
    print(f"wrote {a.out}: {m['name']} V={a.V} mesh={a.mesh} np={a.np} iters={a.iters}" +
          (f"; analytic R={an['R_total_K_W']:.3f} K/W dP={an['dP_Pa']:.1f} Pa" if an else ""))


if __name__ == "__main__":
    main()
