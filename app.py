# ==============================================================================
# KABELÁŘSKÝ NÁKUPNÍ DASHBOARD — app.py
# Verze: 2.0.0
# Popis: Inteligentní nákupní dashboard pro kabelářský průmysl.
#        Sleduje ceny LME kovů, čínský spot (CCMN), FX kurzy, ceny ropy (BZ=F + SMA)
#        a kalkulačku transitního času Čína→ČR. Data jsou stahována živě
#        ze zdarma dostupných zdrojů bez placených API klíčů.
# Stack: Streamlit · Pandas · Plotly · BeautifulSoup4 · lxml · requests · yfinance
# ==============================================================================

# ── Standardní knihovny ────────────────────────────────────────────────────────
import base64
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

try:
    from helukabel_tables import (
        ktg_min_drums_for_bend,
        ktg_wood_drums,
        render_helukabel_catalog,
    )
except ImportError:  # chybí soubor na deployi (např. nepushnutý na GitHub)
    render_helukabel_catalog = None  # type: ignore[assignment]
    ktg_min_drums_for_bend = None  # type: ignore[assignment]
    ktg_wood_drums = None  # type: ignore[assignment]

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

/* ── Základ: grafitový (charcoal) gradient s barevnými zářemi ─────────── */
.stApp {
    background:
        radial-gradient(1100px 520px at 88% -8%, rgba(77,159,255,0.10), transparent 60%),
        radial-gradient(900px 480px at -8% 28%, rgba(253,126,20,0.07), transparent 55%),
        radial-gradient(1000px 640px at 108% 82%, rgba(52,201,142,0.06), transparent 60%),
        linear-gradient(180deg, #171B22 0%, #14181F 55%, #191C22 100%) !important;
    color: #E9EDF3 !important;
    font-family: 'Syne', sans-serif !important;
}

[data-testid="stAppViewContainer"],
[data-testid="stMain"],
section[data-testid="stMain"] > div:first-child {
    background: transparent !important;
    color: #E9EDF3 !important;
    font-family: 'Syne', sans-serif !important;
}

h1, h2, h3, h4, h5 { color: #F2F5F9 !important; }

/* ── Dekorativní "kabelové svazky" po krajích obrazovky ───────────────── */
.stApp::before,
.stApp::after {
    content: '';
    position: fixed;
    top: 0;
    bottom: 0;
    width: 300px;
    z-index: 0;
    pointer-events: none;
    opacity: 0.5;
    background-image: url("data:image/svg+xml,%3Csvg%20xmlns='http://www.w3.org/2000/svg'%20width='300'%20height='900'%20viewBox='0%200%20300%20900'%20fill='none'%3E%3Cpath%20d='M70%200C150%20112%20-10%20338%2070%20450C150%20562%20-10%20788%2070%20900'%20stroke='%230D6EFD'%20stroke-width='5'%20stroke-linecap='round'%20opacity='0.5'/%3E%3Cpath%20d='M82%200C162%20112%202%20338%2082%20450C162%20562%202%20788%2082%20900'%20stroke='%230D6EFD'%20stroke-width='5'%20opacity='0.32'/%3E%3Cpath%20d='M150%200C70%20112%20230%20338%20150%20450C70%20562%20230%20788%20150%20900'%20stroke='%23FD7E14'%20stroke-width='4'%20opacity='0.45'/%3E%3Cpath%20d='M220%200C300%20112%20140%20338%20220%20450C300%20562%20140%20788%20220%20900'%20stroke='%23198754'%20stroke-width='4'%20opacity='0.40'/%3E%3Cpath%20d='M35%200C-45%20112%20115%20338%2035%20450C-45%20562%20115%20788%2035%20900'%20stroke='%23DC3545'%20stroke-width='3'%20opacity='0.35'/%3E%3Cpath%20d='M265%200C185%20112%20345%20338%20265%20450C185%20562%20345%20788%20265%20900'%20stroke='%236C757D'%20stroke-width='3'%20opacity='0.30'/%3E%3C/svg%3E");
    background-repeat: repeat-y;
    background-size: 300px 900px;
}

.stApp::before { left: -60px; }
.stApp::after { right: -60px; transform: scaleX(-1); }

@media (max-width: 1200px) {
    .stApp::before, .stApp::after { display: none; }
}

/* Obsah nad dekorací + decentní vycentrování na velkých monitorech */
[data-testid="stMain"] { position: relative; z-index: 1; }
[data-testid="stMainBlockContainer"],
.block-container {
    max-width: 1680px;
    margin: 0 auto;
}

p, span, label, .stMarkdown { color: #D6DDE7; }

#MainMenu { visibility: hidden; }
header[data-testid="stHeader"] { visibility: hidden; height: 0; }
footer { visibility: hidden; }
[data-testid="stDecoration"] { display: none; }
[data-testid="stStatusWidget"] { display: none; }

[data-testid="stSidebar"],
[data-testid="stSidebarContent"] {
    background-color: #1A1F28 !important;
    border-right: 1px solid #2C3442 !important;
}

::-webkit-scrollbar { width: 6px; height: 6px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: #3A4454; border-radius: 4px; }

/* ── Hlavička: tmavé sklo + gradientní linka ───────────────────────────── */
.dash-header {
    background: rgba(30, 36, 46, 0.82);
    backdrop-filter: blur(14px);
    -webkit-backdrop-filter: blur(14px);
    border: 1px solid rgba(77, 159, 255, 0.16);
    border-radius: 20px;
    padding: 24px 32px 20px;
    margin-bottom: 20px;
    box-shadow: 0 2px 6px rgba(0, 0, 0, 0.25), 0 18px 40px -18px rgba(0, 0, 0, 0.5);
    position: relative;
    overflow: hidden;
}

.dash-header::before {
    content: '';
    position: absolute;
    top: 0; left: 0; right: 0;
    height: 4px;
    background: linear-gradient(90deg, #4D9FFF, #8B5CF6, #FD7E14, #34C98E);
    border-radius: 20px 20px 0 0;
}

.dash-header-content {
    display: flex;
    justify-content: space-between;
    align-items: center;
    flex-wrap: wrap;
    gap: 16px;
}

.dash-brand {
    display: flex;
    align-items: center;
    gap: 18px;
}

.dash-logo {
    flex-shrink: 0;
    background: #FFFFFF;
    border-radius: 14px;
    padding: 7px 12px;
    display: flex;
    align-items: center;
    box-shadow: 0 4px 14px rgba(0, 0, 0, 0.35);
}

.dash-logo img {
    height: 52px;
    display: block;
}

.dash-title {
    font-family: 'Syne', sans-serif;
    font-size: 2rem;
    font-weight: 800;
    color: #F2F5F9;
    margin: 0 0 6px 0;
}

.dash-title span {
    background: linear-gradient(120deg, #4D9FFF, #A78BFA);
    -webkit-background-clip: text;
    background-clip: text;
    color: transparent;
}

.dash-subtitle {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.72rem;
    color: #8D99AB;
    letter-spacing: 1.5px;
    text-transform: uppercase;
}

.dash-timestamp {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.75rem;
    color: #B8C2D0;
    line-height: 1.7;
}

.dash-timestamp strong { color: #F2F5F9; }

.badge {
    display: inline-flex;
    align-items: center;
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.65rem;
    font-weight: 600;
    padding: 4px 12px;
    border-radius: 100px;
    box-shadow: 0 1px 3px rgba(15, 23, 42, 0.08);
}

.badge-live { background: rgba(52, 201, 142, 0.14); color: #4ADE9C; border: 1px solid rgba(52, 201, 142, 0.4); }
.badge-offline { background: rgba(240, 86, 94, 0.14); color: #F58489; border: 1px solid rgba(240, 86, 94, 0.4); }
.badge-model { background: rgba(250, 204, 21, 0.12); color: #E8C654; border: 1px solid rgba(250, 204, 21, 0.35); }

.section-header {
    display: flex;
    align-items: center;
    flex-wrap: wrap;
    gap: 10px 12px;
    margin: 24px 0 16px 0;
    padding-bottom: 12px;
    position: relative;
    border-bottom: 1px solid #2C3442;
}

.section-header::after {
    content: '';
    position: absolute;
    left: 0;
    bottom: -1px;
    width: 96px;
    height: 3px;
    border-radius: 3px;
    background: linear-gradient(90deg, #4D9FFF, #8B5CF6);
}

.section-title {
    font-family: 'Syne', sans-serif;
    font-size: 1rem;
    font-weight: 700;
    color: #F2F5F9;
    text-transform: uppercase;
    letter-spacing: 1.2px;
}

.metric-card {
    position: relative;
    background: linear-gradient(160deg, rgba(35, 42, 54, 0.95), rgba(27, 32, 41, 0.95));
    border: 1px solid #2C3442;
    border-radius: 16px;
    padding: 16px 16px 16px 20px;
    margin-bottom: 10px;
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.25), 0 14px 28px -16px rgba(0, 0, 0, 0.45);
    transition: transform 0.18s ease, box-shadow 0.18s ease, border-color 0.18s ease;
    overflow: hidden;
}

.metric-card:hover {
    transform: translateY(-2px);
    border-color: #3D4859;
    box-shadow: 0 2px 5px rgba(0, 0, 0, 0.3), 0 22px 40px -18px rgba(0, 0, 0, 0.6);
}

.metric-card::before {
    content: '';
    position: absolute;
    top: 0; left: 0;
    width: 5px;
    height: 100%;
    border-radius: 16px 0 0 16px;
}

.card-copper::before { background: #FD7E14; }
.card-aluminum::before { background: #A8B2C1; }
.card-usd::before { background: #34C98E; }
.card-eur::before { background: #4D9FFF; }
.card-cny::before { background: #F0565E; }
.card-oil::before { background: #FACC15; }
.card-plastic::before { background: #2DD4BF; }
.card-logistics::before { background: #A78BFA; }
.card-neutral::before { background: #64748B; }
.card-lead::before { background: #A78BFA; }
.card-zinc::before { background: #818CF8; }
.card-tin::before { background: #F472B6; }
.card-nickel::before { background: #22D3EE; }

.card-label {
    font-size: 0.68rem;
    font-weight: 700;
    color: #8D99AB;
    text-transform: uppercase;
    margin-bottom: 8px;
}

.card-value {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 1.45rem;
    font-weight: 700;
    color: #F7FAFD;
    margin-bottom: 6px;
}

.card-value-sm { font-size: 1.1rem; }
.card-unit {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.85rem;
    font-weight: 600;
    color: #B8C2D0;
    margin: 4px 0 8px 0;
    letter-spacing: 0.4px;
}
.card-unit-emphasis {
    font-size: 1.2rem;
    font-weight: 700;
    color: #F2F5F9;
    margin: 8px 0 12px 0;
    letter-spacing: 0.6px;
    text-transform: uppercase;
}
.card-extra {
    font-size: 0.78rem;
    font-weight: 500;
    color: #9AA6B8;
    line-height: 1.45;
    margin-top: 8px;
}
.card-extra-emphasis {
    font-size: 1rem;
    font-weight: 700;
    color: #E9EDF3;
    margin-top: 14px;
    padding-top: 10px;
    border-top: 1px solid #2C3442;
    line-height: 1.5;
}
.card-delta-row { margin-top: 6px; display: flex; gap: 6px; flex-wrap: wrap; }

.metal-price-grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 0;
    margin-top: 8px;
    border: 1px solid #2C3442;
    border-radius: 12px;
    overflow: hidden;
    background: rgba(20, 24, 31, 0.35);
}

.metal-price-col {
    min-width: 0;
    padding: 12px 14px 14px;
}

.metal-price-col-lme {
    background: rgba(77, 159, 255, 0.05);
}

.metal-price-col-ccmn {
    border-left: 1px solid #2C3442;
    background: rgba(250, 204, 21, 0.04);
}

.metal-price-region {
    font-family: 'Syne', sans-serif;
    font-size: 0.72rem;
    font-weight: 800;
    color: #F2F5F9;
    letter-spacing: 1.1px;
    text-transform: uppercase;
    margin-bottom: 2px;
}

.metal-price-src {
    font-size: 0.58rem;
    font-weight: 600;
    color: #8D99AB;
    text-transform: uppercase;
    letter-spacing: 0.6px;
    margin-bottom: 6px;
}

.metal-price-sub {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.68rem;
    color: #9AA6B8;
    margin-top: 4px;
}

.card-spark {
    margin-top: 8px;
    line-height: 0;
}

.card-spark svg {
    width: 100%;
    max-width: 220px;
    height: 36px;
    display: block;
}

.fill-gallery {
    display: grid;
    grid-template-columns: repeat(5, 1fr);
    gap: 10px;
    margin: 8px 0 6px;
}
.fill-gallery-card {
    background: linear-gradient(160deg, rgba(35, 42, 54, 0.95), rgba(27, 32, 41, 0.95));
    border: 1px solid #2C3442;
    border-radius: 10px;
    padding: 10px 8px 10px;
    text-align: center;
}
.fill-gallery-card svg {
    width: 56px;
    height: 56px;
    display: block;
    margin: 0 auto 6px;
}
.fill-gallery-title {
    font-family: 'Syne', sans-serif;
    font-size: 0.88rem;
    font-weight: 700;
    color: #F2F5F9;
}
.fill-gallery-sub {
    font-size: 0.72rem;
    color: #8D99AB;
    margin: 3px 0 8px;
    line-height: 1.3;
    min-height: 2.2em;
}
.fill-card-vals {
    display: flex;
    flex-direction: column;
    gap: 4px;
}
.fill-card-row {
    display: flex;
    justify-content: space-between;
    align-items: baseline;
    gap: 6px;
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.82rem;
    font-weight: 700;
    padding: 5px 8px;
    border-radius: 6px;
    line-height: 1.3;
    text-align: left;
}
.fill-card-row > span:last-child {
    text-align: right;
}
.fill-card-ff {
    display: block;
    font-size: 0.72rem;
    font-weight: 600;
    opacity: 0.9;
    margin-top: 2px;
}
.fill-card-row.fill-min {
    background: rgba(240, 86, 94, 0.14);
    color: #F58489;
}
.fill-card-row.fill-gold {
    background: rgba(250, 204, 21, 0.14);
    color: #FACC15;
}
.fill-card-row.fill-max {
    background: rgba(52, 201, 142, 0.14);
    color: #4ADE9C;
}
.fill-chip {
    display: inline-block;
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.8rem;
    font-weight: 700;
    padding: 3px 8px;
    border-radius: 6px;
    white-space: nowrap;
}
.fill-min { color: #F58489; }
.fill-gold { color: #FACC15; }
.fill-max { color: #4ADE9C; }
.fill-legend {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    margin: 4px 0 6px;
    align-items: center;
    font-size: 0.85rem;
}
@media (max-width: 900px) {
    .fill-gallery { grid-template-columns: repeat(3, 1fr); }
}
@media (max-width: 520px) {
    .fill-gallery { grid-template-columns: 1fr; }
}

.delta-chip {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.72rem;
    padding: 2px 8px;
    border-radius: 6px;
}

.delta-up { background: rgba(52, 201, 142, 0.14); color: #4ADE9C; }
.delta-down { background: rgba(240, 86, 94, 0.14); color: #F58489; }
.delta-flat { background: rgba(141, 153, 171, 0.14); color: #9AA6B8; }

.spread-card {
    background: linear-gradient(160deg, rgba(35, 42, 54, 0.95), rgba(27, 32, 41, 0.95));
    border: 1px solid #2C3442;
    border-radius: 14px;
    padding: 12px 14px;
    margin-bottom: 8px;
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.25), 0 10px 22px -14px rgba(0, 0, 0, 0.4);
}

.spread-label { font-size: 0.65rem; font-weight: 700; color: #8D99AB; text-transform: uppercase; }
.spread-value { font-family: 'IBM Plex Mono', monospace; font-size: 1.2rem; font-weight: 700; color: #F7FAFD; }
.spread-details { font-size: 0.68rem; color: #9AA6B8; }

.chart-wrap {
    background: rgba(30, 36, 46, 0.92);
    border: 1px solid #2C3442;
    border-radius: 16px;
    padding: 16px 12px;
    margin-bottom: 12px;
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.25), 0 12px 26px -16px rgba(0, 0, 0, 0.4);
}

/* ── Mobil & tablet: kompaktní rozvržení, posuvné taby ─────────────────── */
@media (max-width: 768px) {
    .block-container {
        padding-left: 0.8rem !important;
        padding-right: 0.8rem !important;
        padding-top: 1rem !important;
    }
    .dash-title { font-size: 1.3rem; }
    .dash-header { padding: 16px 18px 14px; border-radius: 16px; }
    .dash-brand { gap: 12px; }
    .dash-logo { border-radius: 10px; padding: 5px 8px; }
    .dash-logo img { height: 34px; }
    .metal-price-grid {
        grid-template-columns: 1fr;
        gap: 0;
    }
    .metal-price-col-ccmn {
        border-left: none;
        border-top: 1px solid #2C3442;
    }
    .metric-card { padding: 12px 12px 12px 16px; }
    .card-value { font-size: 1.2rem; }
    .card-unit-emphasis { font-size: 1.05rem; }
    .card-extra-emphasis { font-size: 0.92rem; }
    .section-title { font-size: 0.85rem; }
    [data-testid="stHorizontalBlock"] { flex-direction: column !important; }
    [data-testid="stHorizontalBlock"] > div { width: 100% !important; }
    [data-testid="stTabs"] { padding: 6px 8px 14px 8px; border-radius: 14px; }
    [data-testid="stTabs"] button {
        font-size: 0.88rem !important;
        padding: 6px 10px !important;
        white-space: nowrap !important;
    }
    [data-testid="stTabs"] [data-baseweb="tab-list"] {
        overflow-x: auto !important;
        flex-wrap: nowrap !important;
        scrollbar-width: none;
    }
    [data-testid="stTabs"] [data-baseweb="tab-list"]::-webkit-scrollbar { display: none; }
    .chart-wrap { padding: 10px 4px; border-radius: 12px; }
    .currency-bar { padding: 10px 12px; }
}

.info-box {
    background: rgba(77, 159, 255, 0.08);
    border: 1px solid rgba(77, 159, 255, 0.28);
    border-left: 4px solid #4D9FFF;
    border-radius: 10px;
    padding: 10px 14px;
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.78rem;
    color: #C9D3E0;
    line-height: 1.55;
    margin: 8px 0;
}

.info-box strong { color: #E9EDF3; }

.warning-box {
    background: rgba(250, 204, 21, 0.09);
    border: 1px solid rgba(250, 204, 21, 0.35);
    border-left: 4px solid #FACC15;
    border-radius: 10px;
    padding: 10px 14px;
    font-size: 0.78rem;
    color: #E8C654;
}

.error-box {
    background: rgba(240, 86, 94, 0.10);
    border: 1px solid rgba(240, 86, 94, 0.32);
    border-radius: 10px;
    padding: 10px 14px;
    font-size: 0.75rem;
    color: #F58489;
    text-align: center;
}

.success-box {
    background: rgba(52, 201, 142, 0.12);
    border: 1px solid rgba(52, 201, 142, 0.45);
    border-left: 4px solid #34C98E;
    border-radius: 10px;
    padding: 12px 14px;
    font-size: 0.85rem;
    color: #4ADE9C;
    font-weight: 600;
    line-height: 1.55;
    margin: 8px 0;
}

.success-box strong { color: #7FEBC0; }
.warning-box strong { color: #F5DA7A; }

.briefing-grid {
    display: grid;
    grid-template-columns: repeat(6, minmax(0, 1fr));
    gap: 8px;
    margin: 4px 0 10px 0;
}
@media (max-width: 1100px) {
    .briefing-grid { grid-template-columns: repeat(3, minmax(0, 1fr)); }
}
@media (max-width: 640px) {
    .briefing-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
.briefing-tile {
    background: rgba(30, 36, 46, 0.92);
    border: 1px solid #2C3442;
    border-radius: 12px;
    padding: 10px 12px;
    border-left: 3px solid #3D4859;
}
.briefing-tile.ok { border-left-color: #34C98E; }
.briefing-tile.warn { border-left-color: #FACC15; }
.briefing-tile.bad { border-left-color: #F0565E; }
.briefing-tile .bl {
    font-family: 'Syne', sans-serif;
    font-size: 0.62rem;
    font-weight: 700;
    letter-spacing: 0.7px;
    text-transform: uppercase;
    color: #8D99AB;
}
.briefing-tile .bv {
    font-family: 'Syne', sans-serif;
    font-size: 1.12rem;
    font-weight: 700;
    color: #E9EDF3;
    margin-top: 2px;
    line-height: 1.2;
}
.briefing-tile .bs {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.68rem;
    color: #8D99AB;
    margin-top: 4px;
}

.data-table-wrap {
    background: rgba(30, 36, 46, 0.92);
    border: 1px solid #2C3442;
    border-radius: 16px;
    padding: 16px;
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.25), 0 12px 26px -16px rgba(0, 0, 0, 0.4);
}

.data-table-wrap table { width: 100%; border-collapse: collapse; }
.data-table-wrap th { color: #F2F5F9; border-bottom: 2px solid #3D4859; padding: 8px 12px; }
.data-table-wrap td { color: #C9D3E0; border-bottom: 1px solid #262D39; padding: 9px 12px; }
.data-table-wrap tr:hover td { background: #232A36; }

.section-divider {
    height: 1px;
    background: linear-gradient(90deg, transparent, #3A4454 20%, #3A4454 80%, transparent);
    margin: 24px 0;
}

.dash-footer {
    text-align: center;
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.68rem;
    color: #8D99AB;
    padding: 20px 0;
    border-top: 1px solid #2C3442;
    margin-top: 32px;
}

button[kind="primary"],
button[data-testid="baseButton-primary"] {
    background: linear-gradient(135deg, #2E7CE8, #4D9FFF) !important;
    color: #FFFFFF !important;
    border: none !important;
    font-weight: 700 !important;
    border-radius: 10px !important;
    box-shadow: 0 6px 16px -6px rgba(77, 159, 255, 0.5) !important;
}

button[kind="secondary"],
.stButton > button {
    background: rgba(35, 42, 54, 0.9) !important;
    border: 1.5px solid #3A4454 !important;
    color: #7DB8FF !important;
    font-weight: 600 !important;
    border-radius: 10px !important;
    transition: background 0.15s ease, border-color 0.15s ease !important;
}

button[kind="secondary"]:hover { background: rgba(77, 159, 255, 0.12) !important; border-color: #4D9FFF !important; }

[data-testid="stExpander"] {
    background: rgba(30, 36, 46, 0.9) !important;
    border: 1px solid #2C3442 !important;
    border-radius: 14px !important;
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.25), 0 10px 22px -14px rgba(0, 0, 0, 0.35) !important;
}

[data-testid="stTabs"] {
    background: rgba(28, 33, 43, 0.85);
    backdrop-filter: blur(10px);
    -webkit-backdrop-filter: blur(10px);
    padding: 10px 20px 20px 20px;
    border-radius: 18px;
    border: 1px solid #2C3442;
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.25), 0 18px 38px -20px rgba(0, 0, 0, 0.5);
}
[data-testid="stTabs"] button {
    font-family: 'Syne', sans-serif !important;
    font-weight: 700 !important;
    font-size: 1.05rem !important;
    border-radius: 10px 10px 0 0 !important;
}
[data-testid="stTabs"] button:hover { background: rgba(77, 159, 255, 0.08) !important; }
[data-testid="stTabs"] [data-baseweb="tab-highlight"] {
    background: linear-gradient(90deg, #4D9FFF, #8B5CF6) !important;
    height: 3px !important;
    border-radius: 3px !important;
}
[data-testid="stTabs"] [data-baseweb="tab-border"] { background: #2C3442 !important; }

details summary {
    font-family: 'Syne', sans-serif !important;
    font-weight: 700 !important;
    color: #F2F5F9 !important;
}

[data-testid="stNumberInput"] input,
[data-testid="stDateInput"] input,
[data-testid="stTextInput"] input {
    background: #171C24 !important;
    border: 1.5px solid #323B4A !important;
    border-radius: 10px !important;
    color: #E9EDF3 !important;
    font-family: 'IBM Plex Mono', monospace !important;
}

[data-testid="stSelectbox"] > div > div {
    background: #171C24 !important;
    border: 1.5px solid #323B4A !important;
    border-radius: 10px !important;
    color: #E9EDF3 !important;
}

[data-baseweb="popover"] [data-baseweb="menu"],
[data-baseweb="popover"] ul {
    background: #1E242E !important;
    color: #E9EDF3 !important;
}

[data-testid="stDataFrame"] {
    border: 1px solid #2C3442 !important;
    border-radius: 14px !important;
}

[data-testid="stRadio"] label {
    background: rgba(35, 42, 54, 0.9) !important;
    border: 1.5px solid #3A4454 !important;
    border-radius: 100px !important;
    color: #C9D3E0 !important;
    font-weight: 600 !important;
    padding: 4px 14px !important;
    transition: border-color 0.15s ease, background 0.15s ease !important;
}

[data-testid="stRadio"] label[data-checked="true"],
[data-testid="stRadio"] div[aria-checked="true"] label {
    border-color: #4D9FFF !important;
    color: #FFFFFF !important;
    background: linear-gradient(135deg, #2E7CE8, #4D9FFF) !important;
    box-shadow: 0 4px 12px -4px rgba(77, 159, 255, 0.45) !important;
}

[data-testid="stSegmentedControl"] {
    background: #1A1F28 !important;
    border: 1px solid #2C3442 !important;
    border-radius: 12px !important;
}

.currency-bar {
    background: rgba(28, 33, 43, 0.88);
    backdrop-filter: blur(10px);
    -webkit-backdrop-filter: blur(10px);
    border: 1px solid #2C3442;
    border-radius: 16px;
    padding: 14px 18px;
    margin-bottom: 16px;
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.25), 0 14px 30px -18px rgba(0, 0, 0, 0.45);
}

.currency-bar-label {
    font-weight: 700;
    color: #F2F5F9;
    text-transform: uppercase;
}

.currency-bar-hint { color: #8D99AB; }

[data-testid="stMetricLabel"] { color: #8D99AB !important; font-weight: 700 !important; }
[data-testid="stMetricValue"] { color: #F7FAFD !important; font-weight: 700 !important; }

.stProgress > div > div > div > div {
    background: linear-gradient(90deg, #4D9FFF, #34C98E) !important;
}
.stProgress > div > div > div { background-color: #262D39 !important; }

[data-testid="stHorizontalBlock"] { gap: 0.65rem !important; }
div[data-testid="column"] {
    padding-left: 6px !important;
    padding-right: 6px !important;
    margin-bottom: 8px !important;
}

</style>
"""


def _render_app_branding() -> None:
    """Globální CSS (až po ověření přístupu). Logo je součástí dash-headeru."""
    st.markdown(CUSTOM_CSS, unsafe_allow_html=True)


@st.cache_data
def _logo_data_uri() -> str | None:
    """logo.png jako base64 data-URI pro vložení do HTML záhlaví."""
    try:
        raw = Path("logo.png").read_bytes()
        return "data:image/png;base64," + base64.b64encode(raw).decode("ascii")
    except Exception:
        return None


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
    delta_html: str | None = None,
    sparkline_html: str | None = None,
) -> str:
    """Sestaví HTML pro metrickou kartu a vrátí jako řetězec."""
    delta_row = f'<div class="card-delta-row">{delta_html or delta_chip(delta, delta_suffix)}</div>'
    extra_cls = "card-extra card-extra-emphasis" if emphasis else "card-extra"
    unit_cls = "card-unit card-unit-emphasis" if emphasis else "card-unit"
    extra_row = f'<div class="{extra_cls}">{extra}</div>' if extra else ""
    spark_row = f'<div class="card-spark">{sparkline_html}</div>' if sparkline_html else ""
    size_cls = " card-value-sm" if value_size == "sm" else ""
    return f"""
    <div class="metric-card {card_class}">
        <div class="card-label">{label}</div>
        <div class="card-value{size_cls}">{value}</div>
        <div class="{unit_cls}">{unit}</div>
        {delta_row}
        {spark_row}
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


def _show_plotly(fig: go.Figure | None, *, toolbar: bool = False) -> None:
    """Vykreslí Plotly graf v chart-wrap kontejneru (bez modebaru — mobil-friendly)."""
    if fig is None:
        return
    _ensure_plot_separators(fig)
    st.markdown('<div class="chart-wrap">', unsafe_allow_html=True)
    st.plotly_chart(
        fig,
        use_container_width=True,
        config={
            "displayModeBar": toolbar,
            "displaylogo": False,
            "responsive": True,
            "scrollZoom": False,
        },
    )
    st.markdown("</div>", unsafe_allow_html=True)


_LME_METAL_CARDS: list[tuple[str, str, str, str]] = [
    ("copper", "Měď (Cu)", "card-copper", "copper_stock"),
    ("aluminum", "Hliník (Al)", "card-aluminum", "aluminum_stock"),
]

_CCMN_SPREAD_METALS = [("copper", "Měď"), ("aluminum", "Hliník")]

_CNB_METRIC_CARDS = [
    ("USD", "USD/CZK", "Americký dolar", "card-usd"),
    ("EUR", "EUR/CZK", "Euro", "card-eur"),
    ("CNY", "CNY/CZK", "Čínský jüan", "card-cny"),
]


# Období pro procentní změny na kartách kovů (label chipu, počet dní)
_METAL_TREND_PERIODS: list[tuple[str, int]] = [("7D", 7), ("1M", 30), ("3M", 90)]


def _wm_trend_pct(metal_key: str, days: int) -> float | None:
    """% změna LME Cash za posledních N dní (z historie Westmetall)."""
    try:
        df = fetch_westmetall_history(WM_HISTORY_URLS[metal_key])
        if df is None or df.empty:
            return None
        df = df.dropna(subset=["Close"]).sort_values("Date")
        last_date = df["Date"].iloc[-1]
        last = float(df["Close"].iloc[-1])
        past = df[df["Date"] <= last_date - pd.Timedelta(days=days)]
        if past.empty:
            return None
        ref = float(past["Close"].iloc[-1])
        if ref == 0:
            return None
        return (last / ref - 1.0) * 100.0
    except Exception:
        return None


def _trend_chip(label: str, pct: float | None) -> str:
    """Chip „7D ▲ +1.2 %“ — zelený růst, červený pokles, šedý beze změny."""
    if pct is None:
        return f'<span class="delta-chip delta-flat">{label} — N/A</span>'
    if pct > 0.05:
        return f'<span class="delta-chip delta-up">{label} ▲ +{format_num(pct, 1)} %</span>'
    if pct < -0.05:
        return f'<span class="delta-chip delta-down">{label} ▼ {format_num(pct, 1)} %</span>'
    return f'<span class="delta-chip delta-flat">{label} — 0.0 %</span>'


def _metal_trend_chips(metal_key: str) -> str:
    """HTML chipy procentních změn (7D / 1M / 3M) pro kartu kovu."""
    return "".join(
        _trend_chip(lbl, _wm_trend_pct(metal_key, days))
        for lbl, days in _METAL_TREND_PERIODS
    )


def _rsi_chip(metal_key: str) -> str:
    """Chip s RSI (14) a krátkou interpretací pro kartu kovu."""
    rsi = _metal_rsi_value(metal_key)
    if rsi is None:
        return ""
    msg, alert_type = interpret_rsi(rsi)
    cls = {"success": "delta-up", "warning": "delta-down"}.get(alert_type, "delta-flat")
    short = msg.split(" (")[0]
    return (
        f'<span class="delta-chip {cls}" title="RSI (14) · {msg} · zdroj: Westmetall">'
        f"RSI {rsi:.1f} · {short}</span>"
    )


def _ccmn_price_block(metal_key: str, lme_usd: float | None, unit: str, ccy: str) -> str:
    """HTML blok s cenou CCMN spotu (Čína) pro kartu kovu — vč. CNY a % vs LME."""
    china_usd, _, cny_price = get_ccmn_china_usd(metal_key)
    if china_usd is None and cny_price is None:
        return (
            '<div class="card-value card-value-sm">N/A</div>'
            '<div class="metal-price-sub">ccmn.cn momentálně nedostupné</div>'
        )
    china_disp = usd_to_display(china_usd, ccy) if china_usd is not None else None
    if china_disp is None:
        # chybí kurz pro přepočet — ukaž alespoň originál v CNY
        return (
            f'<div class="card-value">{format_num(cny_price, 0)}</div>'
            f'<div class="card-unit card-unit-emphasis">CNY / TONA</div>'
            '<div class="metal-price-sub">chybí kurz pro přepočet</div>'
        )
    sub_bits = [f"{format_num(cny_price, 0)} CNY/t"]
    spread_pct = _ccmn_vs_lme_spread_pct(china_usd, lme_usd) if lme_usd else None
    if spread_pct is not None:
        sign = "+" if spread_pct >= 0 else ""
        sub_bits.append(f"{sign}{format_num(spread_pct, 1)} % vs LME")
    return (
        f'<div class="card-value">{format_num(china_disp, 0)}</div>'
        f'<div class="card-unit card-unit-emphasis">{unit}</div>'
        f'<div class="metal-price-sub">{" · ".join(sub_bits)}</div>'
    )


def _render_lme_metal_card(
    metal_key: str,
    label: str,
    card_class: str,
    stock_key: str,
    wm_data: dict | None,
) -> None:
    """Metrická karta kovu — LME Cash (Westmetall) + CCMN spot (Čína) vedle sebe."""
    price_usd, _, _ = resolve_metal_price(metal_key, wm_data)
    unit = metal_unit_label()
    ccy = get_display_currency()
    stock_extra = wm_stock_extra(wm_data, stock_key)

    if price_usd is None:
        st.markdown(
            error_card(label, card_class, "Data nedostupná · Westmetall"),
            unsafe_allow_html=True,
        )
        return
    price_disp = usd_to_display(price_usd, ccy)
    if price_disp is None and ccy == "EUR":
        st.markdown(
            error_card(label, card_class, "N/A — chybí EUR/USD"),
            unsafe_allow_html=True,
        )
        return

    chips = _metal_trend_chips(metal_key) + _rsi_chip(metal_key)
    extra = stock_extra or "Westmetall LME Cash"
    st.markdown(
        f"""
    <div class="metric-card {card_class}">
        <div class="card-label">{label}</div>
        <div class="metal-price-grid">
            <div class="metal-price-col metal-price-col-lme">
                <div class="metal-price-region">LME</div>
                <div class="metal-price-src">Londýn · Westmetall Cash</div>
                <div class="card-value">{format_num(price_disp, 0)}</div>
                <div class="card-unit card-unit-emphasis">{unit}</div>
            </div>
            <div class="metal-price-col metal-price-col-ccmn">
                <div class="metal-price-region">Čína</div>
                <div class="metal-price-src">Changjiang spot · ccmn.cn</div>
                {_ccmn_price_block(metal_key, price_usd, unit, ccy)}
            </div>
        </div>
        <div class="card-delta-row">{chips}</div>
        <div class="card-extra card-extra-emphasis">{extra}</div>
    </div>
    """,
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
def _eur_cny_history_full() -> tuple[pd.DataFrame | None, bool]:
    """Plná historie EUR/CNY — přímý ticker, jinak odvozeno EURUSD ÷ CNYUSD."""
    direct = _yf_history("EURCNY=X")
    if direct is not None and not direct.empty:
        return direct, False

    eur_usd = _yf_history("EURUSD=X")
    cny_usd = _yf_history("CNYUSD=X")
    if eur_usd is None or cny_usd is None or eur_usd.empty or cny_usd.empty:
        return None, False

    merged = pd.merge(
        eur_usd.rename(columns={"Close": "eur_usd"}),
        cny_usd.rename(columns={"Close": "cny_usd"}),
        on="Date",
        how="inner",
    )
    merged = merged[merged["cny_usd"] > 0]
    if merged.empty:
        return None, False
    merged["Close"] = merged["eur_usd"] / merged["cny_usd"]
    return merged[["Date", "Close"]].copy(), True


def fetch_eur_cny_history(period: str = "3mo") -> tuple[pd.DataFrame | None, bool]:
    """Historie EUR/CNY oříznutá podle globálního období."""
    full, derived = _eur_cny_history_full()
    return filter_history_by_period(full), derived


_FX_SPARK_DAYS = 30
_FX_SPARK_COLORS = {
    "card-usd": "#34C98E",
    "card-eur": "#4D9FFF",
    "card-cny": "#F0565E",
}


def _sparkline_svg(values: list[float], color: str = "#4D9FFF", width: int = 160, height: int = 36) -> str:
    """Kompaktní SVG sparkline (posledních N hodnot) — bez Plotly, čistý HTML."""
    clean = [float(v) for v in values if v is not None and math.isfinite(float(v))]
    if len(clean) < 2:
        return ""
    lo, hi = min(clean), max(clean)
    span = hi - lo or 1.0
    pad = 2
    pts: list[str] = []
    n = len(clean)
    for i, v in enumerate(clean):
        x = pad + (width - 2 * pad) * i / (n - 1)
        y = height - pad - (height - 2 * pad) * ((v - lo) / span)
        pts.append(f"{x:.1f},{y:.1f}")
    polyline = " ".join(pts)
    # vyplněná plocha pod čárou (jemný gradient efekt)
    area = f"0,{height} {polyline} {width},{height}"
    return (
        f'<svg viewBox="0 0 {width} {height}" preserveAspectRatio="none" '
        f'aria-hidden="true">'
        f'<polyline fill="none" stroke="{color}" stroke-width="1.8" '
        f'stroke-linejoin="round" stroke-linecap="round" points="{polyline}"/>'
        f'<polygon fill="{color}" fill-opacity="0.12" points="{area}"/>'
        f"</svg>"
    )


def _fx_series_tail(kind: str, n: int = _FX_SPARK_DAYS) -> list[float]:
    """Posledních n hodnot FX série pro sparkline (Yahoo / odvozené kříže)."""
    df: pd.DataFrame | None = None
    invert = False
    if kind == "usd":
        df = _yf_history("USDCZK=X")
    elif kind == "eur":
        df = _yf_history("EURCZK=X")
    elif kind == "cny":
        df, _ = _cny_czk_history_full()
    elif kind == "eurusd":
        df = _yf_history("EURUSD=X")
    elif kind == "usdeur":
        df = _yf_history("EURUSD=X")
        invert = True
    elif kind == "cnyeur":
        eur = _yf_history("EURCZK=X")
        cny, _ = _cny_czk_history_full()
        if eur is not None and cny is not None and not eur.empty and not cny.empty:
            merged = pd.merge(
                cny.rename(columns={"Close": "cny"}),
                eur.rename(columns={"Close": "eur"}),
                on="Date",
                how="inner",
            )
            merged = merged[merged["eur"] > 0]
            if not merged.empty:
                merged["Close"] = merged["cny"] / merged["eur"]
                df = merged[["Date", "Close"]]
    if df is None or df.empty or "Close" not in df.columns:
        return []
    s = pd.to_numeric(df["Close"], errors="coerce").dropna()
    if invert:
        s = 1.0 / s.replace(0, pd.NA)
        s = s.dropna()
    return [float(v) for v in s.tail(n).tolist()]


def _fx_sparkline_html(kind: str, card_class: str) -> str | None:
    """SVG sparkline (30d) pro FX kartu, nebo None pokud data chybí."""
    vals = _fx_series_tail(kind)
    if len(vals) < 2:
        return None
    color = _FX_SPARK_COLORS.get(card_class, "#4D9FFF")
    svg = _sparkline_svg(vals, color=color)
    return svg or None


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


def _metal_rsi_value(metal_key: str) -> float | None:
    """Aktuální RSI pro měď nebo hliník (Westmetall)."""
    try:
        if metal_key == "copper":
            return _rsi_from_history(fetch_westmetall_history(WM_HISTORY_URLS["copper"]))
        if metal_key == "aluminum":
            return _rsi_from_history(fetch_westmetall_history(WM_HISTORY_URLS["aluminum"]))
    except Exception:
        return None
    return None


def build_daily_export_df() -> pd.DataFrame:
    """
    Jednořádkový snapshot aktuálních cen, kurzů a RSI pro export (datum = dnes, Praha).
    """
    today = now_prague().strftime("%Y-%m-%d")
    ccy = get_display_currency()
    wm = fetch_westmetall()
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

    for metal_key, prefix in [("copper", "med"), ("aluminum", "hlinik")]:
        rsi = _metal_rsi_value(metal_key)
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



def get_chart_period() -> str:
    """Aktuální yfinance period string z globálního přepínače."""
    return st.session_state.get("chart_period_yf", "3mo")


def get_chart_period_label() -> str:
    """Štítek období (1W, 1M, …) pro titulky grafů."""
    return st.session_state.get("chart_period_label", "3M")


def _ccmn_vs_lme_spread_pct(ccmn_usd: float, lme_usd: float) -> float | None:
    """CCMN oproti LME v % — (CCMN − LME) / LME × 100."""
    try:
        if lme_usd is None or ccmn_usd is None or float(lme_usd) == 0:
            return None
        return (float(ccmn_usd) - float(lme_usd)) / float(lme_usd) * 100.0
    except (TypeError, ValueError, ZeroDivisionError):
        return None


def get_ccmn_china_usd(metal_key: str) -> tuple[float | None, dict | None, float | None]:
    """
    Čínská strana spreadu — spot ccmn.cn + přepočet CNY přes ČNB.
    Vrátí (USD/t, ccmn dict, CNY/t).
    """
    ccmn = fetch_ccmn_spot(metal_key)
    if not ccmn or not ccmn.get("price"):
        return None, None, None
    usd_per_cny = get_usd_per_cny()
    if not usd_per_cny:
        return None, ccmn, ccmn["price"]
    return ccmn["price"] * usd_per_cny, ccmn, ccmn["price"]


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

_PLOT_PAPER = "#1E242E"
_PLOT_BG = "#1A1F28"
_PLOT_TITLE_COLOR = "#E9EDF3"
_PLOT_TICK_COLOR = "#B8C2D0"
_PLOT_GRID = "#2C3442"

_TICK_AXIS = dict(
    gridcolor=_PLOT_GRID,
    tickfont=dict(family="IBM Plex Mono, monospace", size=10, color=_PLOT_TICK_COLOR),
    showgrid=True,
    zeroline=False,
    showline=True,
    linecolor="#3A4454",
)

_HOVER_LABEL = dict(
    bgcolor="#232A36",
    bordercolor="#3D4859",
    font=dict(family="IBM Plex Mono, monospace", size=11, color="#E9EDF3"),
)

# Mezera = tisíce, tečka = desetinná (český standard v Plotly)
_PLOT_SEPARATORS = " ."


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


# Klouzavé průměry: (sloupec, popisek, barva, styl čáry) — jemné, ať nepřebíjí cenu
# Barvy záměrně odlišné od zásob LME (tyrkysová) i cenových křivek (oranžová/zelená/šedá)
_SMA_STYLES = [
    ("SMA20", "SMA 20d", "#7DB8FF", "dot"),
    ("SMA50", "SMA 50d", "#A78BFA", "dash"),
]


def _add_sma_columns(df: pd.DataFrame, price_col: str = "Close") -> pd.DataFrame:
    """Přidá SMA20/SMA50 z cenového sloupce (volat PŘED ořezem období, ať jsou průměry přesné)."""
    out = df.copy()
    s = pd.to_numeric(out[price_col], errors="coerce")
    out["SMA20"] = s.rolling(window=20, min_periods=1).mean()
    out["SMA50"] = s.rolling(window=50, min_periods=1).mean()
    return out


def _sma_extra_traces(df: pd.DataFrame | None) -> list[dict]:
    """Sestaví extra_traces s SMA řadami pro grafové funkce."""
    if df is None or df.empty:
        return []
    return [
        {"y": df[col], "name": name, "color": color, "width": 1.4, "dash": dash}
        for col, name, color, dash in _SMA_STYLES
        if col in df.columns
    ]


def metal_price_history_figure(
    df: pd.DataFrame,
    title: str,
    color: str,
    y_col: str = "Close",
    y_label: str = "USD/t",
    height: int = 320,
    extra_traces: list[dict] | None = None,
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
        name="Cena",
        showlegend=bool(extra_traces),
        hovertemplate=(
            f"<b>%{{x|%d.%m.%Y}}</b><br>{y_label}: %{{y:,.2f}}<extra></extra>"
        ),
    )

    if extra_traces:
        for tr in extra_traces:
            fig.add_trace(go.Scatter(
                x=plot_df["Date"],
                y=tr["y"],
                mode="lines",
                name=tr.get("name", ""),
                line=dict(
                    color=tr.get("color", "#94a3b8"),
                    width=tr.get("width", 1.5),
                    dash=tr.get("dash", "dot"),
                ),
                hovertemplate=(
                    f"<b>%{{x|%d.%m.%Y}}</b><br>{tr.get('name', '')}: %{{y:,.2f}}<extra></extra>"
                ),
            ))

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
        showlegend=bool(extra_traces),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.06,
            xanchor="right",
            x=1,
            font=dict(family="IBM Plex Mono, monospace", size=10, color=_PLOT_TICK_COLOR),
            bgcolor=_PLOT_PAPER,
        ),
        hovermode="x unified",
        hoverlabel=_HOVER_LABEL,
        xaxis=dict(**_TICK_AXIS, tickformat="%d.%m.%Y", title=None),
    )

    # Rozsah osy Y přes cenu i SMA řady, ať se klouzavé průměry neoříznou
    range_df = plot_df[[y_col]].rename(columns={y_col: "_yr"})
    if extra_traces:
        combined = pd.concat(
            [pd.to_numeric(range_df["_yr"], errors="coerce")]
            + [pd.to_numeric(pd.Series(tr["y"]).reset_index(drop=True), errors="coerce")
               for tr in extra_traces],
            ignore_index=True,
        )
        range_df = pd.DataFrame({"_yr": combined})
    _apply_financial_y_axis(fig, range_df, "_yr")
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
    extra_traces: list[dict] | None = None,
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
            fig = interactive_metal_dual_chart(
                df, graph_title, color, y_unit, extra_traces=extra_traces
            )
        else:
            fig = metal_price_history_figure(
                df,
                graph_title,
                color,
                price_col,
                y_unit,
                extra_traces=extra_traces,
            )
        if fig:
            _ensure_plot_separators(fig)
            st.plotly_chart(
                fig,
                use_container_width=True,
                config={
                    "displayModeBar": False,
                    "displaylogo": False,
                    "responsive": True,
                    "scrollZoom": False,
                },
            )
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
    extra_traces: list[dict] | None = None,
) -> go.Figure | None:
    """
    Graf LME Cash-Settlement (osa Y vlevo) + LME Stock (osa Y vpravo).
    Obě osy jsou dynamicky oříznuty na min/max s 2% rezervou.
    extra_traces: [{"y": Series, "name": str, "color": str, "dash": str, "width": float}]
    — vykreslí se na primární cenové ose (např. SMA20/SMA50).
    """
    if df is None or df.empty or "Close" not in df.columns:
        return None

    x_data = df["Date"]
    r, g, b = int(price_color[1:3], 16), int(price_color[3:5], 16), int(price_color[5:7], 16)
    fig = go.Figure()

    # 1. Výpočet limitů pro cenu — včetně extra řad (SMA), ať se neoříznou
    price_s = pd.to_numeric(df["Close"], errors="coerce").dropna()
    if price_s.empty:
        return None
    range_series = [price_s]
    if extra_traces:
        range_series.extend(
            pd.to_numeric(pd.Series(tr["y"]).reset_index(drop=True), errors="coerce").dropna()
            for tr in extra_traces
        )
    range_all = pd.concat(range_series, ignore_index=True)
    p_min, p_max = float(range_all.min()), float(range_all.max())
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

    # 2b. Extra řady na primární ose (klouzavé průměry apod.)
    if extra_traces:
        for tr in extra_traces:
            fig.add_trace(go.Scatter(
                x=x_data,
                y=tr["y"],
                mode="lines",
                name=tr.get("name", ""),
                yaxis="y",
                line=dict(
                    color=tr.get("color", "#94a3b8"),
                    width=tr.get("width", 1.5),
                    dash=tr.get("dash", "dot"),
                ),
                hovertemplate=(
                    f"<b>%{{x|%d.%m.%Y}}</b><br>{tr.get('name', '')}: %{{y:,.2f}}<extra></extra>"
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

        # Zásoby: plná tyrkysová čára, barevně sladěná s pravou osou — jasně
        # odlišitelná od přerušovaných SMA průměrů na cenové ose
        fig.add_trace(go.Scatter(
            x=x_data,
            y=df["Stock"],
            mode="lines",
            name="Zásoby LME (t)",
            yaxis="y2",
            opacity=0.65,
            line=dict(color="#2DD4BF", width=1.6),
            hovertemplate="<b>%{x|%d.%m.%Y}</b><br>Zásoby: %{y:,.0f} t<extra></extra>",
        ))

        y2_axis = dict(
            title=dict(text="Zásoby (t)", font=dict(size=10, color="#2DD4BF")),
            overlaying="y",
            side="right",
            showgrid=False,
            tickfont=dict(family="IBM Plex Mono, monospace", size=10, color="#2DD4BF"),
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

    if ccy == "EUR" and not get_eurusd_rate():
        st.warning("Chyba načítání dat z Westmetallu — chybí kurz EUR/USD pro přepočet.")
        st.markdown(
            '<div class="error-box">Chyba načítání dat z Westmetallu</div>',
            unsafe_allow_html=True,
        )
        return

    # SMA počítáme z plné (převedené) historie, teprve potom ořez na zvolené období
    conv = _add_sma_columns(apply_currency_to_df(full.copy()))
    plot = filter_wm_history_by_period(conv)
    if plot is None or plot.empty:
        st.warning("Chyba načítání dat z Westmetallu")
        st.markdown(
            '<div class="error-box">Chyba načítání dat z Westmetallu</div>',
            unsafe_allow_html=True,
        )
        return

    _render_metal_history_with_tabs(
        plot,
        chart_title,
        color,
        y_unit,
        price_col="Close",
        source_note="Westmetall",
        is_dual=True,
        extra_traces=_sma_extra_traces(plot),
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


# ==============================================================================
# ─────────────────────────────────────────────────────────────────────────────
#  HLAVNÍ RENDEROVACÍ FUNKCE
# ─────────────────────────────────────────────────────────────────────────────
# ==============================================================================

# Po kolika obchodních dnech bez běhu robota zobrazit varování
_ROBOT_STALE_BDAYS = 2
# Prahy ranního briefingu (jen tržní data — žádné interní nákupy)
_ALERT_METAL_7D_PCT = 3.0
_ALERT_CHINA_CHEAP_PCT = -2.0
_ALERT_CHINA_RICH_PCT = 5.0
_ALERT_BRENT_DAY_PCT = 3.0
_ALERT_EURCZK_7D_PCT = 1.5


@st.cache_data(ttl=CACHE_TTL)
def _load_robot_payload() -> dict | None:
    """Načte robot_data.json (CCMN, Yahoo spot, _ts, volitelně _health)."""
    try:
        import json
        with open("robot_data.json", "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else None
    except Exception:
        return None


@st.cache_data(ttl=CACHE_TTL)
def _robot_last_run() -> str | None:
    """Čas posledního běhu data robota (ISO string kvůli cache serializaci)."""
    data = _load_robot_payload()
    if data and data.get("_ts"):
        try:
            return str(pd.Timestamp(data["_ts"]))
        except Exception:
            pass
    try:
        df = pd.read_csv("robot_history.csv", parse_dates=["Date"])
        if not df.empty:
            return str(pd.Timestamp(df["Date"].max()))
    except Exception:
        pass
    return None


def _robot_stale_bdays() -> int | None:
    """Obchodní dny od posledního běhu robota; None = soubor chybí."""
    last_str = _robot_last_run()
    if last_str is None:
        return None
    last = pd.Timestamp(last_str)
    today = now_prague().date()
    return len(pd.bdate_range(last.date() + timedelta(days=1), today))


def _expected_cnb_date(now: datetime | None = None):
    """Očekávané datum ČNB lístku (před ~15:00 ještě předchozí pracovní den)."""
    now = now or now_prague()
    d = now.date()
    if d.weekday() >= 5:
        while d.weekday() >= 5:
            d -= timedelta(days=1)
        return d
    if now.hour < 15:
        d -= timedelta(days=1)
        while d.weekday() >= 5:
            d -= timedelta(days=1)
    return d


def _parse_cnb_date(date_str: str):
    try:
        return datetime.strptime(str(date_str).strip(), "%d.%m.%Y").date()
    except (TypeError, ValueError):
        return None


def _close_trend_pct(df: pd.DataFrame | None, days: int) -> float | None:
    """% změna Close za N dní."""
    try:
        if df is None or df.empty or "Close" not in df.columns or "Date" not in df.columns:
            return None
        out = df.dropna(subset=["Close"]).sort_values("Date")
        last_date = out["Date"].iloc[-1]
        last = float(out["Close"].iloc[-1])
        past = out[out["Date"] <= last_date - pd.Timedelta(days=days)]
        if past.empty:
            return None
        ref = float(past["Close"].iloc[-1])
        if ref == 0:
            return None
        return (last / ref - 1.0) * 100.0
    except Exception:
        return None


def _collect_health_alerts(
    wm_data: dict | None,
    cnb: dict | None,
    oil: dict | None,
) -> list[tuple[str, str, str]]:
    """Výpadky zdrojů. (severity, titulek, text) — error / warning."""
    alerts: list[tuple[str, str, str]] = []
    robot = _load_robot_payload()
    stale = _robot_stale_bdays()

    if stale is None:
        alerts.append((
            "error",
            "Data robota chybí",
            "robot_data.json / robot_history.csv se nenašly. "
            "Čína (CCMN), ropa a část FX grafů nepojedou. "
            "Zkontroluj GitHub Action data_robot.yml.",
        ))
    elif stale > _ROBOT_STALE_BDAYS:
        last_str = _robot_last_run()
        last_fmt = pd.Timestamp(last_str).strftime("%d.%m.%Y %H:%M") if last_str else "?"
        alerts.append((
            "error",
            "Data robota jsou stará",
            f"{stale} obchodních dní od posledního běhu ({last_fmt}). "
            "Action pravděpodobně padá — CCMN a Yahoo v aplikaci nejsou živé scrape.",
        ))

    if robot:
        health = robot.get("_health") if isinstance(robot.get("_health"), dict) else {}
        ccmn = robot.get("ccmn") or {}
        if not ccmn.get("copper") or health.get("ccmn_copper") is False:
            alerts.append((
                "error",
                "CCMN měď nedostupná",
                "Robot nenačetl 1#铜 z ccmn.cn — spread Čína vs LME u mědi je N/A. "
                "HTML webu se mohlo změnit.",
            ))
        if not ccmn.get("aluminum") or health.get("ccmn_aluminum") is False:
            alerts.append((
                "error",
                "CCMN hliník nedostupný",
                "Robot nenačetl A00铝 z ccmn.cn.",
            ))
        yf_spot = robot.get("yf_spot") or {}
        if not yf_spot.get("BZ=F") or health.get("brent") is False:
            alerts.append((
                "warning",
                "Brent (Yahoo) výpadek",
                "BZ=F v robot_data.json chybí — proxy plastů i karta ropy budou N/A.",
            ))
        if not yf_spot.get("EURUSD=X") or health.get("eurusd") is False:
            alerts.append((
                "warning",
                "EUR/USD výpadek",
                "Bez EURUSD=X nejde přepočítat kovy do EUR.",
            ))

    if not wm_data or "copper" not in (wm_data or {}) or "aluminum" not in (wm_data or {}):
        missing = []
        if not wm_data or "copper" not in wm_data:
            missing.append("měď")
        if not wm_data or "aluminum" not in wm_data:
            missing.append("hliník")
        alerts.append((
            "error",
            "Westmetall LME výpadek",
            f"Živý scrape westmetall.com nevrátil: {', '.join(missing)}. "
            "Ceny LME v kartách budou N/A — to není záloha z robota.",
        ))

    if not cnb:
        alerts.append((
            "error",
            "ČNB kurzovní lístek nedostupný",
            "Bez ČNB nejde spočítat landed cost ani přepočet CCMN (CNY→USD).",
        ))
    else:
        if "CNY" not in cnb or "USD" not in cnb:
            alerts.append((
                "error",
                "ČNB: chybí CNY nebo USD",
                "Spread Čína vs LME nelze spočítat.",
            ))
        cnb_d = _parse_cnb_date(str(cnb.get("_date", "")))
        expected = _expected_cnb_date()
        if cnb_d and cnb_d < expected:
            alerts.append((
                "warning",
                "ČNB lístek není dnešní",
                f"Načteno {cnb_d.strftime('%d.%m.%Y')}, očekáváno {expected.strftime('%d.%m.%Y')}.",
            ))

    if oil is None or "brent" not in (oil or {}):
        if not any(a[1].startswith("Brent") for a in alerts):
            alerts.append((
                "warning",
                "Brent nedostupný",
                "Yahoo/robot nevrátil BZ=F.",
            ))

    return alerts


def _collect_move_alerts(
    cu_7d: float | None,
    al_7d: float | None,
    cu_spread_pct: float | None,
    brent_day_pct: float | None,
    eur_7d: float | None,
) -> list[tuple[str, str, str]]:
    """Pohyby trhu nad prahem — jen veřejné indexy."""
    alerts: list[tuple[str, str, str]] = []

    def metal_move(name: str, pct: float | None) -> None:
        if pct is None:
            return
        if abs(pct) >= _ALERT_METAL_7D_PCT:
            smer = "nahoru" if pct > 0 else "dolů"
            alerts.append((
                "warning",
                f"{name} 7D {smer} {pct:+.1f} %",
                f"Práh ±{_ALERT_METAL_7D_PCT:.0f} % za 7 dní (LME Cash, Westmetall).",
            ))

    metal_move("Měď", cu_7d)
    metal_move("Hliník", al_7d)

    if cu_spread_pct is not None:
        if cu_spread_pct <= _ALERT_CHINA_CHEAP_PCT:
            alerts.append((
                "warning",
                f"Čína levnější než LME ({cu_spread_pct:+.1f} %)",
                "CCMN spot měď vs LME Cash. Spread je tržní, ne vaše nákupní cena.",
            ))
        elif cu_spread_pct >= _ALERT_CHINA_RICH_PCT:
            alerts.append((
                "warning",
                f"Čína dražší než LME ({cu_spread_pct:+.1f} %)",
                "CCMN spot měď vs LME Cash.",
            ))

    if brent_day_pct is not None and abs(brent_day_pct) >= _ALERT_BRENT_DAY_PCT:
        alerts.append((
            "warning",
            f"Brent denní pohyb {brent_day_pct:+.1f} %",
            f"Práh ±{_ALERT_BRENT_DAY_PCT:.0f} % (BZ=F). Proxy plastů se hýbe se zpožděním.",
        ))

    if eur_7d is not None and abs(eur_7d) >= _ALERT_EURCZK_7D_PCT:
        alerts.append((
            "warning",
            f"EUR/CZK 7D {eur_7d:+.1f} %",
            f"Práh ±{_ALERT_EURCZK_7D_PCT:.1f} % (Yahoo EURCZK=X).",
        ))

    rsi_cu = _metal_rsi_value("copper")
    if rsi_cu is not None:
        if rsi_cu >= 70:
            alerts.append((
                "warning",
                f"Měď RSI {rsi_cu:.0f} — překoupeno",
                "Westmetall, RSI 14. Orientační signál, ne pokyn k nákupu.",
            ))
        elif rsi_cu <= 30:
            alerts.append((
                "warning",
                f"Měď RSI {rsi_cu:.0f} — přeprodáno",
                "Westmetall, RSI 14. Orientační signál, ne pokyn k nákupu.",
            ))
    return alerts


def _briefing_tile(label: str, value: str, sub: str, state: str) -> str:
    return (
        f'<div class="briefing-tile {state}">'
        f'<div class="bl">{label}</div>'
        f'<div class="bv">{value}</div>'
        f'<div class="bs">{sub}</div>'
        f"</div>"
    )


def _alert_banner(kind: str, title: str, body: str) -> str:
    cls = {"error": "error-box", "warning": "warning-box", "ok": "success-box"}[kind]
    return (
        f'<div class="{cls}" style="margin:6px 0;text-align:left;">'
        f"<strong>{title}</strong> — {body}</div>"
    )


def render_morning_briefing() -> None:
    """Ranní strip + alerty výpadků a pohybů trhu (žádná interní data)."""
    wm_data = fetch_westmetall()
    cnb = fetch_cnb_rates()
    oil = fetch_oil_data()
    ccy = get_display_currency()

    cu_usd, _, _ = resolve_metal_price("copper", wm_data)
    al_usd, _, _ = resolve_metal_price("aluminum", wm_data)
    cu_disp = usd_to_display(cu_usd, ccy)
    al_disp = usd_to_display(al_usd, ccy)
    cu_7d = _wm_trend_pct("copper", 7)
    al_7d = _wm_trend_pct("aluminum", 7)
    china_usd, _, _ = get_ccmn_china_usd("copper")
    cu_spread = _ccmn_vs_lme_spread_pct(china_usd, cu_usd) if china_usd and cu_usd else None
    brent = (oil or {}).get("brent") or {}
    brent_px = brent.get("price")
    brent_day = brent.get("delta_pct")
    eur_info = (cnb or {}).get("EUR")
    usd_info = (cnb or {}).get("USD")
    eur_7d = _close_trend_pct(_yf_history("EURCZK=X"), 7)

    def _tile_state(ok: bool, warn: bool = False) -> str:
        if not ok:
            return "bad"
        if warn:
            return "warn"
        return "ok"

    cu_sub = "7D N/A" if cu_7d is None else f"7D {cu_7d:+.1f} %"
    al_sub = "7D N/A" if al_7d is None else f"7D {al_7d:+.1f} %"
    if cu_spread is None:
        spread_val, spread_sub, spread_ok = "N/A", "CCMN vs LME", False
    else:
        spread_val = f"{cu_spread:+.1f} %"
        spread_sub = "CCMN měď vs LME"
        spread_ok = True
    eur_sub = f"ČNB {(cnb or {}).get('_date', '')}".strip()
    if eur_7d is not None:
        eur_sub = f"7D {eur_7d:+.1f} % · {eur_sub}"
    brent_sub = "Yahoo BZ=F"
    if brent_day is not None:
        brent_sub = f"den {brent_day:+.1f} % · {brent_sub}"

    stale = _robot_stale_bdays()
    health = _collect_health_alerts(wm_data, cnb, oil)
    moves = _collect_move_alerts(cu_7d, al_7d, cu_spread, brent_day, eur_7d)
    has_error = any(k == "error" for k, _, _ in health)

    tiles = [
        _briefing_tile(
            f"Měď LME · {ccy}",
            format_num(cu_disp, 0) if cu_disp is not None else "N/A",
            cu_sub,
            _tile_state(cu_disp is not None, cu_7d is not None and abs(cu_7d) >= _ALERT_METAL_7D_PCT),
        ),
        _briefing_tile(
            f"Hliník LME · {ccy}",
            format_num(al_disp, 0) if al_disp is not None else "N/A",
            al_sub,
            _tile_state(al_disp is not None, al_7d is not None and abs(al_7d) >= _ALERT_METAL_7D_PCT),
        ),
        _briefing_tile(
            "Čína vs LME",
            spread_val,
            spread_sub,
            _tile_state(
                spread_ok,
                spread_ok and (
                    cu_spread <= _ALERT_CHINA_CHEAP_PCT or cu_spread >= _ALERT_CHINA_RICH_PCT
                ),
            ),
        ),
        _briefing_tile(
            "EUR/CZK",
            f"{eur_info['rate']:.4f}" if eur_info else "N/A",
            eur_sub or "ČNB",
            _tile_state(bool(eur_info), eur_7d is not None and abs(eur_7d) >= _ALERT_EURCZK_7D_PCT),
        ),
        _briefing_tile(
            "USD/CZK",
            f"{usd_info['rate']:.4f}" if usd_info else "N/A",
            f"ČNB {(cnb or {}).get('_date', '')}".strip() or "ČNB",
            _tile_state(bool(usd_info)),
        ),
        _briefing_tile(
            "Brent",
            f"${brent_px:.2f}" if brent_px is not None else "N/A",
            brent_sub,
            _tile_state(
                brent_px is not None,
                brent_day is not None and abs(brent_day) >= _ALERT_BRENT_DAY_PCT,
            ),
        ),
    ]

    status_bits = []
    if has_error:
        status_bits.append("zdroj v chybě")
    elif health:
        status_bits.append("zdroj varování")
    else:
        status_bits.append("zdroje OK")
    if moves:
        status_bits.append(f"{len(moves)} pohyb trhu")
    if stale is not None and stale <= _ROBOT_STALE_BDAYS:
        last_str = _robot_last_run()
        if last_str:
            status_bits.append(f"robot {pd.Timestamp(last_str).strftime('%d.%m. %H:%M')}")

    st.markdown(
        "<div style='font-family:Syne,sans-serif;font-size:0.75rem;font-weight:700;"
        "color:#8D99AB;text-transform:uppercase;letter-spacing:1px;margin:8px 0 6px 0;'>"
        f"Ranní briefing · {' · '.join(status_bits)}</div>"
        f'<div class="briefing-grid">{"".join(tiles)}</div>',
        unsafe_allow_html=True,
    )

    for kind, title, body in health:
        st.markdown(_alert_banner(kind, title, body), unsafe_allow_html=True)
    for kind, title, body in moves:
        st.markdown(_alert_banner(kind, title, body), unsafe_allow_html=True)
    if not health and not moves:
        st.markdown(
            _alert_banner(
                "ok",
                "Zdroje v pořádku",
                "Westmetall, ČNB i robot odpovídají. Žádný pohyb nad prahem "
                f"(Cu/Al 7D ±{_ALERT_METAL_7D_PCT:.0f} %, Čína vs LME "
                f"{_ALERT_CHINA_CHEAP_PCT:.0f}…+{_ALERT_CHINA_RICH_PCT:.0f} %).",
            ),
            unsafe_allow_html=True,
        )
    st.caption(
        "Jen veřejné trhy (LME, CCMN, ČNB, Yahoo). Interní nákupy a zásilky sem nepatří."
    )


def render_header() -> None:
    """Vykreslí animované záhlaví dashboardu."""
    now = now_prague()
    logo_uri = _logo_data_uri()
    logo_html = (
        f'<div class="dash-logo"><img src="{logo_uri}" alt="pbcable s.r.o."></div>'
        if logo_uri else ""
    )
    st.markdown(f"""
    <div class="dash-header">
        <div class="dash-header-content">
            <div class="dash-brand">
                {logo_html}
                <div>
                    <div class="dash-title">
                        <span>⚡</span> Kabelářský dashboard
                    </div>
                    <div class="dash-subtitle">
                        Cable Industry Procurement Intelligence Platform
                    </div>
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
            'font-size:0.7rem;color:#8D99AB;">'
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

# Minimální počet CCMN bodů v zobrazeném období, aby se graf přepnul
# ze zástupného COMEX proxy na skutečná čínská (CCMN) data
_MIN_CCMN_POINTS = 10

# Konfigurace korelačních grafů LME vs Čína (proxy) pro jednotlivé kovy
_CORRELATION_METALS = [
    {
        "wm_key": "copper",
        "metal_label": "měď",
        "lme_name": "LME Cu Cash",
        "ccmn_col": "CCMN_Cu",
        "fallback_ticker": "HG=F",
        "fallback_factor": 2204.62,  # USD/lb → USD/t
        "fallback_label": "COMEX HG=F (Proxy) v USD/t",
        "color": "#f97316",
    },
    {
        "wm_key": "aluminum",
        "metal_label": "hliník",
        "lme_name": "LME Al Cash",
        "ccmn_col": "CCMN_Al",
        "fallback_ticker": "ALI=F",
        "fallback_factor": 1.0,  # ALI=F je kótován přímo v USD/t
        "fallback_label": "COMEX ALI=F (Proxy) v USD/t",
        "color": "#A8B2C1",
    },
]


def _render_metal_correlation(cfg: dict, robot: pd.DataFrame, period_lbl: str) -> None:
    """Jeden korelační graf: LME Cash (Westmetall) vs čínský proxy (CCMN / COMEX) — USD/t."""
    lme = fetch_westmetall_history(WM_HISTORY_URLS[cfg["wm_key"]])
    if lme is None or lme.empty:
        st.warning(
            f"Westmetall: historii LME ({cfg['metal_label']}) se nepodařilo stáhnout — "
            "korelační graf není k dispozici."
        )
        return

    merged = pd.merge(lme[["Date", "Close"]], robot, on="Date", how="inner")
    merged = filter_history_by_period(merged)
    if merged is None or merged.empty:
        st.warning(
            f"Pro zvolené období nejsou k dispozici překrývající se data LME a robota "
            f"({cfg['metal_label']})."
        )
        return

    # Čínský proxy: primárně skutečný CCMN spot (CNY/t → USD/t), pokud je ve
    # střádané historii dost bodů pro smysluplný graf; jinak COMEX futures.
    proxy_label = None
    proxy_color = "#8b5cf6"
    if cfg["ccmn_col"] in merged.columns and "CNYUSD=X" in merged.columns:
        ccmn_proxy = pd.to_numeric(merged[cfg["ccmn_col"]], errors="coerce") * merged["CNYUSD=X"]
        if int(ccmn_proxy.notna().sum()) >= _MIN_CCMN_POINTS:
            merged["Proxy_USD"] = ccmn_proxy
            proxy_label = "CCMN (Čína) v USD/t"
            proxy_color = "#ef4444"
    if proxy_label is None:
        if cfg["fallback_ticker"] not in merged.columns:
            st.warning(
                f"V robot_history.csv chybí {cfg['ccmn_col']}/CNYUSD=X i {cfg['fallback_ticker']} — "
                f"korelační graf pro {cfg['metal_label']} nelze sestavit. "
                "Po dalším běhu datového robota se doplní automaticky."
            )
            return
        merged["Proxy_USD"] = merged[cfg["fallback_ticker"]] * cfg["fallback_factor"]
        proxy_label = cfg["fallback_label"]

    merged = merged.dropna(subset=["Close", "Proxy_USD"]).reset_index(drop=True)
    if merged.empty:
        st.warning(
            f"Po odfiltrování chybějících hodnot nezbyla žádná překrývající se data "
            f"({cfg['metal_label']})."
        )
        return

    fig = interactive_line_chart(
        merged,
        f"{cfg['lme_name']} — vs {proxy_label} · {period_lbl}",
        color=cfg["color"],
        y_label="USD/t",
        height=320,
        y_column="Close",
        extra_traces=[{
            "y": merged["Proxy_USD"],
            "name": proxy_label,
            "color": proxy_color,
            "dash": "solid",
        }],
        show_legend=True,
        tight_yaxis=True,
        y_tickformat=",.0f",
    )
    if fig is not None:
        _show_plotly(fig)


def _render_historical_correlation() -> None:
    """Historická korelace LME vs Čína (proxy) — měď a hliník pod sebou, USD/t."""
    period_lbl = get_chart_period_label()
    st.markdown(
        "<div style='font-family:Syne,sans-serif;font-size:0.75rem;font-weight:700;"
        "color:#8D99AB;text-transform:uppercase;letter-spacing:1px;margin-bottom:8px;'>"
        f"Historická korelace — LME vs Čína ({period_lbl}, USD/t)</div>",
        unsafe_allow_html=True,
    )

    try:
        robot = pd.read_csv("robot_history.csv", parse_dates=["Date"])
    except FileNotFoundError:
        st.warning("Soubor robot_history.csv nenalezen — spusťte datového robota (GitHub Actions).")
        return
    except Exception as e:
        st.warning(f"robot_history.csv se nepodařilo načíst — korelační grafy nejsou k dispozici. ({e})")
        return

    # Střádaná historie čínských CCMN spotů (robot ji doplňuje, nikdy nepřepisuje)
    try:
        ccmn_hist = pd.read_csv("ccmn_history.csv", parse_dates=["Date"])
        robot = pd.merge(robot, ccmn_hist, on="Date", how="left")
    except FileNotFoundError:
        pass  # soubor vznikne prvním během robota; do té doby jede COMEX proxy
    except Exception:
        pass

    for cfg in _CORRELATION_METALS:
        _render_metal_correlation(cfg, robot, period_lbl)


# ── Predikce trendu (ensemble statistických modelů) ──────────────────────────
_FORECAST_HORIZON = 21       # obchodních dní ≈ 1 kalendářní měsíc
_FORECAST_FIT_WINDOW = 45    # dní pro odhad trendu (OLS regrese)
_FORECAST_VOL_WINDOW = 90    # dní pro odhad denní volatility
_FORECAST_BAND_Z = 1.28      # ±1.28σ ≈ 80% interval spolehlivosti
_FORECAST_HOLT_WINDOW = 120  # dní pro fit Holtova vyhlazování
_FORECAST_MR_HALF_LIFE = 20.0  # poločas návratu k SMA50 (dny)
_FORECAST_DIR_THRESHOLD = 0.5  # ± % — pod tím bereme výhled jako stagnaci
_FORECAST_BACKTEST_ORIGINS = 30  # kolik minulých „startů“ se backtestuje
_FORECAST_BACKTEST_MIN = 8       # minimum úspěšných originů pro zobrazení MAPE

# (název modelu, barva, styl čáry) — pořadí odpovídá _forecast_models()
_FORECAST_MODEL_STYLES = [
    ("Trend (regrese 45d)", "#A78BFA", "dash"),
    ("Holt (adaptivní trend)", "#7DB8FF", "dot"),
    ("Návrat k SMA50", "#2DD4BF", "dashdot"),
]


def _forecast_trend_ols(s: pd.Series, horizon: int) -> list[float] | None:
    """Model 1: OLS přímka posledních _FORECAST_FIT_WINDOW dní ukotvená na poslední ceně."""
    if len(s) < _FORECAST_FIT_WINDOW + 1:
        return None
    y = s.iloc[-_FORECAST_FIT_WINDOW:].reset_index(drop=True).astype(float)
    x = pd.Series(range(len(y)), dtype=float)
    x_dev = x - x.mean()
    denom = float((x_dev ** 2).sum())
    if denom == 0:
        return None
    slope = float((x_dev * (y - y.mean())).sum()) / denom
    last_price = float(s.iloc[-1])
    return [last_price + slope * h for h in range(1, horizon + 1)]


def _forecast_holt(s: pd.Series, horizon: int, alpha: float = 0.3, beta: float = 0.1) -> list[float] | None:
    """
    Model 2: Holtovo dvojité exponenciální vyhlazování — adaptivní trend,
    který dává větší váhu novějším datům (rychleji zachytí obrat než regrese).
    """
    vals = [float(v) for v in s.iloc[-_FORECAST_HOLT_WINDOW:]]
    if len(vals) < 10:
        return None
    level, trend = vals[0], vals[1] - vals[0]
    for v in vals[1:]:
        prev_level = level
        level = alpha * v + (1 - alpha) * (level + trend)
        trend = beta * (level - prev_level) + (1 - beta) * trend
    return [level + h * trend for h in range(1, horizon + 1)]


def _forecast_mean_reversion(s: pd.Series, horizon: int) -> list[float] | None:
    """
    Model 3: návrat k průměru — cena exponenciálně konverguje k SMA50
    (poločas _FORECAST_MR_HALF_LIFE dní). Zachycuje „gumičkový“ efekt trhu.
    """
    if len(s) < 50:
        return None
    sma50 = float(s.rolling(50).mean().iloc[-1])
    last = float(s.iloc[-1])
    return [
        sma50 + (last - sma50) * (0.5 ** (h / _FORECAST_MR_HALF_LIFE))
        for h in range(1, horizon + 1)
    ]


def _forecast_models(
    hist: pd.DataFrame | None,
    price_col: str = "Close",
    horizon: int = _FORECAST_HORIZON,
) -> dict | None:
    """
    Spočítá všechny modely + ensemble (průměr modelů) + pásmo nejistoty
    z reálné denní volatility (šířka roste s √h). MODEL — ne předpověď budoucnosti.
    Vrací: {"dates", "last_price", "models": {název: [ceny]}, "ensemble", "lo", "hi"}.
    """
    if hist is None or hist.empty or price_col not in hist.columns:
        return None
    s = pd.to_numeric(hist[price_col], errors="coerce").dropna()
    if len(s) < _FORECAST_FIT_WINDOW + 1:
        return None

    paths = {
        "Trend (regrese 45d)": _forecast_trend_ols(s, horizon),
        "Holt (adaptivní trend)": _forecast_holt(s, horizon),
        "Návrat k SMA50": _forecast_mean_reversion(s, horizon),
    }
    models = {name: p for name, p in paths.items() if p is not None}
    if not models:
        return None

    ensemble = [
        sum(p[h] for p in models.values()) / len(models)
        for h in range(horizon)
    ]

    daily_changes = s.diff().dropna().iloc[-_FORECAST_VOL_WINDOW:]
    sigma = float(daily_changes.std()) if len(daily_changes) > 1 else 0.0
    lo = [ensemble[h] - _FORECAST_BAND_Z * sigma * math.sqrt(h + 1) for h in range(horizon)]
    hi = [ensemble[h] + _FORECAST_BAND_Z * sigma * math.sqrt(h + 1) for h in range(horizon)]

    last_date = pd.to_datetime(hist["Date"]).max()
    return {
        "dates": pd.bdate_range(last_date + pd.Timedelta(days=1), periods=horizon),
        "last_price": float(s.iloc[-1]),
        "models": models,
        "ensemble": ensemble,
        "lo": lo,
        "hi": hi,
    }


def _forecast_backtest(
    hist: pd.DataFrame | None,
    price_col: str = "Close",
    horizon: int = _FORECAST_HORIZON,
    n_origins: int = _FORECAST_BACKTEST_ORIGINS,
) -> dict | None:
    """
    Walk-forward backtest: pro posledních n_origins obchodních dní spustí model
    „jakoby ten den“ a srovná predikci za horizon dní s reálnou cenou.
    Vrací MAPE (%) pro ensemble i jednotlivé modely + počet úspěšných originů.
    """
    if hist is None or hist.empty or price_col not in hist.columns:
        return None
    df = hist[["Date", price_col]].dropna().copy()
    df["Date"] = pd.to_datetime(df["Date"])
    df = df.sort_values("Date").reset_index(drop=True)
    # potřebujeme fit okno + horizon dopředu + aspoň n_origins originů
    min_len = _FORECAST_FIT_WINDOW + horizon + n_origins
    if len(df) < min_len:
        return None

    # poslední index, pro který ještě existuje skutečná cena za horizon dní
    last_origin = len(df) - 1 - horizon
    first_origin = max(_FORECAST_FIT_WINDOW, last_origin - n_origins + 1)
    if first_origin > last_origin:
        return None

    abs_pct: dict[str, list[float]] = {"ensemble": []}
    for name, _, _ in _FORECAST_MODEL_STYLES:
        abs_pct[name] = []

    for i in range(first_origin, last_origin + 1):
        past = df.iloc[: i + 1]
        actual = float(df[price_col].iloc[i + horizon])
        if actual == 0:
            continue
        fc = _forecast_models(past, price_col=price_col, horizon=horizon)
        if fc is None:
            continue
        for name, path in fc["models"].items():
            abs_pct.setdefault(name, []).append(abs(path[-1] / actual - 1.0) * 100.0)
        abs_pct["ensemble"].append(abs(fc["ensemble"][-1] / actual - 1.0) * 100.0)

    n_ok = len(abs_pct["ensemble"])
    if n_ok < _FORECAST_BACKTEST_MIN:
        return None

    def _mape(vals: list[float]) -> float | None:
        return sum(vals) / len(vals) if vals else None

    return {
        "n": n_ok,
        "horizon": horizon,
        "ensemble_mape": _mape(abs_pct["ensemble"]),
        "models_mape": {
            name: _mape(vals)
            for name, vals in abs_pct.items()
            if name != "ensemble" and vals
        },
    }


def _forecast_chart(
    hist: pd.DataFrame,
    fc: dict,
    title: str,
    color: str,
    y_label: str,
    height: int = 320,
) -> go.Figure:
    """Vějířový graf: 60 dní historie + projekce všech modelů s pásmem nejistoty."""
    tail = hist.tail(60).copy()
    tail["Date"] = pd.to_datetime(tail["Date"])

    # Napojení projekcí na poslední známý bod (bez vizuální mezery)
    last_date = tail["Date"].iloc[-1]
    last_price = fc["last_price"]
    x_fc = [last_date] + list(fc["dates"])
    lo_full = [last_price] + fc["lo"]
    hi_full = [last_price] + fc["hi"]

    fig = go.Figure()

    # Pásmo nejistoty kolem ensemble (fialový vějíř)
    fig.add_trace(go.Scatter(
        x=x_fc, y=hi_full, mode="lines",
        line=dict(width=0), showlegend=False, hoverinfo="skip",
    ))
    fig.add_trace(go.Scatter(
        x=x_fc, y=lo_full, mode="lines",
        line=dict(width=0), fill="tonexty", fillcolor="rgba(167,139,250,0.14)",
        name="Pásmo nejistoty (80 %)", hoverinfo="skip",
    ))

    # Historie (plná čára v barvě kovu)
    fig.add_trace(go.Scatter(
        x=tail["Date"], y=tail["Close"], mode="lines",
        name="Historie", line=dict(color=color, width=2.2),
        hovertemplate=f"<b>%{{x|%d.%m.%Y}}</b><br>{y_label}: %{{y:,.0f}}<extra></extra>",
    ))

    # Jednotlivé modely (přerušované čáry)
    for name, mdl_color, dash in _FORECAST_MODEL_STYLES:
        path = fc["models"].get(name)
        if path is None:
            continue
        fig.add_trace(go.Scatter(
            x=x_fc, y=[last_price] + path, mode="lines",
            name=name, line=dict(color=mdl_color, width=1.7, dash=dash),
            hovertemplate=f"<b>%{{x|%d.%m.%Y}}</b><br>{name}: %{{y:,.0f}}<extra></extra>",
        ))

    # Těsný rozsah osy Y přes historii, modely i pásmo
    all_vals = pd.concat([
        pd.to_numeric(tail["Close"], errors="coerce"),
        pd.Series(lo_full, dtype=float),
        pd.Series(hi_full, dtype=float),
    ]).dropna()
    y_min, y_max = float(all_vals.min()), float(all_vals.max())
    pad = (y_max - y_min) * 0.05 or 1.0

    fig.update_layout(
        separators=_PLOT_SEPARATORS,
        title=dict(text=title, font=dict(family="Syne, sans-serif", size=13, color=_PLOT_TITLE_COLOR), y=0.97),
        height=height,
        margin=dict(l=10, r=10, t=46, b=12),
        paper_bgcolor=_PLOT_PAPER,
        plot_bgcolor=_PLOT_BG,
        showlegend=True,
        legend=dict(
            orientation="h", yanchor="bottom", y=1.08, xanchor="right", x=1,
            font=dict(family="IBM Plex Mono, monospace", size=10, color=_PLOT_TICK_COLOR),
            bgcolor=_PLOT_PAPER,
        ),
        xaxis=dict(**_TICK_AXIS, tickformat="%d.%m."),
        yaxis=dict(**_TICK_AXIS, tickformat=",.0f", title=dict(text=y_label, standoff=8),
                   range=[y_min - pad, y_max + pad], autorange=False),
        hoverlabel=_HOVER_LABEL,
        hovermode="x unified",
    )
    return fig


def _forecast_direction(end_price: float, last_price: float) -> str:
    """Směr výhledu modelu: up / down / flat (práh _FORECAST_DIR_THRESHOLD %)."""
    pct = (end_price / last_price - 1.0) * 100.0
    if pct > _FORECAST_DIR_THRESHOLD:
        return "up"
    if pct < -_FORECAST_DIR_THRESHOLD:
        return "down"
    return "flat"


_DIR_WORDS = {"up": "růst 📈", "down": "pokles 📉", "flat": "stagnaci ➡️"}


def _render_forecast_for_metal(name: str, color: str, hist: pd.DataFrame | None, y_unit: str) -> None:
    """Jedna predikce: graf všech modelů + konsenzus a shrnutí za horizont."""
    if hist is None or hist.empty:
        st.markdown(
            f'<div class="error-box">Predikce {name}: historická data nejsou k dispozici</div>',
            unsafe_allow_html=True,
        )
        return
    fc = _forecast_models(hist)
    if fc is None:
        st.markdown(
            f'<div class="error-box">Predikce {name}: nedostatek dat pro odhad trendu '
            f'(potřeba ≥ {_FORECAST_FIT_WINDOW} dní)</div>',
            unsafe_allow_html=True,
        )
        return

    last_price = fc["last_price"]

    fig = _forecast_chart(hist, fc, f"{name} — projekce {_FORECAST_HORIZON} obch. dní", color, y_unit)
    _show_plotly(fig)

    # Konsenzus: na čem se modely shodují?
    directions = {
        mdl_name: _forecast_direction(path[-1], last_price)
        for mdl_name, path in fc["models"].items()
    }
    counts = {d: list(directions.values()).count(d) for d in ("up", "down", "flat")}
    top_dir, top_count = max(counts.items(), key=lambda kv: kv[1])
    n_models = len(directions)

    ens_end = fc["ensemble"][-1]
    ens_pct = (ens_end / last_price - 1.0) * 100.0
    ens_sign = "+" if ens_pct >= 0 else ""

    model_bits = " · ".join(
        f"{mdl_name.split(' (')[0]}: <strong>{format_num(path[-1], 0)}</strong>"
        for mdl_name, path in fc["models"].items()
    )

    if top_count == n_models and n_models >= 2:
        verdict_cls, verdict = "success-box", (
            f"🎯 <strong>Shoda {top_count}/{n_models} modelů na {_DIR_WORDS[top_dir]}</strong> — "
            "silnější signál (modely s různou logikou míří stejným směrem)."
        )
    elif top_count >= 2:
        verdict_cls, verdict = "info-box", (
            f"<strong>Převaha {top_count}/{n_models} modelů: {_DIR_WORDS[top_dir]}.</strong> "
            "Menšinový model se odchyluje — signál ber s rezervou."
        )
    else:
        verdict_cls, verdict = "warning-box", (
            "<strong>Modely se neshodují</strong> — trh bez jasného směru, "
            "výhledu nepřikládej velkou váhu."
        )

    # Walk-forward backtest — jak moc se model historicky mýlil
    bt = _forecast_backtest(hist)
    bt_html = ""
    if bt and bt.get("ensemble_mape") is not None:
        mape = bt["ensemble_mape"]
        model_mape = " · ".join(
            f"{name.split(' (')[0]} {m:.1f} %"
            for name, m in bt["models_mape"].items()
            if m is not None
        )
        bt_html = (
            f"<br>📏 <strong>Backtest MAPE</strong> (průměrná |odchylka| za posledních "
            f"{bt['n']} startů × {bt['horizon']} dní): "
            f"ensemble <strong>{mape:.1f} %</strong>"
            + (f" · {model_mape}" if model_mape else "")
            + " — čím nižší, tím spolehlivější výhled."
        )

    st.markdown(
        f'<div class="{verdict_cls}" style="margin:-4px 0 6px 0;">{verdict}</div>'
        f'<div class="card-extra" style="margin:0 0 14px 4px;">'
        f'Průměr modelů za ~1 měsíc: <strong>{format_num(ens_end, 0)} {y_unit}</strong> '
        f'({ens_sign}{ens_pct:.1f} % vůči poslední ceně) · '
        f'80% pásmo: {format_num(fc["lo"][-1], 0)} – {format_num(fc["hi"][-1], 0)} {y_unit}<br>'
        f'{model_bits} {y_unit}{bt_html}</div>',
        unsafe_allow_html=True,
    )


def _render_price_forecast_section() -> None:
    """Sekce predikcí trendu pro Cu a Al — statistický MODEL."""
    ccy = get_display_currency()
    y_unit = f"{ccy}/t"
    st.markdown(
        "<div style='display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin-bottom:8px;'>"
        "<span style='font-family:Syne,sans-serif;font-size:0.75rem;font-weight:700;"
        "color:#8D99AB;text-transform:uppercase;letter-spacing:1px;'>"
        f"Predikce trendu — ~1 měsíc dopředu ({y_unit})</span>"
        f"{badge_html(False, 'statistická extrapolace', model=True)}</div>",
        unsafe_allow_html=True,
    )
    st.markdown(
        '<div class="warning-box">⚠️ <strong>Toto není předpověď budoucnosti.</strong> '
        "Tři nezávislé statistické modely s odlišnou logikou: "
        f"<strong>Trend</strong> (regrese posledních {_FORECAST_FIT_WINDOW} dní — „trh pokračuje stejným tempem“), "
        "<strong>Holt</strong> (adaptivní vyhlazování — větší váha nejnovějším dnům, rychleji chytá obraty) a "
        "<strong>Návrat k SMA50</strong> (cena se stahuje zpět ke klouzavému průměru). "
        f"Pásmo nejistoty vychází z reálné volatility posledních {_FORECAST_VOL_WINDOW} dní. "
        f"Pod grafem je <strong>backtest MAPE</strong> — průměrná absolutní odchylka predikce "
        f"za posledních {_FORECAST_BACKTEST_ORIGINS} startů × {_FORECAST_HORIZON} dní "
        "(čím nižší %, tím spolehlivější výhled). "
        "Shoda modelů = silnější signál; žádný z nich neumí zohlednit zprávy, cla ani výpadky hutí.</div>",
        unsafe_allow_html=True,
    )

    if get_display_currency() == "EUR" and not get_eurusd_rate():
        st.warning("Predikce: chybí kurz EUR/USD pro přepočet — přepněte na USD.")
        return

    # Měď a hliník — Westmetall LME Cash
    for wm_key, name, color in [("copper", "Měď (Cu)", "#f97316"), ("aluminum", "Hliník (Al)", "#A8B2C1")]:
        full = fetch_westmetall_history(WM_HISTORY_URLS[wm_key])
        conv = apply_currency_to_df(full.copy()) if full is not None and not full.empty else None
        _render_forecast_for_metal(name, color, conv, y_unit)


def render_metals() -> None:
    """Sekce 1 – LME kovy, spot CCMN vs LME, historie Westmetall."""

    wm_data = fetch_westmetall()
    period_lbl = get_chart_period_label()

    has_cu = wm_data and "copper" in wm_data
    has_al = wm_data and "aluminum" in wm_data
    has_ccmn = fetch_ccmn_spot("copper") is not None

    section_header(
        "🔩", "Metaly — LME & Čína (CCMN)",
        badge_html(has_cu and has_al, "westmetall.com LME Cash"),
        badge_html(has_ccmn, "ccmn.cn spot"),
    )

    if not wm_data:
        st.warning("Westmetall: LME data se nepodařilo stáhnout — ceny mědi a hliníku nejsou k dispozici.")

    col_cu, col_al = st.columns(2)
    cu_cfg, al_cfg = _LME_METAL_CARDS
    with col_cu:
        _render_lme_metal_card(cu_cfg[0], cu_cfg[1], cu_cfg[2], cu_cfg[3], wm_data)
    with col_al:
        _render_lme_metal_card(al_cfg[0], al_cfg[1], al_cfg[2], al_cfg[3], wm_data)

    st.markdown("<br>", unsafe_allow_html=True)

    # ── Historické grafy — pod sebou na plnou šířku (mobil-friendly) ─────────
    st.markdown(
        "<div style='font-family:Syne,sans-serif;font-size:0.75rem;font-weight:700;"
        "color:#8D99AB;text-transform:uppercase;letter-spacing:1px;margin-bottom:8px;'>"
        f"Historické grafy — Měď & Hliník (Westmetall, {period_lbl})</div>",
        unsafe_allow_html=True,
    )

    _render_wm_metal_history_chart("copper", "Měď (Cu)", "#f97316")
    _render_wm_metal_history_chart("aluminum", "Hliník (Al)", "#A8B2C1")

    # ── Historická korelace LME vs Čína (CCMN / COMEX proxy) ─────────────────
    st.markdown("<br>", unsafe_allow_html=True)
    _render_historical_correlation()

    # ── Predikce trendu (statistický MODEL) ──────────────────────────────────
    st.markdown("<br>", unsafe_allow_html=True)
    _render_price_forecast_section()

    # ── CCMN vs LME spread — na závěr sekce ──────────────────────────────────
    st.markdown("<br>", unsafe_allow_html=True)
    _render_ccmn_spreads(wm_data)

    if wm_data and wm_data.get("_source") == "westmetall.com":
        st.markdown(
            f'<div class="info-box">'
            f'📦 <strong>Westmetall</strong> LME Cash &amp; skladové zásoby · '
            f'Načteno: <strong>{wm_data.get("_ts", "N/A")}</strong></div>',
            unsafe_allow_html=True,
        )

    st.markdown('<div class="section-divider"></div>', unsafe_allow_html=True)


def _render_ccmn_spread_item(metal_key: str, metal_name: str, wm_data: dict | None) -> None:
    """Jedna spread karta CCMN (Čína) vs LME."""
    ccy = get_display_currency()
    lme_usd, _, _ = resolve_metal_price(metal_key, wm_data)
    china_usd, _, cny_price = get_ccmn_china_usd(metal_key)

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
        spread_pct = _ccmn_vs_lme_spread_pct(china_usd, lme_usd)
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


def _render_ccmn_spreads(wm_data: dict | None) -> None:
    """CCMN (Čína) vs LME spread — živá data (ccmn.cn + ČNB + Westmetall)."""
    ccy = get_display_currency()
    st.markdown(
        f"<div style='margin-bottom:10px;'>"
        f"<span style='font-family:Syne,sans-serif;font-size:0.7rem;font-weight:700;"
        f"color:#8D99AB;text-transform:uppercase;letter-spacing:1px;'>"
        f"CCMN (Čína) vs LME Spread ({ccy}/t)</span></div>",
        unsafe_allow_html=True,
    )
    if not get_usd_per_cny():
        st.warning(
            "Spread: chybí kurz CNY z ČNB — přepočet CCMN (CNY/t) na USD/EUR nelze spočítat."
        )
    spread_cols = st.columns(len(_CCMN_SPREAD_METALS))
    for (metal_key, metal_name), col in zip(_CCMN_SPREAD_METALS, spread_cols):
        with col:
            _render_ccmn_spread_item(metal_key, metal_name, wm_data)


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

    cnb_date_note = f" ze dne {cnb.get('_date', 'N/A')}" if cnb else ""
    st.markdown(
        f'<div class="info-box">'
        f'Karty CZK párů: oficiální kurzovní lístek <strong>ČNB</strong>{cnb_date_note} · '
        f'Historické grafy ({period_lbl}), křížové kurzy a 30denní sparkliny: <strong>Yahoo Finance</strong> · '
        f'CNY/CZK graf: CNYCZK=X nebo odvozeno USDCZK×CNYUSD'
        f'</div>',
        unsafe_allow_html=True,
    )

    eur_usd_spot = fetch_yf_spot("EURUSD=X")
    # 2 kurzy vedle sebe na řádek (3 řady × 2 karty) — čitelné na PC i mobilu
    cols = [*st.columns(2), *st.columns(2), *st.columns(2)]

    for (code, pair, subtitle, cls), col in zip(_CNB_METRIC_CARDS, cols[:3]):
        with col:
            info = (cnb or {}).get(code)
            spark_kind = {"USD": "usd", "EUR": "eur", "CNY": "cny"}.get(code, "")
            spark = _fx_sparkline_html(spark_kind, cls) if spark_kind else None
            if info:
                st.markdown(
                    metric_card(
                        pair, f"{info['rate']:.4f}", subtitle,
                        card_class=cls, sparkline_html=spark,
                    ),
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
                    sparkline_html=_fx_sparkline_html("eurusd", "card-eur"),
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
                    sparkline_html=_fx_sparkline_html("usdeur", "card-usd"),
                ),
                unsafe_allow_html=True,
            )
        else:
            st.markdown(error_card("USD/EUR", "card-usd", "Kurz nedostupný"), unsafe_allow_html=True)

    with cols[5]:
        cny_info = (cnb or {}).get("CNY")
        eur_info = (cnb or {}).get("EUR")
        if cny_info and eur_info and eur_info.get("rate"):
            cny_eur = float(cny_info["rate"]) / float(eur_info["rate"])
            st.markdown(
                metric_card(
                    "CNY/EUR", f"{cny_eur:.4f}", "Jüan / Euro (ČNB kříž)",
                    card_class="card-cny",
                    sparkline_html=_fx_sparkline_html("cnyeur", "card-cny"),
                ),
                unsafe_allow_html=True,
            )
        else:
            st.markdown(error_card("CNY/EUR", "card-cny", "Data nedostupná · ČNB"), unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # ── Interaktivní grafy (globální období, Yahoo) ───────────────────────────
    fx_charts = [
        ("CNY/CZK", "#ef4444", "CZK", "cny"),
        ("EUR/CZK", "#3b82f6", "CZK", "eur"),
        ("USD/CZK", "#22c55e", "CZK", "usd"),
        ("EUR/USD", "#8b5cf6", "USD", "eurusd"),
        ("EUR/CNY", "#f59e0b", "CNY", "eurcny"),
    ]
    col_a, col_b = st.columns(2)
    chart_cols = [col_a, col_b, col_a, col_b, col_a]

    for (pair, color, unit, kind), col in zip(fx_charts, chart_cols):
        with col:
            derived = False
            if kind == "cny":
                hist, derived = fetch_cny_czk_history(period)
            elif kind == "eur":
                hist = fetch_fx_history("EURCZK=X", period)
            elif kind == "usd":
                hist = fetch_fx_history("USDCZK=X", period)
            elif kind == "eurcny":
                hist, derived = fetch_eur_cny_history(period)
            else:
                hist = fetch_fx_history("EURUSD=X", period)
            if hist is not None and not hist.empty:
                if kind == "cny" and derived:
                    sub = " · odvozeno USDCZK×CNYUSD"
                elif kind == "eurcny" and derived:
                    sub = " · odvozeno EURUSD÷CNYUSD"
                else:
                    sub = ""
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
        "color:#8D99AB;text-transform:uppercase;letter-spacing:1px;margin-bottom:8px;'>"
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
                            font-size:0.65rem;color:#8D99AB;line-height:1.7;">
                    Základ (Brent):<br>
                    <strong style="color:#E9EDF3;">${plastics['_brent']:.2f}/bbl</strong><br><br>
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
    "🇨🇳 Čína",
    "🇹🇷 Turecko",
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

_EXACT_HS_DUTIES = {
    "85446010": {"label": "Solární kabel / Kabel > 1000V Cu", "duty": 3.7},
    "85446090": {"label": "Kabel 3.6/6.6kV (Ostatní)", "duty": 3.7},
    "85444991": {"label": "Silový kabel 0,6/1kV", "duty": 3.3},
    "85444995": {"label": "Kabel > 80V <= 1000V (Cu/Al)", "duty": 3.3},
    "85444290": {"label": "Kabel s konektory", "duty": 3.3},
    "85444993": {"label": "Datový/Komunikační kabel <= 80V", "duty": 0.0},
    "85444920": {"label": "Ethernetový kabel v metráži", "duty": 0.0},
    "85447000": {"label": "Optický kabel", "duty": 0.0},
    "70196990": {"label": "Firesleeve HTFS", "duty": 7.0},
    "39209928": {"label": "HTFT silicone rubber firesleeve tape", "duty": 6.5},
    "39269097": {"label": "Heatshrink end caps", "duty": 6.5}
}

_HS_SELECTBOX_OPTIONS = [f"{k} - {v['label']}" for k, v in _EXACT_HS_DUTIES.items()]

_DEFAULT_INVOICE_DUTY = 3.7
_DEFAULT_IMPORT_HS_LABEL = "85446010 - Solární kabel / Kabel > 1000V Cu"

_INVOICE_COL_NAME = "Název / Typ kabelu"
_INVOICE_COL_QTY = "Množství (m)"
_INVOICE_COL_PRICE = "Nákupní cena za 1m (EUR)"
_INVOICE_COL_HS = "HS Kód / Nápověda"
_INVOICE_COL_DUTY = "Aplikované clo (%)"


def _extract_hs_code(hs_label: str) -> str:
    """Vytáhne 8místný HS kód z popisku selectboxu."""
    return "".join(c for c in str(hs_label) if c.isdigit())[:8]


def _hs_label_for_code(code: str) -> str:
    """Sjednocený popisek HS kategorie pro selectbox."""
    info = _EXACT_HS_DUTIES[code]
    return f"{code} - {info['label']}"


def _duty_for_hs_label(hs_label: str, *, force_zero: bool = False) -> float:
    """Clo (%) podle HS popisku; výchozí 3,7 % pokud kód není ve slovníku."""
    if force_zero:
        return 0.0
    code = _extract_hs_code(hs_label)
    if code in _EXACT_HS_DUTIES:
        return float(_EXACT_HS_DUTIES[code]["duty"])
    return _DEFAULT_INVOICE_DUTY


def _normalize_hs_label(hs_label: object) -> str:
    """Sjednotí HS popisek na platnou volbu selectboxu."""
    hs_raw = str(hs_label)
    code = _extract_hs_code(hs_raw)
    if code in _EXACT_HS_DUTIES:
        return _hs_label_for_code(code)
    if hs_raw in _HS_SELECTBOX_OPTIONS:
        return hs_raw
    return _DEFAULT_IMPORT_HS_LABEL


def _apply_duty_from_hs_column(df: pd.DataFrame, *, force_zero: bool = False) -> pd.DataFrame:
    """Přepočítá sloupec cla z HS kódů — volat vždy PŘED vykreslením data_editoru."""
    if df is None or df.empty:
        return df
    out = df.copy().reset_index(drop=True)
    if _INVOICE_COL_HS not in out.columns:
        out[_INVOICE_COL_HS] = _DEFAULT_IMPORT_HS_LABEL
    if _INVOICE_COL_DUTY not in out.columns:
        out[_INVOICE_COL_DUTY] = 0.0

    out[_INVOICE_COL_HS] = out[_INVOICE_COL_HS].apply(_normalize_hs_label)
    out[_INVOICE_COL_DUTY] = out[_INVOICE_COL_HS].apply(
        lambda hs: _duty_for_hs_label(hs, force_zero=force_zero)
    )
    return out


def _normalize_invoice_hs_options(df: pd.DataFrame) -> pd.DataFrame:
    """Neplatné HS popisky (např. z importu) sjednotí na platnou volbu selectboxu."""
    if df is None or df.empty or _INVOICE_COL_HS not in df.columns:
        return df
    out = df.copy()
    valid_hs = set(_HS_SELECTBOX_OPTIONS)
    invalid = ~out[_INVOICE_COL_HS].astype(str).isin(valid_hs)
    if invalid.any():
        out.loc[invalid, _INVOICE_COL_HS] = _DEFAULT_IMPORT_HS_LABEL
    return out


_DEFAULT_INVOICE_DF = pd.DataFrame([
    {
        _INVOICE_COL_NAME: "Solární kabel",
        _INVOICE_COL_QTY: 300_000.0,
        _INVOICE_COL_PRICE: 1.85,
        _INVOICE_COL_HS: f"85446010 - {_EXACT_HS_DUTIES['85446010']['label']}",
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

    st.markdown("#### Import dat z Pohody")
    is_atr_turkey = st.checkbox("🇹🇷 Aplikovat nulové clo (Zboží z Turecka s certifikátem A.TR)", value=False)

    uploaded_file = st.file_uploader(
        "Nahrát exportní soubor (CSV nebo Excel z Pohody)",
        type=["csv", "xlsx", "xls"],
        key="landed_file_uploader"
    )

    if uploaded_file is None:
        st.session_state.pop("landed_parsed_file_id", None)
    elif st.session_state.get("landed_parsed_file_id") != uploaded_file.file_id:
        try:
            if uploaded_file.name.lower().endswith('.csv'):
                try:
                    df_in = pd.read_csv(uploaded_file, sep=',', encoding='utf-8-sig', header=None)
                except Exception:
                    uploaded_file.seek(0)
                    df_in = pd.read_csv(uploaded_file, sep=';', encoding='utf-8-sig', header=None)
            else:
                df_in = pd.read_excel(uploaded_file, header=None)

            header_row_idx = -1
            for r_idx, row in df_in.iterrows():
                row_str = ' '.join(str(x).lower() for x in row.values if pd.notna(x))
                if any(k in row_str for k in ['označení', 'množství', 'j.cena', 'description', 'q´ty', 'qty', 'unit price']):
                    header_row_idx = r_idx
                    break

            if header_row_idx == -1:
                header_row_idx = 0
            new_rows = []

            for i in range(header_row_idx + 1, len(df_in)):
                row = df_in.iloc[i]
                vals = [str(x).strip() for x in row.values if pd.notna(x) and str(x).strip() != '']
                if len(vals) == 0:
                    continue

                name_val = vals[0]
                name_lower = name_val.lower()

                # 1. Zahození absolutního balastu (prázdné, součty faktury, stránkování)
                if name_lower in ['nan', ''] or any(k in name_lower for k in [
                    'celkem', 'total', 'zaokrouhl', 'dph', 'záloha', 'tax',
                    'subtotal', 'page', 'strana', 'vystavil', 'slev', 'discount'
                ]):
                    continue

                # 2. Zahození informativních řádků o balení (nechceme je lepit do názvu)
                if 'info:' in name_lower:
                    continue

                num_vals = []

                for token in vals[1:]:
                    if '%' in token:
                        continue
                    clean_token = token.replace(' ', '').replace('\xa0', '').replace('€', '').replace('$', '').replace('Kč', '')

                    try:
                        # Chytré parsování čísel 1.234,56 vs 1,234.56
                        if '.' in clean_token and ',' in clean_token:
                            if clean_token.rfind('.') > clean_token.rfind(','):
                                clean_token = clean_token.replace(',', '')
                            else:
                                clean_token = clean_token.replace('.', '').replace(',', '.')
                        else:
                            clean_token = clean_token.replace(',', '.')

                        f_val = float(clean_token)
                        num_vals.append(f_val)
                    except ValueError:
                        pass

                # 3. ROZHODOVACÍ LOGIKA: Má to čísla = Hlavní položka | Nemá čísla = Barva
                if len(num_vals) >= 2:
                    qty_val = num_vals[0]
                    price_val = num_vals[1]

                    if qty_val > 0 and price_val > 0:
                        matched_duty = 0.0 if is_atr_turkey else 3.7

                        new_rows.append({
                            _INVOICE_COL_NAME: name_val,
                            _INVOICE_COL_QTY: qty_val,
                            _INVOICE_COL_PRICE: price_val,
                            _INVOICE_COL_HS: _DEFAULT_IMPORT_HS_LABEL,
                            _INVOICE_COL_DUTY: matched_duty,
                        })
                else:
                    # Nemá to čísla -> Je to doplňující popis (barva) k předchozí položce
                    if len(new_rows) > 0 and len(name_val) >= 3:
                        new_rows[-1][_INVOICE_COL_NAME] += f" ({name_val})"

            if new_rows:
                st.session_state.landed_invoice_data = pd.DataFrame(
                    new_rows,
                    columns=list(_DEFAULT_INVOICE_DF.columns),
                )
                st.session_state.pop("landed_invoice_editor", None)
                st.success(f"Úspěšně nahráno {len(new_rows)} položek s výchozím claem 3,7 %.")
            else:
                st.warning("Nenalezeny žádné platné položky. Zkontrolujte formát exportu.")
        except Exception as e:
            st.error(f"Chyba při zpracování exportu z Pohody: {e}")
        st.session_state.landed_parsed_file_id = uploaded_file.file_id

    st.markdown("#### Položky faktury")
    if "landed_invoice_data" not in st.session_state:
        st.session_state.landed_invoice_data = _DEFAULT_INVOICE_DF.copy()

    st.caption(
        "Import z Pohody nastaví u všech položek výchozí HS kategorii a **clo 3,7 %** (0 % u A.TR). "
        "Skutečnou sazbu cla upravíte ručním výběrem kategorie v seznamu."
    )

    zero_duty = force_zero_duty or is_atr_turkey
    st.session_state.landed_invoice_data = _normalize_invoice_hs_options(
        st.session_state.landed_invoice_data
    )
    # Klíčové: clo vypočítat PŘED vykreslením editoru (widget jinak drží starou hodnotu v cache).
    invoice_df = _apply_duty_from_hs_column(
        st.session_state.landed_invoice_data,
        force_zero=zero_duty,
    )
    st.session_state.landed_invoice_data = invoice_df
    hs_before_edit = invoice_df[_INVOICE_COL_HS].astype(str).tolist()

    if not st.session_state.landed_invoice_data.empty:
        df_calc = st.session_state.landed_invoice_data
        qty = pd.to_numeric(df_calc[_INVOICE_COL_QTY], errors="coerce").fillna(0)
        price = pd.to_numeric(df_calc[_INVOICE_COL_PRICE], errors="coerce").fillna(0)
        total_qty = qty.sum()
        total_val = (qty * price).sum()

        sum_col1, sum_col2, _sum_col3 = st.columns(3)
        sum_col1.metric("Celková metráž / ks", format_num(total_qty, 2))
        sum_col2.metric("Celková hodnota položek", f"{format_num(total_val, 2)} EUR")
        st.markdown("---")

    edited_df = st.data_editor(
        invoice_df,
        key="landed_invoice_editor",
        column_config={
            _INVOICE_COL_NAME: st.column_config.TextColumn("Název položky", width="large"),
            _INVOICE_COL_QTY: st.column_config.NumberColumn("Množství", min_value=0.0, format="%.2f"),
            _INVOICE_COL_PRICE: st.column_config.NumberColumn("Jednotková cena", min_value=0.0, format="%.3f"),
            _INVOICE_COL_HS: st.column_config.SelectboxColumn(
                "HS Kód / Nápověda",
                help="Vyberte HS kód — clo (%) se automaticky přepočítá.",
                width="large",
                options=_HS_SELECTBOX_OPTIONS,
                required=True,
            ),
            _INVOICE_COL_DUTY: st.column_config.NumberColumn(
                "Aplikované clo (%)",
                min_value=0.0,
                max_value=100.0,
                format="%.1f %%",
                help="Automaticky z HS kódu. U Turecka (A.TR) nebo trasy 🇹🇷 je 0 %.",
            ),
        },
        disabled=[_INVOICE_COL_DUTY],
        num_rows="dynamic",
        use_container_width=True,
        hide_index=True,
    )

    edited_df = edited_df.reset_index(drop=True)
    hs_after_edit = edited_df[_INVOICE_COL_HS].astype(str).tolist()
    st.session_state.landed_invoice_data = edited_df

    # HS se změnil → uložit, smazat cache widgetu, rerun; clo se dopočítá pre-syncem na začátku.
    if hs_after_edit != hs_before_edit or len(hs_after_edit) != len(hs_before_edit):
        st.session_state.pop("landed_invoice_editor", None)
        st.rerun()

    invoice = _sanitize_invoice_input(
        _apply_duty_from_hs_column(st.session_state.landed_invoice_data, force_zero=zero_duty)
    )
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
        f"color:#E9EDF3;margin-bottom:6px;'>"
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


def _resolve_cz_sk_country(country_code: str, country_name: str) -> str | None:
    """Z ISO kódu nebo názvu země vrátí 'CZ'/'SK', jinak None (mimo ČR/SK)."""
    cc = str(country_code or "").upper()
    if cc in ("CZ", "SK"):
        return cc
    name = str(country_name or "").lower()
    if "slovak" in name or "slovensko" in name:
        return "SK"
    if "czech" in name or "česko" in name or "czechia" in name:
        return "CZ"
    return None


def _search_photon(q: str) -> list[dict]:
    """
    Geokódování přes Photon (Komoot, OSM data) — funguje i ze sdílených
    cloudových IP, kde Nominatim blokuje. Filtruje pouze ČR a SK.
    """
    url = "https://photon.komoot.io/api/"
    params = {"q": q, "limit": 15, "lang": "default"}
    try:
        resp = requests.get(url, params=params, headers=_NOMINATIM_HEADERS, timeout=15)
        resp.raise_for_status()
        data = resp.json()
    except (requests.RequestException, ValueError):
        return []

    features = data.get("features") if isinstance(data, dict) else None
    if not isinstance(features, list):
        return []

    results: list[dict] = []
    seen: set[tuple] = set()
    for feat in features:
        if not isinstance(feat, dict):
            continue
        props = feat.get("properties") or {}
        geom = feat.get("geometry") or {}
        coords = geom.get("coordinates") or []
        country = _resolve_cz_sk_country(props.get("countrycode", ""), props.get("country", ""))
        if country is None:
            continue
        try:
            lon = float(coords[0])
            lat = float(coords[1])
        except (IndexError, TypeError, ValueError):
            continue

        name = str(props.get("name") or "").strip()
        street = str(props.get("street") or "").strip()
        housenr = str(props.get("housenumber") or "").strip()
        primary = name or (f"{street} {housenr}".strip())
        locality = str(
            props.get("city")
            or props.get("district")
            or props.get("county")
            or props.get("state")
            or ""
        ).strip()
        postcode = str(props.get("postcode") or "N/A").strip() or "N/A"
        country_label = str(props.get("country") or "").strip()

        line_parts = [
            p for p in (primary, locality, postcode if postcode != "N/A" else "", country_label) if p
        ]
        display_name = ", ".join(dict.fromkeys(line_parts)) or q

        key = (round(lat, 4), round(lon, 4), display_name)
        if key in seen:
            continue
        seen.add(key)
        results.append({
            "lat": lat,
            "lon": lon,
            "display_name": display_name,
            "postcode": postcode,
            "country": country,
        })
    return results


def _search_nominatim(q: str) -> list[dict]:
    """Geokódování přes OSM Nominatim — záloha (funguje hlavně lokálně)."""
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
        country = _resolve_cz_sk_country(addr.get("country_code", ""), addr.get("country", ""))
        if country is None:
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


@st.cache_data(ttl=86400, show_spinner=False)
def search_domestic_location(query: str) -> list[dict]:
    """
    Vyhledání míst v ČR a na Slovensku.
    Primárně Photon (funguje i z cloudu), záloha Nominatim.
    Vrací list {lat, lon, display_name, postcode, country}.
    """
    q = (query or "").strip()
    if len(q) < 2:
        return []

    hits = _search_photon(q)
    if hits:
        return hits
    return _search_nominatim(q)


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


# Průměrná rychlost pro záložní odhad času jízdy (OSRM nedostupné)
_DOMESTIC_AVG_SPEED_KMH = 65.0


@st.cache_data(ttl=86400, show_spinner=False)
def get_driving_distance(
    lat1: float, lon1: float, lat2: float, lon2: float
) -> tuple[float, bool, float | None]:
    """
    Silniční vzdálenost v km + doba jízdy v minutách (OSRM).
    Vrací (km, použito_osrm, minuty | None).
    Při selhání API: haversine × 1,3, čas None a druhá hodnota False.
    """
    url = (
        "https://router.project-osrm.org/route/v1/driving/"
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
        duration_min: float | None
        try:
            duration_min = float(routes[0]["duration"]) / 60.0
            if duration_min <= 0:
                duration_min = None
        except (KeyError, TypeError, ValueError):
            duration_min = None
        return dist_km, True, duration_min
    except (requests.RequestException, ValueError, KeyError, TypeError, IndexError):
        fallback_km = haversine_distance(lat1, lon1, lat2, lon2) * _DOMESTIC_ROAD_FACTOR
        return fallback_km, False, None


def _format_drive_time(minutes: float | None) -> str:
    """Formát doby jízdy: '4 h 05 min' / '35 min' / '—'."""
    if minutes is None or minutes <= 0:
        return "—"
    h, m = divmod(int(round(minutes)), 60)
    return f"{h} h {m:02d} min" if h else f"{m} min"


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


def _render_domestic_price_breakdown(quote: dict) -> None:
    """Vizuální rozpad ceny: fixní složky (manipulace + přistavení) vs LTL km složka."""
    price_czk = quote.get("price_czk")
    if not quote.get("price_valid") or price_czk is None or price_czk <= 0:
        return

    parts = [
        ("Manipulace", float(quote.get("fix_handling", 0.0)), "#64748b"),
        ("Přistavení k hubu", float(quote.get("fix_positioning", 0.0)), "#94a3b8"),
        ("Kilometrová složka (LTL)", float(quote.get("km_part", 0.0)), "#0D6EFD"),
    ]
    model_total = sum(v for _, v, _ in parts)
    price = float(price_czk)
    if price > model_total + 0.5:
        parts.append(("Dorovnání na min. cenu", price - model_total, "#f59e0b"))

    fig = go.Figure()
    for name, val, color in parts:
        if val <= 0:
            continue
        pct = val / price * 100.0
        fig.add_trace(go.Bar(
            y=[""],
            x=[val],
            name=name,
            orientation="h",
            marker=dict(color=color),
            text=f"{pct:.0f} %",
            textposition="inside",
            insidetextanchor="middle",
            textfont=dict(family="IBM Plex Mono, monospace", size=11, color="#ffffff"),
            hovertemplate=f"<b>{name}</b>: %{{x:,.0f}} CZK ({pct:.0f} %)<extra></extra>",
        ))

    fig.update_layout(
        separators=_PLOT_SEPARATORS,
        barmode="stack",
        height=120,
        margin=dict(l=10, r=10, t=10, b=10),
        paper_bgcolor=_PLOT_PAPER,
        plot_bgcolor=_PLOT_BG,
        showlegend=True,
        legend=dict(
            orientation="h",
            yanchor="top",
            y=-0.15,
            xanchor="left",
            x=0,
            font=dict(family="IBM Plex Mono, monospace", size=10, color=_PLOT_TICK_COLOR),
            bgcolor=_PLOT_PAPER,
        ),
        xaxis=dict(visible=False, range=[0, price]),
        yaxis=dict(visible=False),
        hoverlabel=_HOVER_LABEL,
    )
    st.markdown("**Rozpad ceny — fixní vs kilometrová složka**")
    _show_plotly(fig, toolbar=False)
    fix_fee = float(quote.get("fix_fee", 0.0))
    km_part = float(quote.get("km_part", 0.0))
    st.caption(
        f"Fixní složka {format_num(fix_fee, 0)} CZK ({fix_fee / price * 100:.0f} %) · "
        f"kilometrová LTL složka {format_num(km_part, 0)} CZK ({km_part / price * 100:.0f} %)"
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
                road_km, used_osrm, drive_min = get_driving_distance(
                    start_lat, start_lon, dest_lat, dest_lon
                )

            dist_help = (
                "Reálná silniční trasa (OSRM)"
                if used_osrm
                else "Záložní odhad: vzdušná vzdálenost × 1,3 (OSRM nedostupné)"
            )
            if drive_min is not None:
                eta_help = "Čas jízdy dle OSRM (bez přestávek a nakládky)"
            else:
                drive_min = road_km / _DOMESTIC_AVG_SPEED_KMH * 60.0
                eta_help = (
                    f"Záložní odhad: {format_num(road_km, 0)} km ÷ "
                    f"{_DOMESTIC_AVG_SPEED_KMH:.0f} km/h (OSRM čas nedostupný)"
                )
            dist = road_km
            quote = _domestic_compute_quote(
                dist, waha, ldm, profile, sazba, vehicle_key
            )

            start_short = start_loc["display_name"].split(",")[0].strip()
            dest_short = dest_loc["display_name"].split(",")[0].strip()
            st.markdown(
                "<div style='background:rgba(77,159,255,0.10); padding:12px; border-radius:10px; "
                "border:1px solid rgba(77,159,255,0.28); border-left:4px solid #4D9FFF; margin-bottom:16px;'>"
                "<span style='font-family:Syne, sans-serif; font-size:1.1rem; "
                "font-weight:700; color:#F7FAFD;'>"
                f"📍 {start_short} "
                f"<span style='font-size:0.85rem; color:#8D99AB;'>"
                f"(PSČ: {start_loc.get('postcode', 'N/A')})</span> "
                f"&nbsp;➡️&nbsp; "
                f"{dest_short} "
                f"<span style='font-size:0.85rem; color:#8D99AB;'>"
                f"(PSČ: {dest_loc.get('postcode', 'N/A')})</span>"
                "</span></div>",
                unsafe_allow_html=True,
            )

            # Mapa trasy — nakládka (modrá) a vykládka (červená)
            map_df = pd.DataFrame([
                {"lat": float(start_lat), "lon": float(start_lon),
                 "color": "#0D6EFD", "size": 2500.0},
                {"lat": float(dest_lat), "lon": float(dest_lon),
                 "color": "#EF4444", "size": 2500.0},
            ])
            st.map(
                map_df,
                latitude="lat",
                longitude="lon",
                color="color",
                size="size",
                height=280,
            )
            st.caption("🔵 Nakládka · 🔴 Vykládka")

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
                "Odhadovaný čas jízdy",
                _format_drive_time(drive_min),
                help=eta_help,
            )
            m3.metric(
                "Využití kapacity",
                f"{cap_pct:.1f} %",
                help=f"Limituje {quote['binding']} · LTL koef. {ltl_koef:.2f}",
            )

            price_eur, eur_czk = _domestic_price_eur(price_czk)
            p_czk, p_eur = st.columns(2)
            if quote["price_valid"] and price_czk is not None:
                p_czk.metric(
                    "Odhadovaná cena k jednání",
                    f"{format_num(price_czk, 0)} CZK",
                    help="Model: kilometrová LTL složka + fixní poplatky (min. cena)",
                )
                if price_eur is not None and eur_czk:
                    p_eur.metric(
                        "Odhadovaná cena v EUR",
                        f"{format_num(price_eur, 0)} EUR",
                        help=f"Kurz ČNB {eur_czk:.4f} CZK/EUR",
                    )
                else:
                    p_eur.metric(
                        "Odhadovaná cena v EUR",
                        "—",
                        help="Kurz ČNB EUR/CZK není k dispozici",
                    )
                _render_domestic_price_breakdown(quote)
            else:
                p_czk.metric("Odhadovaná cena k jednání", "—")
                p_eur.metric("Odhadovaná cena v EUR", "—")
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
#  SEKCE: NÁSTROJE & TIPY (kalkulačky pro sklad / nákup / provoz)
# ──────────────────────────────────────────────────────────────────────────────

# Fill factor — IEC třídy lanění (MIN / GOLD střed / MAX)
# A_kov [mm²] = π × d²/4 × fill_factor
_FILL_FACTOR_ROWS: list[dict] = [
    {
        "cls": "Třída 1",
        "typ": "Plný (Solid — jeden drát)",
        "mat": "CU / AL",
        "min": 0.99, "gold": 1.00, "max": 1.00,
        "svg": "solid",
    },
    {
        "cls": "Třída 2",
        "typ": "Laněný (Nezhutněný)",
        "mat": "CU / AL",
        "min": 0.74, "gold": 0.77, "max": 0.80,
        "svg": "stranded",
    },
    {
        "cls": "Třída 2",
        "typ": "Laněný (Zhutněný — Compacted)",
        "mat": "CU / AL",
        "min": 0.85, "gold": 0.89, "max": 0.93,
        "svg": "compacted",
    },
    {
        "cls": "Třída 5",
        "typ": "Ohebný (Flexibilní)",
        "mat": "CU",
        "min": 0.72, "gold": 0.76, "max": 0.80,
        "svg": "flex5",
    },
    {
        "cls": "Třída 6",
        "typ": "Velmi ohebný (svařovací atd.)",
        "mat": "CU",
        "min": 0.65, "gold": 0.70, "max": 0.75,
        "svg": "flex6",
    },
]


def _fill_factor_cross_section_svg(kind: str, size: int = 120) -> str:
    """
    Schematický průřez vodiče (SVG) — solid / stranded / compacted / flex5 / flex6.
    Barevně Cu-odstín; mezery mezi dráty ukazují fill factor.
    """
    # měď: výplň + okraj; pozadí obálky
    fill, stroke, gap = "#C47A3A", "#8B5A2B", "#1A1F28"
    cx = cy = size / 2
    R = size * 0.42  # vnější obálka

    def wire(x: float, y: float, r: float, *, compact: bool = False) -> str:
        # compact = mírně „zmáčknutý“ elipsovitý tvar
        if compact:
            return (
                f'<ellipse cx="{x:.1f}" cy="{y:.1f}" rx="{r * 1.08:.1f}" ry="{r * 0.92:.1f}" '
                f'fill="{fill}" stroke="{stroke}" stroke-width="0.8"/>'
            )
        return (
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r:.1f}" '
            f'fill="{fill}" stroke="{stroke}" stroke-width="0.7"/>'
        )

    parts = [
        f'<svg viewBox="0 0 {size} {size}" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">',
        f'<circle cx="{cx}" cy="{cy}" r="{R + 2}" fill="{gap}" stroke="#2C3442" stroke-width="1.2"/>',
    ]

    if kind == "solid":
        parts.append(wire(cx, cy, R * 0.92))
    elif kind in ("stranded", "compacted"):
        compact = kind == "compacted"
        # 1 + 6 (7-drátové lano) — u compacted větší dráty = méně mezer
        r = R * (0.36 if compact else 0.30)
        ring = R * (0.62 if compact else 0.68)
        parts.append(wire(cx, cy, r, compact=compact))
        for i in range(6):
            ang = math.radians(60 * i - 90)
            parts.append(wire(cx + ring * math.cos(ang), cy + ring * math.sin(ang), r, compact=compact))
    elif kind == "flex5":
        # více menších drátů (≈ 1+6+12 styl, zjednodušeně náhodně-pravidelná mříž v kruhu)
        r = R * 0.155
        coords: list[tuple[float, float]] = [(cx, cy)]
        for ring_i, (n, rad) in enumerate([(6, 0.38), (12, 0.72)], start=1):
            for i in range(n):
                ang = math.radians(360 * i / n - 90 + (15 if ring_i == 2 else 0))
                coords.append((cx + R * rad * math.cos(ang), cy + R * rad * math.sin(ang)))
        for x, y in coords:
            parts.append(wire(x, y, r))
    else:  # flex6 — ještě jemnější dráty
        r = R * 0.095
        coords = [(cx, cy)]
        for n, rad in [(6, 0.26), (12, 0.48), (18, 0.72)]:
            for i in range(n):
                ang = math.radians(360 * i / n - 90)
                coords.append((cx + R * rad * math.cos(ang), cy + R * rad * math.sin(ang)))
        for x, y in coords:
            parts.append(wire(x, y, r))

    parts.append("</svg>")
    return "".join(parts)


def _circle_area_mm2(diameter_mm: float) -> float:
    """Geometrická plocha kruhu z průměru [mm] → mm²."""
    return math.pi * (diameter_mm ** 2) / 4.0


def render_fill_factor_calculator() -> None:
    """
    Fill factor: průměr vodiče → u každého schématu průřezu hned MIN / GOLD / MAX [mm²].
    """
    section_header("📐", "Fill factor — průřez vodiče z průměru")
    st.markdown(
        '<div class="info-box" style="margin-bottom:8px;">'
        "Zadej <strong>vnější průměr vodiče (mm)</strong> — pod každým schématem "
        "uvidíš odhad průřezu kovu <strong>MIN / GOLD / MAX</strong> "
        "(π × d²/4 × fill factor). Orientační hodnoty."
        "</div>",
        unsafe_allow_html=True,
    )

    diameter = st.number_input(
        "Průměr vodiče [mm]",
        min_value=0.10,
        max_value=100.0,
        value=19.13,
        step=0.01,
        format="%.2f",
        key="fill_factor_diameter",
        help="Naměřený / katalogový vnější průměr jádra (Cu/Al), ne celého kabelu.",
    )
    area = _circle_area_mm2(float(diameter))

    st.markdown(
        '<div class="fill-legend">'
        f'<span class="card-extra">Geometrická plocha: <strong>{format_num(area, 2)} mm²</strong></span>'
        '<span class="fill-chip fill-min" style="background:rgba(240,86,94,0.14);border:1px solid rgba(240,86,94,0.25);">MIN</span>'
        '<span class="fill-chip fill-gold" style="background:rgba(250,204,21,0.14);border:1px solid rgba(250,204,21,0.28);">GOLD</span>'
        '<span class="fill-chip fill-max" style="background:rgba(52,201,142,0.14);border:1px solid rgba(52,201,142,0.25);">MAX</span>'
        '<span class="card-extra">+ fill factor (ff) u každé hodnoty</span>'
        '</div>',
        unsafe_allow_html=True,
    )

    cards: list[str] = []
    for r in _FILL_FACTOR_ROWS:
        a_min = area * r["min"]
        a_gold = area * r["gold"]
        a_max = area * r["max"]
        cards.append(
            f'<div class="fill-gallery-card">'
            f'{_fill_factor_cross_section_svg(r["svg"], size=56)}'
            f'<div class="fill-gallery-title">{r["cls"]}</div>'
            f'<div class="fill-gallery-sub">{r["typ"]}</div>'
            f'<div class="fill-card-vals">'
            f'<div class="fill-card-row fill-min"><span>MIN</span>'
            f'<span>{format_num(a_min, 1)} mm²'
            f'<span class="fill-card-ff">ff {r["min"]:.2f}</span></span></div>'
            f'<div class="fill-card-row fill-gold"><span>GOLD</span>'
            f'<span>{format_num(a_gold, 1)} mm²'
            f'<span class="fill-card-ff">ff {r["gold"]:.2f}</span></span></div>'
            f'<div class="fill-card-row fill-max"><span>MAX</span>'
            f'<span>{format_num(a_max, 1)} mm²'
            f'<span class="fill-card-ff">ff {r["max"]:.2f}</span></span></div>'
            f'</div></div>'
        )

    st.markdown(
        f'<div class="fill-gallery">{"".join(cards)}</div>',
        unsafe_allow_html=True,
    )
    st.caption(
        "Hodnoty v mm² · A = π × d²/4 × fill factor · tmavé mezery = vzduch · "
        "Compacted = zhutněné lano · stejný průměr ≠ stejný průřez u různých tříd."
    )


def _drum_layer_plan(
    flange_mm: float,
    core_mm: float,
    width_mm: float,
    cable_mm: float,
    clearance_mm: float,
    target_m: float | None = None,
) -> dict:
    """
    Návin po vrstvách (řadách):
      závity na vrstvu = floor(l₂ / D)
      střední průměr i-té vrstvy = Kd + (2i+1)·D   (i od 0)
      délka plné vrstvy = závity · π · průměr_vrstvy
    Každá další vrstva má větší obvod — délka se automaticky zvětšuje.
    target_m: pokud zadáno, naplánuje jen potřebný návin (poslední vrstva může být částečná).
    """
    empty = {
        "f_eff": None, "turns_per_layer": 0, "max_layers": 0,
        "capacity_m": None, "layers_used": 0, "turns_total": 0.0,
        "length_m": 0.0, "fits": None, "rows": [],
    }
    if min(flange_mm, core_mm, width_mm, cable_mm) <= 0:
        return empty
    f_eff = flange_mm - 2.0 * clearance_mm
    if f_eff <= core_mm + cable_mm:
        return {**empty, "f_eff": f_eff}
    turns_per = int(math.floor(width_mm / cable_mm))
    if turns_per < 1:
        return {**empty, "f_eff": f_eff}
    # max. počet vrstev: vnější okraj poslední vrstvy ≤ F_eff
    # okraj vrstvy i: Kd + 2·(i+1)·D
    max_layers = int(math.floor((f_eff - core_mm) / (2.0 * cable_mm)))
    if max_layers < 1:
        return {**empty, "f_eff": f_eff, "turns_per_layer": turns_per}

    rows: list[dict] = []
    length_mm = 0.0
    turns_total = 0.0
    layers_used = 0
    remaining_mm = None if target_m is None else max(float(target_m), 0.0) * 1000.0

    for i in range(max_layers):
        mean_d = core_mm + (2 * i + 1) * cable_mm
        full_len = turns_per * math.pi * mean_d  # mm
        if remaining_mm is None:
            # plná kapacita
            rows.append({
                "Vrstva": i + 1,
                "Ø středu [mm]": round(mean_d, 1),
                "Závity": turns_per,
                "Délka [m]": round(full_len / 1000.0, 2),
            })
            length_mm += full_len
            turns_total += turns_per
            layers_used = i + 1
        else:
            if remaining_mm <= 0:
                break
            if full_len <= remaining_mm + 1e-9:
                use_turns = turns_per
                use_len = full_len
            else:
                # částečná vrstva — počet závitů úměrný zbývající délce
                use_turns = remaining_mm / (math.pi * mean_d)
                use_len = remaining_mm
            rows.append({
                "Vrstva": i + 1,
                "Ø středu [mm]": round(mean_d, 1),
                "Závity": round(use_turns, 1),
                "Délka [m]": round(use_len / 1000.0, 2),
            })
            length_mm += use_len
            turns_total += use_turns
            layers_used = i + 1
            remaining_mm -= use_len

    # kapacita celého bubnu (vždy spočítat)
    cap_mm = 0.0
    for i in range(max_layers):
        mean_d = core_mm + (2 * i + 1) * cable_mm
        cap_mm += turns_per * math.pi * mean_d

    fits = None
    if target_m is not None:
        fits = (remaining_mm is not None) and (remaining_mm <= 1e-6)

    return {
        "f_eff": f_eff,
        "turns_per_layer": turns_per,
        "max_layers": max_layers,
        "capacity_m": cap_mm / 1000.0,
        "layers_used": layers_used,
        "turns_total": turns_total,
        "length_m": length_mm / 1000.0,
        "fits": fits,
        "rows": rows,
    }


def _drum_schematic_svg(fd: float, kd: float, l2: float) -> str:
    """Kompaktní SVG schéma bubnu s popisky Fd / Kd / l2."""
    w, h = 140, 78
    display_w, display_h = 120, 68
    scale = 52.0 / max(fd, 1.0)
    flange_h = max(fd * scale, 14)
    core_h = max(kd * scale, 5)
    drum_w = max(min(l2 * scale * 0.85, 58), 22)
    cx, cy = w / 2, h / 2 + 2
    x0 = cx - drum_w / 2
    flange_w = 5
    wind_h = max((flange_h - core_h) / 2 - 2, 2)
    parts = [
        f'<svg width="{display_w}" height="{display_h}" viewBox="0 0 {w} {h}" '
        f'xmlns="http://www.w3.org/2000/svg" aria-hidden="true" '
        f'style="display:block;flex-shrink:0;max-width:120px;height:auto;">',
        f'<rect x="{x0 - flange_w:.1f}" y="{cy - flange_h / 2:.1f}" width="{flange_w}" '
        f'height="{flange_h:.1f}" rx="1.5" fill="#8D99AB" stroke="#2C3442"/>',
        f'<rect x="{x0 + drum_w:.1f}" y="{cy - flange_h / 2:.1f}" width="{flange_w}" '
        f'height="{flange_h:.1f}" rx="1.5" fill="#8D99AB" stroke="#2C3442"/>',
        f'<rect x="{x0:.1f}" y="{cy - core_h / 2:.1f}" width="{drum_w:.1f}" '
        f'height="{core_h:.1f}" fill="#C47A3A" stroke="#8B5A2B"/>',
        f'<rect x="{x0:.1f}" y="{cy - flange_h / 2 + 2:.1f}" width="{drum_w:.1f}" '
        f'height="{wind_h:.1f}" fill="rgba(77,159,255,0.18)" '
        f'stroke="rgba(77,159,255,0.35)" stroke-dasharray="2 2"/>',
        f'<text x="{cx}" y="10" text-anchor="middle" fill="#8D99AB" '
        f'font-size="7.5" font-family="Syne,sans-serif">čelo / jádro / šířka</text>',
        "</svg>",
    ]
    return "".join(parts)


def render_drum_capacity_calculator() -> None:
    """
    Kapacita bubnu + plán návinu po vrstvách + doporučení min. KTG dle ohybu.
    """
    section_header("🛢️", "Kapacita bubnu — co se vejde na buben")
    st.markdown(
        '<div class="info-box" style="margin-bottom:10px;">'
        "Návin se počítá <strong>po vrstvách (řadách)</strong> — každá další řada má větší obvod. "
        "Zadej rozměry bubnu a kabelu; volitelně délku k namotání. "
        "Podle ohybu navrhne nejmenší vhodné bubny z katalogu KTG."
        "</div>",
        unsafe_allow_html=True,
    )

    # Předvolba KTG → předvyplní rozměry
    _ktg_all = ktg_wood_drums() if ktg_wood_drums is not None else []

    if _ktg_all:
        preset_labels = ["Vlastní rozměry"] + [
            f"{d['label']} — čelo {d['Fd']} / jádro {d['Kd']} / šířka {d['I2']} mm"
            for d in _ktg_all
        ]
        preset = st.selectbox(
            "Předvolba bubnu (katalog KTG)",
            options=preset_labels,
            index=0,
            key="drum_ktg_preset",
            help="Vyber standardní KTG — předvyplní výšku čela, průměr jádra a šířku návinu. "
            "Nebo nech „Vlastní rozměry“.",
        )
        if preset != "Vlastní rozměry":
            idx = preset_labels.index(preset) - 1
            d0 = _ktg_all[idx]
            # předvyplnit session_state jen při změně předvolby
            prev = st.session_state.get("_drum_preset_applied")
            if prev != preset:
                st.session_state["drum_fd"] = float(d0["Fd"])
                st.session_state["drum_kd"] = float(d0["Kd"])
                st.session_state["drum_l2"] = float(d0["I2"])
                st.session_state["drum_max_load"] = float(d0["max_kg"])
                st.session_state["drum_empty_mass"] = float(d0["mass"])
                st.session_state["drum_kd_mode"] = "Průměr"
                st.session_state["_drum_preset_applied"] = preset
                st.session_state["_drum_preset_i1"] = float(d0["I1"])
                st.session_state["_drum_preset_mass"] = float(d0["mass"])
        else:
            st.session_state["_drum_preset_applied"] = preset

    c_a, c_b = st.columns([1.1, 1])
    with c_a:
        st.markdown("##### Rozměry bubnu [mm]")
        fd = st.number_input(
            "Výška čela [mm]",
            min_value=50.0, max_value=5000.0, value=1000.0, step=10.0,
            key="drum_fd",
            help="Jak vysoké je čelo bubnu (= vnější průměr čela, katalogově Fd).",
        )
        kd_mode = st.radio(
            "Průměr jádra zadat jako",
            options=["Průměr", "Obvod (metr)"],
            horizontal=True,
            key="drum_kd_mode",
            help="Když nejde změřit průměr, omotej metr kolem jádra. Průměr = obvod / π.",
        )
        if kd_mode.startswith("Obvod"):
            circ = st.number_input(
                "Obvod jádra [mm]",
                min_value=60.0, max_value=15000.0, value=1571.0, step=1.0,
                key="drum_kd_circ",
                help="Naměřený obvod jádra metrem. Průměr = obvod / π.",
            )
            kd = float(circ) / math.pi
            st.caption(f"→ průměr jádra = {format_num(kd, 1)} mm")
        else:
            kd = st.number_input(
                "Průměr jádra [mm]",
                min_value=20.0, max_value=4000.0, value=500.0, step=10.0,
                key="drum_kd",
                help="Průměr válce, na který se točí kabel (katalogově Kd).",
            )
        l2 = st.number_input(
            "Šířka návinu [mm]",
            min_value=20.0, max_value=3000.0, value=560.0, step=10.0,
            key="drum_l2",
            help="Vnitřní šířka mezi čely — kam se ukládá kabel (katalogově l₂ / I₂). "
            "Ne celková šířka bubnu přes čela.",
        )
        i1_hint = st.session_state.get("_drum_preset_i1")
        if i1_hint:
            st.caption(f"Celková šířka bubnu (přes čela) z KTG: **{format_num(i1_hint, 0)} mm**")
    with c_b:
        st.markdown("##### Kabel, ohyb & rezerva")
        d_cab = st.number_input(
            "Průměr kabelu [mm]",
            min_value=1.0, max_value=200.0, value=20.0, step=0.5,
            format="%.1f", key="drum_cable_d",
        )
        target_m = st.number_input(
            "Kolik metrů chci namotat (0 = jen kolik se vejde)",
            min_value=0.0, max_value=100000.0, value=0.0, step=10.0,
            key="drum_target_m",
            help="Zadej délku → spočítá závity a vrstvy (řady).",
        )
        clearance_mode = st.selectbox(
            "Volný okraj u čela (rezerva)",
            options=["1 × průměr kabelu", "2 × průměr kabelu", "Vlastní [mm]"],
            index=0, key="drum_clearance_mode",
            help="Mezera mezi horní vrstvou kabelu a okrajem čela.",
        )
        if clearance_mode == "Vlastní [mm]":
            clearance = st.number_input(
                "Rezerva [mm]",
                min_value=0.0, max_value=500.0, value=20.0, step=1.0,
                key="drum_clearance_mm",
            )
        else:
            mult = 1.0 if clearance_mode.startswith("1") else 2.0
            clearance = mult * float(d_cab)
            st.caption(f"Rezerva = {format_num(clearance, 1)} mm")

        bend_labels = {
            "12 × průměr kabelu (mírnější / VDE)": 12,
            "15 × průměr kabelu (běžné HELUKABEL)": 15,
            "20 × průměr kabelu": 20,
            "25 × průměr kabelu": 25,
            "30 × průměr kabelu": 30,
            "40 × průměr kabelu (nejpřísnější)": 40,
        }
        bend_label = st.selectbox(
            "Jak velké musí být jádro oproti kabelu (ohyb)",
            options=list(bend_labels.keys()),
            index=1, key="drum_bend_factor",
            help="Průměr jádra musí být aspoň N× průměr kabelu, jinak se kabel ohýbá moc těsně.",
        )
        bend_n = bend_labels[bend_label]

    with st.expander("Váha návinu a nosnost (volitelné)", expanded=True):
        w1, w2, w3 = st.columns(3)
        with w1:
            kg_per_km = st.number_input(
                "Váha kabelu [kg/km]",
                min_value=0.0, max_value=50000.0, value=0.0, step=10.0,
                key="drum_kg_km",
                help="Z katalogu kabelu. 0 = váhu nepočítat.",
            )
        with w2:
            empty_default = float(st.session_state.get("_drum_preset_mass") or 0.0)
            empty_mass = st.number_input(
                "Hmotnost prázdného bubnu [kg]",
                min_value=0.0, max_value=20000.0, value=empty_default, step=1.0,
                key="drum_empty_mass",
                help="U KTG předvolby se předvyplní. Jinak zadej ručně / 0.",
            )
        with w3:
            max_load = st.number_input(
                "Max. nosnost bubnu [kg]",
                min_value=0.0, max_value=50000.0, value=0.0, step=50.0,
                key="drum_max_load",
                help="Max. hmotnost kabelu na bubnu (ne včetně prázdného bubnu). 0 = nelimitovat.",
            )

    kd_min = bend_n * float(d_cab)
    bend_ok = kd >= kd_min

    st.markdown(
        f"##### Nejmenší vhodný buben z katalogu "
        f"(jádro ≥ **{bend_n:g} ×** průměr kabelu = {format_num(kd_min, 0)} mm)"
    )
    if ktg_min_drums_for_bend is None:
        st.caption("Tabulky KTG nejsou nasazené (`helukabel_tables.py`).")
    else:
        suited = ktg_min_drums_for_bend(float(d_cab), float(bend_n))
        if not suited:
            st.warning(
                f"Žádný standardní KTG buben nemá jádro ≥ {format_num(kd_min, 0)} mm "
                f"pro kabel Ø {format_num(d_cab, 1)} mm. Zvol mírnější ohyb nebo tenčí kabel."
            )
        else:
            best = suited[0]
            st.success(
                f"Nejmenší KTG: **{best['label']}** — "
                f"čelo {best['Fd']} / jádro {best['Kd']} / šířka návinu {best['I2']} mm "
                f"(nosnost {best['max_kg']} kg)."
            )
            show_n = min(8, len(suited))
            rec = pd.DataFrame([
                {
                    "KTG": d["label"],
                    "Výška čela": d["Fd"],
                    "Průměr jádra": d["Kd"],
                    "Šířka návinu": d["I2"],
                    "Jádro / kabel": round(d["Kd"] / d_cab, 1),
                    "Nosnost [kg]": d["max_kg"],
                }
                for d in suited[:show_n]
            ])
            st.dataframe(rec, use_container_width=True, hide_index=True)
            if len(suited) > show_n:
                st.caption(f"… a dalších {len(suited) - show_n} větších KTG splňuje ohyb.")

    if kd >= fd:
        st.markdown(
            '<div class="error-box">Průměr jádra musí být menší než výška / průměr čela.</div>',
            unsafe_allow_html=True,
        )
        return

    cap = _drum_layer_plan(fd, kd, l2, d_cab, clearance, target_m=None)
    plan = None
    if target_m and target_m > 0:
        plan = _drum_layer_plan(fd, kd, l2, d_cab, clearance, target_m=float(target_m))

    st.markdown(
        f'<div style="display:flex;gap:10px;align-items:center;flex-wrap:nowrap;'
        f'margin:4px 0 8px;max-width:560px;">'
        f'<div style="width:120px;flex:0 0 120px;line-height:0;">'
        f'{_drum_schematic_svg(fd, kd, l2)}'
        f'</div>'
        f'<div class="card-extra" style="font-size:0.82rem;line-height:1.35;margin:0;">'
        f'Čelo <strong>{format_num(fd, 0)}</strong> · '
        f'jádro <strong>{format_num(kd, 0)}</strong> · '
        f'šířka <strong>{format_num(l2, 0)}</strong> · '
        f'kabel <strong>{format_num(d_cab, 1)}</strong> mm<br>'
        f'Rezerva <strong>{format_num(clearance, 1)}</strong> → '
        f'max. průměr návinu <strong>{format_num(cap["f_eff"], 1) if cap["f_eff"] is not None else "—"}</strong> mm · '
        f'závity/řada <strong>{cap["turns_per_layer"]}</strong>'
        f'</div></div>',
        unsafe_allow_html=True,
    )

    if cap["capacity_m"] is None:
        st.markdown(
            '<div class="error-box">Po odečtení rezervy nezůstává prostor pro návin. '
            "Zmenši rezervu nebo zkontroluj rozměry.</div>",
            unsafe_allow_html=True,
        )
        return

    capacity_m = float(cap["capacity_m"])
    weight_limit_m: float | None = None
    if max_load > 0 and kg_per_km > 0:
        weight_limit_m = max_load / (kg_per_km / 1000.0)
    usable_m = capacity_m
    limit_note = ""
    if weight_limit_m is not None and weight_limit_m < capacity_m:
        usable_m = weight_limit_m
        limit_note = (
            f" · limitováno nosností ({format_num(max_load, 0)} kg / "
            f"{format_num(kg_per_km, 0)} kg/km → max {format_num(weight_limit_m, 0)} m)"
        )

    r1, r2, r3 = st.columns(3)
    with r1:
        st.metric("Kolik se vejde", f"{capacity_m:,.0f} m".replace(",", " "))
    with r2:
        st.metric("Použitelná délka", f"{usable_m:,.0f} m".replace(",", " "))
    with r3:
        st.metric(
            "Max. řad / závity v řadě",
            f"{cap['max_layers']} / {cap['turns_per_layer']}",
        )

    if bend_ok:
        st.markdown(
            f'<div class="success-box" style="margin-top:8px;">'
            f'✅ <strong>Ohyb OK</strong> — průměr jádra {format_num(kd, 0)} mm ≥ '
            f'{bend_n:g} × kabel = {format_num(kd_min, 0)} mm.'
            f'{limit_note}</div>',
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            f'<div class="warning-box" style="margin-top:8px;">'
            f'⚠️ <strong>Jádro je malé pro zvolený ohyb</strong> — '
            f'{format_num(kd, 0)} mm &lt; {bend_n:g} × kabel = {format_num(kd_min, 0)} mm.'
            f'{limit_note}</div>',
            unsafe_allow_html=True,
        )

    if plan is not None:
        st.markdown("##### Plán návinu pro zadanou délku")
        if plan["fits"]:
            m1, m2, m3 = st.columns(3)
            with m1:
                st.metric("Řady (vrstvy)", f"{plan['layers_used']}")
            with m2:
                st.metric("Závity celkem", f"{plan['turns_total']:.1f}")
            with m3:
                st.metric("Namotáno", f"{plan['length_m']:.1f} m")
            plan_df = pd.DataFrame(plan["rows"]).rename(columns={
                "Vrstva": "Řada",
                "Ø středu [mm]": "Průměr řady [mm]",
            })
            st.dataframe(plan_df, use_container_width=True, hide_index=True)
            st.caption(
                "Každá další řada má větší průměr → delší závit. "
                "Poslední řada může být jen částečně zaplněná."
            )
        else:
            st.error(
                f"Na tento buben se **{format_num(target_m, 0)} m** nevejde "
                f"(kapacita ≈ {format_num(capacity_m, 0)} m, max {cap['max_layers']} vrstev "
                f"× {cap['turns_per_layer']} závitů). "
                "Zvětši buben / šíři, nebo sniž rezervu."
            )
            if plan["rows"]:
                st.dataframe(pd.DataFrame(plan["rows"]), use_container_width=True, hide_index=True)
    else:
        with st.expander("Rozpis kapacity po vrstvách", expanded=False):
            st.dataframe(pd.DataFrame(cap["rows"]), use_container_width=True, hide_index=True)

    # ── Hmotnost návinu ───────────────────────────────────────────────────────
    length_for_weight = float(plan["length_m"]) if (plan and plan.get("fits")) else (
        float(target_m) if target_m and target_m > 0 else usable_m
    )
    if kg_per_km > 0 and length_for_weight > 0:
        cable_kg = length_for_weight * (kg_per_km / 1000.0)
        total_kg = cable_kg + float(empty_mass or 0.0)
        st.markdown("##### Hmotnost návinu")
        ww1, ww2, ww3 = st.columns(3)
        with ww1:
            st.metric(
                "Kabel",
                f"{cable_kg:,.0f} kg".replace(",", " "),
                help=f"{format_num(length_for_weight, 0)} m × {format_num(kg_per_km, 0)} kg/km",
            )
        with ww2:
            st.metric("Prázdný buben", f"{float(empty_mass or 0):,.0f} kg".replace(",", " "))
        with ww3:
            st.metric("Celkem (buben + kabel)", f"{total_kg:,.0f} kg".replace(",", " "))
        if max_load > 0:
            if cable_kg > max_load:
                st.error(
                    f"Kabel **{format_num(cable_kg, 0)} kg** překračuje nosnost bubnu "
                    f"**{format_num(max_load, 0)} kg**."
                )
            else:
                st.caption(
                    f"Využití nosnosti: {cable_kg / max_load * 100:.0f} % "
                    f"({format_num(cable_kg, 0)} / {format_num(max_load, 0)} kg kabelu)."
                )
        elif target_m and target_m > 0 and not (plan and plan.get("fits")):
            st.caption("Váha počítaná z cílové délky — na buben se ale celá nevejde.")
        elif not (target_m and target_m > 0):
            st.caption("Váha = použitelná kapacita bubnu (plný návin). Zadej metry výš pro konkrétní délku.")

    # ── Porovnání dvou bubnů ──────────────────────────────────────────────────
    st.markdown("##### Porovnání dvou bubnů")
    st.caption(
        "Buben A = rozměry výše. Buben B vyber z KTG (nebo zadej vlastní) — "
        "stejný kabel, rezerva a ohyb."
    )
    cmp_on = st.checkbox("Zapnout porovnání s druhým bubnem", key="drum_cmp_on")
    if cmp_on:
        b_src = st.radio(
            "Buben B",
            options=["Z katalogu KTG", "Vlastní rozměry"],
            horizontal=True,
            key="drum_cmp_src",
        )
        if b_src.startswith("Z katalogu") and _ktg_all:
            b_labels = [
                f"{d['label']} — čelo {d['Fd']} / jádro {d['Kd']} / šířka {d['I2']}"
                for d in _ktg_all
            ]
            # výchozí: nejmenší KTG dle ohybu, jinak 101/10
            default_i = 0
            if ktg_min_drums_for_bend is not None:
                suited_b = ktg_min_drums_for_bend(float(d_cab), float(bend_n))
                if suited_b:
                    for i, d in enumerate(_ktg_all):
                        if d["label"] == suited_b[0]["label"]:
                            default_i = i
                            break
            b_pick = st.selectbox(
                "KTG buben B", options=b_labels, index=default_i, key="drum_cmp_ktg",
            )
            b_drum = _ktg_all[b_labels.index(b_pick)]
            fd_b, kd_b, l2_b = float(b_drum["Fd"]), float(b_drum["Kd"]), float(b_drum["I2"])
            empty_b = float(b_drum["mass"])
            max_load_b = float(b_drum["max_kg"])
            label_b = b_drum["label"]
        else:
            bc1, bc2, bc3 = st.columns(3)
            with bc1:
                fd_b = st.number_input(
                    "B — výška čela", 50.0, 5000.0, 1250.0, 10.0, key="drum_cmp_fd",
                )
            with bc2:
                kd_b = st.number_input(
                    "B — průměr jádra", 20.0, 4000.0, 630.0, 10.0, key="drum_cmp_kd",
                )
            with bc3:
                l2_b = st.number_input(
                    "B — šířka návinu", 20.0, 3000.0, 670.0, 10.0, key="drum_cmp_l2",
                )
            empty_b = st.number_input(
                "B — prázdný buben [kg]", 0.0, 20000.0, 0.0, 1.0, key="drum_cmp_empty",
            )
            max_load_b = st.number_input(
                "B — nosnost [kg]", 0.0, 50000.0, 0.0, 50.0, key="drum_cmp_load",
            )
            label_b = "Vlastní B"

        if kd_b >= fd_b:
            st.warning("U bubnu B musí být jádro menší než čelo.")
        else:
            cap_b = _drum_layer_plan(fd_b, kd_b, l2_b, d_cab, clearance, target_m=None)
            plan_b = None
            if target_m and target_m > 0:
                plan_b = _drum_layer_plan(
                    fd_b, kd_b, l2_b, d_cab, clearance, target_m=float(target_m),
                )
            cap_a_m = capacity_m
            cap_b_m = float(cap_b["capacity_m"] or 0)
            usable_b = cap_b_m
            if max_load_b > 0 and kg_per_km > 0:
                lim_b = max_load_b / (kg_per_km / 1000.0)
                usable_b = min(usable_b, lim_b)

            bend_a = "✅" if bend_ok else "⚠️"
            bend_b = "✅" if kd_b >= kd_min else "⚠️"
            fits_a = "—"
            fits_b = "—"
            layers_a = turns_a = layers_b = turns_b = "—"
            if target_m and target_m > 0:
                fits_a = "ano" if (plan and plan.get("fits")) else "ne"
                fits_b = "ano" if (plan_b and plan_b.get("fits")) else "ne"
                if plan and plan.get("fits"):
                    layers_a = str(plan["layers_used"])
                    turns_a = f"{plan['turns_total']:.0f}"
                if plan_b and plan_b.get("fits"):
                    layers_b = str(plan_b["layers_used"])
                    turns_b = f"{plan_b['turns_total']:.0f}"

            cmp_rows = [
                {"Údaj": "Název", "Buben A (výše)": "Aktuální", "Buben B": label_b},
                {"Údaj": "Čelo / jádro / šířka [mm]",
                 "Buben A (výše)": f"{format_num(fd, 0)} / {format_num(kd, 0)} / {format_num(l2, 0)}",
                 "Buben B": f"{format_num(fd_b, 0)} / {format_num(kd_b, 0)} / {format_num(l2_b, 0)}"},
                {"Údaj": "Ohyb (jádro ≥ N×D)",
                 "Buben A (výše)": bend_a,
                 "Buben B": bend_b},
                {"Údaj": "Kapacita [m]",
                 "Buben A (výše)": f"{cap_a_m:,.0f}".replace(",", " "),
                 "Buben B": f"{cap_b_m:,.0f}".replace(",", " ")},
                {"Údaj": "Použitelná délka [m]",
                 "Buben A (výše)": f"{usable_m:,.0f}".replace(",", " "),
                 "Buben B": f"{usable_b:,.0f}".replace(",", " ")},
                {"Údaj": "Max. řad / závity v řadě",
                 "Buben A (výše)": f"{cap['max_layers']} / {cap['turns_per_layer']}",
                 "Buben B": f"{cap_b['max_layers']} / {cap_b['turns_per_layer']}"},
            ]
            if target_m and target_m > 0:
                cmp_rows += [
                    {"Údaj": f"Vejde se {format_num(target_m, 0)} m?",
                     "Buben A (výše)": fits_a, "Buben B": fits_b},
                    {"Údaj": "Řady / závity pro cíl",
                     "Buben A (výše)": f"{layers_a} / {turns_a}",
                     "Buben B": f"{layers_b} / {turns_b}"},
                ]
            if kg_per_km > 0:
                la = float(plan["length_m"]) if (plan and plan.get("fits")) else (
                    float(target_m) if target_m and target_m > 0 else usable_m
                )
                lb = float(plan_b["length_m"]) if (plan_b and plan_b.get("fits")) else (
                    float(target_m) if target_m and target_m > 0 else usable_b
                )
                ca = la * kg_per_km / 1000.0 if la > 0 else 0.0
                cb = lb * kg_per_km / 1000.0 if lb > 0 else 0.0
                cmp_rows += [
                    {"Údaj": "Váha kabelu [kg]",
                     "Buben A (výše)": f"{ca:,.0f}".replace(",", " "),
                     "Buben B": f"{cb:,.0f}".replace(",", " ")},
                    {"Údaj": "Prázdný buben [kg]",
                     "Buben A (výše)": f"{float(empty_mass or 0):,.0f}".replace(",", " "),
                     "Buben B": f"{empty_b:,.0f}".replace(",", " ")},
                    {"Údaj": "Celkem [kg]",
                     "Buben A (výše)": f"{ca + float(empty_mass or 0):,.0f}".replace(",", " "),
                     "Buben B": f"{cb + empty_b:,.0f}".replace(",", " ")},
                ]
            st.dataframe(pd.DataFrame(cmp_rows), use_container_width=True, hide_index=True)
            # rychlý verdikt
            if target_m and target_m > 0 and plan and plan_b:
                if plan.get("fits") and not plan_b.get("fits"):
                    st.info("Pro zadanou délku stačí **buben A**, buben B je malý.")
                elif plan_b.get("fits") and not plan.get("fits"):
                    st.info("Pro zadanou délku stačí **buben B**, buben A je malý.")
                elif plan.get("fits") and plan_b.get("fits"):
                    if fd_b < fd:
                        st.success("Oba bubny délku zvládnou — **B má menší čelo** (kompaktnější).")
                    elif fd < fd_b:
                        st.success("Oba bubny délku zvládnou — **A má menší čelo** (kompaktnější).")
                    else:
                        st.success("Oba bubny zadanou délku zvládnou.")
            elif cap_b_m > cap_a_m * 1.05:
                st.caption(f"Buben B má větší kapacitu (+{cap_b_m - cap_a_m:,.0f} m).".replace(",", " "))
            elif cap_a_m > cap_b_m * 1.05:
                st.caption(f"Buben A má větší kapacitu (+{cap_a_m - cap_b_m:,.0f} m).".replace(",", " "))

    st.caption(
        "Model: ideální těsný návin (závity vedle sebe, vrstvy na sobě). "
        "V praxi bývá délka o něco nižší (mezery, tuhost kabelu)."
    )


def render_tools_and_tips() -> None:
    """Hub praktických kalkulaček a tipů pro sklad, nákup i provoz."""
    section_header("🧰", "Nástroje & tipy")
    st.markdown(
        '<div class="info-box" style="margin-bottom:14px;">'
        "Praktické kalkulačky a tipy pro <strong>sklad</strong>, <strong>nákup</strong> "
        "i běžný provoz. Postupně sem přidáme další nástroje — vyber si aktuální funkci níže."
        "</div>",
        unsafe_allow_html=True,
    )

    tool = st.selectbox(
        "Nástroj",
        options=[
            "Fill factor — průřez vodiče z průměru",
            "Kapacita bubnu — co se vejde na buben",
            "Technické tabulky HELUKABEL (katalog)",
        ],
        key="tools_hub_select",
        help="Seznam se bude rozšiřovat o další kalkulačky a tipy.",
    )
    st.markdown("<br>", unsafe_allow_html=True)

    if tool.startswith("Fill factor"):
        render_fill_factor_calculator()
    elif tool.startswith("Kapacita bubnu"):
        render_drum_capacity_calculator()
    elif tool.startswith("Technické tabulky"):
        if render_helukabel_catalog is None:
            st.error(
                "Modul `helukabel_tables.py` není nasazený. "
                "Nahraj ho do kořene repozitáře na GitHub (vedle `app.py`) "
                "a ideálně i složku `assets/helukabel/` se skeny."
            )
        else:
            render_helukabel_catalog()

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
            Yahoo Finance (grafy, ropa BZ=F) &nbsp;·&nbsp; Transitní model Čína→ČR
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

    render_morning_briefing()

    tabs_list = [
        "🔩 Kovy & Trh",
        "💱 Měnové kurzy",
        "🛢️ Plasty & Ropa",
        "🚛 Logistika ČR & SK",
        "🧰 Nástroje & tipy",
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
            render_tools_and_tips()
    else:
        with tabs[3]:
            render_domestic_logistics()
        with tabs[4]:
            render_tools_and_tips()

    render_footer()


if __name__ == "__main__":
    main()
