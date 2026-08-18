"""Jednoduchý CZ/EN překlad UI. Český text je klíč, angličtina v EN."""

from __future__ import annotations

import streamlit as st

_LANG_KEY = "ui_lang"
_WIDGET_KEY = "ui_lang_seg"

EN: dict[str, str] = {
    # Login
    "🔒 Přístup k dashboardu": "🔒 Dashboard access",
    "Přihlaste se tajným odkazem (`?key=…`) nebo zadejte přístupové heslo.":
        "Sign in with the secret link (`?key=…`) or enter the access password.",
    "Heslo / přístupový klíč": "Password / access key",
    "Zadejte APP_KEY": "Enter access key",
    "Přihlásit se": "Sign in",
    "Neplatné heslo. Přístup odepřen.": "Invalid password. Access denied.",
    "Parametr `key` v adrese URL není platný.": "The `key` parameter in the URL is not valid.",
    "Chybí nebo je neplatné nastavení **APP_KEY** v Streamlit secrets "
    "(soubor `.streamlit/secrets.toml` lokálně nebo Secrets ve Streamlit Cloud).":
        "Missing or invalid **APP_KEY** in Streamlit secrets "
        "(`.streamlit/secrets.toml` locally, or Secrets on Streamlit Cloud).",
    # Header / chrome
    "Kabelářský dashboard": "Cable dashboard",
    "Poslední aktualizace": "Last update",
    "🔄  Obnovit data": "🔄  Refresh data",
    "Data se automaticky obnovují každou hodinu · "
    "Všechny ceny jsou orientační · Žádné placené API":
        "Data refresh automatically every hour · "
        "All prices are indicative · No paid APIs",
    "Zobrazovací měna": "Display currency",
    "Období grafů": "Chart period",
    "nedostupný": "unavailable",
    "Přepočet na EUR není k dispozici — chybí živý kurz EUR/USD z Yahoo Finance. "
    "Ceny v EUR se zobrazí jako N/A.":
        "EUR conversion is unavailable — live EUR/USD from Yahoo Finance is missing. "
        "EUR prices will show as N/A.",
    "💾 Export dat pro analýzu": "💾 Data export",
    "Aktuální ceny kovů, kurzy ČNB, EUR/USD a RSI v jednom řádku. "
    "Soubor se generuje při každém stažení — na serveru se neukládá.":
        "Current metal prices, CNB FX, EUR/USD and RSI in one row. "
        "The file is generated on each download — nothing is stored on the server.",
    "Data pro export nejsou k dispozici.": "Export data are not available.",
    "⬇️ Stáhnout CSV": "⬇️ Download CSV",
    # Tabs
    "🔩 Kovy & Trh": "🔩 Metals & Market",
    "💱 Měnové kurzy": "💱 FX rates",
    "🛢️ Plasty & Ropa": "🛢️ Plastics & Oil",
    "🚢 Nákup a landed costs": "🚢 Purchasing & landed costs",
    "📍 Kontejnery na cestě": "📍 Containers in transit",
    "🚛 Logistika ČR & SK": "🚛 CZ & SK logistics",
    "🧰 Nástroje & tipy": "🧰 Tools & tips",
    # Briefing
    "Ranní briefing": "Morning briefing",
    "zdroj v chybě": "source error",
    "zdroj varování": "source warning",
    "zdroje OK": "sources OK",
    "pohyb trhu": "market move",
    "Měď LME": "Copper LME",
    "Hliník LME": "Aluminium LME",
    "Čína vs LME": "China vs LME",
    "CCMN měď vs LME": "CCMN copper vs LME",
    "Zdroje v pořádku": "Sources OK",
    "Jen veřejné trhy (LME, CCMN, ČNB, Yahoo). Interní nákupy a zásilky sem nepatří.":
        "Public markets only (LME, CCMN, CNB, Yahoo). Internal purchases and shipments do not belong here.",
    # Sections
    "Metaly — LME & Čína (CCMN)": "Metals — LME & China (CCMN)",
    "Měnové Kurzy — ČNB & Křížové": "FX rates — CNB & crosses",
    "Ropa & Plasty — Proxy Model": "Oil & plastics — proxy model",
    "Kontejnery na cestě (GPS tracking)": "Containers in transit (GPS tracking)",
    "Logistika ČR & SK — Kalkulačka přepravy": "CZ & SK logistics — freight calculator",
    "Nástroje & tipy": "Tools & tips",
    "Fill factor — průřez vodiče z průměru": "Fill factor — conductor cross-section from diameter",
    "Kapacita bubnu — co se vejde na buben": "Drum capacity — what fits on a drum",
    "Technické tabulky HELUKABEL (katalog)": "HELUKABEL technical tables (catalogue)",
    "Nástroj": "Tool",
    "Praktické kalkulačky a tipy pro <strong>sklad</strong>, <strong>nákup</strong> "
    "i běžný provoz. Postupně sem přidáme další nástroje — vyber si aktuální funkci níže.":
        "Practical calculators and tips for <strong>warehouse</strong>, <strong>purchasing</strong> "
        "and day-to-day operations. More tools will be added — pick a function below.",
    "Seznam se bude rozšiřovat o další kalkulačky a tipy.":
        "The list will grow with more calculators and tips.",
    "🚢 Logistika a Prodejní ceny": "🚢 Logistics and sales prices",
    "Měď (Cu)": "Copper (Cu)",
    "Hliník (Al)": "Aluminium (Al)",
    "Měď": "Copper",
    "Hliník": "Aluminium",
    "Americký dolar": "US dollar",
    "Čínský jüan": "Chinese yuan",
    "Data nedostupná": "Data unavailable",
    "Data nedostupná · ČNB": "Data unavailable · CNB",
    "Kurz nedostupný": "Rate unavailable",
    "Graf nelze vykreslit": "Chart cannot be rendered",
    # GPS
    "Přidejte zásilku (jméno kontejneru, číslo vydané objednávky, odkaz GPS). "
    "Údaje lze později upravit. Zůstane tu, dokud kontejner sami nesmažete. "
    "Expedice = první GPS signál (vložení trackeru do kontejneru). "
    "Všechny aktivní kontejnery jsou v jedné mapě. ":
        "Add a shipment (container name, issued PO number, GPS link). "
        "You can edit the details later. It stays until you delete the container. "
        "Dispatch = first GPS signal (tracker placed in the container). "
        "All active containers are on one map. ",
    "Poloha se obnovuje max. jednou za {mins} min. "
    "Většina bodů je LBS (buňka), ne satelit.":
        "Position refreshes at most once every {mins} min. "
        "Most points are LBS (cell), not satellite.",
    "Jméno kontejneru": "Container name",
    "Číslo vydané objednávky": "Issued PO number",
    "Odkaz GPS / IMEI": "GPS link / IMEI",
    "např. 26VO00238": "e.g. 26VO00238",
    "Stejný veřejný odkaz jako doteď — mění se jen koncovka ?devNo=":
        "The same public link as before — only the ?devNo= suffix changes.",
    "Přidat GPS": "Add GPS",
    "Kontejner je v seznamu.": "Container is on the list.",
    "Aktivní zásilky": "Active shipments",
    "Upravit": "Edit",
    "Smazat": "Delete",
    "Uložit": "Save",
    "Zrušit": "Cancel",
    "Údaje uloženy.": "Details saved.",
    "Obnovit GPS": "Refresh GPS",
    "Seznam je prázdný. Přidejte první kontejner formulářem výše.":
        "The list is empty. Add the first container with the form above.",
    "Živá poloha teď není dostupná (API Link4Future neodpovědělo).":
        "Live position is unavailable right now (Link4Future API did not respond).",
    "Nepodařilo se načíst: ": "Could not load: ",
    "Stahuji polohu z Link4Future…": "Fetching position from Link4Future…",
    "Vložte odkaz z Link4Future (nebo číslo ?devNo=).":
        "Paste the Link4Future link (or the ?devNo= number).",
    "Vyplňte jméno kontejneru.": "Enter the container name.",
    "Tento GPS odkaz už má jiný kontejner v seznamu.":
        "This GPS link is already used by another container on the list.",
    "Kontejner v seznamu už není.": "That container is no longer on the list.",
    "LBS (buňka)": "LBS (cell)",
    "GPS (satelit)": "GPS (satellite)",
    "Expedice ": "Dispatch ",
    "Expedice (1. signál): ": "Dispatch (1st signal): ",
    "baterie": "battery",
    "bodů": "points",
    # Landed
    "Faktura s více řádky · proporční doprava a deklarace · clo dle HS / Aplikované clo (%) · "
    "kurz <strong>ČNB EUR/CZK</strong>":
        "Multi-line invoice · proportional freight and declaration · duty by HS / Applied duty (%) · "
        "<strong>CNB EUR/CZK</strong> rate",
    "Turecko (A.TR) vynutí clo <strong>0 %</strong> na všech řádcích":
        "Turkey (A.TR) forces <strong>0 %</strong> duty on all lines",
    "Kurz EUR/CZK z ČNB není k dispozici — landed cost nelze spočítat.":
        "CNB EUR/CZK is unavailable — landed cost cannot be calculated.",
    "Trasa": "Route",
    "Cena dopravy (EUR)": "Freight cost (EUR)",
    "Poplatek za celní deklaraci a JSD (CZK)": "Customs declaration + JSD fee (CZK)",
    "🇹🇷 Turecko: u všech řádků se použije clo **0 %** (A.TR).":
        "🇹🇷 Turkey: **0 %** duty is applied on all lines (A.TR).",
    "Import dat z Pohody": "Import data from Pohoda",
    "🇹🇷 Aplikovat nulové clo (Zboží z Turecka s certifikátem A.TR)":
        "🇹🇷 Apply zero duty (goods from Turkey with A.TR certificate)",
    "Nahrát exportní soubor (CSV nebo Excel z Pohody)":
        "Upload export file (CSV or Excel from Pohoda)",
    "🇨🇳 Čína": "🇨🇳 China",
    "🇹🇷 Turecko": "🇹🇷 Turkey",
    # Domestic logistics
    "Vyhledejte <strong>start</strong> a <strong>cíl</strong> v <strong>ČR nebo na Slovensku</strong> "
    "(Košice, Senec, Bratislava, …) · silniční trasa OSRM včetně přeshraniční · "
    "záloha vzdálenosti: vzdušná × 1,3 · cena v CZK i EUR (ČNB) · "
    "poptávka pro dopravce ke stažení":
        "Search <strong>origin</strong> and <strong>destination</strong> in the "
        "<strong>Czech Republic or Slovakia</strong> "
        "(Košice, Senec, Bratislava, …) · OSRM road route including cross-border · "
        "distance fallback: great-circle × 1.3 · price in CZK and EUR (CNB) · "
        "downloadable carrier RFQ",
    "Odkud (Start)": "From (origin)",
    "Kam (Cíl)": "To (destination)",
    # Footer
    "Kabelářský Nákupní Dashboard": "Cable procurement dashboard",
    "Zdroje: westmetall.com (LME Cash) &nbsp;·&nbsp; ČNB &nbsp;·&nbsp; "
    "Yahoo Finance (grafy, ropa BZ=F) &nbsp;·&nbsp; Link4Future (GPS kontejnerů)":
        "Sources: westmetall.com (LME Cash) &nbsp;·&nbsp; CNB &nbsp;·&nbsp; "
        "Yahoo Finance (charts, Brent BZ=F) &nbsp;·&nbsp; Link4Future (container GPS)",
    "Generováno:": "Generated:",
    "Bez placených API klíčů": "No paid API keys",
    "Bez SQL databází": "No SQL databases",
    "⚠️ Veškeré ceny a výpočty jsou orientační. Neslouží jako investiční poradenství. "
    "Data jsou stahována z veřejně dostupných zdrojů a mohou se zpozdit nebo být nepřesná.":
        "⚠️ All prices and calculations are indicative. This is not investment advice. "
        "Data are pulled from public sources and may be delayed or inaccurate.",
    # Metals / FX warnings
    "Westmetall: LME data se nepodařilo stáhnout — ceny mědi a hliníku nejsou k dispozici.":
        "Westmetall: LME data could not be downloaded — copper and aluminium prices are unavailable.",
    "ČNB: kurzovní lístek se nepodařilo načíst — karty CZK párů budou nedostupné.":
        "CNB: the daily FX list could not be loaded — CZK pair cards will be unavailable.",
    "ČNB: v denním kurzovním lístku chybí kód CNY — kurz CNY/CZK nelze zobrazit.":
        "CNB: CNY is missing from the daily FX list — CNY/CZK cannot be shown.",
    "Brent (BZ=F): Yahoo Finance nevrátilo živou cenu — data nedostupná.":
        "Brent (BZ=F): Yahoo Finance did not return a live price — data unavailable.",
    "Chyba načítání dat z Westmetallu": "Error loading data from Westmetall",
    "Soubor robot_history.csv nenalezen — spusťte datového robota (GitHub Actions).":
        "robot_history.csv not found — run the data robot (GitHub Actions).",
    "LME Cash, zásoby &amp; historie měď/hliník: <strong>Westmetall</strong> · "
    "Kurzy CZK: <strong>ČNB</strong> · ostatní grafy: <strong>Yahoo</strong>":
        "LME Cash, stocks &amp; copper/aluminium history: <strong>Westmetall</strong> · "
        "CZK rates: <strong>CNB</strong> · other charts: <strong>Yahoo</strong>",
    "Karty CZK párů: oficiální kurzovní lístek <strong>ČNB</strong>":
        "CZK pair cards: official <strong>CNB</strong> FX list",
    "Historické grafy ({period}), křížové kurzy a 30denní sparkliny: <strong>Yahoo Finance</strong> · "
    "CNY/CZK graf: CNYCZK=X nebo odvozeno USDCZK×CNYUSD":
        "History charts ({period}), crosses and 30-day sparklines: <strong>Yahoo Finance</strong> · "
        "CNY/CZK chart: CNYCZK=X or derived USDCZK×CNYUSD",
    "ze dne {date}": "as of {date}",
    "Historické grafy — Měď & Hliník (Westmetall, {period})":
        "History charts — Copper & Aluminium (Westmetall, {period})",
    "Westmetall LME Cash &amp; skladové zásoby · Načteno:":
        "Westmetall LME Cash &amp; warehouse stocks · Loaded:",
    "Modul `helukabel_tables.py` není nasazený. "
    "Nahraj ho do kořene repozitáře na GitHub (vedle `app.py`) "
    "a ideálně i složku `assets/helukabel/` se skeny.":
        "Module `helukabel_tables.py` is not deployed. "
        "Upload it to the repo root on GitHub (next to `app.py`) "
        "and ideally the `assets/helukabel/` folder with scans.",
    "📗 Technické tabulky HELUKABEL": "📗 HELUKABEL technical tables",
    "Hledat v katalogu": "Search the catalogue",
    "Nalezené položky": "Matching items",
    "Nic nenalezeno — zkus kratší slovo (ohyb, proud, NYY, PE…).":
        "Nothing found — try a shorter word (bend, current, NYY, PE…).",
    "Tabulky a skeny katalogu zůstávají v originále (DE/CZ).":
        "Catalogue tables and scans stay in the original language (DE/CZ).",
}


