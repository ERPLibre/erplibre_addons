#!/usr/bin/env python3
# Copyright 2026 TechnoLibre - Mathieu Benoit
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
"""Capture le plan de salle d'un plan de tables tournantes, pour l'oeil.

Ce scenario existe pour une raison precise : tout le reste de ce module se
verifie par calcul ou par compilation, et rien n'y regarde un RENDU. Le
lanceur node ne couvre que la geometrie pure ; le controle de gabarits
prouve qu'un t-if compile, jamais qu'un nom en cache un autre ; la suite
hoot compte des elements du DOM, jamais la place que le texte y prend une
fois la fonte rendue. Or la hauteur d'une puce de liste est exactement ce
que LIST_LINE_HEIGHT (geometry.js) reserve par ligne, et elle n'existe
qu'au navigateur : seules une image et la mesure qui l'accompagne
tranchent.

Il s'appuie sur le cadre du depot (script/selenium) plutot que de piloter
Selenium lui-meme, pour que la connexion, le mode sans fenetre et le choix du
pilote restent ceux d'ERPLibre.

Les captures atterrissent dans selenium/screenshots/, deja ignore par le
.gitignore du module depuis son premier commit.
"""

import argparse
import os
import sys
import time

from selenium.webdriver.common.by import By

RACINE = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "..")
)
sys.path.append(RACINE)

from script.selenium import selenium_lib, web_login  # noqa: E402

# Les captures vont dans le repertoire du scenario plutot que par
# do_screenshot du cadre, qui les nomme d'apres config.scenario et les range
# relativement au repertoire courant : un chemin absolu ancre sur ce fichier
# donne le meme resultat d'ou qu'on lance le scenario.
DOSSIER = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "screenshots"
)


def capture(selenium_tool, nom):
    """Ecrit une capture et rend son chemin, pour qu'un humain l'ouvre."""
    os.makedirs(DOSSIER, exist_ok=True)
    chemin = os.path.join(DOSSIER, f"{nom}.png")
    selenium_tool.driver.save_screenshot(chemin)
    largeur, hauteur = selenium_tool.driver.execute_script(
        "return [window.innerWidth, window.innerHeight];"
    ) or [0, 0]
    print(f"  capture -> {chemin}  ({largeur}x{hauteur})")
    return chemin


def mesurer_puces(selenium_tool):
    """Rend la boite REELLE de chaque puce de liste, lue du DOM.

    C'est la mesure que le calcul ne peut pas faire : la hauteur d'une
    puce depend de la fonte rendue, que seul le navigateur connait, et
    c'est elle que LIST_LINE_HEIGHT (geometry.js) reserve par ligne.
    Chaque puce porte la table dont elle liste quelqu'un, pour que le
    recoupement avec une table VOISINE se distingue d'un recouvrement
    par sa propre table.
    """
    return selenium_tool.driver.execute_script(
        """
        const out = [];
        for (const el of document.querySelectorAll('.o_event_table_names .o_event_table_person')) {
            const liste = el.closest('.o_event_table_names');
            const r = el.getBoundingClientRect();
            out.push({
                texte: el.textContent.trim(),
                table: liste ? liste.dataset.tableId : null,
                x: r.x, y: r.y, largeur: r.width, hauteur: r.height,
            });
        }
        return out;
        """
    )


def mesurer_obstacles(selenium_tool):
    """Rend la boite de chaque surface et de chaque chaise, par table.

    Une puce qui recouvre la table a laquelle elle appartient n'existe
    pas : la liste est posee a cote. Une puce qui recouvre une table
    VOISINE est le defaut que l'espacement de la grille doit empecher,
    et c'est la seule facon de le constater sur un rendu.
    """
    return selenium_tool.driver.execute_script(
        """
        const out = [];
        const sel = '.o_event_table_surface, .o_event_table_seat';
        for (const el of document.querySelectorAll(sel)) {
            const bloc = el.closest('.o_event_table_block');
            const r = el.getBoundingClientRect();
            out.push({
                genre: el.classList.contains('o_event_table_seat') ? 'chaise' : 'surface',
                table: bloc ? bloc.dataset.tableId : null,
                x: r.x, y: r.y, largeur: r.width, hauteur: r.height,
            });
        }
        return out;
        """
    )


def _recoupe(a, b):
    """Ampleur du recoupement de deux boites, ou None si elles sont
    disjointes. Un contact exact (dx ou dy nul) n'est pas un
    recouvrement."""
    dx = min(a["x"] + a["largeur"], b["x"] + b["largeur"]) - max(
        a["x"], b["x"]
    )
    dy = min(a["y"] + a["hauteur"], b["y"] + b["hauteur"]) - max(
        a["y"], b["y"]
    )
    return (round(dx), round(dy)) if dx > 0 and dy > 0 else None


