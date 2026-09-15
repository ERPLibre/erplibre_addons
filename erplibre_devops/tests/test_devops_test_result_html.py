# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl)

from odoo.tests.common import TransactionCase


class TestDevopsTestResultHtml(TransactionCase):
    """Tests for ANSI-to-HTML conversion in devops.test.result
    and devops.test.case.exec."""

    def test_log_html_empty(self):
        result = self.env["devops.test.result"].create(
            {"name": "Empty log"}
        )
        self.assertFalse(result.log_html)

    def test_log_html_plain_text(self):
        result = self.env["devops.test.result"].create(
            {"name": "Plain", "log": "Hello World"}
        )
        self.assertIn("Hello World", result.log_html)
        self.assertIn("<p>", result.log_html)

    def test_log_html_newline_to_br(self):
        result = self.env["devops.test.result"].create(
            {"name": "Newlines", "log": "line1\nline2"}
        )
        self.assertIn("<br />", result.log_html)

    def test_log_html_ansi_red(self):
        result = self.env["devops.test.result"].create(
            {
                "name": "Red",
                "log": "\033[0;31mError text\033[0m",
            }
        )
        self.assertIn('color: red', result.log_html)
        self.assertIn("Error text", result.log_html)

    def test_log_html_ansi_green(self):
        result = self.env["devops.test.result"].create(
            {
                "name": "Green",
                "log": "\033[0;32mSuccess\033[0m",
            }
        )
        self.assertIn('color: green', result.log_html)

    def test_log_html_ansi_bold(self):
        result = self.env["devops.test.result"].create(
            {
                "name": "Bold",
                "log": "\033[1mBold text\033[0m",
            }
        )
        self.assertIn("font-weight: bold", result.log_html)

    def test_log_html_ansi_underline_blue(self):
        result = self.env["devops.test.result"].create(
            {
                "name": "Underline",
                "log": "\033[4;34mUnderlined\033[0m",
            }
        )
        self.assertIn("text-decoration: underline", result.log_html)
        self.assertIn("color: blue", result.log_html)

    def test_log_html_ansi_bold_yellow(self):
        result = self.env["devops.test.result"].create(
            {
                "name": "BoldYellow",
                "log": "\033[1;33mWarning\033[0m",
            }
        )
        self.assertIn("font-weight: bold", result.log_html)
        self.assertIn("color: yellow", result.log_html)

    def test_log_html_strips_whitespace(self):
        result = self.env["devops.test.result"].create(
            {"name": "Stripped", "log": "  content  "}
        )
        self.assertIn("content", result.log_html)

    def test_log_html_whitespace_only_is_false(self):
        result = self.env["devops.test.result"].create(
            {"name": "Whitespace", "log": "   "}
        )
        self.assertFalse(result.log_html)

    def test_case_exec_log_html_same_conversion(self):
        """devops.test.case.exec uses the same ANSI conversion."""
        workspace = self.env["devops.workspace"].search(
            [("is_me", "=", True)], limit=1
        )
        if not workspace:
            self.skipTest("No 'me' workspace")
        case_exec = self.env["devops.test.case.exec"].create(
            {
                "name": "Exec HTML",
                "log": "\033[0;31mRed error\033[0m",
                "workspace_id": workspace.id,
            }
        )
        self.assertIn('color: red', case_exec.log_html)
        self.assertIn("Red error", case_exec.log_html)
