"""
Referenční tabulky a skeny z katalogu HELUKABEL (technická příloha).
Použití: hub Nástroje & tipy → „Technické tabulky HELUKABEL“.
"""

from __future__ import annotations

from pathlib import Path
import re

import pandas as pd
import streamlit as st

try:
    from i18n import t
except ImportError:
    def t(text: str, **kwargs) -> str:  # type: ignore[misc]
        return text.format(**kwargs) if kwargs else text

_ASSETS = Path(__file__).resolve().parent / "assets" / "helukabel"


def _img(name: str) -> Path:
    return _ASSETS / name


# Ověřené JPG (pata stránky v katalogu). Staré PNG názvy → tyto soubory.
_SCAN_ALIASES: dict[str, list[str]] = {
    "01_ktg_rozmery.png": ["IMG_20260813_141120.jpg"],  # X 109
    "02_ktg_kapacita.png": ["IMG_20260813_141129.jpg"],  # X 110
    "03_vzorce_elektro.png": ["IMG_20260813_141102.jpg"],  # X 107
    "04_vzorce_silnoproud.png": ["IMG_20260813_141111.jpg"],  # X 108
    "05_ohyb_vde.png": ["IMG_20260813_140018.jpg"],  # X 62
    "06_znaceni_zil_din.png": ["IMG_20260813_140005.jpg"],  # X 61
    "07_znaceni_vde0816.png": ["IMG_20260813_135931.jpg"],  # X 59
    "08_proud_ohebne.png": ["IMG_20260813_135308.jpg"],  # X 28
    "09_proud_do1000v.png": ["IMG_20260813_135241.jpg"],  # X 26
    "10_odpor_jadra.png": [],  # X 16 v sadě chybí
    "11_konstrukce_awg.png": ["IMG_20260813_135028.jpg"],  # X 17
    "12_prumery_vde0295.png": ["IMG_20260813_135008.jpg"],  # X 15
}

# filename → (strana X, titulek, keywords) — jen ověřené paty
_SCAN_META: dict[str, tuple[int, str, str]] = {
    "IMG_20260813_134726.jpg": (5, "Odkazy na normy DIN VDE (silová zařízení)", "din vde 0100"),
    "IMG_20260813_134737.jpg": (6, "Odkazy na normy DIN VDE (kabely)", "din vde 0276 0281 0298"),
    "IMG_20260813_134753.jpg": (8, "Harmonizované kódy H05 / H07", "h07rn-f h05vv-f hd 361"),
    "IMG_20260813_134918.jpg": (12, "Kódy silových kabelů NYY / N2XY", "nyy na2xs2y j o re rm"),
    "IMG_20260813_134930.jpg": (13, "Kódy telefonních a zapojovacích kabelů", "telefon stínění pancíř"),
    "IMG_20260813_134951.jpg": (14, "Vysvětlení označovacích kódů", "cu pvc xlpe zkratky"),
    "IMG_20260813_135008.jpg": (15, "Průměry jader VDE 0295", "průměr jádra třída 1 2 5 6"),
    "IMG_20260813_135028.jpg": (17, "Konstrukce lanění a AWG", "awg kcmil třída 2 5 6"),
    "IMG_20260813_135042.jpg": (18, "Jmenovité a provozní napětí", "u0/u 0,6/1 kv"),
    "IMG_20260813_135053.jpg": (19, "Proud — provozní podmínky země / vzduch", "půda 0,7 m 30 °c"),
    "IMG_20260813_135231.jpg": (25, "Proud C / E / F / G 90 °C jádro", "pokládka c e n2xy"),
    "IMG_20260813_135241.jpg": (26, "Proud do 1000 V a teplotně odolné", "h07v h07rn-f jz-500"),
    "IMG_20260813_135255.jpg": (27, "Proud od 0,6/1 kV — guma / řetězy", "nsgaöu nshxafö"),
    "IMG_20260813_135308.jpg": (28, "Proud ohebné kabely 30 °C", "skupina 1 2 3 pojistka"),
    "IMG_20260813_135329.jpg": (30, "Proud kabely se silikonovou izolací", "silikon 150 °c"),
    "IMG_20260813_135504.jpg": (39, "XLPE 6–30 kV — odpor R20 / Rδ", "odpor měď hliník"),
    "IMG_20260813_135516.jpg": (40, "XLPE 6–30 kV — Rstř a XL", "střídavý odpor indukční"),
    "IMG_20260813_135549.jpg": (41, "XLPE 6–30 kV — kapacita a indukčnost", "µf/km mh/km trefoil"),
    "IMG_20260813_135621.jpg": (43, "XLPE 6–30 kV — zemní zkrat / stínění", "zkrat kA stínění"),
    "IMG_20260813_135931.jpg": (59, "Značení žil DIN VDE 0816", "telefon čtyřka svazek"),
    "IMG_20260813_140005.jpg": (61, "Značení žil DIN 40705 / IEC 60446", "pe pen l1 n světlemodrá"),
    "IMG_20260813_140018.jpg": (62, "Min. poloměr ohybu VDE 0298", "ohyb buben 4xd 6xd"),
    "IMG_20260813_140259.jpg": (74, "Požární zatížení — E30 / E90", "n2xh e30 halogen"),
    "IMG_20260813_140316.jpg": (75, "Požární zatížení bezhalogenových kabelů", "nhxhx kwh/m"),
    "IMG_20260813_140520.jpg": (89, "Mezinárodní zkratky norem", "iec din vde ul"),
    "IMG_20260813_140555.jpg": (90, "Vlastnosti izolace a pláště (X 90–91)", "pvc xlpe pur silikon"),
    "IMG_20260813_140642.jpg": (93, "Bezpečnost a výběr kabelu", "uv hlodavci chemikálie"),
    "IMG_20260813_141053.jpg": (106, "Certifikační značky", "vde ce ul ccc kema"),
    "IMG_20260813_134822.jpg": (9, "Harmonizované kódy — plášť", "plášť pur chloropren"),
    "IMG_20260813_134840.jpg": (10, "Kovový plášť, stínění, pancíř HD 361", "stínění pancíř olovo"),
    "IMG_20260813_134907.jpg": (11, "Speciální provedení H / H2 / H8", "plochý spirálový samonosný"),
    "IMG_20260813_135105.jpg": (20, "Způsoby pokládky A1–G", "a1 a2 b1 b2 c e f g trubka stěna"),
    "IMG_20260813_135121.jpg": (21, "Podmínky pokládky země / vzduch", "0,7 m 20 °c 30 °c 2 cm trefoil"),
    "IMG_20260813_135133.jpg": (22, "Proud A1/A2/B1/B2 — 70 °C jádro", "nym h07v 70 °c"),
    "IMG_20260813_135148.jpg": (23, "Proud C/E/F/G — 70 °C jádro", "nyy nym 70 °c volně ve vzduchu"),
    "IMG_20260813_135158.jpg": (24, "Proud A1/A2/B1/B2 — 90 °C jádro", "n2xy h07v2 90 °c"),
    "IMG_20260813_135255.jpg": (27, "Proud NSGAÖU / NSSHÖU od 0,6/1 kV", "guma řetěz nsgaöu"),
    "IMG_20260813_135319.jpg": (29, "Proud — pokračování ohebných / speciál", "ohebné speciál"),
    "IMG_20260813_135340.jpg": (31, "Proud NYY / NAYY / NYCWY 0,6/1 kV", "nyy nayy země vzduch"),
    "IMG_20260813_135348.jpg": (32, "Proud N2XY / NA2XY 0,6/1 kV", "n2xy na2xy xlpe 90 °c"),
    "IMG_20260813_135357.jpg": (33, "Proud NYKY 0,6/1 kV", "nyky olovo"),
    "IMG_20260813_135409.jpg": (34, "Přepočty sdružování na stěně / stropě", "sdružování pod stropem mezera d"),
    "IMG_20260813_135420.jpg": (35, "Přepočty teplota okolí / navíjení", "koeficient 70 °c 90 °c buben vrstvy"),
    "IMG_20260813_135610.jpg": (42, "XLPE 6–30 kV — pokračování elektrických hodnot", "xlpe zkrat"),
    "IMG_20260813_141102.jpg": (107, "Základní vzorce z elektrotechniky", "ohm kappa odpor kapacita"),
    "IMG_20260813_141111.jpg": (108, "Vzorce ze silnoproudé elektrotechniky", "úbytek napětí průřez cos phi"),
    "IMG_20260813_141120.jpg": (109, "Rozměry kabelových bubnů KTG", "ktg buben fd kd l2 nosnost"),
    "IMG_20260813_141129.jpg": (110, "Kapacita bubnů KTG a délky kabelů", "kapacita návin metry 15xd 40xd"),
    "IMG_20260813_141137.jpg": (111, "Vysvětlující poznámky k označování CE", "ce nsr emc"),
    "IMG_20260813_141409.jpg": (125, "Rejstřík podle typů kabelů", "index traycontrol"),
}


def _resolve_scan(filename: str) -> Path | None:
    """Najde sken: přesný soubor, nebo alias ze starého PNG názvu."""
    direct = _img(filename)
    if direct.is_file():
        return direct
    for alt in _SCAN_ALIASES.get(filename, []):
        p = _img(alt)
        if p.is_file():
            return p
    return None


def _dash(v):
    return "—" if v is None else v


