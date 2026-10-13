"""Translate a generated OpenFOAM-14 case (after meshing with the 'esi' flavour) into an
OpenFOAM v1912 chtMultiRegionSimpleFoam case, for local solver testing only.

The physics is identical (same mesh, materials, BCs, flux); only file names, solver and
keyword spellings differ. Usage: python scripts/to_esi.py work/cases/test_esi_coarse
"""
from __future__ import annotations

import os
import re
import sys

case = sys.argv[1]
n_iter = int(sys.argv[2]) if len(sys.argv) > 2 else 300

HDR = """FoamFile
{{
    version     2.0;
    format      ascii;
    class       {cls};
    object      {obj};
}}
"""


def w(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(text)


# 1. rename region domain0 -> fluid in the mesh and the interface patch names
d0 = os.path.join(case, "constant", "domain0")
if os.path.isdir(d0):
    import shutil
    os.makedirs(os.path.join(case, "constant", "fluid"), exist_ok=True)
    shutil.rmtree(os.path.join(case, "constant", "fluid", "polyMesh"), ignore_errors=True)
    shutil.move(os.path.join(d0, "polyMesh"), os.path.join(case, "constant", "fluid", "polyMesh"))
    shutil.rmtree(d0, ignore_errors=True)
for reg in ("fluid", "solid"):
    p = os.path.join(case, "constant", reg, "polyMesh", "boundary")
    s = open(p).read().replace("domain0_to_solid", "fluid_to_solid").replace("solid_to_domain0", "solid_to_fluid")
    s = re.sub(r"sampleRegion\s+domain0;", "sampleRegion     fluid;", s)
    open(p, "w").write(s)

# 2. region properties, control, schemes, solution
w(os.path.join(case, "constant", "regionProperties"), HDR.format(cls="dictionary", obj="regionProperties") + """
regions
(
    fluid       (fluid)
    solid       (solid)
);
""")
w(os.path.join(case, "system", "controlDict"), HDR.format(cls="dictionary", obj="controlDict") + f"""
application     chtMultiRegionSimpleFoam;
startFrom       latestTime;
startTime       0;
stopAt          endTime;
endTime         {n_iter};
deltaT          1;
writeControl    timeStep;
writeInterval   {n_iter};
purgeWrite      1;
writeFormat     ascii;
writePrecision  8;
writeCompression off;
timeFormat      general;
timePrecision   6;
runTimeModifiable true;

functions
{{
    TmaxSolid {{ type volFieldValue; libs (fieldFunctionObjects); region solid; regionType all;
                operation max; fields (T); writeControl timeStep; writeInterval 10; writeFields false; log true; }}
    TavgChip  {{ type surfaceFieldValue; libs (fieldFunctionObjects); region solid; regionType patch; name chip;
                operation areaAverage; fields (T); writeControl timeStep; writeInterval 10; writeFields false; log true; }}
    pIn       {{ type surfaceFieldValue; libs (fieldFunctionObjects); region fluid; regionType patch; name inlet;
                operation areaAverage; fields (p); writeControl timeStep; writeInterval 10; writeFields false; log true; }}
    pOut      {{ type surfaceFieldValue; libs (fieldFunctionObjects); region fluid; regionType patch; name outlet;
                operation areaAverage; fields (p); writeControl timeStep; writeInterval 10; writeFields false; log true; }}
    TOut      {{ type surfaceFieldValue; libs (fieldFunctionObjects); region fluid; regionType patch; name outlet;
                operation areaAverage; fields (T); writeControl timeStep; writeInterval 10; writeFields false; log true; }}
    mdot      {{ type surfaceFieldValue; libs (fieldFunctionObjects); region fluid; regionType patch; name inlet;
                operation sum; fields (phi); writeControl timeStep; writeInterval 10; writeFields false; log true; }}
    qChip     {{ type wallHeatFlux; libs (fieldFunctionObjects); region solid; patches (chip);
                executeControl timeStep; executeInterval 10; writeControl none; log true; }}
    qIface    {{ type wallHeatFlux; libs (fieldFunctionObjects); region fluid; patches (fluid_to_solid);
                executeControl timeStep; executeInterval 10; writeControl none; log true; }}
}}
""")
w(os.path.join(case, "system", "fluid", "fvSchemes"), HDR.format(cls="dictionary", obj="fvSchemes") + """
ddtSchemes      { default steadyState; }
gradSchemes     { default Gauss linear; limited cellLimited Gauss linear 1; grad(U) $limited; grad(k) $limited; grad(omega) $limited; }
divSchemes
{
    default         none;
    div(phi,U)      bounded Gauss linearUpwind limited;
    div(phi,K)      bounded Gauss limitedLinear 1;
    div(phi,h)      bounded Gauss limitedLinear 1;
    div(phi,k)      bounded Gauss upwind;
    div(phi,omega)  bounded Gauss upwind;
    div(phi,Ekp)    bounded Gauss limitedLinear 1;
    div(((rho*nuEff)*dev2(T(grad(U))))) Gauss linear;
}
laplacianSchemes { default Gauss linear limited corrected 0.5; }
interpolationSchemes { default linear; }
snGradSchemes   { default limited corrected 0.5; }
wallDist        { method meshWave; }
""")
w(os.path.join(case, "system", "fluid", "fvSolution"), HDR.format(cls="dictionary", obj="fvSolution") + """
solvers
{
    rho             { solver PCG; preconditioner DIC; tolerance 1e-7; relTol 0.1; }
    p_rgh           { solver GAMG; smoother GaussSeidel; tolerance 1e-7; relTol 0.01; maxIter 100; }
    "(U|h|k|omega)" { solver PBiCGStab; preconditioner DILU; tolerance 1e-7; relTol 0.1; minIter 1; }
}
SIMPLE
{
    momentumPredictor yes;
    nNonOrthogonalCorrectors 0;
    pRefCell        0;
    pRefValue       1e5;
    rhoMin          0.5;
    rhoMax          2.0;
    residualControl { p_rgh 1e-4; U 1e-5; h 1e-5; "(k|omega)" 1e-4; }
}
relaxationFactors
{
    fields    { rho 1.0; p_rgh 0.7; }
    equations { U 0.3; h 0.7; "(k|omega)" 0.3; }
}
""")
w(os.path.join(case, "system", "solid", "fvSchemes"), HDR.format(cls="dictionary", obj="fvSchemes") + """
ddtSchemes      { default steadyState; }
gradSchemes     { default Gauss linear; }
divSchemes      { default none; }
laplacianSchemes { default Gauss linear corrected; }
interpolationSchemes { default linear; }
snGradSchemes   { default corrected; }
""")
w(os.path.join(case, "system", "solid", "fvSolution"), HDR.format(cls="dictionary", obj="fvSolution") + """
solvers
{
    h { solver PCG; preconditioner DIC; tolerance 1e-8; relTol 0.01; }
}
SIMPLE { nNonOrthogonalCorrectors 1; }
relaxationFactors { equations { h 1; } }
""")
w(os.path.join(case, "system", "fvSolution"), HDR.format(cls="dictionary", obj="fvSolution") + "\nSIMPLE {}\n")

# 3. constant: properties
w(os.path.join(case, "constant", "fluid", "thermophysicalProperties"), HDR.format(cls="dictionary", obj="thermophysicalProperties") + """
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
    specie         { molWeight 28.96; }
    thermodynamics { Cp 1006; Hf 0; }
    transport      { mu 1.85e-05; Pr 0.707; }
}
""")
w(os.path.join(case, "constant", "fluid", "turbulenceProperties"), HDR.format(cls="dictionary", obj="turbulenceProperties") + """
simulationType  RAS;
RAS { RASModel kOmegaSST; turbulence on; printCoeffs on; }
""")
w(os.path.join(case, "constant", "fluid", "radiationProperties"), HDR.format(cls="dictionary", obj="radiationProperties") + "\nradiationModel  none;\n")
w(os.path.join(case, "constant", "fluid", "g"), HDR.format(cls="uniformDimensionedVectorField", obj="g") + "\ndimensions [0 1 -2 0 0 0 0];\nvalue (0 0 0);\n")
w(os.path.join(case, "constant", "solid", "thermophysicalProperties"), HDR.format(cls="dictionary", obj="thermophysicalProperties") + """
thermoType
{
    type            heSolidThermo;
    mixture         pureMixture;
    transport       constIso;
    thermo          hConst;
    equationOfState rhoConst;
    specie          specie;
    energy          sensibleEnthalpy;
}
mixture
{
    specie          { molWeight 27; }
    transport       { kappa 200; }
    thermodynamics  { Hf 0; Cp 900; }
    equationOfState { rho 2700; }
}
""")
w(os.path.join(case, "constant", "solid", "radiationProperties"), HDR.format(cls="dictionary", obj="radiationProperties") + "\nradiationModel  none;\n")

# 4. fields: adapt the generated OpenFOAM-14 files
f0 = os.path.join(case, "0", "fluid")
for name in os.listdir(f0):
    p = os.path.join(f0, name)
    s = open(p).read()
    s = s.replace("type coupledTemperature;", "type compressible::turbulentTemperatureCoupledBaffleMixed; Tnbr T; kappaMethod fluidThermo;")
    s = s.replace('#includeEtc "caseDicts/setConstraintTypes"', "sides { type symmetry; }")
    s = s.replace("type turbulentKineticEnergy;", "type turbulentIntensityKineticEnergyInlet;")
    s = s.replace("type turbulentOmega;", "type turbulentMixingLengthFrequencyInlet;")
    if name == "p":
        s = re.sub(r"boundaryField\s*\{.*\}", 'boundaryField\n{\n    ".*" { type calculated; value $internalField; }\n    sides { type symmetry; }\n}', s, flags=re.S)
    open(p, "w").write(s)
# p_rgh for the fluid
w(os.path.join(f0, "p_rgh"), HDR.format(cls="volScalarField", obj="p_rgh") + """
dimensions      [1 -1 -2 0 0 0 0];
internalField   uniform 1e5;
boundaryField
{
    ".*"            { type fixedFluxPressure; value $internalField; }
    outlet          { type fixedValue; value $internalField; }
    sides           { type symmetry; }
}
""")
s0 = os.path.join(case, "0", "solid")
p = os.path.join(s0, "T")
s = open(p).read()
s = s.replace("type coupledTemperature;", "type compressible::turbulentTemperatureCoupledBaffleMixed; Tnbr T; kappaMethod solidThermo;")
s = s.replace('#includeEtc "caseDicts/setConstraintTypes"', "sides { type symmetry; }")
open(p, "w").write(s)
w(os.path.join(s0, "p"), HDR.format(cls="volScalarField", obj="p") + """
dimensions      [1 -1 -2 0 0 0 0];
internalField   uniform 1e5;
boundaryField
{
    ".*"            { type calculated; value $internalField; }
    sides           { type symmetry; }
}
""")
# remove the splitMeshRegions helper field, which the reader cannot parse
for junk in ("cellToRegion",):
    jp = os.path.join(case, "0", junk)
    if os.path.exists(jp):
        os.remove(jp)
print("esi case ready:", case)
