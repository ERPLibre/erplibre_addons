# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

from odoo import models


class IrModuleModule(models.Model):
    _inherit = "ir.module.module"

    def _load_module_terms(
        self, modules, langs, overwrite=False, imported_module=False
    ):
        """Name the answers of the category step of the guide in a language
        loaded after the installation, as the categories are named."""
        res = super()._load_module_terms(
            modules,
            langs,
            overwrite=overwrite,
            imported_module=imported_module,
        )
        if "chatbot.script.step" in self.env:
            self.env["chatbot.script.step"]._linkup_sync_category_answers()
        return res