def _show_scan(filename: str, caption: str, expanded: bool = False) -> None:
    """Zobrazí sken. Chybějící soubor tiše přeskočí — nikdy nehlásí ‚nenalezen‘."""
    path = _resolve_scan(filename)
    if path is None:
        return
    with st.expander(f"📷 Originální sken — {caption}", expanded=expanded):
        st.image(str(path), use_container_width=True)


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
    """Proud C/E/F/G @ 90 °C jádro / 30 °C okolí (X 25)."""
    rows = [
        (1.5, 24, 22, 26, 23, None, None, None, None, None),
        (2.5, 33, 30, 36, 32, None, None, None, None, None),
        (4, 45, 40, 49, 42, None, None, None, None, None),
        (6, 58, 52, 63, 54, None, None, None, None, None),
        (10, 80, 71, 86, 75, None, None, None, None, None),
        (16, 107, 96, 115, 100, None, None, None, None, None),
        (25, 138, 119, 149, 127, 161, 141, 135, 182, 161),
        (35, 171, 147, 185, 158, 200, 176, 169, 226, 201),
        (50, 209, 179, 225, 192, 242, 216, 207, 275, 246),
        (70, 269, 229, 289, 246, 310, 279, 268, 353, 318),
        (95, 328, 278, 352, 298, 377, 342, 328, 430, 389),
        (120, 382, 322, 410, 346, 437, 400, 383, 500, 454),
        (150, 441, 371, 473, 399, 504, 464, 444, 577, 527),
        (185, 506, 424, 542, 456, 575, 533, 510, 661, 605),
        (240, 599, 500, 641, 538, 679, 634, 607, 781, 719),
        (300, 693, 576, 741, 621, 783, 736, 703, 902, 833),
        (400, None, None, None, None, 940, 868, 823, 1085, 1008),
        (500, None, None, None, None, 1083, 998, 946, 1253, 1169),
        (630, None, None, None, None, 1254, 1151, 1088, 1454, 1362),
    ]
    return pd.DataFrame(
        [{
            "mm²": q,
            "C · 2 žíly": _dash(c2), "C · 3 žíly": _dash(c3),
            "E · 2 žíly": _dash(e2), "E · 3 žíly": _dash(e3),
            "F · 2 dotyk": _dash(f2), "F · 3 trefoil": _dash(f3t),
            "F · 3 mezera": _dash(f3f),
            "G · 3 vodorovně": _dash(gh), "G · 3 svisle": _dash(gv),
        } for q, c2, c3, e2, e3, f2, f3t, f3f, gh, gv in rows]
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
            ("Y", "PVC standard", "1,35–1,5", "−30…+70", "samozhášivý", "ano (Cl)", "dobrá"),
            ("Yw", "PVC tepelně odolný", "1,3–1,5", "−20…+90", "samozhášivý", "ano", "dobrá"),
            ("Yk", "PVC mrazuvzdorný", "1,3–1,4", "−40…+70", "samozhášivý", "ano", "dobrá"),
            ("2Y", "LDPE", "0,92–0,94", "−70…+70", "horlavý", "ne", "dobrá"),
            ("2Y", "HDPE", "0,94–0,96", "−50…+80", "horlavý", "ne", "dobrá"),
            ("2X", "XLPE (VPE)", "0,92", "−50…+90", "horlavý", "ne", "dobrá"),
            ("4Y", "PA (polyamid)", "1,02–1,1", "−60…+105", "horlavý", "ne", "velmi dobrá"),
            ("11Y", "PUR", "1,15–1,2", "−40…+90", "samozhášivý*", "ne", "velmi dobrá"),
            ("2G", "Silikon (SIR)", "1,2–1,3", "−60…+180", "samozhášivý", "ne", "střední"),
            ("3G", "EPR", "1,3–1,55", "−50…+90", "horlavý", "ne", "dobrá"),
            ("6G", "Chloropren (CR)", "1,4–1,6", "−40…+100", "samozhášivý", "ano", "dobrá"),
            ("H", "Bezhalogen směs", "1,4–1,6", "−40…+70", "samozhášivý", "ne", "dobrá"),
            ("HX", "Bezhalogen zesítěný", "1,4–1,6", "−40…+90", "samozhášivý", "ne", "dobrá"),
            ("10Y", "PVDF", "1,7–1,9", "−40…+135", "samozhášivý", "ano (F)", "dobrá"),
            ("7Y / 6Y", "FEP", "2,1–2,2", "−100…+205", "samozhášivý", "ano (F)", "dobrá"),
            ("5Y", "PTFE", "2,1–2,3", "−190…+260", "samozhášivý", "ano (F)", "dobrá"),
        ],
        columns=[
            "Kód", "Materiál", "Hustota [g/cm³]", "Provoz [°C]",
            "Hořlavost", "Halogeny", "Otěr",
        ],
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


def df_nominal_voltage() -> pd.DataFrame:
    return pd.DataFrame(
        [
            ("0,6/1", 1, 1.2, 0.6, 1.2, 1.4, 0.7),
            ("3,6/6", 6, 7.2, 3.6, 7.2, 8.3, 4.1),
            ("6/10", 10, 12, 6, 12, 14, 7),
            ("12/20", 20, 24, 12, 24, 28, 14),
            ("18/30", 30, 36, 18, 36, 42, 21),
        ],
        columns=[
            "U₀/U [kV]",
            "3f síť [kV]", "1f obě izol. [kV]", "1f jedna uzem. [kV]",
            "Max 3f [kV]", "Max 1f obě [kV]", "Max 1f uzem. [kV]",
        ],
    )


def df_stranding() -> pd.DataFrame:
    return pd.DataFrame(
        [
            (0.5, "7×0,30", "~16×0,2", "~28×0,15"),
            (0.75, "7×0,37", "~24×0,2", "~42×0,15"),
            (1.0, "7×0,43", "~32×0,2", "~56×0,15"),
            (1.5, "7×0,52", "~30×0,25", "~84×0,15"),
            (2.5, "7×0,67", "~50×0,25", "~140×0,15"),
            (4, "7×0,85", "~56×0,3", "~224×0,15"),
            (6, "7×1,05", "~84×0,3", "~192×0,2"),
            (10, "7×1,35", "~80×0,4", "~320×0,2"),
            (16, "7×1,70", "~128×0,4", "~512×0,2"),
            (25, "7×2,13", "~200×0,4", "~800×0,2"),
            (35, "7×2,52", "~280×0,4", "~1120×0,2"),
            (50, "19×1,83", "~400×0,4", "~705×0,3"),
            (70, "19×2,17", "~356×0,5", "~990×0,3"),
            (95, "19×2,52", "~485×0,5", "~1340×0,3"),
            (120, "37×2,03", "~614×0,5", "~1690×0,3"),
            (150, "37×2,27", "~765×0,5", "~2123×0,3"),
        ],
        columns=["mm²", "Třída 2 (n×ø)", "Třída 5 (n×ø)", "Třída 6 (n×ø)"],
    )


def df_current_ab_70() -> pd.DataFrame:
    """A1/A2/B1/B2 @ 70 °C jádro (X 22) — H07V, NYM, NYY…"""
    rows = [
        (1.5, 15.5, 13.5, 15.5, 13.0, 17.5, 15.5, 16.5, 15.0),
        (2.5, 19.5, 18.0, 18.5, 17.5, 24, 21, 23, 20),
        (4, 26, 24, 25, 23, 32, 28, 30, 27),
        (6, 34, 31, 32, 29, 41, 36, 38, 34),
        (10, 46, 42, 43, 39, 57, 50, 52, 47),
        (16, 61, 56, 57, 52, 76, 68, 69, 62),
        (25, 80, 73, 75, 68, 101, 89, 90, 80),
        (35, 99, 89, 92, 83, 125, 110, 111, 99),
        (50, 119, 108, 110, 99, 151, 134, 133, 118),
        (70, 151, 136, 139, 125, 192, 171, 168, 149),
        (95, 182, 164, 167, 150, 232, 207, 201, 179),
        (120, 210, 188, 192, 172, 269, 239, 232, 206),
        (150, 240, 216, 219, 196, None, None, None, None),
        (185, 273, 245, 248, 223, None, None, None, None),
        (240, 320, 286, 291, 261, None, None, None, None),
        (300, 367, 328, 334, 298, None, None, None, None),
    ]
    return pd.DataFrame(
        [{
            "mm²": q,
            "A1 · 2": _dash(a12), "A1 · 3": _dash(a13),
            "A2 · 2": _dash(a22), "A2 · 3": _dash(a23),
            "B1 · 2": _dash(b12), "B1 · 3": _dash(b13),
            "B2 · 2": _dash(b22), "B2 · 3": _dash(b23),
        } for q, a12, a13, a22, a23, b12, b13, b22, b23 in rows]
    )


def df_current_cefg_70() -> pd.DataFrame:
    """C/E/F/G @ 70 °C jádro (X 23)."""
    rows = [
        (1.5, 19.5, 17.5, 22, 18.5, None, None, None, None, None),
        (2.5, 27, 24, 30, 25, None, None, None, None, None),
        (4, 36, 32, 40, 34, None, None, None, None, None),
        (6, 46, 41, 51, 43, None, None, None, None, None),
        (10, 63, 57, 70, 60, None, None, None, None, None),
        (16, 85, 76, 94, 80, None, None, None, None, None),
        (25, 112, 96, 119, 101, 131, 114, 110, 146, 130),
        (35, 138, 119, 148, 126, 162, 143, 137, 181, 162),
        (50, 168, 144, 180, 153, 196, 174, 167, 219, 197),
        (70, 213, 184, 232, 196, 251, 225, 216, 281, 254),
        (95, 258, 223, 282, 238, 304, 275, 264, 341, 311),
        (120, 299, 259, 328, 276, 352, 321, 308, 396, 362),
        (150, 344, 299, 379, 319, 406, 372, 356, 456, 419),
        (185, 392, 341, 434, 364, 463, 427, 409, 521, 480),
        (240, 461, 403, 514, 430, 546, 507, 485, 615, 569),
        (300, 530, 464, 593, 497, 629, 587, 561, 709, 659),
        (400, None, None, None, None, 754, 689, 656, 852, 795),
        (500, None, None, None, None, 868, 789, 749, 982, 920),
        (630, None, None, None, None, 1005, 905, 855, 1138, 1070),
    ]
    return pd.DataFrame(
        [{
            "mm²": q,
            "C · 2": _dash(c2), "C · 3": _dash(c3),
            "E · 2": _dash(e2), "E · 3": _dash(e3),
            "F · 2": _dash(f2), "F · 3 trefoil": _dash(f3t),
            "F · 3 flat": _dash(f3f),
            "G · vodorovně": _dash(gh), "G · svisle": _dash(gv),
        } for q, c2, c3, e2, e3, f2, f3t, f3f, gh, gv in rows]
    )


