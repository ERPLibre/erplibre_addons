

# ERPLibre — Stream Deck

L'inventaire des Stream Deck des employés. Chaque poste qui fait tourner
l'extension GNOME [ERPLibre Home](https://github.com/TechnoLibre/erplibre-home-gnome-extension)
s'inscrit auprès de cette base, puis y remonte son état et les événements de
ses decks : quels decks sont branchés, depuis quand, quel programme les
pilote et si leur service tourne. Odoo n'ouvre jamais de connexion vers un
poste.

Odoo porte aussi les réglages du deck qu'il veut sur chaque poste : le
programme du deck, les plugins coupés, le rafraîchissement de session,
les jeux et la disposition des touches d'accueil de chaque modèle de
deck. Le poste les reçoit dans la réponse à sa remontée, et son employé
les applique d'un clic (voir Configuration).

L'inventaire appartient à son employé ; un gestionnaire voit tout le parc.
Personne ne l'écrit à la main : seules les routes des postes l'écrivent.

## Menus

| Menu | Qui | Contenu |
|---|---|---|
| Stream Deck › Mes postes | tout employé | ses postes ; le bouton *Ajouter un poste* affiche un code d'appairage |
| Stream Deck › Mes decks | tout employé | les decks que ses postes tiennent ou ont tenus |
| Stream Deck › Parc › Postes, Decks, Événements | gestionnaire | tout, en lecture, sauf le nom, l'archivage, le jeton et la configuration d'un poste |
| Stream Deck › Configuration › Profils, Modèles de deck, Dispositions des touches, Catalogue, Premier pilotage | gestionnaire | les couches de configuration : les profils réutilisables, et les réglages de chaque modèle de deck ; toutes les dispositions des touches et le catalogue où elles choisissent ; la politique du premier pilotage |
| Stream Deck › Paramètres | administrateur | la section *Stream Deck* des Paramètres : la surveillance et le premier pilotage |

Un poste montre ce que disait sa dernière remontée : système
d'exploitation, versions de GNOME Shell, de l'extension et du contrat,
branche et commit du checkout ERPLibre, programme du deck et état de son
service depuis quand, ses decks et ses événements. Son employé peut le
renommer et révoquer son jeton ; le gestionnaire peut aussi l'archiver.
*Parc › Postes* ajoute la colonne *Muet depuis* et le filtre *Muets*. Les
filtres *Configuration en attente* et *Configuration refusée* choisissent
les postes par l'état de leur configuration, et l'onglet *Configuration*
d'un poste montre son profil, ses réglages effectifs avec la couche et le
verrou de chacun, ses surcharges, la disposition des touches de chaque
deck branché, ses propres dispositions et l'état de la révision qui lui
est proposée.

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
| Utilisateur (tout utilisateur interne) | les siens : lire, renommer, révoquer le jeton, choisir un profil « au choix », surcharger les réglages libres | ceux que ses postes tiennent ou ont tenus, en lecture | ceux de ses postes, et ceux d'un deck qu'il détient ou a détenu, à partir de sa première détention |
| Gestionnaire | tous : lire, renommer, archiver, révoquer le jeton, assigner n'importe quel profil, surcharger et verrouiller les réglages | tous, en lecture | tous, en lecture |

Un deck prêté à un autre employé suit le poste qui le tient. Chaque
employé lit l'historique d'un deck à partir du moment où un de ses postes
l'a détenu pour la première fois : la création du deck sur ce poste, ou
l'événement *Changé de poste* qui l'y a amené. Odoo date ce moment
lui-même, jamais avec une heure envoyée par le poste, et le garde quand le
deck revient après un prêt. Le prêteur lit donc toujours le deck et tout
son historique depuis sa première détention, y compris les événements
survenus à l'autre poste : chaque événement porte une copie du nom de son
poste et de son employé, si bien que le prêteur n'a pas besoin de la fiche
de l'autre poste, et ne la reçoit pas. L'emprunteur ne lit rien d'avant
son arrivée. Un poste qui envoie seulement un événement portant le numéro
de série d'un deck tenu ailleurs lit cet événement et le nom du deck qu'il
porte, jamais la fiche du deck ni son historique.

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

