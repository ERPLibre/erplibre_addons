# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
"""The version of a generated module: five parts, the Odoo series first
(« 18.0.1.0.0 »). Parts compare as integers, never as text."""

import re

from odoo.addons.erplibre_studio.arch import ArchError

_VERSION = re.compile(r"^(\d+\.\d+)\.(\d+)\.(\d+)\.(\d+)$")


def valid_version(version, series):
    """Whether ``version`` has 5 parts and starts with ``series``."""
    match = _VERSION.match(version or "")
    return bool(match and match.group(1) == series)


def _version_key(version):
    match = _VERSION.match(version or "")
    if not match:
        raise ArchError(
            f"Invalid version {version}.", "invalid_version", version=version
        )
    series, *parts = match.groups()
    return (*(int(p) for p in series.split(".")), *(int(p) for p in parts))


def bump_version(version):
    """The next patch version of a 5-part version."""
    _version_key(version)
    series, major, minor, patch = _VERSION.match(version).groups()
    return f"{series}.{major}.{minor}.{int(patch) + 1}"


def next_version(requested, generated):
    """The version of a generation: ``requested`` when nothing was
    generated yet or when it is above ``generated``, else the next patch
    version of ``generated``. Raise ``ArchError`` (code
    ``invalid_version``) on a version that has not 5 numeric parts."""
    if not generated:
        return requested
    if _version_key(requested) > _version_key(generated):
        return requested
    return bump_version(generated)
