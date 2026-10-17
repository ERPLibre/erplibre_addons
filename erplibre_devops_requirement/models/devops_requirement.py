# Copyright 2026 TechnoLibre inc. - Mathieu Benoit
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from odoo import _, api, fields, models
from odoo.exceptions import AccessError, ValidationError
from odoo.tools.translate import html_translate


class DevopsRequirement(models.Model):
    """Requis logiciel d'un projet d'implémentation, classé en MoSCoW.

    Le niveau MoSCoW dit ce à quoi le projet s'engage ; `priority` ordonne
    le travail À L'INTÉRIEUR d'un niveau. Les trois booléens suivent le
    cycle : le client ACCEPTE le requis, l'APPROUVE pour développement,
    puis sa réalisation est constatée.

    `devsecops_stage` place le requis dans la boucle DevSecOps, de la
    planification à la surveillance. Il ne remplace pas les trois booléens :
    l'étape dit où en est le TRAVAIL, les booléens ce que le CLIENT a
    constaté.
    """

    _name = "devops.requirement"
    _description = "Software requirement (MoSCoW)"
    _order = "category_id, sequence, code"

    # Un lanceur de tests retrouve le requis par son code : deux requis du
    # même code rendraient le rapprochement ambigu. PostgreSQL tient
    # plusieurs NULL pour distincts, un requis sans code reste donc permis.
    code = fields.Char(string="Code", index=True)
    name = fields.Char(string="Requirement", required=True, translate=True)
    category_id = fields.Many2one(
        "devops.requirement.category",
        string="Domain",
        required=True,
        index=True,
        ondelete="restrict",
    )
    moscow = fields.Selection(
        [
            ("must", "Must have"),
            ("should", "Should have"),
            ("could", "Could have"),
            ("wont", "Won't have"),
        ],
        string="MoSCoW level",
        default="should",
        index=True,
    )
    # Le libellé du palier intermédiaire se dit « Normal » et non
    # « Medium », qui est déjà celui de `size` : un même terme anglais pour
    # deux axes se réduit à une seule entrée de traduction, impossible à
    # accorder dans une langue genrée.
    priority = fields.Selection(
        [("high", "High"), ("medium", "Normal"), ("low", "Low")],
        string="Priority",
        default="medium",
        index=True,
    )
    phase_id = fields.Many2one(
        "devops.requirement.phase",
        string="Phase",
        index=True,
        ondelete="restrict",
    )
    size = fields.Selection(
        [("s", "Small"), ("m", "Medium"), ("l", "Large")],
        string="Estimated effort",
    )
    responsible_id = fields.Many2one("res.users", string="Responsible")
    description = fields.Text(string="Description", translate=True)
    notes = fields.Text(string="Notes")
    sequence = fields.Integer(default=10)
    accepted = fields.Boolean(string="Accepted", index=True)
    approved = fields.Boolean(string="Approved", index=True)
    done = fields.Boolean(string="Done", index=True)
    # Comment le requis est couvert — module, menu, vue — ou, s'il ne l'est
    # pas encore, l'état actuel et la suite.
    achievement = fields.Text(string="Achievement")
    # Ce qui manque encore pour une couverture complète en production :
    # dépendance amont, décision du client, intégration externe.
    missing = fields.Text(string="What is missing")

    # L'étape « code » se libelle « Develop » : « Code » est déjà le
    # libellé du champ `code`, et un même terme anglais se réduit à une
    # seule entrée de traduction, qui ne peut pas dire à la fois le champ et
    # l'activité.
    devsecops_stage = fields.Selection(
        [
            ("plan", "Plan"),
            ("code", "Develop"),
            ("build", "Build"),
            ("test", "Test"),
            ("release", "Release"),
            ("deploy", "Deploy"),
            ("operate", "Operate"),
            ("monitor", "Monitor"),
        ],
        string="DevSecOps stage",
        default="plan",
        required=True,
        index=True,
        # Le kanban groupé par étape affiche aussi les étapes vides.
        group_expand=True,
    )
    requirement_type = fields.Selection(
        [
            ("functional", "Functional"),
            ("non_functional", "Non-functional"),
            ("security", "Security"),
            ("compliance", "Compliance"),
            ("operational", "Operational"),
        ],
        string="Requirement type",
        default="functional",
        index=True,
    )
    # `html_translate` traduit bloc par bloc : un critère reformulé ne fait
    # perdre que la traduction de son propre paragraphe.
    acceptance_criteria = fields.Html(
        string="Acceptance criteria",
        translate=html_translate,
        sanitize=True,
        help=(
            "Observable conditions that make the requirement accepted. "
            "Prefer one scenario per criterion, in the form: Given a "
            "context, When an action happens, Then an expected outcome."
        ),
    )
    security_relevant = fields.Boolean(
        string="Security relevant",
        index=True,
        help="The requirement protects data, access or traceability.",
    )
    data_classification = fields.Selection(
        [
            ("public", "Public"),
            ("internal", "Internal"),
            ("confidential", "Confidential"),
            ("restricted", "Restricted"),
        ],
        string="Data classification",
        help="Most sensitive class of data the requirement handles.",
    )
    depends_on_ids = fields.Many2many(
        "devops.requirement",
        "devops_requirement_dependency_rel",
        "requirement_id",
        "depends_on_id",
        string="Depends on",
        help="Requirements that must be delivered before this one.",
    )
    dependent_ids = fields.Many2many(
        "devops.requirement",
        "devops_requirement_dependency_rel",
        "depends_on_id",
        "requirement_id",
        string="Required by",
        help="Requirements that wait for this one.",
    )
    threat_ids = fields.One2many(
        "devops.requirement.threat", "requirement_id", string="Threats"
    )
    test_ids = fields.One2many(
        "devops.requirement.test", "requirement_id", string="Tests"
    )
    test_count = fields.Integer(
        string="Test count", compute="_compute_test_count"
    )
    # Stocké : une page qui affiche l'état de dizaines de requis le lit en
    # une requête, sans recalculer les lignes de test de chacun.
    test_state = fields.Selection(
        [
            ("none", "No test"),
            ("not_run", "Not run"),
            ("passed", "Passed"),
            ("failed", "Failed"),
        ],
        string="Test state",
        compute="_compute_test_state",
        store=True,
        index=True,
    )
    tour_name = fields.Char(
        string="Tour name",
        compute="_compute_tour_name",
        help="Reference of the first guided tour test, in sequence order.",
    )

    _sql_constraints = [
        ("code_uniq", "unique(code)", "The requirement code must be unique."),
    ]

    # Champs qui résument les tests : ils suivent les résultats que
    # `record_result` écrit, et une saisie directe y ferait passer un
    # verdict inventé pour celui d'un lancement.
    _TEST_SUMMARY_FIELDS = ("test_count", "test_state")

    def _check_test_summary_not_written(self, vals_list):
        # Le calcul de l'ORM ne passe ni par create ni par write : refuser
        # ces champs ici ne bloque que l'écriture d'un appelant. Le
        # superutilisateur garde la main, pour une migration ou une reprise.
        if self.env.su:
            return
        for vals in vals_list:
            written = [
                name for name in self._TEST_SUMMARY_FIELDS if name in vals
            ]
            if written:
                raise AccessError(
                    _(
                        "The test summary of a requirement follows its test "
                        "results and cannot be written: %(fields)s.",
                        fields=", ".join(written),
                    )
                )

    @api.model_create_multi
    def create(self, vals_list):
        self._check_test_summary_not_written(vals_list)
        return super().create(vals_list)

    def write(self, vals):
        self._check_test_summary_not_written([vals])
        return super().write(vals)

    @api.constrains("depends_on_ids")
    def _check_dependency_cycle(self):
        # `_has_cycle` remplace `_check_m2m_recursion`, déprécié en 18.0. Il
        # suit la table de relation en SQL récursif : un requis qui dépend
        # de lui-même, directement ou par une chaîne, forme un cycle.
        if self._has_cycle("depends_on_ids"):
            raise ValidationError(
                _("A requirement cannot depend on itself, even indirectly.")
            )

    @api.depends("test_ids")
    def _compute_test_count(self):
        for requirement in self:
            requirement.test_count = len(requirement.test_ids)

    @api.depends("test_ids.last_result")
    def _compute_test_state(self):
        # Le pire résultat l'emporte : un échec ou une erreur suffit à
        # rendre « failed ». Un test jamais lancé empêche « passed », et un
        # requis dont tous les tests sont ignorés n'a rien prouvé : il
        # reste « not_run ».
        for requirement in self:
            results = set(requirement.test_ids.mapped("last_result"))
            if not results:
                state = "none"
            elif results & {"failed", "error"}:
                state = "failed"
            elif "not_run" in results:
                state = "not_run"
            elif "passed" in results:
                state = "passed"
            else:
                state = "not_run"
            requirement.test_state = state

    @api.depends("test_ids.kind", "test_ids.reference", "test_ids.sequence")
    def _compute_tour_name(self):
        # Rend "" et non False sans visite : la valeur part telle quelle
        # vers une page client, où False s'afficherait « false ». Le tri
        # lit `_origin.id` : une ligne pas encore enregistrée porte un
        # NewId, que Python ne sait pas comparer à un entier.
        for requirement in self:
            tours = requirement.test_ids.filtered(
                lambda line: line.kind == "tour"
            ).sorted(key=lambda line: (line.sequence, line._origin.id or 0))
            requirement.tour_name = tours[:1].reference or ""
