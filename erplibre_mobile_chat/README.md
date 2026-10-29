# ERPLibre — Clavardage mobile

L'application mobile publie avec un identifiant client (uuid), dans Discuss
comme dans le fil d'un enregistrement. Quand la réponse du serveur se perd et
que l'application renvoie le même message, un second message en double
apparaîtrait.

Ce module ajoute `mail.message.erplibre_client_uuid` et accepte ce champ dans
`/mail/message/post`, pour tout modèle `mail.thread`. `message_post` rend le
message déjà publié par le même auteur, sur le même fil (canal ou
enregistrement), avec le même identifiant, sans publier ni notifier de
nouveau. Un autre auteur ou un autre fil n'adopte pas le message. Les droits
de publication restent ceux d'Odoo (`_mail_post_access` du modèle, `write` par
défaut) : hors sudo, un message retrouvé exige le même droit qu'une
publication. Dans un canal, le message déjà publié est rendu avant le
`message_post` de mail : un renvoi ne touche pas `last_interest_dt`, ne
diffuse rien et ne rouvre pas une conversation qu'un membre a fermée. Sur un
autre modèle, ce qu'une surcharge de `message_post` du modèle, ou d'une
extension de `mail.thread` chargée après ce module (`rating`, par exemple),
fait avant `super()` se rejoue sur un renvoi.

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
1920 px). Le fil est tout modèle `mail.thread`, canal ou enregistrement ; un
autre modèle rend 404, comme une session expirée ou un utilisateur portail.
Sur un enregistrement, la route d'Odoo exige le droit de publier
(`_mail_post_access`, `write` par défaut) et rend 404 sans lui.

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

`POST /erplibre_mobile_chat/message/search` (JSON-RPC, utilisateur interne,
`search_term`, `before`, `limit` de 1 à 100, 30 par défaut ou à `null`) cherche
dans les messages des seuls canaux dont l'utilisateur est membre : jamais un
canal public où il n'est pas, jamais la discussion d'autres personnes, même
pour un administrateur. Un message correspond par son corps, son sujet ou le
nom d'une pièce jointe. Le terme est cherché tel que le corps est stocké : pour
le corps, `&`, `<` et `>` deviennent `&amp;`, `&lt;` et `&gt;` (l'apostrophe,
le guillemet et les accents restent tels quels) ; le sujet et les noms prennent
le terme brut ; partout `\`, `%` et `_` sont des caractères, pas des jokers, et
une espace accepte n'importe quel intervalle. La réponse reprend la forme des
routes de boîte d'Odoo : `count` (toutes les correspondances, sans tenir compte
de `before`), `messages` (ids de la page, du plus récent au plus ancien) et
`data` (Store). Rien n'est marqué lu : aucun `set_message_done`.

`mail.message.erplibre_set_starred(starred)` met les messages en favori ou les
en retire pour l'utilisateur courant. Contrairement à `toggle_message_starred`,
un renvoi ne défait rien : seuls les messages dont l'état diffère changent, et
le bus `mail.message/toggle_star` (même charge que chez Odoo) ne part que pour
eux. Un message illisible lève `AccessError`.

`mail.message.erplibre_chat_level` est une sélection dont la plus haute clé
donne le niveau du module (`1.5`). Elle figure dans `fields_get` de
`mail.message` pour tout utilisateur interne, avec ses clés dans `selection` ;
un niveau suivant y ajoute sa clé.

## Notifications de l'application

`POST /erplibre_mobile_chat/push/device` (JSON-RPC, utilisateur connecté,
`endpoint`, `quiet_while_online` faux par défaut) marque l'appareil de
notification (`mail.push.device`) du partenaire courant dont le point de
terminaison est `endpoint` comme celui de l'application, et répond
`{"ok": true}`. Le partenaire qui n'a pas d'appareil de ce point de
terminaison reçoit `{"ok": false}` ; l'appareil d'un autre partenaire reste
intact. La marque tient en trois champs : `erplibre_app`,
`erplibre_quiet_while_online` (la valeur reçue) et `erplibre_session_hash`, le
SHA-256 hexadécimal de l'id de la session qui appelle. L'application appelle
la route après chaque `register_devices` et après chaque nouvelle session. Un
`register_devices` qui passe le point de terminaison à un autre partenaire
efface les trois champs.

À chaque notification d'un message, les appareils marqués des destinataires
d'Odoo (les mêmes partenaires, après le filtre « web_push » des canaux)
reçoivent la charge d'Odoo augmentée de `options.data.erplibre` :
`{"v": 1, "message_id": <id du message>, "channel_type": "chat" | "group" |
"channel" | null}`, `null` hors d'un canal. La charge repasse par
`_truncate_payload` : son JSON chiffré tient toujours dans 4096 octets. Moins
de cinq appareils marqués reçoivent l'envoi après la validation de la
transaction (`cr.postcommit`) : rien ne part pour une publication annulée.
Au-delà, des lignes `mail.push` attendent le cron de mail, que le module
traite en premier pour ses appareils, après la validation du cron lui aussi.
L'envoi reprend le chiffrement et l'en-tête VAPID d'Odoo, tient 200 (la
réponse de ntfy) comme 201 pour un succès, supprime l'appareil sur 404 ou 410
et ne journalise qu'un id d'appareil, jamais le point de terminaison, qui
porte le sujet secret.

Un appareil marqué `erplibre_quiet_while_online` ne reçoit pas les
notifications de message pendant qu'un navigateur de son utilisateur est en
ligne (`res.users._erplibre_browser_online`). La présence des navigateurs
tient en deux champs de `bus.presence`, `erplibre_browser_poll` et
`erplibre_browser_presence`, que `ir.websocket._update_bus_presence` écrit
après la présence d'Odoo, pour toute session du bus sauf celle qui a marqué un
appareil de l'application de cet utilisateur (`erplibre_session_hash`) : le
bus de l'application ne compte jamais comme un navigateur. Un navigateur est
en ligne quand son dernier sondage date de moins de 65 secondes et sa dernière
activité de moins de 30 minutes, les délais d'Odoo pour « hors ligne » et
« absent ».

Quand le dernier message vu d'un membre avance (`_set_last_seen_message` de
`discuss.channel.member` : marquage comme lu, ou sa propre publication), les
appareils de l'application de son partenaire reçoivent, après la validation,
`{"erplibre": {"v": 1, "type": "read", "channel_id": <canal>,
"last_message_id": <message>}}` : une seule notification par appareil, par
canal et par transaction, avec le plus grand id. `set_message_done` et
`mark_all_as_read` de `mail.message` envoient aux appareils de l'application
du lecteur `{"erplibre": {"v": 1, "type": "inbox_done", "threads":
[[<modèle>, <id>], …]}}` : les fils hors des canaux des messages marqués,
triés, ou `threads` à `null` au-delà de 40 fils ; rien quand aucun tel fil ne
reste. Ces deux notifications ne vont jamais à un autre appareil (le service
worker d'Odoo afficherait une notification vide) et passent même pendant
qu'un navigateur est en ligne : elles retirent des notifications.

Tout autre appareil, un navigateur ou l'application sans le module, suit le
code d'Odoo inchangé : même appel de `push_to_end_point`, même charge, même
avertissement d'Odoo sur une réponse 200. Le module ne fait que lui cacher les
appareils marqués, par le contexte `erplibre_skip_app_devices` (voir
`mail.push.device._search` et `mail.push._search`).