Les couches de configuration. Un gestionnaire crée et modifie les
profils, les modèles de deck et toute ligne de réglage, et lui seul pose
un verrou. Un employé lit les profils « au choix », le profil de chacun
de ses postes et toutes les couches modèle, qui ne portent rien de
personnel ; jamais un profil assigné seulement au poste d'un autre
employé, ni les surcharges d'un autre employé. Sur ses propres postes, il
crée, modifie et supprime les surcharges des réglages qu'aucune couche ne
verrouille, jamais *Verrouillé* ni *Source*. Il choisit un profil « au
choix », seulement à la place d'aucun profil ou d'un autre profil « au
choix » : un profil que le gestionnaire a assigné sans le rendre « au
choix » reste, et un employé ne retire jamais un profil. L'état de la
configuration (révisions, valeurs proposées et appliquées, état, raison,
choix du premier pilotage) n'est écrit que par la route de remontée.

Les dispositions des touches suivent les mêmes règles, le verrou portant
sur une disposition entière : un employé lit les dispositions des couches
qu'il lit, et sur ses propres postes crée, modifie et supprime les
dispositions, et leurs touches, des modèles de deck qu'aucune couche ne
verrouille, jamais *Verrouillé*, *Source* ni *Gardée dans le fichier du
poste*. Seule la route de remontée ajoute au catalogue. L'identifiant
d'un plugin est le nom de son fichier, et le répertoire de plugins de
l'utilisateur tient les fichiers de son choix : un employé lit les
actions `plugin:<id>` qu'offrent ses propres postes, jamais celles
qu'offrent seulement ceux d'un autre employé, et n'en nomme aucune autre
dans une touche ; le reste du catalogue, tout le monde le lit.

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
| Deck changé de poste | *Deck changé de poste*, sur le deck | à la remontée qui déplace le deck | par une personne ; tant qu'une est ouverte, quel que soit son destinataire, un nouveau déplacement n'en ouvre aucune et ajoute une note au fil du deck |

- **Destinataire.** *Employé* : l'employé du poste, ou du poste qui tient
  le deck ; pour un déplacement, le nouveau détenteur, le prêteur
  l'apprend par l'historique. *Gestionnaire*, par défaut : l'utilisateur
  nommé dans les Paramètres. *Employé et gestionnaire* : une activité à
  chacun.
- **Jamais de doublon.** Un enregistrement a au plus une activité ouverte
  d'un type par destinataire. Un deck qui a une activité *Deck changé de
  poste* ouverte n'en ouvre aucune autre à un nouveau déplacement, même
  pour un autre détenteur : le déplacement s'ajoute en note au fil du
  deck. Une activité *Service du deck en échec* ou *Deck débranché
  longtemps* marquée faite pendant que son problème dure se rouvre au
  passage suivant du cron ; un silence n'ouvre son activité qu'une fois.
- **Fermeture.** Une activité fermée reste faite, avec le retour « Résolu
  à <heure> : <ce qui s'est passé> », l'heure dans le fuseau du
  destinataire (UTC à défaut) et le texte dans sa langue. Archiver un
  poste ou son employé, ou révoquer son jeton, ferme ses activités et les
  activités *Deck débranché longtemps* de ses decks avec « le poste est
  archivé » ou « le poste est désinscrit ». Archiver un utilisateur,
  depuis les Paramètres ou par son départ, ferme les activités qui lui
  restent, *Deck changé de poste* compris, avec « l'utilisateur assigné
  est archivé », là où Odoo les supprimerait. La fermeture ne dépend pas
  des Paramètres : une activité ouverte avant leur désactivation se ferme
  encore.
- **Gestionnaire archivé.** Si le gestionnaire nommé est archivé ensuite,
  seule la part de l'employé s'ouvre, et chaque passage du cron écrit au
  journal un avertissement qui ne nomme personne.
- **Accès.** Une activité se lit avec son enregistrement. Un employé lit
  les activités de ses postes, celles du gestionnaire comprises, et celles
  des decks qu'il détient ou a détenus, à partir de sa première détention,
  plus celles qui lui sont assignées ; jamais celles du poste d'un autre
  employé. Le reste du fil d'un deck, ses messages et ses fichiers joints,
  se lit lui aussi à partir de la première détention, le message qui ferme
  une activité comptant de l'ouverture de celle-ci. Au fil d'un poste,
  l'employé publie, modifie ses propres messages et ferme ses propres
  activités ; seul un gestionnaire modifie, ferme ou supprime ceux des
  autres. Seule la surveillance crée des activités de ses quatre types.
