# ==============================================================================
# KABELÁŘSKÝ NÁKUPNÍ DASHBOARD — app.py
# Verze: 2.0.0
# Popis: Inteligentní nákupní dashboard pro kabelářský průmysl.
#        Sleduje ceny LME/SHFE kovů, FX kurzy, ceny ropy (BZ=F + SMA)
#        a kalkulačku transitního času Čína→ČR. Data jsou stahována živě
#        ze zdarma dostupných zdrojů bez placených API klíčů.
# Stack: Streamlit · Pandas · Plotly · BeautifulSoup4 · lxml · requests · yfinance
# ==============================================================================

# ── Standardní knihovny ────────────────────────────────────────────────────────
import math
import re
import time
import unicodedata
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

# ── Web scraping ───────────────────────────────────────────────────────────────
import requests
from bs4 import BeautifulSoup

# ── Finanční data ──────────────────────────────────────────────────────────────
import yfinance as yf

# ── Vizualizace ────────────────────────────────────────────────────────────────
import plotly.express as px
import plotly.graph_objects as go

# ── Streamlit ─────────────────────────────────────────────────────────────────
import streamlit as st

TZ_PRAGUE = ZoneInfo("Europe/Prague")
CACHE_TTL = 3600
_YF_HIST_PERIOD = "1y"


def now_prague() -> datetime:
    """Aktuální datum a čas ve středoevropském pásmu (Praha)."""
    return datetime.now(TZ_PRAGUE)


# ==============================================================================
# KONFIGURACE STRÁNKY
# Musí být PRVNÍ Streamlit příkaz – před jakýmkoliv jiným st.*
# ==============================================================================
st.set_page_config(
    page_title="pbcable Dashboard",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="collapsed",
    menu_items={
        "Get Help": None,
        "Report a bug": None,
        "About": "Kabelářský Nákupní Dashboard v2.0 · Živá data · Bez placených API",
    },
)

_SESSION_AUTH = "app_authenticated"
_SESSION_ROLE = "user_role"


def _load_app_key() -> str | None:
    """Načte APP_KEY ze Streamlit secrets; při chybě vrátí None."""
    try:
        key = st.secrets["APP_KEY"]
        if key is None:
            return None
        key_str = str(key).strip()
        return key_str if key_str else None
    except Exception:
        return None


def _load_supplier_key() -> str | None:
    """Načte SUPPLIER_KEY ze Streamlit secrets (přístup dodavatele)."""
    try:
        key = st.secrets["SUPPLIER_KEY"]
        if key is None:
            return None
        key_str = str(key).strip()
        return key_str if key_str else None
    except Exception:
        return None


def _authenticate_user(access_key: str) -> bool:
    """Ověří klíč a nastaví roli v session_state. Vrací True při úspěchu."""
    app_key = _load_app_key()
    supplier_key = _load_supplier_key()
    key = access_key.strip()

    if app_key and key == app_key:
        st.session_state[_SESSION_AUTH] = True
        st.session_state[_SESSION_ROLE] = "admin"
        return True
    if supplier_key and key == supplier_key:
        st.session_state[_SESSION_AUTH] = True
        st.session_state[_SESSION_ROLE] = "supplier"
        return True
    return False


def _query_param_key() -> str | None:
    """Hodnota parametru ?key= z URL."""
    raw = st.query_params.get("key")
    if raw is None:
        return None
    if isinstance(raw, list):
        return str(raw[0]).strip() if raw else None
    return str(raw).strip()


def require_app_authentication() -> None:
    """
    Ověření přístupu: tajný klíč v URL (?key=) nebo heslo.
    Bez úspěšného ověření zastaví běh skriptu (st.stop).
    """
    app_key = _load_app_key()
    if not app_key:
        st.error(
            "Chybí nebo je neplatné nastavení **APP_KEY** v Streamlit secrets "
            "(soubor `.streamlit/secrets.toml` lokálně nebo Secrets ve Streamlit Cloud)."
        )
        st.stop()

    if st.session_state.get(_SESSION_AUTH):
        st.session_state.setdefault(_SESSION_ROLE, "admin")
        return

    url_key = _query_param_key()
    if url_key and _authenticate_user(url_key):
        return

    _left, _center, _right = st.columns([1, 1.2, 1])
    with _center:
        st.markdown("### 🔒 Přístup k dashboardu")
        st.caption(
            "Přihlaste se tajným odkazem (`?key=…`) nebo zadejte přístupové heslo."
        )
        manual_key = st.text_input(
            "Heslo / přístupový klíč",
            type="password",
            key="app_manual_key",
            placeholder="Zadejte APP_KEY",
        )
        if st.button("Přihlásit se", type="primary", use_container_width=True):
            if _authenticate_user(manual_key):
                st.query_params["key"] = manual_key.strip()
                st.rerun()
            else:
                st.error("Neplatné heslo. Přístup odepřen.")
        if url_key and not _authenticate_user(url_key):
            st.warning("Parametr `key` v adrese URL není platný.")

    st.stop()


require_app_authentication()

# ==============================================================================
# CSS INJEKCE — Veškeré styly přímo v kódu
# ==============================================================================
CUSTOM_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Syne:wght@400;500;600;700;800&family=IBM+Plex+Mono:ital,wght@0,300;0,400;0,500;0,600;1,400&display=swap');

*, *::before, *::after { box-sizing: border-box; }

.stApp,
[data-testid="stAppViewContainer"],
[data-testid="stMain"],
section[data-testid="stMain"] > div:first-child {
    background-color: #F8F9FA !important;
    color: #212529 !important;
    font-family: 'Syne', sans-serif !important;
}

