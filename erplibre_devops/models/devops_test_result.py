from odoo import _, api, fields, models

# TODO duplicate code, use an external lib
LST_CONSOLE_REPLACE_HTML = [
    ("\n", "<br />"),
    ("\033[0m", "</span>"),
    ("\033[0;30m", '<span style="color: black">'),
    ("\033[0;31m", '<span style="color: red">'),
    ("\033[0;32m", '<span style="color: green">'),
    ("\033[0;33m", '<span style="color: yellow">'),
    ("\033[0;34m", '<span style="color: blue">'),
    ("\033[0;35m", '<span style="color: purple">'),
    ("\033[0;36m", '<span style="color: cyan">'),
    ("\033[0;37m", '<span style="color: white">'),
    ("\033[1m", '<span style="font-weight: bold">'),
    ("\033[1;30m", '<span style="font-weight: bold;color: black">'),
    ("\033[1;31m", '<span style="font-weight: bold;color: red">'),
    ("\033[1;32m", '<span style="font-weight: bold;color: green">'),
    ("\033[1;33m", '<span style="font-weight: bold;color: yellow">'),
    ("\033[1;34m", '<span style="font-weight: bold;color: blue">'),
    ("\033[1;35m", '<span style="font-weight: bold;color: purple">'),
    ("\033[1;36m", '<span style="font-weight: bold;color: cyan">'),
    ("\033[1;37m", '<span style="font-weight: bold;color: white">'),
    ("\033[4;30m", '<span style="text-decoration: underline;color: black">'),
    ("\033[4;31m", '<span style="text-decoration: underline;color: red">'),
    ("\033[4;32m", '<span style="text-decoration: underline;color: green">'),
    ("\033[4;33m", '<span style="text-decoration: underline;color: yellow">'),
    ("\033[4;34m", '<span style="text-decoration: underline;color: blue">'),
    ("\033[4;35m", '<span style="text-decoration: underline;color: purple">'),
    ("\033[4;36m", '<span style="text-decoration: underline;color: cyan">'),
    ("\033[4;37m", '<span style="text-decoration: underline;color: white">'),
]


class DevopsTestResult(models.Model):
    _name = "devops.test.result"
    _description = "devops_test_result"

    name = fields.Char()

    active = fields.Boolean(default=True)

    log = fields.Text(readonly=True)

    log_html = fields.Html(store=True, compute="_compute_log_html")

    is_finish = fields.Boolean(readonly=True)

    is_pass = fields.Boolean(readonly=True)

    test_case_exec_id = fields.Many2one(
        comodel_name="devops.test.case.exec",
        string="Test Case Exec",
    )

    test_plan_exec_id = fields.Many2one(
        comodel_name="devops.test.plan.exec",
        string="Plan",
        related="test_case_exec_id.test_plan_exec_id",
        readonly=True,
    )

    workspace_id = fields.Many2one(related="test_plan_exec_id.workspace_id")

    @api.multi
    @api.depends("log")
    def _compute_log_html(self):
        for rec in self:
            if rec.log:
                log_html = rec.log.strip()
                for rep_str_from, rep_str_to in LST_CONSOLE_REPLACE_HTML:
                    log_html = log_html.replace(rep_str_from, rep_str_to)
                rec.log_html = f"<p>{log_html}</p>"
