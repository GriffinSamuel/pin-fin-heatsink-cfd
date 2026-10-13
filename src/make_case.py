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

from src.geometry import HeatSinkSpec, export_all, metadata
from src.analytic import solve as analytic_solve

T_IN = 298.15           # K (25 C)
Q_CHIP = 100.0          # W
KAPPA_AL = 200.0        # W/m-K
P_REF = 1e5             # Pa
X_SPLITS = [-0.060, 0.015, 0.045, 0.180]      # m, chip footprint 0.015..0.045
Y_SPLITS = [0.000, 0.015, 0.045, 0.060]
BASE_CELL = 0.003       # m, background cell size
NX = [25, 10, 45]
NY = [5, 10, 5]

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

def block_mesh_dict(H: float) -> str:
    X, Y, Z = X_SPLITS, Y_SPLITS, [0.0, H]
    nz = max(4, round(H / BASE_CELL))

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

def snappy_dict(H: float, level: dict, flavour: str) -> str:
    zone_mode = ("mode        insidePoint;\n            insidePoint (0.030 0.030 0.002);" if flavour == "org"
                 else "cellZoneInside insidePoint;\n            insidePoint (0.030 0.030 0.002);")
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
    hmid = H / 2
    return hdr("dictionary", "snappyHexMeshDict") + f"""
{include}

castellatedMesh true;
snap            true;
addLayers       false;

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
        min (-0.012 -0.001 -0.001);
        max ( 0.085  0.061  {H + 0.001:.4f});
    }}
    pinBox
    {{
        type box;
        min (-0.003 -0.001 0.003);
        max ( 0.066  0.061  {H + 0.001:.4f});
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
            faceZone heatsink;
            cellZone solid;
            {zone_mode}
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

    {inside_key} (-0.030 0.030 {hmid:.4f});
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
    }}
    expansionRatio 1.2;
    finalLayerThickness 0.4;
    minThickness 0.1;
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


def fluid_fields(V: float, k_in: float, omega_in: float, mixing_length: float) -> dict:
    sct = '    #includeEtc "caseDicts/setConstraintTypes"'
    return {
        "U": field("volVectorField", "U", "[0 1 -1 0 0 0 0]", "uniform (0 0 0)", f"""
    ".*"            {{ type noSlip; }}
    inlet           {{ type fixedValue; value uniform ({V} 0 0); }}
    outlet          {{ type pressureInletOutletVelocity; value uniform (0 0 0); }}
{sct}""", "fluid"),
        "T": field("volScalarField", "T", "[0 0 0 1 0 0 0]", f"uniform {T_IN}", f"""
    ".*"            {{ type zeroGradient; }}
    inlet           {{ type fixedValue; value uniform {T_IN}; }}
    outlet          {{ type inletOutlet; inletValue uniform {T_IN}; value uniform {T_IN}; }}
    fluid_to_solid  {{ type coupledTemperature; value uniform {T_IN}; }}
{sct}""", "fluid"),
        "p": field("volScalarField", "p", "[1 -1 -2 0 0 0 0]", f"uniform {P_REF:g}", f"""
    ".*"            {{ type fixedFluxPressure; value $internalField; }}
    outlet          {{ type totalPressure; p0 $internalField; value $internalField; }}
{sct}""", "fluid"),
        "k": field("volScalarField", "k", "[0 2 -2 0 0 0 0]", f"uniform {k_in:.4g}", f"""
    ".*"            {{ type kqRWallFunction; value $internalField; }}
    inlet           {{ type turbulentKineticEnergy; intensity 0.05; value $internalField; }}
    outlet          {{ type inletOutlet; inletValue $internalField; value $internalField; }}
{sct}""", "fluid"),
        "omega": field("volScalarField", "omega", "[0 0 -1 0 0 0 0]", f"uniform {omega_in:.4g}", f"""
    ".*"            {{ type omegaWallFunction; value $internalField; }}
    inlet           {{ type turbulentOmega; mixingLength {mixing_length:.4g}; value $internalField; }}
    outlet          {{ type inletOutlet; inletValue $internalField; value $internalField; }}
{sct}""", "fluid"),
        "nut": field("volScalarField", "nut", "[0 2 -1 0 0 0 0]", "uniform 0", f"""
    ".*"            {{ type nutkWallFunction; value uniform 0; }}
    inlet           {{ type calculated; value uniform 0; }}
    outlet          {{ type calculated; value uniform 0; }}
{sct}""", "fluid"),
        "alphat": field("volScalarField", "alphat", "[1 -1 -1 0 0 0 0]", "uniform 0", f"""
    ".*"            {{ type compressible::alphatWallFunction; value uniform 0; }}
    inlet           {{ type calculated; value uniform 0; }}
    outlet          {{ type calculated; value uniform 0; }}
{sct}""", "fluid"),
    }


def solid_T(q_flux: float) -> str:
    grad = q_flux / KAPPA_AL
    return field("volScalarField", "T", "[0 0 0 1 0 0 0]", f"uniform {T_IN + 20}", f"""
    ".*"            {{ type zeroGradient; }}
    chip            {{ type fixedGradient; gradient uniform {grad:.6g}; }}
    solid_to_fluid  {{ type coupledTemperature; value uniform {T_IN + 20}; }}
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

