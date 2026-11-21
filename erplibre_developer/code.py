# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
"""The git clone that holds a module, and its recent commits.

The repository state comes from the snapshots of erplibre_info_git, or
from ``repo_state.py`` through the runner of erplibre_info. The git calls
made here only read: ``git log``, ``git rev-list`` and ``git status``, each
bounded by the erplibre_info timeout and a count, with stdin closed, no
prompt possible and no optional lock taken (``git status`` does not
refresh the index file).
"""

import os
import re
import subprocess

from odoo.addons.erplibre_info import runner

# A field separator that never appears in a commit subject.
_SEP = "\x1f"
LOG_FORMAT = _SEP.join(("%H", "%an", "%aI", "%s"))
MAX_COMMITS = 100
MAX_DIRTY_FILES = 20
# A commit name given by a caller: hexadecimal only, never an option nor a
# revision expression.
_SHA = re.compile(r"^[0-9a-fA-F]{7,64}$")


class GitLogError(Exception):
    """A read-only git command cannot run, fails or exceeds the timeout."""


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


def is_sha(value):
    """Whether ``value`` is an abbreviated or full commit name."""
    return bool(value and isinstance(value, str) and _SHA.match(value))


def _git(env, clone, args, what):
    """The standard output of ``git -C clone <args>``. The process inherits
    the server environment without the Python variables of
    ``runner._ENV_DROPPED``, never prompts, takes no optional lock and reads
    nothing on stdin.

    Raise ``GitLogError`` when git cannot run, fails or exceeds the
    erplibre_info timeout; ``what`` names the command in the message."""
    variables = {k: v for k, v in os.environ.items() if k not in runner._ENV_DROPPED}
    variables.update(GIT_TERMINAL_PROMPT="0", GIT_OPTIONAL_LOCKS="0")
    try:
        proc = subprocess.run(
            ["git", "-C", clone, *args],
            env=variables,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=runner.timeout(env),
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise GitLogError(
            env._(
                "%(command)s did not finish within %(s)s seconds.",
                command=what,
                s=exc.timeout,
            )
        ) from exc
    except OSError as exc:
        raise GitLogError(env._("git cannot start: %(error)s", error=exc)) from exc
    if proc.returncode:
        raise GitLogError(
            runner.strip_credentials((proc.stderr or "").strip()[-2000:])
            or env._(
                "%(command)s failed (exit code %(code)s).",
                command=what,
                code=proc.returncode,
            )
        )
    return proc.stdout


def git_log(env, clone, rel_path, limit=20):
    """The last ``limit`` commits of ``clone`` that touch ``rel_path``:
    a list of {sha, author, date, subject}, most recent first.

    Raise ``GitLogError`` when git cannot run, fails or exceeds the
    erplibre_info timeout."""
    limit = max(1, min(int(limit or 20), MAX_COMMITS))
    out = _git(
        env,
        clone,
        [
            "log",
            "--no-color",
            f"--max-count={limit}",
            f"--format={LOG_FORMAT}",
            "--",
            rel_path or ".",
        ],
        "git log",
    )
    commits = []
    for line in out.splitlines():
        parts = line.split(_SEP)
        if len(parts) != 4:
            continue
        sha, author, date, subject = parts
        commits.append({"sha": sha, "author": author, "date": date, "subject": subject})
    return commits


def git_ahead(env, clone, target, limit=20):
    """The set of the full names of the commits of HEAD that ``target``
    does not contain, at most ``limit`` of them. The walk follows the order
    of ``git log``, so the set holds every such commit among the last
    ``limit`` commits of HEAD. ``target`` must be a commit name
    (``is_sha``).

    Raise ``GitLogError`` when git fails, for instance on a target the
    clone does not hold."""
    if not is_sha(target):
        raise GitLogError(env._("%(target)s is not a commit name.", target=target))
    limit = max(1, min(int(limit or 20), MAX_COMMITS))
    out = _git(
        env,
        clone,
        ["rev-list", f"--max-count={limit}", f"^{target}", "HEAD", "--"],
        "git rev-list",
    )
    return {line.strip() for line in out.splitlines() if line.strip()}


def git_status(env, clone, limit=MAX_DIRTY_FILES):
    """The uncommitted changes of ``clone``: (count, files), where count is
    the number of changed paths and files the first ``limit`` of them, as
    {status, path} with the two-letter status of ``git status --porcelain``
    and the path relative to the clone. An untracked directory counts as
    one path; a rename names its new path.

    Raise ``GitLogError`` when git cannot run, fails or exceeds the
    erplibre_info timeout."""
    limit = max(0, min(int(limit), MAX_DIRTY_FILES))
    out = _git(
        env,
        clone,
        ["status", "--porcelain=v1", "-z", "--untracked-files=normal"],
        "git status",
    )
    entries = out.split("\0")
    files = []
    count = 0
    index = 0
    while index < len(entries):
        entry = entries[index]
        index += 1
        if len(entry) < 4:
            continue
        status, path = entry[:2], entry[3:]
        if "R" in status or "C" in status:
            # -z writes the source path of a rename or copy as the next entry.
            index += 1
        count += 1
        if len(files) < limit:
            files.append({"status": status, "path": path})
    return count, files
