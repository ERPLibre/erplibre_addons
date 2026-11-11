

# ERPLibre — Stream Deck requirements

The requirements of the ERPLibre Stream Deck — the deck programs, the GNOME
extension ERPLibre Home, its installation, the games and the mobile plugin —
as `devops.requirement` records, each with the repository tests that prove
it. They come from the audit of the Stream Deck design specifications, row
by row, and from the designs of the Odoo inventory, of its monitoring and
of its control of the deck settings, and live here instead of in a
document.

The module depends on `erplibre_streamdeck` and `erplibre_devops_requirement`,
and adds no model, no view and no menu: the requirements show in the
Requirements application, under thirteen domains whose code starts with
`sd_`.

## What the data holds

| Audit row | Requirement |
|---|---|
| covered, or a unit test added since | done, with a proof line per test |
| no unit test yet | to do; *What is missing* says so |
| checked by a long test | done, with a proof of kind *Long test* |
| long test to write | to do; *What is missing* says what the long test must check |
| non-goal, out of scope | MoSCoW *Won't*, done, the reason in the description |
| design decision | MoSCoW *Should*, *Non-functional*, done, the reason in *Achievement* |
| open question, open risk, follow-up | MoSCoW *Should*, to do; *What is missing* says what is left |
| security invariant | MoSCoW *Must*, type *Security*, *Security relevant* |
| proof in another repository | done with a proof line per test of that repository; else to do, *What is missing* names the repository |
| violated | to do, stage *Develop*; *What is missing* describes the gap |

*Achievement* and *What is missing* name files and tests in the same
`<repository>:<path>` form as the proofs below, so each pointer resolves in
its own repository. A done requirement leaves *What is missing* empty. A
requirement that protects a secret, an access or a file mode is of type
*Security* and marked *Security relevant*.

*Notes* opens on the origin of the requirement: what the audit found for
its row.

| Origin | Meaning |
|---|---|
| covered by a test | a test of a repository already proved it |
| unit test missing | no unit test proved it |
| long test needed | only the long test, in virtual machines with a GNOME session, can check it |
| documented only | the design states it: a decision, a rule or a non-goal |
| proof in another repository | its test belongs to the games or the mobile repository |
| violated | the code did not hold it |

What follows the origin says what holds the requirement: *a unit test
pins it*, *an existing test covers it*, *its unit test shows the
violation*.

Each requirement carries a stable code `SD-<DOMAIN>-R<row>`, for example
`SD-DEFECTS-R02`. The data is loaded **once**: it is `noupdate`, so a
requirement edited by hand keeps its edit when the module is updated. The
exception is a requirement whose text a new version rewrites: the
migration of that version loads it again from its file, as it does a
proof whose reference changed, and its French comes back from the catalog.

## The Inventory domain

The domain *Inventory* (`sd_inv`, file `data/requirement_inventory.xml`)
holds the requirements of the Odoo inventory of the workstations and their
decks: one per decision, non-goal and anti-goal of its design, coded
`SD-INV-R<nn>`. Its proofs are Odoo tests of `erplibre_streamdeck`, Node
tests of the extension and unit tests of ERPLibre. A decision the code does
not hold yet stays to do, stage *Develop*, and *What is missing* describes
the gap. A requirement whose guarantee rests on another one lists it under
*Depends on*, and stays to do, naming it in *What is missing*, as long as
that one is not done.

The test `tests/test_requirement_inventory.py` checks that each proof names
a test that exists: an Odoo test is imported and must run under
`--test-tags /<module>`; inside an ERPLibre checkout, a test of the
extension or of ERPLibre must be in the committed tree of its repository
(that check is skipped outside a checkout). A Node test declared in a
`for … of` loop over a literal array is named once per value of the loop;
a name the loop does not produce is not a test. Each test of the five
inventory test files of `erplibre_streamdeck` proves at least one
requirement.

## The Monitoring domain

