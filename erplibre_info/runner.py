# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
"""Run the ERPLibre scripts that read or change the code of the checkout.

The scripts live in the ERPLibre checkout, run with its own interpreter
(``.venv.erplibre/bin/python``) and print JSON on stdout. Nothing here
runs git itself: the scripts own every git call and its options.
"""

import json
import logging
import os
import re
import signal
import subprocess
from collections import namedtuple

import odoo
from odoo.tools import str2bool

_logger = logging.getLogger(__name__)

SCRIPT_STATE = "script/git/repo_state.py"
SCRIPT_UPGRADE = "script/git/repo_upgrade.py"
SCRIPT_APPLY = "script/git/repo_apply.py"
SCRIPT_PULL = "script/git/repo_pull.py"
PYTHON = ".venv.erplibre/bin/python"
# A file every ERPLibre checkout holds, old releases included: it tells a
# checkout too old for a script from no checkout at all.
CHECKOUT_MARKER = "env_var.sh"

PARAM_ROOT = "erplibre_info.root"
PARAM_TIMEOUT = "erplibre_info.timeout"
PARAM_LONG_TIMEOUT = "erplibre_info.long_timeout"
DEFAULT_TIMEOUT = 120
DEFAULT_LONG_TIMEOUT = 3600

# Environment variables of the Odoo process that would make the ERPLibre
# interpreter load Odoo's packages instead of its own.
_ENV_DROPPED = ("PYTHONPATH", "PYTHONHOME", "PYTHONSTARTUP", "VIRTUAL_ENV")

# The user-info part of a URL: « https://user:token@host/... ».
_CREDENTIALS = re.compile(r"(?P<scheme>\b[a-z][a-z0-9+.-]*://)[^/@\s]+@", re.I)

Result = namedtuple("Result", "returncode data stderr command")


class RunnerError(Exception):
    """The script cannot run, or its output is not the JSON expected."""


class RunnerTimeout(RunnerError):
    """The script did not finish within its timeout; its process group was
    killed."""


def strip_credentials(text):
    """Return ``text`` with the user-info part of every URL removed."""
    if not text or not isinstance(text, str):
        return text
    return _CREDENTIALS.sub(r"\g<scheme>", text)


def scrub(data):
    """Return a copy of a JSON value with credentials removed from strings."""
    if isinstance(data, dict):
        return {k: scrub(v) for k, v in data.items()}
    if isinstance(data, list):
        return [scrub(v) for v in data]
    return strip_credentials(data)


def find_root(start, rel=SCRIPT_STATE):
    """The first parent of ``start`` that holds the file ``rel``, by default
    ``script/git/repo_state.py``.

    The Odoo package sits at ``<root>/odoo<V>/odoo/odoo``: three levels
    under the checkout. Six levels bound the walk.
    """
    path = os.path.realpath(start)
    for _level in range(6):
        if os.path.isfile(os.path.join(path, rel)):
            return path
        parent = os.path.dirname(path)
        if parent == path:
            break
        path = parent
    return None


def erplibre_root(env):
    """The ERPLibre checkout: the ``erplibre_info.root`` parameter when set,
    else the checkout found above the running Odoo. None when neither holds
    the scripts."""
    configured = env["ir.config_parameter"].sudo().get_param(PARAM_ROOT)
    if configured:
        configured = os.path.realpath(configured)
        if os.path.isfile(os.path.join(configured, SCRIPT_STATE)):
            return configured
        return None
    return find_root(os.path.dirname(odoo.__file__))


def timeout(env, long=False):
    """Seconds allowed to one script call, from the system parameters."""
    name, default = (
        (PARAM_LONG_TIMEOUT, DEFAULT_LONG_TIMEOUT)
        if long
        else (PARAM_TIMEOUT, DEFAULT_TIMEOUT)
    )
    value = env["ir.config_parameter"].sudo().get_param(name)
    try:
        return max(1, int(value)) if value else default
    except ValueError:
        return default


def param_bool(env, name, default=False):
    value = env["ir.config_parameter"].sudo().get_param(name)
    return str2bool(value, default) if value else default


def checkout_problem(env, script=SCRIPT_STATE):
    """Why ``script`` cannot run: a translated message, or None when the
    checkout, its interpreter and the script are all in place. Reads the
    file system only."""
    root = erplibre_root(env)
    if not root:
        configured = env["ir.config_parameter"].sudo().get_param(PARAM_ROOT)
        if configured:
            checkout = os.path.realpath(configured)
            if not os.path.isdir(checkout):
                return env._(
                    "The directory %(root)s, set in the system parameter "
                    "%(param)s, does not exist.",
                    root=checkout,
                    param=PARAM_ROOT,
                )
        else:
            checkout = find_root(os.path.dirname(odoo.__file__), CHECKOUT_MARKER)
        if checkout:
            return _missing_feature(env, checkout, SCRIPT_STATE)
        return env._(
            "ERPLibre is missing this feature, are you on the right "
            "version? Set the system parameter %(param)s to the directory "
            "that holds %(script)s.",
            param=PARAM_ROOT,
            script=SCRIPT_STATE,
        )
    python = os.path.join(root, PYTHON)
    if not os.access(python, os.X_OK):
        return env._(
            "The ERPLibre interpreter %(python)s is missing.",
            python=python,
        )
    if not os.path.isfile(os.path.join(root, script)):
        return _missing_feature(env, root, script)
    return None


