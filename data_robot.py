import json, requests, re, os, sys, smtplib
from email.mime.text import MIMEText
from bs4 import BeautifulSoup
import yfinance as yf
import pandas as pd
from datetime import datetime

def _scrape_ccmn_url(url, target):
    res = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
    res.encoding = "utf-8"
    soup = BeautifulSoup(res.text, "lxml")
    cell = soup.find(lambda tag: tag.name in ["td", "a", "span"] and tag.get_text(strip=True) == target)
    if cell:
        parent_tr = cell.find_parent("tr")
        if parent_tr:
            cols = parent_tr.find_all("td")
            if len(cols) >= 3:
                price = float(re.sub(r"[^\d.]", "", cols[2].get_text(strip=True)))
                if price > 0: return price
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
        m = re.search(r"([\d,]+(?:\.\d+)?)", span.get_text())
        if not m:
            continue
        price = float(m.group(1).replace(",", ""))
        if price <= 0:
            continue
        if "长江综合" in region:
            return price
        if picked is None or "上海地区" in region:
            picked = price
    return picked

def fetch_ccmn_price(metal):
    target = "1#铜" if metal == "copper" else "A00铝"
    fallback = "https://copper.ccmn.cn/" if metal == "copper" else "https://alu.ccmn.cn/"
    for url in ["https://www.ccmn.cn/", fallback]:
        try:
            price = _scrape_ccmn_url(url, target)
            if price and price > 0:
                return price
        except Exception as e:
            print(f"CCMN chyba {metal} ({url}): {e}")
    return None


_ALERT_METAL_DAY_PCT = 3.0
_ALERT_BRENT_DAY_PCT = 3.0
_ALERT_EURCZK_DAY_PCT = 1.5
_ALERT_CCMN_DAY_PCT = 3.0
_SOURCE_LABELS = {
    "ccmn_copper": "CCMN měď",
    "ccmn_aluminum": "CCMN hliník",
    "brent": "Brent (Yahoo BZ=F)",
    "eurusd": "EUR/USD (Yahoo)",
    "history": "Yahoo historie",
}


def _load_prev_robot():
    try:
        with open("robot_data.json", encoding="utf-8") as f:
            prev = json.load(f)
        return prev if isinstance(prev, dict) else {}
    except Exception:
        return {}


def _yf_pct(data, ticker):
    info = (data.get("yf_spot") or {}).get(ticker) or {}
    pct = info.get("delta_pct")
    try:
        return float(pct) if pct is not None else None
    except (TypeError, ValueError):
        return None


def _pct_change(new, old):
    try:
        new_f, old_f = float(new), float(old)
    except (TypeError, ValueError):
        return None
    if old_f == 0:
        return None
    return (new_f - old_f) / old_f * 100.0


def _collect_alerts(data, ccmn_prev):
    lines = []
    health = data.get("_health") or {}
    missing = [_SOURCE_LABELS.get(k, k) for k, ok in health.items() if not ok]
    if missing:
        lines.append("Výpadek zdroje: " + ", ".join(missing))

    def _move(label, pct, thresh, extra=""):
        if pct is None or abs(pct) < thresh:
            return
        bit = extra.strip()
        lines.append(
            f"{label}: {pct:+.1f} % (práh ±{thresh:.1f} %)"
            + (f" · {bit}" if bit else "")
        )

    cu = (data.get("ccmn") or {}).get("copper")
    al = (data.get("ccmn") or {}).get("aluminum")
    prev = ccmn_prev or {}
    extra_cu = f"{cu:.0f} CNY/t" if isinstance(cu, (int, float)) else ""
    extra_al = f"{al:.0f} CNY/t" if isinstance(al, (int, float)) else ""
    _move("CCMN měď vs včera", _pct_change(cu, prev.get("copper")), _ALERT_CCMN_DAY_PCT, extra_cu)
    _move("CCMN hliník vs včera", _pct_change(al, prev.get("aluminum")), _ALERT_CCMN_DAY_PCT, extra_al)
    hg = (data.get("yf_spot") or {}).get("HG=F") or {}
    hg_extra = f"{hg.get('price')} USD/lb" if hg.get("price") is not None else ""
    _move("Měď COMEX (HG=F) den", _yf_pct(data, "HG=F"), _ALERT_METAL_DAY_PCT, hg_extra)
    ali = (data.get("yf_spot") or {}).get("ALI=F") or {}
    ali_extra = f"{ali.get('price')} USD" if ali.get("price") is not None else ""
    _move("Hliník COMEX (ALI=F) den", _yf_pct(data, "ALI=F"), _ALERT_METAL_DAY_PCT, ali_extra)
    brent = (data.get("yf_spot") or {}).get("BZ=F") or {}
    brent_px = brent.get("price")
    brent_extra = f"${brent_px:.2f}" if isinstance(brent_px, (int, float)) else ""
    _move("Brent den", _yf_pct(data, "BZ=F"), _ALERT_BRENT_DAY_PCT, brent_extra)
    _move("EUR/CZK den", _yf_pct(data, "EURCZK=X"), _ALERT_EURCZK_DAY_PCT)
    return lines


