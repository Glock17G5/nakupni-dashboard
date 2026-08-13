"""
Referenční tabulky a skeny z katalogu HELUKABEL (technická příloha).
Použití: hub Nástroje & tipy → „Technické tabulky HELUKABEL“.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

_ASSETS = Path(__file__).resolve().parent / "assets" / "helukabel"


def _img(name: str) -> Path:
    return _ASSETS / name


def _show_scan(filename: str, caption: str) -> None:
    path = _img(filename)
    if path.is_file():
        with st.expander(f"📷 Originální sken — {caption}", expanded=False):
            st.image(str(path), use_container_width=True)
    else:
        st.caption(f"Sken `{filename}` nenalezen v assets/helukabel.")


def list_catalog_scans() -> list[Path]:
    """Všechny skeny v assets/helukabel (png/jpg/webp), seřazené podle jména."""
    if not _ASSETS.is_dir():
        return []
    files: list[Path] = []
    for pat in ("*.png", "*.jpg", "*.jpeg", "*.webp", "*.PNG", "*.JPG", "*.JPEG"):
        files.extend(_ASSETS.glob(pat))
    return sorted({p.resolve() for p in files}, key=lambda p: p.name.lower())


# ── Bubny KTG — rozměry ───────────────────────────────────────────────────────

_KTG_WOOD = [
    # kod, velikost, Fd, Kd, Bd, I1, I2, max_kg, mass_kg
    ("051", "05", 500, 150, 56, 470, 410, 100, 8),
    ("061", "06", 630, 315, 56, 415, 315, 250, 17),
    ("071", "07", 710, 355, 80, 520, 400, 250, 25),
    ("081", "08", 800, 400, 80, 520, 400, 400, 31),
    ("091", "09", 900, 450, 80, 690, 560, 750, 47),
    ("101", "10", 1000, 500, 80, 710, 560, 900, 71),
    ("121", "12", 1250, 630, 80, 890, 670, 1700, 144),
    ("141", "14", 1400, 710, 80, 890, 670, 2000, 175),
    ("161", "16/8", 1600, 800, 80, 1100, 850, 3000, 280),
    ("181", "18/10", 1800, 1000, 100, 1100, 840, 4000, 380),
    ("201", "20/12", 2000, 1250, 100, 1350, 1045, 5000, 550),
    ("221", "22/12", 2240, 1400, 125, 1450, 1140, 6000, 710),
    ("250", "25/14", 2500, 1400, 125, 1450, 1140, 7500, 875),
    ("251", "25/16", 2500, 1600, 125, 1450, 1130, 7500, 900),
    ("281", "28/18", 2800, 1800, 140, 1635, 1280, 10000, 1175),
]

_KTG_PLASTIC = [
    ("050", 500, 150, 456, 404, 100, 4),
    ("070", 710, 355, 510, 400, 250, 15),
    ("080", 800, 400, 510, 400, 350, 16),
    ("090", 900, 450, 680, 560, 400, 23),
    ("100", 1000, 500, 704, 560, 500, 32),
]

_KTG_DISPOSABLE = [
    ("HE 350", 350, 150, 320, 300, 56, 1.8),
    ("HE 400", 400, 150, 320, 300, 56, 2.1),
    ("HE 401", 400, 150, 425, 405, 56, 2.3),
    ("HE 501", 500, 150, 320, 300, 56, 3.0),
    ("HE 500", 500, 150, 425, 405, 56, 3.3),
    ("HE 600", 600, 150, 425, 405, 56, 4.5),
    ("HE 760", 760, 300, 425, 400, 80, 8.0),
]


def df_ktg_wood() -> pd.DataFrame:
    return pd.DataFrame(
        _KTG_WOOD,
        columns=[
            "Kód", "Velikost", "Fd [mm]", "Kd [mm]", "Bd [mm]",
            "I₁ [mm]", "I₂ [mm]", "Max. nosnost [kg]", "Hmotnost bubnu [kg]",
        ],
    )


def df_ktg_plastic() -> pd.DataFrame:
    return pd.DataFrame(
        _KTG_PLASTIC,
        columns=[
            "Kód", "Fd [mm]", "Kd [mm]", "I₁ [mm]", "I₂ [mm]",
            "Max. nosnost [kg]", "Hmotnost [kg]",
        ],
    )


def df_ktg_disposable() -> pd.DataFrame:
    return pd.DataFrame(
        _KTG_DISPOSABLE,
        columns=[
            "Kód", "Fd [mm]", "Kd [mm]", "I₁ [mm]", "I₂ [mm]",
            "Max. Bd [mm]", "Hmotnost [kg]",
        ],
    )


def ktg_wood_by_code(code: str) -> dict | None:
    for row in _KTG_WOOD:
        if row[0] == code:
            return {
                "kod": row[0], "velikost": row[1],
                "Fd": row[2], "Kd": row[3], "Bd": row[4],
                "I1": row[5], "I2": row[6],
                "max_kg": row[7], "mass": row[8],
            }
    return None


def ktg_wood_drums() -> list[dict]:
    """Všechny standardní dřevěné KTG bubny jako slovníky."""
    out = []
    for row in _KTG_WOOD:
        out.append({
            "kod": row[0], "velikost": row[1],
            "Fd": row[2], "Kd": row[3], "Bd": row[4],
            "I1": row[5], "I2": row[6],
            "max_kg": row[7], "mass": row[8],
            "label": f"{row[0]}/{row[1]}",
        })
    return out


def ktg_min_drums_for_bend(d_cable_mm: float, bend_n: float) -> list[dict]:
    """
    KTG dřevěné bubny s Kd ≥ bend_n × D, seřazené od nejmenšího čela.
    """
    if d_cable_mm <= 0 or bend_n <= 0:
        return []
    kd_min = bend_n * d_cable_mm
    ok = [d for d in ktg_wood_drums() if d["Kd"] >= kd_min]
    return sorted(ok, key=lambda d: (d["Fd"], d["Kd"], d["I2"]))


# ── Ohyb VDE ──────────────────────────────────────────────────────────────────

def df_bend_power_fixed() -> pd.DataFrame:
    return pd.DataFrame(
        [
            ("Pevné uložení", "4 × D", "4 × D", "4 × D"),
            ("Při vytvarování", "1 × D", "2 × D", "3 × D"),
        ],
        columns=[
            "Způsob pokládky",
            "D ≤ 10 mm",
            "10 < D ≤ 25 mm",
            "D > 25 mm",
        ],
    )


def df_bend_flexible() -> pd.DataFrame:
    return pd.DataFrame(
        [
            ("Pevné uložení", "3 × D", "3 × D", "4 × D", "4 × D"),
            ("Volný pohyb", "3 × D", "4 × D", "5 × D", "5 × D"),
            ("Při zavádění", "3 × D", "4 × D", "5 × D", "5 × D"),
            ("Nucené vedení (návin na buben)", "5 × D", "5 × D", "5 × D", "6 × D"),
            ("Trolejový kabel", "3 × D", "4 × D", "5 × D", "5 × D"),
            ("Ve vlečných řetězech", "4 × D", "4 × D", "5 × D", "5 × D"),
            ("Navíjení přes kladku", "7,5 × D", "7,5 × D", "7,5 × D", "7,5 × D"),
        ],
        columns=[
            "Způsob pokládky",
            "D ≤ 8 mm",
            "8 < D ≤ 12 mm",
            "12 < D ≤ 20 mm",
            "D > 20 mm",
        ],
    )


def df_bend_install_comm() -> pd.DataFrame:
    return pd.DataFrame(
        [
            (
                "Skupina A — J-Y(St)Y…Lg, JE-Y(St)Y…Bd, JE-H(St)H…, JE-YCY…, JE-HCH…",
                "7,5 × D", "7,5 × D", "5 × D",
            ),
            (
                "Skupina B — JE-LiYCY…, JE-LiHCH…, JE-LiYY…, J-YY…, J-HH…, J-Y(St)Y…",
                "7,5 × D", "7,5 × D", "2,5 × D",
            ),
        ],
        columns=[
            "Typ / skupina",
            "Při expedici",
            "Opakovaný ohyb s tahem",
            "Jednorázový ohyb bez tahu",
        ],
    )


def bend_factor_flexible(d_mm: float, mode: str) -> float | None:
    """Vrátí násobitel × D pro ohebné kabely (DIN VDE 0298-3)."""
    table = {
        "Pevné uložení": [(8, 3), (12, 3), (20, 4), (1e9, 4)],
        "Volný pohyb": [(8, 3), (12, 4), (20, 5), (1e9, 5)],
        "Při zavádění": [(8, 3), (12, 4), (20, 5), (1e9, 5)],
        "Nucené vedení (návin na buben)": [(8, 5), (12, 5), (20, 5), (1e9, 6)],
        "Trolejový kabel": [(8, 3), (12, 4), (20, 5), (1e9, 5)],
        "Ve vlečných řetězech": [(8, 4), (12, 4), (20, 5), (1e9, 5)],
        "Navíjení přes kladku": [(8, 7.5), (12, 7.5), (20, 7.5), (1e9, 7.5)],
    }
    rows = table.get(mode)
    if not rows:
        return None
    for limit, factor in rows:
        if d_mm <= limit:
            return float(factor)
    return None


# ── Značení žil ───────────────────────────────────────────────────────────────

def df_core_colors_din() -> pd.DataFrame:
    return pd.DataFrame(
        [
            ("AC — fázový 1", "R", "L1", "černá", "nedef. (pref. černá)", ""),
            ("AC — fázový 2", "S", "L2", "červená", "nedef. (např. hnědá)", ""),
            ("AC — fázový 3", "T", "L3", "modrá", "nedefinováno", ""),
            ("AC — střední (N)", "MP", "N", "šedá", "světlemodrá", ""),
            ("DC — kladný", "L+", "+", "—", "nedefinováno", ""),
            ("DC — záporný", "L−", "−", "—", "nedefinováno", ""),
            ("DC — střední", "M", "M", "—", "světlemodrá", ""),
            ("Ochranný (PE)", "—", "PE", "—", "zeleno-žlutá", "⏚"),
            ("PEN", "—", "PEN", "—", "zeleno-žlutá", "⏚"),
            ("Zem (E)", "—", "E", "—", "nedefinováno", "⏚"),
            ("Zem pro ext. napětí (TE)", "—", "TE", "—", "nedefinováno", ""),
        ],
        columns=[
            "Vodič", "Alfanum. staré", "Alfanum. nové",
            "Barva stará", "Barva nová (DIN/IEC)", "Symbol",
        ],
    )


def df_vde0816_quads() -> pd.DataFrame:
    return pd.DataFrame(
        [
            (1, "červená"),
            (2, "zelená"),
            (3, "šedá"),
            (4, "žlutá"),
            (5, "bílá"),
        ],
        columns=["Čtyřka ve svazku", "Barva izolace"],
    )


def df_vde0816_rings() -> pd.DataFrame:
    return pd.DataFrame(
        [
            ("Kmen 1 — žíla a", "bez kroužků"),
            ("Kmen 1 — žíla b", "jednoduché kroužky, rozteč 17 mm"),
            ("Kmen 2 — žíla a", "dvojité kroužky, rozteč 34 mm"),
            ("Kmen 2 — žíla b", "dvojité kroužky, rozteč 17 mm"),
        ],
        columns=["Žíla ve hvězdicové čtyřce", "Značení"],
    )


# ── Průměry jader VDE 0295 ────────────────────────────────────────────────────

_CORE_DIAM = [
    # q, cl1_min, cl1_max, cl2_max, cl56_max
    (0.5, None, 0.9, 1.1, 1.1),
    (0.75, None, 1.0, 1.2, 1.3),
    (1.0, None, 1.2, 1.4, 1.5),
    (1.5, None, 1.5, 1.7, 1.8),
    (2.5, None, 1.9, 2.2, 2.4),
    (4.0, None, 2.4, 2.7, 3.0),
    (6.0, None, 2.9, 3.3, 3.9),
    (10.0, None, 3.7, 4.2, 5.1),
    (16.0, None, 4.6, 5.3, 6.3),
    (25.0, 5.2, 5.7, 6.6, 7.8),
    (35.0, 6.1, 6.7, 7.9, 9.2),
    (50.0, 7.2, 7.8, 9.1, 11.0),
    (70.0, 8.7, 9.4, 11.0, 13.1),
    (95.0, 10.3, 11.0, 12.9, 15.1),
    (120.0, 11.6, 12.4, 14.5, 17.0),
    (150.0, 12.9, 13.8, 16.2, 19.0),
    (185.0, None, 15.4, 18.0, 21.0),
    (240.0, None, 17.6, 20.6, 24.0),
    (300.0, None, 19.8, 23.1, 27.0),
    (400.0, None, 22.2, 26.1, 31.0),
    (500.0, None, None, 29.2, 35.0),
    (630.0, None, None, 33.2, 39.0),
    (800.0, None, None, 37.6, None),
    (1000.0, None, None, 42.2, None),
]


def df_core_diameters() -> pd.DataFrame:
    rows = []
    for q, c1min, c1max, c2, c56 in _CORE_DIAM:
        rows.append({
            "Průřez [mm²]": q,
            "Tř. 1 min-ø [mm]": c1min if c1min is not None else "—",
            "Tř. 1 max-ø [mm]": c1max if c1max is not None else "—",
            "Tř. 2 max-ø [mm]": c2 if c2 is not None else "—",
            "Tř. 5/6 max-ø [mm]": c56 if c56 is not None else "—",
        })
    return pd.DataFrame(rows)


# ── Odpor jádra IEC 60228 / VDE 0295 (max Ω/km @ 20 °C) ───────────────────────

_R_CU12 = {
    0.5: 36.0, 0.75: 24.5, 1.0: 18.1, 1.5: 12.1, 2.5: 7.41, 4: 4.61, 6: 3.08,
    10: 1.83, 16: 1.15, 25: 0.727, 35: 0.524, 50: 0.387, 70: 0.268, 95: 0.193,
    120: 0.153, 150: 0.124, 185: 0.0991, 240: 0.0754, 300: 0.0601, 400: 0.0470,
    500: 0.0366, 630: 0.0283,
}
_R_CU56 = {
    0.5: 39.0, 0.75: 26.0, 1.0: 19.5, 1.5: 13.3, 2.5: 7.98, 4: 4.95, 6: 3.30,
    10: 1.91, 16: 1.21, 25: 0.780, 35: 0.554, 50: 0.386, 70: 0.272, 95: 0.206,
    120: 0.161, 150: 0.129, 185: 0.106, 240: 0.0801, 300: 0.0641, 400: 0.0486,
    500: 0.0384, 630: 0.0287,
}
_R_CU_TIN12 = {
    0.5: 36.7, 0.75: 24.8, 1.0: 18.2, 1.5: 12.2, 2.5: 7.56, 4: 4.70, 6: 3.11,
    10: 1.84, 16: 1.16, 25: 0.734, 35: 0.529, 50: 0.391, 70: 0.270, 95: 0.195,
    120: 0.154, 150: 0.126, 185: 0.100, 240: 0.0762, 300: 0.0607, 400: 0.0475,
    500: 0.0369, 630: 0.0286,
}
_R_CU_TIN56 = {
    0.5: 40.1, 0.75: 26.7, 1.0: 20.0, 1.5: 13.7, 2.5: 8.21, 4: 5.09, 6: 3.39,
    10: 1.95, 16: 1.24, 25: 0.795, 35: 0.565, 50: 0.393, 70: 0.277, 95: 0.210,
    120: 0.164, 150: 0.132, 185: 0.108, 240: 0.0817, 300: 0.0654, 400: 0.0495,
    500: 0.0391, 630: 0.0292,
}
_R_AL12 = {
    10: 3.08, 16: 1.91, 25: 1.20, 35: 0.868, 50: 0.641, 70: 0.443, 95: 0.320,
    120: 0.253, 150: 0.206, 185: 0.164, 240: 0.125, 300: 0.100, 400: 0.0778,
    500: 0.0605, 630: 0.0469,
}


def df_core_resistance() -> pd.DataFrame:
    qs = sorted(set(_R_CU12) | set(_R_CU56) | set(_R_AL12))
    rows = []
    for q in qs:
        rows.append({
            "Průřez [mm²]": q,
            "Cu holé tř. 1/2": _R_CU12.get(q, "—"),
            "Cu holé tř. 5/6": _R_CU56.get(q, "—"),
            "Cu pocín. tř. 1/2": _R_CU_TIN12.get(q, "—"),
            "Cu pocín. tř. 5/6": _R_CU_TIN56.get(q, "—"),
            "Al tř. 1/2": _R_AL12.get(q, "—"),
        })
    return pd.DataFrame(rows)


# ── AWG ↔ mm² ─────────────────────────────────────────────────────────────────

_AWG = [
    (30, 0.05), (28, 0.08), (26, 0.14), (24, 0.25), (22, 0.34), (21, 0.38),
    (20, 0.50), (19, 0.75), (18, 0.75), (17, 1.0), (16, 1.5), (14, 2.5),
    (12, 4.0), (10, 6.0), (8, 10.0), (6, 16.0), (4, 25.0), (2, 35.0),
    (1, 50.0), ("1/0", 55.0), ("2/0", 70.0), ("3/0", 95.0), ("4/0", 120.0),
]
_KCMIL = [
    (250, 120), (300, 150), (350, 185), (400, 185), (500, 240),
    (600, 300), (750, 400), (1000, 500),
]


def df_awg() -> pd.DataFrame:
    rows = [{"AWG": a, "≈ mm²": m} for a, m in _AWG]
    rows += [{"AWG": f"{k} kcmil", "≈ mm²": m} for k, m in _KCMIL]
    return pd.DataFrame(rows)


# ── Proudová zatížitelnost (ohebné, 30 °C) ────────────────────────────────────

_CURRENT_FLEX = [
    # q, g1_A, g1_fuse, g2_A, g2_fuse, g3_A, g3_fuse
    (0.75, 12, 10, 12, 10, 15, 16),
    (1.0, 15, 10, 15, 10, 19, 16),
    (1.5, 18, 16, 18, 16, 24, 20),
    (2.5, 26, 20, 26, 20, 32, 25),
    (4, 34, 25, 34, 25, 42, 35),
    (6, 44, 35, 44, 35, 54, 50),
    (10, 61, 50, 61, 50, 73, 63),
    (16, 82, 63, 82, 63, 98, 80),
    (25, 108, 100, 108, 100, 129, 125),
    (35, 135, 125, 135, 125, 158, 160),
    (50, 168, 160, 168, 160, 198, 200),
    (70, 207, 200, 207, 200, 245, 250),
    (95, 250, 250, 250, 250, 292, 315),
    (120, 292, 250, 292, 250, 344, 315),
    (150, 335, 315, 335, 315, 391, 400),
    (185, 382, 355, 382, 355, 448, 400),
    (240, 453, 400, 453, 400, 528, 500),
    (300, 523, 500, 523, 500, 608, 630),
    (400, None, None, 523, 500, 726, 630),
]


def df_current_flex() -> pd.DataFrame:
    rows = []
    for q, a1, f1, a2, f2, a3, f3 in _CURRENT_FLEX:
        rows.append({
            "Průřez [mm²]": q,
            "Sk.1 Cu [A]": a1 if a1 is not None else "—",
            "Sk.1 pojistka [A]": f1 if f1 is not None else "—",
            "Sk.2 Cu [A]": a2 if a2 is not None else "—",
            "Sk.2 pojistka [A]": f2 if f2 is not None else "—",
            "Sk.3 Cu [A]": a3 if a3 is not None else "—",
            "Sk.3 pojistka [A]": f3 if f3 is not None else "—",
        })
    return pd.DataFrame(rows)


def df_temp_corr_pvc_rubber() -> pd.DataFrame:
    return pd.DataFrame(
        [
            ("30–35", 0.91, 0.94),
            ("35–40", 0.82, 0.87),
            ("40–45", 0.71, 0.79),
            ("45–50", 0.58, 0.71),
            ("50–55", 0.41, 0.61),
            ("55–60", 0.41, 0.50),
            ("60–65", "—", 0.35),
        ],
        columns=["Teplota okolí [°C]", "Guma (max 60 °C jádro)", "PVC (max 70 °C jádro)"],
    )


# ── Vodivost ──────────────────────────────────────────────────────────────────

_KAPPA = {
    "Měď (Cu)": 58.0,
    "Hliník (Al)": 33.0,
    "Stříbro": 62.0,
    "Železo": 7.7,
    "Konstantan": 2.0,
}


def df_conductivity() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"Materiál": m, "κ [m/(Ω·mm²)]": k, "ρ [Ω·mm²/m]": round(1.0 / k, 5)}
            for m, k in _KAPPA.items()
        ]
    )


# ── Nové výpisky z kompletního katalogu (X 5–X 125) ───────────────────────────

_H_VOLTAGE = {
    "01": "100 V",
    "03": "300/300 V",
    "05": "300/500 V",
    "07": "450/750 V",
}
_H_INSUL = {
    "V": "PVC", "V2": "PVC +90 °C", "V3": "PVC mráz", "V4": "PVC zesítěné",
    "V5": "PVC olejivzdorné", "R": "EPR +60 °C", "B": "EPR +90 °C",
    "N": "chloropren", "S": "silikon", "G": "EVA", "X": "XLPE",
    "Z": "bezhalogen zesítěný polyolefin", "Q": "PUR", "E": "PE",
}
_H_CORE = {
    "U": "plný kulatý (tř. 1)", "R": "laněný kulatý (tř. 2)",
    "K": "jemně laněný, pevné uložení", "F": "jemně laněný tř. 5",
    "H": "velmi jemně laněný tř. 6", "D": "svařovací jemně laněný",
    "E": "svařovací velmi jemně laněný",
}
_NYY_PARTS = [
    ("N / (N)", "norma DIN VDE / v souladu s normou"),
    ("A", "hliníkové jádro (bez A = měď)"),
    ("Y / 2X", "izolace PVC / XLPE"),
    ("C / CW / CE", "koncentrický Cu vodič (podélný / vlnový / na žíle)"),
    ("S / SE", "stínění Cu dráty / na každé žíle"),
    ("B / F / R", "pancíř páska / ploché dráty / kulaté dráty"),
    ("Y / 2Y / K", "plášť PVC / PE / olovo"),
    ("J / O", "se zeleno-žlutou / bez PE žíly"),
    ("r/s/e + m", "kulaté / sektor / plné + laněné"),
]


def df_h_code_legend() -> pd.DataFrame:
    rows = [
        ("H / A", "harmonizovaný / schválený národní typ"),
        ("01 / 03 / 05 / 07", "100 V / 300/300 / 300/500 / 450/750 V"),
        ("V … V5, R, N, S, G, X, Z, Q", "izolace / plášť (PVC, pryž, silikon, XLPE, PUR…)"),
        ("-U / -R / -K / -F / -H", "jádro: plné / laněné / pevné flex / tř.5 / tř.6"),
        ("G / X", "se zeleno-žlutou / bez ochranné žíly"),
        ("n × q", "počet žil × průřez mm²"),
        ("H, H2, H8", "plochý dělitelný / nedělitelný / spirálový"),
    ]
    return pd.DataFrame(rows, columns=["Kód", "Význam"])


def df_old_new_codes() -> pd.DataFrame:
    return pd.DataFrame(
        [
            ("Zapojovací PVC", "H05V-U / H05V-K", "NYA / NYAF", "0,5–1,0", "300/500"),
            ("Instalační vodič", "H07V-U / H07V-R / H07V-K", "NYA / NYAF", "1,5–240", "450/750"),
            ("PVC šňůra kulatá", "H03VV-F / H05VV-F", "NYMHöu apod.", "—", "300/300–500"),
            ("Plochý PVC", "H05VVH6 / H07VVH6", "—", "—", "300/500–750"),
            ("Tepelně odolný", "H07G-U / H07G-K", "—", "do 95", "450/750"),
            ("Gumová šňůra", "H05RR-F / H05RN-F", "—", "—", "300/500"),
            ("Těžká gumová", "H07RN-F", "NMHöu / NSHöu", "—", "450/750"),
        ],
        columns=["Typ", "Nová zkratka (HD)", "Stará VDE 0250", "Průřez [mm²]", "U₀/U [V]"],
    )


def df_din_vde_refs() -> pd.DataFrame:
    return pd.DataFrame(
        [
            ("DIN VDE 0100", "Silová zařízení do 1000 V — zřizování"),
            ("DIN VDE 0100-100", "Všeobecné požadavky, oblast použití"),
            ("DIN VDE 0100-410", "Ochrana proti úrazu el. proudem"),
            ("DIN VDE 0100-430", "Ochrana kabelů a vodičů při nadproudu"),
            ("DIN VDE 0100-482", "Protipožární ochrana"),
            ("DIN VDE 0100-520/530", "Kabely, vodiče, sběrnice / spínací zařízení"),
            ("DIN VDE 0100-559", "Svítidla a osvětlovací zařízení"),
            ("DIN VDE 0100-701…705", "Koupelny, bazény, sauny, staveniště, zemědělství"),
            ("DIN VDE 0100-720", "Provozovny s nebezpečím požáru"),
            ("DIN VDE 0100-726…737", "Zdvihadla, dřevěné stěny, přípojky, vlhko/mokro"),
            ("DIN VDE 0101", "Silová zařízení nad 1 kV"),
            ("DIN VDE 0105", "Provoz silových zařízení"),
            ("DIN VDE 0107", "Nemocnice a lékařské prostory"),
            ("DIN VDE 0108", "Shromažďovací objekty, výškové budovy, garáže"),
            ("DIN VDE 0113", "Elektrické vybavení průmyslových strojů"),
            ("DIN VDE 0118", "Podzemní doly"),
            ("DIN VDE 0165 / 0166", "Nebezpečí výbuchu / výbušné látky"),
            ("DIN VDE 0168", "Povrchové doly a kamenolomy"),
            ("DIN VDE 0170/0171", "Provozní prostředky do prostředí s výbuchem"),
            ("DIN VDE 0185", "Ochrana před bleskem"),
            ("DIN VDE 0207", "Izolační a plášťové směsi"),
            ("DIN VDE 0245", "Kabely pro el. provozní prostředky / ohebné PVC"),
            ("DIN VDE 0250", "Silové kabely, vodiče a šňůry"),
            ("DIN VDE 0253", "Izolované topné vodiče"),
            ("DIN VDE 0262", "Instalační XLPE + PVC plášť do 0,6/1 kV"),
            ("DIN VDE 0265", "Plastová izolace + olověný plášť"),
            ("DIN VDE 0266", "Bezhalogenové kabely, jaderné elektrárny (E… )"),
            ("DIN VDE 0271 / 0276", "Distribuční / silové kabely, zatížitelnost"),
            ("DIN VDE 0281 / 0282", "PVC vodiče / gumové kabely (harmonizované)"),
            ("DIN VDE 0292 / HD 361", "Označovací kódy harmonizovaných kabelů"),
            ("DIN VDE 0293", "Značení žil do 1000 V"),
            ("DIN VDE 0295 / IEC 60228", "Jádra — třídy 1/2/5/6, odpor, konstrukce"),
            ("DIN VDE 0298", "Proudová zatížitelnost, ohyb, použití"),
            ("DIN VDE 0472 / 0473", "Zkoušení kabelů a izolačních materiálů"),
            ("DIN VDE 0815 / 0816", "Instalační / venkovní telekomunikační kabely"),
        ],
        columns=["Norma", "Oblast"],
    )


def df_current_cefg_90() -> pd.DataFrame:
    """Proud @ 90 °C jádro / 30 °C okolí — pokládka C, E (výběr)."""
    return pd.DataFrame(
        [
            (1.5, 24, 22, 26, 23),
            (2.5, 32, 30, 36, 32),
            (4, 42, 39, 47, 42),
            (6, 54, 50, 60, 54),
            (10, 73, 68, 82, 73),
            (16, 98, 91, 110, 98),
            (25, 129, 119, 146, 129),
            (35, 158, 146, 179, 158),
            (50, 192, 176, 217, 192),
            (70, 246, 224, 278, 246),
            (95, 298, 271, 338, 298),
            (120, 346, 314, 393, 346),
            (150, 395, 360, 450, 395),
            (185, 450, 408, 514, 450),
            (240, 528, 478, 604, 528),
        ],
        columns=["mm²", "C · 2 žíly [A]", "C · 3 žíly [A]", "E · 2 žíly [A]", "E · 3 žíly [A]"],
    )


def df_xlpe_mv_cap() -> pd.DataFrame:
    return pd.DataFrame(
        [
            (35, 0.22, 0.16, None),
            (50, 0.25, 0.18, 0.14),
            (70, 0.28, 0.20, 0.15),
            (95, 0.31, 0.22, 0.17),
            (120, 0.34, 0.23, 0.18),
            (150, 0.37, 0.25, 0.19),
            (185, 0.40, 0.27, 0.20),
            (240, 0.44, 0.30, 0.22),
            (300, 0.48, 0.32, 0.24),
            (400, 0.55, 0.36, 0.27),
            (500, 0.60, 0.40, 0.29),
        ],
        columns=["mm²", "6/10 kV [µF/km]", "12/20 kV [µF/km]", "18/30 kV [µF/km]"],
    )


def df_xlpe_mv_ind() -> pd.DataFrame:
    return pd.DataFrame(
        [
            (35, 0.45, 0.76, 0.48, 0.76, None, None),
            (50, 0.42, 0.73, 0.45, 0.74, 0.48, 0.75),
            (70, 0.39, 0.70, 0.43, 0.70, 0.45, 0.71),
            (95, 0.38, 0.67, 0.41, 0.68, 0.43, 0.68),
            (120, 0.36, 0.65, 0.39, 0.65, 0.42, 0.66),
            (150, 0.35, 0.63, 0.38, 0.63, 0.41, 0.64),
            (185, 0.34, 0.61, 0.36, 0.62, 0.39, 0.63),
            (240, 0.32, 0.59, 0.35, 0.59, 0.37, 0.60),
            (300, 0.31, 0.57, 0.33, 0.58, 0.36, 0.59),
            (400, 0.30, 0.55, 0.33, 0.55, 0.34, 0.56),
            (500, 0.29, 0.53, 0.31, 0.53, 0.33, 0.54),
        ],
        columns=[
            "mm²",
            "6/10 Δ [mH/km]", "6/10 — [mH/km]",
            "12/20 Δ [mH/km]", "12/20 — [mH/km]",
            "18/30 Δ [mH/km]", "18/30 — [mH/km]",
        ],
    )


def df_fire_load_n2xh() -> pd.DataFrame:
    return pd.DataFrame(
        [
            ("N2XH", "1×2,5 re", 0.14),
            ("N2XH", "1×300 rm", 1.32),
            ("N2XH", "3×1,5 re", 0.48),
            ("N2XH", "3×50 rm", 2.31),
            ("N2XH", "4×1,5 re", 0.54),
            ("N2XH", "4×150 rm", 6.81),
            ("N2XH", "5×1,5 re", 0.62),
            ("N2XCH", "3×1,5/1,5", 0.48),
            ("N2XCH", "4×50/25", 2.77),
            ("(N)HXH-E30", "3×1,5 re", 0.72),
            ("(N)HXH-E30", "3×240 rm", 8.84),
            ("NHXMH", "5×1,5 re", 0.54),
        ],
        columns=["Typ", "Složení", "Požární zatížení [kWh/m]"],
    )


def df_materials_key() -> pd.DataFrame:
    return pd.DataFrame(
        [
            ("PVC (Y)", "1,35–1,5", "70", "horlavý", "ano"),
            ("XLPE (2X)", "0,92", "90", "horlavý", "ne"),
            ("PE (2Y)", "0,92", "70", "horlavý", "ne"),
            ("PUR (11Y)", "1,1–1,2", "80–90", "horlavý", "ne"),
            ("Chloropren (5G)", "1,3–1,5", "60–80", "samozhášivý", "ano"),
            ("Silikon (2G)", "1,2", "180", "samozhášivý", "ne"),
            ("Bezhalogen Z/Z1", "1,4–1,6", "70–90", "nízký dým", "ne"),
            ("FEP / PTFE", "2,1–2,2", "180–260", "nehořlavý", "ano"),
        ],
        columns=["Materiál", "Hustota [g/cm³]", "Trvalá teplota [°C]", "Hořlavost", "Halogeny"],
    )


def df_cert_marks() -> pd.DataFrame:
    return pd.DataFrame(
        [
            ("Belgie", "CEBEC", "Comité Electrotechnique Belge"),
            ("Čína", "CCC", "China Compulsory Certification"),
            ("Dánsko", "DEMKO", "Danmarks Elektriske Materielkontroll"),
            ("Německo", "VDE", "VDE-Prüfstelle"),
            ("Německo", "IPA / Fraunhofer", "Fraunhofer IPA"),
            ("Evropa", "CE", "Communauté Européenne"),
            ("Finsko", "FI / FIMKO", "FIMKO LTD"),
            ("Francie", "NF / UTE", "Union Technique de l'Electricité"),
            ("Velká Británie", "BSI Kitemark", "British Standards Institution"),
            ("Itálie", "IMQ", "Istituto Italiano del Marchio di Qualità"),
            ("Kanada", "CSA", "Canadian Standards Association"),
            ("Nizozemsko", "KEMA-KEUR", "KEMA"),
            ("Norsko", "NEMKO", "Norges Elektriske Materiellkontroll"),
            ("Rakousko", "ÖVE", "Österreichischer Verband für Elektrotechnik"),
            ("Rusko", "GOST-R / PCT", "SGS"),
            ("Švédsko", "SEMKO", "Svenska Elektriska Materielkontrollanstalten"),
            ("Švýcarsko", "+S / SEV", "Schweizerischer Elektrotechnischer Verein"),
            ("USA", "UL / RU", "Underwriters Laboratories"),
        ],
        columns=["Země", "Značka", "Zkušebna"],
    )


def df_h_insulation() -> pd.DataFrame:
    return pd.DataFrame(
        [{"Kód": k, "Materiál / vlastnost": v} for k, v in _H_INSUL.items()]
    )


def df_h_cores() -> pd.DataFrame:
    return pd.DataFrame(
        [{"Kód": k, "Konstrukce jádra": v} for k, v in _H_CORE.items()]
    )


def df_hd_metal_shield() -> pd.DataFrame:
    return pd.DataFrame(
        [
            ("A2 / A3", "Al plášť lisovaný/svařovaný — hladký / zvlněný"),
            ("A4 / A5", "Al plášť na každé žíle / z pásky"),
            ("C2 / C3", "Cu plášť / zvlněný"),
            ("F / F3", "ocelový plášť / zvlněný"),
            ("K", "zinkový plášť"),
            ("L / L2 / L4–L6", "olověný plášť (legovaný / čisté Pb / na žíle)"),
            ("A / A6", "koncentrický Al vodič / meandr"),
            ("C / C6 / C9", "koncentrický Cu / meandr / dělený"),
            ("A7 / A8", "Al stínění / na každé žíle"),
            ("C4 / C5", "Cu opletení nad žilami / na každé žíle"),
            ("C7 / C8", "Cu pásky/dráty nad žilami / na každé žíle"),
            ("D", "tenké ocelové pásky + holý kontaktní vodič"),
        ],
        columns=["Kód HD 361", "Význam"],
    )


def df_hd_armor() -> pd.DataFrame:
    return pd.DataFrame(
        [
            ("Z2 / Z3 / Z4", "pancíř kulaté / ploché ocelové dráty / ocelová páska"),
            ("Z5 / Z6 / Z7", "ocelové opletení / nosné opletení / tvarované dráty"),
            ("Y2 / Y3", "pancíř kulaté / ploché Al dráty"),
            ("Y5 / Y6", "speciální materiály / ocel + Cu dráty"),
            ("D2 / D3", "nosné prvky textil/ocel nad duší / v jádru"),
            ("D4", "samonosný — jádra jako tahové odlehčení"),
            ("D5", "středová vložka výtahového ovládacího kabelu"),
            ("D7 / D8", "nosný prvek vně / průřez „8“"),
            ("H / H2", "plochý dělitelný / nedělitelný"),
            ("H3 / H6", "můstkový / plochý HD 359 / EN 50214"),
            ("H7 / H8", "dvouvrstvá izolace / spirálový"),
        ],
        columns=["Kód", "Význam"],
    )


def df_nyy_examples() -> pd.DataFrame:
    return pd.DataFrame(
        [
            (
                "NYY-J 5×2,5 RE 0,6/1 kV",
                "norma · Cu · PVC izolace · PVC plášť · se zeleno-žlutou · "
                "5 žil · 2,5 mm² · kulaté plné · 0,6/1 kV",
            ),
            (
                "NYY-J 12×1,5 RE 0,6/1 kV",
                "12 žil 1,5 mm² RE, PVC/PVC, s PE žílou",
            ),
            (
                "NA2XS2Y 1×35 RM/16 6/10 kV",
                "v souladu s normou · Al · XLPE · stínění Cu 16 mm² · PE plášť · "
                "1 žíla 35 mm² laněná kulatá · 6/10 kV",
            ),
            (
                "N2XY 3×150 RM 0,6/1 kV",
                "Cu · XLPE izolace · PVC plášť · 3×150 laněné · NN",
            ),
            (
                "NYCWY",
                "Cu · PVC · koncentrický Cu vlnový · PVC plášť",
            ),
        ],
        columns=["Příklad", "Rozklad"],
    )


def df_soil_thermal() -> pd.DataFrame:
    return pd.DataFrame(
        [
            ("Velmi vlhká", 0.7),
            ("Vlhká (běžná)", 1.0),
            ("Suchá", 2.0),
            ("Písek / suché lože", 2.5),
            ("Velmi suchá", 3.0),
        ],
        columns=["Půda", "Měrný tepelný odpor [K·m/W]"],
    )


def df_air_distances() -> pd.DataFrame:
    return pd.DataFrame(
        [
            ("Od stěny / podlahy / stropu", "2 cm"),
            ("Mezi kabely nad sebou", "2 × D"),
            ("Mezi kabelovými systémy nad sebou", "20 cm"),
            ("Mezi kabely vedle sebe", "2 × D"),
            ("Standardní hloubka v zemi", "0,7 m (typicky 0,7–1,2 m)"),
            ("Teplota půdy (tabulková)", "20 °C"),
            ("Teplota vzduchu (tabulková)", "30 °C"),
            ("Cyklické zatížení EVU v zemi", "0,7 (jiné: 0,5 / 0,6 / 0,85 / 1,0)"),
        ],
        columns=["Podmínka", "Hodnota"],
    )


def df_group_factors() -> pd.DataFrame:
    """Sdružování obvodů — typické koeficienty DIN VDE 0298-4 (orientačně)."""
    return pd.DataFrame(
        [
            (1, 1.00), (2, 0.80), (3, 0.70), (4, 0.65),
            (5, 0.60), (6, 0.57), (7, 0.54), (8, 0.52),
            (9, 0.50), (12, 0.45), (16, 0.41), (20, 0.38),
        ],
        columns=["Počet obvodů vedle sebe", "Koeficient"],
    )


def df_install_methods() -> pd.DataFrame:
    return pd.DataFrame(
        [
            ("A1", "v trubce ve stěně, tepelně izolované"),
            ("A2", "vícežilový v trubce ve stěně"),
            ("B1", "v trubce na stěně"),
            ("B2", "vícežilový v trubce na stěně"),
            ("C", "na stěně / podhledu, volně"),
            ("D", "v zemi (chránička / přímo)"),
            ("E", "vícežilový volně ve vzduchu"),
            ("F", "jednožilové volně ve vzduchu, vedle sebe"),
            ("G", "jednožilové volně ve vzduchu, s rozestupem"),
        ],
        columns=["Způsob (IEC/VDE)", "Popis"],
    )


def df_x26_current() -> pd.DataFrame:
    """Proud do 1000 V — výběr z X 26 (volně ve vzduchu 1 žíla / na povrchu 2–3 žíly)."""
    return pd.DataFrame(
        [
            (0.75, 15, 6, 12),
            (1.0, 19, 10, 15),
            (1.5, 24, 16, 18),
            (2.5, 32, 25, 26),
            (4, 42, 32, 34),
            (6, 54, 40, 44),
            (10, 73, 63, 61),
            (16, 98, None, 82),
            (25, 129, None, 108),
            (35, 158, None, 135),
            (50, 198, None, 168),
            (70, 245, None, 207),
            (95, 292, None, 250),
            (120, 344, None, 292),
            (150, 391, None, 335),
            (185, 448, None, 382),
            (240, 528, None, 453),
            (300, 608, None, 523),
            (400, 726, None, None),
            (500, 830, None, None),
        ],
        columns=[
            "mm²",
            "Volně ve vzduchu 1 žíla [A]",
            "Na povrchu 2 žíly [A]",
            "Na povrchu 2–3 žíly (sk. ovládací) [A]",
        ],
    )


def df_safety_select() -> pd.DataFrame:
    return pd.DataFrame(
        [
            ("Provoz", "napětí, proud, ochranná opatření, způsob pokládky, sdružování, přístupnost"),
            ("Vnější vlivy", "teplota, déšť/pára/voda, chemikálie, mechanika, hlodavci, plísně, UV"),
            ("Životnost", "pevné kabely obecně déle než ohebné; limity DIN VDE / HD dodržovat společně"),
            ("Barva pláště", "černá poskytuje vyšší stupeň ochrany (UV) než ostatní barvy"),
            ("Účel", "není-li uvedeno jinak, jen přenos a rozvod el. energie"),
        ],
        columns=["Téma", "Požadavek (X 93)"],
    )


def df_pull_limits() -> pd.DataFrame:
    return pd.DataFrame(
        [
            ("Max. tah na všechny žíly dohromady", "1000 N (není-li schváleno jinak)"),
            ("Pevné uložení při pokládce", "50 N/mm² na jádro"),
            ("Ohebné / flex okruhy (staticky)", "15 N/mm²"),
            ("Ohyb při pokládce", "HD 516 S2 tab. 6 / DIN VDE 0298-300, okolí (20 ± 10) °C"),
            ("Zkrut", "ohebné kabely obecně nejsou na zkrut navrženy"),
        ],
        columns=["Situace", "Limit"],
    )


# ── Vyhledávací index (sekce se nemění, hledání na ně skočí) ──────────────────

_SECTION_KEYS = [
    ("scans", "📷 Všechny skeny"),
    ("ktg", "🛢️ Bubny KTG — rozměry"),
    ("ktgcap", "📦 Bubny KTG — kapacita (sken)"),
    ("bend", "↩️ Min. poloměr ohybu (VDE)"),
    ("colors", "🎨 Značení žil"),
    ("current", "⚡ Proudová zatížitelnost"),
    ("resist", "🔌 Odpor & průměry jader / AWG"),
    ("formulas", "📐 Elektrotechnické vzorce"),
    ("codes", "🏷️ Označovací kódy (H / NYY)"),
    ("din", "📚 Normy DIN VDE"),
    ("fire", "🔥 Požár, tah, materiály, SN"),
    ("certs", "✅ Certifikační značky"),
]


def _radio_label(key: str, n_scans: int) -> str:
    for k, lab in _SECTION_KEYS:
        if k == key:
            return f"{lab} ({n_scans})" if k == "scans" else lab
    return key


_KNOWN_X_PAGES: dict[int, tuple[str, str]] = {
    5: ("Odkazy na normy DIN VDE (silová zařízení)", "din vde 0100 0101 nemocnice výbuch blesk"),
    6: ("Odkazy na normy DIN VDE (kabely)", "din vde 0250 0262 0276 0281"),
    7: ("Harmonizované kódy HD 361 — napětí a izolace", "h05 h07 pvc xlpe kód označení"),
    8: ("Harmonizované kódy — jádra a žíly", "třída 1 5 6 -f -k -u"),
    9: ("Harmonizované kódy — plášť", "plášť pur chloropren"),
    10: ("Kovový plášť, stínění, pancíř HD 361", "stínění pancíř olovo koncentrický c4 z2"),
    11: ("Speciální provedení H / H2 / H8", "plochý spirálový samonosný"),
    12: ("Kódy silových kabelů DIN VDE 0271/0276", "nyy n2xy na2xs2y j o re rm"),
    15: ("Průměry jader VDE 0295", "průměr jádra třída 1 2 5 6"),
    16: ("Odpor jádra Ω/km", "odpor iec 60228 měď hliník"),
    17: ("Konstrukce lanění a AWG", "awg kcmil 7x0,5 třída 2 5 6"),
    19: ("Proud — provozní podmínky země / vzduch", "půda 0,7 m tepelný odpor 20 °c 30 °c"),
    20: ("Proud — přepočty a uspořádání", "sdružování koeficient vzdálenost 2d"),
    25: ("Proud C / E 90 °C jádro", "pokládka c e 90"),
    26: ("Proud do 1000 V a teplotně odolné", "h07v h07rn-f jz-500 volně ve vzduchu"),
    28: ("Proud ohebné kabely 30 °C", "skupina 1 2 3 pojistka"),
    32: ("Proud N2XY / NA2XY / N2XCY 0,6/1 kV", "xlpe země vzduch 90 °c"),
    41: ("XLPE 6–30 kV kapacita a indukčnost", "sn střední napětí µf/km mh/km trefoil"),
    61: ("Značení žil DIN 40705 / IEC 60446", "pe pen l1 n světlemodrá zeleno-žlutá"),
    62: ("Min. poloměr ohybu VDE 0298", "ohyb buben 4xd 6xd vlečný řetěz"),
    73: ("Požární zatížení kWh/m", "n2xh nhxmh e30 halogen"),
    90: ("Materiály izolace a pláště", "pvc xlpe pur silikon halogen"),
    91: ("Vlastnosti materiálů — pokračování", "hustota teplota hořlavost"),
    93: ("Bezpečnost a výběr kabelu", "vnější vlivy uv hlodavci chemikálie"),
    106: ("Certifikační značky", "vde ce ul ccc kema öve"),
    109: ("Rozměry bubnů KTG", "bubny fd kd l2 nosnost"),
}


def _scan_catalog_index() -> list[dict]:
    """Každý soubor ≈ stránka X 5, X 6, … podle pořadí ve složce."""
    out = []
    for i, p in enumerate(list_catalog_scans()):
        xpage = 5 + i
        title, extra = _KNOWN_X_PAGES.get(xpage, (f"Technická příloha — strana X {xpage}", ""))
        out.append({
            "file": p.name,
            "path": p,
            "xpage": xpage,
            "title": title,
            "keywords": f"{title} {extra} x{xpage} {p.name}".lower(),
        })
    return out


_EXTRACT_INDEX: list[dict] = [
    {"key": "ktg", "title": "Rozměry dřevěných / plastových / nevratných bubnů",
     "kw": "buben ktg čelo jádro fd kd l2 nosnost he 350"},
    {"key": "ktgcap", "title": "Kapacita bubnu — kolik metrů se vejde",
     "kw": "kapacita návin délka metr kd/d 15xd 20xd 40xd"},
    {"key": "bend", "title": "Minimální poloměr ohybu VDE 0298 / 0891",
     "kw": "ohyb bending radius buben vlečný řetěz kladka 4xd 6xd 7,5xd"},
    {"key": "colors", "title": "Značení žil L1/L2/L3/N/PE a telefonní čtyřky",
     "kw": "barva žíla pe pen n světlemodrá zeleno-žlutá vde 0816 hvězdicová"},
    {"key": "current", "title": "Proudová zatížitelnost — ohebné, C/E, X 26, sdružování",
     "kw": "proud ampér zatížitelnost 30°c 90°c skupina pojistka sdružování země vzduch n2xy"},
    {"key": "current", "title": "Pokládka do země / vzduchu — hloubka, půda, vzdálenosti",
     "kw": "země 0,7 m tepelný odpor vlhká suchá 2 cm 2d evu 0,7"},
    {"key": "resist", "title": "Odpor jádra Ω/km, průměry, AWG",
     "kw": "odpor ohm awg kcmil třída 1 2 5 6 průměr jádra iec 60228"},
    {"key": "formulas", "title": "Vzorce — odpor, úbytek napětí, průřez",
     "kw": "úbytek napětí kappa měď 58 hliník 33 smyčka cos phi průřez"},
    {"key": "codes", "title": "Rozklad kódu H07RN-F, H05VV-F, NYY, NA2XS2Y",
     "kw": "h07rn-f h05vv-f h07v-k nyy n2xy na2xs2y j o re rm stínění pancíř"},
    {"key": "codes", "title": "HD 361 — plášť, stínění, pancíř, ploché H/H2/H8",
     "kw": "hd 361 a2 c4 z2 pancíř olovo koncentrický spirálový"},
    {"key": "din", "title": "Normy DIN VDE 0100 … 0816",
     "kw": "din vde 0100 0101 0250 0276 0298 koupelna výbuch blesk nemocnice"},
    {"key": "fire", "title": "Požární zatížení N2XH / E30, tah 50/15 N/mm²",
     "kw": "požár kwh/m n2xh nhxmh e30 halogen tah 50 n/mm2 15 n/mm2"},
    {"key": "fire", "title": "XLPE 6–30 kV — kapacita a indukčnost",
     "kw": "xlpe 6/10 12/20 18/30 kv kapacita indukčnost trefoil"},
    {"key": "fire", "title": "Materiály PVC, XLPE, PUR, silikon, bezhalogen",
     "kw": "pvc xlpe pe pur chloropren silikon fep ptfe halogen teplota"},
    {"key": "fire", "title": "Výběr kabelu — provoz a vnější vlivy",
     "kw": "bezpečnost uv hlodavci chemikálie déšť výběr černá plášť"},
    {"key": "certs", "title": "Značky VDE, CE, UL, CCC, KEMA, ÖVE…",
     "kw": "certifikace vde ce ul ccc kema öve csa bsi imq nemko semko"},
    {"key": "scans", "title": "Prohlížeč všech naskenovaných stránek",
     "kw": "sken fotka katalog stránka x"},
]


def search_catalog(query: str) -> list[dict]:
    """Vrátí zásahy ve výpiscích i ve skenech (název strany)."""
    q = (query or "").strip().lower()
    if len(q) < 2:
        return []
    hits: list[dict] = []
    for item in _EXTRACT_INDEX:
        blob = f"{item['title']} {item['kw']}".lower()
        if q in blob or all(part in blob for part in q.split()):
            hits.append({
                "kind": "Výpisek",
                "title": item["title"],
                "key": item["key"],
                "file": "",
            })
    for sc in _scan_catalog_index():
        if q in sc["keywords"] or q in sc["file"].lower():
            hits.append({
                "kind": "Sken",
                "title": f"X {sc['xpage']} — {sc['title']}",
                "key": "scans",
                "file": sc["file"],
            })
    # unique by title
    seen: set[str] = set()
    uniq = []
    for h in hits:
        k = h["title"]
        if k not in seen:
            seen.add(k)
            uniq.append(h)
    return uniq[:40]


def explain_h_code(raw: str) -> list[str]:
    """Hrubý rozklad harmonizovaného kódu (H05VV-F, H07RN-F 3G1,5)."""
    s = raw.upper().replace(" ", "").replace(",", ".")
    bits: list[str] = []
    if s.startswith("H"):
        bits.append("H = harmonizovaný typ")
    elif s.startswith("A"):
        bits.append("A = schválený národní typ")
    for k, v in _H_VOLTAGE.items():
        if k in s[:4]:
            bits.append(f"{k} = jmenovité napětí {v}")
            break
    for k, v in sorted(_H_INSUL.items(), key=lambda x: -len(x[0])):
        if k in s:
            bits.append(f"{k} = {v}")
    for k, v in _H_CORE.items():
        if f"-{k}" in s or s.endswith(k) or f"{k}3" in s or f"{k}5" in s:
            if any(k in part for part in (s[4:8], s[-3:])):
                bits.append(f"{k} = jádro: {v}")
                break
    if "G" in s[4:]:
        bits.append("G = se zeleno-žlutou ochrannou žílou")
    if "X" in s[5:] and "2X" not in s:
        bits.append("X = bez ochranné žíly")
    return bits or ["Kód nerozeznán — zkus např. H07RN-F 3G1,5 nebo H07V-K."]


# ── UI ────────────────────────────────────────────────────────────────────────

def render_helukabel_catalog() -> None:
    """Technické tabulky ze skenů HELUKABEL — referenční hub."""
    n_scans = len(list_catalog_scans())
    st.markdown("### 📗 Technické tabulky HELUKABEL")
    st.markdown(
        '<div class="info-box" style="margin-bottom:12px;">'
        f"Digitální výpisky + prohlížeč skenů "
        f"(<code>assets/helukabel/</code>, {n_scans} stránek). "
        "Nahoře hledej — otevře se příslušná <strong>sekce</strong>."
        "</div>",
        unsafe_allow_html=True,
    )

    q = st.text_input(
        "Hledat v katalogu",
        placeholder="např. ohyb, NYY, H07RN-F, proud, AWG, požár, VDE, buben…",
        key="helu_q",
    )
    hits = search_catalog(q)
    if q.strip() and not hits:
        st.caption("Nic nenalezeno — zkus kratší slovo (ohyb, proud, NYY, PE…).")
    elif hits:
        labels = [f"{h['kind']}: {h['title']}" for h in hits]
        chosen = st.selectbox("Nalezené položky", labels, key="helu_hit_sel")
        hit = hits[labels.index(chosen)]
        if st.button("Otevřít sekci", key="helu_go"):
            st.session_state["helu_topic"] = _radio_label(hit["key"], n_scans)
            if hit.get("file"):
                st.session_state["helu_scan_q"] = hit["file"]
            st.rerun()

    options = [_radio_label(k, n_scans) for k, _ in _SECTION_KEYS]
    if "helu_topic" not in st.session_state or st.session_state["helu_topic"] not in options:
        st.session_state["helu_topic"] = options[0]

    topic = st.radio(
        "Sekce",
        options=options,
        horizontal=True,
        key="helu_topic",
    )
    st.markdown("<br>", unsafe_allow_html=True)

    if topic.startswith("📷"):
        _render_all_scans()
    elif topic.startswith("🛢️"):
        _render_ktg_dims()
    elif topic.startswith("📦"):
        _render_ktg_capacity()
    elif topic.startswith("↩️"):
        _render_bend()
    elif topic.startswith("🎨"):
        _render_colors()
    elif topic.startswith("⚡"):
        _render_current()
    elif topic.startswith("🔌"):
        _render_resistance_awg()
    elif topic.startswith("📐"):
        _render_formulas()
    elif topic.startswith("🏷️"):
        _render_codes()
    elif topic.startswith("📚"):
        _render_din_vde()
    elif topic.startswith("🔥"):
        _render_fire_materials()
    else:
        _render_certs()


def _render_all_scans() -> None:
    meta = _scan_catalog_index()
    if not meta:
        st.warning("Ve složce `assets/helukabel/` zatím nejsou žádné skeny.")
        return
    q = st.text_input("Filtrovat název / stranu / téma", key="helu_scan_q")
    if q.strip():
        ql = q.strip().lower()
        meta = [s for s in meta if ql in s["keywords"] or ql in s["file"].lower()]
    if not meta:
        st.info("Žádný sken neodpovídá filtru.")
        return
    page_size = 10
    n_pages = max(1, (len(meta) + page_size - 1) // page_size)
    page = st.number_input(
        f"List (po {page_size} skenech, zobrazeno {len(meta)})",
        min_value=1, max_value=n_pages, value=1, step=1,
        key="helu_scan_page",
    )
    start = (int(page) - 1) * page_size
    for s in meta[start : start + page_size]:
        with st.expander(f"X {s['xpage']} — {s['title']}  ({s['file']})", expanded=False):
            st.image(str(s["path"]), use_container_width=True)


def _render_ktg_dims() -> None:
    st.markdown("##### Dřevěné bubny (standard)")
    st.dataframe(df_ktg_wood(), use_container_width=True, hide_index=True)
    st.markdown("##### Plastové bubny")
    st.dataframe(df_ktg_plastic(), use_container_width=True, hide_index=True)
    st.markdown("##### Nevratné dřevěné bubny")
    st.dataframe(df_ktg_disposable(), use_container_width=True, hide_index=True)
    st.caption(
        "Fd = průměr čela · Kd = průměr jádra · Bd = otvor · "
        "I₁ = celková šířka · I₂ = šířka návinu."
    )
    _show_scan("01_ktg_rozmery.png", "Rozměry KTG")


def _render_ktg_capacity() -> None:
    st.markdown(
        '<div class="info-box">'
        "Katalogová matice <strong>ø kabelu × buben → délka [m]</strong> "
        "je velmi hustá (D 6–92 mm). Níže je originální sken + rychlý filtr "
        "podle poměru <code>Kd / D</code> (barevná legenda HELUKABEL)."
        "</div>",
        unsafe_allow_html=True,
    )
    d_cab = st.number_input(
        "Průměr kabelu D [mm] — kontrola ohybu vs KTG jádra",
        min_value=1.0, max_value=120.0, value=20.0, step=1.0,
        key="helu_cap_d",
    )
    legend = [
        (40, "🟠 ≤ 40 × D"),
        (30, "🟡 ≤ 30 × D"),
        (25, "🩷 ≤ 25 × D"),
        (20, "🟢 ≤ 20 × D"),
        (15, "🔵 ≤ 15 × D"),
    ]
    rows = []
    for code, vel, fd, kd, _bd, _i1, i2, max_kg, mass in _KTG_WOOD:
        ratio = kd / d_cab if d_cab else None
        tag = "—"
        if ratio is not None:
            for lim, label in legend:
                if kd <= lim * d_cab:
                    tag = label
                    break
            else:
                tag = "⬜ mimo barevné pásmo (jádro velké / D malé)"
        rows.append({
            "Kód": f"{code}/{vel}",
            "Fd": fd, "Kd": kd, "I₂": i2,
            "Kd / D": round(ratio, 1) if ratio else "—",
            "Legenda HELUKABEL": tag,
            "Max. nosnost [kg]": max_kg,
            "Hmotnost [kg]": mass,
        })
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    st.caption(
        "Barva v katalogu znamená, že jádro ještě splňuje daný max. násobek D "
        "(přísnější = menší násobek). Přesné metry návinu: sken níže, "
        "nebo kalkulačka Kapacita bubnu s vlastními rozměry."
    )
    _show_scan("02_ktg_kapacita.png", "Kapacita KTG a délky kabelů")


def _render_bend() -> None:
    st.markdown("##### Silové kabely 0,6/1 kV — pevné uložení (DIN VDE 0298-3)")
    st.dataframe(df_bend_power_fixed(), use_container_width=True, hide_index=True)
    st.markdown("##### Ohebné kabely (DIN VDE 0298-3)")
    st.dataframe(df_bend_flexible(), use_container_width=True, hide_index=True)
    st.markdown("##### Instalační / komunikační (DIN VDE 0891-5 / 0815)")
    st.dataframe(df_bend_install_comm(), use_container_width=True, hide_index=True)

    st.markdown("##### Rychlá kontrola — ohebné kabely")
    c1, c2 = st.columns(2)
    with c1:
        d = st.number_input("Vnější Ø D [mm]", 1.0, 80.0, 16.0, 0.5, key="helu_bend_d")
    with c2:
        mode = st.selectbox(
            "Způsob",
            options=[
                "Pevné uložení", "Volný pohyb", "Při zavádění",
                "Nucené vedení (návin na buben)", "Trolejový kabel",
                "Ve vlečných řetězech", "Navíjení přes kladku",
            ],
            index=3,
            key="helu_bend_mode",
        )
    factor = bend_factor_flexible(float(d), mode)
    if factor:
        r_min = factor * float(d)
        kd_min = 2.0 * r_min
        st.success(
            f"Min. poloměr ohybu **{factor:g} × D = {r_min:.1f} mm** · "
            f"min. průměr jádra bubnu ≈ **{kd_min:.0f} mm** (2 × poloměr)."
        )
    st.caption("Hodnoty v tabulkách nepřekračovat — zkracuje životnost kabelu.")
    _show_scan("05_ohyb_vde.png", "Min. poloměr ohybu VDE")


def _render_colors() -> None:
    st.markdown("##### DIN 40705 / IEC 60446 — značení vodičů")
    st.dataframe(df_core_colors_din(), use_container_width=True, hide_index=True)
    st.markdown(
        "- Světlemodrá = **jen N / střední** (nepoužívat jinde při riziku záměny).\n"
        "- Zeleno-žlutá = **jen PE / PEN**.\n"
        "- Vnitřní rozvody zařízení: preferovat černou / hnědou; při stejných barvách číslovat."
    )
    _show_scan("06_znaceni_zil_din.png", "Značení žil DIN/IEC")

    st.markdown("##### DIN VDE 0816 — venkovní telefonní (hvězdicová čtyřka)")
    c1, c2 = st.columns(2)
    with c1:
        st.dataframe(df_vde0816_quads(), use_container_width=True, hide_index=True)
    with c2:
        st.dataframe(df_vde0816_rings(), use_container_width=True, hide_index=True)
    st.caption(
        "Základní svazek = 5 čtyřek = 10 DA · hlavní svazek 50 nebo 100 DA · "
        "počítací svazek = červená spirála."
    )
    _show_scan("07_znaceni_vde0816.png", "Barevné značení VDE 0816")


def _render_current() -> None:
    st.markdown("##### Ohebné kabely — proud @ 30 °C (katalog X 28)")
    st.caption(
        "Sk.1 = jednožilové v trubce · Sk.2 = vícežilové / kanály · "
        "Sk.3 = jednožilové volně ve vzduchu (rozestup ≥ D)."
    )
    st.dataframe(df_current_flex(), use_container_width=True, hide_index=True)
    st.markdown("##### Přepočítací koeficienty — teplota okolí > 30 °C")
    st.dataframe(df_temp_corr_pvc_rubber(), use_container_width=True, hide_index=True)

    st.markdown("##### Kabely do 1000 V / teplotně odolné (X 26)")
    st.caption(
        "Volně ve vzduchu = 1 zatížená žíla (H07V-K, H07RN-F…). "
        "Na povrchu 2–3 žíly = šňůry / ovládací (JZ, PUR, MULTIFLEX…)."
    )
    st.dataframe(df_x26_current(), use_container_width=True, hide_index=True)

    st.markdown("##### Pevné uložení — pokládka C / E (90 °C jádro, 30 °C okolí)")
    st.dataframe(df_current_cefg_90(), use_container_width=True, hide_index=True)

    st.markdown("##### Provozní podmínky (X 19) — země / vzduch")
    st.dataframe(df_air_distances(), use_container_width=True, hide_index=True)
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("###### Měrný tepelný odpor půdy")
        st.dataframe(df_soil_thermal(), use_container_width=True, hide_index=True)
    with c2:
        st.markdown("###### Sdružování obvodů (orientační koeficient)")
        st.dataframe(df_group_factors(), use_container_width=True, hide_index=True)
    st.markdown("###### Způsoby pokládky IEC / VDE")
    st.dataframe(df_install_methods(), use_container_width=True, hide_index=True)
    st.caption(
        "N2XY / NA2XY / N2XCY 0,6/1 kV (země 20 °C / vzduch 30 °C, XLPE 90 °C) — "
        "hustá matice do 1000 mm² je ve skenech (strana X 32). "
        "Hledej „N2XY“ nahoře."
    )


def _render_resistance_awg() -> None:
    st.markdown("##### Max. odpor jádra @ 20 °C [Ω/km] (VDE 0295 / IEC 60228)")
    st.dataframe(df_core_resistance(), use_container_width=True, hide_index=True)
    st.caption(
        "Třída 1 = plný · 2 = laněný · 5 = jemně laněný · 6 = velmi jemně laněný."
    )
    _show_scan("10_odpor_jadra.png", "Odpor jádra")

    st.markdown("##### Průměry jader podle VDE 0295 (DIN EN 60228)")
    st.dataframe(df_core_diameters(), use_container_width=True, hide_index=True)
    st.caption(
        "¹ min-ø jen Al · ² max-ø tř.1 s minerální izolací (Cu) · "
        "³ min-ø Cu tř.1 není stanoven."
    )
    _show_scan("12_prumery_vde0295.png", "Průměry jader VDE 0295")

    st.markdown("##### Převod AWG / kcmil → mm²")
    c1, c2 = st.columns([1, 2])
    with c1:
        awg_in = st.text_input("AWG nebo kcmil", value="10", key="helu_awg")
        mm = None
        raw = awg_in.strip().lower().replace(" ", "")
        for a, m in _AWG:
            if str(a).lower() == raw or f"{a}awg" == raw:
                mm = m
                break
        if mm is None and "kcmil" in raw:
            try:
                k = int("".join(ch for ch in raw if ch.isdigit()))
                for kk, m in _KCMIL:
                    if kk == k:
                        mm = m
                        break
            except ValueError:
                pass
        if mm is not None:
            st.success(f"**{awg_in}** ≈ **{mm} mm²**")
        else:
            st.caption("Zkus např. 10, 4/0, 500 kcmil")
    with c2:
        st.dataframe(df_awg(), use_container_width=True, hide_index=True)
    _show_scan("11_konstrukce_awg.png", "Konstrukce lanění + AWG")


def _render_formulas() -> None:
    st.markdown("##### Vodivost materiálů")
    st.dataframe(df_conductivity(), use_container_width=True, hide_index=True)

    st.markdown("##### Kalkulačka — odpor / úbytek napětí / průřez")
    mode = st.selectbox(
        "Výpočet",
        [
            "Odpor jádra R",
            "Úbytek napětí u",
            "Potřebný průřez q (z proudu)",
            "Průřez plného jádra z průměru",
        ],
        key="helu_f_mode",
    )
    mat = st.selectbox("Materiál", list(_KAPPA.keys()), key="helu_f_mat")
    kappa = _KAPPA[mat]

    if mode.startswith("Odpor"):
        c1, c2, c3 = st.columns(3)
        with c1:
            length = st.number_input("Délka l [m]", 1.0, 1e6, 100.0, key="helu_f_l")
        with c2:
            q = st.number_input("Průřez q [mm²]", 0.05, 1000.0, 2.5, key="helu_f_q")
        with c3:
            loop = st.checkbox("Smyčka (tam+zpět ×2)", value=True, key="helu_f_loop")
        r = (2.0 if loop else 1.0) * length / (kappa * q)
        st.metric("R", f"{r:.4f} Ω")

    elif mode.startswith("Úbytek"):
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            length = st.number_input("l [m]", 1.0, 1e6, 50.0, key="helu_f_ul")
        with c2:
            q = st.number_input("q [mm²]", 0.05, 1000.0, 2.5, key="helu_f_uq")
        with c3:
            i = st.number_input("I [A]", 0.1, 5000.0, 16.0, key="helu_f_ui")
        with c4:
            system = st.selectbox("Soustava", ["DC", "1f AC", "3f AC"], key="helu_f_sys")
        cos_phi = 1.0
        if system != "DC":
            cos_phi = st.slider("cos φ", 0.5, 1.0, 0.9, 0.05, key="helu_f_cos")
        if system == "DC":
            u = 2 * length * i / (kappa * q)
        elif system == "1f AC":
            u = 2 * length * i * cos_phi / (kappa * q)
        else:
            u = 1.732 * length * i * cos_phi / (kappa * q)
        st.metric("Úbytek napětí u", f"{u:.2f} V")
        st.caption("Doporučení NN: typicky 3–5 % Un. Velké průřezy: zohlednit i reaktanci.")

    elif mode.startswith("Potřebný"):
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            length = st.number_input("l [m]", 1.0, 1e6, 50.0, key="helu_f_ql")
        with c2:
            i = st.number_input("I [A]", 0.1, 5000.0, 16.0, key="helu_f_qi")
        with c3:
            u_allow = st.number_input("Max. u [V]", 0.1, 100.0, 5.0, key="helu_f_qu")
        with c4:
            system = st.selectbox("Soustava", ["DC / 1f", "3f AC"], key="helu_f_qsys")
        cos_phi = st.slider("cos φ (AC)", 0.5, 1.0, 0.9, 0.05, key="helu_f_qcos")
        if system.startswith("DC"):
            q = 2 * length * i / (kappa * u_allow)
            if st.checkbox("Jednofázové AC (× cos φ)", value=False, key="helu_f_q1f"):
                q = 2 * length * i * cos_phi / (kappa * u_allow)
        else:
            q = 1.732 * length * i * cos_phi / (kappa * u_allow)
        st.metric("Potřebný průřez q", f"{q:.2f} mm²")

    else:
        d = st.number_input("Průměr jádra D [mm]", 0.1, 100.0, 1.78, 0.01, key="helu_f_d")
        q = 3.1415926535 * d * d / 4.0
        st.metric("Průřez q", f"{q:.3f} mm²")
        st.caption("Laněné: q ≈ 0,7854 · d² · n (n = počet drátů).")

    _show_scan("03_vzorce_elektro.png", "Základní vzorce (elektro)")
    _show_scan("04_vzorce_silnoproud.png", "Vzorce silnoproud")


def _render_codes() -> None:
    st.markdown("##### Harmonizované kódy (DIN VDE 0292 / HD 361)")
    st.dataframe(df_h_code_legend(), use_container_width=True, hide_index=True)
    raw = st.text_input("Rozložit kód", value="H07RN-F 3G1,5", key="helu_h_parse")
    for line in explain_h_code(raw):
        st.write(f"· {line}")
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("###### Izolace / plášť")
        st.dataframe(df_h_insulation(), use_container_width=True, hide_index=True)
    with c2:
        st.markdown("###### Jádro (-U/-R/-K/-F/-H)")
        st.dataframe(df_h_cores(), use_container_width=True, hide_index=True)
    st.markdown("##### Srovnání nová / stará zkratka")
    st.dataframe(df_old_new_codes(), use_container_width=True, hide_index=True)
    st.markdown("##### Silové kabely DIN VDE 0271 / 0276 (NYY, N2XY…)")
    st.dataframe(
        pd.DataFrame(_NYY_PARTS, columns=["Znak", "Význam"]),
        use_container_width=True, hide_index=True,
    )
    st.markdown("###### Příklady rozkladu")
    st.dataframe(df_nyy_examples(), use_container_width=True, hide_index=True)
    st.markdown("##### HD 361 — kovový plášť, koncentrický vodič, stínění")
    st.dataframe(df_hd_metal_shield(), use_container_width=True, hide_index=True)
    st.markdown("##### HD 361 — pancíř, nosné prvky, ploché / spirálové")
    st.dataframe(df_hd_armor(), use_container_width=True, hide_index=True)


def _render_din_vde() -> None:
    st.markdown("##### Odkazy na normy DIN VDE (X 5–X 6)")
    st.dataframe(df_din_vde_refs(), use_container_width=True, hide_index=True)
    st.caption("Kompletní znění norem je ve skenech — hledej číslo normy nahoře.")


def _render_fire_materials() -> None:
    sub = st.selectbox(
        "Téma",
        [
            "Proud C / E (90 °C jádro)",
            "SN XLPE — kapacita a indukčnost",
            "Požární zatížení (výběr)",
            "Tah / ohyb při pokládce",
            "Materiály izolace a pláště",
            "Výběr kabelu — bezpečnost (X 93)",
        ],
        key="helu_fire_sub",
    )
    if sub.startswith("Proud"):
        st.caption("Pevné uložení v budovách, 90 °C jádro, 30 °C okolí (X 25).")
        st.dataframe(df_current_cefg_90(), use_container_width=True, hide_index=True)
    elif sub.startswith("SN"):
        st.markdown("##### Provozní kapacita XLPE 6–30 kV [µF/km]")
        st.dataframe(df_xlpe_mv_cap(), use_container_width=True, hide_index=True)
        st.markdown("##### Indukčnost — Δ trefoil / — vedle sebe [mH/km]")
        st.dataframe(df_xlpe_mv_ind(), use_container_width=True, hide_index=True)
    elif sub.startswith("Požární"):
        st.dataframe(df_fire_load_n2xh(), use_container_width=True, hide_index=True)
        st.caption("Výběr z X 73. Kompletní typy NHXAF / NHXMH / N2XH / N2XCH / E30 ve skenech.")
    elif sub.startswith("Tah"):
        st.dataframe(df_pull_limits(), use_container_width=True, hide_index=True)
    elif sub.startswith("Materiály"):
        st.dataframe(df_materials_key(), use_container_width=True, hide_index=True)
        st.caption("Zjednodušený výběr z X 90–91. Plná matice vlastností je ve skenech.")
    else:
        st.dataframe(df_safety_select(), use_container_width=True, hide_index=True)


def _render_certs() -> None:
    st.markdown("##### Mezinárodní certifikační značky (X 106)")
    st.dataframe(df_cert_marks(), use_container_width=True, hide_index=True)
