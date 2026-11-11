

# ERPLibre — Stream Deck

L'inventaire des Stream Deck des employés. Chaque poste qui fait tourner
l'extension GNOME [ERPLibre Home](https://github.com/TechnoLibre/erplibre-home-gnome-extension)
s'inscrit auprès de cette base, puis y remonte son état et les événements de
ses decks : quels decks sont branchés, depuis quand, quel programme les
pilote et si leur service tourne. Odoo n'ouvre jamais de connexion vers un
poste.

L'inventaire appartient à son employé ; un gestionnaire voit tout le parc.
Personne ne l'écrit à la main : seules les routes des postes l'écrivent.

## Menus

| Menu | Qui | Contenu |
|---|---|---|
| Stream Deck › Mes postes | tout employé | ses postes ; le bouton *Ajouter un poste* affiche un code d'appairage |
| Stream Deck › Mes decks | tout employé | les decks que ses postes tiennent ou ont tenus |
| Stream Deck › Parc › Postes, Decks, Événements | gestionnaire | tout, en lecture, sauf le nom, l'archivage et le jeton d'un poste |
| Stream Deck › Paramètres | administrateur | la section *Stream Deck* des Paramètres : la surveillance |

Un poste montre ce que disait sa dernière remontée : système
d'exploitation, versions de GNOME Shell, de l'extension et du contrat,
branche et commit du checkout ERPLibre, programme du deck et état de son
service depuis quand, ses decks et ses événements. Son employé peut le
renommer et révoquer son jeton ; le gestionnaire peut aussi l'archiver.
*Parc › Postes* ajoute la colonne *Muet depuis* et le filtre *Muets*.

Un poste et un deck portent chacun leur fil, où la surveillance pose ses
activités et ses notes. Chaque liste d'événements nomme l'événement par
son libellé : l'état du service pour un changement de service (*Service
démarré*, *en échec*, *arrêté*, *absent*), la sorte pour tout autre ;
l'historique filtre sur chaque libellé.

## Inscrire un poste

Dans les préférences de l'extension, page *Inventaire Odoo*, ajouter cette
base par son URL et le nom de la base, puis choisir l'une des trois
méthodes :

- **Code d'appairage** : *Mes postes › Ajouter un poste* affiche un code de
  8 caractères, valable 10 minutes, une seule fois, pour l'employé qui l'a
  demandé.
- **Clé d'API** de l'employé (*Préférences › Sécurité du compte*).
- **Identifiant et mot de passe** de l'employé. Un compte dont l'accès RPC
  est limité aux clés d'API, comme avec l'authentification à deux
  facteurs, passe par l'une des deux autres méthodes.

La clé ou le mot de passe ne sert qu'à l'inscription et n'est gardé nulle
part. L'inscription rend un **jeton de poste**, que l'extension garde dans
le trousseau GNOME ; Odoo n'en garde que le SHA-256. Réinscrire le même
poste garde sa fiche et remplace son jeton. Des identifiants erronés
répétés depuis une même adresse sont soumis à la temporisation des
connexions d'Odoo.

## Accès

| Groupe | Postes | Decks | Événements |
|---|---|---|---|
| Utilisateur (tout utilisateur interne) | les siens : lire, renommer, révoquer le jeton | ceux que ses postes tiennent ou ont tenus, en lecture | ceux de ses postes, et ceux d'un deck qu'il détient ou a détenu, à partir de sa première détention |
| Gestionnaire | tous : lire, renommer, archiver, révoquer le jeton | tous, en lecture | tous, en lecture |

Un deck prêté à un autre employé suit le poste qui le tient. Chaque
employé lit l'historique d'un deck à partir du moment où un de ses postes
l'a détenu pour la première fois : la création du deck sur ce poste, ou
l'événement *Changé de poste* qui l'y a amené. Odoo date ce moment
lui-même, jamais avec une heure envoyée par le poste, et le garde quand le
deck revient après un prêt. Le prêteur lit donc toujours le deck et tout
son historique depuis sa première détention, y compris les événements
survenus à l'autre poste : chaque événement porte une copie du nom de son
poste et de son employé, si bien que le prêteur n'a pas besoin de la fiche
de l'autre poste, et ne la reçoit pas. L'emprunteur, ou un poste qui
déclare le numéro de série d'un autre deck, ne lit rien d'avant son
arrivée.

