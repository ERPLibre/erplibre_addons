# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
"""Création idempotente d'un canal par identifiant client et verrou
consultatif partagé par les dédoublonnages du module."""

import zlib

from odoo import api, fields, models
from odoo.addons.mail.tools.discuss import Store
from odoo.exceptions import AccessError, UserError
from odoo.tools.translate import _

from .mail_message import erplibre_ensure_unique_uuid_index

# Premier entier de la paire de pg_advisory_xact_lock : un espace par
# famille de verrous, pour qu'un canal, un message et une pièce jointe de
# même clé ne se bloquent pas.
LOCK_NAMESPACE_CHANNEL = 0x45524C01
LOCK_NAMESPACE_MESSAGE = 0x45524C02
LOCK_NAMESPACE_ATTACHMENT = 0x45524C03


def erplibre_lock_uuid(env, namespace, uuid):
    """Prend, jusqu'à la fin de la transaction, le verrou consultatif
    (namespace, hash 32 bits signé de « uid:uuid »).

    La recherche d'un doublon puis la création ne sont pas atomiques : sans
    verrou, un renvoi qui arrive pendant que la première transaction est
    ouverte ne voit rien et tente un second enregistrement. Avec le verrou,
    le renvoi attend le commit de la première puis, le plus souvent, la
    trouve. Le verrou sérialise ; il ne garantit pas : les curseurs Odoo
    lisent en REPEATABLE READ, l'instantané date du premier ordre de la
    transaction, avant le verrou, et la recherche qui suit peut ne pas voir
    la ligne que l'autre transaction vient de valider. L'index unique
    partiel de chaque modèle garantit : un renvoi qui chevauche ainsi échoue
    sur l'index au lieu de doubler. Odoo change l'erreur d'intégrité en
    ValidationError, qu'une route JSON-RPC rend en erreur et une route http
    en HTTP 400 (BadRequest) ; le renvoi suivant trouve la ligne. Le hash
    CRC32 peut collisionner : une collision ne fait qu'attendre à tort,
    jamais confondre deux enregistrements.
    """
    key = zlib.crc32(f"{env.uid}:{uuid}".encode())
    if key >= 2**31:
        key -= 2**32
    env.cr.execute("SELECT pg_advisory_xact_lock(%s, %s)", (namespace, key))


class DiscussChannel(models.Model):
    _inherit = "discuss.channel"

    erplibre_client_uuid = fields.Char(
        string="Client UUID",
        index="btree_not_null",
        copy=False,
        readonly=True,
        help="Identifiant généré par l'application mobile ; un renvoi du"
        " même identifiant par le même utilisateur ne crée pas de second"
        " canal.",
    )

    def init(self):
        # Dernière garde du dédoublonnage (voir erplibre_lock_uuid). L'index
        # btree_not_null du champ reste : il sert la recherche par seul
        # identifiant, que l'index unique, mené par create_uid, ne sert pas.
        super().init()
        erplibre_ensure_unique_uuid_index(
            self.env.cr,
            "discuss_channel",
            "discuss_channel_erplibre_client_uuid_uniq",
            ["create_uid", "erplibre_client_uuid"],
        )

    def _erplibre_existing_by_uuid(self):
        """Rend le canal créé par l'utilisateur courant avec l'identifiant
        client du contexte, ou un recordset vide si le contexte n'en porte
        pas ou si aucun canal ne correspond.

        Prend d'abord le verrou de l'identifiant (voir erplibre_lock_uuid).
        Un renvoi avec d'autres valeurs rend quand même le premier canal. Un
        canal archivé n'est pas retrouvé, volontairement : un nouvel appel
        en crée un autre. Si le créateur n'a plus accès au canal trouvé,
        la lecture du résultat lève AccessError (l'application le traite
        comme refusé ou disparu).

        La recherche est sous sudo : l'ACL de création de l'utilisateur ne
        couvre pas un canal dont il a été retiré, mais le créateur reste
        celui qui a émis l'identifiant. Le résultat reprend l'environnement
        courant, donc les droits de lecture de l'appelant.
        """
        uuid = self.env.context.get("erplibre_client_uuid")
        if not uuid or self.env.user._is_public():
            return self.browse()
        erplibre_lock_uuid(self.env, LOCK_NAMESPACE_CHANNEL, uuid)
        found = (
            self.env["discuss.channel"]
            .sudo()
            .search(
                [
                    ("erplibre_client_uuid", "=", uuid),
                    ("create_uid", "=", self.env.uid),
                ],
                limit=1,
            )
        )
        return self.browse(found.ids)

    @api.model_create_multi
    def create(self, vals_list):
        """Crée les canaux ; avec `erplibre_client_uuid` dans le contexte,
        rend le canal déjà créé par le même utilisateur avec cet
        identifiant, sinon enregistre l'identifiant sur le canal créé.

        L'identifiant désigne un seul canal : une création de plusieurs
        enregistrements avec un identifiant dans le contexte est refusée.
        """
        uuid = self.env.context.get("erplibre_client_uuid")
        if uuid and not self.env.user._is_public():
            if len(vals_list) != 1:
                raise UserError(
                    _("A client UUID identifies a single channel.")
                )
            existing = self._erplibre_existing_by_uuid()
            if existing:
                return existing
            vals_list = [dict(vals_list[0], erplibre_client_uuid=uuid)]
        return super().create(vals_list)

    @api.model
    @api.returns("self", lambda channels: Store(channels).get_result())
    def channel_create(self, name, group_id):
        # Le message « created this channel » et la diffusion de la
        # création ne se rejouent pas sur un renvoi.
        existing = self._erplibre_existing_by_uuid()
        if existing:
            return existing
        return super().channel_create(name, group_id)

    @api.model
    @api.returns("self", lambda channels: Store(channels).get_result())
    def create_group(self, partners_to, default_display_mode=False, name=""):
        # La diffusion de la création ne se rejoue pas sur un renvoi.
        existing = self._erplibre_existing_by_uuid()
        if existing:
            return existing
        return super().create_group(
            partners_to, default_display_mode=default_display_mode, name=name
        )

    def erplibre_remove_member(self, partner_id):
        """Retire une personne d'un groupe ou d'un canal par le chemin du
        départ d'Odoo : la personne reçoit `discuss.channel/leave` et le
        fil affiche qu'elle a quitté. Réservé aux administrateurs ; un
        `chat` n'a pas de membres à retirer.
        """
        self.ensure_one()
        if not self.env.user._is_system():
            raise AccessError(_("Only an administrator can remove a member."))
        if self.channel_type == "chat":
            raise UserError(_("A direct message has no member to remove."))
        partner = self.env["res.partner"].browse(partner_id).exists()
        if not partner or partner not in self.channel_member_ids.partner_id:
            raise UserError(_("This person is not a member of the channel."))
        self._action_unfollow(partner)

    @api.returns("mail.message", lambda value: value.id)
    def message_post(self, **kwargs):
        # Le message déjà publié avec l'identifiant client est rendu avant
        # message_post de mail, qui écrit last_interest_dt : un renvoi ne
        # diffuse rien et ne rouvre pas la conversation qu'un membre a
        # fermée. Sinon la publication suit son cours, et la surcharge de
        # mail.thread refait la recherche sous le même verrou.
        uuid = kwargs.get("erplibre_client_uuid")
        if uuid and self and not self.env.user._is_public():
            existing = self._erplibre_posted_message(uuid)
            if existing:
                return existing
        return super().message_post(**kwargs)
