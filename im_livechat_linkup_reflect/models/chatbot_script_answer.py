# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

from odoo import fields, models
from odoo.addons.mail.tools.discuss import Store


class ChatbotScriptAnswer(models.Model):
    _inherit = "chatbot.script.answer"

    # Set on the answers of a ``linkup_category`` step, which
    # ``chatbot.script.step._linkup_sync_category_answers`` keeps in step
    # with the active categories.
    linkup_category_id = fields.Many2one(
        "linkup.category",
        string="LinkUp category",
        ondelete="cascade",
        readonly=True,
    )

    def _to_store(self, store: Store, /, *, fields=None):
        """An answer of a category step also gives the code of its
        category, which the widget draws as its icon."""
        super()._to_store(store, fields=fields)
        for answer in self.sudo().filtered("linkup_category_id"):
            store.add(
                "chatbot.script.answer",
                {
                    "id": answer.id,
                    "linkup_category_code": answer.linkup_category_id.code,
                },
            )
