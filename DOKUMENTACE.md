# Kabelářský nákupní dashboard — technická specifikace a datová architektura

**Soubor aplikace:** `app.py` (v2.0.0)  
**Stack:** Streamlit · Pandas · Plotly · BeautifulSoup4 · lxml · requests · yfinance  
**Cache:** `@st.cache_data(ttl=3600)` u většiny síťových fetch funkcí (`CACHE_TTL = 3600` s)

---

## Základní pravidlo: žádná vymyšlená data

Aplikace **nepoužívá mock data ani numerické zálohy** pro tržní ceny kovů, kurzy, ropu ani spot CCMN. Pokud zdroj selže, UI zobrazí **N/A**, prázdný graf, `error-box` / `st.warning` / `st.error` — nikoli odhadnutou cenu.

Co **není** považováno za „falešná data“:

- **Alternativní reálný zdroj** stejného typu (např. ticker `STRE=F`, pokud `HRC=F` z Yahoo nevrátí data; subdomény `copper.ccmn.cn` / `alu.ccmn.cn`, pokud homepage `www.ccmn.cn` nemá tabulku).
- **Odvozené hodnoty z reálných vstupů** (USD/CNY z ČNB; CNY/CZK z `USDCZK=X` × `CNYUSD=X`, pokud chybí `CNYCZK=X`; přepočet HRC z USD/short ton na USD/t).
- **Proxy model plastů** — explicitně označený odhad z **živé** ceny Brent (`BZ=F`), ne náhrada LME/CCMN.
- **Manuální režim** v kalkulačce Metal Surcharge — uživatelský vstup, ne automatický feed.
- **Lokální CSV bubnů** — reálný katalog TP KBB 3 (soubor musí existovat v adresáři aplikace).
- **Odhad vzdálenosti** při výpadku OSRM — Haversine × 1,3 (geometrie, ne cena komodity).

---

## Přehled modulů (záložky)

| Záložka | Funkce | Hlavní zdroje dat |
|--------|--------|-------------------|
| Kovy & Trh | `render_metals()` | Westmetall, ccmn.cn, Yahoo HRC, ČNB |
| Měnové kurzy | `render_fx()` | ČNB `denni_kurz.txt`, Yahoo FX |
| Plasty & Ropa | `render_oil_plastics()` | Yahoo `BZ=F`, `CL=F`, proxy model |
| Nákup & Logistika (admin) | `render_landed_cost_pricing()`, `render_logistics()` | Uživatelská faktura + ČNB |
| Logistika ČR & SK | `render_domestic_logistics()` | Nominatim, OSRM, ČNB |
| Plánování nakládky | `render_cargo_visualization()` | CSV TP KBB 3 |
| Souhrnný přehled | `render_summary_table()` | Agregace živých fetchů |

Přístup: `APP_KEY` / `SUPPLIER_KEY` ze `.streamlit/secrets.toml`.

---

## 1. Zdroje dat pro kovy (live i historie)

### 1.1 LME Cash (měď, hliník) — live

- **URL:** `https://www.westmetall.com/en/markdaten.php`
- **Funkce:** `fetch_westmetall()`
- **Parsování:**
  - HTML tabulka; stavové příznaky sekcí: `in_official_prices` (řádek obsahuje „official lme“ + „price“), poté `in_lme_stocks`.
  - Pro každý kov se hledají odkazy `<a href="...field=...">` s přesným parametrem:
    - Měď: `field=LME_Cu_cash` → klíč `copper`
    - Hliník: `field=LME_Al_cash` → klíč `aluminum`
  - Text odkazu se parsuje funkcí `_parse_westmetall_price()` (podpora formátů `13,545.00` i `391,900`).
  - **Validace rozsahu** (ochrana proti špatnému poli): měď 4 000–25 000 USD/t, hliník 1 500–8 000 USD/t.
  - Uložená hodnota: `result[metal]["price"]` v **USD/t**, `unit: "USD/t"`.
- **Zobrazení v UI:** `resolve_metal_price()` — výhradně Westmetall, bez náhradní ceny.
- **Při selhání:** karta kovu `error_card` „Data nedostupná · Westmetall“.