def df_current_ab_90() -> pd.DataFrame:
    """A1/A2/B1/B2 @ 90 °C jádro (X 24) — N2XY, H07V2…"""
    rows = [
        (1.5, 19.0, 17.0, 18.5, 16.5, 23, 20, 22, 19.5),
        (2.5, 26, 23, 25, 22, 31, 28, 30, 26),
        (4, 35, 31, 33, 30, 42, 37, 40, 35),
        (6, 45, 40, 42, 38, 54, 48, 51, 44),
        (10, 61, 54, 57, 51, 75, 66, 69, 60),
        (16, 81, 73, 76, 68, 100, 88, 91, 80),
        (25, 106, 95, 99, 89, 133, 117, 119, 105),
        (35, 131, 117, 121, 109, 164, 144, 146, 128),
        (50, 158, 141, 145, 130, 198, 175, 175, 154),
        (70, 200, 179, 183, 164, 253, 222, 221, 194),
        (95, 241, 216, 220, 197, 306, 269, 265, 233),
        (120, 278, 249, 253, 227, 354, 312, 305, 268),
        (150, 318, 285, 290, 259, None, None, None, None),
        (185, 362, 324, 329, 295, None, None, None, None),
        (240, 424, 380, 386, 346, None, None, None, None),
        (300, 486, 435, 442, 396, None, None, None, None),
    ]
    return pd.DataFrame(
        [{
            "mm²": q,
            "A1 · 2": _dash(a12), "A1 · 3": _dash(a13),
            "A2 · 2": _dash(a22), "A2 · 3": _dash(a23),
            "B1 · 2": _dash(b12), "B1 · 3": _dash(b13),
            "B2 · 2": _dash(b22), "B2 · 3": _dash(b23),
        } for q, a12, a13, a22, a23, b12, b13, b22, b23 in rows]
    )


def df_current_rubber() -> pd.DataFrame:
    """NSGAÖU / NSSHÖU / NT… (X 27), 90/80 °C jádro, 30 °C okolí."""
    rows = [
        (1.5, 30, 32, None, None),
        (2.5, 41, 43, 30, None),
        (4, 55, 56, 41, None),
        (6, 70, 71, 53, None),
        (10, 98, 99, 74, None),
        (16, 132, 133, 99, 105),
        (25, 176, 174, 131, 139),
        (35, 218, 215, 162, 172),
        (50, 276, 270, 202, 215),
        (70, 347, 338, 250, 265),
        (95, 416, 403, 301, 319),
        (120, 488, 473, 352, 371),
        (150, 566, 546, 404, 428),
        (185, 644, 622, 461, 488),
        (240, 775, None, 540, None),
        (300, 898, None, None, None),
    ]
    return pd.DataFrame(
        [{
            "mm²": q,
            "1 žíla volně ≤1,8/3 kV [A]": _dash(a),
            "1 žíla volně 3,6/6 kV [A]": _dash(b),
            "3 žíly na povrchu ≤6/10 kV [A]": _dash(c),
            "3 žíly na povrchu >6/10 kV [A]": _dash(d),
        } for q, a, b, c, d in rows]
    )


def df_rubber_bundle() -> pd.DataFrame:
    return pd.DataFrame(
        [
            ("Na povrchu, s dotykem", 0.76, 0.67),
            ("Volně ve vzduchu / na lávkách", 0.80, 0.70),
            ("V trubkách / kanálech", 0.61, 0.54),
        ],
        columns=["Uložení", "1f AC / DC", "3f"],
    )


def df_current_silicone() -> pd.DataFrame:
    rows = [
        (0.25, 2.8, None, None, None, 5, None),
        (0.5, 6, None, 7, None, 10, None),
        (0.75, 9, 6, 12, 6, 15, 10),
        (1.0, 12, 10, 15, 10, 19, 20),
        (1.5, 16, 16, 18, 16, 24, 25),
        (2.5, 21, 20, 26, 25, 32, 35),
        (4, 28, 25, 34, 35, 42, 50),
        (6, 36, 35, 44, 50, 54, 63),
        (10, 49, 50, 61, 63, 73, 80),
        (16, 65, 63, 82, 80, 98, 100),
        (25, 85, 80, 108, 100, 129, 125),
        (35, 105, 100, 135, None, 158, 160),
        (50, 140, 125, 168, None, 198, 200),
        (70, 175, 160, 207, None, 245, 250),
        (95, 210, 200, 250, None, 292, 300),
        (120, 250, 250, 292, None, 344, 335),
        (150, None, None, 335, None, 391, None),
        (185, None, None, 382, None, 448, None),
        (240, None, None, 453, None, 528, None),
        (300, None, None, 523, None, 608, None),
    ]
    return pd.DataFrame(
        [{
            "mm²": q,
            "Sk.1 [A]": _dash(a1), "Sk.1 pojistka": _dash(f1),
            "Sk.2 [A]": _dash(a2), "Sk.2 pojistka": _dash(f2),
            "Sk.3 [A]": _dash(a3), "Sk.3 pojistka": _dash(f3),
        } for q, a1, f1, a2, f2, a3, f3 in rows]
    )


def df_silicone_temp() -> pd.DataFrame:
    return pd.DataFrame(
        [
            ("do 150", "100 %"),
            ("150–155", "91 %"),
            ("155–160", "82 %"),
            ("160–165", "71 %"),
            ("165–170", "58 %"),
            ("170–175", "41 %"),
        ],
        columns=["Teplota okolí [°C]", "Zatížitelnost"],
    )


def _nyy_df(rows: list, cols: list[str]) -> pd.DataFrame:
    out = []
    for row in rows:
        d = {"mm²": row[0]}
        for c, v in zip(cols, row[1:]):
            d[c] = _dash(v)
        out.append(d)
    return pd.DataFrame(out)


_NYY_COLS = [
    "NYY Δ", "NYY 4ž", "NYY 1ž", "NYCWY Δ", "NYCWY 4ž",
    "NAYY Δ", "NAYY 4ž", "NAYY 1ž", "NAYCWY Δ", "NAYCWY 4ž",
]


def df_nyy_ground() -> pd.DataFrame:
    """NYY/NAYY země 20 °C, EVU 0,7 (X 31)."""
    return _nyy_df([
        (1.5, 30, 27, 41, 31, 27, None, None, None, None, None),
        (2.5, 39, 36, 55, 40, 36, None, None, None, None, None),
        (4, 50, 47, 71, 51, 47, None, None, None, None, None),
        (6, 62, 59, 90, 63, 59, None, None, None, None, None),
        (10, 83, 79, 124, 84, 79, None, None, None, None, None),
        (16, 107, 102, 160, 108, 102, None, None, None, None, None),
        (25, 138, 133, 208, 139, 133, 106, 102, 160, 108, 103),
        (35, 164, 159, 250, 166, 160, 127, 123, 193, 129, 123),
        (50, 195, 188, 296, 196, 190, 151, 144, 230, 153, 145),
        (70, 238, 232, 365, 238, 234, 185, 179, 283, 187, 180),
        (95, 286, 280, 438, 281, 280, 222, 215, 340, 223, 216),
        (120, 325, 318, 501, 315, 319, 253, 245, 389, 252, 246),
        (150, 365, 359, 563, 347, 357, 284, 275, 436, 280, 276),
        (185, 413, 406, 639, 385, 402, 322, 313, 496, 314, 313),
        (240, 479, 473, 746, 432, 463, 375, 364, 578, 358, 362),
        (300, 541, 535, 848, 473, 518, 425, 419, 656, 397, 415),
        (400, 614, 613, 975, 521, 579, 487, 484, 756, 441, 474),
        (500, 693, 687, 1125, 574, 624, 558, 553, 873, 489, 528),
        (630, 777, None, 1304, 636, None, 635, None, 1011, 539, None),
        (800, 859, None, 1507, None, None, 716, None, 1166, None, None),
        (1000, 936, None, 1715, None, None, 796, None, 1332, None, None),
    ], _NYY_COLS)


def df_nyy_air() -> pd.DataFrame:
    """NYY/NAYY vzduch 30 °C (X 31)."""
    return _nyy_df([
        (1.5, 21, 19.5, 27, 22, 19.5, None, None, None, None, None),
        (2.5, 28, 25, 35, 29, 26, None, None, None, None, None),
        (4, 37, 34, 47, 39, 34, None, None, None, None, None),
        (6, 47, 43, 59, 49, 44, None, None, None, None, None),
        (10, 64, 59, 81, 67, 60, None, None, None, None, None),
        (16, 84, 79, 107, 89, 80, None, None, None, None, None),
        (25, 114, 106, 144, 119, 108, 87, 82, 110, 91, 83),
        (35, 139, 129, 176, 146, 132, 107, 100, 135, 112, 101),
        (50, 169, 157, 214, 177, 160, 131, 119, 166, 137, 121),
        (70, 213, 199, 270, 221, 202, 166, 152, 210, 173, 155),
        (95, 264, 246, 334, 270, 249, 205, 186, 259, 212, 189),
        (120, 307, 285, 389, 310, 289, 239, 216, 302, 247, 220),
        (150, 352, 326, 446, 350, 329, 273, 246, 345, 280, 249),
        (185, 406, 374, 516, 399, 377, 317, 285, 401, 321, 287),
        (240, 483, 445, 618, 462, 443, 378, 338, 479, 374, 339),
        (300, 557, 511, 717, 519, 504, 437, 400, 555, 426, 401),
        (400, 646, 597, 843, 583, 577, 513, 472, 653, 488, 468),
        (500, 747, 669, 994, 657, 626, 600, 539, 772, 556, 524),
        (630, 858, None, 1180, 744, None, 701, None, 915, 628, None),
        (800, 971, None, 1396, None, None, 809, None, 1080, None, None),
        (1000, 1078, None, 1620, None, None, 916, None, 1258, None, None),
    ], _NYY_COLS)


def df_nyky() -> pd.DataFrame:
    return pd.DataFrame(
        [
            (1.5, 28, 18.5), (2.5, 37, 27), (4, 48, 36), (6, 60, 45),
            (10, 80, 62), (16, 103, 81), (25, 134, 110), (35, 162, 134),
            (50, 192, 163), (70, 235, 205), (95, 283, 253), (120, 323, 294),
            (150, 363, 334), (185, 412, 386), (240, 478, 457), (300, 542, 529),
            (400, 615, 610),
        ],
        columns=["mm²", "Země [A]", "Vzduch [A]"],
    )


def df_multicore_factor() -> pd.DataFrame:
    return pd.DataFrame(
        [
            (5, 0.70, 0.75), (7, 0.60, 0.65), (10, 0.50, 0.55),
            (14, 0.45, 0.50), (19, 0.40, 0.45), (24, 0.35, 0.40),
            (40, 0.30, 0.35), (61, 0.25, 0.30),
        ],
        columns=["Počet zatížených žil", "Země", "Vzduch"],
    )