Quand un poste remonte un deck que tient un autre poste, le deck passe à ce
poste sans confirmation, et Odoo ajoute un événement *Changé de poste*
(`moved`) daté de la réception. Il nomme le nouveau poste et son employé,
et le poste que le deck a quitté, chacun par une copie de son nom. Son
employé devient détenteur du deck à ce moment, à moins de l'avoir détenu
avant ; l'employé de l'ancien poste lit toujours le deck et son
historique, même si ce poste n'en a jamais envoyé d'événement. Le même
poste qui remonte de nouveau le deck ne déplace rien.

Archiver un utilisateur archive ses postes et révoque leurs jetons ; les
postes, leurs decks et leurs événements restent lisibles du gestionnaire.
Les codes d'appairage ne sont lisibles de personne.

## Surveillance

Odoo surveille quatre problèmes : un service du deck qui reste en échec,
un poste muet, un deck débranché longtemps et un deck changé de poste. Il
écrit toujours l'historique. Il n'ouvre d'activités Odoo que si
*Paramètres › Stream Deck* les active, ce qui n'est pas le cas par défaut.

### L'historique, toujours

| Événement | Écrit par | Quand |
|---|---|---|
| *Service démarré*, *en échec*, *arrêté*, *absent* (`service_changed`) | le poste | son service du deck change d'état |
| *Poste muet* (`silent`) | Odoo | le poste n'a envoyé aucune remontée pendant le délai de silence ; daté de la fin de ce délai après sa dernière remontée |
| *Poste revenu* (`heard_again`) | Odoo | la première remontée après un silence ; daté de sa réception |
| *Changé de poste* (`moved`) | Odoo | un poste remonte un deck que tient un autre poste (voir Accès) |

Un deck débranché longtemps n'a pas d'événement à lui : son événement
`unplugged` le date déjà.

Le cron *Stream Deck : surveiller les postes et les decks* tourne toutes
les 5 minutes, ce qui donne la granularité de chaque délai. Il marque un
poste muet une seule fois (*Muet depuis*) ; sa remontée suivante efface la
marque, tout comme son archivage et le retrait de son jeton. Un poste
archivé, sans jeton (désinscrit ou révoqué) ou qui n'a jamais remonté ne
devient jamais muet. L'extension remonte toutes les 15 minutes, et pas
pendant que l'écran est verrouillé : un poste éteint la nuit, en veille ou
verrouillé au-delà du délai devient muet, puis revient à sa remontée
suivante.

### Les activités, sur demande

| Problème | Type d'activité, sur | S'ouvre | Se ferme |
|---|---|---|---|
| Service du deck en échec | *Service du deck en échec*, sur le poste | le service est resté `failed` pendant son délai | seule, à la remontée qui porte un autre état |
| Poste muet | *Poste muet*, sur le poste | le poste devient muet | seule, à sa remontée suivante |
| Deck débranché longtemps | *Deck débranché longtemps*, sur le deck | le deck est débranché depuis son délai, compté de sa dernière apparition ou de son dernier événement `unplugged`, le plus récent des deux | seule, à la remontée qui le montre branché |
| Deck changé de poste | *Deck changé de poste*, sur le deck | à la remontée qui déplace le deck | par une personne ; un nouveau déplacement ajoute une note à l'activité ouverte, quel que soit son destinataire |

- **Destinataire.** *Employé* : l'employé du poste, ou du poste qui tient
  le deck ; pour un déplacement, le nouveau détenteur, le prêteur
  l'apprend par l'historique. *Gestionnaire*, par défaut : l'utilisateur
  nommé dans les Paramètres. *Employé et gestionnaire* : une activité à
  chacun.
