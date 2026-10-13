"""Surrogate model (T8): a small MLP that predicts thermal resistance R and pressure drop dP
from the design variables (d, p/d, h, layout, V), trained on the CFD sweep, with K-fold
cross-validation, then used to search the continuous design space for the lowest-R design
under a pressure-drop budget. The predicted optimum is meant to be verified with one real
CFD case (see PLAN.md T8).

PyTorch (CUDA when available) is used for training; a NumPy implementation of the same
network is the fallback so the pipeline also runs where torch is not installed.

    .venv/bin/python -m src.surrogate --csv results/sweep.csv --out results --docs docs \
        --dp-budget 150 --verify-out work/cases/surrogate_optimum
"""
from __future__ import annotations

import argparse
import json
import math
import os
import time

import numpy as np
import pandas as pd

try:
    import torch
    import torch.nn as nn
    HAVE_TORCH = True
except Exception:  # pragma: no cover
    HAVE_TORCH = False

# Geometry-derived features: the pin count along the flow (n_rows) and the wetted pin area change in
# integer steps with (d, p/d), so a model of the raw design variables alone cannot see those jumps.
FEATURES = ["d", "pd", "h", "layout_staggered", "V", "n_rows", "log_area"]
TARGETS = ["log_R", "log_dP"]
BOUNDS = {"d": (2.0, 4.0), "pd": (1.8, 2.8), "h": (20.0, 35.0)}


def geom_features(d, pd_, h, layout):
    """n_rows (pins in flow direction) and log of wetted pin side area, from the real geometry generator."""
    from src.geometry import HeatSinkSpec, metadata
    m = metadata(HeatSinkSpec(d=float(d), pd=float(pd_), h=float(h), layout=str(layout)))
    return float(m["n_rows"]), math.log(m["n_pins"] * math.pi * float(d) * float(h))


def frame(df: pd.DataFrame) -> pd.DataFrame:
    d = df.copy()
    g = [geom_features(r.d, r.pd, r.h, r.layout) for r in d.itertuples()]
    d["n_rows"] = [x[0] for x in g]
    d["log_area"] = [x[1] for x in g]
    d["layout_staggered"] = (d["layout"] == "staggered").astype(float)
    if "V" not in d:
        d["V"] = 4.0
    d["log_R"] = np.log(d["R_max_K_W"])
    d["log_dP"] = np.log(d["dP_Pa"])
    return d


class Scaler:
    def fit(self, X):
        self.mu, self.sd = X.mean(0), X.std(0) + 1e-9
        return self

    def t(self, X):
        return (X - self.mu) / self.sd

    def inv(self, Z):
        return Z * self.sd + self.mu


# ---------------------------------------------------------------- NumPy MLP (fallback)

class NumpyMLP:
    """2 hidden layers, tanh, Adam, full-batch. Same architecture as the torch model."""

    def __init__(self, n_in, n_out, width=32, seed=0):
        rng = np.random.default_rng(seed)
        self.W = [rng.normal(0, 1 / math.sqrt(n_in), (n_in, width)), rng.normal(0, 1 / math.sqrt(width), (width, width)),
                  rng.normal(0, 1 / math.sqrt(width), (width, n_out))]
        self.b = [np.zeros(width), np.zeros(width), np.zeros(n_out)]

    def forward(self, X):
        a1 = np.tanh(X @ self.W[0] + self.b[0])
        a2 = np.tanh(a1 @ self.W[1] + self.b[1])
        return a2 @ self.W[2] + self.b[2], (a1, a2)

    def fit(self, X, Y, epochs=3000, lr=5e-3, wd=1e-4):
        params = self.W + self.b
        m = [np.zeros_like(p) for p in params]
        v = [np.zeros_like(p) for p in params]
        b1, b2, eps = 0.9, 0.999, 1e-8
        for t in range(1, epochs + 1):
            out, (a1, a2) = self.forward(X)
            err = out - Y
            g_out = 2 * err / len(X)
            gW2 = a2.T @ g_out; gb2 = g_out.sum(0)
            g2 = (g_out @ self.W[2].T) * (1 - a2 ** 2)
            gW1 = a1.T @ g2; gb1 = g2.sum(0)
            g1 = (g2 @ self.W[1].T) * (1 - a1 ** 2)
            gW0 = X.T @ g1; gb0 = g1.sum(0)
            grads = [gW0 + wd * self.W[0], gW1 + wd * self.W[1], gW2 + wd * self.W[2], gb0, gb1, gb2]
            for i, (p, g) in enumerate(zip(params, grads)):
                m[i] = b1 * m[i] + (1 - b1) * g
                v[i] = b2 * v[i] + (1 - b2) * g * g
                p -= lr * (m[i] / (1 - b1 ** t)) / (np.sqrt(v[i] / (1 - b2 ** t)) + eps)
        return self

    def predict(self, X):
        return self.forward(X)[0]


# ---------------------------------------------------------------- torch MLP

if HAVE_TORCH:
    class TorchMLP(nn.Module):
        def __init__(self, n_in, n_out, width=32):
            super().__init__()
            self.net = nn.Sequential(nn.Linear(n_in, width), nn.Tanh(), nn.Linear(width, width), nn.Tanh(),
                                     nn.Linear(width, n_out))

        def forward(self, x):
            return self.net(x)


