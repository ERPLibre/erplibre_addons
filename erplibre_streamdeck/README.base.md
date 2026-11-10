<!---------------------------->
<!-- multilingual suffix: en, fr -->
<!-- no suffix: en -->
<!---------------------------->

<!-- [en] -->

# ERPLibre — Stream Deck

The base of the inventory of the employees' Stream Decks: which workstation
each deck is plugged into, which program drives it and whether its service
runs. The inventory belongs to its employee; a manager sees the whole fleet.

This version holds **no model and no menu**: it ships the access vocabulary
that the inventory builds on, and that `erplibre_streamdeck_devops_requirement`
depends on.

## Groups

The category **Stream Deck** carries two groups:

| Group | Who | Role |
|---|---|---|
| `group_streamdeck_user` "User" | every internal user, through `base.group_user` | owns their workstations and their decks |
| `group_streamdeck_manager` "Manager" | the administrator at installation; implies "User" | sees the workstations and the decks of everyone |

`base.group_user` implies the user group: every employee is a Stream Deck
user without any further setting, and the employees that exist at
installation receive the group too. A portal or public user never receives
it.

<!-- [fr] -->

# ERPLibre — Stream Deck

La base de l'inventaire des Stream Deck des employés : à quel poste chaque
deck est branché, quel programme le pilote et si son service tourne.
L'inventaire appartient à son employé ; un gestionnaire voit tout le parc.

Cette version ne contient **aucun modèle ni aucun menu** : elle livre le
vocabulaire d'accès sur lequel l'inventaire se bâtit, et dont dépend
`erplibre_streamdeck_devops_requirement`.

## Groupes

La catégorie **Stream Deck** porte deux groupes :

| Groupe | Qui | Rôle |
|---|---|---|
| `group_streamdeck_user` « Utilisateur » | tout utilisateur interne, par `base.group_user` | possède ses postes et ses decks |
| `group_streamdeck_manager` « Gestionnaire » | l'administrateur à l'installation ; implique « Utilisateur » | voit les postes et les decks de tous |

`base.group_user` implique le groupe utilisateur : tout employé est
utilisateur Stream Deck sans autre réglage, et les employés qui existent à
l'installation reçoivent eux aussi le groupe. Un utilisateur portail ou
public ne le reçoit jamais.