def chevauchements(boites):
    """Paires de puces dont les boites se recoupent, avec l'ampleur."""
    trouves = []
    for i in range(len(boites)):
        for j in range(i + 1, len(boites)):
            ampleur = _recoupe(boites[i], boites[j])
            if ampleur:
                trouves.append(
                    (boites[i]["texte"], boites[j]["texte"], *ampleur)
                )
    return trouves


def empietements(puces, obstacles):
    """Puces posees sur la surface ou les chaises d'une AUTRE table."""
    trouves = []
    for puce in puces:
        for obstacle in obstacles:
            if obstacle["table"] == puce["table"]:
                continue
            ampleur = _recoupe(puce, obstacle)
            if ampleur:
                trouves.append(
                    (
                        puce["texte"],
                        f"{obstacle['genre']} de la table"
                        f" {obstacle['table']}",
                        *ampleur,
                    )
                )
    return trouves


def run(config, selenium_tool):
    # L'identifiant EXTERNE de l'action, jamais son numero : ir_act_window.id
    # est attribue a l'installation et differe d'une base a l'autre. Un numero
    # emprunte a une autre base designe une action inexistante, qu'Odoo affiche
    # sans lever d'erreur ni changer le code de sortie : la capture reussit et
    # ne montre rien.
    # « debug=assets » est OBLIGATOIRE : sans lui l'instance sert le paquet
    # d'actifs deja en cache, et la page rend le code d'AVANT la
    # modification qu'on vient capturer. Le symptome est muet — la capture
    # reussit, les mesures sont coherentes, elles decrivent l'ancien rendu.
    # Le seul indice est un selecteur qui ne trouve rien alors que la page
    # s'affiche normalement. La liste des FICHIERS d'actifs reste gelee
    # jusqu'a un redemarrage, ce parametre ne rouvre que leur contenu.
    url = (
        f"{config.url}/odoo/action-{config.action_ref}"
        f"/{config.plan_id}?debug=assets"
    )
    print(f"Ouverture du plan : {url}")
    selenium_tool.driver.get(url)
    time.sleep(config.attente)

    # L'onglet « Floor Plan » du formulaire de plan.
    try:
        onglet = selenium_tool.driver.find_element(
            By.XPATH,
            "//a[@name='floor_plan'] | //a[contains(text(),'Floor Plan')]",
        )
        onglet.click()
        time.sleep(config.attente)
    except Exception as erreur:  # noqa: BLE001
        print(
            f"  (onglet Floor Plan non clique : {erreur.__class__.__name__})"
        )

    # Mesure CE QUE L'OUVERTURE DONNE, sans rien cliquer. Cliquer « Fit to
    # window » d'abord reparait le cadrage avant de le mesurer : un plan qui
    # s'ouvre trop grand rendait alors exactement le meme releve qu'un plan
    # qui s'ajuste seul, et l'outil ne pouvait structurellement pas montrer
    # la difference entre les deux. --ajuster_avant le demande quand on veut
    # mesurer l'autre etat, celui d'apres le clic.
    if config.ajuster_avant:
        for libelle in ("Fit to window", "Ajuster"):
            try:
                selenium_tool.driver.find_element(
                    By.XPATH, f"//button[contains(text(), '{libelle}')]"
                ).click()
                time.sleep(1.5)
                print(f"  bouton « {libelle} » clique.")
                break
            except Exception:  # noqa: BLE001
                continue

    # L'echelle appliquee a la salle, lue sur l'element qui la porte : c'est
    # elle qui dit si le plan s'est ajuste seul, et aucune boite mesuree plus
    # bas ne la revele, toutes etant deja exprimees en pixels ecran.
    echelle = selenium_tool.driver.execute_script(
        """
        const salle = document.querySelector('.o_event_table_room');
        return salle ? getComputedStyle(salle).transform : null;
        """
    )
    print(f"  echelle de la salle a l'ouverture : {echelle}")

    # Le debordement se mesure en comparant la boite de CHAQUE puce au
    # rectangle du cadre, jamais par scrollWidth/clientWidth du conteneur :
    # les listes sont en position absolue et n'entrent pas dans le calcul de
    # defilement de leur parent. Sur un plan dont deux puces sortaient
    # visiblement par la gauche, scrollWidth annoncait « rien a signaler ».
    debords = selenium_tool.driver.execute_script(
        """
        const cadre = document.querySelector('.o_event_table_floor');
        if (!cadre) { return null; }
        const c = cadre.getBoundingClientRect();
        const out = [];
        const sel = '.o_event_table_names .o_event_table_person';
        for (const el of document.querySelectorAll(sel)) {
            const r = el.getBoundingClientRect();
            const sorties = {
                gauche: Math.round(c.left - r.left),
                droite: Math.round(r.right - c.right),
                haut: Math.round(c.top - r.top),
                bas: Math.round(r.bottom - c.bottom),
            };
            const dehors = Object.entries(sorties)
                .filter(([, v]) => v > 0)
                .map(([k, v]) => `${k} ${v}px`);
            if (dehors.length) {
                out.push({texte: el.textContent.trim(), dehors});
            }
        }
        return {cadre: [Math.round(c.left), Math.round(c.top),
                        Math.round(c.width), Math.round(c.height)],
                debords: out};
        """
    )
    if debords:
        print(
            f"\n  cadre du plan : {debords['cadre']} (x, y, largeur, hauteur)"
        )
        print(f"  {len(debords['debords'])} puce(s) sortent du cadre :")
        for item in debords["debords"]:
            print(f"    \"{item['texte']}\" : {', '.join(item['dehors'])}")

    capture(selenium_tool, "plan_de_salle")

    boites = mesurer_puces(selenium_tool)
    if not boites:
        # Zero puce n'est PAS « aucun chevauchement » : c'est une mesure qui
        # n'a rien mesure. Sans ce garde, le rapport annonce « 0 paire qui se
        # chevauche » face a une page d'erreur, a un onglet reste ferme ou a
        # un plan sans combinaison retenue — et se lit comme un succes.
        titre = selenium_tool.driver.title
        corps = selenium_tool.driver.execute_script(
            "return (document.body.innerText || '').slice(0, 400);"
        )
        print("\n  ECHEC : aucune puce de liste trouvee dans le DOM.")
        print(f"    titre de la page : {titre}")
        print(f"    debut du corps   : {corps!r}")
        return 2
    print(f"\n  {len(boites)} puce(s) de liste lues dans le DOM :")
    for b in boites:
        print(
            f"    \"{b['texte']}\" : {b['largeur']:.0f} x {b['hauteur']:.0f} px"
            f"  a ({b['x']:.0f}, {b['y']:.0f})  table {b['table']}"
        )

    recoupes = chevauchements(boites)
    print(
        f"\n  {len(recoupes)} paire(s) de puces qui se chevauchent REELLEMENT :"
    )
    for texte_a, texte_b, dx, dy in recoupes:
        print(
            f'    "{texte_a}" / "{texte_b}" : {dx} px horizontalement, {dy} px verticalement'
        )

    # Une puce posee sur une table VOISINE est le defaut que l'espacement de
    # la grille (step_x, step_y) doit empecher. Le calcul le promet ; seul le
    # rendu le constate.
    poses = empietements(boites, mesurer_obstacles(selenium_tool))
    print(f"\n  {len(poses)} puce(s) posee(s) sur une table voisine :")
    for texte, quoi, dx, dy in poses:
        print(
            f'    "{texte}" sur {quoi} : {dx} px horizontalement, {dy} px verticalement'
        )

    if config.zoom_table:
        # Cadrage serre sur la premiere table, pour lire les noms a l'oeil.
        selenium_tool.driver.execute_script(
            """
            const bloc = document.querySelector('.o_event_table_block');
            if (bloc) { bloc.scrollIntoView({block: 'center', inline: 'center'}); }
            """
        )
        time.sleep(1)
        capture(selenium_tool, "table_rapprochee")

    return 0


