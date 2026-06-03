import json, requests, re, os
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

def main():
    print("Startuji datoveho robota...")
    data = {"ccmn": {}, "yf_spot": {}, "_ts": datetime.now().strftime("%Y-%m-%d %H:%M")}

    print("Stahuji CCMN (Čína)...")
    data["ccmn"]["copper"] = fetch_ccmn_price("copper")
    data["ccmn"]["aluminum"] = fetch_ccmn_price("aluminum")

    print("Stahuji Yahoo Spot ceny...")
    for t in ["HRC=F", "STRE=F", "BZ=F", "CL=F", "EURUSD=X"]:
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

    with open("robot_data.json", "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

    print("Stahuji Yahoo Historii (1 rok)...")
    hist_tickers = ["HRC=F", "STRE=F", "BZ=F", "EURUSD=X", "USDCZK=X", "EURCZK=X", "CNYUSD=X", "CNYCZK=X", "HG=F"]
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

    print("Hotovo! Data a historie uložena.")

if __name__ == "__main__":
    main()
