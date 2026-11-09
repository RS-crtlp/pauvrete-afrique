"""
Agent IA - Pauvreté en Afrique
==============================
1. Extrait les indicateurs de pauvreté de l'API de la Banque mondiale
2. Collecte les actualités récentes (Google News, Le Monde Afrique, RFI, Jeune Afrique...)
3. Rédige une analyse avec Claude (si le SDK `anthropic` et une clé API sont disponibles)
4. Écrit le tout dans web/data.json, lu par la page web

Usage :  python agent.py
"""
from __future__ import annotations

import email.utils
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).parent
OUT = ROOT / "web" / "data.json"
UA = {"User-Agent": "Mozilla/5.0 (pauvrete-afrique-agent)"}

WB = "https://api.worldbank.org/v2"

# Les 54 pays africains (codes ISO3) + nom français
PAYS = {
    "DZA": "Algérie", "AGO": "Angola", "BEN": "Bénin", "BWA": "Botswana", "BFA": "Burkina Faso",
    "BDI": "Burundi", "CPV": "Cap-Vert", "CMR": "Cameroun", "CAF": "Centrafrique", "TCD": "Tchad",
    "COM": "Comores", "COD": "RD Congo", "COG": "Congo", "CIV": "Côte d'Ivoire", "DJI": "Djibouti",
    "EGY": "Égypte", "GNQ": "Guinée équatoriale", "ERI": "Érythrée", "SWZ": "Eswatini", "ETH": "Éthiopie",
    "GAB": "Gabon", "GMB": "Gambie", "GHA": "Ghana", "GIN": "Guinée", "GNB": "Guinée-Bissau",
    "KEN": "Kenya", "LSO": "Lesotho", "LBR": "Libéria", "LBY": "Libye", "MDG": "Madagascar",
    "MWI": "Malawi", "MLI": "Mali", "MRT": "Mauritanie", "MUS": "Maurice", "MAR": "Maroc",
    "MOZ": "Mozambique", "NAM": "Namibie", "NER": "Niger", "NGA": "Nigeria", "RWA": "Rwanda",
    "STP": "Sao Tomé-et-Principe", "SEN": "Sénégal", "SYC": "Seychelles", "SLE": "Sierra Leone",
    "SOM": "Somalie", "ZAF": "Afrique du Sud", "SSD": "Soudan du Sud", "SDN": "Soudan",
    "TZA": "Tanzanie", "TGO": "Togo", "TUN": "Tunisie", "UGA": "Ouganda", "ZMB": "Zambie", "ZWE": "Zimbabwe",
}

INDICATEURS = {
    "SI.POV.DDAY": "Pauvreté extrême (< 3,00 $/jour, PPA 2021), % population",
    "SI.POV.LMIC": "Pauvreté (< 4,20 $/jour, PPA 2021), % population",
    "SI.POV.UMIC": "Pauvreté (< 8,30 $/jour, PPA 2021), % population",
    "SI.POV.NAHC": "Pauvreté selon le seuil national, % population",
    "SI.POV.GINI": "Indice de Gini",
    "SP.POP.TOTL": "Population totale",
}

FLUX_RSS = [
    # (nom affiché, url, filtrer par mots-clés ?)
    ("Google Actualités (FR)", "https://news.google.com/rss/search?q=pauvret%C3%A9+Afrique+when:30d&hl=fr&gl=FR&ceid=FR:fr", False),
    ("Google Actualités (FR)", "https://news.google.com/rss/search?q=%22Banque+mondiale%22+pauvret%C3%A9+Afrique+when:30d&hl=fr&gl=FR&ceid=FR:fr", False),
    ("Google News (EN)", "https://news.google.com/rss/search?q=poverty+Africa+when:30d&hl=en-US&gl=US&ceid=US:en", False),
    ("Le Monde Afrique", "https://www.lemonde.fr/afrique/rss_full.xml", True),
    ("RFI Afrique", "https://www.rfi.fr/fr/afrique/rss", True),
    ("Jeune Afrique", "https://www.jeuneafrique.com/feed/", True),
    ("BBC Africa", "https://feeds.bbci.co.uk/news/world/africa/rss.xml", True),
]
MOTS_CLES = re.compile(
    r"pauvr|précarit|faim|famine|insécurité alimentaire|malnutri|humanitaire|inégalit|banque mondiale|"
    r"\bpib\b|chômage|inflation|vie chère|économi|malnutrition|humanitarian|econom|"
    r"poverty|poor|hunger|famine|food insecurity|inequality|world bank|unemployment|debt|dette",
    re.I,
)


def log(msg: str) -> None:
    print(f"[{datetime.now():%H:%M:%S}] {msg}", flush=True)


def get(url: str, timeout: int = 60, essais: int = 3) -> bytes:
    req = urllib.request.Request(url, headers=UA)
    for i in range(essais):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except Exception:  # noqa: BLE001
            if i == essais - 1:
                raise
            time.sleep(2 * (i + 1))


