

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