- **Jamais de doublon.** Un enregistrement a au plus une activité ouverte
  d'un type par destinataire, et un deck une seule activité *Deck changé
  de poste* ouverte. Une activité *Service du deck en échec* ou *Deck
  débranché longtemps* marquée faite pendant que son problème dure se
  rouvre au passage suivant du cron ; un silence n'ouvre son activité
  qu'une fois.
- **Fermeture.** Une activité fermée reste faite, avec le retour « Résolu
  à <heure> : <ce qui s'est passé> », l'heure dans le fuseau du
  destinataire (UTC à défaut) et le texte dans sa langue. Archiver un
  poste ou son employé, ou révoquer son jeton, ferme ses activités et les
  activités *Deck débranché longtemps* de ses decks avec « le poste est
  archivé » ou « le poste est désinscrit ». La fermeture ne dépend pas des
  Paramètres : une activité ouverte avant leur désactivation se ferme
  encore.
- **Gestionnaire archivé.** Si le gestionnaire nommé est archivé ensuite,
  seule la part de l'employé s'ouvre, et chaque passage du cron écrit au
  journal un avertissement qui ne nomme personne.
- **Accès.** Une activité se lit avec son enregistrement. Un employé lit
  les activités de ses postes, celles du gestionnaire comprises, et
  celles des decks qu'il détient ou a détenus, à partir de sa première
  détention, plus celles qui lui sont assignées ; jamais celles du poste
  d'un autre employé. Au fil d'un poste, l'employé publie, modifie ses
  propres messages et ferme ses propres activités ; seul un gestionnaire
  modifie, ferme ou supprime ceux des autres. Seule la surveillance crée
  des activités de ses quatre types.
- **Notification.** Odoo prévient le destinataire d'une nouvelle activité
  comme pour toute activité (boîte de réception ou courriel, selon sa
  préférence). Le module n'envoie aucun courriel ni aucune notification
  de son côté.

### Paramètres › Stream Deck

Réservés aux administrateurs, comme toute la page Paramètres. Chaque
paramètre est l'`ir.config_parameter` `erplibre_streamdeck.<clé>`.

| Paramètre | Clé | Défaut | Borne |
|---|---|---|---|
| Activités de détection Stream Deck | `activities_enabled` | désactivé | — |
| Activités pour | `activity_recipient` | Gestionnaire | Employé, Gestionnaire, Employé et gestionnaire |
| Gestionnaire des activités | `activity_manager_id` | vide | requis pour activer les activités pour Gestionnaire ou Employé et gestionnaire ; proposé parmi les gestionnaires Stream Deck |
| Service du deck en échec, Poste muet, Deck changé de poste, Deck débranché longtemps | `alert_service_failed`, `alert_silent`, `alert_moved`, `alert_unplugged` | cochés | — |
| Muet après (minutes) | `silent_after_min` | 60 | 30 au moins : un battement manqué n'est pas un silence |
| Débranché longtemps après (heures) | `unplugged_after_h` | 72 | 1 au moins |
| Service en échec depuis (minutes) | `service_failed_after_min` | 10 | 0 au moins |

Le délai de silence date aussi l'événement *Poste muet* : il vaut même
activités désactivées. Les 72 heures couvrent une fin de semaine sans
alerte pour un portable emporté ; les 10 minutes laissent le service du
deck repartir seul après un échec bref.

### Ce qui reste de l'historique seulement

- Tout problème tant que les activités sont désactivées, le défaut.
- Un problème dont la case est décochée.
- Un service du deck en échec, ou un deck débranché, moins longtemps que
  son délai.
- Rien ne sort d'Odoo : ni courriel, ni notification push, ni message
  hors des activités Odoo. Les délais sont globaux, jamais par poste ni
  par employé, et la santé du deck lui-même (firmware, touches) n'est pas
  surveillée.

## Protocole de remontée 1.0