The domain *Monitoring* (`sd_mon`, file `data/requirement_monitoring.xml`)
holds the requirements of the monitoring of the workstations and their
decks: one per user decision, design choice, Odoo-side item, non-goal and
anti-goal of its design, coded `SD-MON-R<nn>`, apart from the inventory so
that each part of the work is checked on its own. Its proofs are Odoo
tests of `erplibre_streamdeck`. A design decision that no Odoo test can
hold, such as a locked workstation counted as silent, is done without a
proof, MoSCoW *Should*, *Non-functional*, its reason in *Achievement*. A
gap the code still has stays to do and *What is missing* describes it. A
requirement whose guarantee rests on another one lists it under *Depends
on*, and stays to do, naming it in *What is missing*, as long as that one
is not done.

The test `tests/test_requirement_monitoring.py` checks that each proof
names an Odoo test that runs under `--test-tags /<module>`, that each test
of the files `test_streamdeck_monitor*.py` and `test_streamdeck_settings.py`
of `erplibre_streamdeck` proves at least one requirement, that the
requirements still to do are exactly those it names, and that none is done
while one it depends on is not.

## The Control domain

The domain *Control* (`sd_ctl`, file `data/requirement_control.xml`) holds
the requirements of the control of the deck settings by Odoo, the settings
part of the third lot: one per user decision, design choice and anti-goal
of its design, coded `SD-CTL-R<nn>`. Its proofs are Odoo tests of
`erplibre_streamdeck`, Node tests of the extension and unit tests of
ERPLibre, since the configuration crosses the three repositories. The key
layout, the second part of the lot, adds its requirements after these.

The test `tests/test_requirement_control.py` checks that each proof names
a test that exists, under the same rules as the inventory; that each test
of the files `test_streamdeck_config*.py` of `erplibre_streamdeck` proves
at least one requirement; that the tests holding the review points of the
lot are cited; and that the requirements still to do are exactly those it
names.

## Proofs and verdicts

A proof line is a `devops.requirement.test` whose reference names a test of
a repository:

```text
<repository>:<path>::<test id>
```

| Kind | Repository | Test id | Example |
|---|---|---|---|
| Repository unit test | `erplibre`, `erplibre-home-gnome-extension`, `streamdeck_game` | `Class::method` | `erplibre:test/test_deck_lock.py::LaCommandeSousVerrou::test_a_busy_deck_runs_nothing_and_exits_two` |
| Node test | `erplibre-home-gnome-extension` | the test name | `erplibre-home-gnome-extension:test/unit/deck-service.test.js::restart goes through the unit only when it exists` |
| Long test | `erplibre` | the check name | `erplibre:long_test/install_erplibre_home.py::extension-indicators` |
| Python test | an Odoo module | its dotted path | `odoo.addons.erplibre_streamdeck.tests.test_streamdeck_access.TestStreamdeckAccess.test_the_manager_reads_the_whole_fleet` |

A Python test is an Odoo test, named by the dotted path of its method:
`script/test/odoo_test_report.py --modules erplibre_streamdeck` of ERPLibre
runs the module's tests on a throwaway database and pushes their verdicts.

A test runner pushes its verdict with the reference alone, through
`record_result_by_reference` of `erplibre_devops_requirement`, as a user of
the runner group:


```python
models.execute_kw(
    db, uid, api_key,
    "devops.requirement.test", "record_result_by_reference",
    ["repo_unittest",
     "erplibre:test/test_deck_lock.py::LaCommandeSousVerrou"
     "::test_a_busy_deck_runs_nothing_and_exits_two",
     "passed"],
    {"log": output, "duration": 0.8},
)
```


The verdict reaches every requirement whose proof carries that reference:
the example above updates two requirements in one call.

## Translation

The requirement names, descriptions and domain names are written in English
and ship in Canadian French: `i18n/fr_CA.po` holds the French of every one
of them, so loading the French language (`fr_CA`) shows the requirements in
French. *Achievement*, *What is missing* and *Notes* stay in English in
both languages: `erplibre_devops_requirement` does not declare these fields
translatable, so the module ships no French for them.
