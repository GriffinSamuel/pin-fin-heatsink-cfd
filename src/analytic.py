"""Hand-calculation model of the shrouded pin-fin heat sink (T2).

Model (all SI inside; inputs in mm where stated):
  1. Duct flow: W x (base_t + h). Over the base plate the free height is h, so the
     approach velocity to the pin array is V_a = V_duct * (base_t + h) / h.
  2. Velocity in the narrowest cross-section (Zukauskas / Gaddis-Gnielinski definition):
     u0 = V_a * a/(a-1) with a = S_T/d, or the diagonal gap for close staggered banks.
  3. Heat transfer coefficient from the ESDU 73031 tube-bank correlation
     Nu = c Re^m Pr^0.34 * F_rows (continuous across regimes; stated accuracy ~15%),
     with the Zukauskas/Bejan correlation reported alongside as a second opinion.
  4. Pin-fin efficiency with an adiabatic tip (tips touch the shroud):
     eta_f = tanh(mL)/(mL), m = sqrt(4 h_c / (k_al d)).
  5. The array is treated as a heat exchanger with a uniform fin-root temperature:
     NTU = eta_o h_c A_t / (m_dot c_p), eps = 1 - exp(-NTU), R_conv = 1/(m_dot c_p eps).
  6. Spreading + 1-D conduction through the base plate from the 30 mm chip to the
     60 mm base: Lee, Song, Van Au & Moran (1995) closed form, with the base top
     cooled by the equivalent film coefficient h_eff = 1/(R_conv A_base).
  7. Pressure drop across the bank: Gaddis & Gnielinski (1985) explicit drag
     coefficient, dP = xi * N_rows * rho u0^2 / 2 (bank only; the step onto the
     base plate and the duct friction are not included).
Properties of air at 1 atm from Sutherland-type fits, evaluated at the film temperature.
"""
from __future__ import annotations

import json
import math
import sys

K_AL = 200.0        # W/m-K, aluminium
P_ATM = 101325.0
R_AIR = 287.05
CP_AIR = 1006.0


def air_props(T_c: float) -> dict:
    T = T_c + 273.15
    rho = P_ATM / (R_AIR * T)
    mu = 1.716e-5 * (T / 273.15) ** 1.5 * (273.15 + 110.4) / (T + 110.4)
    k = 0.0241 * (T / 273.15) ** 1.5 * (273.15 + 194.0) / (T + 194.0)
    return {"rho": rho, "mu": mu, "nu": mu / rho, "k": k, "cp": CP_AIR, "Pr": mu * CP_AIR / k}


# ---------------------------------------------------------------- correlations

def esdu_row_factor(n_rows: int) -> float:
    """ESDU 73031 mean row correction (1 for >= 10 rows)."""
    table = {1: 0.65, 2: 0.77, 3: 0.84, 4: 0.90, 5: 0.94, 6: 0.97, 7: 0.99, 8: 0.995, 9: 1.0}
    return table.get(n_rows, 1.0) if n_rows < 10 else 1.0


def nu_esdu_73031(Re: float, Pr: float, n_rows: int, staggered: bool) -> float:
    """ESDU 73031: Nu = c Re^m Pr^0.34 F_rows, Re on the tube OD and the velocity in the
    minimum flow area. Valid 10 < Re < 2e6; pitch/d 1.2-4 (inline), 1-4 (staggered)."""
    if staggered:
        c, m = (1.309, 0.360) if Re < 300 else (0.273, 0.635) if Re < 2e5 else (0.124, 0.700)
    else:
        c, m = (0.742, 0.431) if Re < 300 else (0.211, 0.651) if Re < 2e5 else (0.116, 0.700)
    return c * Re ** m * Pr ** 0.34 * esdu_row_factor(n_rows)


def zukauskas_row_factor(n_rows: int, staggered: bool) -> float:
    pts = ([1, 2, 3, 4, 5, 7, 10, 13, 16, 20],
           [0.64, 0.76, 0.84, 0.89, 0.92, 0.95, 0.97, 0.98, 0.99, 1.0] if staggered else
           [0.70, 0.80, 0.86, 0.90, 0.92, 0.95, 0.97, 0.98, 0.99, 1.0])
    if n_rows >= 20:
        return 1.0
    for (n0, f0), (n1, f1) in zip(zip(*pts), list(zip(*pts))[1:]):
        if n0 <= n_rows <= n1:
            return f0 + (f1 - f0) * (n_rows - n0) / (n1 - n0)
    return 1.0


def nu_zukauskas(Re: float, Pr: float, n_rows: int, staggered: bool, st_over_sl: float) -> float:
    """Zukauskas (1972) as tabulated by Bejan; Re on OD and max velocity. Note the
    constants are piecewise and jump ~25% at Re = 1000 for aligned banks."""
    if staggered:
        if Re < 500:
            c, m = 1.04, 0.4
        elif Re < 1000:
            c, m = 0.71, 0.5
        elif Re < 2e4:
            c, m = 0.35 * st_over_sl ** 0.2, 0.6
        else:
            c, m = 0.031 * st_over_sl ** 0.2, 0.8
    else:
        if Re < 100:
            c, m = 0.9, 0.4
        elif Re < 1000:
            c, m = 0.52, 0.5
        elif Re < 2e4:
            c, m = 0.27, 0.63
        else:
            c, m = 0.033, 0.8
    return c * Re ** m * Pr ** 0.36 * zukauskas_row_factor(n_rows, staggered)


