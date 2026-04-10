#!/usr/bin/env python3
# © 2025 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
import asyncio
import logging
import threading
from html import unescape
from re import compile as re_compile

import odoo
from odoo import _, api, fields, models

_logger = logging.getLogger(__name__)

_HTML_TAG_RE = re_compile(r"<[^>]+>")

# Thread-safe stop signals: task_id -> threading.Event
_STOP_EVENTS: dict = {}
_STOP_EVENTS_LOCK = threading.Lock()


class ProjectTask(models.Model):
    _inherit = "project.task"

    # ── Configuration ────────────────────────────────────────────────────────

    claude_workspace = fields.Char(
        string="Workspace ERPLibre",
        help=(
            "Chemin absolu du workspace ERPLibre à utiliser comme répertoire"
            " de travail pour l'agent Claude Code"
        ),
    )
    claude_working_dir = fields.Char(
        string="Répertoire de travail",
        help=(
            "Répertoire racine du code source sur lequel Claude va travailler."
            " Utilisé si le workspace ERPLibre n'est pas renseigné."
        ),
    )
    claude_module_name = fields.Char(
        string="Nom du module",
        help="Nom du module Odoo à développer (ex: sale_custom_discount)",
    )

    # ── Runtime state ─────────────────────────────────────────────────────────

    claude_status = fields.Selection(
        selection=[
            ("draft", "En attente"),
            ("running", "En cours"),
            ("done", "Terminé"),
            ("error", "Erreur"),
        ],
        string="Statut Claude",
        default="draft",
        readonly=True,
        tracking=True,
    )
    claude_session_id = fields.Char(
        string="Session ID Claude",
        readonly=True,
        help="Identifiant de session Claude Code (pour reprendre ou déboguer)",
    )
    claude_output = fields.Text(
        string="Output Claude",
        readonly=True,
        help="Sortie de l'agent Claude Code en temps réel",
    )

    # ── Actions ───────────────────────────────────────────────────────────────

    def action_start_claude(self):
        """Démarrer l'agent Claude Code dans un thread d'arrière-plan."""
        self.ensure_one()
        if self.claude_status == "running":
            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "title": _("Claude Code"),
                    "message": _("Un agent Claude est déjà en cours d'exécution."),
                    "type": "warning",
                    "sticky": False,
                },
            }

        # Enregistrer un nouvel événement d'arrêt pour cette tâche
        with _STOP_EVENTS_LOCK:
            _STOP_EVENTS[self.id] = threading.Event()

        self.write(
            {
                "claude_status": "running",
                "claude_output": _(
                    "Démarrage de l'agent Claude Code…\n"
                ),
                "claude_session_id": False,
            }
        )

        prompt = self._build_claude_prompt()
        cwd = self.claude_workspace or self.claude_working_dir or "."
        task_id = self.id
        dbname = self.env.cr.dbname

        thread = threading.Thread(
            target=_run_claude_in_thread,
            args=(task_id, dbname, prompt, cwd),
            name=f"claude-task-{task_id}",
            daemon=True,
        )
        thread.start()

    def action_stop_claude(self):
        """Signaler l'arrêt de l'agent Claude en cours."""
        self.ensure_one()
        with _STOP_EVENTS_LOCK:
            event = _STOP_EVENTS.get(self.id)
        if event:
            event.set()
        self.write({"claude_status": "draft"})

    def action_refresh_output(self):
        """Recharger la vue pour voir l'output mis à jour."""
        return {
            "type": "ir.actions.client",
            "tag": "reload",
        }

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _build_claude_prompt(self):
        """Construire le prompt envoyé à Claude à partir des champs de la tâche."""
        lines = []

        if self.claude_workspace:
            lines.append(f"Workspace ERPLibre : {self.claude_workspace}")
        if self.claude_module_name:
            lines.append(f"Module Odoo à développer : {self.claude_module_name}")
        if self.claude_working_dir:
            lines.append(f"Répertoire de travail : {self.claude_working_dir}")

        task_name = self.name or "(sans titre)"
        lines.append(f"\n## Tâche : {task_name}")

        description = self.description or ""
        # Supprimer les balises HTML
        description = _HTML_TAG_RE.sub(" ", description)
        description = unescape(description).strip()
        if description:
            lines.append(f"\n## Description :\n{description}")

        return "\n".join(lines)