AL_PROPS = f"""
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
        kappa       {KAPPA_AL:g};
    }}
    thermodynamics
    {{
        hf          0;
        Cv          900;
    }}
    equationOfState
    {{
        rho         2700;
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
    div(phi,k)      bounded Gauss limitedLinear 1;
    div(phi,omega)  bounded Gauss limitedLinear 1;
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
        U               1e-5;
        h               1e-5;
        "(k|omega)"     1e-4;
    }
}

relaxationFactors
{
    fields
    {
        rho             1.0;
        p               0.3;
    }
    equations
    {
        U               0.7;
        h               0.7;
        "(k|omega)"     0.7;
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

runApplication blockMesh
runApplication snappyHexMesh
runApplication splitMeshRegions -cellZones all -defaultRegion fluid
runApplication -s fluid checkMesh -region fluid -constant
runApplication -s solid checkMesh -region solid -constant
"""
    # OpenFOAM v1912 (ESI) flavour, used only for local mesh testing
    return """
#!/bin/sh
cd ${0%/*} || exit 1
. ${WM_PROJECT_DIR:-/usr/share/openfoam}/bin/tools/RunFunctions 2>/dev/null || true
run() { name=$1; shift; echo "Running $name"; "$name" "$@" > log.$name 2>&1 || { echo "FAILED: $name (see log.$name)"; exit 1; }; }
rm -rf constant/polyMesh/sets
run blockMesh
run snappyHexMesh -overwrite
run splitMeshRegions -cellZones -defaultRegionName fluid -overwrite
checkMesh -region fluid -constant > log.checkMesh.fluid 2>&1
checkMesh -region solid -constant > log.checkMesh.solid 2>&1
"""


def allrun(n_proc: int) -> str:
    return f"""
#!/bin/sh
cd ${{0%/*}} || exit 1    # Run from this directory

# Source tutorial run functions
. $WM_PROJECT_DIR/bin/tools/RunFunctions

./Allmesh || exit 1

runApplication decomposePar -allRegions
runParallel foamMultiRun
runApplication reconstructPar -allRegions -latestTime
rm -rf processor*
"""


def write_case(spec: HeatSinkSpec, V: float, mesh: str, out: str, n_proc: int = 6,
               n_iter: int = 1500, flavour: str = "org") -> dict:
    meta = metadata(spec)
    H = (spec.base_t + spec.h) * 1e-3
    level = MESH_LEVELS[mesh]
    os.makedirs(out, exist_ok=True)
    geom_dir = os.path.join(out, "geometry")
    export_all(spec, geom_dir)
    os.makedirs(os.path.join(out, "constant", "geometry"), exist_ok=True)
    shutil.copy(os.path.join(geom_dir, "heatsink_snappy.stl"), os.path.join(out, "constant", "geometry", "heatsink.stl"))
    if flavour == "esi":   # v1912 looks in constant/triSurface
        os.makedirs(os.path.join(out, "constant", "triSurface"), exist_ok=True)
        shutil.copy(os.path.join(geom_dir, "heatsink_snappy.stl"), os.path.join(out, "constant", "triSurface", "heatsink.stl"))

    # inlet turbulence: 5 % intensity, mixing length 7 % of the duct hydraulic diameter
    A = 0.060 * H
    Dh = 4 * A / (2 * (0.060 + H))
    k_in = 1.5 * (0.05 * V) ** 2
    L_mix = 0.07 * Dh
    omega_in = math.sqrt(k_in) / (0.09 ** 0.25 * L_mix)
    q_flux = Q_CHIP / 0.03 ** 2

    w(os.path.join(out, "system", "blockMeshDict"), block_mesh_dict(H))
    w(os.path.join(out, "system", "snappyHexMeshDict"), snappy_dict(H, level, flavour))
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
    w(os.path.join(out, "system", "functions"), FUNCTIONS)
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
    w(os.path.join(out, "constant", "solid", "physicalProperties"), hdr("dictionary", "physicalProperties", "constant/solid") + AL_PROPS)

    for name, text in fluid_fields(V, k_in, omega_in, L_mix).items():
        w(os.path.join(out, "0", "fluid", name), text)
    w(os.path.join(out, "0", "solid", "T"), solid_T(q_flux))

    w(os.path.join(out, "Allmesh"), allmesh(flavour), executable=True)
    w(os.path.join(out, "Allrun"), allrun(n_proc), executable=True)

    pred = analytic_solve(meta, V)
    case_meta = {
        "spec": meta["spec"], "name": spec.name, "V": V, "mesh": mesh, "n_proc": n_proc,
        "n_iter": n_iter, "flavour": flavour, "duct_height_m": H, "q_flux_W_m2": q_flux,
        "k_in": k_in, "omega_in": omega_in, "n_pins": meta["n_pins"], "n_rows": meta["n_rows"],
        "fin_mass_g": meta["fin_mass_g"],
        "analytic": {k: pred[k] for k in ("R_total_K_W", "R_conv_K_W", "R_base_K_W", "dP_Pa",
                                           "T_chip_max_C", "Re_max", "h_W_m2K", "eta_fin")},
    }
    with open(os.path.join(out, "case.json"), "w") as f:
        json.dump(case_meta, f, indent=2)
    return case_meta


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--d", type=float, required=True)
    ap.add_argument("--pd", type=float, required=True)
    ap.add_argument("--h", type=float, required=True)
    ap.add_argument("--layout", choices=["inline", "staggered"], required=True)
    ap.add_argument("--V", type=float, default=4.0)
    ap.add_argument("--mesh", choices=list(MESH_LEVELS), default="coarse")
    ap.add_argument("--np", type=int, default=6)
    ap.add_argument("--iters", type=int, default=1500)
    ap.add_argument("--flavour", choices=["org", "esi"], default="org")
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    spec = HeatSinkSpec(a.d, a.pd, a.h, a.layout)
    m = write_case(spec, a.V, a.mesh, a.out, a.np, a.iters, a.flavour)
    print(f"wrote {a.out}: {m['name']} V={a.V} mesh={a.mesh} np={a.np} iters={a.iters}; "
          f"analytic R={m['analytic']['R_total_K_W']:.3f} K/W dP={m['analytic']['dP_Pa']:.1f} Pa")


if __name__ == "__main__":
    main()
