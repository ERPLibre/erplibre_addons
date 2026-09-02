# erplibre_mobile_gateway — passerelle SMS mobile auto-hébergée

Envoie des SMS depuis Odoo 18 Community sans Odoo IAP et sans agrégateur
externe. Un téléphone Android exécutant l'application ERPLibre **interroge**
Odoo à intervalle régulier, envoie par sa propre carte SIM, puis rend compte.

Le module trace aussi les **appels téléphoniques** : composés à la main sur le
téléphone, lancés depuis Odoo par le bouton « Appeler », ou mis en file par le
serveur.

## Pourquoi cette architecture

Le serveur Odoo est chez un hébergeur, le téléphone est dans les locaux, souvent
derrière une connexion résidentielle à IP dynamique et NAT d'opérateur. Le
serveur ne peut donc **jamais** joindre le téléphone.

C'est le téléphone qui vient, toujours **en sortant** : il interroge, il
rapporte. Aucun port à ouvrir côté locaux, aucun tunnel, aucune URL publique
pour le téléphone, et rien à maintenir entre les deux.

Une première version passait par un serveur **ntfy** intermédiaire. Il a été
retiré : il ajoutait une machine à installer, à sécuriser et à surveiller, pour
un service que l'interrogation directe rend seule. Chaque interrogation vaut
aussi signal de vie, ce qui rend la détection de panne exacte — une passerelle
qui n'interroge plus **est** hors service, par définition.

## Ce qu'il faut savoir avant de s'en servir

**Android plafonne à 30 segments par minute et par application.** Vérifié dans
les sources AOSP (`SmsUsageMonitor.java`, `DEFAULT_SMS_MAX_COUNT = 30`,
`DEFAULT_SMS_CHECK_PERIOD = 60000`), en comptant les *segments* et non les
messages. Au-delà, Android empile un dialogue de confirmation sur le téléphone :
sur un appareil que personne ne regarde, cela veut dire que **rien ne part**. La
passerelle s'étale donc volontairement sous la limite.

Conséquence pratique : un groupe de 40 destinataires prend environ 100 secondes
si le message est en GSM-7, et **3 min 20 s s'il est accentué**. En français du
Québec, le cas accentué est la norme — `ç` minuscule n'est pas dans l'alphabet
GSM 03.38, donc « reçu », « ça », « leçon », « français » font basculer le
message en UCS-2, à 70 caractères par segment au lieu de 160. Le compositeur
affiche l'estimation avant l'envoi.

**Un canal d'urgence qui échoue en silence est pire qu'un canal absent.** Ce
module est construit autour de ce constat : signal de vie exigé du téléphone,
échéance d'envoi par message, escalade sur un canal indépendant, et
impossibilité pour un rapport tardif de faire régresser un échec en succès.

## Installation

### 1. Secrets, dans l'environnement du processus Odoo

Le code de ce module est publié sous AGPL-3 : aucun secret n'y figure, et aucun
n'est stocké en base — une clé en base part dans les sauvegardes.

```ini
# /etc/erplibre/erplibre_mobile_gateway.env  (chmod 0600, propriétaire = utilisateur Odoo)
ERPLIBRE_SMS_HMAC_SECRET=<64 caractères aléatoires>
```

```ini
# unité systemd d'Odoo
[Service]
EnvironmentFile=/etc/erplibre/erplibre_mobile_gateway.env
```

Générer le secret : `openssl rand -hex 32`.

> `server_environment` d'OCA ne convient pas ici : sans le module compagnon
> `server_environment_files` ni `running_env` dans la configuration — tous deux
> absents de ce dépôt — le champ reste éditable et la valeur saisie est écrite
> dans `res_company.server_env_defaults`, qui est un champ **stocké**.

### 2. Odoo joignable en HTTPS

Le téléphone doit atteindre Odoo, et **en HTTPS** : le contenu des messages et
les numéros y transitent. Le plugin mobile refuse le HTTP en clair, à deux
exceptions près — les adresses de bouclage, et le réseau local si l'exploitant
l'a explicitement autorisé pour une démonstration.

Rien d'autre n'est à installer. Pas de serveur intermédiaire, pas de courtier de
messages : le module expose trois routes sur l'Odoo existant.

### 3. Côté Odoo

1. Installer le module. Il dépend de `sms_twilio`, qui est le module cœur
   introduisant le champ `res.company.sms_provider` ; Twilio reste inutilisé.
