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
donne le niveau du module (`1.4`). Elle figure dans `fields_get` de
`mail.message` pour tout utilisateur interne, avec ses clés dans `selection` ;
un niveau suivant y ajoute sa clé.
