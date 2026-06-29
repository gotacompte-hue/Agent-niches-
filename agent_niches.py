"""
Agent de découverte automatique de niches dropshipping - SEO faible concurrence
---------------------------------------------------------------------------------
Ce script, SANS liste prédéfinie :
1. Récupère les tendances de recherche du jour en France (Google Trends RSS)
2. Pour chaque tendance, génère des variantes de mots-clés (Google Autocomplete)
3. Pour chaque variante, analyse qui occupe la 1ère page Google (gros sites vs petits sites)
4. Calcule un score = volume de recherche élevé + faible présence de gros sites
5. Envoie le top des opportunités sur Telegram

Auteur : généré par Claude pour Romain
"""

import os
import time
from datetime import datetime
from pytrends_modern import TrendReq, TrendsRSS
import requests

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "METS_TON_TOKEN_ICI")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "METS_TON_CHAT_ID_ICI")

NB_TENDANCES_DEPART = 15
NB_VARIANTES_PAR_TENDANCE = 5
SEUIL_VOLUME_MIN = 10

GROS_SITES = [
    "amazon", "cdiscount", "fnac", "leroymerlin", "leroy-merlin",
    "darty", "boulanger", "carrefour", "auchan", "decathlon",
    "zalando", "veepee", "shein", "temu", "aliexpress",
    "wikipedia", "youtube", "pinterest",
]

MAX_GROS_SITES_TOLERES = 5
TOP_N_RESULTATS = 8

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
}


def get_tendances_du_jour():
    """
    Récupère les recherches tendances en France aujourd'hui via le flux RSS
    de Google Trends (rapide et fiable, contrairement à l'ancienne méthode
    de scraping qui ne fonctionne plus en 2026).
    """
    try:
        rss = TrendsRSS()
        trends = rss.get_trends(geo="FR")
        tendances = [t["title"] for t in trends][:NB_TENDANCES_DEPART]
        return tendances
    except Exception as e:
        print(f"Erreur récupération tendances (RSS) : {e}")
        return []


def get_suggestions_google(mot_cle):
    url = "http://suggestqueries.google.com/complete/search"
    params = {"client": "firefox", "q": mot_cle, "hl": "fr"}
    try:
        response = requests.get(url, params=params, headers=HEADERS, timeout=5)
        suggestions = response.json()[1]
        return suggestions[:NB_VARIANTES_PAR_TENDANCE]
    except Exception as e:
        print(f"Erreur autocomplete pour '{mot_cle}' : {e}")
        return []


def get_volume_trends(mots_cles, geo="FR"):
    pytrends = TrendReq(hl="fr-FR", tz=60)
    resultats = {}

    for i in range(0, len(mots_cles), 5):
        lot = mots_cles[i:i + 5]
        try:
            pytrends.build_payload(lot, cat=0, timeframe="today 1-m", geo=geo)
            data = pytrends.interest_over_time()
            for mot in lot:
                if mot in data.columns:
                    resultats[mot] = round(data[mot].mean(), 1)
            time.sleep(2)
        except Exception as e:
            print(f"Erreur volume pour {lot} : {e}")

    return resultats


def analyser_concurrence(mot_cle):
    url = "https://www.google.com/search"
    params = {"q": mot_cle, "num": 10, "hl": "fr", "gl": "fr"}
    try:
        response = requests.get(url, params=params, headers=HEADERS, timeout=8)

        if response.status_code != 200 or "captcha" in response.text.lower():
            return {"nb_gros_sites": None, "accessible": True, "verifie": False}

        contenu = response.text.lower()
        nb_gros_sites = sum(1 for site in GROS_SITES if site in contenu)
        accessible = nb_gros_sites <= MAX_GROS_SITES_TOLERES

        return {"nb_gros_sites": nb_gros_sites, "accessible": accessible, "verifie": True}
    except Exception as e:
        print(f"Erreur analyse concurrence pour '{mot_cle}' : {e}")
        return {"nb_gros_sites": None, "accessible": True, "verifie": False}


def decouvrir_opportunites():
    print("Étape 1/4 — Récupération des tendances du jour...")
    tendances = get_tendances_du_jour()
    print(f"  → {len(tendances)} tendances trouvées : {tendances}")

    if not tendances:
        return []

    print("Étape 2/4 — Génération des variantes de mots-clés...")
    toutes_variantes = set()
    for tendance in tendances:
        variantes = get_suggestions_google(tendance)
        toutes_variantes.update(variantes)
        time.sleep(1)
    toutes_variantes = list(toutes_variantes)
    print(f"  → {len(toutes_variantes)} variantes générées")

    print("Étape 3/4 — Mesure du volume de recherche...")
    volumes = get_volume_trends(toutes_variantes)

    candidats = [mot for mot, vol in volumes.items() if vol >= SEUIL_VOLUME_MIN]
    print(f"  → {len(candidats)} mots-clés dépassent le seuil de volume")

    print("Étape 4/4 — Analyse de la concurrence SEO pour chaque candidat...")
    opportunites = []
    for mot in candidats:
        concurrence = analyser_concurrence(mot)
        if concurrence["accessible"]:
            opportunites.append({
                "mot_cle": mot,
                "volume": volumes[mot],
                "nb_gros_sites": concurrence["nb_gros_sites"],
                "verifie": concurrence["verifie"],
            })
        time.sleep(2)

    opportunites.sort(key=lambda x: x["volume"], reverse=True)
    return opportunites[:TOP_N_RESULTATS]


def formater_message(opportunites):
    date_str = datetime.now().strftime("%d/%m/%Y")
    if not opportunites:
        return f"📊 *Rapport découverte niches du {date_str}*\n\nAucune opportunité accessible détectée aujourd'hui."

    lignes = [f"📊 *Rapport découverte niches du {date_str}*\n"]
    for o in opportunites:
        if o["verifie"]:
            ligne_concurrence = f"   Gros sites en page 1 : {o['nb_gros_sites']}\n"
        else:
            ligne_concurrence = "   Concurrence : ⚠️ non vérifiée (à checker à la main)\n"
        lignes.append(
            f"🔎 *{o['mot_cle']}*\n"
            f"   Volume Trends : {o['volume']}/100\n"
            f"{ligne_concurrence}"
        )
    lignes.append("\n💡 Vérifie manuellement la 1ère page Google avant de te lancer — ce score est indicatif.")
    return "\n".join(lignes)


def envoyer_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "Markdown"}
    response = requests.post(url, data=payload)
    if response.status_code != 200:
        print(f"Erreur envoi Telegram : {response.text}")
    else:
        print("Message envoyé avec succès sur Telegram.")


def main():
    opportunites = decouvrir_opportunites()
    message = formater_message(opportunites)
    print("\n--- Message final ---\n" + message)
    envoyer_telegram(message)


if __name__ == "__main__":
    main()