def df_group_layout() -> pd.DataFrame:
    """Sdružování na stěně / podlaze / stropě (X 34)."""
    n = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 12, 14, 16, 18, 20]
    rows = [
        ("Pod stropem, s dotykem",
         [0.95, 0.81, 0.72, 0.68, 0.66, 0.64, 0.63, 0.62, 0.61, 0.61, 0.61, 0.61, 0.61, 0.61, 0.61]),
        ("Pod stropem, mezera = D",
         [0.95, 0.85, 0.85, 0.85, 0.85, 0.85, 0.85, 0.85, 0.85, 0.85, 0.85, 0.85, 0.85, 0.85, 0.85]),
        ("Stěna/podlaha, mezera = D",
         [1.00, 0.94, 0.90, 0.90, 0.90, 0.90, 0.90, 0.90, 0.90, 0.90, 0.90, 0.90, 0.90, 0.90, 0.90]),
        ("Stěna/podlaha, s dotykem",
         [1.00, 0.85, 0.79, 0.75, 0.73, 0.72, 0.72, 0.71, 0.70, 0.70, 0.70, 0.70, 0.70, 0.70, 0.70]),
        ("Svazek na stěně / v trubce",
         [1.00, 0.80, 0.70, 0.65, 0.60, 0.57, 0.54, 0.52, 0.50, 0.48, 0.45, 0.43, 0.41, 0.39, 0.38]),
    ]
    out = []
    for name, vals in rows:
        d = {"Způsob": name}
        for k, v in zip(n, vals):
            d[str(k)] = v
        out.append(d)
    return pd.DataFrame(out)


def df_temp_ambient() -> pd.DataFrame:
    """Koeficienty okolní teploty vs max. teplota jádra (X 35), základ 30 °C."""
    amb = [10, 15, 20, 25, 30, 35, 40, 45, 50, 55, 60, 65, 70, 75, 80, 85]
    cols = {
        60: [1.29, 1.22, 1.15, 1.08, 1.00, 0.91, 0.82, 0.71, 0.58, 0.41, None, None, None, None, None, None],
        70: [1.22, 1.17, 1.12, 1.06, 1.00, 0.94, 0.87, 0.79, 0.71, 0.61, 0.50, 0.35, None, None, None, None],
        80: [1.18, 1.14, 1.10, 1.05, 1.00, 0.95, 0.89, 0.84, 0.77, 0.71, 0.63, 0.55, 0.45, 0.32, None, None],
        90: [1.15, 1.12, 1.08, 1.04, 1.00, 0.96, 0.91, 0.87, 0.82, 0.76, 0.71, 0.65, 0.58, 0.50, 0.41, 0.29],
    }
    rows = []
    for i, t in enumerate(amb):
        rows.append({
            "Okolí [°C]": t,
            "Jádro 60 °C": _dash(cols[60][i]),
            "Jádro 70 °C": _dash(cols[70][i]),
            "Jádro 80 °C": _dash(cols[80][i]),
            "Jádro 90 °C": _dash(cols[90][i]),
        })
    return pd.DataFrame(rows)


def df_wound_layers() -> pd.DataFrame:
    return pd.DataFrame(
        [(1, 0.80), (2, 0.61), (3, 0.49), (4, 0.42), (5, 0.38)],
        columns=["Vrstev na bubnu", "Koeficient"],
    )


def df_xlpe_r20() -> pd.DataFrame:
    return pd.DataFrame(
        [
            (25, 0.727, 1.20), (35, 0.524, 0.868), (50, 0.387, 0.641),
            (70, 0.268, 0.443), (95, 0.193, 0.320), (120, 0.153, 0.253),
            (150, 0.124, 0.206), (185, 0.0991, 0.164), (240, 0.0754, 0.125),
            (300, 0.0601, 0.100), (400, 0.0470, 0.0778), (500, 0.0366, 0.0605),
        ],
        columns=["mm²", "Cu [Ω/km]", "Al [Ω/km]"],
    )


def df_xlpe_r_temp() -> pd.DataFrame:
    return pd.DataFrame(
        [
            ("Cu", 1.157, 1.177, 1.196, 1.236, 1.275),
            ("Al", 1.161, 1.181, 1.202, 1.242, 1.282),
        ],
        columns=["Jádro", "60 °C", "65 °C", "70 °C", "80 °C", "90 °C"],
    )


def df_xlpe_rac_cu() -> pd.DataFrame:
    rows = [
        (35, 0.671, 0.673, 0.671, 0.672, None, None),
        (50, 0.497, 0.498, 0.496, 0.498, 0.496, 0.497),
        (70, 0.345, 0.346, 0.345, 0.346, 0.344, 0.346),
        (95, 0.249, 0.251, 0.249, 0.250, 0.249, 0.250),
        (120, 0.198, 0.200, 0.198, 0.200, 0.198, 0.199),
        (150, 0.163, 0.165, 0.163, 0.165, 0.162, 0.164),
        (185, 0.132, 0.134, 0.131, 0.133, 0.131, 0.133),
        (240, 0.102, 0.104, 0.101, 0.103, 0.101, 0.103),
        (300, 0.082, 0.085, 0.082, 0.084, 0.082, 0.084),
        (400, 0.068, 0.071, 0.067, 0.070, 0.067, 0.069),
        (500, 0.055, 0.058, 0.055, 0.058, 0.054, 0.057),
    ]
    cols = ["mm²", "6/10 Δ", "6/10 —", "12/20 Δ", "12/20 —", "18/30 Δ", "18/30 —"]
    return pd.DataFrame(
        [{c: _dash(v) for c, v in zip(cols, r)} for r in rows]
    )


def df_xlpe_xl() -> pd.DataFrame:
    rows = [
        (35, 0.144, 0.158, 0.153, 0.168, None, None),
        (50, 0.136, 0.150, 0.145, 0.159, 0.154, 0.169),
        (70, 0.129, 0.143, 0.138, 0.152, 0.147, 0.161),
        (95, 0.123, 0.137, 0.131, 0.145, 0.139, 0.154),
        (120, 0.118, 0.132, 0.126, 0.140, 0.134, 0.148),
        (150, 0.114, 0.128, 0.121, 0.135, 0.129, 0.143),
        (185, 0.110, 0.124, 0.117, 0.131, 0.125, 0.139),
        (240, 0.105, 0.120, 0.112, 0.126, 0.120, 0.134),
        (300, 0.102, 0.116, 0.108, 0.122, 0.115, 0.130),
        (400, 0.097, 0.111, 0.103, 0.117, 0.110, 0.124),
        (500, 0.094, 0.108, 0.100, 0.114, 0.106, 0.120),
    ]
    cols = ["mm²", "6/10 Δ", "6/10 —", "12/20 Δ", "12/20 —", "18/30 Δ", "18/30 —"]
    return pd.DataFrame(
        [{c: _dash(v) for c, v in zip(cols, r)} for r in rows]
    )


def df_xlpe_earth_sc() -> pd.DataFrame:
    rows = [
        (35, 1.2, 1.7, None), (50, 1.4, 1.9, 2.3), (70, 1.5, 2.1, 2.5),
        (95, 1.7, 2.4, 2.7), (120, 1.9, 2.6, 2.9), (150, 2.0, 2.7, 3.1),
        (185, 2.2, 3.0, 3.3), (240, 2.4, 3.3, 3.7), (300, 2.6, 3.5, 4.0),
        (400, 3.0, 4.0, 4.4), (500, 3.3, 4.3, 4.8),
    ]
    return pd.DataFrame(
        [{
            "mm²": q,
            "6/10 kV [A/km]": _dash(a),
            "12/20 kV [A/km]": _dash(b),
            "18/30 kV [A/km]": _dash(c),
        } for q, a, b, c in rows]
    )


def df_xlpe_shield_sc() -> pd.DataFrame:
    rows = [
        (0.1, 9.7, 15.1, 21.2), (0.2, 6.9, 10.7, 15.1), (0.3, 5.7, 8.9, 12.5),
        (0.4, 5.0, 7.7, 10.9), (0.5, 4.5, 7.0, 9.8), (0.6, 4.2, 6.4, 9.0),
        (0.7, 3.9, 6.0, 8.4), (0.8, 3.5, 5.6, 7.9), (0.9, 3.4, 5.3, 7.5),
        (1.0, 3.3, 5.1, 7.2), (1.5, 2.7, 4.2, 5.9), (2.0, 2.3, 3.6, 5.1),
        (3.0, 1.9, 2.9, 4.2), (4.0, 1.7, 2.6, 3.6), (5.0, 1.5, 2.3, 3.2),
    ]
    return pd.DataFrame(
        rows,
        columns=["Doba [s]", "Stínění 16 mm² [kA]", "25 mm² [kA]", "35 mm² [kA]"],
    )


def df_xlpe_shield_assign() -> pd.DataFrame:
    return pd.DataFrame(
        [
            ("35–120", 16),
            ("150–300", 25),
            ("400–500", 35),
        ],
        columns=["Průřez jádra [mm²]", "Stínění [mm²]"],
    )


def df_code_abbrev() -> pd.DataFrame:
    return pd.DataFrame(
        [
            ("N / (N)", "norma VDE / v souladu s VDE"),
            ("-J / -O", "se zeleno-žlutou / bez PE žíly"),
            ("-JZ / -OZ", "s PE + číslované žíly / bez PE + číslované"),
            ("re / rm", "kulaté plné / kulaté laněné"),
            ("Y / 2Y / 2X", "PVC / PE / XLPE"),
            ("C / CW / CE", "koncentrický Cu / vlnový / na žíle"),
            ("(St)", "statické stínění"),
            ("Li", "laněné jádro"),
            ("Ö", "odolný olejům"),
            ("FR", "zpomalovač hoření"),
            ("H / HX", "bezhalogen / bezhalogen zesítěný"),
            ("2G / 3G / 5G", "silikon / EPR / chloropren"),
            ("11Y", "PUR"),
            ("5Y / 6Y / 7Y", "PTFE / FEP / ETFE"),
            ("A-", "venkovní kabel"),
            ("G-", "důlní kabel"),
            ("BLK", "holé Cu jádro bez izolace"),
            ("NC", "nekorozivní kouřové plyny"),
            ("e / f / ff", "jednodrátový / jemně / velmi jemně laněný"),
            ("Lg", "stočení v polohách"),
        ],
        columns=["Kód", "Význam"],
    )


