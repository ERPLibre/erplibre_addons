

# ERPLibre — software requirements (MoSCoW)

Tracks what a project **commits to deliver**: one requirement per line,
classified by domain and by phase, with its MoSCoW level and the state of its
delivery. Each requirement takes its place in the DevSecOps loop, carries its
threats and the list of the tests that prove it, with their last result.

The module ships **no requirement**. It ships the model, the screens and the
vocabulary; the requirements come from a project module, as data.

## The model

| | |
|---|---|
| `devops.requirement` | A requirement: code, title, domain, phase, MoSCoW level, priority, effort, owner, DevSecOps stage, acceptance criteria, dependencies. |
| `devops.requirement.threat` | A threat on a requirement, classified by STRIDE, with its mitigation and its residual risk. |
| `devops.requirement.test` | A test that proves a requirement, and its last known result. |
| `devops.requirement.category` | A functional domain. **Data**, not code. |
| `devops.requirement.phase` | A phase or a milestone. **Data**, not code. |
| `devops.requirement.classifier` | Abstract mixin: `code`, `name`, `sequence`, and the uniqueness of the code. |

### Why the domain is a model and the MoSCoW level a Selection

The rule fits in one sentence: **a Selection when the vocabulary is
universal, a model when it belongs to the project.**

MoSCoW has four values, the same everywhere, defined outside any project: it
is a Selection, and a project that wanted a fifth would no longer be dealing
with MoSCoW. Functional domains, on the other hand, only resemble each other
from one project to the next by accident — freezing them in code would force
every project to patch the shared module to name its own.

### The code carries counts

`code` is not a label: data files reference it, and the domains of the counted
figures of a presentation page compare against it. **Renaming it silently
breaks every count that relies on it** — the figure drops to zero without an
error, and the list its button opens arrives empty.

This is also the reason for the rights below.

The requirement's `code` is unique for the same reason: a test runner finds
the requirement by its code. It stays optional — several requirements without
a code coexist.

## DevSecOps planning

| Field | Role |
|---|---|
| `devsecops_stage` | Stage of the loop: plan, code, build, test, release, deploy, operate, monitor. Clickable status bar, kanban columns. The `code` value is labelled "Develop", so as not to share its translation with the `code` field. |
| `requirement_type` | Functional, non-functional, security, compliance, operational. |
| `acceptance_criteria` | Acceptance criteria, one Given / When / Then scenario per criterion. |
| `security_relevant`, `data_classification` | Whether the requirement touches security, and the most sensitive class of data it handles. |
| `depends_on_ids` / `dependent_ids` | What must be delivered before, what waits for this one. A cycle is refused, even through several hops. |

The DevSecOps stage **does not replace** the three booleans: the stage tells
where the work stands, `accepted` / `approved` / `done` what the client has
observed.

## Tests and their result

A test line is declared in data, by the project. Its `kind` tells what its
`reference` designates:

| `kind` | `reference` |
|---|---|
| `tour` | the name of the guided tour |
| `python` | the dotted path of the test method |
| `selenium` | the path of the script, relative to the repository |
| `manual` | free text |

`test_state`, stored on the requirement, sums up its lines by the worst
result: no test → `none`; a failure or an error → `failed`; otherwise a test
never run → `not_run`; otherwise a passed test → `passed`. Tests all skipped
have proven nothing: `not_run`. `tour_name` returns the reference of the first
`tour` line in sequence order, `""` if there is none.

An external runner writes the result through XML-RPC or JSON-RPC:


```python
models.execute_kw(
    db, uid, password,
    "devops.requirement.test", "record_result",
    ["INV-01", "selenium", "script/selenium/inventory_stock.py", "passed"],
    {"log": output, "duration": 12.4},
)
```


`record_result` **creates nothing**: an unknown requirement or line returns
`False` and leaves a warning in the log. A result outside `not_run`, `passed`,
`failed`, `error`, `skipped` is refused. The log is truncated to 20,000
characters, the end kept — it is the end that carries the failing assertion.
Only the `last_*` fields are written.

## Rights

| Model | Internal user | Test runner | Configuration |
|---|---|---|---|
| `devops.requirement` | read, write | read | all |
| `devops.requirement.category` | read | read | all |
| `devops.requirement.phase` | read | read | all |
| `devops.requirement.threat` | read | — | all |
| `devops.requirement.test` | read | read, result through `record_result` | all |

The vocabulary is read-only for the user: its `code` carries counts, and a
typo there costs more than a badly filled field on a requirement.

The **Requirement test runner** group is meant for the technical account of a
runner, whose credentials live on an integration machine. It does **not**
inherit the internal user: on its own, it reads what the runner matches and
writes nothing directly. `record_result` refuses any caller that is neither in
this group nor an administrator, then writes, as sudo, the result fields only:
the runner can neither declare a line, nor change its reference, nor touch the
requirement. The table holds for a dedicated account only: an internal user
who also receives the group keeps their write access to the requirements.

`test_state` and `test_count` follow the results of the tests: `create` and
`write` refuse them to any caller (AccessError), administrator included. Only
the superuser overrides it.

Threats and tests are declared through the configuration or in data: the
internal user sees them in the requirement form without being able to modify
them.

## Laying down your data

A project module declares the dependency, then its records:


```xml
<record id="categorie_inventaire" model="devops.requirement.category">
    <field name="code">inventaire</field>
    <field name="name">Inventaire et réception</field>
    <field name="sequence">50</field>
</record>

<record id="req_inv_01" model="devops.requirement">
    <field name="code">INV-01</field>
    <field name="name">Stock physique par entrepôt</field>
    <field name="category_id" ref="categorie_inventaire"/>
    <field name="phase_id" ref="phase1"/>
    <field name="moscow">must</field>
    <field name="priority">high</field>
    <field name="size">m</field>
    <field name="devsecops_stage">code</field>
    <field name="requirement_type">functional</field>
</record>

<record id="req_inv_01_test_stock" model="devops.requirement.test">
    <field name="requirement_id" ref="req_inv_01"/>
    <field name="name">Stock per warehouse</field>
    <field name="kind">selenium</field>
    <field name="reference">script/selenium/inventory_stock.py</field>
</record>

<record id="req_inv_01_threat_tampering" model="devops.requirement.threat">
    <field name="requirement_id" ref="req_inv_01"/>
    <field name="stride">tampering</field>
    <field name="description">A user edits a stock count without trace.</field>
    <field name="mitigation">Stock moves are the only way to change a quantity.</field>
    <field name="residual_risk">low</field>
</record>
```


## The screens

List grouped by domain, kanban by DevSecOps stage, form, search with
groupings, graph by domain and pivot view. The form carries the stage status
bar and the Description, Acceptance, Security, Tests and Dependencies tabs.
The search filters the security requirements, those with a failing test and
those without any test. The root menu is `Requirements`; its configuration
holds the domains and the phases.

## See also

`erplibre_devops_guide` renders a presentation page described in data, and
can count requirements in its figures.
