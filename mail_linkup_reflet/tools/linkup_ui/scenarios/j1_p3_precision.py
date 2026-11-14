# Copyright 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
"""Guide §5 P3: Jacques answers the reflection he confirmed in P2 with
"Je voudrais préciser…" and hides the theme Buts; Sam guesses it. Sam
then guesses the hidden theme of the precision of France that waits in
the demonstration, and sends Jacques a second reflection, which Jacques
confirms and answers "Oui, c'est exactement ça !".

Sam turns the reward sounds on from the LinkUp help page before his
first guess, and off again once the second one is checked: a theme found
rings "Ting" for him, a theme missed rings nothing.

Builds on ``run.memory["p1_reflet_id"]``, confirmed by Jacques in P2.
Leaves ``run.memory["p3_precision_id"]``, ``["p3_second_id"]`` (the
second reflection) and ``["p3_exact_id"]`` (its exact answer, whose turn
Sam holds with the three options).
"""

import re

from driver import SETTLE, StepFailure
from selenium.common.exceptions import StaleElementReferenceException
from selenium.webdriver.common.keys import Keys

from .j1_p1_send import (
    MENU_ITEM,
    MENU_SECTION,
    open_reflet_view,
    pick_in_list,
    quote,
    user,
)
from .j1_p2_validate import RECEIVED, open_chat_with, reflet_row

SECTION = "P3"
TITLE = "Réponse, thème caché, devinette (guide §5 P3)"

# The count of the full band of categories that the guide gives: the
# twelve categories.
GUIDE_BAND_SIZE = 12
# The most hidden themes a precision holds.
MAX_THEMES = 2
REWARD_SWITCH = "input[name='linkup_reward_sounds_enabled']"
REWARD_LABEL = "Sons de récompense : reflet confirmé, points, thème trouvé"
# What Jacques writes in the precision hiding Buts; its cards are found by
# this text.
PRECISION_TEXT = "Je veux garder du temps pour ce qui compte pour moi."
SECOND_CATEGORY = "needs"
SECOND_YOU_SAID = "que tu prépares une fête pour tout le quartier"
SECOND_UNDERSTOOD = "tu as besoin de rassembler les gens"
ALREADY_ANSWERED = "Ce reflet a déjà reçu une réponse."

CARD = ".o-mail-Message .o-linkup-RefletCard"
PRECISION = f"{CARD}[data-kind='precision']"
PRECISION_FORM = ".o-linkup-RefletActions-form[data-form='precision']"
OPTION = ".o-linkup-CategoryPicker-option"


# State in the database ---------------------------------------------


def ledger_lines(run, reflet_id):
    """``[(login, rule code, points, cap_reason)]`` of every ledger line of
    a reflection, sorted; ``cap_reason`` is "" for a paid line. Two lines
    of the same login and rule stay two entries."""
    rows = run.sql(
        "SELECT u.login, r.code, l.points, coalesce(l.cap_reason, '')"
        " FROM linkup_points_ledger l"
        " JOIN res_users u ON u.id = l.user_id"
        " JOIN linkup_points_rule r ON r.id = l.rule_id"
        f" WHERE l.reflet_id = {int(reflet_id)}"
    )
    return sorted(
        (login, code, int(points), reason)
        for login, code, points, reason in rows
    )


def karma_of(run, *logins):
    return {login: run.points(login) for login in logins}


def check_delta(run, before, expected):
    """Check that the karma moved from ``before`` by ``expected``, by
    login; return the karma after."""
    after = karma_of(run, *before)
    delta = {login: after[login] - before[login] for login in before}
    run.check(
        delta == expected,
        f"points : {before} → {after} (écart {delta}, attendu {expected})",
    )
    return after


def category_id(run, code):
    return int(
        run.sql(f"SELECT id FROM linkup_category WHERE code = {quote(code)}")[
            0
        ][0]
    )


def starter_self(run, code):
    """The French first-person starter of a category ("Mon but est :")."""
    return run.sql(
        "SELECT starter_self->>'fr_CA' FROM linkup_category"
        f" WHERE code = {quote(code)}"
    )[0][0]


def category_name(run, code):
    return run.sql(
        f"SELECT name->>'fr_CA' FROM linkup_category WHERE code = {quote(code)}"
    )[0][0]