- **Notification.** Odoo prévient le destinataire d'une nouvelle activité
  comme pour toute activité (boîte de réception ou courriel, selon sa
  préférence). Le module n'envoie aucun courriel ni aucune notification
  de son côté. Ce courriel passe par la file des courriels d'Odoo : ni une
  remontée ni le cron n'attendent le serveur de courriel.

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
| Premier pilotage | `first_pilot_policy` | Demander à l'employé | Garder les valeurs locales, Prendre les valeurs d'Odoo ; voir Configuration |

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

## Configuration

Odoo gère une liste fermée de quatre réglages, chacun une ligne du
fichier `~/.config/erplibre-home/streamdeck.conf` du poste :

| Réglage | Clé du fil | Ligne du fichier | Valeurs | Redémarre le service du deck |
|---|---|---|---|---|
| Programme du deck | `deck_program` | `DECK_PROGRAM` | `tiler`, `controller`, `none` | oui |
| Plugins coupés | `plugins_off` | `DECK_PLUGINS_OFF` | au plus 64 identifiants de plugins `[a-z][a-z0-9_]{0,63}`, joints par des virgules | oui |
| Rafraîchissement de session (secondes) | `session_refresh_sec` | `DECK_SESSION_REFRESH_SEC` | un nombre de 0.5 à 60 | oui |
| Jeux | `games` | `GAMES` | `on`, `off` | non |

Aucun chemin, aucune commande et aucun plugin à activer : Odoo ne peut
rien faire exécuter sur un poste. Une valeur se tape nue dans une ligne
(un mot, des identifiants de plugins séparés par des virgules, un nombre)
et se range en JSON ; une valeur hors de cette liste est refusée à
l'écriture. L'onglet *Configuration* liste les plugins que le poste a
trouvés sur son disque.

### Couches et verrous

Un réglage prend sa valeur de la dernière des trois couches qui le fixe :

1. le **profil** du poste (*Configuration › Profils*) ; un profil archivé
   ne compte pour rien ;
2. le **modèle de deck** : les réglages du modèle de chaque deck branché
   (*Configuration › Modèles de deck*, par identifiant produit USB). Avec
   des decks de plusieurs modèles, leurs couches s'appliquent par
   identifiant produit croissant, le plus grand l'emportant, et la fiche
   du poste en avertit ;
3. le **poste** lui-même : ses surcharges, dans son onglet
   *Configuration*.

Une ligne cochée *Verrouillé* arrête là son réglage : une ligne de profil
verrouillée ignore les modèles et le poste, une ligne de modèle
verrouillée ignore les modèles suivants et le poste. Seul un gestionnaire
pose un verrou. Un réglage qu'aucune couche ne fixe reste à l'employé,
sur le poste, et Odoo ne l'adopte jamais.

Un profil coché *Au choix* est proposé aux employés, qui en choisissent
chacun un pour leurs propres postes. Le gestionnaire assigne n'importe
quel profil à n'importe quel poste.

### Proposition et application

À chaque remontée du pilote, Odoo calcule la configuration effective du
poste. Quand son SHA-256 diffère de la dernière proposée, la *Révision
proposée* augmente de un. La réponse porte la révision et l'extension
l'annonce ; rien ne change sur le poste tant que son employé n'a pas
cliqué *Appliquer*. L'extension réécrit alors les lignes gérées de
`streamdeck.conf`, garde toute autre ligne, et redémarre le service du
deck quand un réglage qui l'exige a changé et que le service tourne ; un
service du deck arrêté n'est jamais démarré. Sa remontée suivante dit si
la révision a été appliquée ou refusée, et pourquoi.

| Configuration | Sens |
|---|---|
| Non gérée | aucune couche ne fixe de réglage du poste, il n'a jamais remonté en protocole 1.1, ou son extension ne coche pas cette base comme pilote ; une révision jusque-là en attente est retirée |
| En attente | une révision est proposée et pas encore appliquée, depuis *Configuration en attente depuis* |
| Appliquée | le poste a appliqué la révision proposée |
| Refusée | le poste l'a refusée ; *Raison du refus* dit pourquoi : `invalid:<clé>` (`invalid:key_layouts` pour les dispositions des touches), `write_failed`, `restart_failed` ou `unit_missing` |
| Changée localement | un réglage a changé dans le fichier ; Odoo le propose de nouveau |