Konstanty: `_WESTMETALL_LME_FIELDS`.

### 1.2 LME zásoby (tuny) — live

- **Stejná stránka** `markdaten.php`, sekce **LME Stocks** (`in_lme_stocks`).
- Odkazy opět s `field=LME_Cu_cash` / `field=LME_Al_cash`, ale v kontextu řádku zásob (label „Copper“ / „Aluminium“).
- **Validace:** měď 5 000–2 000 000 t, hliník 5 000–1 500 000 t.
- Uložení: `copper_stock` / `aluminum_stock` → `tons` (integer), `unit: "t"`.
- **UI:** `wm_stock_extra()` na metrických kartách („LME zásoby: X t“).

Konstanty: `_WESTMETALL_STOCK_FIELDS`.

### 1.3 LME historie (měď, hliník)

- **URL:**
  - Měď: `https://www.westmetall.com/en/markdaten.php?action=table&field=LME_Cu_cash`
  - Hliník: `https://www.westmetall.com/en/markdaten.php?action=table&field=LME_Al_cash`
- **Funkce:** `fetch_westmetall_history(url)` → DataFrame sloupce `Date`, `Close` (USD/t), `Stock` (tuny, volitelně ze 4. sloupce tabulky).
- **Filtrování období:** `filter_wm_history_by_period()` / globální přepínač `_WM_PERIOD_DAYS` (5d→7 dní, 1mo→31, 3mo→92, 6mo→183, 1y→365).
- **Grafy:** `_render_wm_metal_history_chart()` — dual axis cena + zásoby, přepočet do EUR přes `apply_currency_to_df()` pokud je zvolena měna EUR a existuje `get_eurusd_rate()`.
- **Při selhání:** `st.warning` + `error-box` „Chyba načítání dat z Westmetallu“.

### 1.4 Čína spot (CCMN) — pouze live

- **Funkce:** `fetch_ccmn_spot(metal)` — jediný zdroj čínské strany spreadu (`get_shfe_china_usd()`).
- **Cílové texty v HTML:**
  - Měď: `1#铜`
  - Hliník: `A00铝`
- **Pořadí URL:**
  1. `https://www.ccmn.cn/`
  2. Záložní reálná stránka sítě CCMN: `https://copper.ccmn.cn/` (měď) nebo `https://alu.ccmn.cn/` (hliník)

**Metoda A — tabulka `tr`/`td` (podle struktury ccmn):**

- Najít buňku, kde `get_text(strip=True) == target` (tagy `td`, `a`, `span`).
- Rodič `tr`, sloupce `td`: index **2** = průměrná cena (均价).
- Cena: `float(re.sub(r"[^\d.]", "", avg_price_str))`.

**Metoda B — bloky spotových cen (aktuální layout subdomén):**

- `div.content1-text-div`, vpravo `span.right` s přesným textem `1#铜` / `A00铝`.
- Cena ve `span.up_down_span` (regex čísla s čárkami tisíců).
- **Priorita regionu:** nejdřív řádek obsahující **长江综合**, jinak **上海地区**, jinak první nalezený blok.

**Výstup:** `{ price, unit: "CNY/t", ticker: "CCMN (...)", source: "ccmn.cn" }` nebo `None`.

**Přepočet na USD/t (spread, tabulka LME vs CCMN):**

```text
USD/t = cena_CNY/t × get_usd_per_cny()
get_usd_per_cny() = rate_CNY_CZK / rate_USD_CZK   (z ČNB, viz sekce 2)
```

- **Při selhání:** spread karta / tabulka N/A, chybová hláška „ccmn.cn (spot) nebo kurz CNY (ČNB)“.

> **Poznámka:** Historická korelace LME vs SHFE/CCMN (Nasdaq CHRIS) byla z aplikace **odstraněna**. Zůstává jen živý spot.

### 1.5 Ocel HRC — live a historie

- **Tickery Yahoo (CME):** `HRC=F` (primární), `STRE=F` (záložní série, pokud první ticker nevrátí historii).
- **Funkce:** `fetch_steel_yfinance()` → `fetch_steel_ticker()`.
- **Jednotka na burze:** USD / short ton → přepočet na **USD/t**:

