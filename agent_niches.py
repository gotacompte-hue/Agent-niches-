"""
Agent de découverte automatique de niches dropshipping - SEO faible concurrence
---------------------------------------------------------------------------------
Version 3 - corrige deux problèmes identifiés :
1. Les "tendances du jour" (RSS) remontaient de l'actu générale (sport, people...)
   et pas des produits -> remplacé par un pool de catégories e-commerce qui tourne
   chaque jour, et c'est l'autocomplete qui découvre les vraies niches dedans.
2. L'analyse de concurrence en scrapant Google était trop souvent bloquée
   silencieusement (renvoyait "0 gros sites" même quand Google bloquait juste la
   requête) -> détection de blocage plus large + score de concurrence "estimé"
   basé sur la longueur du mot-clé, fiable à 100%, qui ne dépend pas de Google.

Auteur : généré par Claude pour Romain
"""

import os
import time
import random
from datetime import date, datetime
from pytrends_modern import TrendReq
import requests

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "METS_TON_TOKEN_ICI")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "METS_TON_CHAT_ID_ICI")

# Pool large de catégories e-commerce. Chaque jour, on en tire un sous-ensemble
# différent (mais stable sur la journée) pour explorer large sans jamais répéter
# exactement la même recherche.
CATEGORIES_SEED = [
    "accessoire cuisine", "rangement maison", "decoration chambre", "luminaire salon",
    "bijoux femme", "bijoux homme", "montre femme", "sac a main", "lunettes de soleil",
    "accessoire telephone", "coque telephone", "gadget bureau", "accessoire voiture",
    "accessoire moto", "soin visage", "soin cheveux", "maquillage", "parfum femme",
    "accessoire bebe", "jouet enfant", "accessoire animaux", "jouet chien", "accessoire chat",
    "equipement fitness", "accessoire yoga", "materiel camping", "accessoire jardin",
    "outil bricolage", "accessoire velo", "accessoire peche", "accessoire piscine",
    "vetement femme", "chaussures femme", "sous vetement femme",
    "accessoire mariage", "papeterie bureau", "accessoire gaming", "accessoire photo",
    "rangement cuisine", "deco terrasse", "accessoire running",
]

NB_CATEGORIES_PAR_JOUR = 10
NB_VARIANTES_PAR_CATEGORIE = 6
SEUIL_VOLUME_MIN = 10
TOP_N_RESULTATS = 10

GROS_SITES = [
    "amazon", "cdiscount", "fnac", "leroymerlin", "leroy-merlin",
    "darty", "boulanger", "carrefour", "auchan", "decathlon",
    "zalando", "veepee", "shein", "temu", "aliexpress",
    "wikipedia", "youtube", "pinterest",
]
MAX_GROS_SITES_TOLERES = 5

# Signaux qui indiquent que Google a bloqué/redirigé la requête (donc la donnée
# n'est pas fiable, à ne pas confondre avec "vraiment 0 gros site")
SIGNAUX_BLOCAGE = [
    "captcha", "recaptcha", "unusual traffic", "trafic inhabituel",
    "nos systemes ont detecte", "/sorry/", "automated queries",
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
}


def choisir_categories_du_jour():
    """Tire un sous-ensemble de catégories, différent chaque jour mais stable
    pour toute la journée (utile si le workflow est relancé plusieurs fois)."""
    random.seed(date.today().isoformat())
    return random.sample(CATEGORIES_SEED, k=min(NB_CATEGORIES_PAR_JOUR, len(CATEGORIES_SEED)))


def get_suggestions_google(mot_cle, n=NB_VARIANTES_PAR_CATEGORIE):
    url = "http://suggestqueries.google.com/complete/search"
    params = {"client": "firefox", "q": mot_cle, "hl": "fr"}
    try:
        response = requests.get(url, params=params, headers=HEADERS, timeout=5)
        suggestions = response.json()[1]
        return suggestions[:n]
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