def xi_gaddis_gnielinski(Re0: float, a: float, b: float, n_rows: int, staggered: bool) -> float:
    """Gaddis & Gnielinski (1985) drag coefficient; dP = xi * N * rho * u0^2 / 2.
    a = S_T/d (transverse), b = S_L/d (longitudinal), Re0 with the narrowest-section
    velocity u0. Valid 1 <= Re0 <= 3.5e5."""
    c = math.sqrt((a / 2) ** 2 + b ** 2)
    diag = staggered and b < 0.5 * math.sqrt(2 * a + 1)
    a_eff = c if diag else a
    xi_lam = 280 * math.pi * ((b ** 0.5 - 0.6) ** 2 + 0.75) / (a_eff ** 1.6 * (4 * a * b - math.pi) * Re0)
    if staggered:
        f_t = 2.5 + 1.2 / (a - 0.85) ** 1.08 + 0.4 * (b / a - 1) ** 3 - 0.01 * (a / b - 1) ** 3
        xi_turb = f_t / Re0 ** 0.25
        blend = 1 - math.exp(-(Re0 + 200) / 1000)
    else:
        f_t = (0.22 + 1.2 * (1 - 0.94 / b) ** 0.6 / (a - 0.85) ** 1.3) * 10 ** (0.47 * (b / a - 1.5)) \
            + 0.03 * (a - 1) * (b - 1)
        xi_turb = f_t / Re0 ** (0.1 * b / a)
        blend = 1 - math.exp(-(Re0 + 1000) / 2000)
    # inlet/outlet correction for few rows (VDI: valid for N >= 5; applied as-is below 5)
    if n_rows > 10:
        f_n = 0.0
    else:
        geo = (2 * (c - 1) / (a * (a - 1))) ** 2 if diag else 1 / a ** 2
        f_n = geo * (1 / n_rows - 1 / 10)
    return xi_lam + (xi_turb + f_n) * blend


def n_main_resistances(n_rows: int, a: float, b: float, staggered: bool) -> int:
    """VDI convention: the number of 'main resistances' equals the number of rows,
    except for staggered banks whose narrowest section is diagonal (n_rows - 1)."""
    if staggered and b < 0.5 * math.sqrt(2 * a + 1):
        return max(n_rows - 1, 1)
    return n_rows


def spreading_resistance_lee(area_source: float, area_plate: float, t: float, k: float, h_eff: float) -> float:
    """Lee, Song, Van Au & Moran (1995): maximum source temperature rise above the fluid
    at the plate's cooled face, including 1-D conduction through the plate. SI units."""
    r1 = math.sqrt(area_source / math.pi)
    r2 = math.sqrt(area_plate / math.pi)
    eps, tau = r1 / r2, t / r2
    Bi = h_eff * r2 / k
    lam = math.pi + 1 / (eps * math.sqrt(math.pi))
    th = math.tanh(lam * tau)
    phi = (th + lam / Bi) / (1 + (lam / Bi) * th)
    psi_max = eps * tau / math.sqrt(math.pi) + (1 - eps) * phi / math.sqrt(math.pi)
    return psi_max / (k * r1 * math.sqrt(math.pi))


# ---------------------------------------------------------------- the model