```text
_ST_TON_FACTOR = 2204.623 / 2000.0   # kg v short tonu / kg v metrické tuně
cena_USD_t = cena_USD_short_ton × _ST_TON_FACTOR
```

- **Historie grafu:** `fetch_metal_history(ticker)` → `_yf_history()` (období 1 rok) + `filter_history_by_period()`.
- **Ocel Scrap:** v aktuální verzi **není implementována** (dříve `BUS=F` bylo odstraněno). Dashboard zobrazuje pouze **HRC** ve sloupci oceli.

### 1.6 Agregace v sekci kovy

- **3 metrické karty:** měď, hliník (LME), ocel HRC (Yahoo).
- **Spread:** `_render_shfe_spreads()` — CCMN (Čína) vs LME, badge `ccmn.cn (Spot)`.
- **Spotové porovnání:** `_render_lme_shfe_spot_comparison()` + `lme_shfe_spot_comparison_figure()` — pouze řádky, kde existují **obě** live ceny.
- **RSI:** viz sekce 5 (Westmetall historie / Yahoo HRC).

---

## 2. Měnové kurzy (FX)

### 2.1 ČNB — denní kurzovní lístek

- **URL:**

```text
https://www.cnb.cz/cs/financni-trhy/devizovy-trh/
kurzy-devizoveho-trhu/kurzy-devizoveho-trhu/denni_kurz.txt
```

- **Funkce:** `fetch_cnb_rates()`
- **Formát:** řádek 0 = datum (`dd.mm.yyyy`), od řádku 2: `Země|Měna|Množství|Kód|Kurz`
- **Normalizace:** `rate = kurz / množství` → **CZK za 1 jednotku cizí měny**
- **Výstup:** `{ "USD": { rate, amount, currency, country }, "EUR": {...}, "CNY": {...}, "_date", "_ts" }` nebo `None`

**Karty v UI (`_CNB_METRIC_CARDS`):**

- USD/CZK, EUR/CZK, CNY/CZK — přímo z ČNB.

### 2.2 USD/CNY (pro CCMN a kalkulačky)

```text
get_usd_per_cny() = rate_CNY / rate_USD
```

kde `rate_*` jsou CZK za 1 USD resp. 1 CNY z ČNB.  
Interpretace: **kolik USD stojí 1 CNY** (přepočet CNY/t → USD/t).

**Při chybě ČNB:** spread CCMN, `get_shfe_china_usd()` a části kalkulaček vrací N/A / warning.

### 2.3 Yahoo Finance — křížové kurzy a historie

| Účel | Ticker(y) | Funkce |
|------|-----------|--------|
| EUR/USD spot | `EURUSD=X` | `fetch_yf_spot()`, `get_eurusd_rate()` |
| EUR/CZK historie | `EURCZK=X` | `fetch_fx_history()` |
| USD/CZK historie | `USDCZK=X` | `fetch_fx_history()` |
| EUR/USD historie | `EURUSD=X` | `fetch_fx_history()` |
| USD/EUR v UI | inverze `1 / Close` z EURUSD | `render_fx()` |
| CNY/CZK historie | `CNYCZK=X`, nebo `USDCZK=X` ⨯ `CNYUSD=X` | `fetch_cny_czk_history()` |

- Spot: poslední vs. předposlední `Close` (delta).
- Historie: `_yf_history()` → 1 rok, ořez `filter_history_by_period()`.
- **Zobrazení kovů/ropy v EUR:** `usd_to_display()` a `apply_currency_to_df()` dělí USD hodnoty kurzem `EURUSD=X`.

**Při selhání Yahoo:** `error_card` / „Graf … data nedostupná (Yahoo)“ — bez náhradního kurzu.

---

## 3. Logika výpočtů (business logic)

### 3.1 Metal Surcharge (`render_metal_surcharge_calculator`)

**Vstupy:**

- Kov: měď / hliník (`_SURCHARGE_METAL_OPTIONS`)
- `kg_per_km` — hmotnost kovu v kabelu
- `orig_total` — původní celková cena za 1 m (v měně nabídky)
- Měny: nabídka, výstup, burza (USD / CNY / EUR dle zdroje)
- Zdroj burzovní ceny: **LME (Live)** Westmetall USD/t, **SHFE (Live)** = CCMN CNY/t, nebo **Manuální**