def fill_parser(parser):
    groupe = parser.add_argument_group(title="Plan de salle")
    groupe.add_argument(
        "--plan_id", default="3", help="Identifiant du plan a ouvrir."
    )
    groupe.add_argument(
        "--action_ref",
        default="erplibre_event_table.action_event_table_plan",
        help=(
            "Identifiant EXTERNE de l'action Odoo. Il est stable d'une base a"
            " l'autre, contrairement au numero de ir_act_window."
        ),
    )
    groupe.add_argument(
        "--attente",
        type=float,
        default=4.0,
        help="Secondes d'attente apres chaque navigation.",
    )
    groupe.add_argument(
        "--zoom_table",
        action="store_true",
        help="Prendre une seconde capture cadree sur une table.",
    )
    groupe.add_argument(
        "--ajuster_avant",
        action="store_true",
        help=(
            "Cliquer « Fit to window » AVANT de mesurer. Par defaut le"
            " scenario mesure ce que l'ouverture donne : cliquer d'abord"
            " reparerait le cadrage avant de le constater."
        ),
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
    # d'authentification. Le theme clair qui en resulte sert la lecture des
    # etiquettes.
    selenium_tool.odoo_profile_click = lambda **_: None

    web_login.run(args, selenium_tool)
    code = run(args, selenium_tool)
    selenium_tool.driver.quit()
    return code


if __name__ == "__main__":
    sys.exit(main())
