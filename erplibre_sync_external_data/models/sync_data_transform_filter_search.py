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

    def action_generate_all(self, lst_key=None):
        if not lst_key:
            return
        lst_str_key = []
        str_key = "#%s"
        lst_str_key.append(str_key)
        for key_s in lst_key:
            str_key = f"{key_s}-%s"
            lst_str_key.append(str_key)
            str_key = f"{key_s} -%s"
            lst_str_key.append(str_key)
            str_key = f"{key_s} %s"
            lst_str_key.append(str_key)
            str_key = f"{key_s}%s"
            lst_str_key.append(str_key)
            str_key = f"{key_s}/%s"
            lst_str_key.append(str_key)
            str_key = f"{key_s} : %s"
            lst_str_key.append(str_key)
            str_key = f"{key_s}: %s"
            lst_str_key.append(str_key)
            str_key = f"{key_s} # %s"
            lst_str_key.append(str_key)
            str_key = f"{key_s}# %s"
            lst_str_key.append(str_key)
        lst_str_key_create = []
        for str_key in lst_str_key:
            filter_search_id = self.env[
                "sync.data.transform.filter_search"
            ].search([("name", "=", str_key)])
            if not filter_search_id:
                lst_str_key_create.append({"name": str_key})
        if lst_str_key_create:
            self.env["sync.data.transform.filter_search"].create(
                lst_str_key_create
            )