**Kurzy:** `_build_fx_rates(cnb)` — ČNB (USD/CZK, EUR/CZK, CNY/CZK) + `eur_usd` z Yahoo + `usd_per_cny`.

**Hodnota kovu v 1 m kabelu (USD):**

```text
metal_per_m_USD = (cena_kovu_USD/t / 1000) × (kg_per_km / 1000)
```

**Dutá cena (fixní složka — práce + plasty):**

```text
hollow_USD = orig_total_USD − orig_metal_per_m_USD
```

kde `orig_metal_per_m_USD` používá **původní** burzovní cenu kovu (`orig_metal_ex`) převedenou do USD.

**Férová cena za 1 m:**

```text
fair_USD = hollow_USD + curr_metal_per_m_USD
```

`curr_metal_per_m_USD` z aktuální burzovní ceny (live LME nebo CCMN, nebo manuální).

**Srovnání s „prostou úměrou“:**

```text
metal_change_pct = (curr_metal_USD − orig_metal_USD) / orig_metal_USD
simple_total_USD = orig_total_USD × (1 + metal_change_pct)
diff_USD = fair_USD − simple_total_USD
```

**Při chybě kurzů nebo live ceny:** výpočet se zastaví (`st.error` / `st.info`), žádné dopočítání fiktivní burzou.

### 3.2 Proxy model plastů (`calc_plastic_prices`)

**Vstup:** živá cena Brent `BZ=F` (`fetch_oil_data()` → `fetch_yf_spot`).

**Rovnice (USD/t), zaokrouhleno na celé USD:**

| Materiál | Vzorec |
|----------|--------|
| PVC (kabelový granulát) | `800 + 8.5 × Brent` |
| XLPE | `1200 + 14.0 × Brent` |
| PA12 (nylonový plášť) | `2500 + 20.0 × Brent` |
| LLDPE (fólie/separátor) | `900 + 10.0 × Brent` |

- UI označuje ceny jako **orientační model** se zpožděním trhu plastů **4–8 týdnů** vůči ropě.
- Bez Brent ceny: karty plastů `error_card`, `calc_plastic_prices` vrací `None`.

**Historie ropy:** `fetch_oil_history()` → `BZ=F`, graf + **SMA 30d**: `Close.rolling(30, min_periods=1).mean()`.

### 3.3 Landed Cost — Čína → ČR (`compute_invoice_landed`)

**Vstupy uživatele:**

- Víceřádková faktura: název, množství (m), nákupní cena (EUR/m), HS nápověda, **Aplikované clo (%)**
- Celková **doprava (EUR)**
- **Poplatek celní deklarace + JSD (CZK)**
- Trasa: **Čína (FCL železnice)** nebo **Turecko (urgent truck)**

**Kurz:** `eur_czk` z ČNB — bez něj `st.error`, výpočet se neprovede.

**Hodnota řádku:**

```text
hodnota_řádku_EUR = množství_m × cena_EUR/m
```

**Proporční rozpad** (podíl na celkovou hodnotu zboží `total_goods`):

```text
podíl_i = hodnota_řádku_i / total_goods

doprava_i = podíl_i × transport_eur
deklarace_i = podíl_i × (customs_czk / eur_czk)

základ_cla_i = hodnota_řádku_i + doprava_i
clo_i = základ_cla_i × (clo_%_i / 100)
```

**Landed celkem a za metr:**

```text
landed_i = hodnota_řádku_i + doprava_i + clo_i + deklarace_i
landed_EUR/m = landed_i / množství_m
landed_CZK/m = landed_EUR/m × eur_czk
```

**Clo a HS:**

- Předvolby `_HS_CODE_OPTIONS` (např. solární kabely 3,7 %, datové 0 %, …).
- Tlačítko „Doplnit clo dle HS nápovědy“ mapuje text HS na default sazbu.
- **Turecko (A.TR):** `force_zero_duty = True` → **clo 0 % na všech řádcích**, HS sazby se ignorují.

**Prodejní ceny:**