def df_fire_load_all() -> pd.DataFrame:
    rows: list[tuple[str, str, float]] = [
        ("N2XH", "1×2,5 re", 0.14), ("N2XH", "1×300 rm", 1.32),
        ("N2XH", "3×1,5 re", 0.48), ("N2XH", "3×50 rm", 2.31),
        ("N2XH", "4×1,5 re", 0.54), ("N2XH", "4×150 rm", 6.81),
        ("N2XH", "5×1,5 re", 0.62),
        ("N2XCH", "3×1,5/1,5", 0.48), ("N2XCH", "4×50/25", 2.77),
        ("(N)HXH-E30", "3×1,5 re", 0.72), ("(N)HXH-E30", "3×240 rm", 8.84),
        ("(N)HXH-E30", "5×1,5 re", 0.99), ("(N)HXH-E30", "5×2,5 re", 1.09),
        ("(N)HXH-E30", "5×16 rm", 2.05), ("(N)HXH-E30", "7×1,5 re", 1.16),
        ("(N)HXH-E30", "12×1,5 re", 1.84), ("(N)HXH-E30", "19×1,5 re", 2.52),
        ("(N)HXH-E30", "24×1,5 re", 3.30), ("(N)HXH-E30", "4×240 rm", 11.76),
        ("(N)HXCH-E30", "3×1,5/1,5 re", 0.63), ("(N)HXCH-E30", "3×50/25 rm", 3.04),
        ("(N)HXCH-E30", "3×240/120 rm", 10.57), ("(N)HXCH-E30", "4×1,5/1,5 re", 0.78),
        ("(N)HXCH-E30", "4×240/120 rm", 12.32),
        ("(N)HXH-E90", "3×1,5 re", 0.55), ("(N)HXH-E90", "3×50 rm", 2.30),
        ("(N)HXH-E90", "3×240 rm", 8.44), ("(N)HXH-E90", "4×1,5 re", 0.67),
        ("(N)HXH-E90", "4×50 rm", 2.88), ("(N)HXH-E90", "5×1,5 re", 0.79),
        ("(N)HXCH-E90", "3×1,5/1,5", 0.86), ("(N)HXCH-E90", "3×240/120", 10.04),
        ("(N)HXCH-E90", "4×1,5/1,5", 0.99), ("(N)HXCH-E90", "4×240/120", 13.00),
        ("NHXHX černý", "1×2,5", 0.22), ("NHXHX černý", "3×1,5", 0.78),
        ("NHXHX černý", "3×50", 3.19), ("NHXHX černý", "4×1,5", 0.89),
        ("NHXHX černý", "4×50", 3.92), ("NHXHX černý", "5×1,5", 1.03),
        ("NHXHX černý", "12×1,5", 1.69), ("NHXHX černý", "19×1,5", 2.36),
        ("NHXCHX černý", "3×1,5/1,5", 0.78), ("NHXCHX černý", "3×50/25", 3.33),
        ("NHXCHX černý", "4×1,5/1,5", 0.89), ("NHXCHX černý", "4×50/25", 4.00),
        ("(N)HMH-O/J", "3×1,5", 0.33), ("(N)HMH-O/J", "5×1,5", 0.45),
        ("(N)HMH-O/J", "5×2,5", 0.52), ("NHXMH", "5×1,5 re", 0.54),
        ("NYSEY 6/10 kV", "3×35/16", 10.56), ("NYSEY 6/10 kV", "3×120/16", 16.12),
        ("NA2XSEY 6/10 kV", "3×35/16", 10.28), ("NA2XSEY 6/10 kV", "3×120/16", 16.68),
    ]
    return pd.DataFrame(rows, columns=["Typ", "Složení", "Požární zatížení [kWh/m]"])


def df_cos_sin() -> pd.DataFrame:
    return pd.DataFrame(
        [
            (1.0, 0.00), (0.9, 0.44), (0.8, 0.60),
            (0.7, 0.71), (0.6, 0.80), (0.5, 0.87),
        ],
        columns=["cos φ", "sin φ ≈"],
    )


# ── Vyhledávací index (sekce se nemění, hledání na ně skočí) ──────────────────

_SECTION_KEYS = [
    ("scans", "📷 Všechny skeny"),
    ("ktg", "🛢️ Bubny KTG — rozměry"),
    ("ktgcap", "📦 Bubny KTG — kapacita"),
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
}


def _scan_catalog_index() -> list[dict]:
    """Index skenů: ověřená pata stránky z _SCAN_META, jinak odhad 5+pořadí."""
    out = []
    for i, p in enumerate(list_catalog_scans()):
        if p.name in _SCAN_META:
            xpage, title, extra = _SCAN_META[p.name]
        else:
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
    {"key": "current", "title": "NYY / NAYY / NYCWY — proud země a vzduch",
     "kw": "nyy nayy nycwy naycwy 0,6/1 kv evu 0,7 trefoil"},
    {"key": "current", "title": "A1 B1 B2 C E F G 70 °C a 90 °C",
     "kw": "a1 a2 b1 b2 nym h07v n2xy pokládka trubka stěna"},
    {"key": "current", "title": "Silikon 150 °C a guma NSGAÖU",
     "kw": "silikon 150 nsgaöu nsshöu nshxafö řetěz"},
    {"key": "current", "title": "Přepočty — sdružování, teplota okolí, navíjení",
     "kw": "koeficient sdružování strop mezera d vrstvy buben 70 90"},
    {"key": "current", "title": "Pokládka do země / vzduchu — hloubka, půda, vzdálenosti",
     "kw": "země 0,7 m tepelný odpor vlhká suchá 2 cm 2d evu 0,7"},
    {"key": "resist", "title": "Odpor jádra Ω/km, průměry, AWG, lanění n×ø",
     "kw": "odpor ohm awg kcmil třída 1 2 5 6 průměr jádra iec 60228 7x0,5"},
    {"key": "formulas", "title": "Vzorce — odpor, úbytek napětí, průřez, U0/U",
     "kw": "úbytek napětí kappa měď 58 hliník 33 smyčka cos phi průřez 0,6/1 kv"},
    {"key": "codes", "title": "Rozkladač kódu H07RN-F, H05VV-F, NYY, NA2XS2Y",
     "kw": "h07rn-f h05vv-f h07v-k nyy n2xy na2xs2y j o re rm stínění pancíř rozložit kód izolace plášť"},
    {"key": "codes", "title": "Zkratky Y 2X 11Y re rm -J -O Li (St)",
     "kw": "pvc xlpe pur re rm j o li stínění bezhalogen"},
    {"key": "din", "title": "Normy DIN VDE 0100 … 0816",
     "kw": "din vde 0100 0101 0250 0276 0298 koupelna výbuch blesk nemocnice"},
    {"key": "fire", "title": "Požární zatížení N2XH / E30 / E90 / NHXHX",
     "kw": "požár kwh/m n2xh nhxmh e30 e90 nhxhx halogen"},
    {"key": "fire", "title": "XLPE 6–30 kV — R20 Rδ Rac XL kapacita zkrat stínění",
     "kw": "xlpe 6/10 12/20 18/30 kv kapacita indukčnost trefoil zkrat kA r20"},
    {"key": "fire", "title": "Materiály PVC, XLPE, PUR, silikon, bezhalogen, PTFE",
     "kw": "pvc xlpe pe pur chloropren silikon fep ptfe halogen teplota otěr"},
    {"key": "ktg", "title": "Rozměry dřevěných / plastových / nevratných bubnů",
     "kw": "buben ktg čelo jádro fd kd l2 nosnost he 350 x109"},
    {"key": "ktgcap", "title": "Kapacita bubnu — kolik metrů se vejde (X 110)",
     "kw": "kapacita návin délka metr kd/d 15xd 20xd 40xd x110"},
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


_H_SHAPE = {
    "H8": "spirálový kabel",
    "H7": "dvouvrstvá izolace",
    "H6": "plochý (HD 359 / EN 50214)",
    "H3": "můstkový",
    "H2": "plochý nedělitelný",
    "H": "plochý dělitelný",
}

_VDE_INSUL = [
    ("NHX", "izolace bezhalogenová (NHX…)"),
    ("HX", "izolace bezhalogenová zesítěná"),
    ("2X", "izolace XLPE (VPE)"),
    ("2Y", "izolace PE"),
    ("11Y", "izolace PUR"),
    ("5G", "izolace chloropren"),
    ("2G", "izolace silikon"),
    ("3G", "izolace EPR"),
    ("Y", "izolace PVC"),
    ("H", "izolace bezhalogenová směs"),
    ("G", "izolace pryž"),
    ("X", "izolace XLPE / zesítěný plast"),
]

_VDE_CONC = [
    ("CW", "koncentrický Cu vodič — vlnový"),
    ("CE", "koncentrický Cu vodič — na každé žíle"),
    ("C", "koncentrický Cu vodič"),
]

_VDE_SCREEN = [
    ("SE", "stínění Cu na každé žíle"),
    ("S", "stínění Cu dráty / pásky"),
]

_VDE_ARMOR = [
    ("B", "pancíř — ocelová páska"),
    ("F", "pancíř — ploché ocelové dráty"),
    ("R", "pancíř — kulaté ocelové dráty"),
]

_VDE_SHEATH = [
    ("2Y", "plášť PE"),
    ("2X", "plášť XLPE"),
    ("HX", "plášť bezhalogenový zesítěný"),
    ("Y", "plášť PVC"),
    ("H", "plášť bezhalogenový"),
    ("K", "plášť olověný"),
    ("Q", "plášť PUR"),
]

_CONSTR = {
    "RE": "kulaté plné jádro (tř. 1)",
    "RM": "kulaté laněné jádro (tř. 2)",
    "SE": "sektorové plné jádro",
    "SM": "sektorové laněné jádro",
}


def _eat_longest(s: str, tokens: list[tuple[str, str]]) -> tuple[str, str, str] | None:
    for code, meaning in sorted(tokens, key=lambda x: -len(x[0])):
        if s.startswith(code):
            return code, meaning, s[len(code):]
    return None