# ---------------------------------------------------------------- Banque mondiale
def wb_series(pays: str, indicateur: str, date: str = "1990:2030") -> list[dict]:
    """Toutes les observations (pagination gérée) pour un ou plusieurs pays."""
    out, page = [], 1
    while True:
        url = f"{WB}/country/{pays}/indicator/{indicateur}?format=json&per_page=5000&date={date}&page={page}"
        reponse = json.loads(get(url))
        if len(reponse) < 2:  # message d'erreur de l'API
            raise RuntimeError(reponse)
        meta, rows = reponse[0], reponse[1]
        out += [r for r in (rows or []) if r.get("value") is not None]
        if page >= meta.get("pages", 1):
            return out
        page += 1


def collecter_banque_mondiale() -> dict:
    codes = ";".join(PAYS)
    log("Banque mondiale : séries régionales…")
    regions = {}
    for code, nom in (("SSF", "Afrique subsaharienne"), ("WLD", "Monde"), ("MEA", "Moyen-Orient & Afrique du Nord")):
        regions[code] = {"nom": nom}
        for ind in ("SI.POV.DDAY", "SI.POV.LMIC", "SI.POV.UMIC", "SP.POP.TOTL"):
            try:
                rows = wb_series(code, ind)
                regions[code][ind] = sorted(([int(r["date"]), r["value"]] for r in rows), key=lambda x: x[0])
            except Exception as e:  # noqa: BLE001
                log(f"  ! {code} {ind}: {e}")
                regions[code][ind] = []

    log("Banque mondiale : 54 pays africains…")
    pays = {c: {"nom": n} for c, n in PAYS.items()}

    def fetch(ind):
        try:
            return ind, wb_series(codes, ind)
        except Exception as e:  # noqa: BLE001
            log(f"  ! {ind}: {e}")
            return ind, []

    with ThreadPoolExecutor(6) as ex:
        for ind, rows in ex.map(fetch, INDICATEURS):
            for r in rows:
                c = r["countryiso3code"]
                if c in pays:
                    pays[c].setdefault(ind, []).append([int(r["date"]), r["value"]])
    for p in pays.values():
        for ind in INDICATEURS:
            p[ind] = sorted(p.get(ind, []), key=lambda x: x[0])

    # Nombre de pauvres (3 $/jour) en Afrique subsaharienne = taux × population
    ssf = regions["SSF"]
    pop = dict(map(tuple, ssf.get("SP.POP.TOTL", [])))
    ssf["nb_pauvres_millions"] = [[a, round(v / 100 * pop[a] / 1e6, 1)] for a, v in ssf.get("SI.POV.DDAY", []) if a in pop]
    return {"regions": regions, "pays": pays, "indicateurs": INDICATEURS}


# ---------------------------------------------------------------- Actualités
def _texte(el, tag):
    x = el.find(tag)
    return (x.text or "").strip() if x is not None and x.text else ""


def lire_flux(nom: str, url: str, filtrer: bool) -> list[dict]:
    try:
        root = ET.fromstring(get(url, 20))
    except Exception as e:  # noqa: BLE001
        log(f"  ! flux {nom}: {e}")
        return []
    items = []
    for it in root.iter("item"):
        titre = _texte(it, "title")
        desc = re.sub(r"<[^>]+>", " ", _texte(it, "description"))
        desc = re.sub(r"\s+", " ", desc).strip()
        if filtrer and not MOTS_CLES.search(f"{titre} {desc}"):
            continue
        source = _texte(it, "source") or nom
        # Google News met " - Journal" à la fin du titre
        if "news.google.com" in url and " - " in titre:
            titre = titre.rsplit(" - ", 1)[0]
        date = None
        try:
            date = email.utils.parsedate_to_datetime(_texte(it, "pubDate")).astimezone(timezone.utc).isoformat()
        except Exception:  # noqa: BLE001
            pass
        items.append({
            "titre": titre, "lien": _texte(it, "link"), "journal": source, "via": nom,
            "date": date, "resume": desc[:280] if "news.google.com" not in url else "",
        })
    log(f"  {nom}: {len(items)} articles retenus")
    return items


def collecter_actualites(max_items: int = 40) -> list[dict]:
    log("Actualités : lecture des flux RSS…")
    with ThreadPoolExecutor(8) as ex:
        lots = ex.map(lambda f: lire_flux(*f), FLUX_RSS)
    vus, tout = set(), []
    for lot in lots:
        for a in lot:
            cle = re.sub(r"\W+", "", a["titre"].lower())[:80]
            if cle and cle not in vus:
                vus.add(cle)
                tout.append(a)
    tout.sort(key=lambda a: a["date"] or "", reverse=True)
    return tout[:max_items]


# ---------------------------------------------------------------- Analyse IA (Claude)
def dernier(serie):
    return serie[-1] if serie else None