def hidden_codes(run, reflet_id):
    """Codes of the hidden themes of a precision, main theme first."""
    rows = run.sql(
        "SELECT c.code FROM linkup_reflet_secret s"
        " JOIN linkup_category_linkup_reflet_secret_rel rel"
        " ON rel.linkup_reflet_secret_id = s.id"
        " JOIN linkup_category c ON c.id = rel.linkup_category_id"
        f" WHERE s.reflet_id = {int(reflet_id)}"
        " ORDER BY c.id = s.primary_category_id DESC, c.sequence"
    )
    return [row[0] for row in rows]


def precision_row(run, reflet_id):
    """``(author, recipient, guess_state, guessed code, body_text)``."""
    return run.sql(
        "SELECT a.login, b.login, r.guess_state, coalesce(g.code, ''),"
        " coalesce(r.body_text, '')"
        " FROM linkup_reflet r"
        " JOIN res_users a ON a.id = r.author_id"
        " JOIN res_users b ON b.id = r.recipient_id"
        " LEFT JOIN linkup_category g ON g.id = r.guessed_category_id"
        f" WHERE r.id = {int(reflet_id)}"
    )[0]


def reward_sounds(run, login):
    """The reward sound setting of ``login``; off without settings."""
    rows = run.sql(
        "SELECT s.linkup_reward_sounds_enabled FROM res_users_settings s"
        f" JOIN res_users u ON u.id = s.user_id WHERE u.login = {quote(login)}"
    )
    return "activés" if rows and rows[0][0] == "t" else "désactivés"


def set_reward_sounds(run, persona, on):
    """Turn the reward sounds of ``persona`` on or off with a click on
    their switch in the LinkUp help page (Discussion › LinkUp › Aide), then
    wait until the server holds the new value. Leaves the help page
    open."""
    persona.click(MENU_SECTION, "LinkUp")
    persona.click(MENU_ITEM, "Aide")
    label = persona.text(
        "label[for='o-linkup-Help-linkup_reward_sounds_enabled']"
    )
    label = re.sub(r"\s+", " ", label).strip()
    run.check(
        label == REWARD_LABEL,
        f"libellé du réglage : {label!r}, attendu « {REWARD_LABEL} »",
    )
    if persona.find(REWARD_SWITCH).is_selected() != on:
        persona.click(REWARD_SWITCH)
    wanted = "activés" if on else "désactivés"
    persona.wait_until(
        lambda _d: persona.find(REWARD_SWITCH).is_selected() == on
        and persona.find(REWARD_SWITCH).is_enabled()
        and reward_sounds(run, persona.login_name) == wanted,
        f"sons de récompense {wanted} en base",
    )


def played(persona, name):
    """Whether the page played the sound ``name`` since ``record_sounds``."""
    return any(name in source for source in persona.played_sounds())


def turn_of(run, reflet_id):
    """Id of the reflection that holds the turn of the pair of a
    reflection, or ""."""
    return run.sql(
        "SELECT coalesce(l.turn_reflet_id::text, '') FROM linkup_reflet r"
        f" JOIN linkup_link l ON l.id = r.link_id WHERE r.id = {int(reflet_id)}"
    )[0][0]


# Screen ------------------------------------------------------------

# Reads a card in one script, so that a card the thread renders again
# between two reads never leaves a stale element behind: the visible card
# matching ``css`` whose ``part`` holds ``text``, or null.
CARD_JS = """
const [css, part, text, inner] = arguments;
for (const card of document.querySelectorAll(css)) {
    if (!card.offsetParent) { continue; }
    if (![...card.querySelectorAll(part)].some((e) => e.textContent.includes(text))) { continue; }
    if (inner) { return card.querySelector(inner); }
    const all = (sel) => [...card.querySelectorAll(sel)];
    const clean = (e) => e ? e.textContent.replace(/\\s+/g, " ").trim() : "";
    const area = card.querySelector(".o-linkup-RefletActions-text");
    return {
        state: card.dataset.state,
        guess: card.dataset.guessState || "",
        header: all(".o-linkup-RefletCard-header svg[data-code]").map((e) => e.dataset.code),
        footer: clean(card.querySelector(".o-linkup-RefletCard-footer")),
        modes: all(".o-linkup-RefletActions[data-mode]").map((e) => e.dataset.mode),
        actions: clean(card.querySelector(".o-linkup-RefletActions")),
        forms: all(".o-linkup-RefletActions-form").map((e) => e.dataset.form),
        options: all(".o-linkup-CategoryPicker-option").map((e) => e.dataset.code),
        pressed: all(".o-linkup-CategoryPicker-option[aria-pressed='true']").map((e) => e.dataset.code),
        unavailable: all(".o-linkup-CategoryPicker-option.o-isUnavailable").map((e) => e.dataset.code),
        text: area ? area.value : null,
    };
}
return null;
"""