def _missing_feature(env, checkout, script):
    """The message for a checkout ``checkout`` that exists but lacks
    ``script``: an ERPLibre older than the feature that needs it."""
    return env._(
        "ERPLibre is missing this feature, are you on the right version? "
        "The script %(script)s does not exist in %(root)s.",
        script=script,
        root=checkout,
    )


def permission_warning(env, data):
    """The translated warning for the ``permissions`` key of a script's
    JSON, or False when it is empty: the account that cannot read the
    clones, their owner, and the command that makes them readable."""
    advice = (data or {}).get("permissions")
    if not advice:
        return False
    values = {
        "account": advice.get("account") or "?",
        "owner": advice.get("owner") or "?",
        "count": advice.get("count") or 0,
        "command": advice.get("command"),
        "container": advice.get("container"),
    }
    if not values["command"]:
        return env._(
            "Missing permissions: the account %(account)s cannot read "
            "%(count)s git repositories owned by %(owner)s. Give it read "
            "access to their .git directories.",
            **values,
        )
    text = env._(
        "Missing permissions: the account %(account)s cannot read "
        "%(count)s git repositories owned by %(owner)s. Run as root: "
        "%(command)s",
        **values,
    )
    if values["container"]:
        text += " " + env._(
            "From the Docker host: docker exec -u root %(container)s " "%(command)s",
            **values,
        )
    return text


def _run_process(argv, cwd, env, timeout):
    """``subprocess.run`` of ``argv`` in a session of its own, output
    captured as text; return the ``CompletedProcess``.

    On timeout the whole process group is killed, not only the script: the
    git, repo and poetry processes it started do not outlive it, and the
    checkout lock they would keep busy is released with them. Raise
    ``subprocess.TimeoutExpired`` then.
    """
    with subprocess.Popen(
        argv,
        cwd=cwd,
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
    ) as proc:
        try:
            stdout, stderr = proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except OSError:
                pass
            proc.communicate()
            raise
    return subprocess.CompletedProcess(argv, proc.returncode, stdout, stderr)


def run(env, script, args, timeout_s=None):
    """Run ``script`` of the checkout with ``args``; return a ``Result``.

    ``data`` is the decoded JSON of stdout, or None when stdout is not
    JSON. ``stderr`` is stripped of URL credentials. Raise ``RunnerError``
    when the checkout, its interpreter or the script is missing (see
    ``checkout_problem``), and ``RunnerTimeout`` when the call exceeds
    ``timeout_s`` (see ``_run_process``). stdin is closed: no prompt can
    wait.
    """
    problem = checkout_problem(env, script)
    if problem:
        raise RunnerError(problem)
    root = erplibre_root(env)
    python = os.path.join(root, PYTHON)
    script_path = os.path.join(root, script)
    variables = {k: v for k, v in os.environ.items() if k not in _ENV_DROPPED}
    variables["GIT_TERMINAL_PROMPT"] = "0"
    command = " ".join([PYTHON, script, *args])
    timeout_s = timeout_s or timeout(env)
    _logger.info("ERPLibre script: %s", command)
    try:
        proc = _run_process(
            [python, script_path, *args],
            cwd=root,
            env=variables,
            timeout=timeout_s,
        )
    except subprocess.TimeoutExpired as exc:
        raise RunnerTimeout(
            env._(
                "%(command)s did not finish within %(seconds)s seconds.",
                command=command,
                seconds=timeout_s,
            )
        ) from exc
    except OSError as exc:
        raise RunnerError(
            env._(
                "%(command)s cannot start: %(error)s",
                command=command,
                error=exc,
            )
        ) from exc
    data = None
    if proc.stdout and proc.stdout.strip():
        try:
            data = scrub(json.loads(proc.stdout))
        except ValueError:
            data = None
    return Result(proc.returncode, data, strip_credentials(proc.stderr), command)


def run_json(env, script, args, timeout_s=None, ok_codes=(0,)):
    """``run``, then raise ``RunnerError`` unless the exit code is in
    ``ok_codes`` and stdout is a JSON object."""
    res = run(env, script, args, timeout_s)
    if res.returncode not in ok_codes or not isinstance(res.data, dict):
        detail = (res.data or {}).get("error") if isinstance(res.data, dict) else ""
        detail = detail or (res.stderr or "").strip()[-2000:]
        raise RunnerError(
            env._(
                "%(command)s failed (exit code %(code)s): %(detail)s",
                command=res.command,
                code=res.returncode,
                detail=detail,
            )
        )
    return res
