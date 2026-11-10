

# ERPLibre — presentation guide

Renders the **presentation page of an implementation project**: a hero with
its figures, sections of cards, a roadmap, a footer. Everything comes from the
database; the component knows nothing of any particular project.

The module ships **no page**. It ships the rendering engine; a project module
describes its own page in data.

## Why in data

A page written in JavaScript is copied from one project to the next, and each
copy drifts. Described in data, it is translated, corrected without a
redeployment, and its figures are counted on the tables instead of going stale
hardcoded in the template.

## The model

| | |
|---|---|
| `devops.guide` | The page: hero, buttons, footer. |
| `devops.guide.stat` | A figure of the hero, literal or counted. |
| `devops.guide.section` | A section, whose **shape** is held by `kind`. |
| `devops.guide.card` | A card: a problem, its answer, at most one button. |
| `devops.guide.counter.mixin` | Abstract mixin: resolves a count described in data. |
| `devops.requirement` (extension) | `guide_id`, the detailed page of the requirement, and `guide_card_ids`, the cards that cite it. |

### The three section shapes

| `kind` | What is rendered |
|---|---|
| `lead` | Its `intro` alone, as body text. |
| `cards` | Its cards, as a grid. |
| `roadmap` | Its cards, as numbered steps. |

A `lead` section **refuses** to hold cards: its rendering stops at the
introduction, and cards placed there would vanish from the page without a
word. The constraint works both ways — when a card is created and when a
section holding cards changes shape.

### The button of a card

Three sources, in this order: `url` opens a tab, `action_xmlid` calls the
action, `count_model` opens that model filtered by `count_domain`. All three
empty: no button, which renders a roadmap step.

**A target without a label renders no button**: a button holding only its
arrow tells nothing about what it opens.

A button whose target the reader cannot open **is not rendered**: an action
that cannot be found, that is not an action, that is restricted to groups the
reader is not a member of, or whose `res_model` the reader cannot read; a
counted model the reader cannot read. `get_page` then returns `action_xmlid`
and `action_label` empty. Emptying the label too prevents the fallback to
`count_model`, which would open another target than the one announced.

### A card restricted to groups

`groups_id` empty: every reader of the guide sees the card. Set: only a member
of at least one of these groups sees it, implied groups included. This avoids
showing a tour that leads to a menu the reader cannot open.

The restriction is an **access rule** on `devops.guide.card`, not a display
filter: the card is missing from the page, from the **Guide** tab of the
requirement form and from an RPC call. The administrator (`base.group_system`)
reads every card, to edit them.

### A card linked to a requirement

`requirement_id` links the card to a requirement of
`erplibre_devops_requirement`. The card then shows, in a grid as in a
roadmap:

- a pill with the **code** and the **MoSCoW level** of the requirement;
- a pill with its **DevSecOps stage** (`devsecops_stage`), which tells whether
  the requirement is delivered: a "could" requirement still in planning does
  not read as a delivered one;
- a pill with the **state of its tests**, coloured by state;
- a **Requirement** button, which opens the requirement form;
- a **Guide** button, if the requirement names a detailed page (`guide_id`);
- a **tour** button, if a tour known to the browser is attached (see below).

`get_page` returns, for each card, a `requirement` dictionary with fixed
keys: `id`, `code`, `name`, `moscow`, `moscow_label`, `stage`, `stage_label`,
`test_state`, `test_state_label`, `has_guide`. A card without a requirement,
or whose requirement is not readable, receives the same keys **empty** (`""`);
`has_guide` is `True` or `""`. An unreadable requirement does not lend its
tour either: the card stays on the page, without a tour button unless it
carries one of its own. The labels arrive translated into the reader's
language.

The stage pill carries one class per value,
`o_devops_guide_pill_stage_<stage>` (`plan`, `code`, `build`, `test`,
`release`, `deploy`, `operate`, `monitor`). It is outlined: dashed while the
requirement is not delivered (`plan` to `test`), solid in `--dg-accent` once
released or deployed, solid in `--dg-ok` in operation or under monitoring. A
project that wants another reading redefines these classes.

### A figure of the hero is not filtered by its domain

A counted card opens **its** model filtered by **its** domain. A figure of the
hero opens the action its `action_xmlid` names, as it is: the module does not
guess a filter in place of whoever chose the action. A figure that must open
a filtered list names an action that is filtered.

