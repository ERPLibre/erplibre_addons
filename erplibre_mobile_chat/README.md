# ERPLibre — Clavardage mobile

L'application mobile publie dans Discuss avec un identifiant client (uuid).
Quand la réponse du serveur se perd et que l'application renvoie le même
message, un second message en double apparaîtrait.

Ce module ajoute `mail.message.erplibre_client_uuid` et accepte ce champ dans
`/mail/message/post`. `discuss.channel.message_post` rend le message déjà
publié par le même auteur, dans le même canal, avec le même identifiant, sans
publier ni notifier de nouveau. Un autre auteur ou un autre canal n'adopte pas
le message.