class Card:
    """A card of a conversation, found again by its text at each use."""

    def __init__(self, persona, css, part, text):
        self.persona = persona
        self.css = css
        self.part = part
        self.text = text

    def read(self):
        return self.persona.js(CARD_JS, self.css, self.part, self.text, None)

    def wait(self, condition=lambda state: True, what="carte"):
        """Wait until the card shows and ``condition(state)`` holds;
        return the state."""
        last = {}

        def holds(_driver):
            state = self.read()
            last["state"] = state
            return state if state and condition(state) else False

        try:
            return self.persona.wait_until(holds, what)
        except StepFailure:
            raise StepFailure(
                f"[{self.persona.login_name}] {what} ; carte {self.css} « {self.text} » : {last.get('state')}"
            ) from None

    def click(self, inner, text=None):
        """Click the descendant ``inner`` of the card (holding ``text``)."""

        def clicked(_driver):
            element = self.persona.js(
                CARD_JS, self.css, self.part, self.text, inner
            )
            try:
                label = element.text if element else ""
                if not element or (text and text not in label):
                    return False
                self.persona.js(
                    "arguments[0].scrollIntoView({block: 'center'});", element
                )
                element.click()
            except StaleElementReferenceException:
                return False
            return label or True

        return self.persona.wait_until(
            clicked, f"{inner} dans la carte « {self.text} »"
        )


def precision_card(persona, role, body, guess_state=None):
    css = f"{PRECISION}[data-role='{role}']"
    if guess_state:
        css += f"[data-guess-state='{guess_state}']"
    return Card(persona, css, ".o-linkup-RefletCard-bodyText", body)


def received_card(persona, state, understood):
    return Card(
        persona,
        f"{RECEIVED}[data-state='{state}']",
        ".o-linkup-RefletCard-understood",
        understood,
    )


def show_thread(persona, login, name):
    """Open the direct conversation with ``login`` from the Reflet view,
    unless it is already the open thread."""
    if persona.has(f".o-mail-Discuss-threadName[title='{name}']"):
        return
    open_reflet_view(persona)
    open_chat_with(persona, user(persona.run, login)[0], name)


def expect_bursts(run, persona, wanted, what):
    """Wait until every ``(kind, points, text)`` of ``wanted`` was shown."""

    def holds(record):
        return all(
            any(
                b["kind"] == kind
                and b["points"] == points
                and text in b["text"]
                for b in record["bursts"]
            )
            for kind, points, text in wanted
        )

    try:
        return persona.wait_points(holds, what)
    except StepFailure:
        raise StepFailure(
            f"{what} ; vu : {persona.recorded_points()}"
        ) from None


def no_store_leak(persona):
    """Whether the Store of the web client holds no hidden theme of a
    precision; None when the debug handle of the client is missing."""
    return persona.js(
        """
        const root = window.odoo && odoo.__WOWL_DEBUG__ && odoo.__WOWL_DEBUG__.root;
        if (!root) { return null; }
        const store = root.env.services["mail.store"];
        return Object.values(store["linkup.reflet"].records)
            .filter((r) => r.kind === "precision" && r.guess_state === "pending")
            .every((r) => !(r.revealed_category_ids || []).length
                && !r.primary_category_id && !r.guessed_category_id);
        """
    )


# Steps -------------------------------------------------------------


def confirmed_card(run, jacques):
    """The card, at Jacques, of the reflection he confirmed in P2."""
    _state, _unread, understood = reflet_row(run, run.memory["p1_reflet_id"])
    return received_card(jacques, "confirmed", understood)