def _parse_cores_tail(tail: str, *, h_code: bool = False) -> list[tuple[str, str, str]]:
    """nGq / nXq / n×q, RE/RM, /stínění, kV, E30."""
    rows: list[tuple[str, str, str]] = []
    t = tail.strip()
    if not t:
        return rows
    pe_kind: str | None = None
    m = None
    if h_code:
        m = re.search(
            r"(?P<n>\d+)\s*G\s*(?P<q>\d+(?:[.,]\d+)?)",
            t,
            re.IGNORECASE,
        )
        if m:
            pe_kind = "G"
        else:
            # HD 361: velké X = bez PE. České 3x1,5 / 3×1,5 = jen násobení.
            m = re.search(
                r"(?P<n>\d+)\s*X\s*(?P<q>\d+(?:[.,]\d+)?)",
                t,
            )
            if m:
                pe_kind = "X"
    if m is None:
        m = re.search(
            r"(?P<n>\d+)\s*[×x*]\s*(?P<q>\d+(?:[.,]\d+)?)",
            t,
        )
    if m:
        n = m.group("n")
        q = m.group("q").replace(",", ".")
        rows.append(("Počet žil", n, f"{n} žil"))
        if pe_kind == "G":
            rows.append(("Ochranná žíla", "G", "se zeleno-žlutou (PE) — započtena v počtu žil"))
        elif pe_kind == "X":
            rows.append(("Ochranná žíla", "X", "bez zeleno-žluté ochranné žíly"))
        rows.append(("Průřez", f"{q} mm²", f"jmenovitý průřez jádra {q} mm²"))
        t = t[: m.start()] + t[m.end():]
    m2 = re.search(r"\b(RE|RM|SE|SM)\b", t, re.IGNORECASE)
    if m2:
        c = m2.group(1).upper()
        rows.append(("Konstrukce jádra", c, _CONSTR.get(c, c)))
        t = t[: m2.start()] + t[m2.end():]
    # Napětí dřív než /stínění, ať RM/16 6/10 kV nesplete 16/6.
    m4 = re.search(
        r"(\d+(?:[.,]\d+)?)\s*/\s*(\d+(?:[.,]\d+)?)\s*(?:kV|KV)",
        t,
        re.IGNORECASE,
    )
    if m4 is None:
        m4 = re.search(
            r"(\d+(?:[.,]\d+)?)\s*/\s*(\d+(?:[.,]\d+)?)",
            t,
        )
        if m4:
            try:
                u0_val = float(m4.group(1).replace(",", "."))
            except ValueError:
                u0_val = 99.0
            if u0_val >= 50:
                m4 = None
    if m4:
        u0, u = m4.group(1).replace(",", "."), m4.group(2).replace(",", ".")
        rows.append(("Jmenovité napětí", f"{u0}/{u} kV", f"U₀/U = {u0}/{u} kV"))
        t = t[: m4.start()] + t[m4.end():]
    m3 = re.search(r"/\s*(\d+(?:[.,]\d+)?)", t)
    if m3:
        rows.append(
            ("Stínění / koncentrický", f"{m3.group(1)} mm²",
             "průřez stínění nebo koncentrického vodiče"),
        )
        t = t[: m3.start()] + t[m3.end():]
    up = t.upper().replace(" ", "")
    for fire, meaning in (
        ("E90", "funkční schopnost 90 min (požár)"),
        ("E30", "funkční schopnost 30 min (požár)"),
        ("FE180", "izolace odolná ohni 180 min"),
        ("FE90", "izolace odolná ohni 90 min"),
    ):
        if fire in up:
            rows.append(("Požární třída", fire, meaning))
            break
    return rows


def decode_cable_designation(raw: str) -> list[tuple[str, str, str]]:
    """Rozklad H07RN-F / NYY-J / NA2XS2Y… → (část, znak, význam)."""
    original = (raw or "").strip()
    if len(original) < 2:
        return []
    compact = original.upper().replace(" ", "")
    compact = compact.replace(",", ".")
    u = original.upper().lstrip()

    hcompact = compact.replace("×", "X").replace("*", "X")
    hm = re.match(r"^(H|A)(01|03|05|07)(.*)$", hcompact)
    if hm and (u.startswith("H") or u.startswith(("A01", "A03", "A05", "A07"))):
        rows: list[tuple[str, str, str]] = []
        pref, volt, rest = hm.groups()
        rows.append((
            "Původ",
            pref,
            "harmonizovaný typ (HD 361 / DIN VDE 0292)" if pref == "H"
            else "schválený národní typ",
        ))
        rows.append(("Jmenovité napětí", volt, _H_VOLTAGE.get(volt, volt)))
        core_m = re.search(r"-(U|R|K|F|H|D|E)(?=\d|$)", rest)
        if core_m:
            mat_block = rest[: core_m.start()]
            core = core_m.group(1)
        else:
            split = re.match(r"^([A-Z]*?)(\d.*)?$", rest)
            mat_block = (split.group(1) if split else rest) or ""
            core = ""
        shape = ""
        for sh in ("H8", "H7", "H6", "H3", "H2"):
            if mat_block.endswith(sh):
                shape = sh
                mat_block = mat_block[: -len(sh)]
                break
        roles = ["Izolace", "Plášť", "Další vrstva"]
        i, ri = 0, 0
        codes = sorted(_H_INSUL.keys(), key=len, reverse=True)
        while i < len(mat_block) and ri < 3:
            hit = next((c for c in codes if mat_block.startswith(c, i)), None)
            if not hit:
                i += 1
                continue
            rows.append((roles[ri], hit, _H_INSUL[hit]))
            i += len(hit)
            ri += 1
        if core:
            rows.append(("Jádro", f"-{core}", _H_CORE.get(core, core)))
        if shape:
            rows.append(("Provedení", shape, _H_SHAPE.get(shape, shape)))
        rows.extend(_parse_cores_tail(original, h_code=True))
        if any(r[0] in ("Izolace", "Jádro") for r in rows) or core or mat_block:
            return rows

    s = compact.replace("×", "X").replace("*", "X")
    vde_rows: list[tuple[str, str, str]] = []
    if s.startswith("(N)"):
        vde_rows.append(("Norma", "(N)", "v souladu s DIN VDE (není plně normový typ)"))
        s = s[3:]
    elif s.startswith("N"):
        vde_rows.append(("Norma", "N", "kabel podle DIN VDE"))
        s = s[1:]
    else:
        return _parse_cores_tail(original, h_code=False)

    if s.startswith("A") and (len(s) == 1 or s[1] in "Y2HGX"):
        vde_rows.append(("Jádro — materiál", "A", "hliník (Al)"))
        s = s[1:]
    else:
        vde_rows.append(("Jádro — materiál", "Cu", "měď (není-li A)"))

    eaten = _eat_longest(s, _VDE_INSUL)
    if eaten:
        code, meaning, s = eaten
        vde_rows.append(("Izolace", code, meaning))

    eaten = _eat_longest(s, _VDE_CONC)
    if eaten:
        code, meaning, s = eaten
        vde_rows.append(("Koncentrický vodič", code, meaning))

    eaten = _eat_longest(s, _VDE_SCREEN)
    if eaten:
        code, meaning, s = eaten
        vde_rows.append(("Stínění", code, meaning))

    eaten = _eat_longest(s, _VDE_ARMOR)
    if eaten:
        code, meaning, s = eaten
        vde_rows.append(("Pancíř", code, meaning))

    eaten = _eat_longest(s, _VDE_SHEATH)
    if eaten:
        code, meaning, s = eaten
        vde_rows.append(("Plášť", code, meaning))

    pe = re.match(r"^-(JZ|OZ|J|O)", s)
    if pe:
        code = pe.group(1)
        meaning = {
            "J": "se zeleno-žlutou ochrannou žílou (PE)",
            "O": "bez zeleno-žluté ochranné žíly",
            "JZ": "s PE + číslované žíly",
            "OZ": "bez PE + číslované žíly",
        }[code]
        vde_rows.append(("Ochranná žíla", f"-{code}", meaning))
        s = s[pe.end():]

    vde_rows.extend(_parse_cores_tail(original, h_code=False))
    return vde_rows


def explain_h_code(raw: str) -> list[str]:
    """Rozklad označení kabelu (H05VV-F, H07RN-F, NYY-J…)."""
    rows = decode_cable_designation(raw)
    if not rows:
        return [
            "Kód nerozeznán — zkus např. H07RN-F 3G1,5 · H07V-K · "
            "NYY-J 5×2,5 RE · NA2XS2Y 1×35 RM/16 6/10 kV."
        ]
    return [f"{part}: {code} — {meaning}" for part, code, meaning in rows]


# ── UI ────────────────────────────────────────────────────────────────────────

def render_helukabel_catalog() -> None:
    """Technické tabulky ze skenů HELUKABEL — referenční hub."""
    n_scans = len(list_catalog_scans())
    st.markdown(f"### {t('📗 Technické tabulky HELUKABEL')}")
    st.caption(t("Tabulky a skeny katalogu zůstávají v originále (DE/CZ)."))
    st.markdown(
        '<div class="info-box" style="margin-bottom:12px;">'
        f"Digitální výpisky + prohlížeč skenů "
        f"(<code>assets/helukabel/</code>, {n_scans} stránek). "
        "Nahoře hledej — otevře se příslušná <strong>sekce</strong>."
        "</div>",
        unsafe_allow_html=True,
    )

    q = st.text_input(
        t("Hledat v katalogu"),
        placeholder="např. ohyb, NYY, H07RN-F, proud, AWG, požár, VDE, buben…",
        key="helu_q",
    )
    hits = search_catalog(q)
    if q.strip() and not hits:
        st.caption(t("Nic nenalezeno — zkus kratší slovo (ohyb, proud, NYY, PE…)."))
    elif hits:
        labels = [f"{h['kind']}: {h['title']}" for h in hits]
        chosen = st.selectbox(t("Nalezené položky"), labels, key="helu_hit_sel")
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
        "I₁ = celková šířka · I₂ = šířka návinu (katalog X 109)."
    )
    _show_scan("IMG_20260813_141120.jpg", "X 109 — rozměry kabelových bubnů KTG")


def _render_ktg_capacity() -> None:
    st.markdown(
        '<div class="info-box">'
        "Katalogová matice <strong>ø kabelu × buben → délka [m]</strong> "
        "je velmi hustá (D 6–92 mm). Níže je filtr podle poměru "
        "<code>Kd / D</code> (barevná legenda HELUKABEL)."
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
        "Barva v katalogu = jádro ještě splňuje daný max. násobek D "
        "(přísnější = menší násobek). Kompletní matice metrů je ve skenu X 110."
    )
    _show_scan(
        "IMG_20260813_141129.jpg",
        "X 110 — kapacita bubnů KTG a délky kabelů [m]",
        expanded=True,
    )


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
    _show_scan("IMG_20260813_140018.jpg", "X 62 — min. poloměr ohybu VDE")


