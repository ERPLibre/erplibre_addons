# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo.addons.erplibre_info.tests.common import (
    PULL_DIR,
    PULL_DRY_RUN,
    PULL_STAMP,
    REPO,
    REPO_CORE,
    REPO_OTHER,
    SERIES,
)
from odoo.addons.erplibre_info_git.tests.common import ErplibreInfoGitCase

STASH_SHA = "5" * 40


class ErplibreInfoGitFetchCase(ErplibreInfoGitCase):
    """The fake checkout and the snapshot model, for the server actions;
    ``server_actions_allowed(dev=False)`` stands for a server started
    without ``--dev``."""


def _revert_repo(path, verdict, **values):
    """One repository of the dry run of a return, with the keys of the
    script."""
    repo = {
        "chemin": path,
        "nom": None,
        "branche": None,
        "detache": True,
        "remote": "Example",
        "cible": None,
        "cible_sha": None,
        "cible_branche": None,
        "source_cible": "instantane",
        "head": None,
        "nos": 0,
        "retard": 0,
        "quittes": None,
        "locaux": None,
        "base": None,
        "superficiel": False,
        "sale": False,
        "non_suivis": 0,
        "stash_prevu": False,
        "operation_en_cours": None,
        "verdict": verdict,
        "applicable": False,
        "sauvegarde_prefixe": f"{SERIES}_avant_retour_",
        "fetch": None,
        "motif": None,
        "erreur": None,
    }
    repo.update(values)
    return repo


REVERT_DRY_RUN = {
    "schema": 1,
    "command": "dry-run",
    "generated_at": "2000-01-01T00:00:00+00:00",
    "root": "",
    "version": SERIES,
    "mode": "instantane",
    "chemin_seul": None,
    "depots": [
        _revert_repo(
            ".",
            "recul",
            branche="example",
            detache=False,
            head="0" * 40,
            cible="a" * 40,
            cible_sha="a" * 40,
            cible_branche="example",
            nos=1,
            quittes=1,
            locaux=0,
            applicable=True,
            sauvegarde_prefixe="example_avant_retour_",
        ),
        _revert_repo(
            REPO,
            "deplacement",
            head="c" * 40,
            cible="1" * 40,
            cible_sha="1" * 40,
            nos=3,
            quittes=3,
            locaux=2,
            applicable=True,
            sale=True,
            stash_prevu=True,
        ),
        _revert_repo(
            REPO_CORE,
            "a_jour",
            head="2" * 40,
            cible="2" * 40,
            cible_sha="2" * 40,
            quittes=0,
            locaux=0,
        ),
        _revert_repo(
            REPO_OTHER,
            "commit_introuvable",
            head="9" * 40,
            cible="4" * 40,
            cible_sha="4" * 40,
            motif="commit not found on Example",
        ),
    ],
    "hors_instantane": ["odooX/outside"],
    "dependances": dict(PULL_DRY_RUN["dependances"]),
    "plan": [".", REPO],
    "attendus": [f".={'a' * 40}:{'0' * 40}", f"{REPO}={'1' * 40}:{'c' * 40}"],
    "counts": {
        "recul": 1,
        "deplacement": 1,
        "a_jour": 1,
        "commit_introuvable": 1,
    },
    "errors": [],
}


def _revert_result(path, state, start, end, backup, **values):
    """One repository of the apply step of a return, with the keys of the
    script."""
    result = {
        "chemin": path,
        "verdict_avant": None,
        "etat": state,
        "branche": None,
        "detache": True,
        "cible": end,
        "cible_sha": end,
        "cible_branche": None,
        "branche_arrivee": None,
        "depart": start,
        "arrivee": end,
        "sauvegarde": backup,
        "sauvegarde_cible": None,
        "stash": {
            "etat": "aucun",
            "sha": None,
            "commande": None,
            "message": None,
        },
        "approfondi": None,
        "conflits": [],
        "ecrases": [],
        "copie_ecrases": None,
        "sortie": "",
        "motif": None,
    }
    result.update(values)
    return result


REVERT_APPLY = {
    "schema": 1,
    "command": "apply",
    "version": SERIES,
    "mode": "instantane",
    "chemin_seul": None,
    "horodatage": PULL_STAMP,
    "dossier": PULL_DIR,
    "plan": [".", REPO],
    "attendus": [".", REPO],
    "derives": [],
    "resultats": [
        _revert_result(
            REPO,
            "recule",
            "c" * 40,
            "1" * 40,
            f"{SERIES}_avant_retour_{PULL_STAMP}",
            stash={
                "etat": "garde",
                "sha": STASH_SHA,
                "commande": f"git -C {REPO} stash apply {STASH_SHA}",
                "message": f"repo_pull retour {PULL_STAMP}",
            },
        ),
        _revert_result(
            ".",
            "recule",
            "0" * 40,
            "a" * 40,
            f"example_avant_retour_{PULL_STAMP}",
            branche="example",
            detache=False,
            cible_branche="example",
            branche_arrivee="example",
        ),
        _revert_result(
            REPO_OTHER,
            "saute_introuvable",
            "9" * 40,
            None,
            None,
            motif="commit not found on Example",
        ),
    ],
    "manifeste": {
        "etat_actuel": "branches",
        "regenere": True,
        "ecrit": True,
        "copie_avant": f"{PULL_DIR}/erplibre_manifest.avant.xml",
        "changements": [],
        "erreur": None,
    },
    "dependances": dict(PULL_DRY_RUN["dependances"]),
    "budget_epuise": False,
    "error": None,
}

STASH_APPLIED = {
    "schema": 1,
    "command": "apply-stash",
    "chemin": REPO,
    "sha": STASH_SHA,
    "etat": "applique",
    "motif": None,
    "conflits": [],
}
