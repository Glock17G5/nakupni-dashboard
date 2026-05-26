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
import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd

# ── Web scraping ───────────────────────────────────────────────────────────────
import requests
from bs4 import BeautifulSoup

# ── Finanční data ──────────────────────────────────────────────────────────────
import yfinance as yf

# ── Vizualizace ────────────────────────────────────────────────────────────────
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

col1, col2 = st.columns([1, 4])
with col1:
    try:
        st.image("logo.png", width=150)
    except Exception:
        pass
with col2:
    st.title("pbcable - Nákupní terminál")

# ==============================================================================
# CSS INJEKCE — Veškeré styly přímo v kódu
# ==============================================================================
CUSTOM_CSS = """
<style>
/* ── Google Fonts import ────────────────────────────────────────────────── */
@import url('https://fonts.googleapis.com/css2?family=Syne:wght@400;500;600;700;800&family=IBM+Plex+Mono:ital,wght@0,300;0,400;0,500;0,600;1,400&display=swap');

/* ── Globální reset a základní typografie ────────────────────────────────── */
*, *::before, *::after {
    box-sizing: border-box;
}

/* ── Hlavní pozadí aplikace ─────────────────────────────────────────────── */
.stApp,
[data-testid="stAppViewContainer"],
[data-testid="stMain"],
section[data-testid="stMain"] > div:first-child {
    background-color: #050d1a !important;
    font-family: 'Syne', sans-serif !important;
}

/* ── Skrytí výchozích Streamlit elementů ────────────────────────────────── */
#MainMenu { visibility: hidden; }
header[data-testid="stHeader"] { visibility: hidden; height: 0; }
footer { visibility: hidden; }
[data-testid="stDecoration"] { display: none; }
[data-testid="stStatusWidget"] { display: none; }

/* ── Sidebar ─────────────────────────────────────────────────────────────── */
[data-testid="stSidebar"],
[data-testid="stSidebarContent"] {
    background-color: #060e1c !important;
    border-right: 1px solid #0f1f35 !important;
}

/* ── Scrollbar ───────────────────────────────────────────────────────────── */
::-webkit-scrollbar { width: 5px; height: 5px; }
::-webkit-scrollbar-track { background: #050d1a; }
::-webkit-scrollbar-thumb { background: #0f1f35; border-radius: 4px; }
::-webkit-scrollbar-thumb:hover { background: #1a2f50; }

/* ══════════════════════════════════════════════════════════════════════════
   ZÁHLAVÍ DASHBOARDU
   ══════════════════════════════════════════════════════════════════════════ */
.dash-header {
    position: relative;
    background: linear-gradient(135deg, #070e1e 0%, #0a1525 40%, #07101d 100%);
    border: 1px solid #0f2040;
    border-radius: 18px;
    padding: 28px 36px 24px 36px;
    margin-bottom: 24px;
    overflow: hidden;
}

/* Animated gradient top border */
.dash-header::before {
    content: '';
    position: absolute;
    top: 0; left: 0; right: 0;
    height: 2px;
    background: linear-gradient(90deg,
        #f59e0b 0%,
        #ef4444 20%,
        #3b82f6 45%,
        #10b981 65%,
        #8b5cf6 85%,
        #f59e0b 100%
    );
    background-size: 200% 100%;
    animation: borderSlide 6s linear infinite;
}

/* Subtle grid texture */
.dash-header::after {
    content: '';
    position: absolute;
    inset: 0;
    background-image:
        linear-gradient(rgba(15, 32, 64, 0.4) 1px, transparent 1px),
        linear-gradient(90deg, rgba(15, 32, 64, 0.4) 1px, transparent 1px);
    background-size: 40px 40px;
    pointer-events: none;
}

@keyframes borderSlide {
    0%   { background-position: 0% 0%; }
    100% { background-position: 200% 0%; }
}

.dash-header-content {
    position: relative;
    z-index: 1;
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
    color: #e8f4ff;
    letter-spacing: -0.5px;
    line-height: 1.1;
    margin: 0 0 6px 0;
}

.dash-title span {
    background: linear-gradient(90deg, #f59e0b, #fbbf24);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
}

.dash-subtitle {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.72rem;
    color: #2a4a7a;
    letter-spacing: 2px;
    text-transform: uppercase;
}

.dash-meta {
    text-align: right;
}

.dash-timestamp {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.73rem;
    color: #1e3a60;
    line-height: 1.8;
}

.dash-timestamp strong {
    color: #2a5080;
}

/* ══════════════════════════════════════════════════════════════════════════
   STATUS BADGES
   ══════════════════════════════════════════════════════════════════════════ */
.badge {
    display: inline-flex;
    align-items: center;
    gap: 5px;
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.65rem;
    font-weight: 500;
    padding: 3px 10px;
    border-radius: 100px;
    letter-spacing: 0.5px;
    white-space: nowrap;
}

.badge-live {
    background: rgba(16, 185, 129, 0.1);
    color: #10b981;
    border: 1px solid rgba(16, 185, 129, 0.25);
}

.badge-live::before {
    content: '●';
    font-size: 0.5rem;
    animation: pulse-green 1.5s infinite;
}

.badge-offline {
    background: rgba(239, 68, 68, 0.08);
    color: #ef4444;
    border: 1px solid rgba(239, 68, 68, 0.2);
}

.badge-offline::before { content: '●'; font-size: 0.5rem; }

.badge-model {
    background: rgba(245, 158, 11, 0.08);
    color: #f59e0b;
    border: 1px solid rgba(245, 158, 11, 0.2);
}

.badge-model::before { content: '◆'; font-size: 0.5rem; }

@keyframes pulse-green {
    0%, 100% { opacity: 1; }
    50%       { opacity: 0.3; }
}

/* ══════════════════════════════════════════════════════════════════════════
   SEKČNÍ NADPISY
   ══════════════════════════════════════════════════════════════════════════ */
.section-header {
    display: flex;
    align-items: center;
    flex-wrap: wrap;
    gap: 10px 12px;
    margin: 28px 0 20px 0;
    padding-bottom: 14px;
    border-bottom: 1px solid #0a1830;
    line-height: 1.4;
}

.section-icon {
    font-size: 1.1rem;
    line-height: 1.3;
    flex-shrink: 0;
}

.section-title {
    font-family: 'Syne', sans-serif;
    font-size: 0.95rem;
    font-weight: 700;
    color: #8ab0d4;
    text-transform: uppercase;
    letter-spacing: 1.5px;
    flex: 1 1 auto;
    line-height: 1.45;
    min-width: 0;
}

/* ══════════════════════════════════════════════════════════════════════════
   METRICKÉ KARTY
   ══════════════════════════════════════════════════════════════════════════ */
.metric-card {
    position: relative;
    background: linear-gradient(145deg, #090f1e 0%, #060c18 60%, #05090f 100%);
    border: 1px solid #0d1d35;
    border-radius: 14px;
    padding: 18px 18px 16px 18px;
    overflow: visible;
    transition: transform 0.18s ease, border-color 0.18s ease, box-shadow 0.18s ease;
    min-height: auto;
    cursor: default;
    margin-bottom: 10px;
}

.metric-card:hover {
    transform: translateY(-3px);
    border-color: #1a2f50;
    box-shadow: 0 12px 40px rgba(0, 0, 0, 0.5);
}

/* Levý barevný pruh místo top border – elegantnější */
.metric-card::before {
    content: '';
    position: absolute;
    top: 0; left: 0;
    width: 3px;
    height: 100%;
    border-radius: 14px 0 0 14px;
}

/* Jemný lesk v levém horním rohu */
.metric-card::after {
    content: '';
    position: absolute;
    top: 0; left: 3px; right: 0;
    height: 1px;
    background: linear-gradient(90deg, rgba(255,255,255,0.04), transparent);
}

/* ── Barevné varianty karet ─────────────────────────────────────────────── */
.card-copper   ::before, .card-copper   { --accent: #f97316; }
.card-copper::before   { background: linear-gradient(180deg, #f97316, #c2440a); }

.card-aluminum ::before, .card-aluminum { --accent: #10b981; }
.card-aluminum::before { background: linear-gradient(180deg, #10b981, #047857); }

.card-lead     ::before, .card-lead     { --accent: #8b5cf6; }
.card-lead::before     { background: linear-gradient(180deg, #8b5cf6, #5b21b6); }

.card-zinc     ::before, .card-zinc     { --accent: #6366f1; }
.card-zinc::before     { background: linear-gradient(180deg, #6366f1, #3730a3); }

.card-tin      ::before, .card-tin      { --accent: #ec4899; }
.card-tin::before      { background: linear-gradient(180deg, #ec4899, #9d174d); }

.card-nickel   ::before, .card-nickel   { --accent: #06b6d4; }
.card-nickel::before   { background: linear-gradient(180deg, #06b6d4, #0e7490); }

.card-steel    ::before, .card-steel    { --accent: #64748b; }
.card-steel::before    { background: linear-gradient(180deg, #94a3b8, #475569); }

.card-usd      ::before, .card-usd      { --accent: #22c55e; }
.card-usd::before      { background: linear-gradient(180deg, #22c55e, #166534); }

.card-eur      ::before, .card-eur      { --accent: #3b82f6; }
.card-eur::before      { background: linear-gradient(180deg, #3b82f6, #1d4ed8); }

.card-cny      ::before, .card-cny      { --accent: #ef4444; }
.card-cny::before      { background: linear-gradient(180deg, #ef4444, #991b1b); }

.card-oil      ::before, .card-oil      { --accent: #f59e0b; }
.card-oil::before      { background: linear-gradient(180deg, #f59e0b, #b45309); }

.card-plastic  ::before, .card-plastic  { --accent: #14b8a6; }
.card-plastic::before  { background: linear-gradient(180deg, #14b8a6, #0d9488); }

.card-logistics::before, .card-logistics { --accent: #a78bfa; }
.card-logistics::before{ background: linear-gradient(180deg, #a78bfa, #6d28d9); }

.card-neutral  ::before, .card-neutral  { --accent: #475569; }
.card-neutral::before  { background: linear-gradient(180deg, #475569, #1e293b); }

/* ── Obsah metrické karty ───────────────────────────────────────────────── */
.card-label {
    font-family: 'Syne', sans-serif;
    font-size: 0.66rem;
    font-weight: 600;
    color: #2a4a78;
    text-transform: uppercase;
    letter-spacing: 1.2px;
    margin-bottom: 10px;
    line-height: 1.4;
    white-space: normal;
    overflow: visible;
    word-wrap: break-word;
}

.card-value {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 1.5rem;
    font-weight: 600;
    color: #dceeff;
    line-height: 1.3;
    letter-spacing: -0.5px;
    margin-bottom: 8px;
    word-wrap: break-word;
}

.card-value-sm {
    font-size: 1.15rem;
}

.card-unit {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.67rem;
    color: #1e3a5a;
    margin-bottom: 12px;
    line-height: 1.45;
    white-space: normal;
    word-wrap: break-word;
}

.card-delta-row {
    display: flex;
    align-items: center;
    gap: 6px;
    flex-wrap: wrap;
    margin-top: 4px;
    margin-bottom: 6px;
    line-height: 1.4;
}

.delta-chip {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.72rem;
    font-weight: 500;
    padding: 2px 8px;
    border-radius: 6px;
    display: inline-block;
}

.delta-up   { background: rgba(16, 185, 129, 0.12); color: #10b981; }
.delta-down { background: rgba(239, 68, 68, 0.12);  color: #ef4444; }
.delta-flat { background: rgba(100, 116, 139, 0.12); color: #475569; }

.card-extra {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.62rem;
    color: #1e3a5a;
    margin-top: 8px;
    margin-bottom: 2px;
    line-height: 1.5;
    font-style: italic;
    word-wrap: break-word;
}

/* ══════════════════════════════════════════════════════════════════════════
   SPREAD KARTA
   ══════════════════════════════════════════════════════════════════════════ */
.spread-card {
    background: linear-gradient(145deg, #080f1f 0%, #060c18 100%);
    border: 1px solid #0d1d35;
    border-radius: 12px;
    padding: 14px 16px;
    margin-bottom: 8px;
}

.spread-label {
    font-family: 'Syne', sans-serif;
    font-size: 0.63rem;
    font-weight: 700;
    color: #2a4a78;
    text-transform: uppercase;
    letter-spacing: 1.2px;
    margin-bottom: 8px;
    line-height: 1.4;
}

.spread-value {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 1.25rem;
    font-weight: 600;
    letter-spacing: -0.5px;
    line-height: 1.35;
    margin-bottom: 6px;
}

.spread-details {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.65rem;
    color: #1e3a5a;
    margin-top: 4px;
    line-height: 1.6;
}

/* ══════════════════════════════════════════════════════════════════════════
   GRAFY
   ══════════════════════════════════════════════════════════════════════════ */
.chart-wrap {
    background: linear-gradient(145deg, #070e1e 0%, #050c18 100%);
    border: 1px solid #0a1830;
    border-radius: 14px;
    padding: 18px 14px 14px 14px;
    overflow: visible;
    margin-bottom: 14px;
}

.chart-wrap .js-plotly-plot {
    overflow: visible !important;
}

/* Mezery mezi sloupci (PC) */
[data-testid="stHorizontalBlock"] {
    gap: 0.65rem !important;
    align-items: stretch !important;
}

div[data-testid="column"] {
    padding-left: 6px !important;
    padding-right: 6px !important;
    margin-bottom: 10px !important;
}

/* ══════════════════════════════════════════════════════════════════════════
   MOBILNÍ REŽIM (max-width: 768px)
   ══════════════════════════════════════════════════════════════════════════ */
@media (max-width: 768px) {
    /* Hlavní kontejner – menší vnitřní okraje */
    section[data-testid="stMain"] > div:first-child {
        padding-left: 0.4rem !important;
        padding-right: 0.4rem !important;
    }

    .dash-header {
        padding: 16px 14px 14px 14px;
        margin-bottom: 14px;
        border-radius: 14px;
    }

    .dash-title {
        font-size: 1.35rem;
    }

    .dash-subtitle {
        font-size: 0.62rem;
        letter-spacing: 1.4px;
    }

    .dash-timestamp {
        font-size: 0.62rem;
        line-height: 1.5;
    }

    .section-header {
        margin: 18px 0 8px 0;
        padding-bottom: 6px;
    }

    .section-title {
        font-size: 0.8rem;
        letter-spacing: 1.1px;
    }

    .metric-card {
        padding: 14px 12px 12px 12px;
        min-height: auto;
        margin-bottom: 10px;
    }

    .card-label {
        font-size: 0.6rem;
        margin-bottom: 8px;
        line-height: 1.45;
    }

    .card-value {
        font-size: 1.25rem;
        margin-bottom: 8px;
        line-height: 1.3;
    }

    .card-value-sm {
        font-size: 1rem;
        line-height: 1.3;
    }

    .card-unit {
        font-size: 0.6rem;
        margin-bottom: 10px;
        line-height: 1.45;
    }

    .card-extra {
        font-size: 0.58rem;
        margin-top: 6px;
        line-height: 1.5;
    }

    .spread-card {
        padding: 10px 10px;
        margin-bottom: 6px;
    }

    .spread-value {
        font-size: 1.05rem;
    }

    .spread-details {
        font-size: 0.6rem;
    }

    .info-box,
    .warning-box,
    .error-box {
        font-size: 0.65rem;
        padding: 8px 10px;
        margin: 6px 0;
    }

    .chart-wrap {
        padding: 14px 10px 12px 10px;
        border-radius: 10px;
        margin-bottom: 12px;
    }

    /* Sloupce – na mobilu stack vertikálně */
    [data-testid="stHorizontalBlock"] {
        flex-direction: column !important;
        gap: 0.5rem !important;
    }

    [data-testid="stHorizontalBlock"] > div {
        width: 100% !important;
    }
}

/* ══════════════════════════════════════════════════════════════════════════
   INFO / WARNING / ERROR BOXY
   ══════════════════════════════════════════════════════════════════════════ */
.info-box {
    background: rgba(59, 130, 246, 0.05);
    border: 1px solid rgba(59, 130, 246, 0.15);
    border-left: 3px solid #3b82f6;
    border-radius: 8px;
    padding: 10px 14px;
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.73rem;
    color: #3a6a9a;
    line-height: 1.5;
    margin: 8px 0;
}

.warning-box {
    background: rgba(245, 158, 11, 0.05);
    border: 1px solid rgba(245, 158, 11, 0.15);
    border-left: 3px solid #f59e0b;
    border-radius: 8px;
    padding: 10px 14px;
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.73rem;
    color: #7a5a20;
    line-height: 1.5;
    margin: 8px 0;
}

.error-box {
    background: rgba(239, 68, 68, 0.05);
    border: 1px solid rgba(239, 68, 68, 0.12);
    border-radius: 8px;
    padding: 10px 14px;
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.7rem;
    color: #5a2a2a;
    text-align: center;
    line-height: 1.5;
    margin: 6px 0;
}

/* ══════════════════════════════════════════════════════════════════════════
   TABULKY
   ══════════════════════════════════════════════════════════════════════════ */
.data-table-wrap {
    background: linear-gradient(145deg, #070e1e 0%, #050c18 100%);
    border: 1px solid #0a1830;
    border-radius: 14px;
    padding: 18px 20px;
    overflow-x: auto;
}

.data-table-wrap table {
    width: 100%;
    border-collapse: collapse;
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.78rem;
}

.data-table-wrap th {
    font-family: 'Syne', sans-serif;
    font-size: 0.63rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 1.2px;
    color: #2a4a78;
    padding: 8px 12px;
    border-bottom: 1px solid #0a1830;
    text-align: left;
    white-space: nowrap;
}

.data-table-wrap td {
    color: #6a9ac0;
    padding: 9px 12px;
    border-bottom: 1px solid #050d1a;
    white-space: nowrap;
}

.data-table-wrap tr:last-child td { border-bottom: none; }
.data-table-wrap tr:hover td { background: rgba(15, 30, 60, 0.4); }

/* ══════════════════════════════════════════════════════════════════════════
   KALKULÁTOR
   ══════════════════════════════════════════════════════════════════════════ */
.calc-result {
    background: linear-gradient(145deg, #070e1e 0%, #050c18 100%);
    border: 1px solid #0a1830;
    border-radius: 10px;
    padding: 14px 16px;
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.85rem;
    color: #5a9ad4;
    text-align: center;
    margin: 4px 0;
}

.calc-result-label {
    font-family: 'Syne', sans-serif;
    font-size: 0.63rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 1px;
    color: #2a4a78;
    margin-bottom: 4px;
}

.calc-result-value {
    font-size: 1.2rem;
    font-weight: 600;
    color: #a0d4f0;
    letter-spacing: -0.3px;
}

/* ══════════════════════════════════════════════════════════════════════════
   ODDĚLOVAČ
   ══════════════════════════════════════════════════════════════════════════ */
.section-divider {
    height: 1px;
    background: linear-gradient(90deg, transparent 0%, #0a1830 20%, #0f2040 50%, #0a1830 80%, transparent 100%);
    margin: 28px 0;
}

/* ══════════════════════════════════════════════════════════════════════════
   FOOTER
   ══════════════════════════════════════════════════════════════════════════ */
.dash-footer {
    text-align: center;
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.65rem;
    color: #0f2040;
    padding: 24px 0 12px 0;
    border-top: 1px solid #080e1c;
    margin-top: 40px;
    line-height: 2;
}

/* ══════════════════════════════════════════════════════════════════════════
   STREAMLIT PŘEPISY
   ══════════════════════════════════════════════════════════════════════════ */

/* Sloupce – mezery definovány výše u .chart-wrap bloku */

/* Streamlit tlačítka */
button[kind="secondary"] {
    font-family: 'Syne', sans-serif !important;
    font-size: 0.78rem !important;
    background: #080f1e !important;
    border: 1px solid #0f2040 !important;
    color: #4a7ab5 !important;
    border-radius: 8px !important;
}

button[kind="secondary"]:hover {
    background: #0d1a30 !important;
    border-color: #1a3060 !important;
    color: #6a9ad4 !important;
}

/* Expander */
[data-testid="stExpander"] {
    border: 1px solid #0a1830 !important;
    border-radius: 10px !important;
    background: #060c18 !important;
}

[data-testid="stExpanderToggleIcon"] { color: #2a4a78 !important; }

details summary {
    font-family: 'Syne', sans-serif !important;
    font-size: 0.82rem !important;
    color: #4a7ab5 !important;
}

/* Number input */
[data-testid="stNumberInput"] input {
    font-family: 'IBM Plex Mono', monospace !important;
    font-size: 0.9rem !important;
    background: #070e1e !important;
    border: 1px solid #0f2040 !important;
    color: #a0c8e8 !important;
    border-radius: 8px !important;
}

/* Dataframe */
[data-testid="stDataFrame"] {
    border: 1px solid #0a1830 !important;
    border-radius: 12px !important;
    overflow: hidden !important;
}

/* Selectbox */
[data-testid="stSelectbox"] > div > div {
    background: #070e1e !important;
    border: 1px solid #0f2040 !important;
    border-radius: 8px !important;
    color: #6a9ad4 !important;
    font-family: 'IBM Plex Mono', monospace !important;
    font-size: 0.82rem !important;
}

/* Plotly grafy – průhledné pozadí */
.js-plotly-plot .plotly .main-svg {
    background-color: transparent !important;
}

/* Přepínač období grafu (1M / 3M / 6M / 1Y) */
[data-testid="stRadio"] > div {
    gap: 6px !important;
    flex-wrap: wrap !important;
}
[data-testid="stRadio"] label {
    background: #070e1e !important;
    border: 1px solid #0f2040 !important;
    border-radius: 8px !important;
    padding: 4px 14px !important;
    font-family: 'IBM Plex Mono', monospace !important;
    font-size: 0.72rem !important;
    color: #2a5080 !important;
    transition: all 0.15s ease !important;
}
[data-testid="stRadio"] label:hover {
    border-color: #1a3a6a !important;
    color: #6a9ad4 !important;
}
[data-testid="stRadio"] label[data-checked="true"],
[data-testid="stRadio"] div[aria-checked="true"] label {
    border-color: #f59e0b !important;
    color: #fbbf24 !important;
    background: rgba(245, 158, 11, 0.08) !important;
}

/* Progress bar logistiky */
.stProgress > div > div > div > div {
    background: linear-gradient(90deg, #f59e0b, #3b82f6) !important;
}
.stProgress > div > div > div {
    background-color: #0a1525 !important;
    border-radius: 6px !important;
}

/* Date input */
[data-testid="stDateInput"] input {
    font-family: 'IBM Plex Mono', monospace !important;
    background: #070e1e !important;
    border: 1px solid #0f2040 !important;
    color: #a0c8e8 !important;
    border-radius: 8px !important;
}

/* Globální přepínač měny (USD / EUR) */
.currency-bar {
    background: linear-gradient(135deg, #070e1e 0%, #0a1525 100%);
    border: 1px solid #0f2040;
    border-radius: 14px;
    padding: 14px 20px;
    margin-bottom: 20px;
}
.currency-bar-label {
    font-family: 'Syne', sans-serif;
    font-size: 0.78rem;
    font-weight: 700;
    color: #3a6a9a;
    text-transform: uppercase;
    letter-spacing: 1px;
    margin-bottom: 8px;
    line-height: 1.4;
}
.currency-bar-hint {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.68rem;
    color: #1e3a60;
    line-height: 1.65;
    padding-top: 8px;
}
[data-testid="stSegmentedControl"] {
    background: #050d1a !important;
    border-radius: 10px !important;
    padding: 3px !important;
    border: 1px solid #0f2040 !important;
}

/* Metric widget přepis */
[data-testid="stMetric"] {
    background: transparent !important;
    padding: 0 !important;
}

[data-testid="stMetricLabel"] {
    font-family: 'Syne', sans-serif !important;
    font-size: 0.72rem !important;
    color: #2a4a78 !important;
}

[data-testid="stMetricValue"] {
    font-family: 'IBM Plex Mono', monospace !important;
    color: #a0c8e8 !important;
}

</style>
"""

