# © 2021-2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
"""The values of the ERPLibre block of *Settings › About*: what
``make version`` prints, plus the commit of the checkout and its code mode.

Every value comes from the file ``script/version/update_env_version.py``
reads for it, or from a read-only git command bounded by ``GIT_TIMEOUT``.
A missing or unreadable file, and a git command that fails, give None:
the block says « unknown » for it. Nothing is written: git runs with
``GIT_OPTIONAL_LOCKS=0`` (no index refresh) and its ``safe.directory``
is passed on the command line, never stored.
"""

import json
import os
import re
import subprocess
import xml.etree.ElementTree as ET

SEMVER_FILE = ".erplibre-semver-version"
PYTHON_ODOO_FILE = ".python-odoo-version"
PYTHON_TOOLING_FILE = os.path.join("conf", "python-erplibre-version")
ODOO_FILE = ".odoo-version"
POETRY_FILE = ".poetry-version"
VERSION_DATA_FILE = os.path.join("conf", "supported_version_erplibre.json")
INSTALLED_FILE = os.path.join(".repo", "installed_odoo_version.txt")
STATE_FILE = ".erplibre-state.json"
MOBILE_PATH = os.path.join("mobile", "erplibre_home_mobile")
LOCAL_MANIFEST = os.path.join(".repo", "local_manifests", "erplibre_manifest.xml")

# Seconds allowed to each git command: the Settings form waits for them.
GIT_TIMEOUT = 3

_SHA = re.compile(r"[0-9a-f]{40}")


def read_text(root, rel):
    """The stripped content of ``root/rel``, or None when it is missing,
    unreadable or empty."""
    try:
        with open(os.path.join(root, rel), encoding="utf-8") as fh:
            return fh.read().strip() or None
    except (OSError, UnicodeDecodeError):
        return None


def read_json(root, rel):
    """The JSON object of ``root/rel``, or None."""
    text = read_text(root, rel)
    if not text:
        return None
    try:
        data = json.loads(text)
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


def version_key(root, odoo_version, python_version):
    """The key of ``conf/supported_version_erplibre.json`` whose entry
    carries this Odoo and Python version, as ``update_env_version.py``
    detects it; None without a match."""
    data = read_json(root, VERSION_DATA_FILE) or {}
    for key, value in data.items():
        if (
            isinstance(value, dict)
            and value.get("odoo_version") == odoo_version
            and value.get("python_version") == python_version
        ):
            return key
    return None


def extra_active(root, odoo_version):
    """Whether ``.erplibre-state.json`` records the extra modules for this
    Odoo version. A missing or unreadable file is an empty state: inactive,
    as ``erplibre_state.get_version_extra`` reads it."""
    state = read_json(root, STATE_FILE) or {}
    entry = (state.get("odoo_versions") or {}).get(odoo_version)
    return bool(isinstance(entry, dict) and entry.get("extra"))


def manifest_mode(root):
    """« frozen » when the local manifest pins a project on a full commit,
    « branches » when it follows branches, None when it is missing or
    unreadable: ``update_env_version.local_manifest_frozen``."""
    try:
        tree = ET.parse(os.path.join(root, LOCAL_MANIFEST)).getroot()
    except (OSError, ET.ParseError):
        return None
    frozen = any(_SHA.fullmatch(p.get("revision") or "") for p in tree.iter("project"))
    return "frozen" if frozen else "branches"


def git(root, *args):
    """The stripped output of the read-only ``git args`` in ``root``, or
    None when git is missing, fails or exceeds ``GIT_TIMEOUT``. The root
    may belong to another account: ``safe.directory`` is given for this
    command only."""
    env = dict(os.environ, GIT_TERMINAL_PROMPT="0", GIT_OPTIONAL_LOCKS="0")
    try:
        proc = subprocess.run(
            ["git", "-c", "safe.directory=*", "-C", root, *args],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=GIT_TIMEOUT,
            env=env,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    out = proc.stdout.strip()
    return out if proc.returncode == 0 and out else None


def commit_info(root):
    """{short, branch, describe} of the HEAD of ``root``; each is None when
    git cannot tell it, ``branch`` also on a detached HEAD."""
    if not os.path.exists(os.path.join(root, ".git")):
        return {"short": None, "branch": None, "describe": None}
    return {
        "short": git(root, "rev-parse", "--short", "HEAD"),
        "branch": git(root, "symbolic-ref", "--short", "-q", "HEAD"),
        "describe": git(root, "describe", "--tags"),
    }


def read(root):
    """The values of the block for the checkout ``root``, None for a value
    no source gives; ``root`` None (no checkout found) gives only that."""
    if not root:
        return {
            "semver": None,
            "python_odoo": None,
            "python_tooling": None,
            "odoo_version": None,
            "poetry_version": None,
            "mobile": None,
            "mobile_path": MOBILE_PATH,
            "extra": None,
            "version_key": None,
            "installed_versions": [],
            "commit": {"short": None, "branch": None, "describe": None},
            "mode": None,
        }
    odoo_version = read_text(root, ODOO_FILE)
    python_odoo = read_text(root, PYTHON_ODOO_FILE)
    installed = read_text(root, INSTALLED_FILE)
    return {
        "semver": read_text(root, SEMVER_FILE),
        "python_odoo": python_odoo,
        "python_tooling": read_text(root, PYTHON_TOOLING_FILE),
        "odoo_version": odoo_version,
        "poetry_version": read_text(root, POETRY_FILE),
        "mobile": os.path.isdir(os.path.join(root, MOBILE_PATH)),
        "mobile_path": MOBILE_PATH,
        "extra": extra_active(root, odoo_version) if odoo_version else None,
        "version_key": (
            version_key(root, odoo_version, python_odoo)
            if odoo_version and python_odoo
            else None
        ),
        "installed_versions": sorted(installed.splitlines()) if installed else [],
        "commit": commit_info(root),
        "mode": manifest_mode(root),
    }
