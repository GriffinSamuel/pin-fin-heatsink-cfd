# Pin-fin heat sink CFD optimisation. Run inside WSL/Linux with OpenFOAM 14 sourced:
#   source /opt/openfoam14/etc/bashrc
PY ?= .venv/bin/python
NP ?= 6

.PHONY: venv test quick geometry analytic coarse sweep analysis surrogate visuals clean

venv:
	python3 -m venv .venv && .venv/bin/pip install -U pip wheel && .venv/bin/pip install -r requirements.txt

test:
	$(PY) -m pytest -q tests

geometry:
	$(PY) -m src.geometry --d 3 --pd 2.2 --h 35 --layout staggered

analytic:
	$(PY) -m src.analytic --d 3 --pd 2.2 --h 35 --layout staggered

# one coarse CFD case of the centre design (about 5 minutes on 6 cores)
coarse:
	$(PY) -m src.make_case --d 3 --pd 2.2 --h 35 --layout staggered --V 4 --mesh coarse --np $(NP) --iters 300 --out work/cases/center_coarse
	cd work/cases/center_coarse && ./Allrun
	$(PY) -m src.results work/cases/center_coarse

# reproduce the unit tests, the geometry, the hand calculation and one coarse CFD case
quick: test geometry analytic coarse

sweep:
	$(PY) -m src.sweep --mesh coarse --V 4 --np 8 --jobs 1 --iters 600

analysis:
	$(PY) -m src.analysis --csv results/sweep.csv --out results --fig figures --docs docs

surrogate:
	$(PY) -m src.surrogate --csv results/sweep.csv --out results --docs docs

visuals:
	xvfb-run -a $(PY) -m src.visuals --case $(CASE) --out figures

clean:
	rm -rf work/cases work/sweep
