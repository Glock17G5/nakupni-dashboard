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
# Standardní hodnoty (katalog HELUKABEL X 16 / IEC 60228).

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


# ── Proudová zatížitelnost (ohebné, 30 °C) — výběr z katalogu X 28 ─────────────

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


# ── UI ────────────────────────────────────────────────────────────────────────

def render_helukabel_catalog() -> None:
    """Technické tabulky ze skenů HELUKABEL — referenční hub."""
    st.markdown("### 📗 Technické tabulky HELUKABEL")
    st.markdown(
        '<div class="info-box" style="margin-bottom:12px;">'
        "Digitální přepis skenů z technické přílohy katalogu. "
        "U hustých matic (kapacita bubnů, proud do 1000 V, konstrukce lanění) "
        "je k dispozici i <strong>originální sken</strong>. "
        "Pro vlastní bubny použij kalkulačku <em>Kapacita bubnu</em> — "
        "KTG rozměry slouží jako předloha / srovnání."
        "</div>",
        unsafe_allow_html=True,
    )

    topic = st.radio(
        "Sekce",
        options=[
            "🛢️ Bubny KTG — rozměry",
            "📦 Bubny KTG — kapacita (sken)",
            "↩️ Min. poloměr ohybu (VDE)",
            "🎨 Značení žil",
            "⚡ Proudová zatížitelnost",
            "🔌 Odpor & průměry jader / AWG",
            "📐 Elektrotechnické vzorce",
        ],
        horizontal=True,
        key="helu_topic",
    )
    st.markdown("<br>", unsafe_allow_html=True)

    if topic.startswith("🛢️"):
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
    else:
        _render_formulas()


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
    _show_scan("08_proud_ohebne.png", "Proudová zatížitelnost ohebné")

    st.markdown("##### Kabely do 1000 V / teplotně odolné (X 26)")
    st.info(
        "Tabulka je závislá na typu kabelu a způsobu uložení — "
        "pro přesnost otevři originální sken (více sloupců podle typů)."
    )
    _show_scan("09_proud_do1000v.png", "Proud do 1000 V")


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
            q = 2 * length * i / (kappa * u_allow)  # DC; for 1f multiply cos in AC case
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
