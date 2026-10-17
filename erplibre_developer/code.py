# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
"""The git clone that holds a module, and its recent commits.

The repository state comes from erplibre_info (its snapshots, or
``repo_state.py`` through its runner). The only git call made here is a
read-only ``git log`` bounded by the erplibre_info timeout and a commit
count, with stdin closed and no prompt possible.
"""

import os
import subprocess

from odoo.addons.erplibre_info import runner

# A field separator that never appears in a commit subject.
_SEP = "\x1f"
LOG_FORMAT = _SEP.join(("%H", "%an", "%aI", "%s"))
MAX_COMMITS = 100


class GitLogError(Exception):
    """git log cannot run or fails."""


def repository_of(path, stop=None):
    """The top directory of the git clone that holds ``path``: the first
    parent with a ``.git`` entry (a directory, a file or a link), never
    above ``stop``. None outside any clone."""
    current = os.path.realpath(path)
    stop = os.path.realpath(stop) if stop else None
    while True:
        if os.path.lexists(os.path.join(current, ".git")):
            return current
        if stop and current == stop:
            return None
        parent = os.path.dirname(current)
        if parent == current:
            return None
        current = parent


def relative_to(path, root):
    """``path`` relative to ``root`` when it lies under it, else
    ``path`` unchanged. False stays False."""
    if not path or not root:
        return path
    real = os.path.realpath(path)
    root = os.path.realpath(root)
    if real == root or real.startswith(root + os.sep):
        return os.path.relpath(real, root)
    return path


def git_log(env, clone, rel_path, limit=20):
    """The last ``limit`` commits of ``clone`` that touch ``rel_path``:
    a list of {sha, author, date, subject}, most recent first.

    Raise ``GitLogError`` when git cannot run, fails or exceeds the
    erplibre_info timeout."""
    limit = max(1, min(int(limit or 20), MAX_COMMITS))
    variables = {k: v for k, v in os.environ.items() if k not in runner._ENV_DROPPED}
    variables.update(GIT_TERMINAL_PROMPT="0", GIT_OPTIONAL_LOCKS="0")
    command = [
        "git",
        "-C",
        clone,
        "log",
        "--no-color",
        f"--max-count={limit}",
        f"--format={LOG_FORMAT}",
        "--",
        rel_path or ".",
    ]
    try:
        proc = subprocess.run(
            command,
            env=variables,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=runner.timeout(env),
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise GitLogError(
            env._("git log did not finish within %(s)s seconds.", s=exc.timeout)
        ) from exc
    except OSError as exc:
        raise GitLogError(env._("git cannot start: %(error)s", error=exc)) from exc
    if proc.returncode:
        raise GitLogError(
            runner.strip_credentials((proc.stderr or "").strip()[-2000:])
            or env._("git log failed (exit code %(code)s).", code=proc.returncode)
        )
    commits = []
    for line in proc.stdout.splitlines():
        parts = line.split(_SEP)
        if len(parts) != 4:
            continue
        sha, author, date, subject = parts
        commits.append({"sha": sha, "author": author, "date": date, "subject": subject})
    return commits