def p3_1(run):
    _sid, _pid, sam_name = user(run, "sam")
    jacques = run.persona("jacques")
    show_thread(jacques, "sam", sam_name)
    card = confirmed_card(run, jacques)
    state = card.wait(
        lambda s: "answer" in s["modes"],
        "réponse offerte sous la carte confirmée",
    )
    run.check(
        f"{sam_name} t'a bien compris" in state["actions"],
        f"question de la réponse : {state['actions']!r}",
    )
    label = card.click(
        ".o-linkup-RefletActions-precise", "Je voudrais préciser…"
    )
    state = card.wait(
        lambda s: "precision" in s["forms"],
        "formulaire de la précision ouvert",
    )
    run.check(
        f"Thème caché, facultatif : {sam_name} devra le deviner"
        in state["actions"],
        f"consigne du thème caché absente : {state['actions']!r}",
    )
    codes = state["options"]
    active = [
        r[0]
        for r in run.sql(
            "SELECT code FROM linkup_category WHERE active ORDER BY sequence, id"
        )
    ]
    run.check(
        codes == active, f"bande : {codes}, catégories actives : {active}"
    )
    run.check(
        len(codes) == GUIDE_BAND_SIZE,
        f"bande de {len(codes)} icônes ({', '.join(codes)}), le guide en annonce {GUIDE_BAND_SIZE}",
    )
    run.check(
        state["text"] == "",
        f"texte de la précision prérempli à l'ouverture : {state['text']!r}",
    )

    # A hidden theme never touches the text of the precision: its starter
    # would give the theme away before the guess (LU-F-032 RM2). Two
    # themes at most: once two are chosen, every other one is unavailable,
    # and a click on one of them chooses nothing.
    chosen = ["emotions", "goals"]
    card.click(f"{PRECISION_FORM} {OPTION}[data-code='{chosen[0]}']")
    run.settle()
    state = card.wait(
        lambda s: s["pressed"] == [chosen[0]],
        "Émotions choisi",
    )
    run.check(
        state["text"] == "",
        f"le thème principal a rempli le texte : {state['text']!r}"
        f" (amorce « {starter_self(run, chosen[0])} »)",
    )
    card.click(f"{PRECISION_FORM} {OPTION}[data-code='{chosen[1]}']")
    state = card.wait(
        lambda s: sorted(s["pressed"]) == chosen,
        "Buts et Émotions choisis ensemble",
    )
    others = sorted(set(codes) - set(chosen))
    unavailable = sorted(state["unavailable"])
    run.check(
        unavailable == others,
        f"indisponibles : {unavailable}, attendu toutes les autres {others}",
    )
    run.check(
        state["text"] == "",
        f"le second thème a rempli le texte : {state['text']!r}",
    )
    third = others[0]
    card.click(f"{PRECISION_FORM} {OPTION}[data-code='{third}']")
    run.settle()
    state = card.read()
    run.check(
        sorted(state["pressed"]) == chosen,
        f"un troisième thème ({third}) a été pris : thèmes pressés {state['pressed']}",
    )
    run.check(
        state["text"] == "",
        f"le troisième thème refusé a rempli le texte : {state['text']!r}",
    )
    for code in chosen:
        card.click(f"{PRECISION_FORM} {OPTION}[data-code='{code}']")
    state = card.wait(
        lambda s: s["pressed"] == [] and s["unavailable"] == [],
        "thèmes retirés, tous disponibles",
    )
    run.check(
        state["text"] == "",
        f"texte de la précision après le retrait des thèmes : {state['text']!r}",
    )
    return (
        f"« {label.strip().splitlines()[0]} » : bande de {len(codes)} icônes ; Émotions puis Buts choisis, texte resté vide,"
        f" les {len(unavailable)} autres indisponibles, un clic sur {third} refusé ;"
        " thèmes retirés : texte vide"
    )