Le [CONTRACT.md](https://github.com/TechnoLibre/erplibre-home-gnome-extension/blob/main/CONTRACT.md)
de l'extension décrit le même protocole du côté du poste.

Le client envoie d'abord `GET <url>/web/login?db=<base>` avec un pot à
témoins pour choisir la base, puis chaque appel est un `POST` d'un objet
JSON, auquel répond un objet JSON, sous `/streamdeck/v1/`. Toute autre
méthode HTTP reçoit 405. Chaque corps porte `"protocol": "1.0"` : une
version majeure inconnue est refusée, une version mineure plus récente est
acceptée et ses clés inconnues ignorées. Chaque réponse porte `protocol` ;
une réponse d'erreur y ajoute `error`.

| Route | Authentification | Corps | Réponse 200 |
|---|---|---|---|
| `enroll` | les identifiants de la méthode | `method` (`pairing_code`, `api_key` ou `password`), `code`, `key` ou `login` + `password`, `fingerprint`, `hostname` | `workstation_id`, `token` |
| `report` | `Authorization: Bearer <jeton>` | `state`, `events`, `lost_events` | `accepted` (les uuid des événements), `heartbeat_s` (900) |
| `unenroll` | `Authorization: Bearer <jeton>` | rien d'autre | rien d'autre ; le jeton est révoqué |

- `fingerprint` : 64 chiffres hexadécimaux en minuscules, le HMAC-SHA256
  de l'identifiant de la machine avec pour clé l'utilisateur Linux, l'URL
  et la base ; l'identifiant brut ne quitte jamais le poste.
- `state` : nom d'hôte, système d'exploitation, versions de GNOME Shell, de
  l'extension et du contrat, branche et commit ERPLibre, programme du
  deck, état du service (`active`, `failed`, `inactive`, `absent`) et les
  decks branchés en ce moment (numéro de série, identifiant produit USB,
  chemin USB, firmware). Les decks du poste absents de la liste deviennent
  débranchés.
- `events` : `plugged`, `unplugged` ou `service_changed`, chacun avec son
  propre uuid et l'heure où il a été observé. `moved`, `silent` et
  `heard_again` ne sont écrits que par Odoo : une remontée qui en porte un
  est un 400 `bad_request`. Un uuid déjà
  enregistré est accusé de nouveau sans changement : une remontée renvoyée
  ne crée rien. Une heure de plus de 5 minutes en avance sur la réception
  est remplacée par l'heure de réception.
- `lost_events` : le total cumulé des événements que le poste a abandonnés
  sans les envoyer ; Odoo garde le plus grand total reçu.
- Un deck se reconnaît à son numéro de série, clé `sn:<numéro>` ; un deck
  sans numéro de série lisible se reconnaît à son poste, son identifiant
  produit et son chemin USB, clé `nosn:<poste>:<produit>:<chemin>`, et
  n'est jamais fusionné avec le deck d'un autre poste. Un numéro hors de
  `[A-Za-z0-9._-]{1,64}` est un 400 `bad_request` : sans `:`, il ne peut
  jamais nommer un deck sans numéro.
- Chaque texte d'un corps compte au plus 256 caractères et aucun
  caractère NUL, un identifiant produit USB a 4 chiffres hexadécimaux, et
  un deck, dans `state` comme dans un événement, porte un numéro de série
  ou un chemin USB ; tout autre cas est un 400 `bad_request` et rien
  n'est écrit.

| Statut | `error` | Sens |
|---|---|---|
| 400 | `bad_request` | le corps n'est pas du JSON, ou une valeur manque, est du mauvais type ou trop longue ; rien n'est écrit |
| 400 | `protocol_unsupported` | version majeure inconnue |
| 401 | `credentials_refused` | clé ou mot de passe erroné, code d'appairage inconnu, utilisé ou expiré, ou temporisation des connexions |
| 401 | `token_invalid` | jeton absent, inconnu ou révoqué |
| 403 | `user_inactive` | l'employé est archivé, ou n'est pas utilisateur Stream Deck (un compte portail, par exemple) |

Ni un corps, ni un en-tête, ni une réponse n'est journalisé, et chaque
réponse est marquée `Cache-Control: no-store`.

## Traductions

Le français canadien (`fr_CA`) couvre chaque terme du module : menus, vues,
champs et messages.