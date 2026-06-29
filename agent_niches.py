"""
Agent de decouverte automatique de niches dropshipping - SEO faible concurrence
---------------------------------------------------------------------------------
Version 9 : corrige le vrai probleme du rapport precedent. "recette cuisine"
etait un trop gros poisson comme mot-cle de reference : il ecrasait quasiment
tous les autres mots-cles a 0 dans la reponse brute de Google (avant meme mon
calcul de ratio), car Google Trends arrondit a l'entier sur une echelle 0-100
par requete. Remplace par "coque telephone", un terme e-commerce courant et
donc bien plus proche en ordre de grandeur des mots-cles produits qu'on teste.
Ajout d'une distinction claire entre "volume mesure a 0" et "volume non
mesurable avec ce repere" pour ne pas afficher une fausse precision.

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

# "coque telephone" sert desormais UNIQUEMENT de repere fixe (retire des
# categories explorees pour ne pas faire double emploi)
CATEGORIES_SEED = [
    "accessoire cuisine", "rangement maison", "decoration chambre", "luminaire salon",
    "bijoux femme", "bijoux homme", "montre femme", "sac a main", "lunettes de soleil",
    "gadget bureau", "accessoire voiture",
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

MOT_CLE_ANCRE = "coque telephone"

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
    """
    Retourne un dict mot_cle -> score relatif (None si en-dessous du seuil de
    mesure, distinct d'un vrai zero).
    """
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
                        if valeur_brute <= 0:
                            resultats[mot] = None  # non mesurable a cette echelle
                        else:
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
    if score is None:
        return "Non mesurable (sous le seuil)"
    elif score >= 50:
        return "Fort"
    elif score >= 15:
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

    print(f"Etape 4/4 - Mesure du volume relatif (repere = '{MOT_CLE_ANCRE}')...")
    scores = get_scores_relatifs(toutes_variantes)
    nb_mesures = sum(1 for v in scores.values() if v is not None)
    print(f"  -> {len(scores)} mots-cles traites, {nb_mesures} mesures avec une vraie valeur")

    opportunites = [
        {
            "mot_cle": mot,
            "score": score,
            "volume": etiquette_volume(score),
            "estimation": score_concurrence_estime(mot),
        }
        for mot, score in scores.items()
    ]
    # Trie : les scores mesures (les plus forts d'abord), puis les non-mesurables a la fin
    opportunites.sort(key=lambda x: (x["score"] is None, -(x["score"] or 0)))
    return opportunites[:TOP_N_RESULTATS]


def formater_message(opportunites):
    date_str = datetime.now().strftime("%d/%m/%Y")
    if not opportunites:
        return f"Rapport decouverte niches du {date_str}\n\nAucun mot-cle traite avec succes aujourd'hui (Google a probablement tout bloque)."

    lignes = [f"*Rapport decouverte niches du {date_str}*\n"]
    for o in opportunites:
        score_affiche = o["score"] if o["score"] is not None else "-"
        lignes.append(
            f"*{o['mot_cle']}*\n"
            f"   Volume relatif : {o['volume']} (score {score_affiche})\n"
            f"   Concurrence estimee : {o['estimation']}\n"
        )
    lignes.append(f"\nScore relatif a '{MOT_CLE_ANCRE}'. Verifie toujours manuellement la 1ere page Google avant de te lancer.")
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