Une extension plus ancienne que le contrat 1.3 remonte sans être pilotée,
et la fiche dit qu'elle est trop ancienne. Une extension du contrat 1.3
est pilotée sans les dispositions des touches, qui commencent au contrat
1.4 (protocole 1.2).

### Premier pilotage

La première fois qu'un poste est piloté, ses réglages libres peuvent
porter des valeurs locales qui diffèrent de celles d'Odoo. Le
gestionnaire du Stream Deck en décide dans *Stream Deck › Configuration ›
Premier pilotage*, comme l'administrateur des Paramètres dans
*Paramètres › Stream Deck* :

- **Demander à l'employé**, le défaut : l'extension demande une seule fois
  s'il garde les valeurs locales, qui deviennent alors des surcharges du
  poste de source *Fichier du poste*, ou s'il prend celles d'Odoo. La
  fiche dit qu'Odoo attend ce choix et nomme les réglages concernés.
- **Garder les valeurs locales** : Odoo les adopte aussitôt, sans
  demander.
- **Prendre les valeurs d'Odoo** : rien n'est adopté.

Une valeur locale vide, ou déjà celle d'Odoo, ne pose aucune question.
Les réglages verrouillés sont toujours proposés à la confirmation
habituelle, quel que soit le choix. Le poste garde la réponse dans *Choix
du premier pilotage* ; appliquer une première révision vaut *Prendre les
valeurs d'Odoo*.

### Changements locaux

Après l'application d'une révision, un réglage géré changé dans le
fichier, depuis le menu TODO › Stream Deck par exemple, se traite à la
remontée suivante :

- un réglage **libre** devient une surcharge du poste, de source *Fichier
  du poste*, sans question : la révision suivante égale le fichier, et
  l'extension la note appliquée sans rien annoncer ;
- un réglage **verrouillé**, ou un réglage retiré du fichier ou rendu
  invalide, est proposé de nouveau sous une nouvelle révision, que
  l'employé confirme comme toute autre.

### Dispositions des touches

L'écran d'accueil de chaque modèle de deck se dispose dans Odoo. Une
disposition des touches vaut pour un identifiant produit USB et
appartient à un profil, à un modèle de deck ou à un poste : l'onglet
*Dispositions des touches* de chacun, ou *Configuration › Dispositions
des touches*. Sa fiche liste une ligne par touche : l'index (0 la touche
en haut à gauche, numérotées rangée par rangée), l'action et l'icône
choisies dans le catalogue, et un libellé d'au plus 16 caractères sans
caractère de contrôle. *Créer les touches* ajoute une ligne vide pour
chaque touche du modèle, et l'aperçu montre la grille. Une action est la
touche d'accueil d'un plugin (`plugin:<id>`), une touche du tableau de
bord (`tiles`) ou une touche noire (`empty`) ; une touche sans action est
laissée au programme du deck, qui y place ses fixtures et son tableau de
bord. Un plugin a au plus une touche d'accueil par disposition, et un
plugin que la disposition ne nomme pas n'en a aucune : la fiche avertit
des *Plugins sans touche*, parmi les plugins qu'offre son propre poste
pour la disposition d'un poste, sinon parmi ceux qu'un poste offre dans
sa dernière remontée.

Les dispositions d'un modèle se replient comme les réglages, profil <
modèle de deck < poste, et *Verrouillé* tient la disposition entière :
une disposition verrouillée arrête le repli pour son modèle. La touche
d'accueil d'un plugin coupé, par Odoo ou sinon par le fichier du poste,
part comme une touche noire : le poste refuse une disposition qui nomme
un plugin coupé. Seules les
dispositions des decks branchés vont au poste, dans le réglage
`key_layouts` de la révision, verrouillé quand l'une d'elles l'est ;
l'extension les écrit dans `~/.config/erplibre-home/keymap.json` quand
l'employé applique la révision, et y garde les dispositions des modèles
qu'Odoo n'envoie pas. Odoo ne retire jamais une disposition du fichier :
un modèle qu'aucune couche ne dispose, ou ne dispose plus, y garde la
dernière disposition appliquée, et un modèle que le fichier ne nomme
pas prend la disposition automatique du programme du deck.
L'onglet *Configuration* du poste le dit pour chaque modèle branché
auquel Odoo n'envoie pas de disposition.