def p3_2(run):
    reflet_id = run.memory["p1_reflet_id"]
    _sid, _pid, sam_name = user(run, "sam")
    _jid, _jpid, jacques_name = user(run, "jacques")
    jacques = run.persona("jacques")
    sam = run.persona("sam")
    before = karma_of(run, "sam", "jacques")
    sam.record_points()
    jacques.record_points()

    card = confirmed_card(run, jacques)
    starter = starter_self(run, "goals")
    card.click(f"{PRECISION_FORM} {OPTION}[data-code='goals']")
    run.settle()
    state = card.wait(lambda s: s["pressed"] == ["goals"], "Buts choisi")
    run.check(
        state["text"] == "",
        f"Buts a rempli le texte de la précision : {state['text']!r}",
    )
    jacques.type(
        f"{PRECISION_FORM} .o-linkup-RefletActions-text", PRECISION_TEXT
    )
    full_text = PRECISION_TEXT
    card.wait(
        lambda s: s["text"] == full_text,
        f"texte de la précision « {full_text} »",
    )
    card.click(
        f"{PRECISION_FORM} .o-linkup-RefletActions-send",
        f"Envoyer à {sam_name}",
    )
    goals = category_name(run, "goals")
    precision_card(jacques, "author", PRECISION_TEXT, "pending").wait(
        lambda s: s["footer"] == f"Thème caché : {goals}",
        f"précision envoyée, « Thème caché : {goals} »",
    )

    rows = run.sql(
        f"SELECT id FROM linkup_reflet WHERE parent_id = {int(reflet_id)} AND kind = 'precision'"
    )
    run.check(len(rows) == 1, f"précisions du reflet {reflet_id} : {rows}")
    precision_id = int(rows[0][0])
    run.memory["p3_precision_id"] = precision_id
    row = precision_row(run, precision_id)
    run.check(
        row == ["jacques", "sam", "pending", "", full_text],
        f"précision {precision_id} : {row}",
    )
    run.check(
        starter.rstrip(" :") not in row[-1],
        f"le texte de la précision dévoile Buts par son amorce « {starter} » : {row[-1]!r}",
    )
    themes = hidden_codes(run, precision_id)
    run.check(themes == ["goals"], f"thèmes cachés : {themes}")
    lines = ledger_lines(run, precision_id)
    expected = [
        ("jacques", "precision_sent", 1000, ""),
        ("sam", "precision_sent", 1000, ""),
    ]
    run.check(
        lines == expected,
        f"registre de la précision : {lines}, attendu {expected}",
    )
    after = check_delta(run, before, {"sam": 1000, "jacques": 1000})
    for persona in (jacques, sam):
        expect_bursts(
            run,
            persona,
            [("gain", 1000, "Précision envoyée")],
            f"+1000 affiché chez {persona.login_name}",
        )

    turn = turn_of(run, precision_id)
    run.check(
        turn == str(precision_id),
        f"tour de la paire au reflet {turn!r}, attendu la précision {precision_id}",
    )
    show_thread(sam, "jacques", jacques_name)
    precision_card(sam, "recipient", PRECISION_TEXT, "pending").wait(
        lambda s: s["modes"] == ["guess"],
        "chez Sam, la précision offre la devinette",
    )
    return f"précision {precision_id}, thème caché Buts, texte « {full_text} » ; points {before} → {after} ; le tour est à Sam"