def faits_cles(wb: dict) -> dict:
    ssf = wb["regions"]["SSF"]
    classement = sorted(
        ((p["nom"], *dernier(p["SI.POV.DDAY"])) for p in wb["pays"].values() if p["SI.POV.DDAY"]),
        key=lambda x: -x[2],
    )
    return {
        "ssf_3usd": dernier(ssf["SI.POV.DDAY"]),
        "ssf_3usd_1990": ssf["SI.POV.DDAY"][0] if ssf["SI.POV.DDAY"] else None,
        "monde_3usd": dernier(wb["regions"]["WLD"]["SI.POV.DDAY"]),
        "ssf_nb_pauvres_millions": dernier(ssf["nb_pauvres_millions"]),
        "top10_plus_pauvres": classement[:10],
        "top5_moins_pauvres": classement[-5:],
    }


def charger_cle_api() -> None:
    """Trouve ANTHROPIC_API_KEY même si elle a été définie après le lancement du serveur :
    fichier .env du projet, puis variables utilisateur Windows (setx)."""
    if os.environ.get("ANTHROPIC_API_KEY"):
        return
    env = ROOT / ".env"
    if env.exists():
        for ligne in env.read_text(encoding="utf-8").splitlines():
            if ligne.strip().startswith("ANTHROPIC_API_KEY="):
                os.environ["ANTHROPIC_API_KEY"] = ligne.split("=", 1)[1].strip().strip('"\'')
                return
    if os.name == "nt":
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as k:
                os.environ["ANTHROPIC_API_KEY"] = winreg.QueryValueEx(k, "ANTHROPIC_API_KEY")[0]
        except OSError:
            pass


def analyse_claude(faits: dict, actus: list[dict]) -> dict | None:
    charger_cle_api()
    try:
        import anthropic
    except ImportError:
        log("Analyse IA ignorée : `pip install anthropic` pour l'activer.")
        return None
    titres = "\n".join(f"- [{a['journal']}, {(a['date'] or '')[:10]}] {a['titre']}" for a in actus[:30])
    prompt = (
        "Tu es un analyste en développement économique. À partir des données de la Banque mondiale "
        "et des titres de presse récents ci-dessous, rédige en français une note de synthèse "
        "(150 à 220 mots) sur la pauvreté en Afrique : niveau actuel et tendance, pays les plus touchés, "
        "et ce que l'actualité récente indique. Cite les chiffres exacts fournis, sans en inventer. "
        "Termine par 3 points d'attention sous forme de liste à puces. Réponds en Markdown simple, sans titre.\n\n"
        f"DONNÉES BANQUE MONDIALE (JSON) :\n{json.dumps(faits, ensure_ascii=False)}\n\n"
        f"TITRES DE PRESSE RÉCENTS :\n{titres}"
    )
    model = os.environ.get("CLAUDE_MODEL", "claude-opus-5-5")
    try:
        client = anthropic.Anthropic()
        kwargs = dict(
            model=model, max_tokens=4000,
            output_config={"effort": "low"},
            messages=[{"role": "user", "content": prompt}],
        )
        try:  # repli automatique côté serveur si la requête est refusée par un classifieur
            msg = client.beta.messages.create(**kwargs, betas=["server-side-fallback-2026-07-01"], fallbacks="default")
        except TypeError:
            msg = client.messages.create(**kwargs)
        if msg.stop_reason == "refusal":
            log("Analyse IA : requête refusée par le modèle.")
            return None
        texte = "".join(b.text for b in msg.content if b.type == "text").strip()
        log("Analyse IA rédigée par Claude.")
        return {"texte": texte, "modele": msg.model}
    except anthropic.AuthenticationError:
        log("Analyse IA ignorée : aucune clé API valide (définissez ANTHROPIC_API_KEY).")
    except anthropic.APIConnectionError as e:
        log(f"Analyse IA : connexion impossible ({e}).")
    except anthropic.APIStatusError as e:
        log(f"Analyse IA : erreur API {e.status_code}.")
    except Exception as e:  # noqa: BLE001  (identifiants absents, etc.)
        log(f"Analyse IA ignorée : {e}")
    return None


# ---------------------------------------------------------------- Exécution
def executer() -> dict:
    debut = datetime.now(timezone.utc)
    wb = collecter_banque_mondiale()
    # Si une série n'a pas pu être téléchargée, on garde celle de la dernière exécution
    try:
        ancien = json.loads(OUT.read_text(encoding="utf-8"))["banque_mondiale"]
        for groupe in ("regions", "pays"):
            for code, bloc in wb[groupe].items():
                for k, v in ancien.get(groupe, {}).get(code, {}).items():
                    if not bloc.get(k) and v:
                        bloc[k] = v
    except Exception:  # noqa: BLE001
        pass
    actus = collecter_actualites()
    faits = faits_cles(wb)
    data = {
        "maj": debut.isoformat(),
        "banque_mondiale": wb,
        "faits": faits,
        "actualites": actus,
        "analyse": analyse_claude(faits, actus),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    tmp = OUT.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    tmp.replace(OUT)
    log(f"Terminé : {OUT} ({len(actus)} articles, {OUT.stat().st_size // 1024} Ko)")
    return data


if __name__ == "__main__":
    try:
        executer()
    except Exception as e:  # noqa: BLE001
        log(f"ÉCHEC : {e}")
        sys.exit(1)