Chaque poste reçoit les dispositions dans les limites du catalogue de sa
propre remontée, puisqu'il refuse la révision entière pour une touche que
son programme du deck ne sait pas disposer : un modèle que ce catalogue
ne décrit pas ne reçoit aucune disposition, une touche au-delà de son
nombre de touches est laissée de côté, une action qui lui manque part
comme une touche noire, comme le programme du deck la montrerait, et une
icône qui lui manque est laissée de côté. Une remontée sans catalogue ne
reçoit aucune disposition ; ses réglages partent quand même.

Le catalogue (*Configuration › Catalogue*) est l'union de ce que
remontent les postes : les actions, les icônes et la géométrie de chaque
modèle de deck. Un élément qu'aucun poste ne remonte plus reste, avec la
date où il a été vu la dernière fois, à l'heure près ; une action garde
les postes dont la dernière remontée l'a offerte (*Offert par*). La géométrie d'un
modèle est une constante de son matériel : un modèle de la table livrée
avec le module prend celle de la table, et un modèle hors de la table
garde la géométrie remontée la première. Aucune remontée ne la change :
aucun poste ne décide des touches qu'Odoo dispose pour les autres.

Une disposition changée dans le fichier après l'application de sa
révision se traite comme un réglage, par le SHA-256 de la disposition de
chaque modèle (JSON canonique : clés triées, sans espace, tout caractère
hors ASCII échappé en `\uXXXX`) :

- une disposition **libre** devient une disposition du poste marquée
  *Gardée dans le fichier du poste*, de source *Fichier du poste*, et
  Odoo n'envoie plus de disposition pour ce modèle ; créer ou changer une
  de ses touches la renvoie. Odoo ne tient pas les touches d'une telle
  disposition, qui ne prend donc aucun verrou d'ici là : un verrou qu'il
  ne pourrait jamais reproposer laisserait passer une modification à la
  main ;
- une disposition **verrouillée**, ou retirée du fichier, est proposée de
  nouveau.

La question du premier pilotage couvre les dispositions libres comme les
réglages libres : une disposition libre du fichier dont l'empreinte
diffère de celle d'Odoo met `key_layouts` dans `ask`, sauf si une des
dispositions envoyées est verrouillée, et garder les valeurs locales
l'adopte comme plus haut. Un poste piloté avant le protocole 1.2 a déjà
fait son choix : une disposition suit alors la règle d'un réglage
nouvellement géré, proposée sous une nouvelle révision.

### Historique de la configuration

| Événement | Quand |
|---|---|
| *Configuration appliquée* (`config_applied`) | le poste remonte la révision proposée appliquée ; avec sa révision |
| *Configuration refusée* (`config_refused`) | le poste la remonte refusée ; avec sa révision et sa raison |
| *Réglage local adopté* (`config_adopted`) | une valeur locale libre devient une surcharge ; avec ses réglages, `key_layouts:<identifiant produit>` pour une disposition gardée dans le fichier |
| *Réglage changé localement* (`config_drift`) | un réglage verrouillé, ou retiré, est proposé de nouveau ; avec ses réglages, `key_layouts:<identifiant produit>` pour une disposition |

Odoo seul les écrit, et ils n'ouvrent aucune activité : l'état se lit
sur le poste. L'historique filtre sur chacun d'eux.

## Protocole de remontée 1.2

