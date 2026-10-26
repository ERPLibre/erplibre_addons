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

`POST /erplibre_mobile_chat/attachment/upload` reprend les champs de
`/mail/attachment/upload` (`ufile`, `thread_id`, `thread_model`, `is_pending`,
`voice`, jeton CSRF) avec un `client_uuid` obligatoire, enregistré dans
`ir.attachment.erplibre_client_uuid`. Un renvoi du même identifiant par le
même utilisateur rend la pièce jointe déjà créée, sans seconde pièce jointe ni
seconde métadonnée vocale. Sinon la route d'Odoo fait le travail, avec ses
contrôles et sa réponse, mais l'image est gardée originale (aucune réduction à
1920 px). Seul `discuss.channel` est accepté ; une session expirée ou un
utilisateur portail reçoit 404.

`POST /erplibre_mobile_chat/message/update_content` (JSON-RPC, utilisateur
interne) reprend les paramètres de `/mail/message/update_content`
(`message_id`, `body`, `attachment_ids`, `attachment_tokens`, `partner_ids`)
avec un `expected_fingerprint` obligatoire : la valeur de
`mail.message.erplibre_body_fingerprint`, le SHA-256 hexadécimal des octets
UTF-8 du corps HTML tel que Store le rend (champ `body` de la réponse d'Odoo),
un corps vide ou `false` étant haché comme la chaîne vide `""`. Si l'empreinte
actuelle diffère, ou si le message a été vidé (supprimé) et que `body` n'est
pas vide, rien n'est écrit et la réponse porte `erplibre_conflict` (`"deleted"`
pour un message vide, sinon `"changed"`) avec le message actuel au format de la
réponse d'Odoo. Sinon la route d'Odoo fait le travail, avec ses contrôles, la
marque « modifié », le bus et sa réponse. Un `message_id` non numérique, un
message absent ou que l'utilisateur ne peut pas modifier selon Odoo rend 404,
sans verrou. `attachment_ids` à `null` garde les pièces jointes, `[]` les
supprime toutes. Après les contrôles d'accès, la ligne du message est
verrouillée avant la relecture du corps et la comparaison : deux modifications
concurrentes ne passent pas toutes deux. Le champ figure dans `fields_get` de
`mail.message` pour tout utilisateur interne, ce qui signale ce niveau du
module.