p, span, label, .stMarkdown { color: #212529; }

#MainMenu { visibility: hidden; }
header[data-testid="stHeader"] { visibility: hidden; height: 0; }
footer { visibility: hidden; }
[data-testid="stDecoration"] { display: none; }
[data-testid="stStatusWidget"] { display: none; }

[data-testid="stSidebar"],
[data-testid="stSidebarContent"] {
    background-color: #FFFFFF !important;
    border-right: 2px solid #CED4DA !important;
}

::-webkit-scrollbar { width: 6px; height: 6px; }
::-webkit-scrollbar-track { background: #F8F9FA; }
::-webkit-scrollbar-thumb { background: #ADB5BD; border-radius: 4px; }

.dash-header {
    background: #FFFFFF;
    border: 2px solid #343A40;
    border-radius: 14px;
    padding: 24px 32px 20px;
    margin-bottom: 20px;
    box-shadow: 0 4px 14px rgba(0, 0, 0, 0.08);
    position: relative;
}

.dash-header::before {
    content: '';
    position: absolute;
    top: 0; left: 0; right: 0;
    height: 4px;
    background: linear-gradient(90deg, #0D6EFD, #198754, #FD7E14);
    border-radius: 14px 14px 0 0;
}

.dash-header-content {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    flex-wrap: wrap;
    gap: 16px;
}

.dash-title {
    font-family: 'Syne', sans-serif;
    font-size: 2rem;
    font-weight: 800;
    color: #000000;
    margin: 0 0 6px 0;
}

.dash-title span { color: #0D6EFD; }

.dash-subtitle {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.72rem;
    color: #495057;
    letter-spacing: 1.5px;
    text-transform: uppercase;
}

.dash-timestamp {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.75rem;
    color: #212529;
    line-height: 1.7;
}

.dash-timestamp strong { color: #000000; }

.badge {
    display: inline-flex;
    align-items: center;
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.65rem;
    font-weight: 600;
    padding: 4px 10px;
    border-radius: 100px;
}

.badge-live { background: #D1E7DD; color: #0F5132; border: 1px solid #198754; }
.badge-offline { background: #F8D7DA; color: #842029; border: 1px solid #DC3545; }
.badge-model { background: #FFF3CD; color: #664D03; border: 1px solid #FFC107; }

.section-header {
    display: flex;
    align-items: center;
    flex-wrap: wrap;
    gap: 10px 12px;
    margin: 24px 0 16px 0;
    padding-bottom: 12px;
    border-bottom: 2px solid #343A40;
}

.section-title {
    font-family: 'Syne', sans-serif;
    font-size: 1rem;
    font-weight: 700;
    color: #000000;
    text-transform: uppercase;
    letter-spacing: 1.2px;
}

.metric-card {
    position: relative;
    background: #FFFFFF;
    border: 2px solid #495057;
    border-radius: 12px;
    padding: 16px;
    margin-bottom: 10px;
    box-shadow: 0 3px 10px rgba(0, 0, 0, 0.1);
}

.metric-card::before {
    content: '';
    position: absolute;
    top: 0; left: 0;
    width: 4px;
    height: 100%;
    border-radius: 12px 0 0 12px;
}

.card-copper::before { background: #FD7E14; }
.card-aluminum::before { background: #198754; }
.card-steel::before { background: #6C757D; }
.card-usd::before { background: #198754; }
.card-eur::before { background: #0D6EFD; }
.card-cny::before { background: #DC3545; }
.card-oil::before { background: #FFC107; }
.card-plastic::before { background: #20C997; }
.card-logistics::before { background: #6F42C1; }
.card-neutral::before { background: #495057; }
.card-lead::before { background: #6F42C1; }
.card-zinc::before { background: #6610F2; }
.card-tin::before { background: #D63384; }
.card-nickel::before { background: #0DCAF0; }

.card-label {
    font-size: 0.68rem;
    font-weight: 700;
    color: #495057;
    text-transform: uppercase;
    margin-bottom: 8px;
}

.card-value {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 1.45rem;
    font-weight: 700;
    color: #000000;
    margin-bottom: 6px;
}

.card-value-sm { font-size: 1.1rem; }
.card-unit {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.85rem;
    font-weight: 600;
    color: #343a40;
    margin: 4px 0 8px 0;
    letter-spacing: 0.4px;
}
.card-unit-emphasis {
    font-size: 1.2rem;
    font-weight: 700;
    color: #000000;
    margin: 8px 0 12px 0;
    letter-spacing: 0.6px;
    text-transform: uppercase;
}
.card-extra {
    font-size: 0.78rem;
    font-weight: 500;
    color: #495057;
    line-height: 1.45;
    margin-top: 8px;
}
.card-extra-emphasis {
    font-size: 1rem;
    font-weight: 700;
    color: #212529;
    margin-top: 14px;
    padding-top: 10px;
    border-top: 2px solid #DEE2E6;
    line-height: 1.5;
}
.card-delta-row { margin-top: 6px; }

.delta-chip {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.72rem;
    padding: 2px 8px;
    border-radius: 6px;
}

.delta-up { background: #D1E7DD; color: #0F5132; }
.delta-down { background: #F8D7DA; color: #842029; }
.delta-flat { background: #E9ECEF; color: #495057; }

.spread-card {
    background: #FFFFFF;
    border: 2px solid #ADB5BD;
    border-radius: 10px;
    padding: 12px 14px;
    margin-bottom: 8px;
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
}

.spread-label { font-size: 0.65rem; font-weight: 700; color: #495057; text-transform: uppercase; }
.spread-value { font-family: 'IBM Plex Mono', monospace; font-size: 1.2rem; font-weight: 700; color: #000000; }
.spread-details { font-size: 0.68rem; color: #495057; }

.chart-wrap {
    background: #FFFFFF;
    border: 2px solid #CED4DA;
    border-radius: 12px;
    padding: 16px 12px;
    margin-bottom: 12px;
    box-shadow: 0 2px 10px rgba(0, 0, 0, 0.08);
}

@media (max-width: 768px) {
    .dash-title { font-size: 1.35rem; }
    .metric-card { padding: 12px; }
    .card-value { font-size: 1.2rem; }
    .card-unit-emphasis { font-size: 1.05rem; }
    .card-extra-emphasis { font-size: 0.92rem; }
    [data-testid="stHorizontalBlock"] { flex-direction: column !important; }
    [data-testid="stHorizontalBlock"] > div { width: 100% !important; }
}

.info-box {
    background: #E7F1FF;
    border: 1px solid #0D6EFD;
    border-left: 4px solid #0D6EFD;
    border-radius: 8px;
    padding: 10px 14px;
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.78rem;
    color: #212529;
    line-height: 1.55;
    margin: 8px 0;
}

.warning-box {
    background: #FFF3CD;
    border: 1px solid #FFC107;
    border-left: 4px solid #FFC107;
    border-radius: 8px;
    padding: 10px 14px;
    font-size: 0.78rem;
    color: #664D03;
}

.error-box {
    background: #F8D7DA;
    border: 1px solid #DC3545;
    border-radius: 8px;
    padding: 10px 14px;
    font-size: 0.75rem;
    color: #842029;
    text-align: center;
}

.data-table-wrap {
    background: #FFFFFF;
    border: 2px solid #CED4DA;
    border-radius: 12px;
    padding: 16px;
}

.data-table-wrap table { width: 100%; border-collapse: collapse; }
.data-table-wrap th { color: #000000; border-bottom: 2px solid #343A40; padding: 8px 12px; }
.data-table-wrap td { color: #212529; border-bottom: 1px solid #DEE2E6; padding: 9px 12px; }
.data-table-wrap tr:hover td { background: #F1F3F5; }

.calc-result {
    background: #FFFFFF;
    border: 2px solid #495057;
    border-radius: 10px;
    padding: 14px;
    text-align: center;
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
}

.calc-result-label {
    font-size: 0.65rem;
    font-weight: 700;
    color: #495057;
    text-transform: uppercase;
}

.calc-result-value {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 1.2rem;
    font-weight: 700;
    color: #000000;
}

.section-divider { height: 2px; background: #CED4DA; margin: 24px 0; }

.dash-footer {
    text-align: center;
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.68rem;
    color: #495057;
    padding: 20px 0;
    border-top: 2px solid #CED4DA;
    margin-top: 32px;
}

button[kind="primary"],
button[data-testid="baseButton-primary"] {
    background: #0D6EFD !important;
    color: #FFFFFF !important;
    border: 2px solid #0A58CA !important;
    font-weight: 700 !important;
    border-radius: 8px !important;
}

button[kind="secondary"],
.stButton > button {
    background: #FFFFFF !important;
    border: 2px solid #0D6EFD !important;
    color: #0D6EFD !important;
    font-weight: 600 !important;
    border-radius: 8px !important;
}

button[kind="secondary"]:hover { background: #E7F1FF !important; }

[data-testid="stExpander"] {
    background: #FFFFFF !important;
    border: 2px solid #495057 !important;
    border-radius: 10px !important;
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06) !important;
}

[data-testid="stTabs"] {
    background: #FFFFFF;
    padding: 10px 20px 20px 20px;
    border-radius: 12px;
    border: 2px solid #CED4DA;
    box-shadow: 0 2px 10px rgba(0, 0, 0, 0.05);
}
[data-testid="stTabs"] button {
    font-family: 'Syne', sans-serif !important;
    font-weight: 700 !important;
    font-size: 1.05rem !important;
}

details summary {
    font-family: 'Syne', sans-serif !important;
    font-weight: 700 !important;
    color: #000000 !important;
}

[data-testid="stNumberInput"] input,
[data-testid="stDateInput"] input {
    background: #FFFFFF !important;
    border: 2px solid #495057 !important;
    color: #000000 !important;
    font-family: 'IBM Plex Mono', monospace !important;
}

[data-testid="stSelectbox"] > div > div {
    background: #FFFFFF !important;
    border: 2px solid #495057 !important;
    color: #000000 !important;
}

[data-testid="stDataFrame"] {
    border: 2px solid #CED4DA !important;
    border-radius: 10px !important;
}

[data-testid="stRadio"] label {
    background: #FFFFFF !important;
    border: 2px solid #ADB5BD !important;
    color: #212529 !important;
    font-weight: 600 !important;
    padding: 4px 14px !important;
}

[data-testid="stRadio"] label[data-checked="true"],
[data-testid="stRadio"] div[aria-checked="true"] label {
    border-color: #0D6EFD !important;
    color: #FFFFFF !important;
    background: #0D6EFD !important;
}

[data-testid="stSegmentedControl"] {
    background: #E9ECEF !important;
    border: 2px solid #495057 !important;
    border-radius: 10px !important;
}

.currency-bar {
    background: #FFFFFF;
    border: 2px solid #343A40;
    border-radius: 12px;
    padding: 14px 18px;
    margin-bottom: 16px;
    box-shadow: 0 3px 10px rgba(0, 0, 0, 0.08);
}

.currency-bar-label {
    font-weight: 700;
    color: #000000;
    text-transform: uppercase;
}

.currency-bar-hint { color: #495057; }

[data-testid="stMetricLabel"] { color: #495057 !important; font-weight: 700 !important; }
[data-testid="stMetricValue"] { color: #000000 !important; font-weight: 700 !important; }

.stProgress > div > div > div > div {
    background: linear-gradient(90deg, #0D6EFD, #198754) !important;
}
.stProgress > div > div > div { background-color: #E9ECEF !important; }

[data-testid="stHorizontalBlock"] { gap: 0.65rem !important; }
div[data-testid="column"] {
    padding-left: 6px !important;
    padding-right: 6px !important;
    margin-bottom: 8px !important;
}

</style>
"""


def _render_app_branding() -> None:
    """Logo a titulek + globální CSS (až po ověření přístupu)."""
    st.markdown(CUSTOM_CSS, unsafe_allow_html=True)
    col1, col2 = st.columns([1, 4])
    with col1:
        try:
            st.image("logo.png", width=150)
        except Exception:
            pass
    with col2:
        st.title("pbcable s.r.o.")


# ==============================================================================
# ─────────────────────────────────────────────────────────────────────────────
#  POMOCNÉ FUNKCE UI
# ─────────────────────────────────────────────────────────────────────────────
# ==============================================================================

def badge_html(is_live: bool, source: str = "", model: bool = False) -> str:
    """Vrátí HTML pro status badge (LIVE / OFFLINE / MODEL)."""
    if model:
        return f'<span class="badge badge-model">◆ MODEL{" · " + source if source else ""}</span>'
    if is_live:
        return f'<span class="badge badge-live">LIVE{" · " + source if source else ""}</span>'
    return '<span class="badge badge-offline">OFFLINE</span>'


def section_header(icon: str, title: str, *badges_html: str) -> None:
    """Vykreslí záhlaví sekce s ikonkou, titulkem a libovolnými odznaky."""
    badges_str = " &nbsp; ".join(badges_html)
    st.markdown(
        f"""
        <div class="section-header">
            <span class="section-icon">{icon}</span>
            <span class="section-title">{title}</span>
            {badges_str}
        </div>
        """,
        unsafe_allow_html=True,
    )


def format_num(value, decimals: int = 2, prefix: str = "", suffix: str = "") -> str:
    """Formátuje číslo na řetězec s mezerou jako oddělovačem tisíců."""
    if value is None:
        return "N/A"
    try:
        formatted = f"{float(value):,.{decimals}f}".replace(",", " ")
        return f"{prefix}{formatted}{suffix}"
    except (ValueError, TypeError):
        return "N/A"


def delta_chip(delta_val, suffix: str = "") -> str:
    """Vrátí HTML chip pro změnu hodnoty (▲ zelená / ▼ červená / — šedá)."""
    if delta_val is None:
        return '<span class="delta-chip delta-flat">— N/A</span>'
    try:
        d = float(delta_val)
        if d > 0:
            return f'<span class="delta-chip delta-up">▲ +{format_num(d, 2)}{suffix}</span>'
        elif d < 0:
            return f'<span class="delta-chip delta-down">▼ {format_num(d, 2)}{suffix}</span>'
        else:
            return f'<span class="delta-chip delta-flat">— 0.00{suffix}</span>'
    except (ValueError, TypeError):
        return '<span class="delta-chip delta-flat">— N/A</span>'


def metric_card(
    label: str,
    value: str,
    unit: str,
    delta=None,
    delta_suffix: str = "",
    card_class: str = "card-neutral",
    extra: str = None,
    value_size: str = "",
    emphasis: bool = False,
) -> str:
    """Sestaví HTML pro metrickou kartu a vrátí jako řetězec."""
    delta_row = f'<div class="card-delta-row">{delta_chip(delta, delta_suffix)}</div>'
    extra_cls = "card-extra card-extra-emphasis" if emphasis else "card-extra"
    unit_cls = "card-unit card-unit-emphasis" if emphasis else "card-unit"
    extra_row = f'<div class="{extra_cls}">{extra}</div>' if extra else ""
    size_cls = " card-value-sm" if value_size == "sm" else ""
    return f"""
    <div class="metric-card {card_class}">
        <div class="card-label">{label}</div>
        <div class="card-value{size_cls}">{value}</div>
        <div class="{unit_cls}">{unit}</div>
        {delta_row}
        {extra_row}
    </div>
    """


def error_card(label: str, card_class: str = "card-neutral", msg: str = "Data momentálně nedostupná") -> str:
    """Vrátí metrickou kartu s chybovým hlášením."""
    return f"""
    <div class="metric-card {card_class}">
        <div class="card-label">{label}</div>
        <div class="error-box" style="margin-top:10px;">{msg}</div>
    </div>
    """


def _show_plotly(fig: go.Figure | None, *, toolbar: bool = True) -> None:
    """Vykreslí Plotly graf v chart-wrap kontejneru."""
    if fig is None:
        return
    _ensure_plot_separators(fig)
    st.markdown('<div class="chart-wrap">', unsafe_allow_html=True)
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": toolbar})
    st.markdown("</div>", unsafe_allow_html=True)


_LME_METAL_CARDS: list[tuple[str, str, str, str]] = [
    ("copper", "Měď (Cu)", "card-copper", "copper_stock"),
    ("aluminum", "Hliník (Al)", "card-aluminum", "aluminum_stock"),
]

_SHFE_SPREAD_METALS = [("copper", "Měď"), ("aluminum", "Hliník")]

_CNB_METRIC_CARDS = [
    ("USD", "USD/CZK", "Americký dolar", "card-usd"),
    ("EUR", "EUR/CZK", "Euro", "card-eur"),
    ("CNY", "CNY/CZK", "Čínský jüan", "card-cny"),
]


def _render_lme_metal_card(
    metal_key: str,
    label: str,
    card_class: str,
    stock_key: str,
    wm_data: dict | None,
) -> None:
    """Metrická karta LME Cash (měď / hliník) — Westmetall."""
    price_usd, _, _ = resolve_metal_price(metal_key, wm_data)
    unit = metal_unit_label()
    ccy = get_display_currency()
    stock_extra = wm_stock_extra(wm_data, stock_key)
    if price_usd is not None:
        price_disp = usd_to_display(price_usd, ccy)
        if price_disp is None and ccy == "EUR":
            st.markdown(
                error_card(label, card_class, "N/A — chybí EUR/USD"),
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                metric_card(
                    label,
                    format_num(price_disp, 0) if price_disp is not None else "N/A",
                    unit,
                    card_class=card_class,
                    extra=stock_extra or "Westmetall LME Cash",
                    emphasis=True,
                ),
                unsafe_allow_html=True,
            )
    else:
        st.markdown(
            error_card(label, card_class, "Data nedostupná · Westmetall"),
            unsafe_allow_html=True,
        )


def _render_steel_metric_card(
    steel_data: dict | None,
    label: str,
    default_ticker: str,
) -> None:
    """Metrická karta oceli (HRC) — Yahoo."""
    unit = metal_unit_label()
    ccy = get_display_currency()
    d_suffix = currency_delta_suffix()
    if steel_data:
        st_price = usd_to_display(steel_data["price"], ccy)
        st_delta = usd_to_display(steel_data.get("delta"), ccy)
        st.markdown(
            metric_card(
                label,
                format_num(st_price, 0) if st_price is not None else "N/A",
                unit,
                delta=st_delta,
                delta_suffix=d_suffix if st_delta is not None else "",
                card_class="card-steel",
                extra=f'{steel_data.get("ticker", default_ticker)} · Yahoo',
                emphasis=True,
            ),
            unsafe_allow_html=True,
        )
    else:
        st.warning(f"{label}: Yahoo Finance nevrátilo živou cenu ({default_ticker}).")
        st.markdown(
            error_card(label, "card-steel", "Data nedostupná"),
            unsafe_allow_html=True,
        )


# ==============================================================================
# ─────────────────────────────────────────────────────────────────────────────
#  DATOVÉ FUNKCE – METALY (LME via westmetall.com)
# ─────────────────────────────────────────────────────────────────────────────
# ==============================================================================

# Westmetall LME Cash — pole v URL (Settlement Kasse), ne skladové zásoby
_WESTMETALL_LME_FIELDS: dict[str, tuple[str, str, tuple[float, float]]] = {
    "copper":   ("LME_Cu_cash", "Copper",    (4_000, 25_000)),
    "aluminum": ("LME_Al_cash", "Aluminium", (1_500, 8_000)),
}

_WESTMETALL_STOCK_FIELDS: dict[str, tuple[str, str, tuple[int, int]]] = {
    "copper_stock":   ("LME_Cu_cash", "Copper",    (5_000, 2_000_000)),
    "aluminum_stock": ("LME_Al_cash", "Aluminium", (5_000, 1_500_000)),
}

WM_HISTORY_URLS: dict[str, str] = {
    "copper": (
        "https://www.westmetall.com/en/markdaten.php?action=table&field=LME_Cu_cash"
    ),
    "aluminum": (
        "https://www.westmetall.com/en/markdaten.php?action=table&field=LME_Al_cash"
    ),
}

_WM_HTTP_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.westmetall.com/",
}

_WM_MONTHS_EN: dict[str, int] = {
    "january": 1, "february": 2, "march": 3, "april": 4,
    "may": 5, "june": 6, "july": 7, "august": 8,
    "september": 9, "october": 10, "november": 11, "december": 12,
}

# Počet dní pro filtrování westmetall historie (globální přepínač)
_WM_PERIOD_DAYS: dict[str, int] = {
    "5d":  7,
    "1mo": 31,
    "3mo": 92,
    "6mo": 183,
    "1y":  365,
}

# Pevné pořadí sloupcového grafu kovů
_BAR_CHART_ORDER: list[tuple[str, str]] = [
    ("copper",   "Copper"),
    ("aluminum", "Aluminum"),
    ("steel",    "Steel"),
]


def _parse_westmetall_price(text: str) -> float | None:
    """Parsuje čísla z westmetall: '13,545.00' (USD/t) i '391,900' (tuny zásob)."""
    if not text or not re.search(r"\d", text):
        return None
    raw = re.sub(r"[^\d.,]", "", text.strip())
    if "," in raw and "." in raw:
        raw = raw.replace(",", "")
    elif "," in raw:
        parts = raw.split(",")
        if len(parts) == 2 and len(parts[1]) == 3 and not parts[1].endswith("00"):
            # Tisícové oddělovače: 391,900 → 391900
            raw = parts[0] + parts[1]
        elif len(parts) == 2 and len(parts[1]) <= 2:
            raw = parts[0] + "." + parts[1]
        else:
            raw = raw.replace(",", "")
    try:
        return float(raw)
    except ValueError:
        return None


def _parse_wm_table_date(text: str) -> datetime | None:
    """Parsuje datum z westmetall tabulky, např. '22. May 2026'."""
    text = text.strip()
    m = re.match(r"(\d{1,2})\.\s*([A-Za-z]+)\s*(\d{4})", text)
    if m:
        day, month_name, year = int(m.group(1)), m.group(2).lower(), int(m.group(3))
        month = _WM_MONTHS_EN.get(month_name)
        if month:
            try:
                return datetime(year, month, day)
            except ValueError:
                return None
    for fmt in ("%d.%m.%Y", "%d.%m.%y"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


@st.cache_data(ttl=CACHE_TTL)
def fetch_westmetall_history(url: str) -> pd.DataFrame | None:
    """
    Stáhne historii z westmetall tabulky (action=table&field=LME_*_cash).
    Sloupce: Date, Close (USD/t LME Cash), Stock (tuny skladu).
    """
    is_aluminum = "LME_Al" in url
    price_lo, price_hi = (1_500, 8_000) if is_aluminum else (4_000, 25_000)
    stock_lo, stock_hi = 1_000, 2_000_000

    try:
        resp = requests.get(url, headers=_WM_HTTP_HEADERS, timeout=25)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "lxml")
        rows: list[dict] = []

        for table in soup.find_all("table"):
            for row in table.find_all("tr"):
                cells = row.find_all(["td", "th"])
                if len(cells) < 2:
                    continue
                date_txt = cells[0].get_text(strip=True)
                if not date_txt or date_txt.lower() == "date":
                    continue
                dt = _parse_wm_table_date(date_txt)
                if dt is None:
                    continue

                price = _parse_westmetall_price(cells[1].get_text(strip=True))
                if price is None or not (price_lo <= price <= price_hi):
                    continue

                stock = None
                if len(cells) >= 4:
                    stock_raw = _parse_westmetall_price(cells[3].get_text(strip=True))
                    if stock_raw is not None and stock_lo <= stock_raw <= stock_hi:
                        stock = int(round(stock_raw))

                rows.append({"Date": dt, "Close": price, "Stock": stock})

        if not rows:
            return None

        df = pd.DataFrame(rows)
        df = df.drop_duplicates(subset=["Date"], keep="first")
        df = df.sort_values("Date").reset_index(drop=True)
        return df

    except Exception:
        return None


def filter_history_by_period(df: pd.DataFrame | None, date_col: str = "Date") -> pd.DataFrame | None:
    """Ořízne historii podle globálního přepínače období (1W–1Y) — bez nového stahování."""
    if df is None or df.empty:
        return None
    days = _WM_PERIOD_DAYS.get(get_chart_period(), 92)
    out = df.copy()
    if date_col in out.columns:
        out[date_col] = pd.to_datetime(out[date_col], utc=True).dt.tz_localize(None)
    prague_now = now_prague()
    cutoff = pd.Timestamp(prague_now.replace(tzinfo=None)).normalize() - pd.Timedelta(days=days)
    filtered = out[out[date_col] >= cutoff]
    return filtered.reset_index(drop=True) if not filtered.empty else None


filter_wm_history_by_period = filter_history_by_period


@st.cache_data(ttl=CACHE_TTL)
def fetch_westmetall() -> dict | None:
    """
    Scrapuje LME Cash (Settlement Kasse) z westmetall.com/en/markdaten.php.
    Parsuje podle field=LME_*_cash v odkazech — vyhne se LME Stocks (tuny ve skladu).
    """
    url = "https://www.westmetall.com/en/markdaten.php"
    try:
        resp = requests.get(url, headers=_WM_HTTP_HEADERS, timeout=18)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "lxml")
        result: dict = {}
        in_official_prices = False
        in_lme_stocks = False

        for row in soup.find_all("tr"):
            row_lower = row.get_text(" ", strip=True).lower()

            if "official lme" in row_lower and "price" in row_lower:
                in_official_prices = True
                in_lme_stocks = False
                continue
            if in_official_prices and "lme stocks" in row_lower:
                in_official_prices = False
                in_lme_stocks = True
                continue
            if in_lme_stocks and (
                "exchange rates" in row_lower or "german metal" in row_lower
            ):
                in_lme_stocks = False
                continue

            if in_official_prices:
                for metal, (field, label, (lo, hi)) in _WESTMETALL_LME_FIELDS.items():
                    if metal in result:
                        continue
                    if label.lower() not in row_lower:
                        continue
                    cash_prices: list[float] = []
                    for link in row.find_all("a", href=True):
                        href = link.get("href", "")
                        if f"field={field}" not in href:
                            continue
                        val = _parse_westmetall_price(link.get_text(strip=True))
                        if val is not None and lo <= val <= hi:
                            cash_prices.append(val)
                    if cash_prices:
                        result[metal] = {
                            "price": round(cash_prices[0], 2),
                            "unit":  "USD/t",
                            "field": field,
                        }

            if in_lme_stocks:
                for stock_key, (field, label, (lo, hi)) in _WESTMETALL_STOCK_FIELDS.items():
                    if stock_key in result:
                        continue
                    if label.lower() not in row_lower:
                        continue
                    for link in row.find_all("a", href=True):
                        href = link.get("href", "")
                        if f"field={field}" not in href:
                            continue
                        val = _parse_westmetall_price(link.get_text(strip=True))
                        if val is not None and lo <= val <= hi:
                            result[stock_key] = {
                                "tons": int(round(val)),
                                "unit": "t",
                            }
                            break

        if result:
            result["_source"] = "westmetall.com"
            result["_ts"] = now_prague().strftime("%Y-%m-%d %H:%M")
            return result
        return None

    except Exception:
        return None


# Převod CME HRC (USD / short ton) → USD / metrická tuna
_ST_TON_FACTOR = 2204.623 / 2000.0

_STEEL_HRC_TICKERS = ("HRC=F", "STRE=F")


@st.cache_data(ttl=CACHE_TTL)
def fetch_steel_ticker(ticker: str, note: str) -> dict | None:
    spot = fetch_yf_spot(ticker)
    if not spot:
        return None
    price_t = spot["price"] * _ST_TON_FACTOR
    prev_t = spot["prev"] * _ST_TON_FACTOR
    return {
        "price": round(price_t, 2), "prev_price": round(prev_t, 2),
        "delta": round(price_t - prev_t, 2), "delta_pct": spot["delta_pct"],
        "unit": "USD/t", "ticker": ticker, "note": note,
        "_source": "Yahoo Finance (Robot)", "_ts": now_prague().strftime("%Y-%m-%d %H:%M"),
    }


@st.cache_data(ttl=CACHE_TTL)
def fetch_steel_yfinance() -> dict | None:
    """Ocel HRC — Yahoo HRC=F, záloha STRE=F."""
    for ticker in _STEEL_HRC_TICKERS:
        data = fetch_steel_ticker(ticker, "Hot Rolled Coil (CME)")
        if data:
            return data
    return None


@st.cache_data(ttl=CACHE_TTL)
def _yf_history(ticker: str) -> pd.DataFrame | None:
    try:
        import os
        if not os.path.exists("robot_history.csv"):
            return None
        df = pd.read_csv("robot_history.csv", parse_dates=["Date"])
        if ticker in df.columns:
            return df[["Date", ticker]].rename(columns={ticker: "Close"}).dropna()
    except Exception:
        pass
    return None


def fetch_metal_history(ticker: str = "HG=F", period: str = "6mo") -> pd.DataFrame | None:
    """Historie tickeru oříznutá podle globálního období (period jen kvůli kompatibilitě API)."""
    return filter_history_by_period(_yf_history(ticker))


# ==============================================================================
# ─────────────────────────────────────────────────────────────────────────────
#  DATOVÉ FUNKCE – Čínský spot (ccmn.cn)
# ─────────────────────────────────────────────────────────────────────────────
# ==============================================================================


@st.cache_data(ttl=CACHE_TTL)
def fetch_ccmn_spot(metal: str = "copper") -> dict | None:
    try:
        import json
        with open("robot_data.json", "r", encoding="utf-8") as f:
            data = json.load(f)
        price = data.get("ccmn", {}).get(metal)
        if price:
            target = "1#铜" if metal == "copper" else "A00铝"
            return {"price": price, "unit": "CNY/t", "ticker": f"CCMN ({target})", "source": "ccmn.cn"}
    except Exception:
        pass
    return None


def _safe_float(s: str) -> float | None:
    """Bezpečný převod řetězce na float; vrátí None při selhání."""
    try:
        v = float(s.strip())
        return v if v != 0.0 else None
    except (ValueError, AttributeError):
        return None


# ==============================================================================
# ─────────────────────────────────────────────────────────────────────────────
#  DATOVÉ FUNKCE – FX (ČNB + yfinance trendy)
# ─────────────────────────────────────────────────────────────────────────────
# ==============================================================================

@st.cache_data(ttl=CACHE_TTL)
def fetch_cnb_rates() -> dict | None:
    """
    Stahuje denní kurzovní lístek ČNB z URL:
    https://www.cnb.cz/cs/financni-trhy/devizovy-trh/kurzy-devizoveho-trhu/
           kurzy-devizoveho-trhu/denni_kurz.txt
    Formát řádku: Země|Měna|Množství|Kód|Kurz
    Vrátí dict {KÓD: {rate, amount, currency, country}, _date, _ts} nebo None.
    """
    url = (
        "https://www.cnb.cz/cs/financni-trhy/devizovy-trh/"
        "kurzy-devizoveho-trhu/kurzy-devizoveho-trhu/denni_kurz.txt"
    )
    try:
        resp = requests.get(url, timeout=15)
        resp.encoding = "utf-8"
        lines = resp.text.strip().split("\n")
        if len(lines) < 3:
            return None

        date_str = lines[0].split("#")[0].strip()   # "02.05.2024"
        rates: dict = {"_date": date_str, "_ts": now_prague().strftime("%Y-%m-%d %H:%M")}

        for line in lines[2:]:
            parts = line.strip().split("|")
            if len(parts) != 5:
                continue
            country, currency, amount_str, code, rate_str = parts
            try:
                amount     = int(amount_str)
                rate_val   = float(rate_str.replace(",", "."))
                rate_unit  = rate_val / amount     # normalizace na 1 jednotku
                code_key = code.strip().upper()
                rates[code_key] = {
                    "rate":     round(rate_unit, 6),
                    "amount":   amount,
                    "currency": currency.strip(),
                    "country":  country.strip(),
                }
            except (ValueError, ZeroDivisionError):
                continue

        return rates if len(rates) > 3 else None
    except Exception:
        return None


def fetch_fx_history(ticker: str, period: str = "3mo") -> pd.DataFrame | None:
    """Historie FX páru oříznutá podle globálního období (period jen kvůli kompatibilitě)."""
    return filter_history_by_period(_yf_history(ticker))


@st.cache_data(ttl=CACHE_TTL)
def _cny_czk_history_full() -> tuple[pd.DataFrame | None, bool]:
    """Plná historie CNY/CZK — cache nezávislá na přepínači období."""
    direct = _yf_history("CNYCZK=X")
    if direct is not None and not direct.empty:
        return direct, False

    usd_czk = _yf_history("USDCZK=X")
    cny_usd = _yf_history("CNYUSD=X")
    if usd_czk is None or cny_usd is None or usd_czk.empty or cny_usd.empty:
        return None, False

    merged = pd.merge(
        usd_czk.rename(columns={"Close": "usd_czk"}),
        cny_usd.rename(columns={"Close": "cny_usd"}),
        on="Date",
        how="inner",
    )
    if merged.empty:
        return None, False
    merged["Close"] = merged["usd_czk"] * merged["cny_usd"]
    return merged[["Date", "Close"]].copy(), True


def fetch_cny_czk_history(period: str = "3mo") -> tuple[pd.DataFrame | None, bool]:
    """Historie CNY/CZK oříznutá podle globálního období."""
    full, derived = _cny_czk_history_full()
    return filter_history_by_period(full), derived


@st.cache_data(ttl=CACHE_TTL)
def fetch_yf_spot(ticker: str) -> dict | None:
    try:
        import json
        with open("robot_data.json", "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("yf_spot", {}).get(ticker)
    except Exception:
        pass
    return None


# ==============================================================================
#  RSI — Smart signály (pandas ewm, bez nových knihoven)
# ==============================================================================

_RSI_PERIOD = 14


def calculate_rsi(df: pd.DataFrame, column: str, period: int = 14) -> float | None:
    """
    Relative Strength Index (Wilder) — průměrné zisky/ztráty přes pandas ewm.
    Vrátí poslední RSI (0–100) nebo None při nedostatku dat.
    """
    if df is None or df.empty or column not in df.columns:
        return None
    prices = pd.to_numeric(df[column], errors="coerce").dropna()
    if len(prices) < period + 1:
        return None
    delta = prices.diff()
    gain = delta.clip(lower=0)
    loss = (-delta).clip(lower=0)
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, pd.NA)
    rsi = 100 - (100 / (1 + rs))
    rsi = rsi.where(avg_loss > 0, 100.0)
    last = rsi.iloc[-1]
    if pd.isna(last):
        return None
    return float(last)


def interpret_rsi(rsi: float) -> tuple[str, str]:
    """Textová interpretace RSI a typ Streamlit upozornění (success / warning / info)."""
    if rsi < 30:
        return "🟢 Přeprodáno (Silný potenciál k růstu / Zvážit nákup)", "success"
    if rsi > 70:
        return "🔴 Překoupeno (Riziko korekce / Vyčkat)", "warning"
    return "⚪ Neutrální zóna", "info"


def _rsi_from_history(df: pd.DataFrame | None, column: str = "Close") -> float | None:
    """Bezpečný výpočet RSI z historického DataFrame."""
    try:
        return calculate_rsi(df, column, period=_RSI_PERIOD)
    except Exception:
        return None


def _metal_rsi_value(metal_key: str, steel_data: dict | None) -> float | None:
    """Aktuální RSI pro měď, hliník (Westmetall) nebo ocel (Yahoo)."""
    try:
        if metal_key == "copper":
            return _rsi_from_history(fetch_westmetall_history(WM_HISTORY_URLS["copper"]))
        if metal_key == "aluminum":
            return _rsi_from_history(fetch_westmetall_history(WM_HISTORY_URLS["aluminum"]))
        if metal_key == "steel":
            if not steel_data:
                return None
            ticker = steel_data.get("ticker", "HRC=F")
            return _rsi_from_history(_yf_history(ticker))
    except Exception:
        return None
    return None


def render_rsi_signals(steel_data: dict | None) -> None:
    """Sekce Smart signály — RSI pro měď, hliník a ocel."""
    section_header("💡", "Tržní signály (RSI)")
    st.markdown(
        '<div class="info-box" style="margin-bottom:12px;">'
        "RSI (14) z historických cen · Měď &amp; Hliník: <strong>Westmetall</strong> · "
        "Ocel: <strong>Yahoo Finance</strong> · Orientační signál, nikoli investiční radu."
        "</div>",
        unsafe_allow_html=True,
    )
    rsi_metals = [
        ("copper", "Měď (Cu)"),
        ("aluminum", "Hliník (Al)"),
        ("steel", "Ocel (HRC)"),
    ]
    cols = st.columns(3)
    for (metal_key, label), col in zip(rsi_metals, cols):
        with col:
            rsi = _metal_rsi_value(metal_key, steel_data)
            if rsi is not None:
                st.metric(f"RSI — {label}", f"{rsi:.1f}", help="Relative Strength Index (14)")
                msg, alert_type = interpret_rsi(rsi)
                if alert_type == "success":
                    st.success(msg)
                elif alert_type == "warning":
                    st.warning(msg)
                else:
                    st.info(msg)
            else:
                st.metric(f"RSI — {label}", "N/A")
                st.info("Nedostatek historických dat pro výpočet RSI (min. 15 bodů).")


def build_daily_export_df() -> pd.DataFrame:
    """
    Jednořádkový snapshot aktuálních cen, kurzů a RSI pro export (datum = dnes, Praha).
    """
    today = now_prague().strftime("%Y-%m-%d")
    ccy = get_display_currency()
    wm = fetch_westmetall()
    steel = fetch_steel_yfinance()
    cnb = fetch_cnb_rates()

    cu_usd, _, _ = resolve_metal_price("copper", wm)
    al_usd, _, _ = resolve_metal_price("aluminum", wm)

    row: dict = {
        "datum": today,
        "mena_zobrazeni": ccy,
        "med_cena_usd_t": cu_usd,
        "hlinik_cena_usd_t": al_usd,
        "med_cena_zobrazeni": usd_to_display(cu_usd, ccy),
        "hlinik_cena_zobrazeni": usd_to_display(al_usd, ccy),
        "eur_usd": get_eurusd_rate(),
    }

    if steel:
        row["ocel_cena_usd_t"] = steel.get("price")
        row["ocel_cena_zobrazeni"] = usd_to_display(steel.get("price"), ccy)
        row["ocel_delta_pct"] = steel.get("delta_pct")
    else:
        row["ocel_cena_usd_t"] = None
        row["ocel_cena_zobrazeni"] = None
        row["ocel_delta_pct"] = None

    for metal_key, prefix in [("copper", "med"), ("aluminum", "hlinik"), ("steel", "ocel")]:
        rsi = _metal_rsi_value(metal_key, steel)
        row[f"{prefix}_rsi"] = round(rsi, 2) if rsi is not None else None
        if rsi is not None:
            signal_text, _ = interpret_rsi(rsi)
            row[f"{prefix}_rsi_signal"] = signal_text
        else:
            row[f"{prefix}_rsi_signal"] = None

    if cnb:
        row["cnb_datum"] = cnb.get("_date")
        for code, col in [("USD", "usd_czk"), ("EUR", "eur_czk"), ("CNY", "cny_czk")]:
            info = cnb.get(code)
            row[col] = info.get("rate") if info else None
    else:
        row["cnb_datum"] = None
        row["usd_czk"] = row["eur_czk"] = row["cny_czk"] = None

    try:
        oil = fetch_oil_data()
        if oil and oil.get("brent"):
            row["brent_usd_bbl"] = oil["brent"].get("price")
        else:
            row["brent_usd_bbl"] = None
    except Exception:
        row["brent_usd_bbl"] = None

    return pd.DataFrame([row])


def render_data_export() -> None:
    """Postranní panel — stažení denního CSV snapshotu (bez zápisu na server)."""
    with st.sidebar:
        st.markdown("### 💾 Export dat pro analýzu")
        st.caption(
            "Aktuální ceny kovů, kurzy ČNB, EUR/USD a RSI v jednom řádku. "
            "Soubor se generuje při každém stažení — na serveru se neukládá."
        )
        try:
            export_df = build_daily_export_df()
            if export_df.empty:
                st.warning("Data pro export nejsou k dispozici.")
                return
            csv_bytes = export_df.to_csv(index=False).encode("utf-8-sig")
            file_name = f"pbcable_ceny_{now_prague().strftime('%Y-%m-%d')}.csv"
            st.download_button(
                label="⬇️ Stáhnout CSV",
                data=csv_bytes,
                file_name=file_name,
                mime="text/csv",
                use_container_width=True,
            )
        except Exception as e:
            st.error(f"Export se nepodařilo připravit. Detail chyby: {e}")


# Globální přepínač období grafů → yfinance period
CHART_PERIODS: dict[str, str] = {
    "1W": "5d",
    "1M": "1mo",
    "3M": "3mo",
    "6M": "6mo",
    "1Y": "1y",
}

# Kovové položky v souhrnné tabulce — Westmetall LME Cash
SUMMARY_WM_METALS: dict[str, str] = {
    "copper":   "Copper",
    "aluminum": "Aluminum",
}


def get_eurusd_rate() -> float | None:
    """Kurz EURUSD z Yahoo (USD za 1 EUR)."""
    spot = fetch_yf_spot("EURUSD=X")
    if spot and spot.get("price"):
        rate = float(spot["price"])
        return rate if rate > 0 else None
    return None


def get_display_currency() -> str:
    """Aktuálně zvolená zobrazovací měna (USD nebo EUR)."""
    return st.session_state.get("display_currency", "USD")


def usd_to_display(amount_usd: float | None, currency: str | None = None) -> float | None:
    """Přepočet USD hodnoty do zvolené měny (EUR = USD / EURUSD)."""
    if amount_usd is None:
        return None
    currency = currency or get_display_currency()
    if currency == "USD":
        return float(amount_usd)
    rate = get_eurusd_rate()
    if not rate:
        return None
    return float(amount_usd) / rate


def apply_currency_to_df(df: pd.DataFrame, column: str = "Close") -> pd.DataFrame:
    """Přepočte sloupec historie z USD do zvolené měny (pro grafy)."""
    out = df.copy()
    if get_display_currency() == "EUR":
        rate = get_eurusd_rate()
        if rate and column in out.columns:
            out[column] = out[column] / rate
    return out


def metal_unit_label() -> str:
    return f"{get_display_currency()} / tona"


def oil_unit_label() -> str:
    return f"{get_display_currency()} / barel"


def currency_delta_suffix() -> str:
    return f" {get_display_currency()}"


def format_oil_price(value_usd: float | None, decimals: int = 2) -> str:
    """Formát ceny ropy v zvolené měně."""
    val = usd_to_display(value_usd)
    if val is None:
        return "N/A"
    sym = "€" if get_display_currency() == "EUR" else "$"
    return f"{sym}{format_num(val, decimals)}"


def get_usd_per_cny() -> float | None:
    """USD za 1 CNY — výhradně z kurzovního lístku ČNB (kód CNY)."""
    cnb = fetch_cnb_rates()
    if not cnb:
        return None
    cny_czk = cnb.get("CNY", {}).get("rate")
    usd_czk = cnb.get("USD", {}).get("rate")
    if cny_czk and usd_czk and usd_czk:
        return float(cny_czk) / float(usd_czk)
    return None


_CALC_CURRENCIES = ("EUR", "USD", "CZK", "CNY")
_EXCHANGE_CURRENCIES = ("USD", "CNY", "EUR")
_SURCHARGE_METAL_OPTIONS = {"Měď (Cu)": "copper", "Hliník (Al)": "aluminum"}


def _build_fx_rates(cnb: dict | None) -> dict | None:
    """Kurzy pro kalkulačku: ČNB (CZK páry) + EUR/USD (Yahoo) + USD/CNY (ČNB)."""
    if not cnb:
        return None
    usd_czk = (cnb.get("USD") or {}).get("rate")
    eur_czk = (cnb.get("EUR") or {}).get("rate")
    if not usd_czk or not eur_czk:
        return None
    return {
        "usd_czk": float(usd_czk),
        "eur_czk": float(eur_czk),
        "cny_czk": float((cnb.get("CNY") or {}).get("rate") or 0) or None,
        "eur_usd": get_eurusd_rate(),
        "usd_per_cny": get_usd_per_cny(),
    }


def _to_usd(amount: float, currency: str, rates: dict) -> float | None:
    """Převod libovolné měny na USD (základ pro výpočet)."""
    if currency == "USD":
        return amount
    if currency == "EUR":
        eur_usd = rates.get("eur_usd")
        return amount * eur_usd if eur_usd else None
    if currency == "CZK":
        return amount / rates["usd_czk"]
    if currency == "CNY":
        upc = rates.get("usd_per_cny")
        return amount * upc if upc else None
    return None


def _from_usd(amount_usd: float, currency: str, rates: dict) -> float | None:
    """Převod z USD do cílové měny."""
    if currency == "USD":
        return amount_usd
    if currency == "EUR":
        eur_usd = rates.get("eur_usd")
        return amount_usd / eur_usd if eur_usd else None
    if currency == "CZK":
        return amount_usd * rates["usd_czk"]
    if currency == "CNY":
        upc = rates.get("usd_per_cny")
        return amount_usd / upc if upc else None
    return None


def _metal_value_per_meter_usd(price_per_ton_usd: float, kg_per_km: float) -> float:
    """Hodnota kovu v 1 m kabelu: (USD/t / 1000) × (kg/km / 1000)."""
    return (price_per_ton_usd / 1000.0) * (kg_per_km / 1000.0)


def _live_metal_price_in_currency(
    metal_key: str,
    currency: str,
    wm_data: dict | None,
    rates: dict,
) -> float | None:
    """Aktuální burzovní cena kovu v zvolené měně burzy (LME USD nebo SHFE CNY)."""
    try:
        if currency == "CNY":
            shfe = fetch_ccmn_spot(metal_key)
            return float(shfe["price"]) if shfe and shfe.get("price") else None
        price_usd, _, _ = resolve_metal_price(metal_key, wm_data)
        if price_usd is None:
            return None
        if currency == "USD":
            return float(price_usd)
        if currency == "EUR":
            eur_usd = rates.get("eur_usd")
            return float(price_usd) / eur_usd if eur_usd else None
    except Exception:
        return None
    return None


def render_metal_surcharge_calculator(cnb: dict | None) -> None:
    """Profesionální kabelářská kalkulačka — dutá cena + metal surcharge."""
    rates = _build_fx_rates(cnb)
    wm_data = fetch_westmetall()

    st.markdown(
        '<div class="info-box">'
        "Cena za 1 m = <strong>dutá cena</strong> (práce + plasty, fixní) + "
        "<strong>přirážka za kov</strong> (dle burzy a hmotnosti v kabelu). "
        "Převody měn: kurzy <strong>ČNB</strong> + <strong>EUR/USD</strong> (Yahoo)."
        "</div>",
        unsafe_allow_html=True,
    )

    if not rates:
        st.warning(
            "Kalkulačka vyžaduje kurzy ČNB (USD/CZK, EUR/CZK) a ideálně EUR/USD z Yahoo."
        )
        return

    c1, c2, c3 = st.columns(3)
    with c1:
        metal_label = st.selectbox(
            "Výběr kovu",
            options=list(_SURCHARGE_METAL_OPTIONS.keys()),
            key="surcharge_metal",
        )
        metal_key = _SURCHARGE_METAL_OPTIONS[metal_label]
        kg_per_km = st.number_input(
            "Hmotnost kovu v kabelu (kg/km)",
            min_value=0.0,
            value=500.0,
            step=10.0,
            format="%.1f",
            key="surcharge_kg_km",
        )
    with c2:
        orig_total = st.number_input(
            "Původní celková cena za 1 m",
            min_value=0.0,
            value=2.50,
            step=0.01,
            format="%.4f",
            key="surcharge_orig_total",
        )
        offer_currency = st.selectbox(
            "Měna původní nabídky",
            options=_CALC_CURRENCIES,
            index=0,
            key="surcharge_offer_ccy",
        )
    with c3:
        output_currency = st.selectbox(
            "Výstupní měna výsledku",
            options=_CALC_CURRENCIES,
            index=0,
            key="surcharge_output_ccy",
        )

    lme_live = _live_metal_price_in_currency(metal_key, "USD", wm_data, rates)
    shfe_live = _live_metal_price_in_currency(metal_key, "CNY", wm_data, rates)

    st.markdown(
        "<div style='font-family:Syne,sans-serif;font-size:0.72rem;font-weight:700;"
        "color:#495057;text-transform:uppercase;letter-spacing:1px;margin:12px 0 8px 0;'>"
        "Burzovní data kovu (za tunu)</div>",
        unsafe_allow_html=True,
    )

    price_source = st.radio(
        "Zdroj aktuální ceny:",
        options=["LME (Live)", "SHFE (Live)", "Manuální (Predikce)"],
        horizontal=True,
        key="surcharge_price_source",
    )

    if price_source == "LME (Live)":
        _orig_ccy_hint = "USD"
        _default_orig = (lme_live * 0.92) if lme_live else 8000.0
    elif price_source == "SHFE (Live)":
        _orig_ccy_hint = "CNY"
        _default_orig = (shfe_live * 0.92) if shfe_live else 70000.0
    else:
        _orig_ccy_hint = "dle měny burzy"
        _default_orig = (lme_live * 0.92) if lme_live else 8000.0

    orig_metal_ex = st.number_input(
        f"Původní cena kovu na burze ({_orig_ccy_hint}/t)",
        min_value=0.0,
        value=float(_default_orig),
        step=50.0,
        format="%.2f",
        key="surcharge_orig_metal_ex",
        help="Referenční cena v měně odpovídající zvolenému zdroji aktuální ceny.",
    )

    curr_metal_ex: float | None = None
    exchange_currency: str = "USD"

    if price_source == "LME (Live)":
        exchange_currency = "USD"
        curr_metal_ex = lme_live
        if curr_metal_ex is not None:
            st.metric(
                "Aktuální cena LME (live)",
                f"{format_num(curr_metal_ex, 2)} USD/t",
                help="Westmetall LME Cash — automaticky v výpočtu",
            )
        else:
            st.warning(
                f"LME live cena pro {metal_label} není k dispozici (Westmetall)."
            )
    elif price_source == "SHFE (Live)":
        exchange_currency = "CNY"
        curr_metal_ex = shfe_live
        if curr_metal_ex is not None:
            st.metric(
                "Aktuální cena SHFE (live)",
                f"{format_num(curr_metal_ex, 2)} CNY/t",
                help="Sina Finance / SHFE — automaticky v výpočtu",
            )
        else:
            st.warning(
                f"SHFE live cena pro {metal_label} není k dispozici (Sina / kurz CNY)."
            )
    else:
        m1, m2 = st.columns(2)
        with m1:
            curr_metal_ex = st.number_input(
                "Aktuální cena kovu na burze (manuální)",
                min_value=0.0,
                value=float(lme_live or shfe_live or 9000.0),
                step=50.0,
                format="%.2f",
                key="surcharge_curr_metal_manual",
            )
        with m2:
            exchange_currency = st.selectbox(
                "Měna burzy",
                options=_EXCHANGE_CURRENCIES,
                index=0,
                key="surcharge_exchange_ccy",
            )

    if curr_metal_ex is None:
        st.info("Pro výpočet zvolte dostupný live zdroj nebo přepněte na manuální predikci.")
        return

    if kg_per_km <= 0 or orig_total <= 0 or orig_metal_ex <= 0 or curr_metal_ex <= 0:
        st.info("Vyplňte kladné hodnoty ceny, hmotnosti a burzovních cen.")
        return

    orig_metal_usd = _to_usd(orig_metal_ex, exchange_currency, rates)
    curr_metal_usd = _to_usd(curr_metal_ex, exchange_currency, rates)
    orig_total_usd = _to_usd(orig_total, offer_currency, rates)
    if orig_metal_usd is None or curr_metal_usd is None or orig_total_usd is None:
        st.error("Chybí kurz pro zvolenou kombinaci měn (zkontrolujte ČNB / EUR/USD / CNY).")
        return

    orig_metal_per_m_usd = _metal_value_per_meter_usd(orig_metal_usd, kg_per_km)
    curr_metal_per_m_usd = _metal_value_per_meter_usd(curr_metal_usd, kg_per_km)
    hollow_usd = orig_total_usd - orig_metal_per_m_usd

    fair_usd = hollow_usd + curr_metal_per_m_usd
    orig_metal_ex_usd = _to_usd(orig_metal_ex, exchange_currency, rates)
    if not orig_metal_ex_usd:
        st.error("Nelze převést původní burzovní cenu do USD pro výpočet růstu.")
        return
    metal_change_pct = (curr_metal_usd - orig_metal_ex_usd) / orig_metal_ex_usd
    simple_total_usd = orig_total_usd * (1.0 + metal_change_pct)
    diff_usd = fair_usd - simple_total_usd

    def _out(usd_val: float) -> float | None:
        return _from_usd(usd_val, output_currency, rates)

    hollow_out = _out(hollow_usd)
    new_metal_out = _out(curr_metal_per_m_usd)
    fair_out = _out(fair_usd)
    simple_out = _out(simple_total_usd)
    diff_out = _out(diff_usd)
    orig_total_out = _out(orig_total_usd)

    if any(v is None for v in (hollow_out, new_metal_out, fair_out, simple_out, diff_out)):
        st.error("Nelze převést výsledek do výstupní měny — chybí kurz.")
        return

    sym = output_currency
    st.markdown("<br>", unsafe_allow_html=True)
    r1, r2, r3 = st.columns(3)
    results = [
        (r1, "1. Dutá cena (fixní)", hollow_out, "Práce + plasty — nemění se"),
        (r2, "2. Nová přirážka za kov", new_metal_out, f"Aktuální burza ({exchange_currency}/t)"),
        (r3, "3. Férová cena za 1 m", fair_out, "Dutá + nový kov"),
    ]
    for col, title, val, hint in results:
        with col:
            st.markdown(
                f'<div class="calc-result">'
                f'<div class="calc-result-label">{title}</div>'
                f'<div class="calc-result-value">{format_num(val, 4)} {sym}</div>'
                f'<div style="font-family:IBM Plex Mono,monospace;font-size:0.65rem;'
                f'color:#6C757D;margin-top:4px;">{hint}</div></div>',
                unsafe_allow_html=True,
            )

    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown(
        f'<div class="info-box">'
        f'<strong>Původní nabídka:</strong> {format_num(orig_total_out, 4)} {sym}/m · '
        f'<strong>Růst burzy kovu:</strong> {metal_change_pct * 100:+.2f} %</div>',
        unsafe_allow_html=True,
    )
    c_simp, c_diff = st.columns(2)
    with c_simp:
        st.markdown(
            f'<div class="calc-result">'
            f'<div class="calc-result-label">Prostá přímá úměra (celá cena × růst burzy)</div>'
            f'<div class="calc-result-value">{format_num(simple_out, 4)} {sym}/m</div></div>',
            unsafe_allow_html=True,
        )
    with c_diff:
        color = "#10b981" if diff_out >= 0 else "#ef4444"
        sign = "+" if diff_out >= 0 else ""
        st.markdown(
            f'<div class="calc-result">'
            f'<div class="calc-result-label">Rozdíl: férová vs. prostá úměra</div>'
            f'<div class="calc-result-value" style="color:{color};">'
            f'{sign}{format_num(diff_out, 4)} {sym}/m</div>'
            f'<div style="font-family:IBM Plex Mono,monospace;font-size:0.65rem;'
            f'color:#6C757D;margin-top:4px;">'
            f'Kladné = férový model dražší než plošné zdražení celé nabídky</div></div>',
            unsafe_allow_html=True,
        )


def get_chart_period() -> str:
    """Aktuální yfinance period string z globálního přepínače."""
    return st.session_state.get("chart_period_yf", "3mo")


def get_chart_period_label() -> str:
    """Štítek období (1W, 1M, …) pro titulky grafů."""
    return st.session_state.get("chart_period_label", "3M")


def _shfe_vs_lme_spread_pct(shfe_usd: float, lme_usd: float) -> float | None:
    """SHFE oproti LME v % — (SHFE − LME) / LME × 100."""
    try:
        if lme_usd is None or shfe_usd is None or float(lme_usd) == 0:
            return None
        return (float(shfe_usd) - float(lme_usd)) / float(lme_usd) * 100.0
    except (TypeError, ValueError, ZeroDivisionError):
        return None


def get_shfe_china_usd(metal_key: str) -> tuple[float | None, dict | None, float | None]:
    """
    Čínská strana spreadu — spot ccmn.cn + přepočet CNY přes ČNB.
    Vrátí (USD/t, shfe dict, CNY/t).
    """
    shfe = fetch_ccmn_spot(metal_key)
    if not shfe or not shfe.get("price"):
        return None, None, None
    usd_per_cny = get_usd_per_cny()
    if not usd_per_cny:
        return None, shfe, shfe["price"]
    return shfe["price"] * usd_per_cny, shfe, shfe["price"]


def resolve_metal_price(
    metal_key: str,
    wm_data: dict | None,
) -> tuple[float | None, float | None, str]:
    """LME Cash cena USD/t — výhradně Westmetall (strict, bez zálohy)."""
    if not wm_data or metal_key not in wm_data:
        return None, None, ""
    info = wm_data[metal_key]
    if not isinstance(info, dict) or info.get("price") is None:
        return None, None, ""
    return float(info["price"]), None, "Westmetall"


def wm_stock_extra(wm_data: dict | None, stock_key: str) -> str | None:
    """Text LME zásob pro metric kartu."""
    if not wm_data:
        return None
    info = wm_data.get(stock_key)
    if isinstance(info, dict) and info.get("tons"):
        return f"LME zásoby: {format_num(int(info['tons']), 0)} t"
    return None


# ==============================================================================
# ─────────────────────────────────────────────────────────────────────────────
#  DATOVÉ FUNKCE – ROPA A PLASTY (proxy model)
# ─────────────────────────────────────────────────────────────────────────────
# ==============================================================================

_OIL_TICKERS = {
    "brent": ("BZ=F", "Brent Crude Oil"),
    "wti":   ("CL=F", "WTI Crude Oil"),
}


@st.cache_data(ttl=CACHE_TTL)
def fetch_oil_data() -> dict | None:
    """Ceny ropy Brent a WTI — sdílená cache s fetch_yf_spot."""
    result: dict = {}
    for key, (ticker, name) in _OIL_TICKERS.items():
        spot = fetch_yf_spot(ticker)
        if not spot:
            continue
        result[key] = {
            "price":     round(spot["price"], 2),
            "prev":      round(spot["prev"], 2),
            "delta":     round(spot["delta"], 2),
            "delta_pct": spot["delta_pct"],
            "unit":      "USD/bbl",
            "name":      name,
            "ticker":    ticker,
        }
    if result:
        result["_ts"] = now_prague().strftime("%Y-%m-%d %H:%M")
        return result
    return None


def calc_plastic_prices(brent_usd: float | None) -> dict | None:
    """
    Proxy model pro odhad cen plastů na základě ceny Brent ropy.

    Koeficienty jsou lineární aproximace historických vztahů:
        PVC  (kabelový granulát):  800 + 8.5  × Brent  [USD/t]
        XLPE (síťovaný polyetylen): 1200 + 14.0 × Brent  [USD/t]
        PA12 (nylonový plášť):     2500 + 20.0 × Brent  [USD/t]
        LLDPE (fólie/separátor):    900 + 10.0 × Brent  [USD/t]

    ⚠ Zpoždění trhů plastů za ropou: typicky 4–8 týdnů.
    """
    if brent_usd is None:
        return None
    try:
        b = float(brent_usd)
        return {
            "pvc":   {"price": round(800  + 8.5  * b, 0), "desc": "PVC Granulát (kabelový)"},
            "xlpe":  {"price": round(1200 + 14.0 * b, 0), "desc": "XLPE Granulát"},
            "pa12":  {"price": round(2500 + 20.0 * b, 0), "desc": "PA12 Plášť (Nylon)"},
            "lldpe": {"price": round(900  + 10.0 * b, 0), "desc": "LLDPE Separátor"},
            "_brent": b,
        }
    except (ValueError, TypeError):
        return None


def fetch_oil_history(period: str = "6mo") -> pd.DataFrame | None:
    """Historie Brent (BZ=F) oříznutá podle globálního období."""
    return filter_history_by_period(_yf_history("BZ=F"))


# ==============================================================================
# ─────────────────────────────────────────────────────────────────────────────
#  GRAFICKÉ FUNKCE (Plotly)
# ─────────────────────────────────────────────────────────────────────────────
# ==============================================================================

_PLOT_PAPER = "#FFFFFF"
_PLOT_BG = "#F8F9FA"
_PLOT_TITLE_COLOR = "#212529"
_PLOT_TICK_COLOR = "#000000"
_PLOT_GRID = "#DEE2E6"

_TICK_AXIS = dict(
    gridcolor=_PLOT_GRID,
    tickfont=dict(family="IBM Plex Mono, monospace", size=10, color=_PLOT_TICK_COLOR),
    showgrid=True,
    zeroline=False,
    showline=True,
    linecolor="#ADB5BD",
)

_HOVER_LABEL = dict(
    bgcolor="#FFFFFF",
    bordercolor="#495057",
    font=dict(family="IBM Plex Mono, monospace", size=11, color="#212529"),
)

# Mezera = tisíce, tečka = desetinná (český standard v Plotly)
_PLOT_SEPARATORS = " ."


def _chart_period_cutoff() -> pd.Timestamp:
    """Spodní hranice data podle globálního přepínače období (1W–1Y)."""
    days = _WM_PERIOD_DAYS.get(get_chart_period(), 92)
    prague_now = now_prague()
    return pd.Timestamp(prague_now.replace(tzinfo=None)).normalize() - pd.Timedelta(days=days)


def _ensure_plot_separators(fig: go.Figure | None) -> go.Figure | None:
    """Jednotné české formátování čísel na osách a v hoveru."""
    if fig is not None:
        fig.update_layout(separators=_PLOT_SEPARATORS)
    return fig


def _tight_yaxis_range(
    *series: pd.Series | list | None,
    padding_ratio: float = 0.15,
    min_relative_span: float = 0.003,
) -> tuple[float, float] | None:
    """
    Rozsah osy Y podle min/max dat (bez nuly), aby byly vidět denní výkyvy.
    Při téměř ploché křivce rozšíří rozsah kolem středu (min. podíl od střední hodnoty).
    """
    vals: list[float] = []
    for s in series:
        if s is None:
            continue
        arr = pd.Series(s).dropna().astype(float)
        if arr.empty:
            continue
        vals.extend(arr.tolist())
    if not vals:
        return None
    lo, hi = min(vals), max(vals)
    span = hi - lo
    mid = (hi + lo) / 2.0
    min_span = max(abs(mid) * min_relative_span, 1e-6)
    if span < min_span:
        lo, hi = mid - min_span / 2.0, mid + min_span / 2.0
        span = min_span
    pad = span * padding_ratio
    return lo - pad, hi + pad


def _history_to_dated_series(
    df: pd.DataFrame,
    value_col: str,
    date_col: str | None = "Date",
) -> pd.Series:
    """Normalizuje historii na Series (index = datum, hodnoty = float)."""
    if df is None or df.empty:
        return pd.Series(dtype=float)
    work = df.copy()
    if date_col and date_col in work.columns:
        dates = pd.to_datetime(work[date_col], errors="coerce").dt.normalize()
        values = pd.to_numeric(work[value_col], errors="coerce")
    else:
        work = work.reset_index()
        col0 = work.columns[0]
        dates = pd.to_datetime(work[col0], errors="coerce").dt.normalize()
        values = pd.to_numeric(work[value_col], errors="coerce")
    out = pd.Series(values.values, index=dates, name=value_col)
    out = out[out.index.notna()]
    out = out[~out.index.duplicated(keep="last")]
    return out.sort_index().dropna()


def _clip_series_to_chart_period(series: pd.Series) -> pd.Series:
    """Ořízne časovou řadu podle aktivního období v UI."""
    if series is None or series.empty:
        return pd.Series(dtype=float)
    cutoff = _chart_period_cutoff()
    idx = pd.to_datetime(series.index, errors="coerce").normalize()
    clipped = series.copy()
    clipped.index = idx
    return clipped[clipped.index >= cutoff].dropna()


def _apply_financial_y_axis(fig: go.Figure, df: pd.DataFrame, y_col: str) -> go.Figure:
    """Osa Y bez nuly — dynamický rozsah dle min/max zobrazených dat (+ malá rezerva)."""
    if df is None or df.empty or y_col not in df.columns:
        return fig
    series = pd.to_numeric(df[y_col], errors="coerce").dropna()
    if series.empty:
        return fig
    y_min, y_max = float(series.min()), float(series.max())
    if y_min == y_max:
        pad = max(abs(y_min) * 0.02, 1.0)
        y_min -= pad
        y_max += pad
    else:
        span = y_max - y_min
        pad = span * 0.06
        y_min -= pad
        y_max += pad
    fig.update_yaxes(
        autorange=False,
        range=[y_min, y_max],
        rangemode="normal",
        showgrid=True,
        zeroline=False,
        tickformat=",.2f",
    )
    return fig


def metal_price_history_figure(
    df: pd.DataFrame,
    title: str,
    color: str,
    y_col: str = "Close",
    y_label: str = "USD/t",
    height: int = 320,
) -> go.Figure | None:
    """Profesionální čárový graf ceny kovu (Plotly Express) s dynamickou osou Y."""
    if df is None or df.empty or y_col not in df.columns:
        return None

    plot_df = df.copy()
    if "Date" in plot_df.columns:
        plot_df["Date"] = pd.to_datetime(plot_df["Date"])
    plot_df = plot_df.sort_values("Date").reset_index(drop=True)

    fig = px.line(
        plot_df,
        x="Date",
        y=y_col,
        title=title,
        labels={"Date": "Datum", y_col: y_label},
    )
    fig.update_traces(
        line_color=color,
        line_width=2.5,
        hovertemplate=(
            f"<b>%{{x|%d.%m.%Y}}</b><br>{y_label}: %{{y:,.2f}}<extra></extra>"
        ),
    )
    fig.update_layout(
        separators=_PLOT_SEPARATORS,
        height=height,
        margin=dict(l=12, r=12, t=44, b=12),
        paper_bgcolor=_PLOT_PAPER,
        plot_bgcolor=_PLOT_BG,
        title=dict(
            text=title,
            font=dict(family="Syne, sans-serif", size=13, color=_PLOT_TITLE_COLOR),
            x=0.02,
            xanchor="left",
        ),
        showlegend=False,
        hovermode="x unified",
        hoverlabel=_HOVER_LABEL,
        xaxis=dict(**_TICK_AXIS, tickformat="%d.%m.%Y", title=None),
    )
    _apply_financial_y_axis(fig, plot_df, y_col)
    return fig


def _metal_history_table_df(
    df: pd.DataFrame,
    price_col: str = "Close",
    y_unit: str = "USD/t",
) -> pd.DataFrame:
    """Tabulka historie — nejnovější záznamy nahoře."""
    if df is None or df.empty:
        return pd.DataFrame()
    out = df.copy()
    if "Date" in out.columns:
        out["Date"] = pd.to_datetime(out["Date"])
        out = out.sort_values("Date", ascending=False)
    rename: dict[str, str] = {
        "Date": "Datum",
        price_col: f"Cena ({y_unit})",
    }
    if "Stock" in out.columns:
        rename["Stock"] = "Zásoby (t)"
    keep = [c for c in ["Date", "Stock", price_col] if c in out.columns]
    out = out[keep].rename(columns=rename)
    if "Datum" in out.columns:
        out["Datum"] = out["Datum"].dt.strftime("%d.%m.%Y")
    return out.reset_index(drop=True)


def _render_metal_history_with_tabs(
    df: pd.DataFrame | None,
    chart_title: str,
    color: str,
    y_unit: str,
    price_col: str = "Close",
    source_note: str = "",
    is_dual: bool = False,
) -> None:
    """Graf + surová data v záložkách pro jeden kov."""
    if df is None or df.empty:
        st.markdown(
            '<div class="error-box">Historická data nejsou k dispozici</div>',
            unsafe_allow_html=True,
        )
        return

    period_lbl = get_chart_period_label()
    graph_title = f"{chart_title} — {period_lbl}"
    if source_note:
        graph_title += f" · {source_note}"

    tab_chart, tab_table = st.tabs(["📈 Graf", "🗄️ Tabulka dat"])

    with tab_chart:
        if is_dual:
            fig = interactive_metal_dual_chart(df, graph_title, color, y_unit)
        else:
            fig = metal_price_history_figure(
                df,
                graph_title,
                color,
                price_col,
                y_unit,
            )
        if fig:
            _ensure_plot_separators(fig)
            st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": True})
        else:
            st.markdown('<div class="error-box">Graf nelze vykreslit</div>', unsafe_allow_html=True)

    with tab_table:
        table_df = _metal_history_table_df(df, price_col, y_unit)
        price_label = f"Cena ({y_unit})"
        col_config = {
            "Datum": st.column_config.TextColumn("Datum", width="medium"),
        }
        if price_label in table_df.columns or "Zásoby (t)" in table_df.columns:
            table_df = table_df.copy()
        if price_label in table_df.columns:
            table_df[price_label] = table_df[price_label].apply(
                lambda x: format_num(x, 2) if pd.notna(x) else "N/A"
            )
            col_config[price_label] = st.column_config.TextColumn(price_label, width="medium")
        if "Zásoby (t)" in table_df.columns:
            table_df["Zásoby (t)"] = table_df["Zásoby (t)"].apply(
                lambda x: format_num(x, 0) if pd.notna(x) else "N/A"
            )
            col_config["Zásoby (t)"] = st.column_config.TextColumn("Zásoby (t)", width="medium")
        st.dataframe(
            table_df,
            use_container_width=True,
            hide_index=True,
            column_config=col_config,
        )


def interactive_line_chart(
    df: pd.DataFrame,
    title: str,
    color: str = "#3b82f6",
    y_label: str = "",
    height: int = 300,
    y_column: str = "Close",
    extra_traces: list[dict] | None = None,
    show_legend: bool = False,
    tight_yaxis: bool = False,
    y_tickformat: str | None = None,
) -> go.Figure | None:
    """
    Interaktivní čárový graf (plotly.graph_objects) s volitelnými dalšími řadami.
    extra_traces: [{"y": Series/array, "name": str, "color": str, "dash": "solid"|"dot"|...}]
    tight_yaxis: osa Y jen kolem dat (vhodné pro FX — výkyvy v tisícinách).
    """
    if df is None or df.empty or y_column not in df.columns:
        return None

    x_data = df["Date"] if "Date" in df.columns else df.index
    fig = go.Figure()

    r, g, b = int(color[1:3], 16), int(color[3:5], 16), int(color[5:7], 16)
    scatter_fill: str | None = "tozeroy"
    scatter_fillcolor = f"rgba({r},{g},{b},0.08)"
    if tight_yaxis:
        scatter_fill = None
        scatter_fillcolor = None

    fig.add_trace(go.Scatter(
        x=x_data,
        y=df[y_column],
        mode="lines",
        name=title.split("—")[0].strip() if "—" in title else "Cena",
        line=dict(color=color, width=2.2, shape="spline", smoothing=0.8),
        fill=scatter_fill,
        fillcolor=scatter_fillcolor,
        hovertemplate=f"<b>%{{x|%d.%m.%Y}}</b><br>{y_label}: %{{y:,.4f}}<extra></extra>",
    ))

    if extra_traces:
        for tr in extra_traces:
            fig.add_trace(go.Scatter(
                x=x_data,
                y=tr["y"],
                mode="lines",
                name=tr.get("name", ""),
                line=dict(
                    color=tr.get("color", "#94a3b8"),
                    width=tr.get("width", 1.8),
                    dash=tr.get("dash", "dot"),
                ),
                hovertemplate=f"<b>%{{x|%d.%m.%Y}}</b><br>{tr.get('name', '')}: %{{y:,.4f}}<extra></extra>",
            ))

    y_series = [df[y_column]]
    if extra_traces:
        y_series.extend(tr.get("y") for tr in extra_traces)
    y_range = _tight_yaxis_range(*y_series) if tight_yaxis else None
    default_tick = ",.4f" if tight_yaxis else ",.2f"
    yaxis_layout = dict(**_TICK_AXIS, tickformat=y_tickformat or default_tick)
    if y_range is not None:
        yaxis_layout["range"] = list(y_range)

    fig.update_layout(
        separators=_PLOT_SEPARATORS,
        title=dict(text=title, font=dict(family="Syne, sans-serif", size=13, color=_PLOT_TITLE_COLOR), y=0.97),
        height=height,
        margin=dict(l=10, r=10, t=42 if show_legend else 36, b=12),
        paper_bgcolor=_PLOT_PAPER,
        plot_bgcolor=_PLOT_BG,
        showlegend=show_legend,
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.08,
            xanchor="right",
            x=1,
            font=dict(family="IBM Plex Mono, monospace", size=10, color=_PLOT_TICK_COLOR),
            bgcolor=_PLOT_PAPER,
        ) if show_legend else None,
        xaxis=dict(**_TICK_AXIS, tickformat="%b %y"),
        yaxis=yaxis_layout,
        hoverlabel=_HOVER_LABEL,
        hovermode="x unified",
    )
    return fig


def interactive_metal_dual_chart(
    df: pd.DataFrame,
    title: str,
    price_color: str = "#f97316",
    y_price_label: str = "USD/t",
    height: int = 320,
) -> go.Figure | None:
    """
    Graf LME Cash-Settlement (osa Y vlevo) + LME Stock (osa Y vpravo).
    Obě osy jsou dynamicky oříznuty na min/max s 2% rezervou.
    """
    if df is None or df.empty or "Close" not in df.columns:
        return None

    x_data = df["Date"]
    r, g, b = int(price_color[1:3], 16), int(price_color[3:5], 16), int(price_color[5:7], 16)
    fig = go.Figure()

    # 1. Výpočet limitů pro cenu (vyhneme se chybám s NaN hodnotami)
    price_s = pd.to_numeric(df["Close"], errors="coerce").dropna()
    if price_s.empty:
        return None
    p_min, p_max = float(price_s.min()), float(price_s.max())
    p_pad = (p_max - p_min) * 0.02 if p_max > p_min else p_max * 0.02
    if p_pad == 0:
        p_pad = 1.0

    # 2. Vykreslení křivky ceny (LME Cash-Settlement)
    fig.add_trace(go.Scatter(
        x=x_data,
        y=df["Close"],
        mode="lines",
        name="LME Cash-Settlement",
        yaxis="y",
        line=dict(color=price_color, width=2.2, shape="spline", smoothing=0.8),
        fill="tozeroy",
        fillcolor=f"rgba({r},{g},{b},0.08)",
        hovertemplate=(
            f"<b>%{{x|%d.%m.%Y}}</b><br>{y_price_label}: %{{y:,.2f}}<extra></extra>"
        ),
    ))

    # 3. Zpracování limitů a křivky pro zásoby (LME Stock)
    has_stock = "Stock" in df.columns and df["Stock"].notna().any()
    y2_axis = None
    if has_stock:
        stock_s = pd.to_numeric(df["Stock"], errors="coerce").dropna()
        s_min, s_max = float(stock_s.min()), float(stock_s.max())
        s_pad = (s_max - s_min) * 0.02 if s_max > s_min else s_max * 0.02
        if s_pad == 0:
            s_pad = 100.0

        fig.add_trace(go.Scatter(
            x=x_data,
            y=df["Stock"],
            mode="lines",
            name="LME Stock",
            yaxis="y2",
            line=dict(color="#94a3b8", width=1.8, dash="dot"),
            hovertemplate="<b>%{x|%d.%m.%Y}</b><br>Zásoby: %{y:,.0f} t<extra></extra>",
        ))

        y2_axis = dict(
            title=dict(text="Zásoby (t)", font=dict(size=10, color=_PLOT_TITLE_COLOR)),
            overlaying="y",
            side="right",
            showgrid=False,
            tickfont=dict(family="IBM Plex Mono, monospace", size=10, color=_PLOT_TICK_COLOR),
            tickformat=",.0f",
            range=[s_min - s_pad, s_max + s_pad],
            autorange=False,
        )

    # 4. Sestavení finálního layoutu s pevnými limity
    fig.update_layout(
        separators=_PLOT_SEPARATORS,
        title=dict(text=title, font=dict(family="Syne, sans-serif", size=13, color=_PLOT_TITLE_COLOR), y=0.98),
        height=height,
        margin=dict(l=10, r=10, t=48, b=12),
        paper_bgcolor=_PLOT_PAPER,
        plot_bgcolor=_PLOT_BG,
        showlegend=True,
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.1,
            xanchor="right",
            x=1,
            font=dict(family="IBM Plex Mono, monospace", size=10, color=_PLOT_TICK_COLOR),
            bgcolor=_PLOT_PAPER,
        ),
        xaxis=dict(**_TICK_AXIS, tickformat="%b %y"),
        yaxis=dict(
            **_TICK_AXIS,
            tickformat=",.0f",
            title=dict(text=y_price_label, standoff=8),
            range=[p_min - p_pad, p_max + p_pad],
            autorange=False,
        ),
        yaxis2=y2_axis,
        hoverlabel=_HOVER_LABEL,
        hovermode="x unified",
    )
    return fig


def _render_wm_metal_history_chart(
    metal_key: str,
    chart_title: str,
    color: str,
) -> None:
    """Vykreslí westmetall historii mědi/hliníku nebo zobrazí chybu."""
    period_lbl = get_chart_period_label()
    ccy = get_display_currency()
    y_unit = f"{ccy}/t"
    url = WM_HISTORY_URLS[metal_key]

    full = fetch_westmetall_history(url)
    if full is None:
        st.warning("Chyba načítání dat z Westmetallu")
        st.markdown(
            '<div class="error-box">Chyba načítání dat z Westmetallu</div>',
            unsafe_allow_html=True,
        )
        return

    hist = filter_wm_history_by_period(full)
    if hist is None or hist.empty:
        st.warning("Chyba načítání dat z Westmetallu")
        st.markdown(
            '<div class="error-box">Chyba načítání dat z Westmetallu</div>',
            unsafe_allow_html=True,
        )
        return

    if ccy == "EUR" and not get_eurusd_rate():
        st.warning("Chyba načítání dat z Westmetallu — chybí kurz EUR/USD pro přepočet.")
        st.markdown(
            '<div class="error-box">Chyba načítání dat z Westmetallu</div>',
            unsafe_allow_html=True,
        )
        return

    plot = apply_currency_to_df(hist.copy())
    _render_metal_history_with_tabs(
        plot,
        chart_title,
        color,
        y_unit,
        price_col="Close",
        source_note="Westmetall",
        is_dual=True,
    )


def interactive_oil_chart(
    df: pd.DataFrame,
    title: str,
    color: str = "#f59e0b",
    height: int = 300,
) -> go.Figure | None:
    """Brent graf s historickou cenou a 30denním klouzavým průměrem (trend)."""
    if df is None or df.empty:
        return None
    plot_df = df.copy()
    plot_df["SMA30"] = plot_df["Close"].rolling(window=30, min_periods=1).mean()
    return interactive_line_chart(
        plot_df,
        title,
        color=color,
        y_label=oil_unit_label(),
        height=height,
        extra_traces=[{
            "y": plot_df["SMA30"],
            "name": "SMA 30d (trend)",
            "color": "#94a3b8",
            "dash": "dot",
            "width": 2.0,
        }],
        show_legend=True,
    )


_LME_SHFE_SPOT_COMPARE: list[tuple[str, str]] = [
    ("copper", "Copper"),
    ("aluminum", "Aluminum"),
]


def lme_shfe_spot_comparison_figure(wm_data: dict | None) -> go.Figure | None:
    """Vodorovný graf — LME vs CCMN aktuální cena (USD/t); jen kovy s oběma zdroji."""
    labels: list[str] = []
    prices: list[float] = []
    colors: list[str] = []

    for metal_key, metal_label in _LME_SHFE_SPOT_COMPARE:
        lme_usd, _, _ = resolve_metal_price(metal_key, wm_data)
        shfe_usd, _, _ = get_shfe_china_usd(metal_key)
        if (
            lme_usd is None
            or shfe_usd is None
            or float(lme_usd) <= 0
            or float(shfe_usd) <= 0
        ):
            continue
        labels.append(f"{metal_label} — LME")
        prices.append(float(lme_usd))
        colors.append("#0D6EFD")
        labels.append(f"{metal_label} — CCMN")
        prices.append(float(shfe_usd))
        colors.append("#FD7E14")

    if not labels:
        return None

    fig = go.Figure(
        go.Bar(
            y=labels,
            x=prices,
            orientation="h",
            marker=dict(color=colors, line_width=0),
            text=[f" {format_num(p, 0)} USD/t" for p in prices],
            textposition="outside",
            textfont=dict(family="IBM Plex Mono, monospace", size=9.5, color=_PLOT_TITLE_COLOR),
            hovertemplate="<b>%{y}</b><br>%{x:,.0f} USD/t<extra></extra>",
        )
    )
    fig.update_layout(
        separators=_PLOT_SEPARATORS,
        title=dict(
            text="Porovnání LME vs CCMN (Čína) — aktuální ceny (USD/t)",
            font=dict(family="Syne, sans-serif", size=13, color=_PLOT_TITLE_COLOR),
        ),
        height=max(180, 52 * len(labels)),
        margin=dict(l=10, r=10, t=36, b=12),
        paper_bgcolor=_PLOT_PAPER,
        plot_bgcolor=_PLOT_BG,
        showlegend=False,
        xaxis=dict(
            gridcolor=_PLOT_GRID,
            tickfont=dict(family="IBM Plex Mono, monospace", size=10, color=_PLOT_TICK_COLOR),
            tickformat=",.0f",
            showgrid=True,
            zeroline=False,
            title="USD/t",
        ),
        yaxis=dict(
            tickfont=dict(family="Syne, sans-serif", size=10, color=_PLOT_TICK_COLOR),
            showgrid=False,
        ),
        bargap=0.28,
        hoverlabel=_HOVER_LABEL,
    )
    return fig


def _render_lme_shfe_spot_comparison(wm_data: dict | None) -> None:
    """Tabulka + graf: LME a CCMN ceny mědi a hliníku v USD/t (bez oceli)."""
    table_rows: list[dict[str, str]] = []

    for metal_key, metal_label in _LME_SHFE_SPOT_COMPARE:
        lme_str = "N/A"
        shfe_str = "N/A"
        diff_str = "N/A"
        pct_str = "N/A"
        lme_usd: float | None = None
        shfe_usd: float | None = None
        try:
            lme_usd, _, _ = resolve_metal_price(metal_key, wm_data)
            if lme_usd is not None:
                lme_str = format_num(lme_usd, 0)
        except Exception:
            pass
        try:
            shfe_usd, _, _ = get_shfe_china_usd(metal_key)
            if shfe_usd is not None:
                shfe_str = format_num(shfe_usd, 0)
        except Exception:
            pass
        if lme_usd is not None and shfe_usd is not None:
            diff_usd = shfe_usd - lme_usd
            diff_str = f"{diff_usd:+,.0f}".replace(",", " ")
            spread_pct = _shfe_vs_lme_spread_pct(shfe_usd, lme_usd)
            if spread_pct is not None:
                pct_str = f"{spread_pct:+.1f} %"
        if lme_str != "N/A" or shfe_str != "N/A":
            table_rows.append(
                {
                    "Kov": metal_label,
                    "LME (Londýn) [USD/t]": lme_str,
                    "CCMN (Changjiang Spot) [USD/t]": shfe_str,
                    "Rozdíl CCMN−LME [USD/t]": diff_str,
                    "Rozdíl vůči LME [%]": pct_str,
                }
            )

    if not table_rows:
        st.markdown(
            '<div class="error-box" style="padding:10px;">'
            "Porovnání LME vs CCMN (Čína) — aktuální ceny nejsou k dispozici."
            "</div>",
            unsafe_allow_html=True,
        )
        return

    st.markdown(
        "<div style='font-family:Syne,sans-serif;font-size:0.75rem;font-weight:700;"
        "color:#495057;text-transform:uppercase;letter-spacing:1px;margin-bottom:8px;'>"
        "Aktuální ceny LME vs CCMN (Čína) (USD/t)</div>",
        unsafe_allow_html=True,
    )
    st.dataframe(
        pd.DataFrame(table_rows),
        use_container_width=True,
        hide_index=True,
        column_config={
            "Kov": st.column_config.TextColumn("Kov", width="small"),
            "LME (Londýn) [USD/t]": st.column_config.TextColumn("LME (Londýn) [USD/t]"),
            "CCMN (Changjiang Spot) [USD/t]": st.column_config.TextColumn(
                "CCMN (Changjiang Spot) [USD/t]"
            ),
            "Rozdíl CCMN−LME [USD/t]": st.column_config.TextColumn("Rozdíl CCMN−LME [USD/t]"),
            "Rozdíl vůči LME [%]": st.column_config.TextColumn("Rozdíl vůči LME [%]"),
        },
    )

    fig = lme_shfe_spot_comparison_figure(wm_data)
    if fig is not None:
        st.markdown("<br>", unsafe_allow_html=True)
        _ensure_plot_separators(fig)
        _show_plotly(fig, toolbar=False)
        st.caption(
            "LME: Westmetall Cash · CCMN: ccmn.cn spot + přepočet CNY→USD (ČNB) · vše v USD/t"
        )


def bar_metals(
    data: dict,
    title: str | None = None,
    currency: str | None = None,
) -> go.Figure | None:
    """
    Vodorovný sloupcový graf pro vizuální porovnání cen kovů.
    """
    currency = currency or get_display_currency()
    if title is None:
        title = f"Porovnání LME cen kovů ({currency}/t)"
    color_map = {
        "copper":   "#f97316",
        "aluminum": "#10b981",
        "steel":    "#64748b",
    }
    metals, prices, colors = [], [], []
    for key, label in _BAR_CHART_ORDER:
        v = data.get(key)
        if isinstance(v, dict) and "price" in v and float(v["price"]) > 0:
            metals.append(label)
            prices.append(float(v["price"]))
            colors.append(color_map.get(key, "#475569"))
    if not metals:
        return None

    fig = go.Figure(go.Bar(
        y=metals,
        x=prices,
        orientation="h",
        marker=dict(color=colors, line_width=0),
        text=[f" {format_num(p, 0)} {currency}/t" for p in prices],
        textposition="outside",
        textfont=dict(family="IBM Plex Mono, monospace", size=9.5, color=_PLOT_TITLE_COLOR),
        hovertemplate=f"<b>%{{y}}</b><br>%{{x:,.0f}} {currency}/t<extra></extra>",
    ))
    fig.update_layout(
        separators=_PLOT_SEPARATORS,
        title=dict(text=title, font=dict(family="Syne, sans-serif", size=13, color=_PLOT_TITLE_COLOR)),
        height=220,
        margin=dict(l=10, r=10, t=36, b=12),
        paper_bgcolor=_PLOT_PAPER,
        plot_bgcolor=_PLOT_BG,
        showlegend=False,
        xaxis=dict(
            gridcolor=_PLOT_GRID,
            tickfont=dict(family="IBM Plex Mono, monospace", size=10, color=_PLOT_TICK_COLOR),
            tickformat=",.0f",
            showgrid=True,
            zeroline=False,
        ),
        yaxis=dict(
            tickfont=dict(family="Syne, sans-serif", size=10, color=_PLOT_TICK_COLOR),
            showgrid=False,
        ),
        bargap=0.35,
        hoverlabel=_HOVER_LABEL,
    )
    return fig


# ==============================================================================
# ─────────────────────────────────────────────────────────────────────────────
#  HLAVNÍ RENDEROVACÍ FUNKCE
# ─────────────────────────────────────────────────────────────────────────────
# ==============================================================================

def render_header() -> None:
    """Vykreslí animované záhlaví dashboardu."""
    now = now_prague()
    st.markdown(f"""
    <div class="dash-header">
        <div class="dash-header-content">
            <div>
                <div class="dash-title">
                    <span>⚡</span> Kabelářský dashboard
                </div>
                <div class="dash-subtitle">
                    Cable Industry Procurement Intelligence Platform
                </div>
            </div>
            <div class="dash-meta">
                <div class="dash-timestamp">
                    <strong>Poslední aktualizace</strong> (CET)<br>
                    {now.strftime("%d.%m.%Y %H:%M:%S")}<br>
                    Cache TTL: <strong>1 hod</strong>
                </div>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # Refresh tlačítko
    c1, c2 = st.columns([1, 6])
    with c1:
        if st.button("🔄  Obnovit data", use_container_width=True):
            st.cache_data.clear()
            st.rerun()
    with c2:
        st.markdown(
            '<div style="padding:8px 0;font-family:\'IBM Plex Mono\',monospace;'
            'font-size:0.7rem;color:#495057;">'
            'Data se automaticky obnovují každou hodinu · '
            'Všechny ceny jsou orientační · Žádné placené API</div>',
            unsafe_allow_html=True,
        )


def render_global_controls() -> tuple[str, str]:
    """Globální přepínač měny (USD/EUR) a období grafů (1W–1Y)."""
    if "display_currency" not in st.session_state:
        st.session_state.display_currency = "USD"
    if "chart_period_yf" not in st.session_state:
        st.session_state.chart_period_yf = "3mo"
        st.session_state.chart_period_label = "3M"

    eurusd = get_eurusd_rate()
    if st.session_state.display_currency == "EUR" and not eurusd:
        st.warning(
            "Přepočet na EUR není k dispozici — chybí živý kurz EUR/USD z Yahoo Finance. "
            "Ceny v EUR se zobrazí jako N/A."
        )

    st.markdown('<div class="currency-bar">', unsafe_allow_html=True)
    c_cur, c_per, c_info = st.columns([1.6, 2.4, 2.8])
    with c_cur:
        st.markdown(
            '<div class="currency-bar-label">Zobrazovací měna</div>',
            unsafe_allow_html=True,
        )
        choice = st.segmented_control(
            "Měna",
            options=["USD", "EUR"],
            default=st.session_state.display_currency,
            key="global_currency_seg",
            label_visibility="collapsed",
        )
        if choice:
            st.session_state.display_currency = choice
    with c_per:
        st.markdown(
            '<div class="currency-bar-label">Období grafů</div>',
            unsafe_allow_html=True,
        )
        period_labels = list(CHART_PERIODS.keys())
        p_choice = st.segmented_control(
            "Období",
            options=period_labels,
            default=st.session_state.chart_period_label,
            key="global_period_seg",
            label_visibility="collapsed",
        )
        if p_choice:
            st.session_state.chart_period_label = p_choice
            st.session_state.chart_period_yf = CHART_PERIODS[p_choice]
    with c_info:
        rate_txt = (
            f"EUR/USD (Yahoo): <strong style='color:#0D6EFD;'>{eurusd:.4f}</strong>"
            if eurusd
            else "EUR/USD: <strong style='color:#ef4444;'>nedostupný</strong>"
        )
        st.markdown(
            f'<div class="currency-bar-hint">{rate_txt}<br>'
            f'LME Cash, zásoby &amp; historie měď/hliník: <strong>Westmetall</strong> · '
            f'Kurzy CZK: <strong>ČNB</strong> · ostatní grafy: <strong>Yahoo</strong></div>',
            unsafe_allow_html=True,
        )
    st.markdown("</div>", unsafe_allow_html=True)
    return st.session_state.display_currency, st.session_state.chart_period_yf


# ──────────────────────────────────────────────────────────────────────────────
#  SEKCE 1: METALY
# ──────────────────────────────────────────────────────────────────────────────

def render_metals() -> None:
    """Sekce 1 – LME kovy, ocel HRC, spot CCMN vs LME, historie Westmetall."""

    wm_data = fetch_westmetall()
    steel_hrc = fetch_steel_yfinance()
    period = get_chart_period()
    period_lbl = get_chart_period_label()

    has_cu = wm_data and "copper" in wm_data
    has_al = wm_data and "aluminum" in wm_data

    section_header(
        "🔩", "Metaly — LME, Ocel & SHFE",
        badge_html(has_cu and has_al, "westmetall.com LME Cash"),
        badge_html(steel_hrc is not None, "Yahoo HRC"),
    )

    if not wm_data:
        st.warning("Westmetall: LME data se nepodařilo stáhnout — ceny mědi a hliníku nejsou k dispozici.")

    ccy = get_display_currency()
    col_cu, col_al, col_hrc = st.columns(3)
    cu_cfg, al_cfg = _LME_METAL_CARDS
    with col_cu:
        _render_lme_metal_card(cu_cfg[0], cu_cfg[1], cu_cfg[2], cu_cfg[3], wm_data)
    with col_al:
        _render_lme_metal_card(al_cfg[0], al_cfg[1], al_cfg[2], al_cfg[3], wm_data)
    with col_hrc:
        _render_steel_metric_card(steel_hrc, "Ocel HRC", "HRC=F")

    with st.expander(
        "🧮 Profesionální kabelářská kalkulačka (Metal Surcharge)",
        expanded=False,
    ):
        render_metal_surcharge_calculator(fetch_cnb_rates())

    st.markdown("<br>", unsafe_allow_html=True)
    render_rsi_signals(steel_hrc)
    st.markdown("<br>", unsafe_allow_html=True)

    # ── Historické grafy — měď & hliník (Westmetall), ocel HRC (Yahoo) ────────
    st.markdown(
        "<div style='font-family:Syne,sans-serif;font-size:0.75rem;font-weight:700;"
        "color:#495057;text-transform:uppercase;letter-spacing:1px;margin-bottom:8px;'>"
        f"Historické grafy — Měď & Hliník (Westmetall, {period_lbl}) · "
        f"Ocel HRC (Yahoo, {ccy}/t)</div>",
        unsafe_allow_html=True,
    )
    col_cu_hist, col_al_hist, col_st_hist = st.columns(3)
    y_unit = f"{ccy}/t"
    steel_ticker = (steel_hrc or {}).get("ticker", "HRC=F")

    with col_cu_hist:
        _render_wm_metal_history_chart("copper", "Měď (Cu)", "#f97316")

    with col_al_hist:
        _render_wm_metal_history_chart("aluminum", "Hliník (Al)", "#10b981")

    with col_st_hist:
        st_hist = fetch_metal_history(steel_ticker, period)
        if st_hist is not None and not st_hist.empty:
            st_plot = st_hist.copy()
            st_plot["Close"] = st_plot["Close"] * _ST_TON_FACTOR
            st_plot = apply_currency_to_df(st_plot)
            _render_metal_history_with_tabs(
                st_plot,
                "Ocel HRC",
                "#64748b",
                y_unit,
                price_col="Close",
                source_note=f"Yahoo {steel_ticker}",
            )
        else:
            st.markdown(
                '<div class="error-box">Graf oceli HRC momentálně nedostupný (Yahoo HRC=F / STRE=F)</div>',
                unsafe_allow_html=True,
            )

    st.markdown("<br>", unsafe_allow_html=True)

    # ── SHFE spread panel ─────────────────────────────────────────────────────
    col_spread_full, _ = st.columns([1, 2])
    with col_spread_full:
        _render_shfe_spreads(wm_data)

    # ── Aktuální ceny LME vs CCMN (měď, hliník — USD/t, bez oceli) ───────────
    st.markdown("<br>", unsafe_allow_html=True)
    _render_lme_shfe_spot_comparison(wm_data)

    if wm_data and wm_data.get("_source") == "westmetall.com":
        st.markdown(
            f'<div class="info-box">'
            f'📦 <strong>Westmetall</strong> LME Cash &amp; skladové zásoby · '
            f'Načteno: <strong>{wm_data.get("_ts", "N/A")}</strong></div>',
            unsafe_allow_html=True,
        )

    st.markdown('<div class="section-divider"></div>', unsafe_allow_html=True)


def _render_shfe_spread_item(metal_key: str, metal_name: str, wm_data: dict | None) -> None:
    """Jedna spread karta CCMN (Čína) vs LME."""
    ccy = get_display_currency()
    lme_usd, _, _ = resolve_metal_price(metal_key, wm_data)
    china_usd, _, cny_price = get_shfe_china_usd(metal_key)

    if china_usd is not None and lme_usd is not None:
        spread_usd = china_usd - lme_usd
        spread_disp = usd_to_display(spread_usd, ccy)
        lme_disp = usd_to_display(lme_usd, ccy)
        china_disp = usd_to_display(china_usd, ccy)
        if spread_disp is None or lme_disp is None or china_disp is None:
            st.markdown(
                f'<div class="spread-card"><div class="spread-label">{metal_name}: CCMN (Čína) vs LME</div>'
                f'<div class="error-box" style="margin-top:6px;">N/A — chybí kurz EUR/USD</div></div>',
                unsafe_allow_html=True,
            )
            return
        s_color = "#10b981" if spread_usd >= 0 else "#ef4444"
        s_sign = "+" if spread_usd >= 0 else ""
        spread_pct = _shfe_vs_lme_spread_pct(china_usd, lme_usd)
        pct_html = ""
        if spread_pct is not None:
            pct_sign = "+" if spread_pct >= 0 else ""
            pct_html = (
                f' <span style="font-size:0.85rem;font-weight:600;">'
                f"({pct_sign}{spread_pct:.1f} % vůči LME)</span>"
            )
        st.markdown(
            f"<div style='margin-bottom:6px;'>{badge_html(True, 'ccmn.cn (Spot)')}</div>"
            f'<div class="spread-card"><div class="spread-label">{metal_name}: CCMN (Čína) vs LME</div>'
            f'<div class="spread-value" style="color:{s_color};">'
            f"{s_sign}{format_num(spread_disp, 0)} {ccy}/t{pct_html}</div>"
            f'<div class="spread-details">CCMN: {format_num(cny_price, 0)} CNY/t (≈ {format_num(china_disp, 0)} {ccy}/t)<br>'
            f"LME Cash (Westmetall): {format_num(lme_disp, 0)} {ccy}/t</div></div>",
            unsafe_allow_html=True,
        )
        return

    missing = []
    if lme_usd is None:
        missing.append("LME Cash (Westmetall)")
    if china_usd is None:
        missing.append("ccmn.cn (spot) nebo kurz CNY (ČNB)")
    st.markdown(
        f'<div class="spread-card"><div class="spread-label">{metal_name}: CCMN (Čína) vs LME</div>'
        f'<div class="error-box" style="margin-top:6px;">Data nedostupná — {", ".join(missing)}</div></div>',
        unsafe_allow_html=True,
    )


def _render_shfe_spreads(wm_data: dict | None) -> None:
    """CCMN (Čína) vs LME spread — živá data (ccmn.cn + ČNB + Westmetall)."""
    ccy = get_display_currency()
    st.markdown(
        f"<div style='margin-bottom:10px;'>"
        f"<span style='font-family:Syne,sans-serif;font-size:0.7rem;font-weight:700;"
        f"color:#495057;text-transform:uppercase;letter-spacing:1px;'>"
        f"CCMN (Čína) vs LME Spread ({ccy}/t)</span></div>",
        unsafe_allow_html=True,
    )
    if not get_usd_per_cny():
        st.warning(
            "Spread: chybí kurz CNY z ČNB — přepočet CCMN (CNY/t) na USD/EUR nelze spočítat."
        )
    for metal_key, metal_name in _SHFE_SPREAD_METALS:
        _render_shfe_spread_item(metal_key, metal_name, wm_data)


# ──────────────────────────────────────────────────────────────────────────────
#  SEKCE 2: MĚNY (FX)
# ──────────────────────────────────────────────────────────────────────────────

def render_fx() -> None:
    """Sekce 2 – ČNB kurzy v kartách, Yahoo pro grafy a křížové EUR/USD."""

    cnb = fetch_cnb_rates()
    cnb_live = cnb is not None

    section_header(
        "💱", "Měnové Kurzy — ČNB & Křížové",
        badge_html(cnb_live, "ČNB"),
        badge_html(True, "Yahoo grafy"),
    )

    if not cnb_live:
        st.warning("ČNB: kurzovní lístek se nepodařilo načíst — karty CZK párů budou nedostupné.")
    elif "CNY" not in cnb:
        st.warning(
            "ČNB: v denním kurzovním lístku chybí kód CNY — kurz CNY/CZK nelze zobrazit."
        )

    period = get_chart_period()
    period_lbl = get_chart_period_label()

    st.markdown(
        f'<div class="info-box">'
        f'Karty CZK párů: oficiální kurzovní lístek <strong>ČNB</strong>'
        f'{f" ze dne {cnb.get('_date', 'N/A')}" if cnb else ""} · '
        f'Historické grafy ({period_lbl}) a křížové kurzy: <strong>Yahoo Finance</strong> · '
        f'CNY/CZK graf: CNYCZK=X nebo odvozeno USDCZK×CNYUSD'
        f'</div>',
        unsafe_allow_html=True,
    )

    eur_usd_spot = fetch_yf_spot("EURUSD=X")
    cols = st.columns(5)

    for (code, pair, subtitle, cls), col in zip(_CNB_METRIC_CARDS, cols[:3]):
        with col:
            info = (cnb or {}).get(code)
            if info:
                st.markdown(
                    metric_card(pair, f"{info['rate']:.4f}", subtitle, card_class=cls),
                    unsafe_allow_html=True,
                )
            else:
                st.markdown(error_card(pair, cls, "Data nedostupná · ČNB"), unsafe_allow_html=True)

    with cols[3]:
        if eur_usd_spot and eur_usd_spot["price"]:
            st.markdown(
                metric_card(
                    "EUR/USD", f"{eur_usd_spot['price']:.4f}", "Euro / USD (Yahoo)",
                    delta=eur_usd_spot.get("delta"), delta_suffix="",
                    card_class="card-eur",
                ),
                unsafe_allow_html=True,
            )
        else:
            st.markdown(error_card("EUR/USD", "card-eur", "Kurz nedostupný"), unsafe_allow_html=True)

    with cols[4]:
        if eur_usd_spot and eur_usd_spot["price"]:
            usd_eur = 1.0 / eur_usd_spot["price"]
            prev_usd_eur = 1.0 / eur_usd_spot["prev"] if eur_usd_spot["prev"] else usd_eur
            st.markdown(
                metric_card(
                    "USD/EUR", f"{usd_eur:.4f}", "Dolar / Euro (Yahoo)",
                    delta=usd_eur - prev_usd_eur, delta_suffix="",
                    card_class="card-usd",
                ),
                unsafe_allow_html=True,
            )
        else:
            st.markdown(error_card("USD/EUR", "card-usd", "Kurz nedostupný"), unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # ── Interaktivní grafy (globální období, Yahoo) ───────────────────────────
    fx_charts = [
        ("CNY/CZK", "#ef4444", "CZK", "cny"),
        ("EUR/CZK", "#3b82f6", "CZK", "eur"),
        ("USD/CZK", "#22c55e", "CZK", "usd"),
        ("EUR/USD", "#8b5cf6", "USD", "eurusd"),
    ]
    col_a, col_b = st.columns(2)
    chart_cols = [col_a, col_b, col_a, col_b]

    for (pair, color, unit, kind), col in zip(fx_charts, chart_cols):
        with col:
            derived = False
            if kind == "cny":
                hist, derived = fetch_cny_czk_history(period)
            elif kind == "eur":
                hist = fetch_fx_history("EURCZK=X", period)
            elif kind == "usd":
                hist = fetch_fx_history("USDCZK=X", period)
            else:
                hist = fetch_fx_history("EURUSD=X", period)
            if hist is not None and not hist.empty:
                sub = " · odvozeno USDCZK×CNYUSD" if kind == "cny" and derived else ""
                fig = interactive_line_chart(
                    hist,
                    f"{pair} — {period_lbl}{sub}",
                    color,
                    unit,
                    tight_yaxis=True,
                )
                if fig:
                    _show_plotly(fig)
            else:
                st.markdown(
                    f'<div class="error-box">Graf {pair} — data nedostupná (Yahoo)</div>',
                    unsafe_allow_html=True,
                )

    # USD/EUR graf (inverze EUR/USD historie)
    st.markdown("<br>", unsafe_allow_html=True)
    hist_eu = fetch_fx_history("EURUSD=X", period)
    if hist_eu is not None and not hist_eu.empty:
        hist_ue = hist_eu.copy()
        hist_ue["Close"] = 1.0 / hist_ue["Close"]
        fig_ue = interactive_line_chart(
            hist_ue,
            f"USD/EUR — {period_lbl}",
            "#22c55e",
            "EUR",
            tight_yaxis=True,
        )
        if fig_ue:
            _show_plotly(fig_ue)

    st.markdown('<div class="section-divider"></div>', unsafe_allow_html=True)


# ──────────────────────────────────────────────────────────────────────────────
#  SEKCE 3: ROPA A PLASTY
# ──────────────────────────────────────────────────────────────────────────────

def render_oil_plastics() -> None:
    """Sekce 3 – ropa Brent/WTI, proxy model cen plastů, historický graf."""

    oil  = fetch_oil_data()
    brent_price  = (oil or {}).get("brent", {}).get("price")
    live = brent_price is not None
    plastics     = calc_plastic_prices(brent_price) if brent_price else None

    if not live:
        st.warning("Brent (BZ=F): Yahoo Finance nevrátilo živou cenu — data nedostupná.")

    section_header(
        "🛢️", "Ropa & Plasty — Proxy Model",
        badge_html(live, "Yahoo Finance"),
        badge_html(False, "", model=True) if plastics else badge_html(False),
    )

    # ── Karty ropy ─────────────────────────────────────────────────────────────
    col_br, col_wt, col_spr, col_pvc, col_xlpe, col_pa12 = st.columns(6)

    ccy_oil = get_display_currency()
    oil_unit = oil_unit_label()
    oil_d_suffix = currency_delta_suffix()

    with col_br:
        if oil and "brent" in oil:
            b = oil["brent"]
            st.markdown(metric_card(
                "Brent Crude Oil",
                format_oil_price(b["price"]),
                oil_unit,
                delta=usd_to_display(b["delta"], ccy_oil),
                delta_suffix=oil_d_suffix,
                card_class="card-oil",
            ), unsafe_allow_html=True)
        else:
            st.markdown(
                error_card("Brent Crude Oil", "card-oil", "Data nedostupná"),
                unsafe_allow_html=True,
            )

    with col_wt:
        if oil and "wti" in oil:
            w = oil["wti"]
            st.markdown(metric_card("WTI Crude Oil", f"${w['price']:.2f}", "USD / barel",
                                     delta=w["delta"], delta_suffix=" USD", card_class="card-oil"),
                        unsafe_allow_html=True)
        else:
            st.markdown(error_card("WTI Crude Oil", "card-oil"), unsafe_allow_html=True)

    with col_spr:
        if oil and "brent" in oil and "wti" in oil:
            spread = oil["brent"]["price"] - oil["wti"]["price"]
            st.markdown(metric_card("Brent / WTI", f"${spread:+.2f}", "USD / barel",
                                     card_class="card-neutral", extra="Brent premium nad WTI"),
                        unsafe_allow_html=True)
        else:
            st.markdown(error_card("Brent / WTI", "card-neutral"), unsafe_allow_html=True)

    plastic_cards = [
        (col_pvc,  "pvc",   "PVC Granulát"),
        (col_xlpe, "xlpe",  "XLPE Granulát"),
        (col_pa12, "pa12",  "PA12 Plášť"),
    ]
    for col, key, label in plastic_cards:
        with col:
            if plastics and key in plastics:
                st.markdown(
                    metric_card(label, format_num(plastics[key]["price"], 0, prefix="~"), "USD/t (model)",
                                 card_class="card-plastic", extra="Lag 4–8 týdnů"),
                    unsafe_allow_html=True,
                )
            else:
                st.markdown(error_card(label, "card-plastic"), unsafe_allow_html=True)

    # Disclaimer pro plastový model
    st.markdown("""
    <div class="warning-box">
        ⚠️ <strong>Model plastů:</strong> Ceny PVC, XLPE, PA12 a LLDPE jsou <em>orientační odhady</em>
        vypočítané lineárním proxy modelem z ceny Brent ropy. Skutečné spotové ceny závisejí na
        nabídce/poptávce, alokaci kapacit petrochemických závodů a logistice.
        Historické časové zpoždění reakce trhu: <strong>4–8 týdnů</strong>.
    </div>
    """, unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # ── Brent graf (BZ=F) + SMA 30d trend + přepínač období ─────────────────
    st.markdown(
        "<div style='font-family:Syne,sans-serif;font-size:0.75rem;font-weight:700;"
        "color:#495057;text-transform:uppercase;letter-spacing:1px;margin-bottom:8px;'>"
        "Brent Crude (BZ=F) — historie &amp; SMA 30d</div>",
        unsafe_allow_html=True,
    )
    period_lbl = get_chart_period_label()
    oil_hist = fetch_oil_history(get_chart_period())
    if oil_hist is not None and not oil_hist.empty:
        oil_plot = apply_currency_to_df(oil_hist.copy())
        fig_oil = interactive_oil_chart(
            oil_plot,
            f"Brent Crude Oil ({ccy_oil}) — {period_lbl} · SMA 30d = trend",
            "#f59e0b",
            320,
        )
        if fig_oil:
            _show_plotly(fig_oil)
    else:
        st.markdown('<div class="error-box">Graf ropy momentálně nedostupný</div>',
                    unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # ── Tabulka plastů ────────────────────────────────────────────────────────
    col_g, col_t = st.columns([3, 1])

    with col_g:
        st.markdown(
            f'<div class="info-box">Graf výše: <strong>oranžová</strong> = spot Brent (BZ=F) v {ccy_oil}, '
            '<strong>šedá přerušovaná</strong> = 30denní klouzavý průměr (indikace trendu). '
            'Historie z Yahoo Finance.</div>',
            unsafe_allow_html=True,
        )

    with col_t:
        if plastics:
            rows = "".join([
                f'<tr><td>{plastics[k]["desc"]}</td>'
                f'<td style="color:#14b8a6;text-align:right;">{format_num(plastics[k]["price"], 0, prefix="~")}</td></tr>'
                for k in ["pvc", "xlpe", "pa12", "lldpe"]
            ])
            st.markdown(f"""
            <div class="data-table-wrap" style="height:100%;">
                <table>
                    <thead>
                        <tr>
                            <th>Materiál</th>
                            <th style="text-align:right;">USD/t</th>
                        </tr>
                    </thead>
                    <tbody>
                        {rows}
                    </tbody>
                </table>
                <div style="margin-top:12px;font-family:'IBM Plex Mono',monospace;
                            font-size:0.65rem;color:#6C757D;line-height:1.7;">
                    Základ (Brent):<br>
                    <strong style="color:#212529;">${plastics['_brent']:.2f}/bbl</strong><br><br>
                    Model: lineární proxy<br>
                    Zdroj: Yahoo Finance
                </div>
            </div>
            """, unsafe_allow_html=True)

    st.markdown('<div class="section-divider"></div>', unsafe_allow_html=True)


# ──────────────────────────────────────────────────────────────────────────────
#  SEKCE 4: LOGISTIKA
# ──────────────────────────────────────────────────────────────────────────────

# Transitní časy Čína → ČR (dny)
TRANSIT_DAYS: dict[str, int] = {
    "Železniční doprava": 20,
    "Námořní doprava":    40,
    "Letecká doprava":      5,
}

_LANDED_ROUTES = (
    "🇨🇳 Čína (FCL Železnice)",
    "🇹🇷 Turecko (Urgent truck)",
)
_ROUTE_TURKEY = _LANDED_ROUTES[1]

_HS_CODE_OPTIONS: list[tuple[str, float]] = [
    ("Solární kabely (HS 85446010 90)", 3.7),
    ("Střední napětí VN (HS 85446090 90)", 3.7),
    ("Kabely 80V-1000V (HS 85444995 90)", 3.7),
    ("Hliníky nad 0.51mm (HS 85444991 00)", 3.7),
    ("Napájecí kabely do 80V (HS 85444993 00)", 3.3),
    ("Datové / Telekom. kabely (HS 85444920)", 0.0),
    ("Speciální kabely", 3.7),
]
_HS_LABELS = [label for label, _ in _HS_CODE_OPTIONS]
_HS_DEFAULT_DUTY = {label: pct for label, pct in _HS_CODE_OPTIONS}

_INVOICE_COL_NAME = "Název / Typ kabelu"
_INVOICE_COL_QTY = "Množství (m)"
_INVOICE_COL_PRICE = "Nákupní cena za 1m (EUR)"
_INVOICE_COL_HS = "HS Kód / Nápověda"
_INVOICE_COL_DUTY = "Aplikované clo (%)"

_DEFAULT_INVOICE_DF = pd.DataFrame([
    {
        _INVOICE_COL_NAME: "Solární kabel",
        _INVOICE_COL_QTY: 300_000.0,
        _INVOICE_COL_PRICE: 1.85,
        _INVOICE_COL_HS: _HS_LABELS[0],
        _INVOICE_COL_DUTY: 3.7,
    },
])


def _get_eur_czk_rate(cnb: dict | None) -> float | None:
    """Kurz EUR/CZK z kurzovního lístku ČNB (CZK za 1 EUR)."""
    if not cnb:
        return None
    info = cnb.get("EUR")
    if info and info.get("rate"):
        return float(info["rate"])
    return None


def _sanitize_invoice_input(df: pd.DataFrame) -> pd.DataFrame:
    """Vyčistí řádky z data_editor — pouze platné položky faktury."""
    if df is None or df.empty:
        return pd.DataFrame(columns=_DEFAULT_INVOICE_DF.columns)
    out = df.copy()
    for col in _DEFAULT_INVOICE_DF.columns:
        if col not in out.columns:
            out[col] = _DEFAULT_INVOICE_DF[col].iloc[0] if len(_DEFAULT_INVOICE_DF) else ""
    out = out[_DEFAULT_INVOICE_DF.columns]
    out[_INVOICE_COL_NAME] = out[_INVOICE_COL_NAME].astype(str).str.strip()
    out[_INVOICE_COL_QTY] = pd.to_numeric(out[_INVOICE_COL_QTY], errors="coerce").fillna(0)
    out[_INVOICE_COL_PRICE] = pd.to_numeric(out[_INVOICE_COL_PRICE], errors="coerce").fillna(0)
    out[_INVOICE_COL_DUTY] = pd.to_numeric(out[_INVOICE_COL_DUTY], errors="coerce").fillna(0)
    if _INVOICE_COL_HS in out.columns:
        out[_INVOICE_COL_HS] = out[_INVOICE_COL_HS].astype(str)
        out.loc[~out[_INVOICE_COL_HS].isin(_HS_LABELS), _INVOICE_COL_HS] = _HS_LABELS[0]
    mask = (
        (out[_INVOICE_COL_NAME] != "")
        & (out[_INVOICE_COL_NAME].str.lower() != "nan")
        & (out[_INVOICE_COL_QTY] > 0)
        & (out[_INVOICE_COL_PRICE] > 0)
    )
    return out.loc[mask].reset_index(drop=True)


def compute_invoice_landed(
    invoice: pd.DataFrame,
    transport_eur: float,
    customs_czk: float,
    eur_czk: float,
    force_zero_duty: bool,
) -> pd.DataFrame | None:
    """
    Proporční rozpočítání dopravy, cla a celní deklarace na řádky faktury.
    Clo v % ze sloupce Aplikované clo (%) — u Turecka vynuceno 0 %.
    """
    if invoice is None or invoice.empty:
        return None

    rows: list[dict] = []
    for _, r in invoice.iterrows():
        qty = float(r[_INVOICE_COL_QTY])
        price = float(r[_INVOICE_COL_PRICE])
        row_value = qty * price
        duty_pct = 0.0 if force_zero_duty else float(r[_INVOICE_COL_DUTY])
        rows.append({
            _INVOICE_COL_NAME: r[_INVOICE_COL_NAME],
            _INVOICE_COL_HS: r.get(_INVOICE_COL_HS, ""),
            _INVOICE_COL_QTY: qty,
            _INVOICE_COL_PRICE: price,
            _INVOICE_COL_DUTY: duty_pct,
            "Hodnota řádku (EUR)": row_value,
        })

    calc = pd.DataFrame(rows)
    total_goods = calc["Hodnota řádku (EUR)"].sum()
    if total_goods <= 0:
        return None

    customs_total_eur = customs_czk / eur_czk
    calc["Podíl na faktuře"] = calc["Hodnota řádku (EUR)"] / total_goods
    calc["Doprava přidělená (EUR)"] = calc["Podíl na faktuře"] * transport_eur
    calc["Základ pro clo (EUR)"] = (
        calc["Hodnota řádku (EUR)"] + calc["Doprava přidělená (EUR)"]
    )
    calc["Clo (EUR)"] = calc["Základ pro clo (EUR)"] * (calc[_INVOICE_COL_DUTY] / 100.0)
    calc["Deklarace přidělená (EUR)"] = calc["Podíl na faktuře"] * customs_total_eur
    calc["Celková Landed cena položky (EUR)"] = (
        calc["Hodnota řádku (EUR)"]
        + calc["Doprava přidělená (EUR)"]
        + calc["Clo (EUR)"]
        + calc["Deklarace přidělená (EUR)"]
    )
    calc["Finální Landed nákupka za 1 m (EUR)"] = (
        calc["Celková Landed cena položky (EUR)"] / calc[_INVOICE_COL_QTY]
    )
    calc["Finální Landed nákupka za 1 m (CZK)"] = (
        calc["Finální Landed nákupka za 1 m (EUR)"] * eur_czk
    )
    return calc


def _apply_sales_pricing(results: pd.DataFrame, margin_pct: float) -> pd.DataFrame:
    """Přidá sloupce prodejní ceny (přirážka / marže) z landed CZK/m."""
    out = results.copy()
    landed_czk = out["Finální Landed nákupka za 1 m (CZK)"]
    pct = margin_pct / 100.0
    out["Prodej (Přirážka CZK)"] = landed_czk * (1.0 + pct)
    if pct >= 1.0:
        out["Prodej (Marže CZK)"] = float("nan")
    else:
        out["Prodej (Marže CZK)"] = landed_czk / (1.0 - pct)
    return out


def render_landed_cost_pricing() -> None:
    """Logistika a cenotvorba — faktura (více řádků), landed cost, prodejní ceny."""
    st.header("🚢 Logistika a Prodejní ceny")

    cnb = fetch_cnb_rates()
    eur_czk = _get_eur_czk_rate(cnb)
    cnb_date = (cnb or {}).get("_date", "N/A")

    st.markdown(
        f'<div class="info-box">'
        f'Faktura s více řádky · proporční doprava a deklarace · clo dle HS / Aplikované clo (%) · '
        f'kurz <strong>ČNB EUR/CZK</strong>{f" ({cnb_date})" if cnb else ""} · '
        f'Turecko (A.TR) vynutí clo <strong>0 %</strong> na všech řádcích'
        f'</div>',
        unsafe_allow_html=True,
    )

    if not eur_czk or eur_czk <= 0:
        st.error("Kurz EUR/CZK z ČNB není k dispozici — landed cost nelze spočítat.")
        return

    c_route, c_trans, c_custom, c_fx = st.columns([2, 1, 1, 1])
    with c_route:
        route_label = st.radio(
            "Trasa",
            options=list(_LANDED_ROUTES),
            key="landed_route",
            horizontal=True,
        )
        force_zero_duty = route_label == _ROUTE_TURKEY
        if force_zero_duty:
            st.caption("🇹🇷 Turecko: u všech řádků se použije clo **0 %** (A.TR).")
    with c_trans:
        transport_eur = st.number_input(
            "Cena dopravy (EUR)",
            min_value=0.0,
            value=12_000.0,
            step=100.0,
            format="%.2f",
            key="landed_transport_eur",
        )
    with c_custom:
        customs_czk = st.number_input(
            "Poplatek za celní deklaraci a JSD (CZK)",
            min_value=0.0,
            value=1_000.0,
            step=100.0,
            format="%.2f",
            key="landed_customs_czk",
        )
    with c_fx:
        st.metric("EUR/CZK (ČNB)", f"{eur_czk:.4f}")

    st.markdown("#### Položky faktury")
    if "landed_invoice_data" not in st.session_state:
        st.session_state.landed_invoice_data = _DEFAULT_INVOICE_DF.copy()

    edited = st.data_editor(
        st.session_state.landed_invoice_data,
        num_rows="dynamic",
        use_container_width=True,
        hide_index=True,
        key="landed_invoice_editor",
        column_config={
            _INVOICE_COL_NAME: st.column_config.TextColumn(
                _INVOICE_COL_NAME,
                width="medium",
                required=True,
            ),
            _INVOICE_COL_QTY: st.column_config.NumberColumn(
                _INVOICE_COL_QTY,
                min_value=0.0,
                format="%.0f",
                required=True,
            ),
            _INVOICE_COL_PRICE: st.column_config.NumberColumn(
                _INVOICE_COL_PRICE,
                min_value=0.0,
                format="%.4f",
                required=True,
            ),
            _INVOICE_COL_HS: st.column_config.SelectboxColumn(
                _INVOICE_COL_HS,
                options=_HS_LABELS,
                help="Nápověda k HS kódu — orientační sazba cla",
                required=True,
            ),
            _INVOICE_COL_DUTY: st.column_config.NumberColumn(
                _INVOICE_COL_DUTY,
                min_value=0.0,
                max_value=100.0,
                format="%.2f",
                help="Finální % cla pro výpočet (Čína). U Turecka se ignoruje.",
                required=True,
            ),
        },
    )
    st.session_state.landed_invoice_data = edited

    if st.button("📋 Doplnit clo (%) dle HS nápovědy", key="landed_fill_duty_hs"):
        if force_zero_duty:
            st.info("Turecko (A.TR): clo je vynuceno na 0 % — HS sazby se nepoužijí.")
        else:
            filled = _sanitize_invoice_input(edited)
            if not filled.empty:
                filled[_INVOICE_COL_DUTY] = filled[_INVOICE_COL_HS].map(_HS_DEFAULT_DUTY)
                st.session_state.landed_invoice_data = filled
                st.rerun()

    invoice = _sanitize_invoice_input(edited)
    if invoice.empty:
        st.info("Přidejte alespoň jeden řádek faktury (název, množství > 0, cena > 0).")
        return

    results = compute_invoice_landed(
        invoice,
        transport_eur,
        customs_czk,
        eur_czk,
        force_zero_duty,
    )
    if results is None:
        st.warning("Celková hodnota zboží na faktuře musí být větší než nula.")
        return

    total_goods = results["Hodnota řádku (EUR)"].sum()
    total_landed = results["Celková Landed cena položky (EUR)"].sum()
    s1, s2, s3 = st.columns(3)
    s1.metric("Hodnota zboží na faktuře", f"{format_num(total_goods, 2)} EUR")
    s2.metric("Celkové náklady (landed)", f"{format_num(total_landed, 2)} EUR")
    s3.metric("Celkem v CZK", f"{format_num(total_landed * eur_czk, 0)} Kč")

    st.markdown("#### Výsledky — Landed Cost po položkách")
    display_cols = [
        _INVOICE_COL_NAME,
        _INVOICE_COL_HS,
        _INVOICE_COL_QTY,
        _INVOICE_COL_PRICE,
        _INVOICE_COL_DUTY,
        "Celková Landed cena položky (EUR)",
        "Finální Landed nákupka za 1 m (EUR)",
        "Finální Landed nákupka za 1 m (CZK)",
    ]

    st.subheader("Tvorba prodejní ceny")
    margin_pct = st.number_input(
        "Požadovaná marže / přirážka (%)",
        min_value=0.0,
        max_value=99.0,
        value=30.0,
        step=1.0,
        format="%.1f",
        key="landed_margin_pct",
        help="Přirážka: ×(1+p/100) · Marže: ÷(1−p/100) z Landed CZK/m",
    )

    results_sales = _apply_sales_pricing(results, margin_pct)
    display_cols += ["Prodej (Přirážka CZK)", "Prodej (Marže CZK)"]

    show = results_sales[display_cols].copy()
    st.dataframe(
        show,
        use_container_width=True,
        hide_index=True,
    )

    if margin_pct >= 100.0:
        st.warning("Marže 100 % a více — sloupec Prodej (Marže CZK) není definován.")

    with st.expander("🔍 Detail proporcí (doprava, clo, deklarace)", expanded=False):
        detail_cols = [
            _INVOICE_COL_NAME,
            "Hodnota řádku (EUR)",
            "Podíl na faktuře",
            "Doprava přidělená (EUR)",
            "Základ pro clo (EUR)",
            "Clo (EUR)",
            "Deklarace přidělená (EUR)",
        ]
        st.dataframe(
            results_sales[detail_cols].copy(),
            use_container_width=True,
            hide_index=True,
        )

    st.markdown('<div class="section-divider"></div>', unsafe_allow_html=True)


def render_logistics() -> None:
    """Sekce 4 – kalkulačka transitního času Čína → ČR s progress barem."""

    section_header(
        "🚚", "Logistika — Transitní Čas Čína → ČR",
        badge_html(True, "Kalkulačka"),
    )

    st.markdown(
        '<div class="info-box">'
        'Odhad doručení surovin a komponent z Číny do ČR · '
        '<strong>Vlak 20 dní</strong> · <strong>Loď 40 dní</strong> · <strong>Letadlo 5 dní</strong>'
        '</div>',
        unsafe_allow_html=True,
    )

    col_form, col_result = st.columns([1, 1])

    with col_form:
        transport = st.selectbox(
            "Způsob dopravy",
            list(TRANSIT_DAYS.keys()),
            index=0,
            help="Železniční doprava je prioritní varianta pro většinu nákladů.",
        )
        ship_date = st.date_input(
            "Datum odeslání",
            value=now_prague().date(),
            help="Den odjezdu nákladu z Číny",
        )

    transit_days = TRANSIT_DAYS[transport]
    delivery_date = ship_date + timedelta(days=transit_days)
    today = now_prague().date()

    if today < ship_date:
        elapsed = 0
        progress = 0.0
        phase = "Čeká na odeslání"
        phase_color = "#f59e0b"
    elif today >= delivery_date:
        elapsed = transit_days
        progress = 1.0
        phase = "Doručeno (nebo po termínu)"
        phase_color = "#22c55e"
    else:
        elapsed = (today - ship_date).days
        progress = min(1.0, elapsed / transit_days)
        phase = f"Na cestě — den {elapsed + 1} z {transit_days}"
        phase_color = "#3b82f6"

    days_left = max(0, (delivery_date - today).days)

    with col_result:
        st.markdown(f"""
        <div class="metric-card card-logistics" style="margin-top:28px;">
            <div class="card-label">Očekávané doručení</div>
            <div class="card-value" style="font-size:1.6rem;color:#a0c8e8;">
                {delivery_date.strftime("%d.%m.%Y")}
            </div>
            <div class="card-unit">{transport} · {transit_days} dní transit</div>
            <div style="margin-top:10px;font-family:'IBM Plex Mono',monospace;
                        font-size:0.72rem;color:{phase_color};">{phase}</div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown(
        f"<div style='font-family:IBM Plex Mono,monospace;font-size:0.72rem;"
        f"color:#212529;margin-bottom:6px;'>"
        f"Průběh cesty · odesláno {ship_date.strftime('%d.%m.%Y')} → "
        f"doručení {delivery_date.strftime('%d.%m.%Y')} · dnes {today.strftime('%d.%m.%Y')}"
        f"</div>",
        unsafe_allow_html=True,
    )
    st.progress(progress, text=f"{int(progress * 100)} % dokončeno trasy")

    c1, c2, c3, c4 = st.columns(4)
    milestones = [
        (c1, "Odesláno",       ship_date.strftime("%d.%m.%Y"), "#f59e0b"),
        (c2, "Dnes",           today.strftime("%d.%m.%Y"),      "#3b82f6"),
        (c3, "Zbývá",          f"{days_left} dní" if days_left else "—", "#8b5cf6"),
        (c4, "Doručení (ETA)", delivery_date.strftime("%d.%m.%Y"), "#22c55e"),
    ]
    for col, label, val, clr in milestones:
        with col:
            st.markdown(f"""
            <div class="spread-card">
                <div class="spread-label">{label}</div>
                <div class="spread-value" style="color:{clr};font-size:1.1rem;">{val}</div>
            </div>
            """, unsafe_allow_html=True)

    st.markdown('<div class="section-divider"></div>', unsafe_allow_html=True)


# ── Logistika ČR & SK (přeprava kamionem) ─────────────────────────────────────

_DOMESTIC_ROAD_FACTOR = 1.3
_DOMESTIC_LDM_PER_EUR_PALLET = 0.4
_DOMESTIC_MIN_PRICE_CZK = 1200.0

_DOMESTIC_SOLO_MAX_KG = 7500.0
_DOMESTIC_SOLO_LABEL = "Sólo náklaďák (do 7,5 t)"
_DOMESTIC_SOLO_LEGACY_LABELS = frozenset({
    "Sólo náklaďák (do 9.5t)",
    "Sólo náklaďák (do 9,5 t)",
})

_DOMESTIC_VEHICLE_ORDER = [
    "Kamion (návěs 24t)",
    _DOMESTIC_SOLO_LABEL,
    "Plachtová dodávka (do 1,6 t)",
]

_DOMESTIC_VEHICLE_PROFILES: dict[str, dict[str, float]] = {
    "Kamion (návěs 24t)": {
        "max_w": 24000.0,
        "max_l": 13.6,
        "def_rate": 45.0,
        "fix_handling": 600.0,
        "fix_hub_km": 30.0,
        "default_w": 15000.0,
        "default_l": 6.0,
        "ltl_exp": 0.55,
        "ltl_floor": 0.48,
        "min_price": 1200.0,
    },
    _DOMESTIC_SOLO_LABEL: {
        "max_w": _DOMESTIC_SOLO_MAX_KG,
        "max_l": 7.2,
        "def_rate": 30.0,
        "fix_handling": 350.0,
        "fix_hub_km": 25.0,
        "default_w": 5000.0,
        "default_l": 2.0,
        "ltl_exp": 0.42,
        "ltl_floor": 0.55,
        "min_price": 1200.0,
    },
    "Plachtová dodávka (do 1,6 t)": {
        "max_w": 1600.0,
        "max_l": 4.0,
        "def_rate": 20.0,
        "fix_handling": 200.0,
        "fix_hub_km": 15.0,
        "default_w": 800.0,
        "default_l": 0.8,
        "ltl_floor": 0.88,
        "min_price": 900.0,
    },
}

_NOMINATIM_HEADERS = {"User-Agent": "pbcable-dashboard"}


def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Vzdušná vzdálenost mezi dvěma body na Zemi (km)."""
    r_earth_km = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = (
        math.sin(dphi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return r_earth_km * c


@st.cache_data(ttl=86400, show_spinner=False)
def search_domestic_location(query: str) -> list[dict]:
    """
    Vyhledání míst v ČR a na Slovensku (Nominatim).
    Vrací list {lat, lon, display_name, postcode, country}.
    """
    q = (query or "").strip()
    if len(q) < 2:
        return []

    time.sleep(1)
    url = "https://nominatim.openstreetmap.org/search"
    params = {
        "q": q,
        "countrycodes": "cz,sk",
        "format": "json",
        "addressdetails": 1,
        "limit": 12,
    }
    try:
        resp = requests.get(
            url, params=params, headers=_NOMINATIM_HEADERS, timeout=15
        )
        resp.raise_for_status()
        data = resp.json()
    except (requests.RequestException, ValueError):
        return []

    if not isinstance(data, list):
        return []

    results: list[dict] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        addr = item.get("address") or {}
        country = str(addr.get("country_code", "")).upper()
        if country not in ("CZ", "SK"):
            country_name = str(addr.get("country", "")).lower()
            if "slovak" in country_name or "slovensko" in country_name:
                country = "SK"
            elif "czech" in country_name or "česko" in country_name or "czechia" in country_name:
                country = "CZ"
            else:
                continue
        postcode = addr.get("postcode") or addr.get("postal_code") or "N/A"
        try:
            results.append({
                "lat": float(item["lat"]),
                "lon": float(item["lon"]),
                "display_name": str(item.get("display_name", q)),
                "postcode": str(postcode),
                "country": country,
            })
        except (KeyError, TypeError, ValueError):
            continue
    return results


def _location_select_label(loc: dict) -> str:
    country = loc.get("country", "CZ")
    country_lbl = "SK" if country == "SK" else "ČR"
    return f'{loc["display_name"]} ({country_lbl} · PSČ: {loc["postcode"]})'


def _render_location_search(
    section_title: str,
    input_key: str,
    select_key: str,
    default_query: str = "",
) -> dict | None:
    """Vyhledání a výběr místa v ČR nebo na SK — text_input + selectbox pod ním."""
    st.markdown(f"**{section_title}**")
    query = st.text_input(
        "🔍 Vyhledat město, ulici nebo PSČ (ČR / SK)",
        value=default_query,
        key=input_key,
        placeholder="např. Metylovice, Košice, Senec, Praha 1, 040 01",
    )
    if not query.strip():
        return None

    with st.spinner("Vyhledávám (ČR & SK)…"):
        hits = search_domestic_location(query.strip())

    if not hits:
        st.caption("Žádné výsledky — upřesněte dotaz.")
        return None

    idx = st.selectbox(
        "Vyberte adresu",
        range(len(hits)),
        format_func=lambda i: _location_select_label(hits[i]),
        key=select_key,
    )
    return hits[idx]


@st.cache_data(ttl=86400, show_spinner=False)
def get_driving_distance(
    lat1: float, lon1: float, lat2: float, lon2: float
) -> tuple[float, bool]:
    """
    Silniční vzdálenost v km (OSRM). Vrací (km, použito_osrm).
    Při selhání API: haversine × 1,3 a druhá hodnota False.
    """
    url = (
        "http://router.project-osrm.org/route/v1/driving/"
        f"{lon1},{lat1};{lon2},{lat2}?overview=false"
    )
    try:
        resp = requests.get(url, timeout=20)
        resp.raise_for_status()
        data = resp.json()
        if data.get("code") != "Ok":
            raise ValueError(str(data.get("message", "OSRM error")))
        routes = data.get("routes") or []
        if not routes:
            raise ValueError("OSRM: no routes")
        dist_km = float(routes[0]["distance"]) / 1000.0
        if dist_km <= 0:
            raise ValueError("OSRM: invalid distance")
        return dist_km, True
    except (requests.RequestException, ValueError, KeyError, TypeError, IndexError):
        fallback_km = haversine_distance(lat1, lon1, lat2, lon2) * _DOMESTIC_ROAD_FACTOR
        return fallback_km, False


def _domestic_vehicle_key(v_type: str) -> str:
    if "Dodávka" in v_type:
        return "van"
    if "Sólo" in v_type:
        return "solo"
    return "truck"


def _domestic_normalize_vehicle_type(v_type: str) -> str:
    """Mapuje zastaralé názvy vozidel (např. sólo 9,5 t) na aktuální profil."""
    if v_type in _DOMESTIC_VEHICLE_PROFILES:
        return v_type
    if v_type in _DOMESTIC_SOLO_LEGACY_LABELS or "Sólo" in v_type:
        return _DOMESTIC_SOLO_LABEL
    if "Dodávka" in v_type:
        return "Plachtová dodávka (do 1,6 t)"
    if "Kamion" in v_type:
        return "Kamion (návěs 24t)"
    return _DOMESTIC_VEHICLE_ORDER[0]


def _domestic_vehicle_option_label(v_type: str) -> str:
    profile = _DOMESTIC_VEHICLE_PROFILES[v_type]
    return (
        f"{v_type} — max {format_num(profile['max_w'], 0)} kg / "
        f"{profile['max_l']:.1f} LDM"
    )


def _domestic_suggest_vehicle(weight_kg: float, ldm: float) -> str:
    """Nejmenší vozidlo z katalogu, které pojme váhu i LDM (dodávka → sólo → kamion)."""
    for v_type in reversed(_DOMESTIC_VEHICLE_ORDER):
        profile = _DOMESTIC_VEHICLE_PROFILES[v_type]
        if weight_kg <= profile["max_w"] and ldm <= profile["max_l"]:
            return v_type
    return _DOMESTIC_VEHICLE_ORDER[0]


def _domestic_capacity_info(
    weight_kg: float,
    ldm: float,
    profile: dict[str, float],
) -> dict[str, float | bool | str]:
    """Vytížení vozu — váha vs. LDM, včetně přetížení."""
    max_w, max_l = profile["max_w"], profile["max_l"]
    cap_w = weight_kg / max_w
    cap_l = ldm / max_l
    podil_kapacity = max(cap_w, cap_l)
    return {
        "podil_kapacity": podil_kapacity,
        "cap_pct": podil_kapacity * 100.0,
        "cap_w_pct": cap_w * 100.0,
        "cap_l_pct": cap_l * 100.0,
        "binding": "váha" if cap_w >= cap_l else "LDM",
        "overload": podil_kapacity > 1.0,
        "progress": min(1.0, podil_kapacity),
    }


def _domestic_compute_fix_fee(
    profile: dict[str, float],
    rate_czk_km: float,
) -> dict[str, float]:
    """
    Fixní složka = manipulace (nakládka/vykládka) + dojezd k regionálnímu hubu (km × sazba).
    U kamionu při 45 CZK/km: 600 + 30×45 ≈ 1 950 Kč (Metylovice → aglomerace ~30 km).
    """
    handling = profile.get("fix_handling", 0.0)
    hub_km = profile.get("fix_hub_km", 0.0)
    positioning = hub_km * rate_czk_km
    return {
        "fix_handling": handling,
        "fix_hub_km": hub_km,
        "fix_positioning": positioning,
        "fix_fee": handling + positioning,
    }


def _domestic_ltl_coefficient(
    podil_for_ltl: float,
    profile: dict[str, float],
    vehicle_key: str,
) -> float:
    """
    LTL koeficient dle typu vozidla (orientační tržní model CZ).
    Kamion: dokládka ^0,55 · sólo: ^0,42 · dodávka: min. 88 % km sazby (celý vůz).
    """
    floor = profile.get("ltl_floor", 0.5)
    if vehicle_key == "van":
        return max(floor, podil_for_ltl)
    exp = profile.get("ltl_exp", 0.55)
    return max(floor, podil_for_ltl ** exp)


def _render_domestic_capacity_bar(cap: dict[str, float | bool | str]) -> None:
    """Vizuální ukazatel vytížení vozidla."""
    pct = cap["cap_pct"]
    progress_val = cap["progress"]
    binding = cap["binding"]
    if cap["overload"]:
        st.progress(
            1.0,
            text=f"Vytížení vozu: {pct:.0f} % — PŘETÍŽENÍ",
        )
    else:
        st.progress(
            float(progress_val),
            text=f"Vytížení vozu: {pct:.0f} %",
        )
    st.caption(
        f"Váha {cap['cap_w_pct']:.0f} % · LDM {cap['cap_l_pct']:.0f} % · "
        f"limituje: **{binding}**"
    )


def _domestic_compute_quote(
    dist_km: float,
    weight_kg: float,
    ldm: float,
    profile: dict[str, float],
    rate_czk_km: float,
    vehicle_key: str,
) -> dict[str, float | bool | str | None]:
    """Kapacita + cena k jednání; při přetížení cena None."""
    cap = _domestic_capacity_info(weight_kg, ldm, profile)
    overload = cap["overload"]
    podil_for_ltl = min(1.0, cap["podil_kapacity"])
    ltl_koef = _domestic_ltl_coefficient(podil_for_ltl, profile, vehicle_key)

    km_part = dist_km * rate_czk_km * ltl_koef
    fix_parts = _domestic_compute_fix_fee(profile, rate_czk_km)
    fix_fee = fix_parts["fix_fee"]
    min_price = profile.get("min_price", _DOMESTIC_MIN_PRICE_CZK)

    price_czk: float | None = None
    if not overload:
        price_czk = max(min_price, km_part + fix_fee)

    return {
        **cap,
        "ltl_koef": ltl_koef,
        "km_part": km_part,
        **fix_parts,
        "price_czk": price_czk,
        "price_valid": not overload,
    }


def _render_domestic_pallet_cheat_sheet() -> None:
    """Tahák — specifikace vozidel a tabulka palet 1–34."""
    with st.expander("ℹ️ Tahák: Počet EUR palet vs. Ložné metry (LDM)"):
        st.markdown(
            "**🚚 Typy vozidel a technické specifikace:**<br>"
            "• **Kamion (plachtový návěs 24 t):** délka 13,6 m · šířka 2,48 m · "
            "výška 2,7–3,0 m · **max 24 t / 13,6 LDM** · až 34 EUR palet<br>"
            "• **Sólo náklaďák (do 7,5 t):** délka cca 7,2 m · šířka 2,48 m · "
            "výška cca 2,7 m · **max 7,5 t / 7,2 LDM** · cca 18 EUR palet<br>"
            "• **Plachtová dodávka (do 1,6 t):** délka 4,2–4,8 m · šířka 2,2 m · "
            "výška 2,0–2,3 m · **max 1,6 t / 4,0 LDM** · 8–10 EUR palet<br><br>"
            "Vzorec: **`1 EUR paleta = 0,4 LDM`**. "
            "Návěs 2,48 m pojme **34 nestohovatelných palet** (1,2 × 0,8 m) = **13,6 LDM**.<br><br>"
            "**Fixní složka ceny:** manipulace (nakládka/vykládka) + "
            "**dojezd k regionálnímu městu** (km × sazba/km). "
            "Kamion: 600 Kč + 30 km × sazba (např. 30×45 = 1 350 Kč → fix ~1 950 Kč).",
            unsafe_allow_html=True,
        )

        pallets = list(range(1, 35))
        ldms = [round(p * _DOMESTIC_LDM_PER_EUR_PALLET, 1) for p in pallets]
        tc1, tc2, tc3 = st.columns(3)
        tc1.dataframe(
            pd.DataFrame({"Počet palet": pallets[:12], "LDM": ldms[:12]}),
            hide_index=True,
            use_container_width=True,
        )
        tc2.dataframe(
            pd.DataFrame({"Počet palet": pallets[12:24], "LDM": ldms[12:24]}),
            hide_index=True,
            use_container_width=True,
        )
        tc3.dataframe(
            pd.DataFrame({"Počet palet": pallets[24:], "LDM": ldms[24:]}),
            hide_index=True,
            use_container_width=True,
        )


_DOMESTIC_CARGO_PRESETS = [
    "Kabel na dřevěných bubnech",
    "Kabel na dřevěných bubnech položených na paletách",
    "Vlastní popis",
]

_DOMESTIC_LOAD_CONTACT_KEYS = ["bez_kontaktu", "radim_kochan", "lukas_filak"]

_DOMESTIC_LOAD_CONTACTS: dict[str, dict[str, str]] = {
    "bez_kontaktu": {
        "label": "Bez kontaktu na nakládce",
        "name": "",
        "email": "",
        "phone": "",
    },
    "radim_kochan": {
        "label": "Radim Kocháň",
        "name": "Radim Kocháň",
        "email": "radim.kochan@pbcable.cz",
        "phone": "+420 605 497 552",
    },
    "lukas_filak": {
        "label": "Lukáš Filák",
        "name": "Lukáš Filák",
        "email": "lukas.filak@pbcable.cz",
        "phone": "+420 734 222 733",
    },
}


def _domestic_load_contact_display(key: str) -> str:
    """Text kontaktu na nakládce pro poptávku (prázdný = bez kontaktu)."""
    if key == "bez_kontaktu":
        return ""
    person = _DOMESTIC_LOAD_CONTACTS[key]
    return (
        f"{person['name']}\n"
        f"e-mail: {person['email']}\n"
        f"telefon: {person['phone']}"
    )


def _domestic_price_eur(price_czk: float | None) -> tuple[float | None, float | None]:
    """Převod CZK → EUR kurzem ČNB. Vrací (EUR, eur_czk)."""
    if price_czk is None:
        return None, None
    eur_czk = _get_eur_czk_rate(fetch_cnb_rates())
    if not eur_czk or eur_czk <= 0:
        return None, eur_czk
    return price_czk / eur_czk, eur_czk


def _render_domestic_shipment_form() -> dict:
    """Formulář zboží, termínů a kontaktu pro poptávku dopravy."""
    st.markdown("#### Poptávka dopravy — detaily zásilky")
    cargo_choice = st.selectbox(
        "Přepravované zboží",
        _DOMESTIC_CARGO_PRESETS,
        key="domestic_cargo_preset",
    )
    cargo_custom = ""
    if cargo_choice == "Vlastní popis":
        cargo_custom = st.text_area(
            "Vlastní popis zboží",
            placeholder="např. měděný drát na cívkách, 12 palet…",
            key="domestic_cargo_custom",
        ).strip()
        if not cargo_custom:
            st.warning("Doplňte vlastní popis zboží pro kompletní poptávku.")
    cargo_desc = cargo_custom if cargo_choice == "Vlastní popis" else cargo_choice

    pickup_mode = st.radio(
        "Termín nakládky",
        ["Možno hned", "Konkrétní termín"],
        horizontal=True,
        key="domestic_pickup_mode",
    )
    load_date = None
    unload_date = None
    if pickup_mode == "Konkrétní termín":
        today = now_prague().date()
        c_load, c_unload = st.columns(2)
        with c_load:
            load_date = st.date_input(
                "Datum nakládky",
                value=today,
                key="domestic_load_date",
            )
        with c_unload:
            unload_date = st.date_input(
                "Datum vykládky",
                value=today + timedelta(days=1),
                key="domestic_unload_date",
            )

    with st.expander("Kontakt na nakládce", expanded=True):
        load_contact_key = st.selectbox(
            "Osoba na nakládce",
            _DOMESTIC_LOAD_CONTACT_KEYS,
            format_func=lambda k: _DOMESTIC_LOAD_CONTACTS[k]["label"],
            key="domestic_load_contact_key",
        )
        if load_contact_key != "bez_kontaktu":
            person = _DOMESTIC_LOAD_CONTACTS[load_contact_key]
            st.caption(
                f"{person['email']} · {person['phone']}"
            )
        else:
            st.caption("V poptávce nebude uveden kontakt na nakládce.")

    load_contact_text = _domestic_load_contact_display(load_contact_key)

    unload_contact = st.text_input(
        "Kontakt na vykládce (volitelně)",
        placeholder="jméno, telefon, e-mail, časové okno…",
        key="domestic_unload_contact",
    )
    request_note = st.text_area(
        "Poznámka pro dopravce (volitelně)",
        placeholder="např. vazačná páska, pomoc s vykládkou, rampa…",
        key="domestic_request_note",
    )

    return {
        "cargo_desc": cargo_desc or "—",
        "pickup_mode": pickup_mode,
        "load_date": load_date,
        "unload_date": unload_date,
        "load_contact_key": load_contact_key,
        "load_contact_text": load_contact_text,
        "unload_contact": unload_contact.strip(),
        "request_note": request_note.strip(),
    }


def _format_domestic_transport_request(
    *,
    start_loc: dict,
    dest_loc: dict,
    v_type: str,
    weight_kg: float,
    ldm: float,
    eur_pallets: int,
    road_km: float,
    used_osrm: bool,
    shipment: dict,
) -> str:
    """Sestaví text poptávky dopravy k odeslání dopravci (bez interní kalkulace)."""
    lines = [
        "POPTÁVKA DOPRAVY — pbcable s.r.o.",
        f"Vygenerováno: {now_prague().strftime('%d.%m.%Y %H:%M')}",
        "",
        "Dobrý den,",
        "poptáváme přepravu níže uvedené zásilky. Prosíme o zaslání cenové nabídky "
        "a potvrzení volné kapacity vozidla.",
        "",
        "── Trasa ──",
        f"Nakládka: {start_loc['display_name']} ({start_loc.get('country', 'CZ')})",
        f"Vykládka: {dest_loc['display_name']} ({dest_loc.get('country', 'CZ')})",
        f"Vzdálenost: cca {format_num(road_km, 0)} km"
        + (" (OSRM)" if used_osrm else " (odhad)"),
        "",
        "── Náklad ──",
        f"Požadovaný typ vozidla: {v_type}",
        f"Zboží: {shipment['cargo_desc']}",
        f"Hmotnost: {format_num(weight_kg, 0)} kg",
        f"Ložné metry: {ldm:.1f} LDM",
    ]
    if eur_pallets > 0:
        lines.append(f"EUR palety: {eur_pallets} ks")
    lines.extend([
        "",
        "── Termíny ──",
    ])
    if shipment["pickup_mode"] == "Možno hned":
        lines.append("Nakládka: možno ihned / dle dohody")
        lines.append("Vykládka: dle dohody")
    else:
        if shipment["load_date"]:
            lines.append(f"Datum nakládky: {shipment['load_date'].strftime('%d.%m.%Y')}")
        if shipment["unload_date"]:
            lines.append(f"Datum vykládky: {shipment['unload_date'].strftime('%d.%m.%Y')}")
    if shipment.get("load_contact_text"):
        lines.extend(["", "── Kontakt na nakládce ──", shipment["load_contact_text"]])
    elif shipment.get("load_contact_key") == "bez_kontaktu":
        lines.extend(["", "── Kontakt na nakládce ──", "Bez uvedeného kontaktu"])
    if shipment["unload_contact"]:
        lines.extend(["", "── Kontakt na vykládce ──", shipment["unload_contact"]])
    if shipment["request_note"]:
        lines.extend(["", "── Poznámka ──", shipment["request_note"]])

    lines.append("")
    lines.append("Předem děkujeme za Vaši nabídku a zprávu o dostupnosti.")
    lines.append("S pozdravem,")
    lines.append("Nákupní a logistické oddělení pbcable s.r.o.")
    return "\n".join(lines)


def render_domestic_logistics() -> None:
    """Kalkulačka přepravy ČR & SK — start a cíl z Nominatim, trasa přes OSRM."""
    section_header("🚛", "Logistika ČR & SK — Kalkulačka přepravy")

    st.markdown(
        '<div class="info-box">'
        'Vyhledejte <strong>start</strong> a <strong>cíl</strong> v <strong>ČR nebo na Slovensku</strong> '
        '(Košice, Senec, Bratislava, …) · silniční trasa OSRM včetně přeshraniční · '
        'záloha vzdálenosti: vzdušná × 1,3 · cena v CZK i EUR (ČNB) · '
        'poptávka pro dopravce ke stažení'
        '</div>',
        unsafe_allow_html=True,
    )

    col_form, col_result = st.columns([1, 1])

    with col_form:
        start_loc = _render_location_search(
            "Odkud (Start)",
            "domestic_start_query",
            "domestic_start_select",
            default_query="Metylovice",
        )
        st.markdown("<br>", unsafe_allow_html=True)
        dest_loc = _render_location_search(
            "Kam (Cíl)",
            "domestic_dest_query",
            "domestic_dest_select",
        )
        st.markdown("<br>", unsafe_allow_html=True)

        st.markdown("#### Parametry nákladu a vozidla")
        v_type_raw = st.selectbox(
            "Druh vozidla",
            _DOMESTIC_VEHICLE_ORDER,
            format_func=_domestic_vehicle_option_label,
            key="domestic_v_type_selector_v75",
            help=f"Sólo: pevný limit {_DOMESTIC_SOLO_MAX_KG:.0f} kg (7,5 t).",
        )
        v_type = _domestic_normalize_vehicle_type(v_type_raw)
        profile = _DOMESTIC_VEHICLE_PROFILES[v_type]
        max_w = profile["max_w"]
        max_l = profile["max_l"]
        def_rate = profile["def_rate"]
        default_w = profile["default_w"]
        default_l = profile["default_l"]
        vehicle_key = _domestic_vehicle_key(v_type)
        v_idx = _DOMESTIC_VEHICLE_ORDER.index(v_type)

        waha = st.number_input(
            "Váha (kg)",
            min_value=1.0,
            value=float(default_w),
            step=50.0,
            key=f"domestic_weight_{v_idx}",
        )

        eur_pallets = st.number_input(
            "Počet EUR palet (volitelně)",
            min_value=0,
            max_value=34,
            value=0,
            step=1,
            key=f"domestic_pallets_{v_idx}",
        )
        if eur_pallets > 0:
            ldm_auto = float(eur_pallets) * _DOMESTIC_LDM_PER_EUR_PALLET
            ldm = st.number_input(
                "Ložné metry (LDM)",
                min_value=0.1,
                value=ldm_auto,
                step=0.1,
                format="%.1f",
                disabled=True,
                key=f"domestic_ldm_pallet_{v_idx}",
                help=f"Automaticky: {eur_pallets} palet × 0,4 LDM = {ldm_auto:.1f} LDM",
            )
        else:
            ldm = st.number_input(
                "Ložné metry (LDM)",
                min_value=0.1,
                value=float(default_l),
                step=0.1,
                format="%.1f",
                key=f"domestic_ldm_{v_idx}",
            )

        sazba = st.number_input(
            "Sazba za celé auto (CZK/km)",
            min_value=0.0,
            value=float(def_rate),
            step=0.5,
            format="%.1f",
            key=f"domestic_sazba_{v_idx}",
        )

        fix_preview = _domestic_compute_fix_fee(profile, sazba)
        st.caption(
            f"Fixní složka (orientačně): **{format_num(fix_preview['fix_fee'], 0)} CZK** · "
            f"manipulace {format_num(fix_preview['fix_handling'], 0)} + "
            f"dojezd {fix_preview['fix_hub_km']:.0f} km × {sazba:.1f} = "
            f"{format_num(fix_preview['fix_positioning'], 0)} CZK"
        )

        st.markdown("**Vytížení vozidla (náklad)**")
        _render_domestic_capacity_bar(
            _domestic_capacity_info(waha, ldm, profile)
        )
        suggested_v = _domestic_suggest_vehicle(waha, ldm)
        if suggested_v != v_type:
            st.info(
                f"Dle hmotnosti ({format_num(waha, 0)} kg) a LDM ({ldm:.1f}) "
                f"doporučujeme vozidlo: **{suggested_v}**."
            )

        _render_domestic_pallet_cheat_sheet()
        shipment_form = _render_domestic_shipment_form()

    with col_result:
        if not start_loc or not dest_loc:
            st.info("Vyberte startovní a cílovou adresu pro výpočet a náhled poptávky.")
            if shipment_form.get("cargo_desc") and shipment_form["cargo_desc"] != "—":
                st.caption(
                    f"Zboží připraveno: {shipment_form['cargo_desc']} · "
                    f"termín: {shipment_form['pickup_mode']}"
                )
        else:
            start_lat, start_lon = start_loc["lat"], start_loc["lon"]
            dest_lat, dest_lon = dest_loc["lat"], dest_loc["lon"]

            with st.spinner("Počítám silniční trasu (OSRM)…"):
                road_km, used_osrm = get_driving_distance(
                    start_lat, start_lon, dest_lat, dest_lon
                )

            dist_help = (
                "Reálná silniční trasa (OSRM)"
                if used_osrm
                else "Záložní odhad: vzdušná vzdálenost × 1,3 (OSRM nedostupné)"
            )
            dist = road_km
            quote = _domestic_compute_quote(
                dist, waha, ldm, profile, sazba, vehicle_key
            )

            start_short = start_loc["display_name"].split(",")[0].strip()
            dest_short = dest_loc["display_name"].split(",")[0].strip()
            st.markdown(
                "<div style='background:#E7F1FF; padding:12px; border-radius:8px; "
                "border-left:4px solid #0D6EFD; margin-bottom:16px;'>"
                "<span style='font-family:Syne, sans-serif; font-size:1.1rem; "
                "font-weight:700; color:#000000;'>"
                f"📍 {start_short} "
                f"<span style='font-size:0.85rem; color:#495057;'>"
                f"(PSČ: {start_loc.get('postcode', 'N/A')})</span> "
                f"&nbsp;➡️&nbsp; "
                f"{dest_short} "
                f"<span style='font-size:0.85rem; color:#495057;'>"
                f"(PSČ: {dest_loc.get('postcode', 'N/A')})</span>"
                "</span></div>",
                unsafe_allow_html=True,
            )

            st.markdown("**Vytížení vozidla (trasa + náklad)**")
            _render_domestic_capacity_bar(quote)

            if quote["overload"]:
                st.error(
                    f"🚨 POZOR: Náklad přesahuje kapacitu vozidla **{v_type}**! "
                    f"(Využití {quote['cap_pct']:.0f} % · max {format_num(max_w, 0)} kg / {max_l} LDM). "
                    f"Zvolte větší vozidlo nebo snižte náklad. **Cenu nelze spočítat.**",
                    icon="🚨",
                )

            ltl_koef = quote["ltl_koef"]
            cap_pct = quote["cap_pct"]
            price_czk = quote["price_czk"]

            m1, m2, m3 = st.columns(3)
            m1.metric(
                "Vzdálenost silniční",
                f"{format_num(road_km, 0)} km",
                help=dist_help,
            )
            m2.metric(
                "Využití kapacity",
                f"{cap_pct:.1f} %",
                help=f"Limituje {quote['binding']} · LTL koef. {ltl_koef:.2f}",
            )
            price_eur, eur_czk = _domestic_price_eur(price_czk)
            if quote["price_valid"] and price_czk is not None:
                eur_hint = (
                    f"≈ {format_num(price_eur, 0)} EUR"
                    if price_eur is not None
                    else "EUR: kurz ČNB nedostupný"
                )
                m3.metric(
                    "Odhadovaná cena k jednání",
                    f"{format_num(price_czk, 0)} CZK",
                    help=eur_hint,
                )
                if price_eur is not None and eur_czk:
                    st.caption(
                        f"**{format_num(price_eur, 0)} EUR** (dle kurzu ČNB {eur_czk:.4f} CZK/EUR)"
                    )
            else:
                m3.metric("Odhadovaná cena k jednání", "—")
                st.caption("Cena není k dispozici — přetížení vozidla.")

            request_text = _format_domestic_transport_request(
                start_loc=start_loc,
                dest_loc=dest_loc,
                v_type=v_type,
                weight_kg=waha,
                ldm=ldm,
                eur_pallets=int(eur_pallets),
                road_km=road_km,
                used_osrm=used_osrm,
                shipment=shipment_form,
            )
            st.markdown("---")
            st.markdown("**📋 Text poptávky pro dopravce (generováno automaticky)**")
            st.code(request_text, language="text")
            st.download_button(
                label="⬇️ Stáhnout poptávku jako textový soubor (.txt)",
                data=request_text.encode("utf-8-sig"),
                file_name=f"poptavka_dopravy_{now_prague().strftime('%Y-%m-%d')}.txt",
                mime="text/plain",
                use_container_width=True,
            )

            route_note = (
                "reálná silniční trasa (OSRM)"
                if used_osrm
                else "záložní odhad (vzdušná × 1,3)"
            )
            start_cc = start_loc.get("country", "CZ")
            dest_cc = dest_loc.get("country", "CZ")
            cross_border = start_cc != dest_cc
            border_note = " · přeshraniční trasa CZ↔SK" if cross_border else ""
            st.caption(
                f"{v_type} · max {format_num(max_w, 0)} kg / {max_l} LDM · "
                f"vzdálenost: {route_note}{border_note} · sazba {sazba:.1f} CZK/km · "
                f"start ({start_cc}): {start_loc['display_name']} · "
                f"cíl ({dest_cc}): {dest_loc['display_name']}"
            )

    st.markdown('<div class="section-divider"></div>', unsafe_allow_html=True)


# ──────────────────────────────────────────────────────────────────────────────
#  SEKCE 5: SOUHRNNÁ PŘEHLEDOVÁ TABULKA
# ──────────────────────────────────────────────────────────────────────────────

def render_summary_table() -> None:
    """Souhrnná tabulka všech klíčových indikátorů dashboardu."""

    section_header("📊", "Souhrnný Přehled — Klíčové Indikátory")

    rows = []
    ccy = get_display_currency()

    # Kovy — Copper, Aluminum: Westmetall LME Cash
    wm = fetch_westmetall()
    for mk, label in SUMMARY_WM_METALS.items():
        if wm and mk in wm:
            price_disp = usd_to_display(wm[mk]["price"], ccy)
            if price_disp is not None:
                rows.append({
                    "Kategorie": "⚙️ Kov",
                    "Indikátor": label,
                    "Hodnota":   f"{format_num(price_disp, 0)} {ccy}/t",
                    "Δ %":       "LME Cash",
                    "Trend":     "—",
                    "Zdroj":     "Westmetall",
                })

    # Ocel — Yahoo HRC
    steel = fetch_steel_yfinance()
    if steel:
        dp = steel.get("delta_pct", 0) or 0
        p_disp = usd_to_display(steel["price"], ccy)
        rows.append({
            "Kategorie": "⚙️ Kov",
            "Indikátor": "Steel (HRC)",
            "Hodnota":   f"{format_num(p_disp, 0)} {ccy}/t" if p_disp else "N/A",
            "Δ %":       f"{dp:+.2f}%",
            "Trend":     "▲" if steel.get("delta", 0) > 0 else "▼",
            "Zdroj":     "Yahoo Finance",
        })

    # Měny — ČNB pro CZK páry
    cnb = fetch_cnb_rates()
    if cnb:
        for code, label in [("USD", "USD/CZK"), ("EUR", "EUR/CZK"), ("CNY", "CNY/CZK")]:
            info = cnb.get(code)
            if info:
                rows.append({
                    "Kategorie": "💱 Měna",
                    "Indikátor": label,
                    "Hodnota":   f"{info['rate']:.4f} CZK",
                    "Δ %":       "ČNB denní",
                    "Trend":     "—",
                    "Zdroj":     "ČNB",
                })

    # Křížové kurzy — Yahoo
    eur_usd = fetch_yf_spot("EURUSD=X")
    if eur_usd:
        dp = eur_usd.get("delta_pct", 0) or 0
        rows.append({
            "Kategorie": "💱 Měna",
            "Indikátor": "EUR/USD",
            "Hodnota":   f"{eur_usd['price']:.4f}",
            "Δ %":       f"{dp:+.3f}%",
            "Trend":     "▲" if dp > 0 else ("▼" if dp < 0 else "—"),
            "Zdroj":     "Yahoo Finance",
        })
    if eur_usd and eur_usd["price"]:
        ue = 1.0 / eur_usd["price"]
        rows.append({
            "Kategorie": "💱 Měna",
            "Indikátor": "USD/EUR",
            "Hodnota":   f"{ue:.4f}",
            "Δ %":       "inverze EUR/USD",
            "Trend":     "—",
            "Zdroj":     "Yahoo Finance",
        })

    # Ropa — Brent v zvolené měně
    oil = fetch_oil_data()
    if oil and "brent" in oil:
        o = oil["brent"]
        p_disp = usd_to_display(o["price"], ccy)
        rows.append({
            "Kategorie": "🛢️ Energie",
            "Indikátor": o["name"],
            "Hodnota":   f"{format_oil_price(o['price'])}/bbl",
            "Δ %":       f"{o['delta_pct']:+.2f}%",
            "Trend":     "▲" if o["delta"] > 0 else "▼",
            "Zdroj":     "Yahoo Finance",
        })
    if oil and "wti" in oil:
        o = oil["wti"]
        rows.append({
            "Kategorie": "🛢️ Energie",
            "Indikátor": o["name"],
            "Hodnota":   f"${o['price']:.2f}/bbl",
            "Δ %":       f"{o['delta_pct']:+.2f}%",
            "Trend":     "▲" if o["delta"] > 0 else "▼",
            "Zdroj":     "Yahoo Finance",
        })

    # Logistika — výchozí železnice
    rows.append({
        "Kategorie": "🚚 Logistika",
        "Indikátor": "Transit Čína→ČR (vlak)",
        "Hodnota":   f"{TRANSIT_DAYS['Železniční doprava']} dní",
        "Δ %":       "ETA kalkulačka",
        "Trend":     "—",
        "Zdroj":     "Model",
    })

    if rows:
        df = pd.DataFrame(rows)
        st.dataframe(
            df,
            use_container_width=True,
            hide_index=True,
            height=min(len(df) * 38 + 42, 600),
            column_config={
                "Kategorie": st.column_config.TextColumn("Kategorie",    width="small"),
                "Indikátor": st.column_config.TextColumn("Indikátor",    width="medium"),
                "Hodnota":   st.column_config.TextColumn("Hodnota",      width="medium"),
                "Δ %":       st.column_config.TextColumn("Δ den/den",    width="small"),
                "Trend":     st.column_config.TextColumn("↕",            width="small"),
                "Zdroj":     st.column_config.TextColumn("Zdroj",        width="small"),
            },
        )
    else:
        st.markdown(
            '<div class="error-box" style="padding:20px;">'
            'Souhrnná data nejsou k dispozici.</div>',
            unsafe_allow_html=True,
        )

    st.markdown('<div class="section-divider"></div>', unsafe_allow_html=True)


# ──────────────────────────────────────────────────────────────────────────────
#  FOOTER
# ──────────────────────────────────────────────────────────────────────────────

def render_footer() -> None:
    """Footer s metadaty a upozorněním."""
    now = now_prague()
    st.markdown(f"""
    <div class="dash-footer">
        <div>⚡ Kabelářský Nákupní Dashboard &nbsp;·&nbsp; v2.0.0 &nbsp;·&nbsp; Python + Streamlit</div>
        <div>
            Zdroje: westmetall.com (LME Cash) &nbsp;·&nbsp; ČNB &nbsp;·&nbsp;
            Yahoo Finance (grafy, ocel HRC, ropa BZ=F) &nbsp;·&nbsp; Transitní model Čína→ČR
        </div>
        <div>
            Generováno: {now.strftime("%d.%m.%Y %H:%M:%S")} &nbsp;·&nbsp;
            Cache TTL: 3600 s &nbsp;·&nbsp;
            Bez placených API klíčů &nbsp;·&nbsp; Bez SQL databází
        </div>
        <div style="margin-top:6px;">
            ⚠️ Veškeré ceny a výpočty jsou orientační. Neslouží jako investiční poradenství.
            Data jsou stahována z veřejně dostupných zdrojů a mohou se zpozdit nebo být nepřesná.
        </div>
    </div>
    """, unsafe_allow_html=True)


# ==============================================================================
# ─────────────────────────────────────────────────────────────────────────────
#  ENTRY POINT
# ─────────────────────────────────────────────────────────────────────────────
# ==============================================================================

def main() -> None:
    """Hlavní funkce – sestaví celý dashboard voláním dílčích render funkcí."""
    _render_app_branding()
    render_data_export()
    render_header()
    render_global_controls()

    is_supplier = st.session_state.get("user_role") == "supplier"

    tabs_list = [
        "🔩 Kovy & Trh",
        "💱 Měnové kurzy",
        "🛢️ Plasty & Ropa",
        "🚛 Logistika ČR & SK",
        "📊 Souhrnný přehled",
    ]

    if not is_supplier:
        tabs_list.insert(3, "🚢 Nákup & Logistika")

    tabs = st.tabs(tabs_list)

    with tabs[0]:
        render_metals()

    with tabs[1]:
        render_fx()

    with tabs[2]:
        render_oil_plastics()

    if not is_supplier:
        with tabs[3]:
            render_landed_cost_pricing()
            render_logistics()
        with tabs[4]:
            render_domestic_logistics()
        with tabs[5]:
            render_summary_table()
    else:
        with tabs[3]:
            render_domestic_logistics()
        with tabs[4]:
            render_summary_table()

    render_footer()


if __name__ == "__main__":
    main()