def _render_colors() -> None:
    st.markdown("##### DIN 40705 / IEC 60446 — značení vodičů")
    st.dataframe(df_core_colors_din(), use_container_width=True, hide_index=True)
    st.markdown(
        "- Světlemodrá = **jen N / střední** (nepoužívat jinde při riziku záměny).\n"
        "- Zeleno-žlutá = **jen PE / PEN**.\n"
        "- Vnitřní rozvody zařízení: preferovat černou / hnědou; při stejných barvách číslovat."
    )
    _show_scan("IMG_20260813_140005.jpg", "X 61 — značení žil DIN 40705 / IEC 60446")

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
    _show_scan("IMG_20260813_135931.jpg", "X 59 — barevné značení DIN VDE 0816")


def _render_current() -> None:
    tab = st.selectbox(
        "Tabulka proudu",
        [
            "Ohebné 30 °C (X 28) + teplota",
            "Do 1000 V / teplotně odolné (X 26)",
            "A1–B2 70 °C — NYM / H07V (X 22)",
            "C/E/F/G 70 °C — NYY (X 23)",
            "A1–B2 90 °C — N2XY (X 24)",
            "C/E/F/G 90 °C — N2XY (X 25)",
            "NYY / NAYY země i vzduch (X 31)",
            "NYKY olovo (X 33)",
            "Guma NSGAÖU / NSSHÖU (X 27)",
            "Silikon 150 °C (X 30)",
            "Sdružování a přepočty (X 19 / 34 / 35)",
        ],
        key="helu_cur_tab",
    )

    if tab.startswith("Ohebné"):
        st.caption(
            "Sk.1 = jednožilové v trubce · Sk.2 = vícežilové / kanály · "
            "Sk.3 = jednožilové volně ve vzduchu (rozestup ≥ D)."
        )
        st.dataframe(df_current_flex(), use_container_width=True, hide_index=True)
        st.markdown("##### Teplota okolí > 30 °C (PVC / guma)")
        st.dataframe(df_temp_corr_pvc_rubber(), use_container_width=True, hide_index=True)
        _show_scan("IMG_20260813_135308.jpg", "X 28 — proud ohebné kabely 30 °C")

    elif tab.startswith("Do 1000"):
        st.caption(
            "Volně ve vzduchu = 1 zatížená žíla (H07V-K, H07RN-F…). "
            "Na povrchu 2–3 žíly = šňůry / ovládací (JZ, PUR, MULTIFLEX…)."
        )
        st.dataframe(df_x26_current(), use_container_width=True, hide_index=True)
        _show_scan("IMG_20260813_135241.jpg", "X 26 — proud do 1000 V / teplotně odolné")

    elif tab.startswith("A1–B2 70"):
        st.caption("H07V-U/-R/-K, NYM, NYY, NHXMH… jádro 70 °C, okolí 30 °C.")
        st.dataframe(df_current_ab_70(), use_container_width=True, hide_index=True)
        _show_scan("IMG_20260813_135133.jpg", "X 22 — proud A1/A2/B1/B2 70 °C")

    elif tab.startswith("C/E/F/G 70"):
        st.caption("NYM, NYY… jádro 70 °C. F/G od 25 mm² (jednožilové).")
        st.dataframe(df_current_cefg_70(), use_container_width=True, hide_index=True)
        _show_scan("IMG_20260813_135148.jpg", "X 23 — proud C/E/F/G 70 °C")

    elif tab.startswith("A1–B2 90"):
        st.caption("H07V2, N2XY, N2XH… jádro 90 °C, okolí 30 °C.")
        st.dataframe(df_current_ab_90(), use_container_width=True, hide_index=True)
        _show_scan("IMG_20260813_135158.jpg", "X 24 — proud A1/A2/B1/B2 90 °C")

    elif tab.startswith("C/E/F/G 90"):
        st.caption("N2XY, N2XH, NHXH FE180… jádro 90 °C. F/G od 25 mm².")
        st.dataframe(df_current_cefg_90(), use_container_width=True, hide_index=True)
        _show_scan("IMG_20260813_135231.jpg", "X 25 — proud C/E/F/G 90 °C")

    elif tab.startswith("NYY"):
        st.caption("DIN VDE 0276-603, země 20 °C EVU 0,7 · vzduch 30 °C. Δ = trefoil, 1ž = DC s odlehlým zpětným.")
        env = st.radio("Prostředí", ["Země", "Vzduch"], horizontal=True, key="helu_nyy_env")
        st.dataframe(
            df_nyy_ground() if env == "Země" else df_nyy_air(),
            use_container_width=True, hide_index=True,
        )
        st.markdown("##### Mnohožilové (od 5 žil, 1,5–10 mm²)")
        st.dataframe(df_multicore_factor(), use_container_width=True, hide_index=True)
        _show_scan("IMG_20260813_135340.jpg", "X 31 — NYY / NAYY / NYCWY")
        _show_scan("IMG_20260813_135348.jpg", "X 32 — N2XY / NA2XY (XLPE, kompletní matice)")

    elif tab.startswith("NYKY"):
        st.caption("NYKY 0,6/1 kV — 3/4žilové. Od 5 žil násob koeficientem níže.")
        st.dataframe(df_nyky(), use_container_width=True, hide_index=True)
        st.dataframe(df_multicore_factor(), use_container_width=True, hide_index=True)
        _show_scan("IMG_20260813_135357.jpg", "X 33 — NYKY 0,6/1 kV")

    elif tab.startswith("Guma"):
        st.caption("NSGAÖU / NSHXAFÖ volně ve vzduchu 1 žíla · NSSHÖU / NT na povrchu 3 žíly.")
        st.dataframe(df_current_rubber(), use_container_width=True, hide_index=True)
        st.markdown("##### Sdružování (násobitel k hodnotám výše)")
        st.dataframe(df_rubber_bundle(), use_container_width=True, hide_index=True)
        _show_scan("IMG_20260813_135255.jpg", "X 27 — guma / řetězy od 0,6/1 kV")

    elif tab.startswith("Silikon"):
        st.caption("Orientační hodnoty do 150 °C okolí. Skupiny 1/2/3 jako u ohebných.")
        st.dataframe(df_current_silicone(), use_container_width=True, hide_index=True)
        st.markdown("##### Nad 150 °C okolí")
        st.dataframe(df_silicone_temp(), use_container_width=True, hide_index=True)
        _show_scan("IMG_20260813_135329.jpg", "X 30 — silikonová izolace")

    else:
        st.markdown("##### Provozní podmínky země / vzduch")
        st.dataframe(df_air_distances(), use_container_width=True, hide_index=True)
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("###### Měrný tepelný odpor půdy")
            st.dataframe(df_soil_thermal(), use_container_width=True, hide_index=True)
        with c2:
            st.markdown("###### Způsoby pokládky IEC / VDE")
            st.dataframe(df_install_methods(), use_container_width=True, hide_index=True)
        st.markdown("##### Sdružování na stěně / podlaze / stropě (počet obvodů)")
        st.dataframe(df_group_layout(), use_container_width=True, hide_index=True)
        st.caption("Mezera > 2×D vodorovně → bez snížení. Jednožilové: n/2 resp. n/3 obvodů.")
        st.markdown("##### Teplota okolí vs max. teplota jádra (základ 30 °C)")
        st.dataframe(df_temp_ambient(), use_container_width=True, hide_index=True)
        st.markdown("##### Navíjení na buben")
        st.dataframe(df_wound_layers(), use_container_width=True, hide_index=True)
        st.caption("Spirálový návin: koeficient 0,80.")
        st.markdown("##### Mnohožilové 5+ (1,5–10 mm²)")
        st.dataframe(df_multicore_factor(), use_container_width=True, hide_index=True)
        _show_scan("IMG_20260813_135053.jpg", "X 19 — provozní podmínky")
        _show_scan("IMG_20260813_135105.jpg", "X 20 — způsoby pokládky A1–G")
        _show_scan("IMG_20260813_135121.jpg", "X 21 — země / vzduch")
        _show_scan("IMG_20260813_135409.jpg", "X 34 — sdružování")
        _show_scan("IMG_20260813_135420.jpg", "X 35 — teplota / navíjení")


def _render_resistance_awg() -> None:
    st.markdown("##### Max. odpor jádra @ 20 °C [Ω/km] (VDE 0295 / IEC 60228)")
    st.dataframe(df_core_resistance(), use_container_width=True, hide_index=True)
    st.caption(
        "Třída 1 = plný · 2 = laněný · 5 = jemně laněný · 6 = velmi jemně laněný. "
        "Sken tabulky odporu (X 16) v této sadě chybí — hodnoty jsou ve výpisku."
    )

    st.markdown("##### Průměry jader podle VDE 0295 (DIN EN 60228)")
    st.dataframe(df_core_diameters(), use_container_width=True, hide_index=True)
    st.caption(
        "¹ min-ø jen Al · ² max-ø tř.1 s minerální izolací (Cu) · "
        "³ min-ø Cu tř.1 není stanoven."
    )
    _show_scan("IMG_20260813_135008.jpg", "X 15 — průměry jader VDE 0295")

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
    st.markdown("##### Konstrukce lanění (DIN VDE 0295 / IEC 60228) — n × ø drátu")
    st.caption("~ = orientační počet drátů (není závazný).")
    st.dataframe(df_stranding(), use_container_width=True, hide_index=True)
    _show_scan("IMG_20260813_135028.jpg", "X 17 — konstrukce lanění + AWG")