st.markdown(CUSTOM_CSS, unsafe_allow_html=True)


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
    """Formátuje číslo na řetězec; při chybě vrátí 'N/A'."""
    if value is None:
        return "N/A"
    try:
        return f"{prefix}{float(value):,.{decimals}f}{suffix}"
    except (ValueError, TypeError):
        return "N/A"


def delta_chip(delta_val, suffix: str = "") -> str:
    """Vrátí HTML chip pro změnu hodnoty (▲ zelená / ▼ červená / — šedá)."""
    if delta_val is None:
        return '<span class="delta-chip delta-flat">— N/A</span>'
    try:
        d = float(delta_val)
        if d > 0:
            return f'<span class="delta-chip delta-up">▲ +{d:,.2f}{suffix}</span>'
        elif d < 0:
            return f'<span class="delta-chip delta-down">▼ {d:,.2f}{suffix}</span>'
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
) -> str:
    """Sestaví HTML pro metrickou kartu a vrátí jako řetězec."""
    delta_row = f'<div class="card-delta-row">{delta_chip(delta, delta_suffix)}</div>'
    extra_row = f'<div class="card-extra">{extra}</div>' if extra else ""
    size_cls = " card-value-sm" if value_size == "sm" else ""
    return f"""
    <div class="metric-card {card_class}">
        <div class="card-label">{label}</div>
        <div class="card-value{size_cls}">{value}</div>
        <div class="card-unit">{unit}</div>
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
                ),
                unsafe_allow_html=True,
            )
    else:
        st.markdown(
            error_card(label, card_class, "Data nedostupná · Westmetall"),
            unsafe_allow_html=True,
        )


def _render_steel_metric_card(steel_data: dict | None) -> None:
    """Metrická karta oceli (HRC) — Yahoo."""
    unit = metal_unit_label()
    ccy = get_display_currency()
    d_suffix = currency_delta_suffix()
    if steel_data:
        st_price = usd_to_display(steel_data["price"], ccy)
        st_delta = usd_to_display(steel_data.get("delta"), ccy)
        st.markdown(
            metric_card(
                "Ocel (HRC)",
                format_num(st_price, 0) if st_price is not None else "N/A",
                unit,
                delta=st_delta,
                delta_suffix=d_suffix if st_delta is not None else "",
                card_class="card-steel",
                extra=f'{steel_data.get("ticker", "HRC")} · Yahoo · armoured cables',
            ),
            unsafe_allow_html=True,
        )
    else:
        st.warning("Ocel (HRC): Yahoo Finance nevrátilo živou cenu.")
        st.markdown(
            error_card("Ocel (HRC)", "card-steel", "Data nedostupná"),
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

_STEEL_TICKERS = ("HRC=F", "STRE=F")


@st.cache_data(ttl=CACHE_TTL)
def fetch_steel_yfinance() -> dict | None:
    """Ocel (Hot Rolled Coil) — Yahoo HRC=F nebo STRE=F, cena v USD/t."""
    for ticker in _STEEL_TICKERS:
        try:
            hist = yf.Ticker(ticker).history(period="10d")
            hist = hist.dropna(subset=["Close"])
            if hist.empty:
                continue
            price_st = float(hist["Close"].iloc[-1])
            prev_st = float(hist["Close"].iloc[-2]) if len(hist) > 1 else price_st
            price_t = price_st * _ST_TON_FACTOR
            prev_t = prev_st * _ST_TON_FACTOR
            return {
                "price":      round(price_t, 2),
                "prev_price": round(prev_t, 2),
                "delta":      round(price_t - prev_t, 2),
                "delta_pct":  round((price_t - prev_t) / prev_t * 100, 2) if prev_t else 0,
                "unit":       "USD/t",
                "ticker":     ticker,
                "note":       "Hot Rolled Coil (CME)",
                "_source":    "Yahoo Finance",
                "_ts":        now_prague().strftime("%Y-%m-%d %H:%M"),
            }
        except Exception:
            continue
    return None


@st.cache_data(ttl=CACHE_TTL)
def _yf_history(ticker: str) -> pd.DataFrame | None:
    """Plná historie tickeru (1 rok) — cache nezávislá na přepínači období."""
    try:
        hist = yf.Ticker(ticker).history(period=_YF_HIST_PERIOD)
        hist = hist.dropna(subset=["Close"])
        if hist.empty:
            return None
        out = hist[["Close"]].reset_index()
        if "Date" not in out.columns and "Datetime" in out.columns:
            out = out.rename(columns={"Datetime": "Date"})
        return out
    except Exception:
        return None


def fetch_metal_history(ticker: str = "HG=F", period: str = "6mo") -> pd.DataFrame | None:
    """Historie tickeru oříznutá podle globálního období (period jen kvůli kompatibilitě API)."""
    return filter_history_by_period(_yf_history(ticker))


# ==============================================================================
# ─────────────────────────────────────────────────────────────────────────────
#  DATOVÉ FUNKCE – SHFE (Čínská burza přes Sina Finance)
# ─────────────────────────────────────────────────────────────────────────────
# ==============================================================================

_SHFE_TICKERS = {"copper": "nf_CU0", "aluminum": "nf_AL0"}


@st.cache_data(ttl=CACHE_TTL)
def fetch_shfe_sina(metal: str = "copper") -> dict | None:
    """
    Stahuje aktuální ceny z SHFE přes Sina Finance hq API.
    Formát odpovědi: var hq_str_nf_CU0="datum,čas,open,high,low,close,settle,...";
    Vrátí {price (CNY/t), open, settle, ticker} nebo None.
    """
    ticker_map = _SHFE_TICKERS
    ticker = ticker_map.get(metal, "nf_CU0")
    url    = f"http://hq.sinajs.cn/list={ticker}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        "Referer":    "http://finance.sina.com.cn/",
    }
    try:
        resp = requests.get(url, headers=headers, timeout=12)
        resp.encoding = "gbk"   # Sina Finance používá GBK
        match = re.search(r'"([^"]+)"', resp.text)
        if not match:
            return None
        parts = match.group(1).split(",")
        if len(parts) < 6:
            return None
        # Typická pozice 5 = close (aktuální cena), 7 = settle
        price   = _safe_float(parts[5])
        settle  = _safe_float(parts[6]) if len(parts) > 6 else None
        op      = _safe_float(parts[2]) if len(parts) > 2 else None
        if price and 5_000 < price < 1_000_000:   # rozumný rozsah CNY/t
            return {
                "price":  price,
                "open":   op,
                "settle": settle,
                "unit":   "CNY/t",
                "ticker": ticker,
            }
        return None
    except Exception:
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
    """Aktuální spot kurz / cena z yfinance (poslední close vs. předchozí den)."""
    try:
        hist = yf.Ticker(ticker).history(period="10d")
        hist = hist.dropna(subset=["Close"])
        if hist.empty:
            return None
        price = float(hist["Close"].iloc[-1])
        prev = float(hist["Close"].iloc[-2]) if len(hist) > 1 else price
        return {
            "price":     round(price, 6),
            "prev":      round(prev, 6),
            "delta":     round(price - prev, 6),
            "delta_pct": round((price - prev) / prev * 100, 3) if prev else 0,
        }
    except Exception:
        return None


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
    return f"{sym}{val:,.{decimals}f}"


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


def get_shfe_china_usd(metal_key: str) -> tuple[float | None, dict | None, float | None]:
    """
    Čínská strana spreadu — pouze SHFE (Sina) + přepočet CNY přes ČNB.
    Vrátí (USD/t, shfe dict, CNY/t).
    """
    shfe = fetch_shfe_sina(metal_key)
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
        return f"LME zásoby: {int(info['tons']):,} t"
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

_TICK_AXIS = dict(
    gridcolor="#070e1e",
    tickfont=dict(family="IBM Plex Mono, monospace", size=9, color="#1e3a60"),
    showgrid=True,
    zeroline=False,
    showline=False,
)

_HOVER_LABEL = dict(
    bgcolor="#070e1e",
    bordercolor="#0f2040",
    font=dict(family="IBM Plex Mono, monospace", size=11, color="#8ab0d4"),
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
) -> go.Figure | None:
    """
    Interaktivní čárový graf (plotly.graph_objects) s volitelnými dalšími řadami.
    extra_traces: [{"y": Series/array, "name": str, "color": str, "dash": "solid"|"dot"|...}]
    """
    if df is None or df.empty or y_column not in df.columns:
        return None

    x_data = df["Date"] if "Date" in df.columns else df.index
    fig = go.Figure()

    r, g, b = int(color[1:3], 16), int(color[3:5], 16), int(color[5:7], 16)
    fig.add_trace(go.Scatter(
        x=x_data,
        y=df[y_column],
        mode="lines",
        name=title.split("—")[0].strip() if "—" in title else "Cena",
        line=dict(color=color, width=2.2, shape="spline", smoothing=0.8),
        fill="tozeroy",
        fillcolor=f"rgba({r},{g},{b},0.08)",
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

    fig.update_layout(
        title=dict(text=title, font=dict(family="Syne, sans-serif", size=12, color="#3a6a9a"), y=0.97),
        height=height,
        margin=dict(l=10, r=10, t=42 if show_legend else 36, b=12),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        showlegend=show_legend,
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.08,
            xanchor="right",
            x=1,
            font=dict(family="IBM Plex Mono, monospace", size=9, color="#4a7ab5"),
            bgcolor="rgba(0,0,0,0)",
        ) if show_legend else None,
        xaxis=dict(**_TICK_AXIS, tickformat="%b %y"),
        yaxis=dict(**_TICK_AXIS, tickformat=",.2f"),
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
    Graf LME Cash (osa Y vlevo) + LME zásoby (osa Y vpravo) z westmetall historie.
    """
    if df is None or df.empty or "Close" not in df.columns:
        return None

    x_data = df["Date"]
    r, g, b = int(price_color[1:3], 16), int(price_color[3:5], 16), int(price_color[5:7], 16)
    fig = go.Figure()

    fig.add_trace(go.Scatter(
        x=x_data,
        y=df["Close"],
        mode="lines",
        name="LME Cash",
        yaxis="y",
        line=dict(color=price_color, width=2.2, shape="spline", smoothing=0.8),
        fill="tozeroy",
        fillcolor=f"rgba({r},{g},{b},0.08)",
        hovertemplate=(
            f"<b>%{{x|%d.%m.%Y}}</b><br>{y_price_label}: %{{y:,.2f}}<extra></extra>"
        ),
    ))

    has_stock = "Stock" in df.columns and df["Stock"].notna().any()
    if has_stock:
        fig.add_trace(go.Scatter(
            x=x_data,
            y=df["Stock"],
            mode="lines",
            name="LME zásoby",
            yaxis="y2",
            line=dict(color="#94a3b8", width=1.8, dash="dot"),
            hovertemplate="<b>%{x|%d.%m.%Y}</b><br>Zásoby: %{y:,.0f} t<extra></extra>",
        ))

    y2_axis = dict(
        title=dict(text="Zásoby (t)", font=dict(size=9, color="#64748b")),
        overlaying="y",
        side="right",
        showgrid=False,
        tickfont=dict(family="IBM Plex Mono, monospace", size=9, color="#64748b"),
        tickformat=",.0f",
    ) if has_stock else None

    fig.update_layout(
        title=dict(text=title, font=dict(family="Syne, sans-serif", size=12, color="#3a6a9a"), y=0.98),
        height=height,
        margin=dict(l=10, r=10, t=48, b=12),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        showlegend=True,
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.1,
            xanchor="right",
            x=1,
            font=dict(family="IBM Plex Mono, monospace", size=9, color="#4a7ab5"),
            bgcolor="rgba(0,0,0,0)",
        ),
        xaxis=dict(**_TICK_AXIS, tickformat="%b %y"),
        yaxis=dict(**_TICK_AXIS, tickformat=",.0f", title=dict(text=y_price_label, standoff=8)),
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
    fig = interactive_metal_dual_chart(
        plot,
        f"{chart_title} — {period_lbl} · Westmetall",
        color,
        y_unit,
    )
    if fig:
        _show_plotly(fig)
    else:
        st.warning("Chyba načítání dat z Westmetallu")
        st.markdown(
            '<div class="error-box">Chyba načítání dat z Westmetallu</div>',
            unsafe_allow_html=True,
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
        text=[f" {p:,.0f} {currency}/t" for p in prices],
        textposition="outside",
        textfont=dict(family="IBM Plex Mono, monospace", size=9.5, color="#3a6a9a"),
        hovertemplate=f"<b>%{{y}}</b><br>%{{x:,.0f}} {currency}/t<extra></extra>",
    ))
    fig.update_layout(
        title=dict(text=title, font=dict(family="Syne, sans-serif", size=12, color="#3a6a9a")),
        height=220,
        margin=dict(l=10, r=10, t=36, b=12),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        showlegend=False,
        xaxis=dict(
            gridcolor="#060d1a",
            tickfont=dict(family="IBM Plex Mono, monospace", size=9, color="#1e3a60"),
            tickformat=",.0f",
            showgrid=True,
            zeroline=False,
        ),
        yaxis=dict(
            tickfont=dict(family="Syne, sans-serif", size=10, color="#4a7ab5"),
            showgrid=False,
        ),
        bargap=0.35,
        hoverlabel=dict(
            bgcolor="#070e1e",
            bordercolor="#0f2040",
            font=dict(family="IBM Plex Mono, monospace", size=11, color="#8ab0d4"),
        ),
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
                    <span>⚡</span> Kabelářský Nákupní Dashboard
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
            'font-size:0.7rem;color:#1a3050;">'
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
            f"EUR/USD (Yahoo): <strong style='color:#4a7ab5;'>{eurusd:.4f}</strong>"
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
    """Sekce 1 – LME & SHFE ceny kovů, spreads, historické grafy."""

    wm_data = fetch_westmetall()
    steel_data = fetch_steel_yfinance()
    period = get_chart_period()
    period_lbl = get_chart_period_label()

    has_cu = wm_data and "copper" in wm_data
    has_al = wm_data and "aluminum" in wm_data

    section_header(
        "🔩", "Metaly — LME, Ocel & SHFE",
        badge_html(has_cu and has_al, "westmetall.com LME Cash"),
        badge_html(steel_data is not None, "Yahoo HRC"),
    )

    if not wm_data:
        st.warning("Westmetall: LME data se nepodařilo stáhnout — ceny mědi a hliníku nejsou k dispozici.")

    ccy = get_display_currency()
    cols = st.columns(3)
    for (mk, mn, cls, stock_key), col in zip(_LME_METAL_CARDS, cols[:2]):
        with col:
            _render_lme_metal_card(mk, mn, cls, stock_key, wm_data)
    with cols[2]:
        _render_steel_metric_card(steel_data)

    st.markdown("<br>", unsafe_allow_html=True)

    # ── Historické grafy — měď & hliník (Westmetall), ocel (Yahoo) ────────────
    st.markdown(
        "<div style='font-family:Syne,sans-serif;font-size:0.75rem;font-weight:700;"
        "color:#2a4a78;text-transform:uppercase;letter-spacing:1px;margin-bottom:8px;'>"
        f"Historické grafy — Měď & Hliník (Westmetall, {period_lbl}) · "
        f"Ocel (Yahoo, {ccy}/t)</div>",
        unsafe_allow_html=True,
    )
    col_cu, col_al, col_st = st.columns(3)
    y_unit = f"{ccy}/t"
    steel_ticker = (steel_data or {}).get("ticker", "HRC=F")

    with col_cu:
        _render_wm_metal_history_chart("copper", "Měď (Cu)", "#f97316")

    with col_al:
        _render_wm_metal_history_chart("aluminum", "Hliník (Al)", "#10b981")

    with col_st:
        st_hist = fetch_metal_history(steel_ticker, period) if steel_data else None
        if st_hist is not None:
            st_plot = st_hist.copy()
            st_plot["Close"] = st_plot["Close"] * _ST_TON_FACTOR
            st_plot = apply_currency_to_df(st_plot)
            fig_st = interactive_line_chart(
                st_plot,
                f"Ocel (HRC) — {period_lbl}",
                "#64748b",
                y_unit,
            )
            if fig_st:
                _show_plotly(fig_st)
        else:
            st.markdown('<div class="error-box">Graf oceli momentálně nedostupný</div>', unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # ── SHFE spread panel ─────────────────────────────────────────────────────
    col_spread_full, _ = st.columns([1, 2])
    with col_spread_full:
        _render_shfe_spreads(wm_data)

    # ── Srovnávací bar chart (měď, hliník, ocel) ──────────────────────────────
    bar_data: dict = {}
    for mk in ["copper", "aluminum"]:
        p_usd, _, _ = resolve_metal_price(mk, wm_data)
        p_disp = usd_to_display(p_usd, ccy)
        if p_disp is not None:
            bar_data[mk] = {"price": p_disp}
    if steel_data:
        p_st = usd_to_display(steel_data["price"], ccy)
        if p_st is not None:
            bar_data["steel"] = {"price": p_st}
    if bar_data:
        fig_bar = bar_metals(bar_data, currency=ccy)
        if fig_bar:
            st.markdown("<br>", unsafe_allow_html=True)
            _show_plotly(fig_bar, toolbar=False)

    if wm_data and wm_data.get("_source") == "westmetall.com":
        st.markdown(
            f'<div class="info-box">'
            f'📦 <strong>Westmetall</strong> LME Cash &amp; skladové zásoby · '
            f'Načteno: <strong>{wm_data.get("_ts", "N/A")}</strong></div>',
            unsafe_allow_html=True,
        )

    st.markdown('<div class="section-divider"></div>', unsafe_allow_html=True)


def _render_shfe_spread_item(metal_key: str, metal_name: str, wm_data: dict | None) -> None:
    """Jedna spread karta SHFE vs LME."""
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
                f'<div class="spread-card"><div class="spread-label">{metal_name}: SHFE vs LME</div>'
                f'<div class="error-box" style="margin-top:6px;">N/A — chybí kurz EUR/USD</div></div>',
                unsafe_allow_html=True,
            )
            return
        s_color = "#10b981" if spread_usd >= 0 else "#ef4444"
        s_sign = "+" if spread_usd >= 0 else ""
        st.markdown(
            f"<div style='margin-bottom:6px;'>{badge_html(True, 'Sina / SHFE')}</div>"
            f'<div class="spread-card"><div class="spread-label">{metal_name}: SHFE vs LME</div>'
            f'<div class="spread-value" style="color:{s_color};">{s_sign}{spread_disp:,.0f} {ccy}/t</div>'
            f'<div class="spread-details">SHFE: {cny_price:,.0f} CNY/t (≈ {china_disp:,.0f} {ccy}/t)<br>'
            f"LME Cash (Westmetall): {lme_disp:,.0f} {ccy}/t</div></div>",
            unsafe_allow_html=True,
        )
        return

    missing = []
    if lme_usd is None:
        missing.append("LME Cash (Westmetall)")
    if china_usd is None:
        missing.append("SHFE (Sina) nebo kurz CNY (ČNB)")
    st.markdown(
        f'<div class="spread-card"><div class="spread-label">{metal_name}: SHFE vs LME</div>'
        f'<div class="error-box" style="margin-top:6px;">Data nedostupná — {", ".join(missing)}</div></div>',
        unsafe_allow_html=True,
    )


def _render_shfe_spreads(wm_data: dict | None) -> None:
    """SHFE vs LME spread — pouze živá data (Sina + ČNB + Westmetall)."""
    ccy = get_display_currency()
    st.markdown(
        f"<div style='margin-bottom:10px;'>"
        f"<span style='font-family:Syne,sans-serif;font-size:0.7rem;font-weight:700;"
        f"color:#2a4a78;text-transform:uppercase;letter-spacing:1px;'>"
        f"SHFE vs LME Spread ({ccy}/t)</span></div>",
        unsafe_allow_html=True,
    )
    if not get_usd_per_cny():
        st.warning(
            "Spread: chybí kurz CNY z ČNB — přepočet SHFE (CNY/t) na USD/EUR nelze spočítat."
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
                fig = interactive_line_chart(hist, f"{pair} — {period_lbl}{sub}", color, unit)
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
        fig_ue = interactive_line_chart(hist_ue, f"USD/EUR — {period_lbl}", "#22c55e", "EUR")
        if fig_ue:
            _show_plotly(fig_ue)

    # ── Kalkulátor přepočtu (ČNB kurzy) ───────────────────────────────────────
    with st.expander("🧮  Kalkulátor přepočtu – nákupní ekvivalenty", expanded=False):
        usd_rate = (cnb or {}).get("USD", {}).get("rate", 0)
        eur_rate = (cnb or {}).get("EUR", {}).get("rate", 0)
        cny_rate = (cnb or {}).get("CNY", {}).get("rate", 0)

        c_in, c_out1, c_out2, c_out3 = st.columns([2, 1, 1, 1])
        with c_in:
            amount = st.number_input(
                "Částka k přepočtu (USD)",
                min_value=0.0, value=50_000.0, step=1_000.0,
                help="Zadejte částku v USD pro přepočet (kurzy z ČNB)",
            )

        for col, label, val, prefix in [
            (c_out1, "USD → CZK", amount * usd_rate if usd_rate else None, "Kč"),
            (c_out2, "USD → EUR", amount * usd_rate / eur_rate if (usd_rate and eur_rate) else None, "EUR"),
            (c_out3, "USD → CNY", amount * usd_rate / cny_rate if (usd_rate and cny_rate) else None, "CNY"),
        ]:
            with col:
                if val:
                    st.markdown(f"""
                    <div class="calc-result">
                        <div class="calc-result-label">{label}</div>
                        <div class="calc-result-value">{val:,.2f} {prefix}</div>
                    </div>
                    """, unsafe_allow_html=True)

        wm_calc = fetch_westmetall()
        cu_price, _, _ = resolve_metal_price("copper", wm_calc)
        if cu_price and cu_price > 0:
            tonnes = amount / cu_price
            st.markdown(f"""
            <div class="info-box" style="margin-top:8px;">
                💡 Za <strong>{amount:,.0f} USD</strong> lze při LME Cash (Westmetall) koupit
                přibližně <strong>{tonnes:.3f} tun</strong> (≈ {tonnes*1000:.1f} kg) mědi.
            </div>
            """, unsafe_allow_html=True)
        elif not cu_price:
            st.warning("Kalkulátor mědi: cena z Westmetall není k dispozici.")

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
                    metric_card(label, f"~{plastics[key]['price']:,.0f}", "USD/t (model)",
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
        "color:#2a4a78;text-transform:uppercase;letter-spacing:1px;margin-bottom:8px;'>"
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
                f'<td style="color:#14b8a6;text-align:right;">~{plastics[k]["price"]:,.0f}</td></tr>'
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
                            font-size:0.65rem;color:#1e3a60;line-height:1.7;">
                    Základ (Brent):<br>
                    <strong style="color:#2a5080;">${plastics['_brent']:.2f}/bbl</strong><br><br>
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
        f"color:#2a5080;margin-bottom:6px;'>"
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
                    "Hodnota":   f"{price_disp:,.0f} {ccy}/t",
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
            "Hodnota":   f"{p_disp:,.0f} {ccy}/t" if p_disp else "N/A",
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
    render_header()
    render_global_controls()
    render_metals()
    render_fx()
    render_oil_plastics()
    render_logistics()
    render_summary_table()
    render_footer()


if __name__ == "__main__":
    main()