```text
Prodej (Přirážka CZK) = landed_CZK/m × (1 + marže%/100)
Prodej (Marže CZK)     = landed_CZK/m / (1 − marže%/100)   (marže < 100 %)
```

### 3.4 Transitní čas Čína → ČR (`render_logistics`)

Fixní kalendářní model (ne API) — `TRANSIT_DAYS`:

| Doprava | Dny |
|---------|-----|
| Železniční doprava | 20 |
| Námořní doprava | 40 |
| Letecká doprava | 5 |

```text
datum_doručení = datum_odeslání + transit_days
progress = elapsed / transit_days   (omezeno 0–1)
```

---

## 4. Logistika a plánování

### 4.1 Plánovač nakládky — 2D bin packing bubnů

**Katalog:**

- Soubor: `TPKBB3_dřevěné bubny_2017.xlsx - List1.csv` (ve stejné složce jako `app.py`)
- **Funkce:** `load_and_interpolate_drums()`
- Automatická detekce sloupců (typ, průměr, šířka, váha) přes `_identify_drum_csv_columns()`
- Čísla: `_parse_czech_number()` (čárka jako desetinná oddělovač)

**Interpolace průměrů VDE 80–260 po 10 cm:**

- Rozsah: `_DRUM_DIAMETER_MIN_CM = 80` … `_DRUM_DIAMETER_MAX_CM = 260`, krok 10
- Pro každý průměr `d`: `pandas.Series(...).reindex([d]).interpolate(method="index")` pro šířku i váhu prázdného bubnu
- Klíč katalogu: `"VDE {d}"`

**Návěs:**

- Šířka **245 cm**, délka **1360 cm** (13,6 m), max. hmotnost **24 000 kg**

**Bin packing (`_pack_drums_row_wise`):**

- Skládání od čela návěsu (**Y = 0**)
- Bubny v řadě vedle sebe po ose X (šířka), dokud `row_x + šířka_bubnu ≤ 245 cm`
- Nová řada: `row_y += max_průměr_v_řadě`, `row_x = 0`
- Každá jednotka: `total_weight_kg = váha_prázdného_bubnu + váha_kabelu_kg`

**Těžiště (`_compute_cargo_center_of_gravity`):**

```text
COG_x = Σ (váha_i × (x_i + šířka_i/2)) / Σ váha_i
COG_y = Σ (váha_i × (y_i + průměr_i/2)) / Σ váha_i
```

- Doporučená zóna na ose Y: **1/3 až 1/2 délky návěsu** (viz zelený pás v Plotly půdorysu).
- Překročení hmotnosti nebo délky → `st.warning`, bez utajení přetížení.

**Při chybě CSV:** `FileNotFoundError` → `st.error` + návod umístit soubor — **žádný výchozí katalog v kódu**.

### 4.2 Logistika ČR/SK — vzdálenost a cena přepravy

**Geolokace — Nominatim**

- **URL:** `https://nominatim.openstreetmap.org/search`
- **Funkce:** `search_domestic_location(query)`
- Parametry: `countrycodes=cz,sk`, `format=json`, `addressdetails=1`, `limit=12`
- Header: `User-Agent: pbcable-dashboard`
- Rate limit: `time.sleep(1)` před dotazem
- Vrací: `lat`, `lon`, `display_name`, `postcode`, `country` (CZ/SK)

**Vzdálenost — OSRM**

- **URL:** `http://router.project-osrm.org/route/v1/driving/{lon1},{lat1};{lon2},{lat2}?overview=false`
- **Funkce:** `get_driving_distance()` → `(km, used_osrm: bool)`
- Vzdálenost: `routes[0].distance / 1000` (metry → km)

**Záložní výpočet při selhání OSRM:**

```text
km = haversine_distance(lat1, lon1, lat2, lon2) × _DOMESTIC_ROAD_FACTOR
_DOMESTIC_ROAD_FACTOR = 1.3
```

- Haversine: poloměr Země 6371 km, standardní vzorec velkého kruhu.
- UI upozorní: „Záložní odhad: vzdušná vzdálenost × 1,3 (OSRM nedostupné)“ — stále **odhad vzdálenosti**, ne fiktivní cena komodity.

