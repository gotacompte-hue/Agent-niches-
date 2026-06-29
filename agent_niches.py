"""
Agent de decouverte automatique de niches dropshipping - SEO faible concurrence
---------------------------------------------------------------------------------
Version 8 : le systeme de pause/retry contre les 429 fonctionne (confirme par
les logs - les lots bloques ont fini par reussir a la 2e tentative). Le vrai
probleme etait le seuil de score, trop exigeant car relatif a "recette cuisine"
(l'une des requetes les plus tapees en France) : il cachait la quasi-totalite
des mots-cles pourtant correctement mesures. Suppression du seuil couperet,
remplace par un classement + etiquette qualitative. Legere augmentation du
nombre de categories explorees, le mecanisme anti-blocage ayant prouve sa
fiabilite.

Auteur : genere par Claude pour Romain
"""

import os
import time
import random
import unicodedata
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
    "coach", "guess", "yves rocher", "kenzo", "longchamp", "furla",
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

NB_CATEGORIES_PAR_JOUR = 8
NB_VARIANTES_PAR_CATEGORIE = 4
TOP_N_RESULTATS = 15

PAUSE_ENTRE_LOTS = 15
PAUSE_AVANT_RETRY = 25

HEADERS_GOOGLE = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
}
HEADERS_WIKIPEDIA = {
    "User-Agent": "AgentNichesRomain/1.0 (outil personnel de recherche de niches dropshipping)"
}


def normaliser(texte):
    texte = texte.lower().strip()
    texte = unicodedata.normalize("NFKD", texte)
    return "".join(c for c in texte if not unicodedata.combining(c))


def choisir_categories_du_jour():
    random.seed(date.today().isoformat())
    return random.sample(CATEGORIES_SEED, k=min(NB_CATEGORIES_PAR_JOUR, len(CATEGORIES_SEED)))


def get_marques_wikipedia():
    marques = set(normaliser(m) for m in MARQUES_SECOURS)
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
                marques.add(normaliser(member["title"]))
        except Exception as e:
            print(f"Erreur recuperation marques Wikipedia pour '{cat}' : {e}")
    print(f"  -> {len(marques)} marques connues chargees (Wikipedia + liste de secours)")
    return marques


def est_une_marque(mot_cle, marques):
    mc = normaliser(mot_cle)
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
    pytrends = TrendReq(hl="fr-FR", tz=60, retries=1, backoff_factor=0)
    resultats = {}
    nb_lots = (len(mots_cles) + 3) // 4

    for index_lot in range(nb_lots):
        debut = index_lot * 4
        lot = mots_cles[debut:debut + 4] + [MOT_CLE_ANCRE]

        for tentative in range(2):
            try:
                pytrends.build_payload(lot, cat=0, timeframe="today 1-m", geo=geo)
                data = pytrends.interest_over_time()

                if MOT_CLE_ANCRE not in data.columns:
                    break
                valeur_ancre = data[MOT_CLE_ANCRE].mean()
                if valeur_ancre <= 0:
                    break

                for mot in lot[:-1]:
                    if mot in data.columns:
                        valeur_brute = data[mot].mean()
                        resultats[mot] = round((valeur_brute / valeur_ancre) * 100, 1)
                break
            except Exception as e:
                print(f"Erreur volume pour {lot} (tentative {tentative + 1}/2) : {e}")
                if tentative == 0:
                    print(f"  -> Pause de {PAUSE_AVANT_RETRY}s avant nouvel essai...")
                    time.sleep(PAUSE_AVANT_RETRY)

        if index_lot < nb_lots - 1:
            print(f"  -> Pause de {PAUSE_ENTRE_LOTS}s avant le prochain lot...")
            time.sleep(PAUSE_ENTRE_LOTS)

    return resultats


def score_concurrence_estime(mot_cle):
    nb_mots = len(mot_cle.split())
    if nb_mots >= 4:
        return "Faible (longue traine)"
    elif nb_mots == 3:
        return "Moyenne"
    else:
        return "Probablement elevee (mot-cle trop court/generique)"


def etiquette_volume(score):
    if score >= 20:
        return "Fort"
    elif score >= 5:
        return "Moyen"
    else:
        return "Faible"


def decouvrir_opportunites():
    print("Etape 1/4 - Chargement de la liste de marques (Wikipedia)...")
    marques = get_marques_wikipedia()

    categories = choisir_categories_du_jour()
    categories_normalisees = [normaliser(c) for c in categories]
    print(f"Etape 2/4 - Categories explorees aujourd'hui : {categories}")

    print("Etape 3/4 - Generation des variantes via Google Autocomplete...")
    toutes_variantes = set()
    for cat in categories:
        for variante in get_suggestions_google(cat):
            v = variante.strip()
            if normaliser(v) in categories_normalisees:
                continue
            if est_une_marque(v, marques):
                continue
            toutes_variantes.add(v)
        time.sleep(1)
    toutes_variantes = list(toutes_variantes)
    print(f"  -> {len(toutes_variantes)} variantes generees apres filtrage")

    print("Etape 4/4 - Mesure du volume relatif (ancre = recette cuisine)...")
    scores = get_scores_relatifs(toutes_variantes)
    print(f"  -> {len(scores)} mots-cles mesures avec succes")

    opportunites = [
        {
            "mot_cle": mot,
            "score": score,
            "volume": etiquette_volume(score),
            "estimation": score_concurrence_estime(mot),
        }
        for mot, score in scores.items()
    ]
    opportunites.sort(key=lambda x: x["score"], reverse=True)
    return opportunites[:TOP_N_RESULTATS]


def formater_message(opportunites):
    date_str = datetime.now().strftime("%d/%m/%Y")
    if not opportunites:
        return f"Rapport decouverte niches du {date_str}\n\nAucun mot-cle mesure avec succes aujourd'hui (Google a probablement tout bloque)."

    lignes = [f"*Rapport decouverte niches du {date_str}*\n"]
    for o in opportunites:
        lignes.append(
            f"*{o['mot_cle']}*\n"
            f"   Volume relatif : {o['volume']} (score {o['score']})\n"
            f"   Concurrence estimee : {o['estimation']}\n"
        )
    lignes.append("\nScore relatif a 'recette cuisine'. Verifie toujours manuellement la 1ere page Google avant de te lancer.")
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