def _render_formulas() -> None:
    st.markdown("##### Vodivost materiálů")
    st.dataframe(df_conductivity(), use_container_width=True, hide_index=True)
    st.markdown("##### Jmenovité / max. provozní napětí U₀/U (X 18)")
    st.dataframe(df_nominal_voltage(), use_container_width=True, hide_index=True)
    st.caption(
        "3f: U = √3 · U₀. DC 0,6/1 kV: max. žíla–žíla 1,8 kV, žíla–zem 0,9 kV."
    )
    _show_scan("IMG_20260813_135042.jpg", "X 18 — jmenovité a provozní napětí")

    st.markdown("##### Přehled vzorců (X 107–108)")
    st.markdown(
        r"""
- Plné jádro: $q = D^2 \cdot 0{,}7854$ · $D = \sqrt{q \cdot 1{,}2732}$
- Laněné: $q = d^2 \cdot 0{,}7854 \cdot n$
- Odpor: $R = l / (\kappa \cdot q)$ · smyčka $\times 2$
- Úbytek DC: $u = 2\,l\,I / (\kappa q)$ · 1f AC $\times \cos\varphi$ · 3f $u = 1{,}732\,l\,I\cos\varphi / (\kappa q)$
- Průřez z proudu: DC/1f $q = 2\,I\,l / (\kappa u)$ · 3f $q = 1{,}732\,I\cos\varphi\,l / (\kappa u)$
- Průřez z výkonu: DC/1f $q = 2\,l P / (\kappa u U)$ · 3f $q = l P / (\kappa u U)$
- Přesný úbytek (s reaktancí): 3f $u = 1{,}732\,l I (R_w\cos\varphi + \omega L\sin\varphi)\cdot 10^{-3}$ V  
  ($\omega = 314$ při 50 Hz; $R_w$ v Ω/km, $L$ v H/km nebo $\omega L$ v Ω/km)
- $P_{3f} = 1{,}732\,U I\cos\varphi$ · $S_{3f} = 1{,}732\,U I$ · $Q = P\tan\varphi$
- Koax. kapacita: $C = \varepsilon_r \cdot 10^3 / (18\ln(D_a/d))$ nF/km
- $R_{\delta,\mathrm{Cu}} = R_{20}\cdot(234{,}5+\delta)/254{,}5$ · $R_{\delta,\mathrm{Al}} = R_{20}\cdot(228+\delta)/248$
"""
    )
    st.dataframe(df_cos_sin(), use_container_width=True, hide_index=True)
    st.caption("Doporučený úbytek NN: 3–5 % Un (výjimečně do 7 %).")

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

    _show_scan("IMG_20260813_141102.jpg", "X 107 — základní vzorce z elektrotechniky")
    _show_scan("IMG_20260813_141111.jpg", "X 108 — vzorce ze silnoproudé elektrotechniky")


def _render_codes() -> None:
    st.markdown("##### Rozkladač označení kabelu")
    st.caption(
        "Napiš H07RN-F, H07V-K, NYY-J, NA2XS2Y… — izolace, plášť, jádro, žíly a napětí se doplní samy."
    )
    examples = [
        "H07RN-F 3G1,5",
        "H05VV-F 3G1,5",
        "H07V-K 1×2,5",
        "H07V-U",
        "NYY-J 5×2,5 RE 0,6/1 kV",
        "N2XY 3×150 RM",
        "NA2XS2Y 1×35 RM/16 6/10 kV",
        "NYCWY-J 4×50 SM",
        "N2XH-J 4×16 RE",
        "(N)HXH-E30 3×1,5",
    ]
    if "helu_h_parse" not in st.session_state:
        st.session_state["helu_h_parse"] = examples[0]
    cols = st.columns(5)
    for i, ex in enumerate(examples[:5]):
        if cols[i].button(ex, key=f"helu_ex_{i}"):
            st.session_state["helu_h_parse"] = ex
            st.rerun()
    cols2 = st.columns(5)
    for i, ex in enumerate(examples[5:]):
        if cols2[i].button(ex, key=f"helu_ex_{i+5}"):
            st.session_state["helu_h_parse"] = ex
            st.rerun()

    raw = st.text_input(
        "Označení kabelu",
        key="helu_h_parse",
        placeholder="např. H07RN-F 3G2,5  nebo  NYY-J 5×2,5 RE",
    )
    decoded = decode_cable_designation(raw)
    if decoded:
        st.success(" · ".join(m for _p, _c, m in decoded))
        st.markdown(" · ".join(f"**{p}** `{c}`" for p, c, _m in decoded))
        st.dataframe(
            pd.DataFrame(decoded, columns=["Část", "Znak", "Význam"]),
            use_container_width=True,
            hide_index=True,
        )
    elif raw.strip():
        st.warning(
            "Kód nerozeznán — zkus H07RN-F 3G1,5 · H07V-K · "
            "NYY-J 5×2,5 RE · NA2XS2Y 1×35 RM/16 6/10 kV."
        )

    st.markdown("##### Harmonizované kódy (DIN VDE 0292 / HD 361)")
    st.dataframe(df_h_code_legend(), use_container_width=True, hide_index=True)
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
    st.markdown("##### Časté zkratky (X 14)")
    st.dataframe(df_code_abbrev(), use_container_width=True, hide_index=True)
    _show_scan("IMG_20260813_134753.jpg", "X 8 — harmonizované kódy H05 / H07")
    _show_scan("IMG_20260813_134918.jpg", "X 12 — kódy silových kabelů NYY / N2XY")
    _show_scan("IMG_20260813_134930.jpg", "X 13 — kódy telefonních a zapojovacích kabelů")
    _show_scan("IMG_20260813_134951.jpg", "X 14 — vysvětlení označovacích kódů")


def _render_din_vde() -> None:
    st.markdown("##### Odkazy na normy DIN VDE (X 5–X 6)")
    st.dataframe(df_din_vde_refs(), use_container_width=True, hide_index=True)
    st.caption("Kompletní znění norem je ve skenech níže.")
    _show_scan("IMG_20260813_134726.jpg", "X 5 — DIN VDE silová zařízení")
    _show_scan("IMG_20260813_134737.jpg", "X 6 — DIN VDE kabely")


def _render_fire_materials() -> None:
    sub = st.selectbox(
        "Téma",
        [
            "SN XLPE — R, C, L, zkrat",
            "Požární zatížení kWh/m",
            "Tah / ohyb při pokládce",
            "Materiály izolace a pláště",
            "Výběr kabelu — bezpečnost (X 93)",
        ],
        key="helu_fire_sub",
    )
    if sub.startswith("SN"):
        st.markdown("##### Odpor jádra @ 20 °C [Ω/km] (X 39)")
        st.dataframe(df_xlpe_r20(), use_container_width=True, hide_index=True)
        st.markdown("##### Přepočet na teplotu jádra")
        st.dataframe(df_xlpe_r_temp(), use_container_width=True, hide_index=True)
        c1, c2, c3 = st.columns(3)
        with c1:
            mat = st.selectbox("Materiál", ["Cu", "Al"], key="helu_rd_mat")
        with c2:
            r20 = st.number_input("R₂₀ [Ω/km]", 0.01, 5.0, 0.727, 0.001, key="helu_rd_r20")
        with c3:
            delta = st.number_input("Teplota jádra δ [°C]", 20.0, 120.0, 90.0, 1.0, key="helu_rd_d")
        if mat == "Cu":
            rd = r20 * (234.5 + delta) / 254.5
        else:
            rd = r20 * (228.0 + delta) / 248.0
        st.success(f"Rδ = **{rd:.4f} Ω/km**")
        st.markdown("##### Činný odpor 50 Hz Cu [Ω/km] (X 40)")
        st.dataframe(df_xlpe_rac_cu(), use_container_width=True, hide_index=True)
        st.markdown("##### Indukční odpor XL 50 Hz [Ω/km]")
        st.dataframe(df_xlpe_xl(), use_container_width=True, hide_index=True)
        st.markdown("##### Provozní kapacita [µF/km] (X 41)")
        st.dataframe(df_xlpe_mv_cap(), use_container_width=True, hide_index=True)
        st.markdown("##### Indukčnost — Δ trefoil / — vedle sebe [mH/km]")
        st.dataframe(df_xlpe_mv_ind(), use_container_width=True, hide_index=True)
        st.markdown("##### Zemní zkratový proud [A/km] (X 43)")
        st.dataframe(df_xlpe_earth_sc(), use_container_width=True, hide_index=True)
        st.markdown("##### Zkratová zatížitelnost Cu stínění (350 °C)")
        st.dataframe(df_xlpe_shield_sc(), use_container_width=True, hide_index=True)
        st.dataframe(df_xlpe_shield_assign(), use_container_width=True, hide_index=True)
        _show_scan("IMG_20260813_135504.jpg", "X 39 — XLPE odpor R20 / Rδ")
        _show_scan("IMG_20260813_135516.jpg", "X 40 — XLPE Rstř a XL")
        _show_scan("IMG_20260813_135549.jpg", "X 41 — XLPE kapacita a indukčnost")
        _show_scan("IMG_20260813_135621.jpg", "X 43 — zemní zkrat / stínění")
    elif sub.startswith("Požární"):
        types = ["Vše"] + sorted(df_fire_load_all()["Typ"].unique().tolist())
        pick = st.selectbox("Typ kabelu", types, key="helu_fire_typ")
        df = df_fire_load_all()
        if pick != "Vše":
            df = df[df["Typ"] == pick]
        st.dataframe(df, use_container_width=True, hide_index=True)
        st.caption("Výběr z X 74–75. Další rozměry ve skenech.")
        _show_scan("IMG_20260813_140259.jpg", "X 74 — požární zatížení E30 / E90")
        _show_scan("IMG_20260813_140316.jpg", "X 75 — požární zatížení bezhalogen")
    elif sub.startswith("Tah"):
        st.dataframe(df_pull_limits(), use_container_width=True, hide_index=True)
        _show_scan("IMG_20260813_140018.jpg", "X 62 — ohyb při pokládce (VDE)")
    elif sub.startswith("Materiály"):
        st.dataframe(df_materials_key(), use_container_width=True, hide_index=True)
        st.caption(
            "X 90–91. PUR a PA = velmi dobrý otěr. "
            "LOI: PVC 23–42 %, PE <18 %, FEP/PTFE >95 %. "
            "Bezhalogen (H, HX, 2Y, 2X, 11Y) bez korozivních plynů."
        )
        _show_scan("IMG_20260813_140555.jpg", "X 90–91 — vlastnosti izolace a pláště")
    else:
        st.dataframe(df_safety_select(), use_container_width=True, hide_index=True)
        _show_scan("IMG_20260813_140642.jpg", "X 93 — bezpečnost a výběr kabelu")


def _render_certs() -> None:
    st.markdown("##### Mezinárodní certifikační značky (X 106)")
    st.dataframe(df_cert_marks(), use_container_width=True, hide_index=True)
    _show_scan("IMG_20260813_141053.jpg", "X 106 — certifikační značky")
    _show_scan("IMG_20260813_141137.jpg", "X 111 — poznámky k označování CE")