Le [CONTRACT.md](https://github.com/TechnoLibre/erplibre-home-gnome-extension/blob/main/CONTRACT.md)
de l'extension décrit le même protocole du côté du poste.

Le client envoie d'abord `GET <url>/web/login?db=<base>` avec un pot à
témoins pour choisir la base, puis chaque appel est un `POST` d'un objet
JSON, auquel répond un objet JSON, sous `/streamdeck/v1/`. Toute autre
méthode HTTP reçoit 405. Chaque corps porte `"protocol"` : `"1.2"` pour
un poste qui reçoit les dispositions des touches, `"1.1"` pour un poste
qui ne reçoit que les réglages, `"1.0"` avant : une version majeure
inconnue est refusée, une version mineure plus récente est acceptée et ses
clés inconnues ignorées. Chaque réponse porte `"protocol": "1.2"` ; une
réponse d'erreur y ajoute `error`.

| Route | Authentification | Corps | Réponse 200 |
|---|---|---|---|
| `enroll` | les identifiants de la méthode | `method` (`pairing_code`, `api_key` ou `password`), `code`, `key` ou `login` + `password`, `fingerprint`, `hostname` | `workstation_id`, `token` |
| `report` | `Authorization: Bearer <jeton>` | `state`, `events`, `lost_events`, `config` (1.1) | `accepted` (les uuid des événements), `heartbeat_s` (900), `config` (1.1, au pilote d'un poste configuré) |
| `unenroll` | `Authorization: Bearer <jeton>` | rien d'autre | rien d'autre ; le jeton est révoqué |

- `fingerprint` : 64 chiffres hexadécimaux en minuscules, le HMAC-SHA256
  de l'identifiant de la machine avec pour clé l'utilisateur Linux, l'URL
  et la base ; l'identifiant brut ne quitte jamais le poste.
- `state` : nom d'hôte, système d'exploitation, versions de GNOME Shell, de
  l'extension et du contrat, branche et commit ERPLibre, programme du
  deck, état du service (`active`, `failed`, `inactive`, `absent`) et les
  decks branchés en ce moment (numéro de série, identifiant produit USB,
  chemin USB, firmware). Les decks du poste absents de la liste deviennent
  débranchés. En 1.1, `deck_plugins` liste au plus 128 identifiants des
  plugins du deck trouvés sur le disque du poste ; ses répétitions sont
  écartées. En 1.2, `deck_catalog` est le catalogue du programme du
  deck, `{"format": 1, "actions", "icons", "models": {<identifiant
  produit>: {"cols", "rows", "keys"}}}`, ajouté au catalogue d'Odoo ;
  plus grand que 32 Kio, ou d'un autre format, il est ignoré, et une
  action ou une icône d'une forme inconnue est sautée, comme un modèle
  dont la géométrie n'accueille aucune touche (aucune touche, ou plus de
  touches que de cases). Les nombres d'une géométrie sont des entiers de
  0 à 256 ; tout autre cas est un 400 `bad_request`.
- `events` : `plugged`, `unplugged` ou `service_changed`, chacun avec son
  propre uuid et l'heure où il a été observé. `moved`, `silent`,
  `heard_again` et les quatre sortes `config_*` ne sont écrits que par
  Odoo : une remontée qui en porte un est un 400 `bad_request`. Un uuid déjà
  enregistré est accusé de nouveau sans changement : une remontée renvoyée
  ne crée rien. Une heure de plus de 5 minutes en avance sur la réception
  est remplacée par l'heure de réception.
- `lost_events` : le total cumulé des événements que le poste a abandonnés
  sans les envoyer ; Odoo garde le plus grand total reçu.
- `config` (1.1, ignoré dans un corps 1.0) : `{"pilot": false}` d'une
  destination qui n'est pas le pilote du poste, qui ne reçoit aucun
  `config` en retour. Du pilote, `{"pilot": true, "revision_applied",
  "current", "result", "choice"}` : `current` les quatre réglages tels que
  le fichier les porte, null quand absents ou invalides ; `result` l'issue
  de la dernière révision, `{"revision", "status", "reason", "at"}` avec
  `status` `applied` ou `refused` ; `choice` la réponse à la question du
  premier pilotage, `keep_local` ou `take_odoo`, envoyée une fois. Une
  valeur hors du schéma, ou un statut, une raison ou un choix inconnu, est
  un 400 `bad_request` ; une clé hors des quatre réglages est ignorée. En
  1.2, `current.key_layouts` associe l'identifiant produit de chaque
  disposition de `keymap.json` au SHA-256 de cette disposition, null
  quand le fichier n'en porte pas (au plus 128), et la raison
  `invalid:key_layouts` est connue.
- `config` de la réponse : `{"revision", "hash", "settings", "locked"}`,
  plus `ask` pendant un premier pilotage sous *Demander à l'employé*.
  `hash` est le SHA-256 du JSON canonique de `settings` (clés triées, sans
  espace), `locked` les réglages verrouillés, `ask` les réglages libres
  dont la valeur locale diffère de celle d'Odoo, `key_layouts` compris.
  En 1.2, `settings.key_layouts` associe l'identifiant produit de chaque
  deck branché qu'Odoo dispose, dans les limites du catalogue de la
  remontée, à `{"keys": [{"key", "action", "icon",
  "label"}]}`, par touche croissante, `icon` et `label` seulement quand
  ils sont fixés, au plus 16 modèles ; `locked` liste alors
  `key_layouts` quand une de ces dispositions est verrouillée.
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