from odoo import _, api, fields, models


class SyncDataTransformFilterSearch(models.Model):
    _name = "sync.data.transform.filter_search"
    _description = "sync_data_transform filter search"

    name = fields.Char()

    active = fields.Boolean(default=True)

    sequence = fields.Integer(default=10)

    # pattern_string = fields.Text(default="")
    #
    # pattern_value = fields.Text(default="")

    def action_generate_all(self, keys=None):
        if not keys:
            return
        patterns = []
        str_key = "#%s"
        patterns.append(str_key)
        for key_s in keys:
            str_key = f"{key_s}-%s"
            patterns.append(str_key)
            str_key = f"{key_s} -%s"
            patterns.append(str_key)
            str_key = f"{key_s} %s"
            patterns.append(str_key)
            str_key = f"{key_s}%s"
            patterns.append(str_key)
            str_key = f"{key_s}/%s"
            patterns.append(str_key)
            str_key = f"{key_s} : %s"
            patterns.append(str_key)
            str_key = f"{key_s}: %s"
            patterns.append(str_key)
            str_key = f"{key_s} # %s"
            patterns.append(str_key)
            str_key = f"{key_s}# %s"
            patterns.append(str_key)
        patterns_to_create = []
        for str_key in patterns:
            filter_search_id = self.env[
                "sync.data.transform.filter_search"
            ].search([("name", "=", str_key)])
            if not filter_search_id:
                patterns_to_create.append({"name": str_key})
        if patterns_to_create:
            self.env["sync.data.transform.filter_search"].create(
                patterns_to_create
            )
