"""
Agent de recherche de fournisseurs CJ Dropshipping
---------------------------------------------------
Version 7 : test diagnostic pur. Le diagnostic precedent a confirme que CJ
n'a quasiment rien sous "unicorn" en anglais. Avant d'abandonner CJ pour toute
la deco enfant, on teste maintenant des termes generiques (sans le mot
"unicorn") pour savoir si c'est tout le rayon deco/textile enfant qui est
faible chez CJ, ou seulement le theme licorne precisement.

Mode diagnostic : pas de filtre de pertinence complexe, pas de verification
de stock (pour aller plus vite) - juste le nombre brut de resultats et
quelques exemples de noms par terme, pour qu'on juge nous-memes.

Auteur: genere par Claude pour Romain
"""

import os
import time
import requests
from datetime import datetime

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "METS_TON_TOKEN_ICI")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "METS_TA_CHAT_ID_ICI")
CJ_API_KEY = os.environ.get("CJ_API_KEY", "METS_TA_CLE_CJ_ICI")

# Termes generiques deco/chambre enfant, SANS le mot "unicorn", pour isoler
# si le probleme est specifique au theme licorne ou plus large.
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
    url = f"{BASE_URL}/authentication/getAccessToken"
    payload = {"apiKey": CJ_API_KEY}
    r = requests.post(url, json=payload, timeout=10)
    data = r.json()
    if not data.get("result"):
        raise Exception(f"Echec authentification CJ : {data.get('message')}")
    return data["data"]["accessToken"]


def rechercher_produits(token, mot_cle, taille=10):
    url = f"{BASE_URL}/product/listV2"
    headers = {"CJ-Access-Token": token}
    params = {"keyWord": mot_cle, "page": 1, "size": taille}
    r = requests.get(url, headers=headers, params=params, timeout=10)
    data = r.json()
    if not data.get("result"):
        print(f"Erreur recherche '{mot_cle}' : {data.get('message')}")
        return []
    contenu = data.get("data", {}).get("content", [])
    if not contenu:
        return []
    return contenu[0].get("productList", [])


def construire_rapport():
    token = get_access_token()
    date_str = datetime.now().strftime("%d/%m/%Y")
    lignes = [f"*Diagnostic deco enfant generique CJ - {date_str}*\n"]
    lignes.append("_Test sans le mot 'unicorn' pour savoir si c'est le theme licorne specifiquement qui manque, ou tout le rayon deco enfant chez CJ._\n")

    for terme in TERMES_DIAGNOSTIC:
        print(f"Recherche : {terme}")
        produits = rechercher_produits(token, terme)
        lignes.append(f"\n— *{terme}* : {len(produits)} resultat(s) brut(s) —")
        for p in produits[:NB_EXEMPLES]:
            nom = p.get("nameEn", "?")
            prix = p.get("sellPrice", "?")
            lignes.append(f"   - {nom} ({prix}$)")
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


def