def get_lang() -> str:
    return st.session_state.get(_LANG_KEY, "cs")


def init_lang() -> None:
    """Jazyk z ?lang=en / session. Výchozí čeština."""
    qp = st.query_params.get("lang")
    if isinstance(qp, list):
        qp = qp[0] if qp else None
    if qp in ("cs", "en"):
        st.session_state[_LANG_KEY] = qp
    else:
        st.session_state.setdefault(_LANG_KEY, "cs")
    if _WIDGET_KEY not in st.session_state:
        st.session_state[_WIDGET_KEY] = "EN" if get_lang() == "en" else "CZ"


def t(text: str, **kwargs) -> str:
    """Vrátí text v aktuálním jazyce. Neznámé řetězce zůstanou česky."""
    out = text
    if get_lang() == "en":
        out = EN.get(text, text)
    if kwargs:
        try:
            return out.format(**kwargs)
        except (KeyError, IndexError, ValueError):
            return out
    return out


def render_lang_switcher() -> None:
    """Přepínač CZ / EN — uloží se do session i do ?lang=."""
    init_lang()
    picked = st.segmented_control(
        "Language",
        options=["CZ", "EN"],
        key=_WIDGET_KEY,
        label_visibility="collapsed",
    )
    new_lang = "en" if picked == "EN" else "cs"
    if new_lang != get_lang():
        st.session_state[_LANG_KEY] = new_lang
        st.query_params["lang"] = new_lang
        st.rerun()