**Cena přepravy:** kalkulace z reálné vzdálenosti a parametrů vozidla / LDM / palet (viz `_DOMESTIC_VEHICLE_ORDER`, minimální cena v CZK, přepočet EUR přes ČNB v UI).

---

## 5. Smart signály — RSI

**Konstanta:** `_RSI_PERIOD = 14`

**Funkce:** `calculate_rsi(df, column="Close", period=14)`

**Algoritmus (Wilder / EWM v Pandas):**

```text
delta = prices.diff()
gain  = delta.clip(lower=0)
loss  = (-delta).clip(lower=0)
avg_gain = gain.ewm(alpha=1/period, min_periods=period, adjust=False).mean()
avg_loss = loss.ewm(alpha=1/period, min_periods=period, adjust=False).mean()
RS  = avg_gain / avg_loss
RSI = 100 − (100 / (1 + RS))
```

- Pokud `avg_loss == 0` → RSI = 100
- Minimum dat: **period + 1** (= 15) bodů; jinak `None` → UI **N/A**

**Zdroje historie pro RSI:**

| Kov | Zdroj |
|-----|--------|
| Měď | `fetch_westmetall_history(WM_HISTORY_URLS["copper"])` |
| Hliník | `fetch_westmetall_history(WM_HISTORY_URLS["aluminum"])` |
| Ocel HRC | `_yf_history(ticker)` — ticker z `fetch_steel_yfinance()` |

**Hraniční interpretace (`interpret_rsi`):**

| RSI | Význam | UI |
|-----|--------|-----|
| **< 30** | Přeprodáno (potenciál růstu / zvážit nákup) | `st.success` |
| **> 70** | Překoupeno (riziko korekce / vyčkat) | `st.warning` |
| 30–70 | Neutrální zóna | `st.info` |

---

## Datový tok (zjednodušené schéma)

```mermaid
flowchart TB
  subgraph metals [Kovy]
    WM[westmetall.com]
    CCMN[ccmn.cn / copper|alu.ccmn.cn]
    YHRC[Yahoo HRC=F / STRE=F]
    CNB1[ČNB kurzy]
    WM --> LME[LME Cash + zásoby + historie]
    CCMN --> SPOT[CNY/t spot]
    CNB1 --> USD_CNY[USD per CNY]
    SPOT --> USD_CNY
    USD_CNY --> SPREAD[Spread vs LME]
    LME --> SPREAD
    YHRC --> STEEL[Ocel USD/t]
  end

  subgraph fx [FX]
    CNB2[ČNB denni_kurz.txt]
    YFX[Yahoo EURUSD EURCZK USDCZK CNYCZK]
    CNB2 --> CZK[CZK páry]
    YFX --> CROSS[Křížové + grafy]
  end

  subgraph calc [Výpočty]
    SURCH[Metal Surcharge]
    LAND[Landed Cost]
    PLAST[Proxy plasty z Brent]
    CNB2 --> LAND
    CNB2 --> SURCH
    YFX --> SURCH
    LME --> SURCH
    SPOT --> SURCH
  end
```

---

## Soubory a konfigurace

| Položka | Účel |
|---------|------|
| `app.py` | Celá aplikace |
| `.streamlit/secrets.toml` | `APP_KEY`, `SUPPLIER_KEY` |
| `TPKBB3_dřevěné bubny_2017.xlsx - List1.csv` | Katalog bubnů (povinný pro plánování nakládky) |
| `requirements.txt` | Python závislosti |

---

## Verze a omezení

- Ceny a signály jsou **orientační**, ne investiční poradenství.
- Scraping závisí na struktuře HTML Westmetall / CCMN (může se změnit).
- Yahoo a veřejné OSRM/Nominatim mohou rate-limitovat nebo být dočasně nedostupné.
- Proxy plasty a transitní dny Čína→ČR jsou **modely**, ne tržní feed — ale vždy vycházejí z reálných vstupů nebo uživatelských parametrů, nikoli z náhodných mock čísel.

*Dokumentace odpovídá stavu `app.py` po odstranění historické korelace LME vs SHFE/CCMN (Nasdaq CHRIS).*