def p3_3(run):
    precision_id = run.memory["p3_precision_id"]
    _jid, _jpid, jacques_name = user(run, "jacques")
    sam = run.persona("sam")
    jacques = run.persona("jacques")
    rewards = reward_sounds(run, "sam")
    run.check(
        rewards == "désactivés",
        f"sons de récompense de Sam avant P3.3 : {rewards}, désactivés par défaut",
    )
    set_reward_sounds(run, sam, True)
    show_thread(sam, "jacques", jacques_name)
    card = precision_card(sam, "recipient", PRECISION_TEXT)
    state = card.wait(
        lambda s: s["guess"] == "pending", "précision en attente de devinette"
    )
    run.check(
        state["header"] == ["hidden"],
        f"icônes de l'en-tête avant la devinette : {state['header']}",
    )
    run.check(
        state["footer"] == "Un thème est caché dans cette réponse.",
        f"pied : {state['footer']!r}",
    )
    leak = no_store_leak(sam)
    run.check(
        leak is True,
        (
            "le Store de Sam contient le thème caché avant la devinette"
            if leak is False
            else "Store du client web illisible (odoo.__WOWL_DEBUG__ absent) : fuite non vérifiable"
        ),
    )
    question = f"{jacques_name} a caché un thème dans cette réponse. Lequel ?"
    run.check(question in state["actions"], f"question : {state['actions']!r}")
    run.check(
        "Un seul essai." in state["actions"],
        f"« Un seul essai. » absent : {state['actions']!r}",
    )

    before = karma_of(run, "sam", "jacques")
    sam.record_sounds()
    sam.record_points()
    jacques.record_points()
    card.click(f"{OPTION}[data-code='goals']")
    card.wait(lambda s: s["pressed"] == ["goals"], "Buts proposé")
    card.click(".o-linkup-RefletActions-guess", "Proposer ce thème")
    goals = category_name(run, "goals")
    state = card.wait(
        lambda s: s["guess"] == "found"
        and s["header"] == ["goals"]
        and s["footer"] == f"Thème trouvé : {goals}",
        f"Buts trouvé et dévoilé, « Thème trouvé : {goals} »",
    )

    row = precision_row(run, precision_id)
    run.check(
        row[2:4] == ["found", "goals"], f"précision {precision_id} : {row}"
    )
    lines = ledger_lines(run, precision_id)
    expected = [
        ("jacques", "precision_sent", 1000, ""),
        ("jacques", "theme_guessed", 100, ""),
        ("sam", "precision_sent", 1000, ""),
        ("sam", "theme_guessed", 100, ""),
    ]
    run.check(
        lines == expected,
        f"registre de la précision : {lines}, attendu {expected}",
    )
    after = check_delta(run, before, {"sam": 100, "jacques": 100})
    for persona in (sam, jacques):
        expect_bursts(
            run,
            persona,
            [("gain", 100, "Thème caché trouvé")],
            f"+100 affiché chez {persona.login_name}",
        )

    # A second try: the card offers none, and the server refuses one.
    run.check(
        "guess" not in state["modes"],
        f"la devinette reste offerte : {state['modes']}",
    )
    answer = sam.rpc(
        "linkup.reflet",
        "action_guess",
        [[precision_id], category_id(run, "emotions")],
    )
    run.check(
        ALREADY_ANSWERED in str(answer.get("error", "")),
        f"second essai : {answer}, attendu le refus « {ALREADY_ANSWERED} »",
    )
    run.check(
        precision_row(run, precision_id)[2:4] == ["found", "goals"],
        "le second essai a changé la devinette",
    )
    check_delta(run, after, {"sam": 0, "jacques": 0})

    try:
        sam.wait_until(
            lambda _d: played(sam, "linkup_ting"), "son « Ting » joué"
        )
    except StepFailure:
        raise StepFailure(
            f"son « Ting » non joué à la devinette trouvée, sons de récompense"
            f" {reward_sounds(run, 'sam')} ; sons joués chez Sam : {sam.played_sounds()}"
        ) from None
    return (
        f"sons de récompense activés par Aide › Sons ; Buts trouvé ; points {before} → {after} ;"
        " second essai refusé ; son Ting joué"
    )


