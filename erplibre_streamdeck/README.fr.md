

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