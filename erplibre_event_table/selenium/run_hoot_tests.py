#!/usr/bin/env python3
# Copyright 2026 TechnoLibre - Mathieu Benoit
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
"""Lance la suite hoot du module et rend un code de sortie, sans main humaine.

Les tests hoot vivent dans le navigateur : rien du cote Python ne les
declenche, et le lanceur node de static/tests/ ne couvre que la geometrie
pure. Ce scenario ouvre la page des tests, attend la fin de la suite, nomme
les tests rouges et sort non nul des qu'il en reste un.

Il lit le resultat dans l'objet du lanceur hoot plutot que dans la console :
hoot capture console.log et console.dir A SON CHARGEMENT (destructuration de
`globalThis.console` en tete de core/logger.js), donc une console remplacee
apres coup ne voit plus rien passer. L'objet, lui, reste joignable par le
chargeur de modules d'Odoo, que module_loader.js publie en `odoo.loader`.

Deux pieges que les options ci-dessous desarment :

- `debug=assets` est OBLIGATOIRE dans l'URL. Sans lui, l'instance sert le
  paquet d'actifs MINIFIE deja en cache : un fichier de test modifie ne
  change rien a ce qui s'execute, et le compte d'echecs reste identique sans
  qu'aucun avertissement ne le signale. Le parametre `debug` de hoot est une
  chaine sans effet sur le lanceur (core/config.js), donc le passer ne met
  pas hoot en mode debogage.
- le mode `headless` de HOOT n'est pas demande. Il efface les tests au fur et
  a mesure (`_erase`), et il ne resterait plus de nom a citer pour les
  rouges. Le mode sans fenetre du NAVIGATEUR est une autre affaire : c'est
  --headless, qui reste disponible.

La LISTE des fichiers d'actifs est gelee independamment de tout cela : un
fichier de test NOUVEAU n'apparait qu'apres un redemarrage de l'instance.
"""

import argparse
import json
import os
import sys
import time

RACINE = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "..")
)
sys.path.append(RACINE)

from script.selenium import selenium_lib, web_login  # noqa: E402

# Les etats que hoot donne a son lanceur (core/runner.js).
ETAT_FINI = "done"

# Rend l'objet du lanceur hoot, ou l'etape qui manque encore. La page charge
# une dizaine de megaoctets de sources non minifiees en mode debug, donc le
# lanceur n'existe pas des le retour de driver.get.
SONDE_LANCEUR = """
const loader = window.odoo && window.odoo.loader;
if (!loader) { return {etape: "chargeur absent"}; }
const mod = loader.modules.get("@web/../lib/hoot/main_runner");
if (!mod) { return {etape: "module main_runner non charge"}; }
const runner = mod.getRunner();
if (!runner) { return {etape: "lanceur non construit"}; }
return {etape: "pret", statut: runner.state.status,
        manuel: Boolean(runner.config.manual)};
"""

DEMARRAGE = """
const runner = window.odoo.loader.modules
    .get("@web/../lib/hoot/main_runner").getRunner();
runner.manualStart();
return runner.state.status;
"""

# Le compte rendu et les tests rouges, lus sur le lanceur. `reporting` porte
# les totaux, `tests` chaque test avec son nom complet et son statut, que
# core/test.js numerote et dont 2 est l'echec ; les messages d'assertion se
# trouvent sur les evenements qui n'ont pas passe.
RESULTATS = """
const runner = window.odoo.loader.modules
    .get("@web/../lib/hoot/main_runner").getRunner();
const bilan = runner.reporting;
// Une assertion porte son message en morceaux, dont certains sont des
// etiquettes ou des noeuds du DOM plutot que du texte : chacun est reduit a
// une chaine courte, faute de quoi le passage par le pilote echoue a
// serialiser l'objet.
const bref = (v) => {
    try {
        if (v === null || v === undefined) { return String(v); }
        if (typeof v === "string") { return v; }
        if (typeof v !== "object") { return String(v); }
        if (v.nodeName) { return "<" + v.nodeName.toLowerCase() + ">"; }
        if (v.text) { return String(v.text); }
        return JSON.stringify(v);
    } catch (err) { return "[illisible]"; }
};
const texte = (m) => (m || []).map(bref).join(" ").trim();
// failedDetails tient les valeurs comparees, seules capables de dire en quoi
// l'attendu et l'obtenu different.
const paires = (d) => (d || []).map(
    (p) => (Array.isArray(p) ? p : [p]).map(bref).join(" : ")
).join("  |  ");
const echecs = [];
for (const test of runner.tests.values()) {
    if (test.status !== 2) { continue; }
    const details = [];
    for (const res of (test.results || [])) {
        for (const ev of (res.events || [])) {
            if (ev.pass === false) {
                details.push({
                    message: texte(ev.message),
                    valeurs: paires(ev.failedDetails).slice(0, 500),
                });
            }
        }
    }
    echecs.push({nom: test.fullName, details: details.slice(0, 4)});
}
return {statut: runner.state.status, passes: bilan.passed,
        echoues: bilan.failed, ignores: bilan.skipped,
        assertions: bilan.assertions, tests: bilan.tests, echecs: echecs};
"""


