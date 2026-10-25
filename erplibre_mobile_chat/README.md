# ERPLibre — Clavardage mobile

L'application mobile publie dans Discuss avec un identifiant client (uuid).
Quand la réponse du serveur se perd et que l'application renvoie le même
message, un second message en double apparaîtrait.

Ce module ajoute `mail.message.erplibre_client_uuid` et accepte ce champ dans
`/mail/message/post`. `discuss.channel.message_post` rend le message déjà
publié par le même auteur, dans le même canal, avec le même identifiant, sans
publier ni notifier de nouveau. Un autre auteur ou un autre canal n'adopte pas
le message.

Le module ajoute aussi `discuss.channel.erplibre_client_uuid`. Avec
`erplibre_client_uuid` dans le contexte, `create`, `create_group` et
`channel_create` rendent le canal déjà créé par le même utilisateur avec cet
identifiant, sans le recréer, sans second message « created this channel » ni
nouvelle diffusion. Un autre utilisateur n'adopte pas le canal.

`discuss.channel.erplibre_remove_member(partner_id)` retire une personne par
le départ d'Odoo (elle reçoit `discuss.channel/leave`, le fil montre qu'elle a
quitté). Réservé aux administrateurs ; refusé dans un `chat`.