def _alert_signature(alerts):
    day = datetime.now().strftime("%Y-%m-%d")
    return day + "|" + "|".join(sorted(alerts))


def _alert_body(alerts):
    ts = datetime.now().strftime("%d.%m.%Y %H:%M")
    return "\n".join([
        f"pbcable datový robot · {ts}",
        "",
        *alerts,
        "",
        "Dashboard: https://pbcable.streamlit.app/",
        "Měď LME Cash je na Westmetallu v appce; tady COMEX + CCMN + Brent.",
    ])


def _send_telegram(text):
    token = (os.environ.get("TELEGRAM_BOT_TOKEN") or os.environ.get("ALERT_TELEGRAM_TOKEN") or "").strip()
    chat = (os.environ.get("TELEGRAM_CHAT_ID") or os.environ.get("ALERT_TELEGRAM_CHAT") or "").strip()
    if not token or not chat:
        return False
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat, "text": text[:4000], "disable_web_page_preview": True},
            timeout=20,
        )
        if r.status_code >= 300:
            print(f"Telegram HTTP {r.status_code}: {r.text[:200]}")
            return False
        print("Telegram alert odeslan.")
        return True
    except Exception as e:
        print(f"Telegram chyba: {e}")
        return False


def _send_email(subject, body):
    host = (os.environ.get("ALERT_SMTP_HOST") or "").strip()
    to_addr = (os.environ.get("ALERT_EMAIL_TO") or "").strip()
    if not host or not to_addr:
        return False
    port = int(os.environ.get("ALERT_SMTP_PORT") or "587")
    user = (os.environ.get("ALERT_SMTP_USER") or "").strip()
    password = os.environ.get("ALERT_SMTP_PASSWORD") or ""
    from_addr = (os.environ.get("ALERT_EMAIL_FROM") or user or "robot@pbcable").strip()
    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = from_addr
    msg["To"] = to_addr
    try:
        with smtplib.SMTP(host, port, timeout=25) as smtp:
            smtp.ehlo()
            try:
                smtp.starttls()
                smtp.ehlo()
            except Exception:
                pass
            if user:
                smtp.login(user, password)
            smtp.sendmail(
                from_addr,
                [addr.strip() for addr in to_addr.split(",") if addr.strip()],
                msg.as_string(),
            )
        print("E-mail alert odeslan.")
        return True
    except Exception as e:
        print(f"E-mail chyba: {e}")
        return False


def _dispatch_alerts(alerts):
    body = _alert_body(alerts)
    print("ALERT:\n" + body)
    sent = _send_telegram(body)
    subject = "pbcable robot: " + (alerts[0][:80] if alerts else "upozornění")
    sent = _send_email(subject, body) or sent
    if not sent:
        print(
            "Alert neodeslan — v GitHub Actions Secrets nastavte TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID "
            "nebo ALERT_SMTP_HOST + ALERT_EMAIL_TO."
        )


