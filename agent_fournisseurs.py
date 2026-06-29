"""
Agent de recherche de fournisseurs CJ Dropshipping
---------------------------------------------------
Version 7b : test diagnostic pur, sans caracteres speciaux (pour eviter les
soucis de copier-coller mobile qui ont casse la version precedente).

Le diagnostic precedent a confirme que CJ n'a quasiment rien sous "unicorn"
en anglais. Avant d'abandonner CJ pour toute la deco enfant, on teste
maintenant des termes generiques (sans le mot "unicorn") pour savoir si c'est
tout le rayon deco/textile enfant qui est faible chez CJ, ou seulement le
theme licorne precisement.

Auteur: genere par Claude pour Romain
"""

import os
import time
import requests
from datetime import datetime

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "METS_TON_TOKEN_ICI")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "METS_TON_CHAT_ID_ICI")
CJ_API_KEY = os.environ.get("CJ_API_KEY", "METS_TA_CLE_CJ_ICI")

TERMES_DIAGNOSTIC = [
    "kids room sticker",
    "nursery wall decal",
    "kids wall sticker",
    "girl room decor",
    "cartoon wall sticker",
    "kids bedroom decor",
    "wall sticker for kids room",
    "baby room decoration",
]

NB_EXEMPLES = 3
BASE_URL = "https://developers.cjdropshipping.com/api2.0/v1"


def get_access_token():
    url = BASE_URL + "/authentication/getAccessToken"
    payload = {"apiKey": CJ_API_KEY}
    r = requests.post(url, json=payload, timeout=10)
    data = r.json()
    if not data.get("result"):
        raise Exception("Echec authentification CJ : " + str(data.get("message")))
    return data["data"]["accessToken"]


def rechercher_produits(token, mot_cle, taille=10):
    url = BASE_URL + "/product/listV2"
    headers = {"CJ-Access-Token": token}
    params = {"keyWord": mot_cle, "page": 1, "size": taille}
    r = requests.get(url, headers=headers, params=params, timeout=10)
    data = r.json()
    if not data.get("result"):
        print("Erreur recherche : " + mot_cle + " : " + str(data.get("message")))
        return []
    contenu = data.get("data", {}).get("content", [])
    if not contenu:
        return []
    return contenu[0].get("productList", [])


def construire_rapport():
    token = get_access_token()
    date_str = datetime.now().strftime("%d/%m/%Y")
    lignes = []
    lignes.append("Diagnostic deco enfant generique CJ - " + date_str)
    lignes.append("")
    lignes.append("Test sans le mot unicorn pour savoir si c'est le theme licorne specifiquement qui manque, ou tout le rayon deco enfant chez CJ.")

    for terme in TERMES_DIAGNOSTIC:
        print("Recherche : " + terme)
        produits = rechercher_produits(token, terme)
        lignes.append("")
        lignes.append(terme + " : " + str(len(produits)) + " resultat(s) brut(s)")
        for p in produits[:NB_EXEMPLES]:
            nom = p.get("nameEn", "?")
            prix = p.get("sellPrice", "?")
            lignes.append("   - " + nom + " (" + str(prix) + "$)")
        time.sleep(1)

    return "\n".join(lignes)


def envoyer_telegram(message):
    url = "https://api.telegram.org/bot" + TELEGRAM_BOT_TOKEN + "/sendMessage"
    morceaux = [message[i:i + 3500] for i in range(0, len(message), 3500)]
    for morceau in morceaux:
        payload = {"chat_id": TELEGRAM_CHAT_ID, "text": morceau}
        r = requests.post(url, data=payload)
        if r.status_code != 200:
            print("Erreur envoi Telegram : " + r.text)
        time.sleep(1)


def main():
    rapport = construire_rapport()
    print("--- Rapport ---")
    print(rapport)
    envoyer_telegram(rapport)


if __name__ == "__main__":
    main()