def solve(meta: dict, V: float, T_in: float = 25.0, Q: float = 100.0) -> dict:
    """meta: dict from geometry.metadata(). V: duct inlet velocity [m/s]. Returns SI results."""
    s = meta["spec"]
    d, h, bt = s["d"] * 1e-3, s["h"] * 1e-3, s["base_t"] * 1e-3
    W, L = s["base_w"] * 1e-3, s["base_l"] * 1e-3
    p = meta["pitch_mm"] * 1e-3
    n, n_rows = meta["n_pins"], meta["n_rows"]
    staggered = s["layout"] == "staggered"
    a = b = p / d                                   # S_T/d = S_L/d (square array)
    A_duct = W * (bt + h)
    V_a = V * (bt + h) / h                          # approach velocity over the plate
    c_diag = math.sqrt((a / 2) ** 2 + b ** 2)
    if staggered and b < 0.5 * math.sqrt(2 * a + 1):
        u0 = V_a * a / (2 * (c_diag - 1))
    else:
        u0 = V_a * a / (a - 1)
    A_fin = n * math.pi * d * h                     # lateral pin area (tips are on the shroud)
    A_base_exp = meta["area_base_exposed_mm2"] * 1e-6
    A_t = A_fin + A_base_exp
    A_chip = (meta["chip_mm"] * 1e-3) ** 2
    A_plate = W * L

    T_s = T_in + 30.0                               # initial guess, fin-root temperature
    T_bulk = T_in + 5.0
    out = {}
    for _ in range(20):
        pr = air_props(0.5 * (T_s + T_bulk))
        pr_in = air_props(T_in)
        m_dot = pr_in["rho"] * V * A_duct
        Re = u0 * d / pr["nu"]
        Nu = nu_esdu_73031(Re, pr["Pr"], n_rows, staggered)
        Nu_z = nu_zukauskas(Re, pr["Pr"], n_rows, staggered, 1.0)
        h_c = Nu * pr["k"] / d
        m_fin = math.sqrt(4 * h_c / (K_AL * d))
        eta_f = math.tanh(m_fin * h) / (m_fin * h)
        eta_o = 1 - (A_fin / A_t) * (1 - eta_f)
        NTU = eta_o * h_c * A_t / (m_dot * pr["cp"])
        eps = 1 - math.exp(-NTU)
        R_conv = 1 / (m_dot * pr["cp"] * eps)
        h_eff = 1 / (R_conv * A_plate)
        R_base = spreading_resistance_lee(A_chip, A_plate, bt, K_AL, h_eff)
        T_s_new = T_in + Q * R_conv
        T_out = T_in + Q / (m_dot * pr["cp"])
        T_bulk = 0.5 * (T_in + T_out)
        if abs(T_s_new - T_s) < 1e-3:
            T_s = T_s_new
            break
        T_s = T_s_new
    xi = xi_gaddis_gnielinski(Re, a, b, n_rows, staggered)
    dP = xi * n_main_resistances(n_rows, a, b, staggered) * pr["rho"] * u0 ** 2 / 2
    R_total = R_conv + R_base
    out.update({
        "V": V, "V_approach": V_a, "u_max": u0, "Re_max": Re, "Pr": pr["Pr"],
        "Nu_esdu": Nu, "Nu_zukauskas": Nu_z, "h_W_m2K": h_c,
        "eta_fin": eta_f, "eta_overall": eta_o, "NTU": NTU, "effectiveness": eps,
        "m_dot_kg_s": m_dot, "T_out": T_out,
        "R_conv_K_W": R_conv, "R_base_K_W": R_base, "R_total_K_W": R_total,
        "R_total_zukauskas_K_W": _r_with_nu(Nu_z, pr, d, h, A_fin, A_t, m_dot, A_chip, A_plate, bt),
        "T_fin_root_C": T_s, "T_chip_max_C": T_in + Q * R_total,
        "xi_gaddis_gnielinski": xi, "dP_Pa": dP, "n_rows": n_rows, "n_pins": n,
    })
    return out


def _r_with_nu(Nu, pr, d, h, A_fin, A_t, m_dot, A_chip, A_plate, bt):
    h_c = Nu * pr["k"] / d
    m_fin = math.sqrt(4 * h_c / (K_AL * d))
    eta_f = math.tanh(m_fin * h) / (m_fin * h)
    eta_o = 1 - (A_fin / A_t) * (1 - eta_f)
    eps = 1 - math.exp(-eta_o * h_c * A_t / (m_dot * pr["cp"]))
    R_conv = 1 / (m_dot * pr["cp"] * eps)
    return R_conv + spreading_resistance_lee(A_chip, A_plate, bt, K_AL, 1 / (R_conv * A_plate))


def main(argv=None):
    import argparse
    from src.geometry import HeatSinkSpec, metadata
    ap = argparse.ArgumentParser()
    ap.add_argument("--d", type=float, required=True)
    ap.add_argument("--pd", type=float, required=True)
    ap.add_argument("--h", type=float, required=True)
    ap.add_argument("--layout", choices=["inline", "staggered"], required=True)
    ap.add_argument("--V", type=float, nargs="+", default=[2, 4, 6])
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    meta = metadata(HeatSinkSpec(a.d, a.pd, a.h, a.layout))
    rows = [solve(meta, V) for V in a.V]
    if a.json:
        json.dump(rows, sys.stdout, indent=2)
        return
    print(f"{meta['n_pins']} pins in {meta['n_rows']} rows, fin mass {meta['fin_mass_g']:.1f} g")
    print(f"{'V':>4} {'Re_max':>7} {'Nu':>6} {'h':>6} {'eta_f':>6} {'R_conv':>7} {'R_base':>7} "
          f"{'R_tot':>6} {'R_zuk':>6} {'T_chip':>7} {'dP':>7}")
    for r in rows:
        print(f"{r['V']:4.1f} {r['Re_max']:7.0f} {r['Nu_esdu']:6.1f} {r['h_W_m2K']:6.0f} "
              f"{r['eta_fin']:6.2f} {r['R_conv_K_W']:7.3f} {r['R_base_K_W']:7.3f} "
              f"{r['R_total_K_W']:6.3f} {r['R_total_zukauskas_K_W']:6.3f} {r['T_chip_max_C']:7.1f} {r['dP_Pa']:7.1f}")


if __name__ == "__main__":
    main()