def main():
    print("Startuji datoveho robota...")
    data = {"ccmn": {}, "yf_spot": {}, "_ts": datetime.now().strftime("%Y-%m-%d %H:%M")}

    print("Stahuji CCMN (Čína)...")
    data["ccmn"]["copper"] = fetch_ccmn_price("copper")
    data["ccmn"]["aluminum"] = fetch_ccmn_price("aluminum")

    print("Stahuji Yahoo Spot ceny...")
    for t in ["HRC=F", "STRE=F", "BZ=F", "CL=F", "EURUSD=X", "EURCZK=X", "HG=F", "ALI=F"]:
        try:
            hist = yf.Ticker(t).history(period="1mo").dropna(subset=["Close"])
            if not hist.empty:
                price = float(hist["Close"].iloc[-1])
                prev = float(hist["Close"].iloc[-2]) if len(hist) > 1 else price
                data["yf_spot"][t] = {
                    "price": round(price, 6), "prev": round(prev, 6),
                    "delta": round(price - prev, 6),
                    "delta_pct": round((price - prev) / prev * 100, 3) if prev else 0
                }
        except: pass

    print("Ukládám denní CCMN historii (append)...")
    today = datetime.now().strftime("%Y-%m-%d")
    cu, al = data["ccmn"]["copper"], data["ccmn"]["aluminum"]
    ccmn_prev = {"copper": None, "aluminum": None}
    try:
        ccmn_hist = pd.read_csv("ccmn_history.csv", dtype={"Date": str})
    except FileNotFoundError:
        ccmn_hist = pd.DataFrame(columns=["Date", "CCMN_Cu", "CCMN_Al"])
    older = ccmn_hist[ccmn_hist["Date"] != today] if not ccmn_hist.empty else ccmn_hist
    if older is not None and not older.empty:
        last = older.sort_values("Date").iloc[-1]
        if pd.notna(last.get("CCMN_Cu")):
            ccmn_prev["copper"] = float(last["CCMN_Cu"])
        if pd.notna(last.get("CCMN_Al")):
            ccmn_prev["aluminum"] = float(last["CCMN_Al"])
    if cu is not None or al is not None:
        ccmn_hist = ccmn_hist[ccmn_hist["Date"] != today]
        new_row = pd.DataFrame([{"Date": today, "CCMN_Cu": cu, "CCMN_Al": al}])
        ccmn_hist = pd.concat([ccmn_hist, new_row], ignore_index=True)
        ccmn_hist.sort_values("Date").to_csv("ccmn_history.csv", index=False)
        print(f"CCMN historie: {len(ccmn_hist)} zaznamu.")
    else:
        print("CCMN ceny nedostupne - historie beze zmeny.")

    print("Stahuji Yahoo Historii (1 rok)...")
    hist_tickers = ["HRC=F", "STRE=F", "BZ=F", "EURUSD=X", "USDCZK=X", "EURCZK=X", "CNYUSD=X", "CNYCZK=X", "HG=F", "ALI=F"]
    hist_dict = {}
    for t in hist_tickers:
        try:
            h = yf.Ticker(t).history(period="1y").dropna(subset=["Close"])
            if not h.empty:
                h.index = h.index.tz_localize(None)
                hist_dict[t] = h["Close"]
        except: pass

    if hist_dict:
        df = pd.DataFrame(hist_dict)
        df.index.name = "Date"
        df.to_csv("robot_history.csv")

    health = {
        "ccmn_copper": data["ccmn"].get("copper") is not None,
        "ccmn_aluminum": data["ccmn"].get("aluminum") is not None,
        "brent": "BZ=F" in data["yf_spot"],
        "eurusd": "EURUSD=X" in data["yf_spot"],
        "history": bool(hist_dict),
    }
    data["_health"] = health
    prev = _load_prev_robot()
    alerts = _collect_alerts(data, ccmn_prev)
    data["_alert_sig"] = _alert_signature(alerts)
    with open("robot_data.json", "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

    if alerts and data["_alert_sig"] != (prev or {}).get("_alert_sig"):
        _dispatch_alerts(alerts)
    elif alerts:
        print("Stejne alerty uz odeslane, preskakuji.")
    else:
        print("Zadne alerty.")

    failed = [k for k, ok in health.items() if not ok]
    if failed:
        print("ALERT vypadek zdroju:", ", ".join(failed))
        sys.exit(1)

    print("Hotovo! Data a historie uložena.")

if __name__ == "__main__":
    main()
