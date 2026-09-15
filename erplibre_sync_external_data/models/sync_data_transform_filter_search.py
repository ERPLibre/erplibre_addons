from odoo import fields, models


class SyncDataTransformFilterSearch(models.Model):
    _name = "sync.data.transform.filter_search"
    _description = "sync_data_transform filter search"

    name = fields.Char()

    active = fields.Boolean(default=True)

    sequence = fields.Integer(default=10)

    SEPARATORS = ("-%s", " -%s", " %s", "%s", "/%s", " : %s", ": %s", " # %s", "# %s")

    def action_generate_all(self, keys=None):
        if not keys:
            return
        patterns = ["#%s"]
        for key_s in keys:
            patterns.extend(f"{key_s}{sep}" for sep in self.SEPARATORS)
        existing = self.env[
            "sync.data.transform.filter_search"
        ].search([("name", "in", patterns)])
        existing_names = set(existing.mapped("name"))
        patterns_to_create = [
            {"name": p} for p in patterns if p not in existing_names
        ]
        if patterns_to_create:
            self.env["sync.data.transform.filter_search"].create(
                patterns_to_create
            )
