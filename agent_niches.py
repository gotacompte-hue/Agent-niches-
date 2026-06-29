"""
Agent de decouverte automatique de niches dropshipping - SEO faible concurrence
---------------------------------------------------------------------------------
Version 5 :
1. Filtre les marques de facon dynamique (categories Wikipedia + liste de
   secours) au lieu d'une liste figee a la main qu'il faut sans cesse completer
2. Corrige un vrai biais de mesure : Google Trends normalise chaque lot de
   mots-cles entre 0 et 100 *au sein du lot*. Sans correction, un mot-cle a
   fort volume dans son lot ecrase tous les autres, meme s'ils ont un vrai
   volume correct en absolu -> ajout d'un mot-cle "ancre" fixe dans chaque lot
   pour rendre les scores enfin comparables entre eux.
3. Explore un peu plus large pour compenser les mots-cles retires (marques)

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

MARQUES_SECOURS = [
    "louis vuitton", "michael kors", "gucci", "chanel", "dior", "nike", "adidas",
    "rolex", "prada", "hermes", "zara", "lacoste", "ralph lauren", "calvin klein",
    "versace", "burberry", "fendi", "balenciaga", "saint laurent", "cartier",
    "tommy hilfiger", "levis", "converse", "vans", "puma", "new balance", "ysl",
    "tissot", "casio", "fossil", "swatch", "festina", "seiko", "citizen",
]

CATEGORIES_WIKIPEDIA_MARQUES = [
    "Marque de vêtements",
    "Marque de joaillerie",
    "Fabricant d'horlogerie",
    "Marque de cosmétique",
    "Équipementier sportif",
    "Marque de chaussures",
    "Marque de maroquinerie",
    "Marque de parfum",
]

MOT_CLE_ANCRE = "recette cuisine"

NB_CATEGORIES_PAR_JOUR = 14
NB_VARIANTES_PAR_CATEGORIE = 8
SEUIL_SCORE_RELATIF_MIN = 5
TOP_N_RESULTATS = 12

HEADERS_GOOGLE = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
}
HEADERS_WIKIPEDIA = {
    "User-Agent": "AgentNichesRomain/1.0 (outil personnel de recherche de niches dropshipping)"
}


def choisir_categories_du_jour():
    random.seed(date.today().isoformat())
    return random.sample(CATEGORIES_SEED, k=min(NB_CATEGORIES_PAR_JOUR, len(CATEGORIES_SEED)))


def get_marques_wikipedia():
    marques = set(MARQUES_SECOURS)
    url = "https://fr.wikipedia.org/w/api.php"
    for cat in CATEGORIES_WIKIPEDIA_MARQUES:
        try:
            params = {
                "action": "query",
                "list": "categorymembers",
                "cmtitle": f"Catégorie:{cat}",
                "cmlimit": "500",
                "cmnamespace": "0",
                "format": "json",
            }
            r = requests.get(url, params=params, headers=HEADERS_WIKIPEDIA, timeout=8)
            data = r.json()
            for member in data.get("query", {}).get("categorymembers", []):
                marques.add(member["title"].lower())
        except Exception as e:
            print(f"Erreur recuperation marques Wikipedia pour '{cat}' : {e}")
    print(f"  -> {len(marques)} marques connues chargees (Wikipedia + liste de secours)")
    return marques


def est_une_marque(mot_cle, marques):
    mc = mot_cle.lower()
    return any(marque in mc for marque in marques)


def get_suggestions_google(mot_cle, n=NB_VARIANTES_PAR_CATEGORIE):
    url = "http://suggestqueries.google.com/complete/search"
    params = {"client": "firefox", "q": mot_cle, "hl": "fr"}
    try:
        response = requests.get(url, params=params, headers=HEADERS_GOOGLE, timeout=5)
        suggestions = response.json()[1]
        return suggestions[:n]
    except Exception as e:
        print(f"Erreur autocomplete pour '{mot_cle}' : {e}")
        return []


def get_scores_relatifs(mots_cles, geo="FR"):
    pytrends = TrendReq(hl="fr-FR", tz=60)
    resultats = {}

    for i in range(0, len(mots_cles), 4):
        lot = mots_cles[i:i + 4] + [MOT_CLE_ANCRE]
        try:
            pytrends.build_payload(lot, cat=0, timeframe="today 1-m", geo=geo)
            data = pytrends.interest_over_time()

            if MOT_CLE_ANCRE not in data.columns:
                continue
            valeur_ancre = data[MOT_CLE_ANCRE].mean()
            if valeur_ancre <= 0:
                continue

            for mot in lot[:-1]:
                if mot in data.columns:
                    valeur_brute = data[mot].mean()
                    resultats[mot] = round((valeur_brute / valeur_ancre) * 100, 1)
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
    print("Etape 1/4 - Chargement de la liste de marques (Wikipedia)...")
    marques = get_marques_wikipedia()

    categories = choisir_categories_du_jour()
    categories_lower = [c.lower().strip() for c in categories]
    print(f"Etape 2/4 - Categories explorees aujourd'hui : {categories}")

    print("Etape 3/4 - Generation des variantes via Google Autocomplete...")
    toutes_variantes = set()
    for cat in categories:
        for variante in get_suggestions_google(cat):
            v = variante.strip()
            if v.lower() in categories_lower:
                continue
            if est_une_marque(v, marques):
                continue
            toutes_variantes.add(v)
        time.sleep(1)
    toutes_variantes = list(toutes_variantes)
    print(f"  -> {len(toutes_variantes)} variantes generees apres filtrage")

    print("Etape 4/4 - Mesure du volume relatif (ancre = recette cuisine)...")
    scores = get_scores_relatifs(toutes_variantes)
    candidats = [mot for mot, score in scores.items() if score >= SEUIL_SCORE_RELATIF_MIN]
    print(f"  -> {len(candidats)} mots-cles depassent le seuil")

    opportunites = [
        {"mot_cle": mot, "score": scores[mot], "estimation": score_concurrence_estime(mot)}
        for mot in candidats
    ]
    opportunites.sort(key=lambda x: x["score"], reverse=True)
    return opportunites[:TOP_N_RESULTATS]


def formater_message(opportunites):
    date_str = datetime.now().strftime("%d/%m/%Y")
    if not opportunites:
        return f"Rapport decouverte niches du {date_str}\n\nAucune opportunite detectee aujourd'hui."

    lignes = [f"*Rapport decouverte niches du {date_str}*\n"]
    for o in opportunites:
        lignes.append(
            f"*{o['mot_cle']}*\n"
            f"   Score volume (relatif) : {o['score']}\n"
            f"   Concurrence estimee : {o['estimation']}\n"
        )
    lignes.append("\nScore relatif a un mot-cle de reference, pas un volume reel. Verifie toujours manuellement la 1ere page Google avant de te lancer.")
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