def attendre_lanceur(selenium_tool, limite):
    """Rend l'etat du lanceur des qu'il existe, ou None passe la limite."""
    fin = time.time() + limite
    dernier = None
    while time.time() < fin:
        dernier = selenium_tool.driver.execute_script(SONDE_LANCEUR)
        if dernier.get("etape") == "pret":
            return dernier
        time.sleep(0.5)
    print(f"  ECHEC : lanceur hoot introuvable ({dernier}).")
    return None


def attendre_fin(selenium_tool, limite):
    """Rend le compte rendu une fois la suite terminee, ou None si l'attente expire."""
    fin = time.time() + limite
    while time.time() < fin:
        resultats = selenium_tool.driver.execute_script(RESULTATS)
        if resultats.get("statut") == ETAT_FINI:
            return resultats
        time.sleep(1)
    return None


def run(config, selenium_tool):
    url = (
        f"{config.url}/web/tests?filter={config.filter}"
        f"&manual=true&debug=assets&timeout={config.timeout_test}"
    )
    print(f"Ouverture de la suite : {url}")
    selenium_tool.driver.get(url)

    etat = attendre_lanceur(selenium_tool, config.attente_chargement)
    if not etat:
        return 2
    if not etat.get("manuel"):
        # Sans manual=true la suite part au chargement : elle peut etre finie
        # avant meme qu'on la regarde, et le demarrage ci-dessous ne ferait
        # rien. On le dit plutot que de rendre un vert non merite.
        print("  ATTENTION : le lanceur n'est pas en mode manuel.")
    print(f"  lanceur pret (statut « {etat.get('statut')} »), demarrage.")
    selenium_tool.driver.execute_script(DEMARRAGE)

    resultats = attendre_fin(selenium_tool, config.attente_suite)
    if resultats is None:
        print(f"  ECHEC : la suite n'a pas fini en {config.attente_suite} s.")
        return 2

    total = resultats["tests"]
    print(
        f"\n  {total} test(s) : {resultats['passes']} passent,"
        f" {resultats['echoues']} echouent, {resultats['ignores']} ignores"
        f" ({resultats['assertions']} assertions)."
    )

    if not total:
        # Zero test n'est PAS « zero echec » : c'est une suite qui n'a rien
        # trouve. Sans ce garde, un filtre qui ne designe rien rend un vert.
        # Un fichier de test NOUVEAU est dans ce cas jusqu'au redemarrage de
        # l'instance, la liste des actifs etant gelee.
        print("  ECHEC : aucun test ne correspond au filtre.")
        return 2

    if resultats["echecs"]:
        print(f"\n  {len(resultats['echecs'])} test(s) rouge(s) :")
        for echec in resultats["echecs"]:
            print(f"    - {echec['nom']}")
            for detail in echec["details"]:
                if detail:
                    print(f"        {detail}")

    if config.json_sortie:
        with open(config.json_sortie, "w") as fichier:
            json.dump(resultats, fichier, indent=2, ensure_ascii=False)
        print(f"\n  compte rendu -> {config.json_sortie}")

    return 1 if resultats["echoues"] else 0


def fill_parser(parser):
    groupe = parser.add_argument_group(title="Suite hoot")
    groupe.add_argument(
        "--filter",
        default="@erplibre_event_table",
        help="Filtre hoot ; « @ » designe une suite.",
    )
    groupe.add_argument(
        "--timeout_test",
        type=int,
        default=15000,
        help="Delai hoot par test, en millisecondes.",
    )
    groupe.add_argument(
        "--attente_chargement",
        type=float,
        default=120.0,
        help=(
            "Secondes accordees au chargement de la page. Le mode debug sert"
            " des sources non minifiees, bien plus lourdes."
        ),
    )
    groupe.add_argument(
        "--attente_suite",
        type=float,
        default=300.0,
        help="Secondes accordees a l'execution de la suite.",
    )
    groupe.add_argument(
        "--json_sortie",
        default="",
        help="Chemin ou ecrire le compte rendu complet.",
    )
    # --debug, --scenario et --scenario_screenshot appartiennent au cadre et
    # sont declares par selenium_lib.fill_parser : les redeclarer ici leverait
    # une ArgumentError pour chaine d'option en conflit.


def compute_args(args):
    return args


def main():
    parser = argparse.ArgumentParser(
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description=__doc__,
    )
    selenium_lib.fill_parser(parser)
    web_login.fill_parser(parser)
    fill_parser(parser)
    args = parser.parse_args()
    web_login.compute_args(args)
    compute_args(args)

    selenium_tool = selenium_lib.SeleniumLib(args)
    selenium_tool.configure()

    # web_login.run termine par odoo_profile_click, qui bascule DEUX entrees
    # du menu profil sans condition : le mode tour, puis le theme sombre. La
    # seconde, « color_scheme.switch », n'existe pas dans tous les montages
    # Odoo 18 et sa recherche expire, ce qui fait echouer une connexion par
    # ailleurs reussie. On desarme l'etape plutot que d'avaler l'exception :
    # un except autour de web_login.run masquerait aussi un vrai echec
    # d'authentification.
    selenium_tool.odoo_profile_click = lambda **_: None

    web_login.run(args, selenium_tool)
    code = run(args, selenium_tool)
    selenium_tool.driver.quit()
    return code


if __name__ == "__main__":
    sys.exit(main())
