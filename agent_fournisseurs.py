"""
Agent de recherche de fournisseurs CJ Dropshipping
---------------------------------------------------
Cherche, pour une liste de mots-cles produits, les meilleures options
fournisseurs chez CJ Dropshipping (prix, livraison, personnalisation,
nombre de boutiques qui le vendent deja) et envoie un rapport sur Telegram.

Version 2 : corrige un vrai bug identifie sur le premier rapport. Le catalogue
CJ est indexe en anglais/chinois, pas en francais -> chercher en francais
("licorne", "personnalise") ne matche presque rien, sauf des mots qui
s'ecrivent pareil dans les deux langues ("stickers"), ce qui ramenait des
produits sans rapport. Mots-cles passes en anglais. Suppression aussi du tri
force par nombre de boutiques (qui ecrasait la pertinence) au profit du tri
par defaut "meilleure correspondance".

Auteur: genere par Claude pour Romain
"""

import os
import time
import requests
from datetime import datetime

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "METS_TON_TOKEN_ICI")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "METS_TON_CHAT_ID_ICI")
CJ_API_KEY = os.environ.get("CJ_API_KEY", "METS_TA_CLE_CJ_ICI")

# Mots-cles en ANGLAIS (le catalogue CJ est indexe en anglais/chinois,
# chercher en francais ne renvoie quasiment rien d'exploitable)
MOTS_CLES_PRODUITS = [
    "unicorn wall stickers",
    "unicorn wallpaper mural",
    "personalized name stickers kids",
    "unicorn fairy lights",
    "unicorn cushion pillow kids",
]

NB_PRODUITS_PAR_MOT_CLE = 5
BASE_URL = "https://developers.cjdropshipping.com/api2.0/v1"


def get_access_token():
    url = f"{BASE_URL}/authentication/getAccessToken"
    payload = {"apiKey": CJ_API_KEY}
    r = requests.post(url, json=payload, timeout=10)
    data = r.json()
    if not data.get("result"):
        raise Exception(f"Echec authentification CJ : {data.get('message')}")
    return data["data"]["accessToken"]


def rechercher_produits(token, mot_cle, taille=NB_PRODUITS_PAR_MOT_CLE):
    url = f"{BASE_URL}/product/listV2"
    headers = {"CJ-Access-Token": token}
    params = {
        "keyWord": mot_cle,
        "page": 1,
        "size": taille,
        # Pas de tri force : on garde le tri par defaut "meilleure
        # correspondance" (orderBy=0) pour que la pertinence prime sur la
        # popularite.
    }
    r = requests.get(url, headers=headers, params=params, timeout=10)
    data = r.json()
    if not data.get("result"):
        print(f"Erreur recherche '{mot_cle}' : {data.get('message')}")
        return []

    contenu = data.get("data", {}).get("content", [])
    if not contenu:
        return []
    return contenu[0].get("productList", [])


def formater_produit(p):
    nom = p.get("nameEn", "Produit sans nom")
    prix = p.get("sellPrice", "?")
    prix_promo = p.get("discountPrice")
    livraison_gratuite = "Oui" if p.get("addMarkStatus") == 1 else "Non"
    nb_listings = p.get("listedNum", 0)
    personnalisable = "Oui" if p.get("isPersonalized") == 1 else "Non"

    ligne_prix = f"{prix}$"
    if prix_promo and str(prix_promo) != str(prix):
        ligne_prix += f" (promo: {prix_promo}$)"

    return (
        f"*{nom}*\n"
        f"   Prix : {ligne_prix} | Livraison gratuite : {livraison_gratuite}\n"
        f"   Deja liste par {nb_listings} boutique(s) | Personnalisable : {personnalisable}"
    )


def construire_rapport():
    token = get_access_token()
    date_str = datetime.now().strftime("%d/%m/%Y")
    lignes = [f"*Rapport fournisseurs CJ du {date_str}*\n"]

    for mot_cle in MOTS_CLES_PRODUITS:
        print(f"Recherche : {mot_cle}")
        produits = rechercher_produits(token, mot_cle)
        lignes.append(f"\n— *{mot_cle}* —")
        if not produits:
            lignes.append("Aucun produit trouve.")
        else:
            for p in produits:
                lignes.append(formater_produit(p))
        time.sleep(1)

    return "\n".join(lignes)


def envoyer_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    morceaux = [message[i:i + 3500] for i in range(0, len(message), 3500)]
    for morceau in morceaux:
        payload = {"chat_id": TELEGRAM_CHAT_ID, "text": morceau, "parse_mode": "Markdown"}
        r = requests.post(url, data=payload)
        if r.status_code != 200:
            print(f"Erreur envoi Telegram : {r.text}")
        time.sleep(1)


def main():
    rapport = construire_rapport()
    print("\n--- Rapport ---\n" + rapport)
    envoyer_telegram(rapport)


if __name__ == "__main__":
    main()