### The `{count}` marker

`action_label`, the label of a card's button, accepts `{count}`, replaced by
the count when `count_model` is set. A label thus stays right when the data
moves, where a hardcoded number drifts. Without a counted model, the marker
stays as it is.

### A count never breaks the page

`_count_records` **always** returns an integer. A model missing from the
registry, an unreadable domain, a domain that is not a list, an unknown field
or a denied access return `0` and leave a trace in the log. A presentation
page must never prevent a screen from opening.

The domain is read by `ast.literal_eval`, which evaluates literals only: no
call, no name, so nothing to execute. The `search_count` runs inside a
savepoint, without which an SQL error would abort the whole transaction —
catching the Python exception does not restore it.

## Opening a page

The module ships no client action: a project declares its own and names its
guide by its XML id.


```xml
<record id="guide_implantation" model="devops.guide">
    <field name="name">Implantation</field>
    <field name="title">Le projet, de bout en bout</field>
</record>

<record id="action_guide_implantation" model="ir.actions.client">
    <field name="name">Implantation</field>
    <field name="tag">devops_guide.page</field>
    <field name="context">{'guide_xmlid': 'mon_module.guide_implantation'}</field>
</record>
```


The **Preview** button of the form opens the same page without any action
existing, by passing `guide_id` in the context.

An unknown `guide_xmlid`, or one that names another model, renders an empty
page that says so — the screen opens instead of breaking.

## Theme

The stylesheet sets eleven variables on `.o_devops_guide`. A project redefines
them without copying the style:

```scss
.o_devops_guide {
    --dg-accent: #1b6b5a;        // accent colour, released requirement
    --dg-accent-soft: #e8f2ef;   // its light background
    --dg-bg: #f7f7f8;            // page background
    --dg-surface: #ffffff;       // card background
    --dg-ink: #1f2937;           // text
    --dg-muted: #5b6b70;         // secondary text
    --dg-line: #e5e7eb;          // rules and borders
    --dg-warn: #f6a623;          // problem icon, pill, tests to run
    --dg-ok: #2e7d32;            // answer icon, passed tests, requirement in operation
    --dg-fail: #c62828;          // failed tests
    --dg-shadow: 0 1px 3px rgba(0, 0, 0, 0.08);
}
```

The green check mark shows only when a problem is stated: it means "answer to
this problem". A text alone stays text.

## Guided tour

Two sources of tour:

- the guide's `tour_name`, started by the first button of the hero;
- the **effective** tour of a card: its own `tour_name`, otherwise its
  requirement's (the requirement's `tour_name`, the reference of its first
  test line of kind "tour").

The label comes from `tour_label`, otherwise from a fallback translated on the
server side ("Start the tour" on the hero, "Show me" on a card).

**A tour button shows only if the tour is in the browser's JS registry**
(`web_tour.tours`). The service returns without doing anything for an unknown
name; a mute button is therefore not shown. A tour declared only in
`web.assets_tests` is in the registry in test mode only: a tour meant for the
guide is declared in `web.assets_backend`, under `static/src`, where its `_t`
are also extracted for translation.

### Onboarding is restored

The manual mode of the service turns on the user's Onboarding **in the
database**. Left on, every following load would start Odoo's native tours not
yet consumed, and the end of the tour would chain into the next one. The
guide reads the state at page load (`session.tour_enabled`) and, if it was
off, restores it as soon as the tour has started.

The running tour goes on, its state living in the browser. In return, **a
page reload erases it**: the service resumes a manual tour at load only when
Onboarding is on. A tour started from the guide therefore navigates through
the menus: no `url` (the guide passes `redirect: false`), no `goToUrl`, no
`expectUnloadPage`.

Do not ship a `web_tour.tour` record for a guide tour, except with
`custom=True`: otherwise it joins the queue of Onboarding tours.

## Detailed guide of a requirement

`guide_id` on the requirement names its detailed page. The **Guide** button of
the requirement form, visible only when `guide_id` is set, opens it through
`action_open_guide`, like the **Preview** button of a guide. The **Guide** tab
of the form lists the cards that cite the requirement.

## See also

`erplibre_devops_requirement`, which this module depends on: it brings the
root menu under which the configuration of the guides hangs, and the model
that the counts of an implementation page count most often.