def fit_model(X, Y, epochs=3000, seed=0, device=None):
    if HAVE_TORCH:
        dev = device or ("cuda" if torch.cuda.is_available() else "cpu")
        torch.manual_seed(seed)
        model = TorchMLP(X.shape[1], Y.shape[1]).to(dev)
        opt = torch.optim.Adam(model.parameters(), lr=5e-3, weight_decay=1e-4)
        Xt = torch.tensor(X, dtype=torch.float32, device=dev)
        Yt = torch.tensor(Y, dtype=torch.float32, device=dev)
        for _ in range(epochs):
            opt.zero_grad()
            loss = ((model(Xt) - Yt) ** 2).mean()
            loss.backward()
            opt.step()
        model.eval()

        def predict(Xn):
            with torch.no_grad():
                return model(torch.tensor(Xn, dtype=torch.float32, device=dev)).cpu().numpy()
        return predict, dev
    model = NumpyMLP(X.shape[1], Y.shape[1], seed=seed).fit(X, Y, epochs=epochs)
    return model.predict, "numpy"


def cross_validate(df: pd.DataFrame, k: int = 5, epochs: int = 3000, seed: int = 0) -> dict:
    d = frame(df)
    X, Y = d[FEATURES].to_numpy(float), d[TARGETS].to_numpy(float)
    rng = np.random.default_rng(seed)
    idx = rng.permutation(len(X))
    folds = np.array_split(idx, k)
    pred = np.zeros_like(Y)
    for f in folds:
        tr = np.setdiff1d(idx, f)
        sx, sy = Scaler().fit(X[tr]), Scaler().fit(Y[tr])
        predict, _ = fit_model(sx.t(X[tr]), sy.t(Y[tr]), epochs=epochs, seed=seed)
        pred[f] = sy.inv(predict(sx.t(X[f])))
    out = {"k": k, "n": len(X)}
    for j, name in enumerate(["R", "dP"]):
        y, p = np.exp(Y[:, j]), np.exp(pred[:, j])
        ss_res, ss_tot = ((y - p) ** 2).sum(), ((y - y.mean()) ** 2).sum()
        out[f"cv_R2_{name}"] = float(1 - ss_res / ss_tot)
        out[f"cv_mape_{name}_pct"] = float(np.mean(np.abs(p / y - 1)) * 100)
    out["cv_pred"] = np.exp(pred).tolist()
    return out


def optimise(predict, sx, sy, V: float, dp_budget: float) -> dict | None:
    """Exhaustive search over a buildable grid (d 0.1 mm, p/d 0.05, h 1 mm, both layouts)."""
    ds = np.round(np.arange(BOUNDS["d"][0], BOUNDS["d"][1] + 1e-9, 0.1), 1)
    pds = np.round(np.arange(BOUNDS["pd"][0], BOUNDS["pd"][1] + 1e-9, 0.05), 2)
    hs = np.arange(BOUNDS["h"][0], BOUNDS["h"][1] + 1e-9, 1.0)
    grid = []
    for d in ds:
        for pd_ in pds:
            for h in hs:
                for lay in (0.0, 1.0):
                    nr, la = geom_features(d, pd_, h, "staggered" if lay else "inline")
                    grid.append([d, pd_, h, lay, V, nr, la])
    grid = np.array(grid)
    P = np.exp(sy.inv(predict(sx.t(grid))))
    ok = P[:, 1] <= dp_budget
    if not ok.any():
        return None
    i = int(np.argmin(np.where(ok, P[:, 0], np.inf)))
    return {"d": float(grid[i, 0]), "pd": float(grid[i, 1]), "h": float(grid[i, 2]),
            "layout": "staggered" if grid[i, 3] else "inline", "V": V,
            "R_pred": float(P[i, 0]), "dP_pred": float(P[i, 1]), "grid_points": int(len(grid))}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", default="results/sweep.csv")
    ap.add_argument("--out", default="results")
    ap.add_argument("--docs", default="docs")
    ap.add_argument("--dp-budget", type=float, default=150.0)
    ap.add_argument("--V", type=float, default=4.0)
    ap.add_argument("--epochs", type=int, default=3000)
    ap.add_argument("--k", type=int, default=5)
    a = ap.parse_args(argv)
    df = pd.read_csv(a.csv)
    if "status" in df:
        df = df[df["status"] == "ok"]
    df = df.dropna(subset=["R_max_K_W", "dP_Pa"])
    if "mesh" in df:
        df = df[df["mesh"] == "coarse"]
    df = df.reset_index(drop=True)
    t0 = time.time()
    cv = cross_validate(df, k=a.k, epochs=a.epochs)
    d = frame(df)
    X, Y = d[FEATURES].to_numpy(float), d[TARGETS].to_numpy(float)
    sx, sy = Scaler().fit(X), Scaler().fit(Y)
    predict, dev = fit_model(sx.t(X), sy.t(Y), epochs=a.epochs)
    opt = optimise(predict, sx, sy, a.V, a.dp_budget)
    summary = {"device": str(dev), "train_time_s": time.time() - t0, "n_cases": int(len(df)),
               "features": FEATURES, "targets": "log(R), log(dP)", "architecture": "MLP 5-32-32-2 tanh, Adam, 3000 epochs",
               **{k: v for k, v in cv.items() if k != "cv_pred"}, "dp_budget_Pa": a.dp_budget, "optimum": opt}
    os.makedirs(a.out, exist_ok=True); os.makedirs(a.docs, exist_ok=True)
    with open(os.path.join(a.out, "surrogate.json"), "w") as f:
        json.dump(summary, f, indent=2)
    pd.DataFrame({"name": df.get("name", pd.Series(range(len(df)))), "R_cfd": df["R_max_K_W"], "dP_cfd": df["dP_Pa"],
                  "R_cv_pred": [p[0] for p in cv["cv_pred"]], "dP_cv_pred": [p[1] for p in cv["cv_pred"]]}
                 ).to_csv(os.path.join(a.out, "surrogate_cv.csv"), index=False)
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    main()
