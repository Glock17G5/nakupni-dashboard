"""
Henry — denní souhrn na Telegram (ne do dashboardu).

Ráno pošle briefing: LME Cash měď/hliník, RSI, SMA 20/50, statistický výhled,
titulky Kurzy.cz. Když napíšete „Ahoj Henry“ / „zprávy“ / /henry, odpoví stejně.

Spuštění:
  python henry.py                 # inbox + ranní souhrn, když HENRY_DAILY=1
  python henry.py --daily         # jen souhrn na TELEGRAM_CHAT_ID
  python henry.py --inbox         # jen nepřečtené zprávy
"""

from __future__ import annotations

import json
import os
import re
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
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
METAL_RE = re.compile(
    r"měď|mědi|měděn|\bcopper\b|hliník|hliníku|hliniku|aluminium|aluminum|"
    r"\blme\b|-medi-|_medi_|/medi-|nedostatek fyzick|\bbhp\b|zambi",
    re.I,
)
NOISE_RE = re.compile(
    r"bitcoin|nvidia|robinhood|hlídačkovn|průměrn[áa] mzda|kakao|pšenice|"
    r"nasdaq|marriott|airbnb|coinbase",
    re.I,
)
MACRO_RE = re.compile(
    r"\bfed\b|sazb|čín|cína|\bchina\b|brent|\bropa\b|\bwti\b|geopolit",
    re.I,
)
ASK_RE = re.compile(
    r"ahoj|henry|/henry|/start|zpráv|zprav|briefing|souhrn|jaké jsou",
    re.I,
)
OFFSET_PATH = ".henry_tg_offset"
DAILY_MARK = ".henry_daily_sent"
TG_LIMIT = 3500


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


def metal_block(name: str, df: pd.DataFrame | None) -> str:
    if df is None or df.empty:
        return f"{name}: Westmetall teď neodpověděl."
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
        ens = (
            f"Statistický výhled ~21 dní: {direction} ({pct:+.1f} %). "
            "Jen matematika z historie (trend + SMA50), ne předpověď LME."
        )
    else:
        ens = "Výhled: málo historie."
    return (
        f"{name} LME Cash {_fmt(price, 0)} USD/t · {week}. {rsi_s}. "
        f"Cena je {vs(s20, 'SMA20')} a {vs(s50, 'SMA50')}. {ens}"
    )


def _abs_url(href: str) -> str:
    raw = (href or "").strip()
    if raw.startswith("//"):
        return "https:" + raw
    if raw.startswith("http"):
        return raw
    if raw.startswith("/"):
        return "https://zpravy.kurzy.cz" + raw
    return raw


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
        out.append({
            "title": title,
            "url": href,
            "when": datum.get_text(" ", strip=True) if datum else "",
        })
    return out


def rss_commodities() -> list[dict]:
    r = _get("https://www.kurzy.cz/zpravy/util/forext.dat?type=rss&col=ptKomodity&rows=40")
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
        if title and link:
            out.append({"title": title, "url": link, "when": ""})
    return out


def pick_news(limit: int = 7) -> list[dict]:
    pooled = [dict(x) for q in ("měď", "hliník") for x in listing(q)]
    pooled.extend(dict(x) for x in rss_commodities())
    metal, macro, seen = [], [], set()
    for item in pooled:
        url, title = item.get("url") or "", item.get("title") or ""
        if not url or url in seen:
            continue
        seen.add(url)
        blob = f"{title} {url}"
        if NOISE_RE.search(title) and not METAL_RE.search(blob):
            continue
        if METAL_RE.search(blob):
            metal.append(item)
        elif MACRO_RE.search(title):
            macro.append(item)
    picked = metal[:limit]
    if len(picked) < limit:
        picked.extend(macro[: min(3, limit - len(picked))])
    return picked


def news_synthesis(items: list[dict]) -> str:
    if not items:
        return "Kurzy.cz teď nemají použitelný titulek k mědi — posílám aspoň ceny."
    blob = " ".join(i["title"].lower() for i in items)
    bits = []
    if re.search(r"nedostat|squeeze|zásob", blob):
        bits.append("fyzický kov / zásoby LME")
    if "bhp" in blob:
        bits.append("BHP")
    if "zambi" in blob:
        bits.append("Zambie")
    if re.search(r"rekord|vyskoč", blob):
        bits.append("skok ceny mědi")
    if re.search(r"čín|cína|china", blob):
        bits.append("Čína")
    if re.search(r"fed|sazb", blob):
        bits.append("Fed / sazby")
    if re.search(r"ropa|brent", blob):
        bits.append("ropa")
    if bits:
        return "Dnes se točí hlavně kolem: " + ", ".join(bits) + "."
    return "Na Kurzy.cz je měď spíš v širších komoditních zprávách. Beru jen relevantní titulky."