def p3_4(run):
    _fid, _fpid, france_name = user(run, "france")
    rows = run.sql(
        "SELECT r.id, coalesce(r.body_text, '') FROM linkup_reflet r"
        " JOIN res_users a ON a.id = r.author_id JOIN res_users b ON b.id = r.recipient_id"
        " WHERE a.login = 'france' AND b.login = 'sam' AND r.kind = 'precision'"
        " AND r.guess_state = 'pending'"
    )
    run.check(
        len(rows) == 1, f"précisions de France en attente de Sam : {rows}"
    )
    precision_id, body = int(rows[0][0]), rows[0][1]
    themes = hidden_codes(run, precision_id)
    run.check(
        themes == ["goals"],
        f"thème attendu de la précision de France : {themes}, le guide dit Buts",
    )

    sam = run.persona("sam")
    france = run.persona("france")
    show_thread(sam, "france", france_name)
    card = precision_card(sam, "recipient", body)
    state = card.wait(
        lambda s: s["guess"] == "pending",
        "précision de France en attente de devinette",
    )
    run.check(
        state["header"] == ["hidden"],
        f"icônes de l'en-tête avant la devinette : {state['header']}",
    )
    before = karma_of(run, "sam", "france")
    ledger_before = ledger_lines(run, precision_id)
    rewards = reward_sounds(run, "sam")
    run.check(
        rewards == "activés",
        f"sons de récompense de Sam : {rewards}, activés en P3.3",
    )
    sam.record_points()
    sam.record_sounds()

    # The missed branch: Émotions, while the hidden theme is Buts.
    card.click(f"{OPTION}[data-code='emotions']")
    card.wait(lambda s: s["pressed"] == ["emotions"], "Émotions proposé")
    card.click(".o-linkup-RefletActions-guess", "Proposer ce thème")
    goals = category_name(run, "goals")
    card.wait(
        lambda s: s["guess"] == "missed"
        and s["header"] == ["goals"]
        and s["footer"] == f"Thème manqué : {goals}",
        f"thème manqué, Buts dévoilé, « Thème manqué : {goals} »",
    )
    row = precision_row(run, precision_id)
    run.check(
        row[2:4] == ["missed", "emotions"], f"précision {precision_id} : {row}"
    )
    lines = ledger_lines(run, precision_id)
    run.check(
        lines == ledger_before,
        f"registre de la précision : {ledger_before} → {lines}",
    )
    after = check_delta(run, before, {"sam": 0, "france": 0})
    run.settle()
    seen = sam.recorded_points()["bursts"]
    run.check(
        not seen, f"points affichés chez Sam pour un thème manqué : {seen}"
    )
    run.check(
        not played(sam, "linkup_ting"),
        f"son « Ting » joué pour un thème manqué, sons de récompense activés : {sam.played_sounds()}",
    )

    show_thread(france, "sam", user(run, "sam")[2])
    precision_card(france, "author", body).wait(
        lambda s: s["guess"] == "missed"
        and s["footer"] == f"Thème manqué : {goals}",
        "chez France, « Thème manqué : Buts »",
    )
    # The reward sounds go back to their default, off.
    set_reward_sounds(run, sam, False)
    return (
        f"branche « manqué » (Émotions) : Buts dévoilé des deux côtés, 0 point {before} → {after} ;"
        f" aucun « +N » ni « Ting » après {SETTLE} s, sons de récompense activés ; remis à désactivés"
    )


def send_second_reflection(run, sam, jacques_name):
    """Write a reflection of category ``SECOND_CATEGORY`` in the Reflet
    view of Sam and send it with "Envoyer à…"."""
    open_reflet_view(sam)
    sam.click(f".o-linkup-HelpBar-category[data-code='{SECOND_CATEGORY}']")
    sam.find(f".o-linkup-RefletForm-title svg[data-code='{SECOND_CATEGORY}']")
    sam.type(".o-linkup-RefletForm-youSaid", SECOND_YOU_SAID)
    sam.type(".o-linkup-RefletForm-understood", SECOND_UNDERSTOOD)
    sam.click(".o-linkup-RefletView-sendTo", "Envoyer à…")
    pick_in_list(run, sam, jacques_name)
    sam.keys(Keys.ENTER, css=".o-linkup-RefletView-picker")
    sam.find_text(
        ".o-linkup-RefletView-notice", f"Reflet envoyé à {jacques_name}."
    )