2. **Réglages → Général → SMS** : choisir « Passerelle mobile ERPLibre ».
3. **Passerelle mobile → Configuration → Passerelles** : créer la fiche et régler
   l'intervalle d'interrogation. Noter l'**identifiant d'appareil** généré.
4. Renseigner un **canal d'escalade indépendant** — un point d'accès HTTP vers
   un fournisseur de SMS payant, ou tout autre canal qui ne dépend pas de cette
   passerelle. Sans lui, l'alerte de panne part par courriel, c'est-à-dire par
   le canal que la passerelle était censée compléter.
5. Restreindre le droit d'envoi : groupe « Passerelle mobile / Envoi », et au besoin
   la liste « Utilisateurs autorisés » de la fiche.

Le module ramène aussi le cron d'envoi du cœur de **1 heure à 2 minutes**
(`post_init_hook`). Ce cron est déclaré `noupdate="1"` dans le cœur : une
surcharge XML fonctionnerait à l'installation mais serait ignorée à chaque mise à
jour, d'où le hook.

### 4. Côté téléphone

Un appareil dédié, sur secteur, verrouillé, rangé hors de portée. Android 8
minimum.

1. Installer l'APK ERPLibre.
2. Accorder les permissions d'**envoi** et de **réception** de SMS. La réception
   sert uniquement à honorer les STOP.
3. Renseigner trois valeurs, et trois seulement : **URL d'Odoo**, **secret
   partagé**, **identifiant d'appareil**. Elles doivent correspondre exactement
   à ce que connaît Odoo — un écart donne un 401 pour le secret, un 404 pour
   l'identifiant.
   Pour mesurer la durée des appels, accorder aussi la permission d'appel et la
   lecture de l'état de la ligne.
4. Retirer l'application de l'optimisation de batterie, sinon le système tuera le
   service. Sur Samsung, Xiaomi, Oppo et Huawei, désactiver aussi le gestionnaire
   d'applications propre au constructeur.
5. Démarrer la passerelle, puis vérifier que la fiche Odoo reçoit un signal de
   vie.

## Protocole

Tout part du téléphone. Trois routes, signées en HMAC-SHA256, horodatées et
protégées du rejeu par un nonce à usage unique. La signature est portée par
l'en-tête `X-Erplibre-Signature` et couvre le corps brut de la requête.

Les routes gardent leur préfixe `/erplibre_sms/` bien que le module ait été
renommé : c'est un protocole, et tout téléphone déjà installé continue de les
appeler.

| Route | Contenu |
|---|---|
| `POST /erplibre_sms/report` | états d'envoi, avec un numéro de séquence par message |
| `POST /erplibre_sms/poll` | réclame les envois en attente, et porte au passage permission, SIM, file d'attente et batterie |
| `POST /erplibre_sms/inbound` | SMS reçus, dont les STOP |

Un rapport **sans numéro de séquence est refusé** : il ne peut pas être ordonné,
donc rien ne prouve qu'il n'est pas un rejeu.

## Limites assumées

- **Aucun accusé de livraison sur long code ne prouve la non-livraison.** Un
  `RESULT_OK` signifie « accepté par le modem », pas « reçu par l'étudiant ». Une
  SIM sans crédit et le filtrage A2P de l'opérateur restent donc difficiles à
  détecter par les seuls accusés — c'est le signal de vie et l'échéance d'envoi
  qui les rattrapent, pas les accusés.
- **Les conditions d'usage des forfaits mobiles grand public interdisent
  généralement l'envoi automatisé.** Un forfait d'affaires ou machine-à-machine
  est préférable. Une ligne suspendue coupe le canal sans avis.
- **Les SMS entrants restent visibles dans l'application Messages du
  téléphone** : l'application n'est pas, et ne doit pas devenir, le gestionnaire
  de SMS par défaut — elle recevrait alors tous les codes d'authentification du
  téléphone. Les réponses des parents sont donc lisibles sur l'écran de veille :
  l'appareil doit être verrouillé.
- **Un plugin SMS Android casse à chaque version majeure d'Android.** Prévoir une
  revérification annuelle du type de service de premier plan, du modèle de
  permissions et de l'hibernation d'applications.

## Tests

```bash
odoo -d <base> -i erplibre_mobile_gateway \
     --test-enable --test-tags /erplibre_mobile_gateway
```

Le test à ne jamais laisser échouer est
`test_late_delivered_cannot_overwrite_failed` : il vérifie qu'un rapport
`delivered` rejoué après un `failed` ne fait pas croire que les étudiants ont été
prévenus.