def build_briefing() -> str:
    now = _now()
    print("Henry skládá briefing…")
    cu = fetch_lme_history("copper")
    al = fetch_lme_history("aluminum")
    news = pick_news()
    lines = [
        f"Ahoj. Tady Henry, {WEEKDAY_CS[now.weekday()]} {now.strftime('%d. %m. %Y %H:%M')}.",
        "",
        metal_block("Měď", cu),
        metal_block("Hliník", al),
        "",
        news_synthesis(news),
    ]
    if news:
        lines.append("")
        for i, item in enumerate(news, 1):
            when = f" ({item['when']})" if item.get("when") else ""
            lines.append(f"{i}. {item['title']}{when}")
            lines.append(item["url"])
        lines.append("")
    lines.append(
        "Zdroje: Westmetall LME Cash, Kurzy.cz (titulky). "
        "Predikce je statistika, ne věštba. Interní nákupy sem nepatří."
    )
    return "\n".join(lines)


def tg_token() -> str:
    return (os.environ.get("TELEGRAM_BOT_TOKEN") or os.environ.get("ALERT_TELEGRAM_TOKEN") or "").strip()


def allowed_chats() -> set[str]:
    raw = (os.environ.get("TELEGRAM_CHAT_ID") or os.environ.get("ALERT_TELEGRAM_CHAT") or "").strip()
    return {x.strip() for x in raw.split(",") if x.strip()}


def tg_api(method: str, payload: dict) -> dict | None:
    token = tg_token()
    if not token:
        print("Chybí TELEGRAM_BOT_TOKEN.")
        return None
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{token}/{method}",
            json=payload,
            timeout=30,
        )
        data = r.json() if r.content else {}
        if r.status_code >= 300 or not data.get("ok"):
            print(f"Telegram {method}: {r.status_code} {str(data)[:240]}")
            return None
        return data
    except Exception as e:
        print(f"Telegram {method}: {e}")
        return None


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
        sent = tg_api("sendMessage", {
            "chat_id": chat_id,
            "text": chunk,
            "disable_web_page_preview": True,
        })
        ok = bool(sent) and ok
    return ok


def send_briefing(chat_id: str) -> bool:
    return send_text(chat_id, build_briefing())


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


def process_inbox(*, skip_allowed_reply: bool = False) -> int:
    """Odpoví na Ahoj Henry / /henry. Cizí chaty ignoruje."""
    allowed = allowed_chats()
    if not tg_token() or not allowed:
        if not allowed:
            print("TELEGRAM_CHAT_ID není nastavené — inbox ignoruji.")
        return 0
    offset = _read_offset()
    payload = {"timeout": 0, "limit": 50}
    if offset:
        payload["offset"] = offset
    data = tg_api("getUpdates", payload)
    if not data:
        return 0
    replied = 0
    last_id = offset
    briefing_cache = None
    for upd in data.get("result") or []:
        last_id = max(last_id, int(upd.get("update_id") or 0) + 1)
        msg = upd.get("message") or upd.get("edited_message") or {}
        chat = (msg.get("chat") or {}).get("id")
        text = (msg.get("text") or msg.get("caption") or "").strip()
        if chat is None or not text:
            continue
        chat_s = str(chat)
        if allowed and chat_s not in allowed:
            print(f"Ignoruji cizí chat {chat_s}")
            continue
        if not ASK_RE.search(text):
            continue
        if skip_allowed_reply:
            continue
        if briefing_cache is None:
            briefing_cache = build_briefing()
        send_text(chat_s, briefing_cache)
        replied += 1
    if last_id:
        _write_offset(last_id)
    return replied


def run(*, daily: bool, inbox: bool) -> int:
    if not tg_token():
        print("Nastavte GitHub Actions secret TELEGRAM_BOT_TOKEN (a TELEGRAM_CHAT_ID).")
        return 1
    sent_daily = False
    if daily:
        chats = allowed_chats()
        if not chats:
            print("Chybí TELEGRAM_CHAT_ID — ranní souhrn nemá kam poslat.")
        elif _daily_already_sent() and "--daily" not in sys.argv:
            print("Denní souhrn už dnes šel — přeskočeno.")
        else:
            text = build_briefing()
            ok = True
            for chat in chats:
                print(f"Posílám denní souhrn do {chat}")
                ok = send_text(chat, text) and ok
            if ok:
                _mark_daily_sent()
            sent_daily = ok
    if inbox:
        n = process_inbox(skip_allowed_reply=sent_daily)
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
    return _now().hour < 10 and _now().weekday() < 5


if __name__ == "__main__":
    args = sys.argv[1:]
    inbox = "--inbox" in args or "--daily" not in args
    daily = _want_daily(args)
    if "--inbox" in args:
        inbox = True
    sys.exit(run(daily=daily, inbox=inbox))
