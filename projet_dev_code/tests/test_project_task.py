# © 2025 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
import threading
from unittest.mock import MagicMock, patch

from .common import ProjetDevCodeCommon

# Path to patch inside the module under test
_MODULE = "odoo.addons.projet_dev_code.models.project_task"


class TestProjetDevCodeFields(ProjetDevCodeCommon):
    """New fields are correctly added to project.task with proper defaults."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.task = cls._make_task(name="Test Task")

    def test_default_status_is_draft(self):
        self.assertEqual(self.task.claude_status, "draft")

    def test_new_fields_default_to_false(self):
        for field in (
            "claude_workspace",
            "claude_working_dir",
            "claude_module_name",
            "claude_output",
            "claude_session_id",
        ):
            self.assertFalse(
                self.task[field],
                f"Field '{field}' should default to False on a new task",
            )


class TestProjetDevCodePrompt(ProjetDevCodeCommon):
    """_build_claude_prompt assembles context fields and strips HTML correctly."""

    def test_includes_task_name(self):
        task = self._make_task(name="Implement feature X")
        self.assertIn("Implement feature X", task._build_claude_prompt())

    def test_includes_workspace(self):
        task = self._make_task(claude_workspace="/home/user/erplibre")
        self.assertIn("/home/user/erplibre", task._build_claude_prompt())

    def test_includes_module_name(self):
        task = self._make_task(claude_module_name="sale_custom_discount")
        self.assertIn("sale_custom_discount", task._build_claude_prompt())

    def test_includes_working_dir(self):
        task = self._make_task(claude_working_dir="/home/user/code")
        self.assertIn("/home/user/code", task._build_claude_prompt())

    def test_strips_html_tags_from_description(self):
        task = self._make_task(description="<p>Fix the <b>bug</b> now</p>")
        prompt = task._build_claude_prompt()
        self.assertNotIn("<p>", prompt)
        self.assertNotIn("<b>", prompt)
        self.assertIn("Fix the", prompt)
        self.assertIn("bug", prompt)

    def test_omits_description_section_when_empty(self):
        task = self._make_task(name="No description here")
        # No description → the "Description :" header should not appear
        self.assertNotIn("Description", task._build_claude_prompt())

    def test_all_fields_present_in_combined_prompt(self):
        task = self._make_task(
            name="Build module",
            claude_workspace="/opt/erplibre",
            claude_module_name="my_module",
            claude_working_dir="/opt/code",
            description="<p>Create a new Odoo module for invoicing</p>",
        )
        prompt = task._build_claude_prompt()
        for expected in (
            "/opt/erplibre",
            "my_module",
            "/opt/code",
            "Build module",
            "Create a new Odoo module for invoicing",
        ):
            self.assertIn(expected, prompt, f"Expected '{expected}' in prompt")

    def test_workspace_takes_precedence_over_working_dir_in_prompt(self):
        task = self._make_task(
            claude_workspace="/workspace",
            claude_working_dir="/workdir",
        )
        prompt = task._build_claude_prompt()
        # Both should appear in the prompt (they are separate fields)
        self.assertIn("/workspace", prompt)
        self.assertIn("/workdir", prompt)


class TestProjetDevCodeActionsStart(ProjetDevCodeCommon):
    """action_start_claude state transitions and thread spawning."""

    def test_returns_warning_when_already_running(self):
        task = self._make_task()
        task.claude_status = "running"
        result = task.action_start_claude()
        self.assertIsNotNone(result)
        self.assertEqual(result.get("type"), "ir.actions.client")
        self.assertEqual(result.get("tag"), "display_notification")
        self.assertEqual(result["params"]["type"], "warning")

    @patch(f"{_MODULE}.threading.Thread")
    def test_sets_status_to_running(self, mock_thread):
        mock_thread.return_value = MagicMock()
        task = self._make_task(claude_workspace="/tmp")
        task.action_start_claude()
        self.assertEqual(task.claude_status, "running")

    @patch(f"{_MODULE}.threading.Thread")
    def test_resets_output_and_session_id(self, mock_thread):
        mock_thread.return_value = MagicMock()
        task = self._make_task(claude_workspace="/tmp")
        task.write({"claude_output": "stale output", "claude_session_id": "old-id"})
        task.action_start_claude()
        self.assertFalse(task.claude_session_id)

    @patch(f"{_MODULE}.threading.Thread")
    def test_spawns_exactly_one_daemon_thread(self, mock_thread):
        mock_instance = MagicMock()
        mock_thread.return_value = mock_instance
        task = self._make_task(claude_workspace="/tmp")
        task.action_start_claude()
        mock_thread.assert_called_once()
        mock_instance.start.assert_called_once()
        # Thread must be daemon so it does not block Odoo shutdown
        call_kwargs = mock_thread.call_args.kwargs
        self.assertTrue(call_kwargs.get("daemon"), "Thread must be daemon=True")

    @patch(f"{_MODULE}.threading.Thread")
    def test_workspace_passed_as_cwd_to_thread(self, mock_thread):
        mock_thread.return_value = MagicMock()
        task = self._make_task(claude_workspace="/my/workspace")
        task.action_start_claude()
        thread_args = mock_thread.call_args.kwargs.get("args", ())
        self.assertIn("/my/workspace", thread_args)

    @patch(f"{_MODULE}.threading.Thread")
    def test_falls_back_to_working_dir_when_no_workspace(self, mock_thread):
        mock_thread.return_value = MagicMock()
        task = self._make_task(
            claude_workspace=False, claude_working_dir="/my/workdir"
        )
        task.action_start_claude()
        thread_args = mock_thread.call_args.kwargs.get("args", ())
        self.assertIn("/my/workdir", thread_args)

    @patch(f"{_MODULE}.threading.Thread")
    def test_api_key_from_settings_passed_to_thread(self, mock_thread):
        mock_thread.return_value = MagicMock()
        self.env["ir.config_parameter"].sudo().set_param(
            "projet_dev_code.anthropic_api_key", "sk-ant-test"
        )
        task = self._make_task(claude_workspace="/tmp")
        task.action_start_claude()
        thread_args = mock_thread.call_args.kwargs.get("args", ())
        self.assertIn("sk-ant-test", thread_args)

    @patch(f"{_MODULE}.threading.Thread")
    def test_cli_path_from_settings_passed_to_thread(self, mock_thread):
        mock_thread.return_value = MagicMock()
        self.env["ir.config_parameter"].sudo().set_param(
            "projet_dev_code.cli_path", "/usr/local/bin/claude"
        )
        task = self._make_task(claude_workspace="/tmp")
        task.action_start_claude()
        thread_args = mock_thread.call_args.kwargs.get("args", ())
        self.assertIn("/usr/local/bin/claude", thread_args)


class TestProjetDevCodeActionsStop(ProjetDevCodeCommon):
    """action_stop_claude correctly signals the background thread."""

    def test_sets_status_to_draft(self):
        task = self._make_task()
        task.claude_status = "running"
        task.action_stop_claude()
        self.assertEqual(task.claude_status, "draft")

    def test_signals_registered_stop_event(self):
        from odoo.addons.projet_dev_code.models.project_task import (
            _STOP_EVENTS,
            _STOP_EVENTS_LOCK,
        )

        task = self._make_task()
        stop_event = threading.Event()
        with _STOP_EVENTS_LOCK:
            _STOP_EVENTS[task.id] = stop_event

        task.claude_status = "running"
        task.action_stop_claude()

        self.assertTrue(stop_event.is_set())

        # Cleanup so this task id does not leak to other tests
        with _STOP_EVENTS_LOCK:
            _STOP_EVENTS.pop(task.id, None)

    def test_does_not_raise_when_no_event_registered(self):
        task = self._make_task()
        task.claude_status = "running"
        # Must not raise even when there is no matching stop event
        task.action_stop_claude()
        self.assertEqual(task.claude_status, "draft")


class TestProjetDevCodeActionsRefresh(ProjetDevCodeCommon):
    """action_refresh_output returns the correct client action."""

    def test_returns_reload_action(self):
        task = self._make_task()
        result = task.action_refresh_output()
        self.assertEqual(result["type"], "ir.actions.client")
        self.assertEqual(result["tag"], "reload")


class TestProjetDevCodeSettings(ProjetDevCodeCommon):
    """res.config.settings fields are stored in ir.config_parameter."""

    def test_api_key_is_persisted(self):
        self.env["res.config.settings"].create(
            {"claude_anthropic_api_key": "sk-ant-test-key"}
        ).execute()
        stored = self.env["ir.config_parameter"].sudo().get_param(
            "projet_dev_code.anthropic_api_key"
        )
        self.assertEqual(stored, "sk-ant-test-key")

    def test_cli_path_is_persisted(self):
        self.env["res.config.settings"].create(
            {"claude_cli_path": "/usr/local/bin/claude"}
        ).execute()
        stored = self.env["ir.config_parameter"].sudo().get_param(
            "projet_dev_code.cli_path"
        )
        self.assertEqual(stored, "/usr/local/bin/claude")

    def test_settings_fields_exist_on_model(self):
        settings = self.env["res.config.settings"].new({})
        self.assertIn("claude_anthropic_api_key", settings._fields)
        self.assertIn("claude_cli_path", settings._fields)
