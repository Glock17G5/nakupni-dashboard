"""
Henry — Telegram souhrn (ne briefing do dashboardu, jen odkaz).

Běží pořád na GitHub Actions (long poll). Na zprávu odpoví během sekund.
Ranní souhrn vždy v 7:00 (Po–Pá, Praha): LME Cash + CCMN vs LME.
Polední report 11:00–13:00 jen při silných dnešních titulcích.
LME flash 14:00–16:00, až je dnešní Official a |den| ≥ práh.

Hlas jen u ranního souhrnu, extra reportů a tlačítka Souhrn.
Zprávy: CZ + svět (Google News), titulky do češtiny.

Příkazy: /henry, update, měď, hliník, zprávy, doprava, kurzy, hlas, /help
"""

from __future__ import annotations

import asyncio
import os
import re
import signal
import sys
import tempfile
import time
import traceback
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime
from urllib.parse import quote
from zoneinfo import ZoneInfo

import pandas as pd
import requests
from bs4 import BeautifulSoup

TZ = ZoneInfo("Europe/Prague")
UA = {
    "User-Agent": "pbcable-henry/1.0 (internal briefing)",
    "Accept-Language": "cs,en;q=0.8",
}
WM_HEADERS = {
    **UA,
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Referer": "https://www.westmetall.com/",
}
WM_URLS = {
    "copper": "https://www.westmetall.com/en/markdaten.php?action=table&field=LME_Cu_cash",
    "aluminum": "https://www.westmetall.com/en/markdaten.php?action=table&field=LME_Al_cash",
}
WM_RANGE = {"copper": (4_000, 25_000), "aluminum": (1_500, 8_000)}
WM_MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
}
WEEKDAY_CS = (
    "pondělí", "úterý", "středa", "čtvrtek", "pátek", "sobota", "neděle",
)
WD_CS = {"po": 0, "út": 1, "ut": 1, "st": 2, "čt": 3, "ct": 3, "pá": 4, "pa": 4, "so": 5, "ne": 6}
NEWS_DAYS = 7
NEWS_LIMIT = 12
LIST_QUERIES = ("měď", "hliník", "kontejner", "Turecko", "Čína", "clo", "energetika")
RSS_COLS = ("ptKomodity", "wzMeny", "wzMakro", "ptEkonomika", "ptPolitika")
GNEWS_CZ = (
    "site:businessinfo.cz when:7d (energetika OR clo OR Čína OR doprava OR Turecko OR sankce)",
    "when:7d (hliník OR aluminium) (LME OR cena OR zásob)",
)
GNEWS_WORLD = (
    "when:7d (copper OR aluminium OR aluminum) (LME OR SHFE OR smelter OR concentrate OR stocks)",
    "when:7d (China OR Turkey) (copper OR aluminium OR aluminum) (tariff OR export OR quota OR CBAM)",
    "when:7d (Red Sea OR Hormuz OR Suez OR \"container freight\" OR SCFI) (shipping OR port OR houthi)",
)
CAT_ORDER = {"metal": 0, "freight": 1, "energy": 2, "geo": 3, "macro": 4}
CAT_LABEL = {
    "metal": "• Kov — měď / hliník",
    "freight": "• Doprava / trasy",
    "energy": "• Energetika",
    "geo": "• Politika / Čína / Turecko / cla",
    "macro": "• Makro / FX",
}
CAT_QUOTA = {"metal": 4, "freight": 2, "energy": 2, "geo": 2, "macro": 2}
CNB_URL = (
    "https://www.cnb.cz/cs/financni-trhy/devizovy-trh/"
    "kurzy-devizoveho-trhu/kurzy-devizoveho-trhu/denni_kurz.txt"
)
TTS_PRESETS = (
    {
        "id": "antonin",
        "voice": "cs-CZ-AntoninNeural",
        "rate": "+0%",
        "pitch": "+0Hz",
        "label": "Antonín",
    },
    {
        "id": "klidny",
        "voice": "cs-CZ-AntoninNeural",
        "rate": "-18%",
        "pitch": "-8Hz",
        "label": "Antonín klidný",
    },
    {
        "id": "hluboky",
        "voice": "cs-CZ-AntoninNeural",
        "rate": "-12%",
        "pitch": "-20Hz",
        "label": "Antonín hluboký",
    },
    {
        "id": "vlasta",
        "voice": "cs-CZ-VlastaNeural",
        "rate": "+0%",
        "pitch": "+0Hz",
        "label": "Vlasta (žena)",
    },
)
TTS_BY_ID = {p["id"]: p for p in TTS_PRESETS}
VOICE_PATH = ".henry_voice"
KB_MARK = ".henry_kb_inline"
TR_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json,text/plain,*/*",
}
METAL_RE = re.compile(
    r"měď|mědi|měděn|\bcopper\b|hliník|hliníku|hliniku|aluminium|aluminum|"
    r"\blme\b|-medi-|_medi_|/medi-|nedostatek fyzick|\bbhp\b|zambi",
    re.I,
)
FREIGHT_RE = re.compile(
    r"námořn|kontejnerov|přeprav[ay].{0,24}(kontej|čín|china|tureck)|"
    r"freight|\bteu\b|baltic|suez|hormuz|rudé moře|red sea|houthi|"
    r"lodní doprav|přístav|fracht|maersk|cma cgm|logistik|"
    r"shanghai.{0,12}(index|spot)|spot rate",
    re.I,
)
ENERGY_RE = re.compile(
    r"energetik|elektřin|zemní plyn|\bLNG\b|\bMWh\b|jád(ro|ern)|uhlí|"
    r"fotovolta|větrn|obnoviteln|\bČEPS\b|\bETS\b|emisní povol|vodík|"
    r"cena elektř|ceny energi",
    re.I,
)
GEO_RE = re.compile(
    r"čín|cína|\bchina\b|tureck|\bturkey\b|yuan|\bcny\b|"
    r"\bcla\b|\bclo\b|tarif|sankc|embarg|\bcbam\b|írán|\biran\b|"
    r"geopolit|trump| clo | clo,|dovoz|vývoz|export",
    re.I,
)
MACRO_RE = re.compile(
    r"\bfed\b|sazb|\bbrent\b|\bwti\b|\bropa\b|eurodolar|eur/usd|eur/czk|"
    r"\becb\b|\bčnb\b|inflac|dolar|dluhopis",
    re.I,
)
NOISE_RE = re.compile(
    r"bitcoin|nvidia|robinhood|hlídačkovn|průměrn[áa] mzda|kakao|pšenice|"
    r"nasdaq|marriott|airbnb|coinbase|hypoték|teplárn|"
    r"plešat|ozempic|cistern|mapa globálních oborových|"
    r"ceny a grafy|vývoj ceny mědi|vývoj ceny hlin",
    re.I,
)
GOLD_RE = re.compile(r"\bzlato\b|\bgold\b", re.I)
# Polední alert: titulek, který typicky hýbe nákupem kabelů (kov, clo, trasa).
CRITICAL_NEWS_RE = re.compile(
    r"hormuz|suez|rudé moře|red sea|houthi|blokád|"
    r"force majeure|sankc|embarg|\bcbam\b|"
    r"zákaz vývoz|exportní zákaz|export ban|"
    r"nedostatek fyzick|\bsqueeze\b|výpadek hut",
    re.I,
)
HIGH_NEWS_RE = re.compile(
    r"\bcla\b|\bclo\b|tarif|celní|"
    r"zásob.{0,16}lme|lme.{0,16}zásob|"
    r"výpadek|stávk|smelter|"
    r"kontejner|fracht|námořn|"
    r"čín.{0,24}(clo|cla|sankc|export|omezen)|"
    r"tureck.{0,24}(clo|celní|vývoz|sankc)",
    re.I,
)
PRICE_SHOCK_PCT = float(os.environ.get("HENRY_SHOCK_PCT") or "1.5")
# 11–13: default 5 = nestačí jeden slabý titulek (high=2 + metal=1).
MIDDAY_IMPACT_MIN = int(os.environ.get("HENRY_IMPACT_MIN") or "5")
DASHBOARD_URL = (
    os.environ.get("HENRY_DASHBOARD_URL") or "https://pbcable.streamlit.app/"
).strip()
OFFSET_PATH = ".henry_tg_offset"
DAILY_MARK = ".henry_daily_sent"
MIDDAY_MARK = ".henry_midday_sent"
LME_MARK = ".henry_lme_sent"
MORNING_URLS = ".henry_morning_urls"
TG_LIMIT = 3500
HELP_TEXT = (
    "Henry. Klikněte na tlačítka pod touhle zprávou (ne na text v bublině).\n"
    "Nebo vlevo lomítko /.\n"
    "\n"
    "Měď — LME + Čína CCMN vs LME + zprávy o mědi za 7 dní\n"
    "Hliník — to samé pro hliník\n"
    "Zprávy — CZ i svět, titulky česky (měď, hliník, doprava, energetika, politika)\n"
    "Doprava — kontejnery, trasy, cla, energie\n"
    "Kurzy — ČNB EUR, USD, CNY, TRY\n"
    "Souhrn — všechno naráz (s hlasem)\n"
    "Hlas — další hlas (Antonín, klidný, hluboký, Vlasta)\n"
    "\n"
    "Ranní souhrn v 7:00 (Po–Pá) a víkendový v 8:00 jsou s hlasem, stejně jako Souhrn.\n"
    "O víkendu LME neobchoduje — číslo zůstane páteční official, zprávy jedou dál.\n"
    "Po–Pá mezi 11. a 13. hodinou jen při velké zprávě. Dnešní LME Cash až po 14. hodině.\n"
    f"Dashboard: {DASHBOARD_URL}\n"
    "Kolegy přidejte do této skupiny."
)
BOT_COMMANDS = [
    {"command": "henry", "description": "Celý souhrn"},
    {"command": "med", "description": "Měď — cena a zprávy"},
    {"command": "hlinik", "description": "Hliník — cena a zprávy"},
    {"command": "zpravy", "description": "Zprávy za 7 dní"},
    {"command": "doprava", "description": "Doprava, Čína, Turecko"},
    {"command": "kurzy", "description": "ČNB EUR USD CNY TRY"},
    {"command": "hlas", "description": "Další hlas (klidný / hluboký / žena)"},
    {"command": "help", "description": "Tlačítka a nápověda"},
]
KINDS = {"help", "fx", "copper", "aluminum", "freight", "news", "full", "voice"}
CU_NEWS_RE = re.compile(r"měď|mědi|měděn|\bcopper\b|-medi-|_medi_|/medi-", re.I)
AL_NEWS_RE = re.compile(r"hliník|hliníku|hliniku|aluminium|aluminum", re.I)
INLINE_KEYBOARD = {
    "inline_keyboard": [
        [
            {"text": "Měď", "callback_data": "copper"},
            {"text": "Hliník", "callback_data": "aluminum"},
            {"text": "Zprávy", "callback_data": "news"},
        ],
        [
            {"text": "Doprava", "callback_data": "freight"},
            {"text": "Kurzy", "callback_data": "fx"},
            {"text": "Souhrn", "callback_data": "full"},
        ],
        [
            {"text": "Nápověda", "callback_data": "help"},
            {"text": "Hlas", "callback_data": "voice"},
        ],
    ],
}

_lme_cache: dict[str, pd.DataFrame | None] = {}
_news_cache: list[dict] | None = None
_news_pool: list[dict] = []
_news_cache_at = 0.0
NEWS_CACHE_SEC = 12 * 60
_ccmn_cache: dict[str, tuple[float, float | None]] = {}
_cnb_cache: dict | None = None
_cnb_cache_at = 0.0
CCMN_CACHE_SEC = 12 * 60
CNB_CACHE_SEC = 30 * 60
CCMN_UA = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
}
_tr_cache: dict[str, str] = {}


def _voice_preset() -> dict:
    key = "antonin"
    try:
        with open(VOICE_PATH, encoding="utf-8") as f:
            raw = (f.read() or "").strip().lower()
        if raw in ("muz", "antonin"):
            key = "antonin"
        elif raw in ("klidny", "klidný"):
            key = "klidny"
        elif raw in ("hluboky", "hluboký"):
            key = "hluboky"
        elif raw in ("zena", "vlasta"):
            key = "vlasta"
        elif raw in TTS_BY_ID:
            key = raw
    except Exception:
        env = (os.environ.get("HENRY_VOICE") or "").strip().lower()
        if "vlasta" in env or env == "zena":
            key = "vlasta"
        elif "hlubok" in env:
            key = "hluboky"
        elif "klidn" in env:
            key = "klidny"
    return TTS_BY_ID.get(key) or TTS_PRESETS[0]


def _write_voice(key: str) -> None:
    with open(VOICE_PATH, "w", encoding="utf-8") as f:
        f.write(key)


def _toggle_voice() -> dict:
    cur = _voice_preset()["id"]
    ids = [p["id"] for p in TTS_PRESETS]
    nxt = ids[(ids.index(cur) + 1) % len(ids)] if cur in ids else ids[0]
    _write_voice(nxt)
    return TTS_BY_ID[nxt]


def _looks_czech(text: str) -> bool:
    return bool(re.search(r"[áčďéěíňóřšťúůýžÁČĎÉĚÍŇÓŘŠŤÚŮÝŽ]", text or ""))


def _gtx_translate(text: str) -> str | None:
    r = requests.get(
        "https://translate.googleapis.com/translate_a/single",
        params={"client": "gtx", "sl": "auto", "tl": "cs", "dt": "t", "q": text[:500]},
        headers=TR_HEADERS,
        timeout=12,
    )
    r.raise_for_status()
    bits = []
    for part in (r.json() or [None])[0] or []:
        if part and part[0]:
            bits.append(part[0])
    out = "".join(bits).strip()
    return out or None


def _lingva_translate(text: str) -> str | None:
    for base in (
        "https://lingva.ml/api/v1/auto/cs/",
        "https://lingva.garudalinux.org/api/v1/auto/cs/",
    ):
        try:
            r = requests.get(
                base + quote(text[:500], safe=""),
                headers=TR_HEADERS,
                timeout=12,
            )
            r.raise_for_status()
            out = str((r.json() or {}).get("translation") or "").strip()
            if out:
                return out
        except Exception:
            continue
    return None


def _mymemory_translate(text: str) -> str | None:
    r = requests.get(
        "https://api.mymemory.translated.net/get",
        params={"q": text[:500], "langpair": "en|cs"},
        headers=TR_HEADERS,
        timeout=12,
    )
    r.raise_for_status()
    out = str(((r.json() or {}).get("responseData") or {}).get("translatedText") or "").strip()
    if not out or "MYMEMORY" in out.upper():
        return None
    return out


def to_czech(text: str) -> str:
    """Cizí titulek do češtiny. gtx z GitHub Actions často spadne, proto zálohy."""
    raw = (text or "").strip()
    if not raw or _looks_czech(raw):
        return raw
    hit = _tr_cache.get(raw)
    if hit:
        return hit
    out = raw
    for fn in (_gtx_translate, _lingva_translate, _mymemory_translate):
        try:
            cand = fn(raw)
        except Exception as e:
            print(f"překlad {fn.__name__}: {e}")
            continue
        if cand and cand.strip() and cand.strip().lower() != raw.lower():
            out = cand.strip()
            break
    if out == raw:
        print(f"překlad selhal: {raw[:80]}")
    _tr_cache[raw] = out
    return out


def _now() -> datetime:
    return datetime.now(TZ)


def _fmt(n, decimals=0) -> str:
    try:
        return f"{float(n):,.{decimals}f}".replace(",", " ")
    except (TypeError, ValueError):
        return "N/A"


def _get(url: str, *, headers=None, timeout=25) -> requests.Response | None:
    try:
        r = requests.get(url, headers=headers or UA, timeout=timeout)
        r.raise_for_status()
        if not r.encoding or r.encoding.lower() in ("iso-8859-1", "ascii"):
            r.encoding = "windows-1250"
        return r
    except Exception as e:
        print(f"GET {url[:80]}: {e}")
        return None


def _parse_price(text: str) -> float | None:
    if not text or not re.search(r"\d", text):
        return None
    raw = re.sub(r"[^\d.,]", "", text.strip())
    if "," in raw and "." in raw:
        raw = raw.replace(",", "")
    elif "," in raw:
        parts = raw.split(",")
        if len(parts) == 2 and len(parts[1]) == 3 and not parts[1].endswith("00"):
            raw = parts[0] + parts[1]
        elif len(parts) == 2 and len(parts[1]) <= 2:
            raw = parts[0] + "." + parts[1]
        else:
            raw = raw.replace(",", "")
    try:
        return float(raw)
    except ValueError:
        return None


def _parse_wm_date(text: str) -> datetime | None:
    text = text.strip()
    m = re.match(r"(\d{1,2})\.\s*([A-Za-z]+)\s*(\d{4})", text)
    if m:
        month = WM_MONTHS.get(m.group(2).lower())
        if month:
            try:
                return datetime(int(m.group(3)), month, int(m.group(1)))
            except ValueError:
                return None
    for fmt in ("%d.%m.%Y", "%d.%m.%y"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def lme(metal: str) -> pd.DataFrame | None:
    if metal not in _lme_cache:
        print(f"Westmetall {metal}…")
        _lme_cache[metal] = fetch_lme_history(metal)
    return _lme_cache[metal]


def fetch_lme_history(metal: str) -> pd.DataFrame | None:
    lo, hi = WM_RANGE[metal]
    r = _get(WM_URLS[metal], headers=WM_HEADERS)
    if r is None:
        return None
    soup = BeautifulSoup(r.text, "lxml")
    rows = []
    for table in soup.find_all("table"):
        for row in table.find_all("tr"):
            cells = row.find_all(["td", "th"])
            if len(cells) < 2:
                continue
            dt = _parse_wm_date(cells[0].get_text(strip=True))
            if dt is None:
                continue
            price = _parse_price(cells[1].get_text(strip=True))
            if price is None or not (lo <= price <= hi):
                continue
            rows.append({"Date": dt, "Close": price})
    if not rows:
        return None
    df = pd.DataFrame(rows).drop_duplicates("Date").sort_values("Date")
    return df.reset_index(drop=True)


def rsi14(df: pd.DataFrame) -> float | None:
    prices = pd.to_numeric(df["Close"], errors="coerce").dropna()
    if len(prices) < 15:
        return None
    delta = prices.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / 14, min_periods=14, adjust=False).mean()
    loss = (-delta).clip(lower=0).ewm(alpha=1 / 14, min_periods=14, adjust=False).mean()
    rs = gain / loss.replace(0, pd.NA)
    rsi = 100 - (100 / (1 + rs))
    last = rsi.iloc[-1]
    return None if pd.isna(last) else float(last)


def rsi_words(rsi: float) -> str:
    if rsi < 30:
        return "přeprodáno"
    if rsi > 70:
        return "překoupeno"
    return "neutrální"


def sma_last(df: pd.DataFrame, window: int) -> float | None:
    s = pd.to_numeric(df["Close"], errors="coerce").dropna()
    if len(s) < window:
        return None
    return float(s.rolling(window).mean().iloc[-1])


def week_pct(df: pd.DataFrame) -> float | None:
    s = pd.to_numeric(df["Close"], errors="coerce").dropna()
    if len(s) < 6:
        return None
    a, b = float(s.iloc[-6]), float(s.iloc[-1])
    if a == 0:
        return None
    return (b / a - 1.0) * 100.0


def day_pct(df: pd.DataFrame | None) -> float | None:
    if df is None or df.empty:
        return None
    s = pd.to_numeric(df["Close"], errors="coerce").dropna()
    if len(s) < 2:
        return None
    a, b = float(s.iloc[-2]), float(s.iloc[-1])
    if a == 0:
        return None
    return (b / a - 1.0) * 100.0


def lme_asof(df: pd.DataFrame | None):
    if df is None or df.empty or "Date" not in df.columns:
        return None
    return pd.to_datetime(df["Date"].iloc[-1]).date()


def lme_is_today(df: pd.DataFrame | None) -> bool:
    d = lme_asof(df)
    return d is not None and d == _naive(_now()).date()


def outlook(df: pd.DataFrame, horizon: int = 21) -> tuple[float, str] | None:
    """Lehký ensemble: OLS 45 dní + tah k SMA50. Ne věštba."""
    s = pd.to_numeric(df["Close"], errors="coerce").dropna()
    if len(s) < 46:
        return None
    y = s.iloc[-45:].reset_index(drop=True).astype(float)
    x = pd.Series(range(len(y)), dtype=float)
    xd = x - x.mean()
    den = float((xd ** 2).sum())
    if den == 0:
        return None
    slope = float((xd * (y - y.mean())).sum()) / den
    last = float(s.iloc[-1])
    ols = last + slope * horizon
    sma50 = float(s.rolling(50, min_periods=20).mean().iloc[-1])
    mr = sma50 + (last - sma50) * (0.5 ** (horizon / 20.0))
    ens = (ols + mr) / 2.0
    pct = (ens / last - 1.0) * 100.0
    if pct > 0.5:
        direction = "růst"
    elif pct < -0.5:
        direction = "pokles"
    else:
        direction = "stagnaci"
    return pct, direction


CCMN_RANGE = {"copper": (30_000, 180_000), "aluminum": (8_000, 50_000)}


def _ccmn_price_from_text(text: str, metal: str) -> float | None:
    """První číslo v rozumném CNY/t — ne cena + denní změna dohromady."""
    lo, hi = CCMN_RANGE[metal]
    for m in re.finditer(r"\d{1,3}(?:,\d{3})+(?:\.\d+)?", text):
        val = float(m.group(0).replace(",", ""))
        if lo <= val <= hi:
            return val
    for m in re.finditer(r"\d{1,3}(?:\s\d{3})+(?:\.\d+)?", text):
        val = float(re.sub(r"\s+", "", m.group(0)))
        if lo <= val <= hi:
            return val
    for m in re.finditer(r"\d{4,6}(?:\.\d+)?", text):
        val = float(m.group(0))
        if lo <= val <= hi:
            return val
    return None


def _scrape_ccmn_url(url: str, target: str, metal: str) -> float | None:
    """Stejný scrape jako data_robot.py — Changjiang / Shanghai, CNY/t."""
    try:
        res = requests.get(url, headers=CCMN_UA, timeout=15)
        res.encoding = "utf-8"
        soup = BeautifulSoup(res.text, "lxml")
    except Exception as e:
        print(f"CCMN {url[:60]}: {e}")
        return None
    cell = soup.find(
        lambda tag: tag.name in ["td", "a", "span"] and tag.get_text(strip=True) == target
    )
    if cell:
        parent_tr = cell.find_parent("tr")
        if parent_tr:
            cols = parent_tr.find_all("td")
            if len(cols) >= 3:
                price = _ccmn_price_from_text(cols[2].get_text(" ", strip=True), metal)
                if price:
                    return price
    picked = None
    for block in soup.select("div.content1-text-div"):
        right = block.find("span", class_="right")
        if not right or right.get_text(strip=True) != target:
            continue
        region_el = block.find("span", class_="left")
        region = region_el.get_text(strip=True) if region_el else ""
        span = block.select_one("span.up_down_span")
        if not span:
            continue
        price = _ccmn_price_from_text(span.get_text(), metal)
        if not price:
            continue
        if "长江综合" in region:
            return price
        if picked is None or "上海地区" in region:
            picked = price
    return picked


def fetch_ccmn_cny(metal: str) -> float | None:
    hit = _ccmn_cache.get(metal)
    if hit and (time.time() - hit[0]) < CCMN_CACHE_SEC:
        return hit[1]
    target = "1#铜" if metal == "copper" else "A00铝"
    fallback = "https://copper.ccmn.cn/" if metal == "copper" else "https://alu.ccmn.cn/"
    price = None
    for url in ("https://www.ccmn.cn/", fallback):
        price = _scrape_ccmn_url(url, target, metal)
        if price:
            break
    _ccmn_cache[metal] = (time.time(), price)
    return price


def fetch_cnb_rates() -> dict | None:
    global _cnb_cache, _cnb_cache_at
    if _cnb_cache is not None and (time.time() - _cnb_cache_at) < CNB_CACHE_SEC:
        return _cnb_cache
    r = _get(CNB_URL, timeout=20)
    if r is None:
        return _cnb_cache
    lines = r.text.strip().splitlines()
    if len(lines) < 3:
        return _cnb_cache
    out: dict = {"_date": lines[0].split("#")[0].strip()}
    for line in lines[2:]:
        parts = line.strip().split("|")
        if len(parts) != 5:
            continue
        code = parts[3].strip().upper()
        try:
            amount = int(parts[2])
            rate = float(parts[4].replace(",", ".")) / amount
        except (ValueError, ZeroDivisionError):
            continue
        out[code] = rate
    if len(out) < 3:
        return _cnb_cache
    _cnb_cache = out
    _cnb_cache_at = time.time()
    return out


def usd_per_cny() -> float | None:
    """USD za 1 CNY z ČNB (CNY/CZK ÷ USD/CZK) — stejná logika jako dashboard."""
    rates = fetch_cnb_rates() or {}
    try:
        cny = float(rates["CNY"])
        usd = float(rates["USD"])
        if usd == 0:
            return None
        return cny / usd
    except (KeyError, TypeError, ValueError):
        return None


def china_vs_lme(metal: str, lme_usd: float | None) -> str:
    cny = fetch_ccmn_cny(metal)
    fx = usd_per_cny()
    if not cny:
        return "Čína CCMN: spot teď nemám."
    if not fx:
        return f"Čína CCMN {_fmt(cny, 0)} CNY/t (kurz CNY→USD teď nemám)."
    usd = cny * fx
    if not lme_usd:
        return f"Čína Changjiang {_fmt(cny, 0)} CNY/t ≈ {_fmt(usd, 0)} USD/t."
    spread = (usd - lme_usd) / lme_usd * 100.0
    if spread < -1:
        vs = f"levnější než LME o {abs(spread):.1f} %"
    elif spread > 1:
        vs = f"dražší než LME o {spread:.1f} %"
    else:
        vs = f"skoro stejně jako LME ({spread:+.1f} %)"
    return (
        f"Čína Changjiang {_fmt(cny, 0)} CNY/t ≈ {_fmt(usd, 0)} USD/t — {vs}."
    )


def _lme_closed() -> bool:
    """LME o víkendu neobchoduje (Praha)."""
    return _now().weekday() >= 5


def _lme_stamp(asof) -> str:
    asof_s = asof.strftime("%d.%m.") if asof else "?"
    today = asof is not None and asof == _naive(_now()).date()
    if today:
        return "dnešní official"
    if _lme_closed():
        return (
            f"poslední official {asof_s} — LME o víkendu neobchoduje, "
            "číslo se nemění"
        )
    return f"official {asof_s} (dnešní až ~13:20 Praha)"


def metal_block(name: str, df: pd.DataFrame | None, *, metal: str | None = None) -> str:
    if df is None or df.empty:
        lme_line = f"{name}: Westmetall teď neodpověděl."
        price = None
    else:
        price = float(df["Close"].iloc[-1])
        rsi = rsi14(df)
        s20, s50 = sma_last(df, 20), sma_last(df, 50)
        wp = week_pct(df)
        week = "týden N/A" if wp is None else f"týden {wp:+.1f} %"
        rsi_s = "RSI N/A" if rsi is None else f"RSI {rsi:.0f} ({rsi_words(rsi)})"

        def vs(sma, label):
            if not sma:
                return f"{label} N/A"
            pct = (price / sma - 1.0) * 100.0
            return f"{'nad' if pct >= 0 else 'pod'} {label} o {abs(pct):.1f} %"

        look = outlook(df)
        if look:
            pct, direction = look
            ens = f"Výhled ~21 dní: {direction} ({pct:+.1f} %, statistika)."
        else:
            ens = "Výhled: málo historie."
        asof = lme_asof(df)
        stamp = _lme_stamp(asof)
        lme_line = (
            f"{name} LME Cash {_fmt(price, 0)} USD/t ({stamp}) · {week}. {rsi_s}. "
            f"{vs(s20, 'SMA20')}, {vs(s50, 'SMA50')}. {ens}"
        )
    if metal in ("copper", "aluminum"):
        return lme_line + "\n" + china_vs_lme(metal, price)
    return lme_line


def _abs_url(href: str) -> str:
    raw = (href or "").strip()
    if raw.startswith("//"):
        return "https:" + raw
    if raw.startswith("http"):
        return raw
    if raw.startswith("/"):
        return "https://zpravy.kurzy.cz" + raw
    return raw


def _naive(dt: datetime | None) -> datetime | None:
    """Porovnávání datumů musí být bez mixu tz-aware / tz-naive."""
    if dt is None:
        return None
    if dt.tzinfo is not None:
        return dt.astimezone(TZ).replace(tzinfo=None)
    return dt


def parse_news_dt(text: str) -> datetime | None:
    text = (text or "").strip()
    if not text:
        return None
    try:
        return _naive(parsedate_to_datetime(text))
    except Exception:
        pass
    m = re.search(r"(\d{1,2})\.\s*(\d{1,2})\.\s*(\d{4})", text)
    if m:
        try:
            return datetime(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        except ValueError:
            return None
    m = re.match(r"(po|út|ut|st|čt|ct|pá|pa|so|ne)\s+\d{1,2}:\d{2}", text, re.I)
    if not m:
        return None
    key = m.group(1).lower()
    want = WD_CS.get(key)
    if want is None:
        return None
    today = _naive(_now()).replace(hour=0, minute=0, second=0, microsecond=0)
    delta = (today.weekday() - want) % 7
    return today - timedelta(days=delta)


def listing(query: str) -> list[dict]:
    r = _get(f"https://zpravy.kurzy.cz/l.asp?comb={quote(query)}")
    if r is None:
        return []
    soup = BeautifulSoup(r.text, "lxml")
    out, seen = [], set()
    for box in soup.select("div.zpravy"):
        a = box.find("a", href=True)
        if a is None:
            continue
        href = _abs_url(a.get("href") or "")
        title = (a.get("title") or a.get_text(" ", strip=True) or "").strip()
        if not title or href in seen or not re.search(r"/\d{5,}-", href):
            continue
        seen.add(href)
        datum = box.select_one(".datum")
        when = datum.get_text(" ", strip=True) if datum else ""
        out.append({
            "title": title,
            "url": href,
            "when": when,
            "dt": parse_news_dt(when),
        })
    return out


def rss_col(col: str) -> list[dict]:
    r = _get(f"https://www.kurzy.cz/zpravy/util/forext.dat?type=rss&col={col}&rows=40")
    if r is None:
        return []
    try:
        root = ET.fromstring(r.content)
    except Exception:
        return []
    out = []
    for item in root.findall(".//item"):
        title = (item.findtext("title") or "").strip()
        link = _abs_url(item.findtext("link") or "")
        pub = (item.findtext("pubDate") or "").strip()
        if title and link:
            out.append({
                "title": title,
                "url": link,
                "when": pub,
                "dt": parse_news_dt(pub),
            })
    return out


def classify(title: str, url: str) -> str | None:
    blob = f"{title} {url}"
    metal = bool(METAL_RE.search(blob))
    freight = bool(FREIGHT_RE.search(blob))
    energy = bool(ENERGY_RE.search(blob))
    if GOLD_RE.search(title) and not metal and not freight and not energy:
        return None
    if NOISE_RE.search(title) and not metal and not freight and not energy:
        return None
    if metal:
        return "metal"
    if freight:
        return "freight"
    if energy:
        return "energy"
    if GEO_RE.search(blob):
        return "geo"
    if MACRO_RE.search(title):
        return "macro"
    return None


def google_news(query: str, *, hl: str = "cs", gl: str = "CZ", ceid: str = "CZ:cs") -> list[dict]:
    url = (
        "https://news.google.com/rss/search?q="
        + quote(query)
        + f"&hl={hl}&gl={gl}&ceid={quote(ceid)}"
    )
    r = _get(url, timeout=25)
    if r is None:
        return []
    try:
        root = ET.fromstring(r.content)
    except Exception:
        return []
    out = []
    for item in root.findall(".//item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        pub = (item.findtext("pubDate") or "").strip()
        if not title or not link:
            continue
        title = re.sub(r"\s*-\s*BusinessInfo\.cz\s*$", "", title, flags=re.I)
        out.append({
            "title": title,
            "url": link,
            "when": pub,
            "dt": parse_news_dt(pub),
        })
    return out


def pick_news(*, cats: tuple[str, ...] | None = None, limit: int = NEWS_LIMIT) -> list[dict]:
    global _news_cache, _news_cache_at, _news_pool
    stale = _news_cache is None or (time.time() - _news_cache_at) > NEWS_CACHE_SEC
    if stale:
        print("Kurzy.cz + Google News CZ/svět za 7 dní…")
        pooled: list[dict] = []
        for q in LIST_QUERIES:
            pooled.extend(listing(q))
        for col in RSS_COLS:
            pooled.extend(rss_col(col))
        for q in GNEWS_CZ:
            pooled.extend(google_news(q))
        for q in GNEWS_WORLD:
            pooled.extend(google_news(q, hl="en-US", gl="US", ceid="US:en"))
        cutoff = _naive(_now()).replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=NEWS_DAYS)
        buckets: dict[str, list[dict]] = {k: [] for k in CAT_ORDER}
        seen: set[str] = set()
        for item in pooled:
            url = item.get("url") or ""
            title = item.get("title") or ""
            dt = _naive(item.get("dt"))
            if not url or url in seen or dt is None or dt < cutoff:
                continue
            cat = classify(title, url)
            if not cat:
                continue
            seen.add(url)
            row = {
                "title": title,
                "url": url,
                "dt": dt,
                "cat": cat,
                "when": dt.strftime("%d.%m."),
            }
            buckets[cat].append(row)
        for cat in buckets:
            buckets[cat].sort(key=lambda x: x["dt"], reverse=True)
        picked: list[dict] = []
        for cat, n in CAT_QUOTA.items():
            picked.extend(buckets[cat][:n])
        picked.sort(key=lambda x: (CAT_ORDER.get(x["cat"], 9), -x["dt"].timestamp()))
        _news_cache = picked
        _news_pool = []
        for cat in buckets:
            _news_pool.extend(buckets[cat])
        _news_cache_at = time.time()
    items = list(_news_cache)
    if cats:
        items = [x for x in items if x.get("cat") in cats]
        extra: list[dict] = []
        if len(items) < limit:
            # freight příkaz bere i geo (Čína/Turecko/cla)
            if "freight" in cats:
                extra = [
                    x for x in (_news_cache or [])
                    if x.get("cat") in ("geo", "energy") and x not in items
                ]
        items = (items + extra)[:limit]
    return items[:limit]


def news_synthesis(items: list[dict]) -> str:
    if not items:
        return "Za posledních 7 dní nemám použitelný titulek k kovu, dopravě, energetice ani politice."
    blob = " ".join(i["title"].lower() for i in items)
    bits = []
    if re.search(r"hliník|aluminium|aluminum", blob):
        bits.append("hliník")
    if re.search(r"měď|copper", blob):
        bits.append("měď")
    if re.search(r"nedostat|squeeze|zásob", blob):
        bits.append("fyzický kov / zásoby LME")
    if re.search(r"hormuz|suez|námoř|kontejner|fracht", blob):
        bits.append("námořní trasy")
    if re.search(r"energetik|elektřin|plyn|LNG|jád", blob):
        bits.append("energetika")
    if re.search(r"tureck|turkey", blob):
        bits.append("Turecko")
    if re.search(r"clo|cla|tarif|sankc|cbam", blob):
        bits.append("cla / sankce")
    if re.search(r"čín|cína|china", blob):
        bits.append("Čína")
    if re.search(r"fed|sazb", blob):
        bits.append("Fed / sazby")
    if re.search(r"ropa|brent|wti", blob):
        bits.append("ropa")
    if "bhp" in blob:
        bits.append("BHP")
    if bits:
        return "Za poslední týden se točí hlavně kolem: " + ", ".join(bits) + "."
    return "Beru jen titulky z posledních 7 dní, které hýbou kovem, dopravou nebo kurzy."


def format_news(items: list[dict]) -> str:
    if not items:
        return "Za posledních 7 dní nemám použitelný titulek."
    lines = ["Zprávy za posledních 7 dní:"]
    current = None
    n = 0
    for item in items:
        cat = item.get("cat")
        if cat != current:
            current = cat
            lines.append("")
            lines.append(CAT_LABEL.get(cat or "", cat or ""))
        n += 1
        lines.append(f"{n}. {to_czech(item['title'])} ({item['when']})")
        lines.append(item["url"])
    return "\n".join(lines)


def spoken_news(items: list[dict]) -> str:
    if not items:
        return news_synthesis(items)
    titles = ". ".join(to_czech(i["title"]) for i in items[:5])
    return news_synthesis(items) + " Hlavní titulky: " + titles + "."


def greeting() -> str:
    now = _now()
    return f"Ahoj. Tady Henry, {WEEKDAY_CS[now.weekday()]} {now.strftime('%d. %m. %Y %H:%M')}."


def fetch_cnb_text() -> str:
    rates = fetch_cnb_rates()
    if not rates:
        return "ČNB teď neodpověděla."
    want = ("EUR", "USD", "CNY", "TRY")
    bits = []
    for code in want:
        val = rates.get(code)
        if val is None:
            continue
        bits.append(f"{code} {float(val):.3f}".replace(".", ","))
    if not bits:
        return "ČNB lístek se nepovedlo přečíst."
    date_str = str(rates.get("_date") or "")
    return f"ČNB {date_str}: " + " · ".join(bits) + " (Kč za 1 jednotku)."


def _metal_news(kind: str) -> list[dict]:
    needle = CU_NEWS_RE if kind == "copper" else AL_NEWS_RE
    items = []
    for row in pick_news(cats=("metal",), limit=NEWS_LIMIT):
        blob = f"{row.get('title') or ''} {row.get('url') or ''}"
        if needle.search(blob):
            items.append(row)
        if len(items) >= 5:
            break
    return items


def build_payload(kind: str) -> tuple[str, str]:
    """Text do chatu + kratší text k hlasu."""
    if kind == "voice":
        p = _toggle_voice()
        label = p["label"]
        text = f"Hlas nastaven: {label}. Souhrn a ranní report budou tímhle hlasem."
        return text, f"Tady Henry. Nový hlas: {label}."
    if kind == "help":
        return HELP_TEXT, "Napište update, měď, hliník, zprávy, doprava, nebo kurzy."
    if kind == "fx":
        text = greeting() + "\n\n" + fetch_cnb_text()
        return text, text
    if kind == "copper":
        block = metal_block("Měď", lme("copper"), metal="copper")
        items = _metal_news("copper")
        extra = ("\n\n" + format_news(items)) if items else "\n\nZa posledních 7 dní nemám zvláštní titulek jen k mědi."
        text = greeting() + "\n\n" + block + extra
        return text, greeting() + " " + block + " " + spoken_news(items)
    if kind == "aluminum":
        block = metal_block("Hliník", lme("aluminum"), metal="aluminum")
        items = _metal_news("aluminum")
        extra = ("\n\n" + format_news(items)) if items else "\n\nZa posledních 7 dní nemám zvláštní titulek jen k hliníku."
        text = greeting() + "\n\n" + block + extra
        return text, greeting() + " " + block + " " + spoken_news(items)
    if kind == "freight":
        items = pick_news(cats=("freight", "geo"), limit=6)
        body = format_news(items)
        text = greeting() + "\n\n" + body
        return text, greeting() + " " + spoken_news(items)
    if kind == "news":
        items = pick_news()
        body = news_synthesis(items) + "\n\n" + format_news(items)
        text = greeting() + "\n\n" + body
        return text, greeting() + " " + spoken_news(items)
    if kind == "midday":
        return _midday_payload()
    # full / morning
    cu = metal_block("Měď", lme("copper"), metal="copper")
    al = metal_block("Hliník", lme("aluminum"), metal="aluminum")
    items = pick_news()
    syn = news_synthesis(items)
    text = "\n".join([
        greeting(),
        "",
        cu,
        al,
        "",
        syn,
        "",
        format_news(items),
        "",
        "LME Official Settlement na Westmetallu: dnešní číslo bývá ~13:20–14:25 Praha. "
        "O víkendu LME neobchoduje — zůstane páteční official. "
        "CCMN Changjiang ráno ~10:30 čínského času (u nás okolo 4:30).",
        f"Dashboard: {DASHBOARD_URL}",
        "Westmetall LME Cash, ccmn.cn, Kurzy.cz, Google News (CZ i svět, titulky česky), ČNB na příkaz kurzy.",
    ])
    spoken = " ".join([greeting(), cu, al, syn, "Odkazy jsou v textu."])
    return text, spoken


def intent(text: str) -> str | None:
    raw = re.sub(r"@[\w]+", "", text or "").strip()
    low = raw.lower()
    if re.search(r"^/hlas\b|^hlas\b", low):
        return "voice"
    if re.search(r"/med\b|/cu\b", low):
        return "copper"
    if re.search(r"/hlinik\b|/al\b", low):
        return "aluminum"
    if re.search(r"/zpravy\b|/news\b", low):
        return "news"
    if re.search(r"/doprava\b", low):
        return "freight"
    if re.search(r"/kurzy\b|/fx\b", low):
        return "fx"
    if re.search(r"/help\b|n[áa]pov[eě]da|\bpomoc\b|p[rř][ií]kaz", low):
        return "help"
    if re.search(r"doprav|kontejner|fracht|tureck|hormuz|suez", low):
        return "freight"
    if re.search(r"kurz|/fx\b|\bčnb\b|\bcnb\b|eur/usd|eur/czk", low):
        return "fx"
    if re.search(r"zpr[aá]v|/news\b", low) and not re.search(
        r"souhrn|briefing|/henry|update", low
    ):
        return "news"
    if re.search(r"hlin[ií]k|aluminum|/al\b", low):
        return "aluminum"
    if re.search(r"měď|mědi|\bmed\b|\bcopper\b|/cu\b", low):
        return "copper"
    if re.search(
        r"ahoj|henry|/henry|/start|/update|\bupdate\b|briefing|souhrn|jaké jsou",
        low,
    ):
        return "full"
    return None


def tg_token() -> str:
    return (os.environ.get("TELEGRAM_BOT_TOKEN") or os.environ.get("ALERT_TELEGRAM_TOKEN") or "").strip()


def allowed_chats() -> set[str]:
    raw = (os.environ.get("TELEGRAM_CHAT_ID") or os.environ.get("ALERT_TELEGRAM_CHAT") or "").strip()
    return {x.strip() for x in raw.split(",") if x.strip()}


def tg_api(method: str, payload: dict, *, timeout: int = 30) -> dict | None:
    token = tg_token()
    if not token:
        print("Chybí TELEGRAM_BOT_TOKEN.")
        return None
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{token}/{method}",
            json=payload,
            timeout=timeout,
        )
        data = r.json() if r.content else {}
        if r.status_code >= 300 or not data.get("ok"):
            print(f"Telegram {method}: {r.status_code} {str(data)[:240]}")
            return None
        return data
    except Exception as e:
        print(f"Telegram {method}: {e}")
        return None


def register_commands() -> None:
    tg_api("setMyCommands", {"commands": BOT_COMMANDS})


def _strip_old_keyboard() -> None:
    """Jednou schová starou dolní lištu, která v Desktopu spouštěla Reply."""
    if os.path.isfile(KB_MARK):
        return
    for chat in allowed_chats():
        tg_api(
            "sendMessage",
            {
                "chat_id": chat,
                "text": "Dolní lišta je pryč — v Telegramu spouštěla Odpovědět.",
                "reply_markup": {"remove_keyboard": True},
            },
        )
        send_text(
            chat,
            "Tlačítka jsou teď pod každou odpovědí (Měď, Souhrn, Hlas…). "
            "Klikejte tam, ne do textu bubliny.",
        )
    try:
        with open(KB_MARK, "w", encoding="utf-8") as f:
            f.write("1")
    except OSError:
        pass


def send_text(chat_id: str, text: str) -> bool:
    ok = True
    rest = text
    while rest:
        chunk, rest = rest[:TG_LIMIT], rest[TG_LIMIT:]
        if rest:
            cut = chunk.rfind("\n")
            if cut > 500:
                rest = chunk[cut + 1 :] + rest
                chunk = chunk[:cut]
        payload = {
            "chat_id": chat_id,
            "text": chunk,
            "disable_web_page_preview": True,
        }
        if not rest:
            payload["reply_markup"] = INLINE_KEYBOARD
        sent = tg_api("sendMessage", payload)
        ok = bool(sent) and ok
    return ok


def _tts_enabled() -> bool:
    flag = (os.environ.get("HENRY_TTS") or "1").strip().lower()
    return flag not in ("0", "false", "no")


def speak_to_mp3(text: str, path: str) -> bool:
    try:
        import edge_tts
    except Exception as e:
        print(f"TTS import: {e}")
        return False
    spoken = re.sub(r"https?://\S+", "", text)
    spoken = re.sub(r"\s+", " ", spoken).strip()[:2200]
    if not spoken:
        return False

    async def _run() -> None:
        p = _voice_preset()
        try:
            comm = edge_tts.Communicate(
                spoken,
                p["voice"],
                rate=p.get("rate") or "+0%",
                pitch=p.get("pitch") or "+0Hz",
            )
        except TypeError:
            comm = edge_tts.Communicate(spoken, p["voice"])
        await comm.save(path)

    try:
        asyncio.run(_run())
        return os.path.isfile(path) and os.path.getsize(path) > 800
    except Exception as e:
        print(f"TTS: {e}")
        return False


def send_voice(chat_id: str, spoken: str) -> bool:
    if not _tts_enabled() or not spoken.strip():
        return False
    token = tg_token()
    if not token:
        return False
    fd, path = tempfile.mkstemp(suffix=".mp3")
    os.close(fd)
    try:
        if not speak_to_mp3(spoken, path):
            return False
        with open(path, "rb") as f:
            r = requests.post(
                f"https://api.telegram.org/bot{token}/sendAudio",
                data={
                    "chat_id": chat_id,
                    "title": "Henry",
                    "performer": "Henry",
                },
                files={"audio": ("henry.mp3", f, "audio/mpeg")},
                timeout=120,
            )
        data = r.json() if r.content else {}
        if r.status_code >= 300 or not data.get("ok"):
            print(f"Telegram sendAudio: {r.status_code} {str(data)[:240]}")
            return False
        return True
    except Exception as e:
        print(f"send_voice: {e}")
        return False
    finally:
        try:
            os.remove(path)
        except OSError:
            pass


def send_reply(chat_id: str, text: str, spoken: str, *, voice: bool = False) -> bool:
    ok = send_text(chat_id, text)
    if voice:
        send_voice(chat_id, spoken)
    return ok


def _read_offset() -> int:
    try:
        with open(OFFSET_PATH, encoding="utf-8") as f:
            return int((f.read() or "0").strip() or "0")
    except Exception:
        return 0


def _write_offset(n: int) -> None:
    with open(OFFSET_PATH, "w", encoding="utf-8") as f:
        f.write(str(n))


def _daily_stamp() -> str:
    return _now().strftime("%Y-%m-%d")


def _daily_already_sent() -> bool:
    try:
        with open(DAILY_MARK, encoding="utf-8") as f:
            return (f.read() or "").strip() == _daily_stamp()
    except Exception:
        return False


def _mark_daily_sent() -> None:
    with open(DAILY_MARK, "w", encoding="utf-8") as f:
        f.write(_daily_stamp())


def _stamp_path_sent(path: str) -> bool:
    try:
        with open(path, encoding="utf-8") as f:
            return (f.read() or "").strip() == _daily_stamp()
    except Exception:
        return False


def _mark_stamp(path: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        f.write(_daily_stamp())


def _midday_already_sent() -> bool:
    return _stamp_path_sent(MIDDAY_MARK)


def _mark_midday_sent() -> None:
    _mark_stamp(MIDDAY_MARK)


def _lme_already_sent() -> bool:
    return _stamp_path_sent(LME_MARK)


def _mark_lme_sent() -> None:
    _mark_stamp(LME_MARK)


def _save_morning_urls(urls: list[str]) -> None:
    with open(MORNING_URLS, "w", encoding="utf-8") as f:
        f.write("\n".join(u for u in urls if u))


def _load_morning_urls() -> set[str]:
    try:
        with open(MORNING_URLS, encoding="utf-8") as f:
            return {ln.strip() for ln in f if ln.strip()}
    except Exception:
        return set()


def _refresh_market() -> None:
    global _news_cache, _news_cache_at, _news_pool, _cnb_cache, _cnb_cache_at
    _lme_cache.clear()
    _ccmn_cache.clear()
    _cnb_cache = None
    _cnb_cache_at = 0.0
    _news_cache = None
    _news_pool = []
    _news_cache_at = 0.0


def _headline_impact(title: str, url: str) -> int:
    blob = f"{title} {url}"
    if CRITICAL_NEWS_RE.search(blob):
        return 3
    if HIGH_NEWS_RE.search(blob):
        return 2
    cat = classify(title, url)
    if cat in ("metal", "freight", "energy"):
        return 1
    return 0


def _today_headlines() -> list[dict]:
    today = _naive(_now()).date()
    seen_morning = _load_morning_urls()
    pick_news(limit=NEWS_LIMIT)
    out = []
    for row in _news_pool:
        dt = row.get("dt")
        url = row.get("url") or ""
        if dt is None or _naive(dt).date() != today:
            continue
        if url and url in seen_morning:
            continue
        impact = _headline_impact(row.get("title") or "", url)
        if impact <= 0:
            continue
        item = dict(row)
        item["impact"] = impact
        out.append(item)
    out.sort(key=lambda x: (-int(x.get("impact") or 0), -x["dt"].timestamp()))
    return out


def evaluate_midday(*, allow_lme_price: bool = False) -> dict:
    """
    Extra report:
    - 11–13 Praha: jen dnešní silné zprávy (LME Official ještě není).
    - po 14:15: i skok dnešního LME Cash, až je na Westmetallu.
    """
    cu_df, al_df = lme("copper"), lme("aluminum")
    cu_d, al_d = day_pct(cu_df), day_pct(al_df)
    headlines = _today_headlines()
    reasons: list[str] = []
    lme_today = lme_is_today(cu_df) or lme_is_today(al_df)
    if allow_lme_price and lme_today:
        if cu_d is not None and abs(cu_d) >= PRICE_SHOCK_PCT:
            reasons.append(f"měď {cu_d:+.1f} % vs včerejší LME Official")
        if al_d is not None and abs(al_d) >= PRICE_SHOCK_PCT:
            reasons.append(f"hliník {al_d:+.1f} % vs včerejší LME Official")
    critical = [h for h in headlines if int(h.get("impact") or 0) >= 3]
    strong = [h for h in headlines if int(h.get("impact") or 0) >= 2]
    if critical:
        reasons.append("kritický titulek: " + critical[0]["title"])
    score = sum(int(h.get("impact") or 0) for h in headlines)
    if (
        score >= MIDDAY_IMPACT_MIN
        and strong
        and not any("kritický titulek" in r for r in reasons)
    ):
        reasons.append(
            f"dnešní zprávy váha {score} (práh {MIDDAY_IMPACT_MIN}, "
            f"{len(strong)} silnějších titulků)"
        )
    should = bool(reasons)
    log = "; ".join(reasons) if reasons else (
        f"klid (LME dnes={'ano' if lme_today else 'ne'}, "
        f"Cu {cu_d:+.1f} % / Al {al_d:+.1f} %, titulky {len(headlines)}, váha {score})"
        if cu_d is not None and al_d is not None
        else f"klid (LME dnes={'ano' if lme_today else 'ne'}, titulky {len(headlines)}, váha {score})"
    )
    return {
        "should": should,
        "reasons": reasons,
        "log": log,
        "headlines": headlines[:6],
        "cu_d": cu_d,
        "al_d": al_d,
        "lme_today": lme_today,
    }


def _midday_payload(decision: dict | None = None) -> tuple[str, str]:
    d = decision or evaluate_midday()
    why = d["reasons"] or ["ruční spuštění"]
    cu = metal_block("Měď", lme("copper"), metal="copper")
    al = metal_block("Hliník", lme("aluminum"), metal="aluminum")
    items = d.get("headlines") or []
    news = format_news(items) if items else "Nový silný titulek od rána nemám — spouštěč je pohyb LME."
    text = "\n".join([
        greeting(),
        "",
        "Polední report — jen protože se něco hnulo:",
        " · ".join(why),
        "",
        cu,
        al,
        "",
        news,
    ])
    spoken = (
        "Polední report. " + " ".join(why) + " " + cu + " " + al
        + " Odkazy jsou v textu."
    )
    return text, spoken


def send_morning(*, force: bool = False) -> bool:
    chats = allowed_chats()
    if not chats:
        print("Chybí TELEGRAM_CHAT_ID — ranní souhrn nemá kam poslat.")
        return False
    if _daily_already_sent() and not force:
        return False
    try:
        _refresh_market()
        text, spoken = build_payload("full")
        if _lme_closed():
            head = (
                "Víkendový souhrn. LME neobchoduje — beru poslední official, "
                "číslo se nemění. Zprávy jedou dál.\n\n"
            )
            spoken_head = "Víkendový souhrn. Burza kovů stojí, číslo je poslední official. "
        else:
            head = "Ranní souhrn.\n\n"
            spoken_head = "Ranní souhrn. "
        text = head + text
        spoken = spoken_head + spoken
        ok = True
        for chat in chats:
            print(f"Posílám ranní souhrn do {chat}")
            ok = send_reply(chat, text, spoken, voice=True) and ok
        if ok:
            _mark_daily_sent()
            _save_morning_urls([i.get("url") or "" for i in pick_news()])
        return ok
    except Exception:
        traceback.print_exc()
        return False


def send_midday(*, force: bool = False) -> bool:
    chats = allowed_chats()
    if not chats:
        print("Chybí TELEGRAM_CHAT_ID — polední report nemá kam poslat.")
        return False
    if _midday_already_sent() and not force:
        return False
    try:
        _refresh_market()
        decision = evaluate_midday(allow_lme_price=False)
        print("Polední vyhodnocení: " + decision["log"])
        if not force and not decision["should"]:
            return False
        text, spoken = _midday_payload(decision)
        ok = True
        for chat in chats:
            print(f"Posílám polední report do {chat}")
            ok = send_reply(chat, text, spoken, voice=True) and ok
        if ok:
            _mark_midday_sent()
        return ok
    except Exception:
        traceback.print_exc()
        return False


def send_lme_flash(*, force: bool = False) -> bool:
    """Až Westmetall má dnešní Official Settlement (~14:15 Praha)."""
    chats = allowed_chats()
    if not chats:
        return False
    if _lme_already_sent() and not force:
        return False
    try:
        _refresh_market()
        cu_df, al_df = lme("copper"), lme("aluminum")
        if not (lme_is_today(cu_df) or lme_is_today(al_df)):
            print("Dnešní LME Official na Westmetallu ještě není.")
            return False
        decision = evaluate_midday(allow_lme_price=True)
        print("LME Official vyhodnocení: " + decision["log"])
        if not force and not decision["should"]:
            print("Dnešní LME je venku, pohyb pod práh — bez extra reportu.")
            _mark_lme_sent()
            return False
        text, spoken = _midday_payload(decision)
        text = text.replace("Polední report — jen protože se něco hnulo:", "Dnešní LME Official je na Westmetallu:")
        spoken = "Dnešní LME Official. " + spoken
        ok = True
        for chat in chats:
            print(f"Posílám LME Official flash do {chat}")
            ok = send_reply(chat, text, spoken, voice=True) and ok
        if ok:
            _mark_lme_sent()
        return ok
    except Exception:
        traceback.print_exc()
        return False


def send_daily(*, force: bool = False) -> bool:
    return send_morning(force=force)


def process_inbox(*, skip_full: bool = False, poll_timeout: int = 0) -> int:
    allowed = allowed_chats()
    if not tg_token() or not allowed:
        if not allowed:
            print("TELEGRAM_CHAT_ID není nastavené — inbox ignoruji.")
        return 0
    offset = _read_offset()
    payload = {
        "timeout": max(0, int(poll_timeout)),
        "limit": 50,
        "allowed_updates": ["message", "edited_message", "callback_query"],
    }
    if offset:
        payload["offset"] = offset
    data = tg_api("getUpdates", payload, timeout=max(30, int(poll_timeout) + 20))
    if not data:
        return 0
    replied = 0
    last_id = offset
    cache: dict[str, tuple[str, str]] = {}
    for upd in data.get("result") or []:
        last_id = max(last_id, int(upd.get("update_id") or 0) + 1)
        cb = upd.get("callback_query") or {}
        msg = upd.get("message") or upd.get("edited_message") or {}
        kind = None
        chat = None
        if cb:
            tg_api("answerCallbackQuery", {"callback_query_id": cb.get("id")})
            chat = ((cb.get("message") or {}).get("chat") or {}).get("id")
            kind = cb.get("data") if cb.get("data") in KINDS else None
        else:
            chat = (msg.get("chat") or {}).get("id")
            text = (msg.get("text") or msg.get("caption") or "").strip()
            if chat is None or not text:
                continue
            kind = intent(text)
        if chat is None or kind is None:
            continue
        chat_s = str(chat)
        if chat_s not in allowed:
            print(f"Ignoruji cizí chat {chat_s}")
            continue
        if skip_full and kind == "full":
            continue
        try:
            if kind not in cache:
                cache[kind] = build_payload(kind)
            body, spoken = cache[kind]
            send_reply(chat_s, body, spoken, voice=(kind in ("full", "voice")))
            replied += 1
        except Exception:
            print(f"Chyba při odpovědi ({kind}) do {chat_s}:")
            traceback.print_exc()
    if last_id:
        _write_offset(last_id)
    return replied


def _morning_window() -> bool:
    now = _now()
    if now.weekday() < 5:
        return 7 <= now.hour < 9
    return 8 <= now.hour < 10


def _midday_window() -> bool:
    now = _now()
    return now.weekday() < 5 and 11 <= now.hour < 13


def _lme_window() -> bool:
    now = _now()
    return now.weekday() < 5 and 14 <= now.hour < 16


def listen() -> int:
    """Long poll Telegram, dokud GitHub Actions job běží."""
    if not tg_token():
        print("Nastavte GitHub Actions secret TELEGRAM_BOT_TOKEN (a TELEGRAM_CHAT_ID).")
        return 1
    try:
        seconds = int((os.environ.get("HENRY_LISTEN_SEC") or "20700").strip())
    except ValueError:
        seconds = 20700
    seconds = max(60, seconds)
    stop = {"v": False}

    def _stop(*_args) -> None:
        stop["v"] = True
        print("Henry končí (signal) — příští job ho zase zvedne.")

    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    register_commands()
    _strip_old_keyboard()
    end = time.time() + seconds
    print(f"Henry poslouchá Telegram (až {seconds}s).")
    while not stop["v"] and time.time() < end:
        sent_brief = False
        if _morning_window():
            sent_brief = send_morning(force=False)
        elif _midday_window():
            sent_brief = send_midday(force=False)
        elif _lme_window():
            sent_brief = send_lme_flash(force=False)
        remaining = end - time.time()
        if remaining <= 1:
            break
        poll = min(50, max(1, int(remaining)))
        n = process_inbox(skip_full=sent_brief, poll_timeout=poll)
        if n:
            print(f"Inbox: {n} odpovědí.")
    print("Henry listen hotovo.")
    return 0


def run(*, daily: bool, inbox: bool) -> int:
    if not tg_token():
        print("Nastavte GitHub Actions secret TELEGRAM_BOT_TOKEN (a TELEGRAM_CHAT_ID).")
        return 1
    register_commands()
    sent_daily = False
    if daily:
        sent_daily = send_morning(force="--daily" in sys.argv)
    if "--midday" in sys.argv:
        sent_daily = send_midday(force=True) or sent_daily
    if inbox:
        n = process_inbox(skip_full=sent_daily)
        print(f"Inbox: {n} odpovědí.")
    return 0


def _want_daily(argv: list[str]) -> bool:
    if "--daily" in argv:
        return True
    flag = (os.environ.get("HENRY_DAILY") or "").strip().lower()
    if flag in ("1", "true", "yes"):
        return True
    if flag in ("0", "false", "no"):
        return False
    return _morning_window()


if __name__ == "__main__":
    args = sys.argv[1:]
    if "--listen" in args:
        sys.exit(listen())
    inbox = "--inbox" in args or "--daily" not in args
    daily = _want_daily(args)
    if "--inbox" in args:
        inbox = True
    sys.exit(run(daily=daily, inbox=inbox))
