import logging

from colorama import Fore, Style

from odoo import _, api, exceptions, fields, models

_logger = logging.getLogger(__name__)

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
    (Style.RESET_ALL, "</span>"),
    (Fore.BLACK, '<span style="color: black">'),
    (Fore.RED, '<span style="color: red">'),
    (Fore.GREEN, '<span style="color: green">'),
    (Fore.YELLOW, '<span style="color: yellow">'),
    (Fore.BLUE, '<span style="color: blue">'),
    (Fore.MAGENTA, '<span style="color: magenta">'),
    (Fore.CYAN, '<span style="color: cyan">'),
    (Fore.WHITE, '<span style="color: white">'),
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


class DevopsTestCaseExec(models.Model):
    _name = "devops.test.case.exec"
    _description = "devops_test_case_exec"

    name = fields.Char()

    active = fields.Boolean(default=True)

    is_finish = fields.Boolean(
        readonly=True,
        help="Execution is finish",
    )

    is_pass = fields.Boolean(
        compute="_compute_is_pass",
        store=True,
        help="True test pass, else test fail.",
    )

    log = fields.Text(help="Log for the test")

    log_html = fields.Html(store=True, compute="_compute_log_html")

    test_plan_exec_id = fields.Many2one(
        comodel_name="devops.test.plan.exec",
        string="Plan",
        ondelete="cascade",
    )

    test_case_id = fields.Many2one(
        comodel_name="devops.test.case",
        string="Test case",
    )

    result_ids = fields.One2many(
        comodel_name="devops.test.result",
        inverse_name="test_case_exec_id",
        string="Results",
        readonly=True,
    )

    workspace_id = fields.Many2one(
        comodel_name="devops.workspace",
        string="Workspace",
        required=True,
    )

    has_devops_action = fields.Boolean(
        store=True, compute="_compute_has_devops_action"
    )

    @api.multi
    @api.depends("test_case_id")
    def _compute_has_devops_action(self):
        for rec in self:
            rec.has_devops_action = (
                rec.test_case_id and rec.test_case_id.test_cb_method_cg_id
            )

    @api.multi
    @api.depends("result_ids", "result_ids.is_pass")
    def _compute_is_pass(self):
        for rec in self:
            if rec.result_ids:
                rec.is_pass = all([a.is_pass for a in rec.result_ids])
            else:
                rec.is_pass = False

    def test_breakpoint(self, ctx=None):
        lst_result_value = []
        for rec in self:
            with rec.workspace_id.devops_create_exec_bundle(
                "Test plan DevOps run test",
                ctx=ctx,
            ) as rec_ws:
                bp_ids = self.env["devops.ide.breakpoint"].search([])
                if not bp_ids:
                    msg = f"List of breakpoint is empty."
                    _logger.error(msg)
                    raise exceptions.Warning(msg)
                for bp_id in bp_ids:
                    if bp_id.ignore_test:
                        continue

                    try:
                        lst_line = bp_id.get_breakpoint_info(rec_ws)
                    except Exception as e:
                        rec.is_finish = True
                        lst_result_value.append(
                            {
                                "name": f"Test breakpoint ID {bp_id.id}",
                                "log": (
                                    "Exception warning Breakpoint"
                                    f" '{bp_id.name}' : {e}"
                                ),
                                "is_finish": True,
                                "is_pass": False,
                                "test_case_exec_id": rec.id,
                            }
                        )
                        continue
                    if not lst_line:
                        msg = (
                            f"Cannot find breakpoint {bp_id.name} for file"
                            f" {bp_id.filename}, key : {bp_id.keyword}"
                        )
                        rec.is_finish = True
                        lst_result_value.append(
                            {
                                "name": f"Test breakpoint ID {bp_id.id}",
                                "log": msg,
                                "is_finish": True,
                                "is_pass": False,
                                "test_case_exec_id": rec.id,
                            }
                        )
                        continue
                    if not bp_id.is_multiple and (
                        len(lst_line) != 1 or len(lst_line[0][1]) > 1
                    ):
                        msg = (
                            f"Breakpoint {bp_id.name} is not suppose to find"
                            f" multiple line and got '{lst_line}' into file"
                            f" '{bp_id.filename}' with key '{bp_id.keyword}'"
                        )
                        rec.is_finish = True
                        lst_result_value.append(
                            {
                                "name": f"Test breakpoint ID {bp_id.id}",
                                "log": msg,
                                "is_finish": True,
                                "is_pass": False,
                                "test_case_exec_id": rec.id,
                            }
                        )
                        continue
                    rec.is_finish = True
                    lst_result_value.append(
                        {
                            "name": f"Test breakpoint ID {bp_id.id}",
                            "is_finish": True,
                            "is_pass": True,
                            "test_case_exec_id": rec.id,
                        }
                    )
        self.env["devops.test.result"].create(lst_result_value)

    @api.multi
    @api.depends("log")
    def _compute_log_html(self):
        for rec in self:
            log_html = rec.log.strip() if rec.log else ""
            if log_html:
                for rep_str_from, rep_str_to in LST_CONSOLE_REPLACE_HTML:
                    log_html = log_html.replace(rep_str_from, rep_str_to)
                rec.log_html = f"<p>{log_html}</p>"
            else:
                rec.log_html = False

    @api.multi
    def open_devops_action(self):
        # TODO add self.ensure_one() in all action
        self.ensure_one()
        if not self.has_devops_action:
            return
        tc_id = self.test_case_id.test_cb_method_cg_id
        ctx = dict(
            self.env.context,
            default_root_workspace_id=self.env.ref(
                "erplibre_devops.devops_workspace_me", raise_if_not_found=False
            ).id,
            default_use_external_cg=True,
            default_use_existing_meta_module=True,
            default_state="code_module",
        )
        if tc_id.type_test == "gen_ucb":
            ctx = dict(
                ctx,
                default_code_generator_name=tc_id.module_tested[0].name,
                default_working_module_path=tc_id.path_generated,
                default_working_module_path_suggestion="#",
                default_working_module_cg_path=tc_id.path_meta,
                default_working_module_cg_path_suggestion="#",
                default_working_module_template_path=tc_id.path_meta,
                default_working_module_template_path_suggestion="#",
                default_use_existing_meta_module_ucb_only=True,
                default_working_module_name=tc_id.module_generated[0].name,
            )
        elif tc_id.type_test == "gen_uca":
            ctx = dict(
                ctx,
                default_code_generator_name=tc_id.module_tested[0].name,
                default_working_module_path=tc_id.path_module_check,
                default_working_module_path_suggestion="#",
                default_working_module_cg_path=tc_id.path_meta,
                default_working_module_cg_path_suggestion="#",
                default_working_module_template_path=tc_id.path_meta,
                default_working_module_template_path_suggestion="#",
                default_use_existing_meta_module_uca_only=True,
            )
        # TODO missing type_test run_c, missing install module before run code gen
        return {
            "name": _("Run code execution from test."),
            "type": "ir.actions.act_window",
            "view_type": "form",
            "view_mode": "form",
            "res_model": "devops.plan.action.wizard",
            "view_id": self.env.ref(
                "erplibre_devops.devops_plan_action_form"
            ).id,
            "target": "new",
            "context": ctx,
        }

    @api.multi
    def open_new_test_plan_execution(self):
        # TODO add self.ensure_one() in all action
        self.ensure_one()
        # TODO do a copy and change run_in_sandbox, remove all test
        ctx = dict(
            self.env.context,
            default_workspace_id=self.env.ref(
                "erplibre_devops.devops_workspace_me",
                raise_if_not_found=False,
            ).id,
            default_run_in_sandbox=False,
            default_test_case_ids=[(4, self.test_case_id.id)],
        )
        return {
            "name": _("Run test plan execution from test case execution."),
            "type": "ir.actions.act_window",
            "view_type": "form",
            "view_mode": "form",
            "res_model": "devops.test.plan.exec",
            "view_id": self.env.ref(
                "erplibre_devops.devops_test_plan_exec_view_form"
            ).id,
            "target": "new",
            "context": ctx,
        }