def p3_5(run):
    _sid, _spid, sam_name = user(run, "sam")
    _jid, _jpid, jacques_name = user(run, "jacques")
    sam = run.persona("sam")
    jacques = run.persona("jacques")
    known = run.memory["p1_reflet_id"]
    before = karma_of(run, "sam", "jacques")

    send_second_reflection(run, sam, jacques_name)
    rows = run.sql(
        "SELECT r.id, r.state FROM linkup_reflet r"
        " JOIN res_users a ON a.id = r.author_id JOIN res_users b ON b.id = r.recipient_id"
        " WHERE a.login = 'sam' AND b.login = 'jacques' AND r.kind = 'initial'"
        f" AND r.id != {int(known)}"
    )
    run.check(
        len(rows) == 1 and rows[0][1] == "sent",
        f"second reflet de Sam à Jacques : {rows}",
    )
    second_id = int(rows[0][0])
    run.memory["p3_second_id"] = second_id
    check_delta(run, before, {"sam": 0, "jacques": 0})

    # Confirmation: the pair already earned its link, only the sending pays.
    show_thread(jacques, "sam", sam_name)
    sam.record_points()
    jacques.record_points()
    sent = received_card(jacques, "sent", SECOND_UNDERSTOOD)
    sent.wait(
        lambda s: "validate" in s["modes"],
        "second reflet à valider chez Jacques",
    )
    sent.click(".o-linkup-RefletActions-confirm", "C'est un lien !")
    card = received_card(jacques, "confirmed", SECOND_UNDERSTOOD)
    card.wait(
        lambda s: "answer" in s["modes"],
        "second reflet confirmé, réponse offerte",
    )
    lines = ledger_lines(run, second_id)
    expected = [
        ("jacques", "reflect_confirmed", 0, "pair_lifetime_cap"),
        ("sam", "reflect_confirmed", 0, "pair_lifetime_cap"),
        ("sam", "reflect_sent", 100, ""),
    ]
    run.check(
        lines == expected,
        f"registre de la confirmation : {lines}, attendu {expected}",
    )
    middle = check_delta(run, before, {"sam": 100, "jacques": 0})
    expect_bursts(
        run,
        sam,
        [("gain", 100, "Ton reflet est confirmé")],
        "+100 d'envoi affiché chez Sam",
    )

    # "Oui, c'est exactement ça !"
    card.click(".o-linkup-RefletActions-exact", "Oui, c'est exactement ça !")
    card.wait(
        lambda s: "exact" in s["forms"],
        "formulaire « Oui, c'est exactement ça ! » ouvert",
    )
    card.click(
        ".o-linkup-RefletActions-form[data-form='exact'] .o-linkup-RefletActions-send",
        f"Envoyer à {sam_name}",
    )
    jacques.find(f"{CARD}[data-kind='answer_exact'][data-role='author']")
    rows = run.sql(
        f"SELECT id FROM linkup_reflet WHERE parent_id = {second_id} AND kind = 'answer_exact'"
    )
    run.check(
        len(rows) == 1, f"réponses exactes du reflet {second_id} : {rows}"
    )
    exact_id = int(rows[0][0])
    run.memory["p3_exact_id"] = exact_id
    lines = ledger_lines(run, exact_id)
    expected = [
        ("jacques", "answer_exact", 250, ""),
        ("sam", "answer_exact", 250, ""),
    ]
    run.check(
        lines == expected,
        f"registre de la réponse : {lines}, attendu {expected}",
    )
    decaying = run.sql(
        "SELECT count(*) FROM linkup_points_ledger l JOIN linkup_points_rule r ON r.id = l.rule_id"
        f" WHERE l.reflet_id = {exact_id} AND r.decay AND l.decay_day IS NOT NULL"
    )[0][0]
    run.check(
        decaying == "2",
        f"lignes de la réponse dans une suite décroissante : {decaying}, attendu 2",
    )
    after = check_delta(run, middle, {"sam": 250, "jacques": 250})
    for persona in (sam, jacques):
        expect_bursts(
            run,
            persona,
            [("gain", 250, "Reformulation confirmée")],
            f"+250 affiché chez {persona.login_name}",
        )
    shown = [b for b in sam.recorded_points()["bursts"] if b["points"] == 1000]
    run.check(
        not shown,
        f"+1000 affiché chez Sam pour une confirmation plafonnée : {shown}",
    )
    run.check(
        turn_of(run, exact_id) == str(exact_id),
        "la réponse exacte ne tient pas le tour",
    )
    return (
        f"reflet {second_id} : confirmation 0 (plafond à vie de la paire), +100 d'envoi ; "
        f"réponse {exact_id} : +250 chacun, suite décroissante ; points {before} → {after}"
    )


STEPS = [
    (
        "P3.1",
        "jacques, carte confirmée › « Je voudrais préciser… » : bande des 12 icônes ; choisir des thèmes laisse le texte vide ; deux thèmes au plus",
        p3_1,
    ),
    (
        "P3.2",
        "Buts caché, texte écrit sans amorce, envoyer : +1000 chacun ; le tour passe à Sam",
        p3_2,
    ),
    (
        "P3.3",
        "sam : icône du thème masquée ; sons de récompense activés (Aide) ; deviner Buts : +100 chacun, son « Ting » ; second essai refusé",
        p3_3,
    ),
    (
        "P3.4",
        "Variante démo : sam, précision de France : thème attendu Buts ; manqué : thème dévoilé, 0 point, aucun Ting",
        p3_4,
    ),
    (
        "P3.5",
        "Second reflet Sam → Jacques confirmé : 0 (plafond de la paire), +100 d'envoi ; « exactement ça » : +250 chacun",
        p3_5,
    ),
]
