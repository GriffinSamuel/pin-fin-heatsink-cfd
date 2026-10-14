"""Regression oracle for the DomainSpec refactor of src/make_case.py (PLAN_CAD.md step 4).

tests/golden/* hold the dictionaries written by the pre-refactor code. The parametric path must keep writing
byte-identical system/, 0/ and constant/ files (the triSurface STL is not compared)."""
import filecmp
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import make_case as mc  # noqa: E402

GOLD = os.path.join(os.path.dirname(os.path.abspath(__file__)), "golden")

CASES = {
    "centre": ["--d", "3", "--pd", "2.2", "--h", "35", "--layout", "staggered"],
    "plate": ["--layout", "plate", "--plate-t", "1.5", "--plate-n", "9", "--h", "35"],
    "pin_inline_esi": ["--d", "3.7", "--pd", "1.8", "--h", "35", "--layout", "inline", "--flavour", "esi"],
}


def _files(root, sub):
    out = []
    for dp, _, fs in os.walk(os.path.join(root, sub)):
        for f in fs:
            if f.endswith((".stl", ".step")):
                continue
            out.append(os.path.relpath(os.path.join(dp, f), root))
    return sorted(out)


@pytest.mark.parametrize("name", list(CASES))
def test_dictionaries_unchanged(name, tmp_path):
    out = str(tmp_path / name)
    mc.main(CASES[name] + ["--V", "4", "--mesh", "coarse", "--np", "6", "--iters", "1500", "--out", out])
    gold = os.path.join(GOLD, name)
    for sub in ("system", "0", "constant"):
        a, b = _files(gold, sub), _files(out, sub)
        assert a == b, f"{name}/{sub}: file lists differ"
        for rel in a:
            assert filecmp.cmp(os.path.join(gold, rel), os.path.join(out, rel), shallow=False), f"{name}: {rel} differs"
    for f in ("Allmesh", "Allrun"):
        assert filecmp.cmp(os.path.join(gold, f), os.path.join(out, f), shallow=False), f"{name}: {f} differs"


def test_blocking_counts():
    dom = mc.domain_for_spec(mc.HeatSinkSpec(3, 2.2, 35, "staggered"))
    assert dom.nx == [25, 10, 45] and dom.ny == [5, 10, 5]
