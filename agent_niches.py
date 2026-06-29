"""
Agent de decouverte automatique de niches dropshipping - SEO faible concurrence
---------------------------------------------------------------------------------
Version 4 :
1. Filtre les categories de depart elles-memes (vraie decouverte uniquement)
2. Supprime le faux signal "gros sites Google" (page bloquee/consentement,
   pas fiable depuis ce type de serveur) -> on garde l'estimation par longueur
   de mot-cle, fiable a 100%, sans dependre de Google.
3. Filtre les noms de marques (contrefacon / risque juridique reel, pas une
   vraie opportunite meme quand le score affiche "faible concurrence")

Auteur : genere par Claude pour Romain
"""

import os
import time
import random
from datetime import date, datetime
from pytrends_modern import TrendReq
import requests

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "METS_TON_TOKEN_ICI")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "METS_TON_CHAT_ID_ICI")

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

# Marques a exclure : pas de vraies opportunites, juste un risque de contrefacon
MARQUES_A_EXCLURE = [
    "louis vuitton", "michael kors", "gucci", "chanel", "dior", "nike", "adidas",
    "rolex", "prada", "hermes", "zara", "lacoste", "ralph lauren", "calvin klein",
    "versace", "burberry", "fendi", "balenciaga", "saint laurent", "cartier",
    "tommy hilfiger", "levis", "converse", "vans", "puma", "new balance", "ysl",
]

NB_CATEGORIES_PAR_JOUR = 10
NB_VARIANTES_PAR_CATEGORIE = 6
SEUIL_VOLUME_MIN = 10
TOP_N_RESULTATS = 12

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
}


def choisir_categories_du_jour():
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


def est_une_marque(mot_cle):
    mc = mot_cle.lower()
    return any(marque in mc for marque in MARQUES_A_EXCLURE)


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
    nb_mots = len(mot_cle.split())
    if nb_mots >= 4:
        return "Faible (longue traine)"
    elif nb_mots == 3:
        return "Moyenne"
    else:
        return "Probablement elevee (mot-cle trop court/generique)"


def decouvrir_opportunites():
    categories = choisir_categories_du_jour()
    categories_lower = [c.lower().strip() for c in categories]
    print(f"Etape 1/3 - Categories explorees aujourd'hui : {categories}")

    print("Etape 2/3 - Generation des variantes via Google Autocomplete...")
    toutes_variantes = set()
    for cat in categories:
        for variante in get_suggestions_google(cat):
            v = variante.strip()
            # On exclut la categorie elle-meme (pas une vraie decouverte)
            if v.lower() in categories_lower:
                continue
            # On exclut les marques (risque de contrefacon)
            if est_une_marque(v):
                continue
            toutes_variantes.add(v)
        time.sleep(1)
    toutes_variantes = list(toutes_variantes)
    print(f"  -> {len(toutes_variantes)} variantes generees apres filtrage")

    print("Etape 3/3 - Mesure du volume de recherche (Google Trends)...")
    volumes = get_volume_trends(toutes_variantes)
    candidats = [mot for mot, vol in volumes.items() if vol >= SEUIL_VOLUME_MIN]
    print(f"  -> {len(candidats)} mots-cles depassent le seuil de volume")

    opportunites = [
        {
            "mot_cle": mot,
            "volume": volumes[mot],
            "estimation": score_concurrence_estime(mot),
        }
        for mot in candidats
    ]
    opportunites.sort(key=lambda x: x["volume"], reverse=True)
    return opportunites[:TOP_N_RESULTATS]


def formater_message(opportunites):
    date_str = datetime.now().strftime("%d/%m/%Y")
    if not opportunites:
        return f"Rapport decouverte niches du {date_str}\n\nAucune opportunite detectee aujourd'hui."

    lignes = [f"*Rapport decouverte niches du {date_str}*\n"]
    for o in opportunites:
        lignes.append(
            f"*{o['mot_cle']}*\n"
            f"   Volume Trends : {o['volume']}/100\n"
            f"   Concurrence estimee : {o['estimation']}\n"
        )
    lignes.append("\nEstimation basee sur la specificite du mot-cle. Verifie toujours manuellement la 1ere page Google avant de te lancer.")
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