# ── Fonctions de thread (hors classe ORM) ─────────────────────────────────────


def _run_claude_in_thread(task_id: int, dbname: str, prompt: str, cwd: str):
    """Point d'entrée du thread d'arrière-plan."""
    try:
        asyncio.run(_run_claude_async(task_id, dbname, prompt, cwd))
    except Exception:
        _logger.exception(
            "Erreur non gérée dans le thread Claude (task %s)", task_id
        )


async def _run_claude_async(
    task_id: int, dbname: str, prompt: str, cwd: str
):
    """Exécuter l'agent Claude Code via le SDK asynchrone."""
    try:
        from claude_agent_sdk import ClaudeAgentOptions, query
    except ImportError:
        _update_task_db(
            task_id,
            dbname,
            output=(
                "Erreur : le module 'claude-agent-sdk' n'est pas installé.\n"
                "Exécutez dans le venv Odoo 18 :\n"
                "  pip install claude-agent-sdk\n"
            ),
            status="error",
        )
        return

    with _STOP_EVENTS_LOCK:
        stop_event = _STOP_EVENTS.get(task_id)

    options = ClaudeAgentOptions(
        permission_mode="acceptEdits",
        cwd=cwd,
    )

    output_chunks: list[str] = []

    try:
        async for message in query(prompt=prompt, options=options):
            # Vérifier si l'utilisateur a demandé l'arrêt
            if stop_event and stop_event.is_set():
                _update_task_db(
                    task_id,
                    dbname,
                    output="\n".join(output_chunks) + "\n\n[Arrêté par l'utilisateur]",
                    status="draft",
                )
                return

            # AssistantMessage : contient des blocs de texte
            if hasattr(message, "content") and isinstance(
                message.content, list
            ):
                for block in message.content:
                    if hasattr(block, "text") and isinstance(block.text, str):
                        output_chunks.append(block.text)
                _update_task_db(
                    task_id,
                    dbname,
                    output="\n".join(output_chunks),
                    status="running",
                )

            # ResultMessage : résultat final
            elif hasattr(message, "is_error") and hasattr(
                message, "session_id"
            ):
                final_output = "\n".join(output_chunks)
                if getattr(message, "result", None):
                    final_output += f"\n\n---\nRésultat : {message.result}"
                cost = getattr(message, "total_cost_usd", None)
                if cost is not None:
                    final_output += f"\nCoût : ${cost:.4f}"
                status = "error" if message.is_error else "done"
                _update_task_db(
                    task_id,
                    dbname,
                    output=final_output,
                    status=status,
                    session_id=message.session_id,
                )

    except Exception as exc:
        _logger.exception(
            "Erreur lors de l'exécution de l'agent Claude (task %s)", task_id
        )
        current = "\n".join(output_chunks)
        separator = "\n\n" if current else ""
        _update_task_db(
            task_id,
            dbname,
            output=f"{current}{separator}Erreur : {exc}",
            status="error",
        )
    finally:
        with _STOP_EVENTS_LOCK:
            _STOP_EVENTS.pop(task_id, None)


def _update_task_db(
    task_id: int,
    dbname: str,
    output: str,
    status: str | None = None,
    session_id: str | None = None,
):
    """
    Mettre à jour les champs Claude de la tâche depuis un thread d'arrière-plan.

    Utilise un curseur indépendant pour ne pas interférer avec la transaction
    principale d'Odoo.
    """
    try:
        registry = odoo.registry(dbname)
        with registry.cursor() as cr:
            env = odoo.api.Environment(cr, odoo.SUPERUSER_ID, {})
            vals: dict = {"claude_output": output}
            if status is not None:
                vals["claude_status"] = status
            if session_id is not None:
                vals["claude_session_id"] = session_id
            env["project.task"].browse(task_id).write(vals)
    except Exception:
        _logger.exception(
            "Impossible de mettre à jour la tâche %s dans la base de données",
            task_id,
        )
