# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import logging
import os

import odoo
from odoo import api, fields, models, release
from odoo.addons.erplibre_info import runner
from odoo.exceptions import UserError

from .. import suggestion

_logger = logging.getLogger(__name__)


class DoctorError(Exception):
    """A check cannot run; the message, already translated, goes to the
    report."""


class ErplibreDoctorReport(models.Model):
    """One analysis of the database by the doctor: the findings of every
    check at the time it ran. A report is a snapshot and never runs again;
    a new analysis makes a new report."""

    _name = "erplibre.doctor.report"
    _description = "ERPLibre doctor report"
    _order = "date desc, id desc"

    name = fields.Char(required=True, readonly=True, copy=False, default="/")
    date = fields.Datetime(default=fields.Datetime.now, readonly=True)
    user_id = fields.Many2one(
        "res.users",
        string="Run by",
        default=lambda self: self.env.user,
        readonly=True,
    )
    state = fields.Selection(
        [("draft", "Draft"), ("done", "Done"), ("error", "Incomplete")],
        default="draft",
        required=True,
        readonly=True,
        help="Incomplete: at least one check could not run, its reason is "
        "in Errors; the findings of the other checks are kept.",
    )
    error = fields.Text(string="Errors", readonly=True)
    image = fields.Char(
        readonly=True,
        help="The database image of the ERPLibre checkout whose modules are "
        "suggested, from conf/module_list_image_db_odoo.json.",
    )
    line_ids = fields.One2many(
        "erplibre.doctor.report.line",
        "report_id",
        string="Findings",
        readonly=True,
    )
    problem_count = fields.Integer(
        string="Problems", compute="_compute_problem_count", store=True
    )
    installable_count = fields.Integer(
        string="To install", compute="_compute_installable_count"
    )

    @api.depends("line_ids.problem")
    def _compute_problem_count(self):
        for report in self:
            report.problem_count = len(report.line_ids.filtered("problem"))

    @api.depends("line_ids.can_install")
    def _compute_installable_count(self):
        for report in self:
            report.installable_count = len(
                report.line_ids.filtered("can_install")
            )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", "/") == "/":
                vals["name"] = (
                    self.env["ir.sequence"].next_by_code(
                        "erplibre.doctor.report"
                    )
                    or "/"
                )
        return super().create(vals_list)

    # -- Analysis -----------------------------------------------------------

    def _doctor_checks(self):
        """The methods of the analysis, in order. Each returns the values of
        its lines without ``report_id``, or raises DoctorError. A module
        that adds a check extends the list and the ``check`` selection of
        the line."""
        return ["_check_suggested_modules"]

    def _run(self):
        """Run every check on the reports and store their lines. A check
        that raises DoctorError adds its message to ``error`` and the
        report ends « Incomplete »; the other checks still run."""
        Line = self.env["erplibre.doctor.report.line"]
        for report in self:
            report.line_ids.unlink()
            errors = []
            for method in report._doctor_checks():
                try:
                    vals_list = getattr(report, method)()
                except DoctorError as error:
                    errors.append(str(error))
                    continue
                for sequence, vals in enumerate(
                    vals_list, start=len(report.line_ids)
                ):
                    vals.setdefault("sequence", sequence)
                    vals["report_id"] = report.id
                Line.create(vals_list)
            report.write(
                {
                    "date": fields.Datetime.now(),
                    "state": "error" if errors else "done",
                    "error": "\n".join(errors) or False,
                }
            )

    def _checkout_root(self):
        """The ERPLibre checkout that holds the image configuration: the
        directory of the ``erplibre_info.root`` parameter when it is set,
        else the first parent of the running Odoo that holds the file."""
        configured = (
            self.env["ir.config_parameter"].sudo().get_param(runner.PARAM_ROOT)
        )
        if configured:
            return os.path.realpath(configured)
        return runner.find_root(
            os.path.dirname(odoo.__file__), suggestion.CONFIG_FILE
        )

    def _suggestion_message(self, error):
        """The translated message of a SuggestionError."""
        messages = {
            "missing": self.env._(
                "The ERPLibre checkout has no %(file)s: no suggested module "
                "to compare with.",
                file=error.value,
            ),
            "unreadable": self.env._(
                "%(file)s cannot be read as a JSON object.", file=error.value
            ),
            "unknown_image": self.env._(
                "The image %(image)s is not described in %(file)s.",
                image=error.value,
                file=suggestion.CONFIG_FILE,
            ),
            "cycle": self.env._(
                "The image %(image)s is its own base in %(file)s.",
                image=error.value,
                file=suggestion.CONFIG_FILE,
            ),
        }
        return messages.get(error.code, str(error))

    def _check_suggested_modules(self):
        """One line per module of the base image of this Odoo series, with
        its state in this database; a module that is not installed is a
        problem."""
        self.ensure_one()
        image = suggestion.image_name(release.series)
        self.image = image
        root = self._checkout_root()
        if not root:
            raise DoctorError(
                self.env._(
                    "No ERPLibre checkout found above the running Odoo: set "
                    "the system parameter %(param)s to its directory.",
                    param=runner.PARAM_ROOT,
                )
            )
        try:
            names = suggestion.image_modules(
                suggestion.read_config(root), image
            )
        except suggestion.SuggestionError as error:
            raise DoctorError(self._suggestion_message(error)) from error
        modules = {
            module.name: module
            for module in self.env["ir.module.module"].search(
                [("name", "in", names)]
            )
        }
        vals_list = []
        for name in names:
            module = modules.get(name)
            state = module.state if module else "absent"
            vals_list.append(
                {
                    "check": "suggested_module",
                    "name": name,
                    "module_id": module.id if module else False,
                    "state_found": state,
                    "problem": state not in ("installed", "to upgrade"),
                }
            )
        return vals_list

    # -- Actions ------------------------------------------------------------

    def _action_open_form(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": self.name,
            "res_model": self._name,
            "res_id": self.id,
            "view_mode": "form",
            "target": "current",
        }

    def action_new_analysis(self):
        """Run a new analysis and open its report. Called from the list
        header without records, and from a report, which it leaves as it
        is."""
        report = self.create({})
        report._run()
        return report._action_open_form()

    def action_install_missing(self):
        """Mark every module the report can install « to install », with
        its dependencies, and open the confirmation: it lists them, then
        installs them and reloads the client, or cancels the marks."""
        modules = self.line_ids.filtered("can_install").module_id
        if not modules:
            raise UserError(
                self.env._(
                    "This report has no module left that can be installed."
                )
            )
        return self.env["erplibre.doctor.report.line"]._action_install_modules(
            modules
        )
