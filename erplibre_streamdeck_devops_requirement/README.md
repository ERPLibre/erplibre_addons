

# ERPLibre — Stream Deck requirements

The requirements of the ERPLibre Stream Deck — the deck programs, the GNOME
extension ERPLibre Home, its installation, the games and the mobile plugin —
as `devops.requirement` records, each with the repository tests that prove
it. They come from the audit of the Stream Deck design specifications, row
by row, and live here instead of in a document.

The module depends on `erplibre_streamdeck` and `erplibre_devops_requirement`,
and adds no model, no view and no menu: the requirements show in the
Requirements application, under ten domains whose code starts with `sd_`.

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
| proof in another repository | to do; *What is missing* names the repository |
| violated | to do, stage *Develop*; *What is missing* describes the gap |

*Achievement* and *What is missing* name files and tests in the same
`<repository>:<path>` form as the proofs below, so each pointer resolves in
its own repository. A requirement that protects a secret, an access or a
file outside the checkout is marked *Security relevant*.

Each requirement carries a stable code `SD-<DOMAIN>-R<row>`, for example
`SD-DEFECTS-R02`. The data is loaded **once**: it is `noupdate`, so a
requirement edited by hand keeps its edit when the module is updated.

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
French. *Achievement*, *What is missing* and *Notes* are not translated:
they name files, tests and commands, which read the same in both languages.