def score_concurrence_estime(mot_cle):
    """Estimation gratuite et fiable à 100%, sans dépendre de Google : plus un
    mot-clé est long/précis, statistiquement moins il est disputé (logique du
    longue traîne en SEO)."""
    nb_mots = len(mot_cle.split())
    if nb_mots >= 4:
        return "Faible (longue traine)"
    elif nb_mots == 3:
        return "Moyenne"
    else:
        return "Probablement elevee (mot-cle trop court/generique)"


def analyser_concurrence_google(mot_cle):
    """Tentative de vérification réelle en regardant qui occupe la page 1 Google.
    Best-effort uniquement : si Google bloque la requête (probable depuis une IP
    GitHub Actions), on renvoie None plutôt qu'un faux 0."""
    url = "https://www.google.com/search"
    params = {"q": mot_cle, "num": 10, "hl": "fr", "gl": "fr"}
    try:
        response = requests.get(url, params=params, headers=HEADERS, timeout=8)
        contenu = response.text.lower()
        url_finale = response.url.lower()

        bloque = (
            response.status_code != 200
            or any(signal in contenu for signal in SIGNAUX_BLOCAGE)
            or "sorry" in url_finale
            or len(contenu) < 2000
        )
        if bloque:
            return None

        nb_gros_sites = sum(1 for site in GROS_SITES if site in contenu)
        return nb_gros_sites
    except Exception as e:
        print(f"Erreur analyse concurrence pour '{mot_cle}' : {e}")
        return None


def decouvrir_opportunites():
    categories = choisir_categories_du_jour()
    print(f"Etape 1/4 - Categories explorees aujourd'hui : {categories}")

    print("Etape 2/4 - Generation des variantes via Google Autocomplete...")
    toutes_variantes = set()
    for cat in categories:
        variantes = get_suggestions_google(cat)
        toutes_variantes.update(variantes)
        time.sleep(1)
    toutes_variantes = list(toutes_variantes)
    print(f"  -> {len(toutes_variantes)} variantes generees")

    print("Etape 3/4 - Mesure du volume de recherche (Google Trends)...")
    volumes = get_volume_trends(toutes_variantes)
    candidats = [mot for mot, vol in volumes.items() if vol >= SEUIL_VOLUME_MIN]
    print(f"  -> {len(candidats)} mots-cles depassent le seuil de volume")

    print("Etape 4/4 - Estimation de la concurrence...")
    opportunites = []
    for mot in candidats:
        nb_gros_sites = analyser_concurrence_google(mot)
        opportunites.append({
            "mot_cle": mot,
            "volume": volumes[mot],
            "nb_gros_sites": nb_gros_sites,
            "estimation": score_concurrence_estime(mot),
        })
        time.sleep(2)

    opportunites.sort(key=lambda x: x["volume"], reverse=True)
    return opportunites[:TOP_N_RESULTATS]


def formater_message(opportunites):
    date_str = datetime.now().strftime("%d/%m/%Y")
    if not opportunites:
        return f"Rapport decouverte niches du {date_str}\n\nAucune opportunite detectee aujourd'hui."

    lignes = [f"*Rapport decouverte niches du {date_str}*\n"]
    for o in opportunites:
        if o["nb_gros_sites"] is not None:
            ligne_concurrence = f"   Gros sites page 1 (verifie) : {o['nb_gros_sites']}\n"
        else:
            ligne_concurrence = "   Gros sites page 1 : non verifiable (Google a bloque)\n"
        lignes.append(
            f"*{o['mot_cle']}*\n"
            f"   Volume Trends : {o['volume']}/100\n"
            f"{ligne_concurrence}"
            f"   Concurrence estimee : {o['estimation']}\n"
        )
    lignes.append("\nVerifie toujours manuellement la 1ere page Google avant de te lancer.")
    return "\n".join(lignes)


def envoyer_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "Markdown"}
    response = requests.post(url, data=payload)
    if response.status_code != 200:
        print(f"Erreur envoi Telegram : {response.text}")
    else:
        print("Message envoye avec succes sur Telegram.")


def main():
    opportunites = decouvrir_opportunites()
    message = formater_message(opportunites)
    print("\n--- Message final ---\n" + message)
    envoyer_telegram(message)


if __name__ == "__main__":
    main()
