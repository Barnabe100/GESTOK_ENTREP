# StockManager — Générateur de licences

Outil réservé à l'éditeur, **jamais embarqué ni distribué avec
StockManager Desktop**. Il détient et manipule la clé privée Ed25519 de
signature des licences ; le client (`app/`) ne détient et n'utilise que la
clé publique correspondante (`app/services/licensing/public_key.py`).

## Règle non négociable

La clé privée de signature (`keys/private_key.pem`) ne doit **jamais** :
- être commitée dans ce dépôt (`keys/` est listé dans `.gitignore`) ;
- être copiée dans `app/` ou tout autre dossier du projet client ;
- se retrouver dans un test, une ressource embarquée, ou l'exécutable
  packagé de StockManager Desktop.

À terme (voir §18 du cahier des charges de la phase Licences), ce dossier a
vocation à vivre dans un dépôt entièrement séparé du dépôt client — cette
séparation est déjà respectée au niveau du code (aucun module de `app/`
n'importe quoi que ce soit depuis `license_generator/`), seule la
séparation physique des dépôts reste à faire lors du packaging final.

## Utilisation

```bash
pip install -r license_generator/requirements.txt

# 1) Une seule fois : génère keys/private_key.pem (à protéger) et
#    keys/public_key.hex (à copier dans public_key.py côté client).
python license_generator/generate_keypair.py

# 2) Pour chaque client : émet une licence signée.
python license_generator/generate_license.py \
    --client "Ma Société" --edition PROFESSIONAL \
    --max-users 5 --max-devices 2 --expires 2027-01-01 \
    --out licence_ma_societe.lic
```

Le fichier `.lic` produit est un JSON `{"payload": {...}, "signature": "..."}`
sans aucune donnée secrète : il peut être transmis librement au client, qui
l'importe depuis l'écran Administration → Licence de StockManager Desktop.
