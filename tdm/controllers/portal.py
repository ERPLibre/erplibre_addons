from collections import OrderedDict
from operator import itemgetter

from odoo import _, http
from odoo.addons.portal.controllers.portal import CustomerPortal
from odoo.addons.portal.controllers.portal import pager as portal_pager
from odoo.exceptions import AccessError, MissingError
from odoo.http import request
from odoo.osv.expression import OR
from odoo.tools import groupby as groupbyelem


class TdmController(CustomerPortal):
    def _prepare_portal_layout_values(self):
        values = super(TdmController, self)._prepare_portal_layout_values()
        values["tdm_entrevue_count"] = request.env[
            "tdm.entrevue"
        ].search_count([])
        values["tdm_entrevue_stage_count"] = request.env[
            "tdm.entrevue.stage"
        ].search_count([])
        values["tdm_offre_emploi_count"] = request.env[
            "tdm.offre.emploi"
        ].search_count([])
        values["tdm_offre_emploi_applique_count"] = request.env[
            "tdm.offre.emploi.applique"
        ].search_count([])
        values["tdm_offre_emploi_applique_stage_count"] = request.env[
            "tdm.offre.emploi.applique.stage"
        ].search_count([])
        values["tdm_offre_emploi_stage_count"] = request.env[
            "tdm.offre.emploi.stage"
        ].search_count([])
        values["tdm_offre_emploi_type_count"] = request.env[
            "tdm.offre.emploi.type"
        ].search_count([])
        values["tdm_secteur_activite_count"] = request.env[
            "tdm.secteur_activite"
        ].search_count([])
        return values

    # ------------------------------------------------------------
    # My Tdm Entrevue
    # ------------------------------------------------------------
    def _tdm_entrevue_get_page_view_values(
        self, tdm_entrevue, access_token, **kwargs
    ):
        values = {
            "page_name": "tdm_entrevue",
            "tdm_entrevue": tdm_entrevue,
            "user": request.env.user,
        }
        return self._get_page_view_values(
            tdm_entrevue,
            access_token,
            values,
            "my_tdm_entrevues_history",
            False,
            **kwargs,
        )

    @http.route(
        ["/my/tdm_entrevues", "/my/tdm_entrevues/page/<int:page>"],
        type="http",
        auth="user",
        website=True,
    )
    def portal_my_tdm_entrevues(
        self,
        page=1,
        date_begin=None,
        date_end=None,
        sortby=None,
        filterby=None,
        search=None,
        search_in="content",
        **kw,
    ):
        values = self._prepare_portal_layout_values()
        TdmEntrevue = request.env["tdm.entrevue"]
        domain = []

        searchbar_sortings = {
            "date": {"label": _("Newest"), "order": "create_date desc"},
            "name": {"label": _("Name"), "order": "name"},
        }
        searchbar_filters = {
            "all": {"label": _("All"), "domain": []},
        }
        searchbar_inputs = {}
        searchbar_groupby = {}

        # default sort by value
        if not sortby:
            sortby = "date"
        order = searchbar_sortings[sortby]["order"]
        # default filter by value
        if not filterby:
            filterby = "all"
        domain = searchbar_filters[filterby]["domain"]

        # search
        if search and search_in:
            search_domain = []
            domain += search_domain
        # archive groups - Default Group By 'create_date'
        archive_groups = self._get_archive_groups("tdm.entrevue", domain)
        if date_begin and date_end:
            domain += [
                ("create_date", ">", date_begin),
                ("create_date", "<=", date_end),
            ]
        # tdm_entrevues count
        tdm_entrevue_count = TdmEntrevue.search_count(domain)
        # pager
        pager = portal_pager(
            url="/my/tdm_entrevues",
            url_args={
                "date_begin": date_begin,
                "date_end": date_end,
                "sortby": sortby,
                "filterby": filterby,
                "search_in": search_in,
                "search": search,
            },
            total=tdm_entrevue_count,
            page=page,
            step=self._items_per_page,
        )

        # content according to pager and archive selected
        tdm_entrevues = TdmEntrevue.search(
            domain,
            order=order,
            limit=self._items_per_page,
            offset=pager["offset"],
        )
        request.session["my_tdm_entrevues_history"] = tdm_entrevues.ids[:100]

        values.update(
            {
                "date": date_begin,
                "date_end": date_end,
                "tdm_entrevues": tdm_entrevues,
                "page_name": "tdm_entrevue",
                "archive_groups": archive_groups,
                "default_url": "/my/tdm_entrevues",
                "pager": pager,
                "searchbar_sortings": searchbar_sortings,
                "searchbar_groupby": searchbar_groupby,
                "searchbar_inputs": searchbar_inputs,
                "search_in": search_in,
                "searchbar_filters": OrderedDict(
                    sorted(searchbar_filters.items())
                ),
                "sortby": sortby,
                "filterby": filterby,
            }
        )
        return request.render("tdm.portal_my_tdm_entrevues", values)

    @http.route(
        ["/my/tdm_entrevue/<int:tdm_entrevue_id>"],
        type="http",
        auth="public",
        website=True,
    )
    def portal_my_tdm_entrevue(
        self, tdm_entrevue_id=None, access_token=None, **kw
    ):
        try:
            tdm_entrevue_sudo = self._document_check_access(
                "tdm.entrevue", tdm_entrevue_id, access_token
            )
        except (AccessError, MissingError):
            return request.redirect("/my")

        values = self._tdm_entrevue_get_page_view_values(
            tdm_entrevue_sudo, access_token, **kw
        )
        return request.render("tdm.portal_my_tdm_entrevue", values)

    # ------------------------------------------------------------
    # My Tdm Entrevue Stage
    # ------------------------------------------------------------
    def _tdm_entrevue_stage_get_page_view_values(
        self, tdm_entrevue_stage, access_token, **kwargs
    ):
        values = {
            "page_name": "tdm_entrevue_stage",
            "tdm_entrevue_stage": tdm_entrevue_stage,
            "user": request.env.user,
        }
        return self._get_page_view_values(
            tdm_entrevue_stage,
            access_token,
            values,
            "my_tdm_entrevue_stages_history",
            False,
            **kwargs,
        )

    @http.route(
        ["/my/tdm_entrevue_stages", "/my/tdm_entrevue_stages/page/<int:page>"],
        type="http",
        auth="user",
        website=True,
    )
    def portal_my_tdm_entrevue_stages(
        self,
        page=1,
        date_begin=None,
        date_end=None,
        sortby=None,
        filterby=None,
        search=None,
        search_in="content",
        **kw,
    ):
        values = self._prepare_portal_layout_values()
        TdmEntrevueStage = request.env["tdm.entrevue.stage"]
        domain = []

        searchbar_sortings = {
            "date": {"label": _("Newest"), "order": "create_date desc"},
            "name": {"label": _("Name"), "order": "name"},
        }
        searchbar_filters = {
            "all": {"label": _("All"), "domain": []},
        }
        searchbar_inputs = {}
        searchbar_groupby = {}

        # default sort by value
        if not sortby:
            sortby = "date"
        order = searchbar_sortings[sortby]["order"]
        # default filter by value
        if not filterby:
            filterby = "all"
        domain = searchbar_filters[filterby]["domain"]

        # search
        if search and search_in:
            search_domain = []
            domain += search_domain
        # archive groups - Default Group By 'create_date'
        archive_groups = self._get_archive_groups("tdm.entrevue.stage", domain)
        if date_begin and date_end:
            domain += [
                ("create_date", ">", date_begin),
                ("create_date", "<=", date_end),
            ]
        # tdm_entrevue_stages count
        tdm_entrevue_stage_count = TdmEntrevueStage.search_count(domain)
        # pager
        pager = portal_pager(
            url="/my/tdm_entrevue_stages",
            url_args={
                "date_begin": date_begin,
                "date_end": date_end,
                "sortby": sortby,
                "filterby": filterby,
                "search_in": search_in,
                "search": search,
            },
            total=tdm_entrevue_stage_count,
            page=page,
            step=self._items_per_page,
        )

        # content according to pager and archive selected
        tdm_entrevue_stages = TdmEntrevueStage.search(
            domain,
            order=order,
            limit=self._items_per_page,
            offset=pager["offset"],
        )
        request.session[
            "my_tdm_entrevue_stages_history"
        ] = tdm_entrevue_stages.ids[:100]

        values.update(
            {
                "date": date_begin,
                "date_end": date_end,
                "tdm_entrevue_stages": tdm_entrevue_stages,
                "page_name": "tdm_entrevue_stage",
                "archive_groups": archive_groups,
                "default_url": "/my/tdm_entrevue_stages",
                "pager": pager,
                "searchbar_sortings": searchbar_sortings,
                "searchbar_groupby": searchbar_groupby,
                "searchbar_inputs": searchbar_inputs,
                "search_in": search_in,
                "searchbar_filters": OrderedDict(
                    sorted(searchbar_filters.items())
                ),
                "sortby": sortby,
                "filterby": filterby,
            }
        )
        return request.render("tdm.portal_my_tdm_entrevue_stages", values)

    @http.route(
        ["/my/tdm_entrevue_stage/<int:tdm_entrevue_stage_id>"],
        type="http",
        auth="public",
        website=True,
    )
    def portal_my_tdm_entrevue_stage(
        self, tdm_entrevue_stage_id=None, access_token=None, **kw
    ):
        try:
            tdm_entrevue_stage_sudo = self._document_check_access(
                "tdm.entrevue.stage", tdm_entrevue_stage_id, access_token
            )
        except (AccessError, MissingError):
            return request.redirect("/my")

        values = self._tdm_entrevue_stage_get_page_view_values(
            tdm_entrevue_stage_sudo, access_token, **kw
        )
        return request.render("tdm.portal_my_tdm_entrevue_stage", values)

    # ------------------------------------------------------------
    # My Tdm Offre Emploi
    # ------------------------------------------------------------
    def _tdm_offre_emploi_get_page_view_values(
        self, tdm_offre_emploi, access_token, **kwargs
    ):
        values = {
            "page_name": "tdm_offre_emploi",
            "tdm_offre_emploi": tdm_offre_emploi,
            "user": request.env.user,
        }
        return self._get_page_view_values(
            tdm_offre_emploi,
            access_token,
            values,
            "my_tdm_offre_emplois_history",
            False,
            **kwargs,
        )

    @http.route(
        ["/my/tdm_offre_emplois", "/my/tdm_offre_emplois/page/<int:page>"],
        type="http",
        auth="user",
        website=True,
    )
    def portal_my_tdm_offre_emplois(
        self,
        page=1,
        date_begin=None,
        date_end=None,
        sortby=None,
        filterby=None,
        search=None,
        search_in="content",
        **kw,
    ):
        values = self._prepare_portal_layout_values()
        TdmOffreEmploi = request.env["tdm.offre.emploi"]
        domain = []

        searchbar_sortings = {
            "date": {"label": _("Newest"), "order": "create_date desc"},
            "name": {"label": _("Name"), "order": "name"},
        }
        searchbar_filters = {
            "all": {"label": _("All"), "domain": []},
        }
        searchbar_inputs = {}
        searchbar_groupby = {}

        # default sort by value
        if not sortby:
            sortby = "date"
        order = searchbar_sortings[sortby]["order"]
        # default filter by value
        if not filterby:
            filterby = "all"
        domain = searchbar_filters[filterby]["domain"]

        # search
        if search and search_in:
            search_domain = []
            domain += search_domain
        # archive groups - Default Group By 'create_date'
        archive_groups = self._get_archive_groups("tdm.offre.emploi", domain)
        if date_begin and date_end:
            domain += [
                ("create_date", ">", date_begin),
                ("create_date", "<=", date_end),
            ]
        # tdm_offre_emplois count
        tdm_offre_emploi_count = TdmOffreEmploi.search_count(domain)
        # pager
        pager = portal_pager(
            url="/my/tdm_offre_emplois",
            url_args={
                "date_begin": date_begin,
                "date_end": date_end,
                "sortby": sortby,
                "filterby": filterby,
                "search_in": search_in,
                "search": search,
            },
            total=tdm_offre_emploi_count,
            page=page,
            step=self._items_per_page,
        )

        # content according to pager and archive selected
        tdm_offre_emplois = TdmOffreEmploi.search(
            domain,
            order=order,
            limit=self._items_per_page,
            offset=pager["offset"],
        )
        request.session[
            "my_tdm_offre_emplois_history"
        ] = tdm_offre_emplois.ids[:100]

        values.update(
            {
                "date": date_begin,
                "date_end": date_end,
                "tdm_offre_emplois": tdm_offre_emplois,
                "page_name": "tdm_offre_emploi",
                "archive_groups": archive_groups,
                "default_url": "/my/tdm_offre_emplois",
                "pager": pager,
                "searchbar_sortings": searchbar_sortings,
                "searchbar_groupby": searchbar_groupby,
                "searchbar_inputs": searchbar_inputs,
                "search_in": search_in,
                "searchbar_filters": OrderedDict(
                    sorted(searchbar_filters.items())
                ),
                "sortby": sortby,
                "filterby": filterby,
            }
        )
        return request.render("tdm.portal_my_tdm_offre_emplois", values)

    @http.route(
        ["/my/tdm_offre_emploi/<int:tdm_offre_emploi_id>"],
        type="http",
        auth="public",
        website=True,
    )
    def portal_my_tdm_offre_emploi(
        self, tdm_offre_emploi_id=None, access_token=None, **kw
    ):
        try:
            tdm_offre_emploi_sudo = self._document_check_access(
                "tdm.offre.emploi", tdm_offre_emploi_id, access_token
            )
        except (AccessError, MissingError):
            return request.redirect("/my")

        values = self._tdm_offre_emploi_get_page_view_values(
            tdm_offre_emploi_sudo, access_token, **kw
        )
        return request.render("tdm.portal_my_tdm_offre_emploi", values)

    # ------------------------------------------------------------
    # My Tdm Offre Emploi Applique
    # ------------------------------------------------------------
    def _tdm_offre_emploi_applique_get_page_view_values(
        self, tdm_offre_emploi_applique, access_token, **kwargs
    ):
        values = {
            "page_name": "tdm_offre_emploi_applique",
            "tdm_offre_emploi_applique": tdm_offre_emploi_applique,
            "user": request.env.user,
        }
        return self._get_page_view_values(
            tdm_offre_emploi_applique,
            access_token,
            values,
            "my_tdm_offre_emploi_appliques_history",
            False,
            **kwargs,
        )

    @http.route(
        [
            "/my/tdm_offre_emploi_appliques",
            "/my/tdm_offre_emploi_appliques/page/<int:page>",
        ],
        type="http",
        auth="user",
        website=True,
    )
    def portal_my_tdm_offre_emploi_appliques(
        self,
        page=1,
        date_begin=None,
        date_end=None,
        sortby=None,
        filterby=None,
        search=None,
        search_in="content",
        **kw,
    ):
        values = self._prepare_portal_layout_values()
        TdmOffreEmploiApplique = request.env["tdm.offre.emploi.applique"]
        domain = []

        searchbar_sortings = {
            "date": {"label": _("Newest"), "order": "create_date desc"},
            "name": {"label": _("Name"), "order": "name"},
        }
        searchbar_filters = {
            "all": {"label": _("All"), "domain": []},
        }
        searchbar_inputs = {}
        searchbar_groupby = {}

        # default sort by value
        if not sortby:
            sortby = "date"
        order = searchbar_sortings[sortby]["order"]
        # default filter by value
        if not filterby:
            filterby = "all"
        domain = searchbar_filters[filterby]["domain"]

        # search
        if search and search_in:
            search_domain = []
            domain += search_domain
        # archive groups - Default Group By 'create_date'
        archive_groups = self._get_archive_groups(
            "tdm.offre.emploi.applique", domain
        )
        if date_begin and date_end:
            domain += [
                ("create_date", ">", date_begin),
                ("create_date", "<=", date_end),
            ]
        # tdm_offre_emploi_appliques count
        tdm_offre_emploi_applique_count = TdmOffreEmploiApplique.search_count(
            domain
        )
        # pager
        pager = portal_pager(
            url="/my/tdm_offre_emploi_appliques",
            url_args={
                "date_begin": date_begin,
                "date_end": date_end,
                "sortby": sortby,
                "filterby": filterby,
                "search_in": search_in,
                "search": search,
            },
            total=tdm_offre_emploi_applique_count,
            page=page,
            step=self._items_per_page,
        )

        # content according to pager and archive selected
        tdm_offre_emploi_appliques = TdmOffreEmploiApplique.search(
            domain,
            order=order,
            limit=self._items_per_page,
            offset=pager["offset"],
        )
        request.session[
            "my_tdm_offre_emploi_appliques_history"
        ] = tdm_offre_emploi_appliques.ids[:100]

        values.update(
            {
                "date": date_begin,
                "date_end": date_end,
                "tdm_offre_emploi_appliques": tdm_offre_emploi_appliques,
                "page_name": "tdm_offre_emploi_applique",
                "archive_groups": archive_groups,
                "default_url": "/my/tdm_offre_emploi_appliques",
                "pager": pager,
                "searchbar_sortings": searchbar_sortings,
                "searchbar_groupby": searchbar_groupby,
                "searchbar_inputs": searchbar_inputs,
                "search_in": search_in,
                "searchbar_filters": OrderedDict(
                    sorted(searchbar_filters.items())
                ),
                "sortby": sortby,
                "filterby": filterby,
            }
        )
        return request.render(
            "tdm.portal_my_tdm_offre_emploi_appliques", values
        )

    @http.route(
        ["/my/tdm_offre_emploi_applique/<int:tdm_offre_emploi_applique_id>"],
        type="http",
        auth="public",
        website=True,
    )
    def portal_my_tdm_offre_emploi_applique(
        self, tdm_offre_emploi_applique_id=None, access_token=None, **kw
    ):
        try:
            tdm_offre_emploi_applique_sudo = self._document_check_access(
                "tdm.offre.emploi.applique",
                tdm_offre_emploi_applique_id,
                access_token,
            )
        except (AccessError, MissingError):
            return request.redirect("/my")

        values = self._tdm_offre_emploi_applique_get_page_view_values(
            tdm_offre_emploi_applique_sudo, access_token, **kw
        )
        return request.render(
            "tdm.portal_my_tdm_offre_emploi_applique", values
        )

    # ------------------------------------------------------------
    # My Tdm Offre Emploi Applique Stage
    # ------------------------------------------------------------
    def _tdm_offre_emploi_applique_stage_get_page_view_values(
        self, tdm_offre_emploi_applique_stage, access_token, **kwargs
    ):
        values = {
            "page_name": "tdm_offre_emploi_applique_stage",
            "tdm_offre_emploi_applique_stage": tdm_offre_emploi_applique_stage,
            "user": request.env.user,
        }
        return self._get_page_view_values(
            tdm_offre_emploi_applique_stage,
            access_token,
            values,
            "my_tdm_offre_emploi_applique_stages_history",
            False,
            **kwargs,
        )

    @http.route(
        [
            "/my/tdm_offre_emploi_applique_stages",
            "/my/tdm_offre_emploi_applique_stages/page/<int:page>",
        ],
        type="http",
        auth="user",
        website=True,
    )
    def portal_my_tdm_offre_emploi_applique_stages(
        self,
        page=1,
        date_begin=None,
        date_end=None,
        sortby=None,
        filterby=None,
        search=None,
        search_in="content",
        **kw,
    ):
        values = self._prepare_portal_layout_values()
        TdmOffreEmploiAppliqueStage = request.env[
            "tdm.offre.emploi.applique.stage"
        ]
        domain = []

        searchbar_sortings = {
            "date": {"label": _("Newest"), "order": "create_date desc"},
            "name": {"label": _("Name"), "order": "name"},
        }
        searchbar_filters = {
            "all": {"label": _("All"), "domain": []},
        }
        searchbar_inputs = {}
        searchbar_groupby = {}

        # default sort by value
        if not sortby:
            sortby = "date"
        order = searchbar_sortings[sortby]["order"]
        # default filter by value
        if not filterby:
            filterby = "all"
        domain = searchbar_filters[filterby]["domain"]

        # search
        if search and search_in:
            search_domain = []
            domain += search_domain
        # archive groups - Default Group By 'create_date'
        archive_groups = self._get_archive_groups(
            "tdm.offre.emploi.applique.stage", domain
        )
        if date_begin and date_end:
            domain += [
                ("create_date", ">", date_begin),
                ("create_date", "<=", date_end),
            ]
        # tdm_offre_emploi_applique_stages count
        tdm_offre_emploi_applique_stage_count = (
            TdmOffreEmploiAppliqueStage.search_count(domain)
        )
        # pager
        pager = portal_pager(
            url="/my/tdm_offre_emploi_applique_stages",
            url_args={
                "date_begin": date_begin,
                "date_end": date_end,
                "sortby": sortby,
                "filterby": filterby,
                "search_in": search_in,
                "search": search,
            },
            total=tdm_offre_emploi_applique_stage_count,
            page=page,
            step=self._items_per_page,
        )

        # content according to pager and archive selected
        tdm_offre_emploi_applique_stages = TdmOffreEmploiAppliqueStage.search(
            domain,
            order=order,
            limit=self._items_per_page,
            offset=pager["offset"],
        )
        request.session[
            "my_tdm_offre_emploi_applique_stages_history"
        ] = tdm_offre_emploi_applique_stages.ids[:100]

        values.update(
            {
                "date": date_begin,
                "date_end": date_end,
                "tdm_offre_emploi_applique_stages": tdm_offre_emploi_applique_stages,
                "page_name": "tdm_offre_emploi_applique_stage",
                "archive_groups": archive_groups,
                "default_url": "/my/tdm_offre_emploi_applique_stages",
                "pager": pager,
                "searchbar_sortings": searchbar_sortings,
                "searchbar_groupby": searchbar_groupby,
                "searchbar_inputs": searchbar_inputs,
                "search_in": search_in,
                "searchbar_filters": OrderedDict(
                    sorted(searchbar_filters.items())
                ),
                "sortby": sortby,
                "filterby": filterby,
            }
        )
        return request.render(
            "tdm.portal_my_tdm_offre_emploi_applique_stages", values
        )

    @http.route(
        [
            "/my/tdm_offre_emploi_applique_stage/<int:tdm_offre_emploi_applique_stage_id>"
        ],
        type="http",
        auth="public",
        website=True,
    )
    def portal_my_tdm_offre_emploi_applique_stage(
        self, tdm_offre_emploi_applique_stage_id=None, access_token=None, **kw
    ):
        try:
            tdm_offre_emploi_applique_stage_sudo = self._document_check_access(
                "tdm.offre.emploi.applique.stage",
                tdm_offre_emploi_applique_stage_id,
                access_token,
            )
        except (AccessError, MissingError):
            return request.redirect("/my")

        values = self._tdm_offre_emploi_applique_stage_get_page_view_values(
            tdm_offre_emploi_applique_stage_sudo, access_token, **kw
        )
        return request.render(
            "tdm.portal_my_tdm_offre_emploi_applique_stage", values
        )

    # ------------------------------------------------------------
    # My Tdm Offre Emploi Stage
    # ------------------------------------------------------------
    def _tdm_offre_emploi_stage_get_page_view_values(
        self, tdm_offre_emploi_stage, access_token, **kwargs
    ):
        values = {
            "page_name": "tdm_offre_emploi_stage",
            "tdm_offre_emploi_stage": tdm_offre_emploi_stage,
            "user": request.env.user,
        }
        return self._get_page_view_values(
            tdm_offre_emploi_stage,
            access_token,
            values,
            "my_tdm_offre_emploi_stages_history",
            False,
            **kwargs,
        )

    @http.route(
        [
            "/my/tdm_offre_emploi_stages",
            "/my/tdm_offre_emploi_stages/page/<int:page>",
        ],
        type="http",
        auth="user",
        website=True,
    )
    def portal_my_tdm_offre_emploi_stages(
        self,
        page=1,
        date_begin=None,
        date_end=None,
        sortby=None,
        filterby=None,
        search=None,
        search_in="content",
        **kw,
    ):
        values = self._prepare_portal_layout_values()
        TdmOffreEmploiStage = request.env["tdm.offre.emploi.stage"]
        domain = []

        searchbar_sortings = {
            "date": {"label": _("Newest"), "order": "create_date desc"},
            "name": {"label": _("Name"), "order": "name"},
        }
        searchbar_filters = {
            "all": {"label": _("All"), "domain": []},
        }
        searchbar_inputs = {}
        searchbar_groupby = {}

        # default sort by value
        if not sortby:
            sortby = "date"
        order = searchbar_sortings[sortby]["order"]
        # default filter by value
        if not filterby:
            filterby = "all"
        domain = searchbar_filters[filterby]["domain"]

        # search
        if search and search_in:
            search_domain = []
            domain += search_domain
        # archive groups - Default Group By 'create_date'
        archive_groups = self._get_archive_groups(
            "tdm.offre.emploi.stage", domain
        )
        if date_begin and date_end:
            domain += [
                ("create_date", ">", date_begin),
                ("create_date", "<=", date_end),
            ]
        # tdm_offre_emploi_stages count
        tdm_offre_emploi_stage_count = TdmOffreEmploiStage.search_count(domain)
        # pager
        pager = portal_pager(
            url="/my/tdm_offre_emploi_stages",
            url_args={
                "date_begin": date_begin,
                "date_end": date_end,
                "sortby": sortby,
                "filterby": filterby,
                "search_in": search_in,
                "search": search,
            },
            total=tdm_offre_emploi_stage_count,
            page=page,
            step=self._items_per_page,
        )

        # content according to pager and archive selected
        tdm_offre_emploi_stages = TdmOffreEmploiStage.search(
            domain,
            order=order,
            limit=self._items_per_page,
            offset=pager["offset"],
        )
        request.session[
            "my_tdm_offre_emploi_stages_history"
        ] = tdm_offre_emploi_stages.ids[:100]

        values.update(
            {
                "date": date_begin,
                "date_end": date_end,
                "tdm_offre_emploi_stages": tdm_offre_emploi_stages,
                "page_name": "tdm_offre_emploi_stage",
                "archive_groups": archive_groups,
                "default_url": "/my/tdm_offre_emploi_stages",
                "pager": pager,
                "searchbar_sortings": searchbar_sortings,
                "searchbar_groupby": searchbar_groupby,
                "searchbar_inputs": searchbar_inputs,
                "search_in": search_in,
                "searchbar_filters": OrderedDict(
                    sorted(searchbar_filters.items())
                ),
                "sortby": sortby,
                "filterby": filterby,
            }
        )
        return request.render("tdm.portal_my_tdm_offre_emploi_stages", values)

    @http.route(
        ["/my/tdm_offre_emploi_stage/<int:tdm_offre_emploi_stage_id>"],
        type="http",
        auth="public",
        website=True,
    )
    def portal_my_tdm_offre_emploi_stage(
        self, tdm_offre_emploi_stage_id=None, access_token=None, **kw
    ):
        try:
            tdm_offre_emploi_stage_sudo = self._document_check_access(
                "tdm.offre.emploi.stage",
                tdm_offre_emploi_stage_id,
                access_token,
            )
        except (AccessError, MissingError):
            return request.redirect("/my")

        values = self._tdm_offre_emploi_stage_get_page_view_values(
            tdm_offre_emploi_stage_sudo, access_token, **kw
        )
        return request.render("tdm.portal_my_tdm_offre_emploi_stage", values)

    # ------------------------------------------------------------
    # My Tdm Offre Emploi Type
    # ------------------------------------------------------------
    def _tdm_offre_emploi_type_get_page_view_values(
        self, tdm_offre_emploi_type, access_token, **kwargs
    ):
        values = {
            "page_name": "tdm_offre_emploi_type",
            "tdm_offre_emploi_type": tdm_offre_emploi_type,
            "user": request.env.user,
        }
        return self._get_page_view_values(
            tdm_offre_emploi_type,
            access_token,
            values,
            "my_tdm_offre_emploi_types_history",
            False,
            **kwargs,
        )

    @http.route(
        [
            "/my/tdm_offre_emploi_types",
            "/my/tdm_offre_emploi_types/page/<int:page>",
        ],
        type="http",
        auth="user",
        website=True,
    )
    def portal_my_tdm_offre_emploi_types(
        self,
        page=1,
        date_begin=None,
        date_end=None,
        sortby=None,
        filterby=None,
        search=None,
        search_in="content",
        **kw,
    ):
        values = self._prepare_portal_layout_values()
        TdmOffreEmploiType = request.env["tdm.offre.emploi.type"]
        domain = []

        searchbar_sortings = {
            "date": {"label": _("Newest"), "order": "create_date desc"},
            "name": {"label": _("Name"), "order": "name"},
        }
        searchbar_filters = {
            "all": {"label": _("All"), "domain": []},
        }
        searchbar_inputs = {}
        searchbar_groupby = {}

        # default sort by value
        if not sortby:
            sortby = "date"
        order = searchbar_sortings[sortby]["order"]
        # default filter by value
        if not filterby:
            filterby = "all"
        domain = searchbar_filters[filterby]["domain"]

        # search
        if search and search_in:
            search_domain = []
            domain += search_domain
        # archive groups - Default Group By 'create_date'
        archive_groups = self._get_archive_groups(
            "tdm.offre.emploi.type", domain
        )
        if date_begin and date_end:
            domain += [
                ("create_date", ">", date_begin),
                ("create_date", "<=", date_end),
            ]
        # tdm_offre_emploi_types count
        tdm_offre_emploi_type_count = TdmOffreEmploiType.search_count(domain)
        # pager
        pager = portal_pager(
            url="/my/tdm_offre_emploi_types",
            url_args={
                "date_begin": date_begin,
                "date_end": date_end,
                "sortby": sortby,
                "filterby": filterby,
                "search_in": search_in,
                "search": search,
            },
            total=tdm_offre_emploi_type_count,
            page=page,
            step=self._items_per_page,
        )

        # content according to pager and archive selected
        tdm_offre_emploi_types = TdmOffreEmploiType.search(
            domain,
            order=order,
            limit=self._items_per_page,
            offset=pager["offset"],
        )
        request.session[
            "my_tdm_offre_emploi_types_history"
        ] = tdm_offre_emploi_types.ids[:100]

        values.update(
            {
                "date": date_begin,
                "date_end": date_end,
                "tdm_offre_emploi_types": tdm_offre_emploi_types,
                "page_name": "tdm_offre_emploi_type",
                "archive_groups": archive_groups,
                "default_url": "/my/tdm_offre_emploi_types",
                "pager": pager,
                "searchbar_sortings": searchbar_sortings,
                "searchbar_groupby": searchbar_groupby,
                "searchbar_inputs": searchbar_inputs,
                "search_in": search_in,
                "searchbar_filters": OrderedDict(
                    sorted(searchbar_filters.items())
                ),
                "sortby": sortby,
                "filterby": filterby,
            }
        )
        return request.render("tdm.portal_my_tdm_offre_emploi_types", values)

    @http.route(
        ["/my/tdm_offre_emploi_type/<int:tdm_offre_emploi_type_id>"],
        type="http",
        auth="public",
        website=True,
    )
    def portal_my_tdm_offre_emploi_type(
        self, tdm_offre_emploi_type_id=None, access_token=None, **kw
    ):
        try:
            tdm_offre_emploi_type_sudo = self._document_check_access(
                "tdm.offre.emploi.type", tdm_offre_emploi_type_id, access_token
            )
        except (AccessError, MissingError):
            return request.redirect("/my")

        values = self._tdm_offre_emploi_type_get_page_view_values(
            tdm_offre_emploi_type_sudo, access_token, **kw
        )
        return request.render("tdm.portal_my_tdm_offre_emploi_type", values)

    # ------------------------------------------------------------
    # My Tdm Secteur_Activite
    # ------------------------------------------------------------
    def _tdm_secteur_activite_get_page_view_values(
        self, tdm_secteur_activite, access_token, **kwargs
    ):
        values = {
            "page_name": "tdm_secteur_activite",
            "tdm_secteur_activite": tdm_secteur_activite,
            "user": request.env.user,
        }
        return self._get_page_view_values(
            tdm_secteur_activite,
            access_token,
            values,
            "my_tdm_secteur_activites_history",
            False,
            **kwargs,
        )

    @http.route(
        [
            "/my/tdm_secteur_activites",
            "/my/tdm_secteur_activites/page/<int:page>",
        ],
        type="http",
        auth="user",
        website=True,
    )
    def portal_my_tdm_secteur_activites(
        self,
        page=1,
        date_begin=None,
        date_end=None,
        sortby=None,
        filterby=None,
        search=None,
        search_in="content",
        **kw,
    ):
        values = self._prepare_portal_layout_values()
        TdmSecteurActivite = request.env["tdm.secteur_activite"]
        domain = []

        searchbar_sortings = {
            "date": {"label": _("Newest"), "order": "create_date desc"},
            "name": {"label": _("Name"), "order": "name"},
        }
        searchbar_filters = {
            "all": {"label": _("All"), "domain": []},
        }
        searchbar_inputs = {}
        searchbar_groupby = {}

        # default sort by value
        if not sortby:
            sortby = "date"
        order = searchbar_sortings[sortby]["order"]
        # default filter by value
        if not filterby:
            filterby = "all"
        domain = searchbar_filters[filterby]["domain"]

        # search
        if search and search_in:
            search_domain = []
            domain += search_domain
        # archive groups - Default Group By 'create_date'
        archive_groups = self._get_archive_groups(
            "tdm.secteur_activite", domain
        )
        if date_begin and date_end:
            domain += [
                ("create_date", ">", date_begin),
                ("create_date", "<=", date_end),
            ]
        # tdm_secteur_activites count
        tdm_secteur_activite_count = TdmSecteurActivite.search_count(domain)
        # pager
        pager = portal_pager(
            url="/my/tdm_secteur_activites",
            url_args={
                "date_begin": date_begin,
                "date_end": date_end,
                "sortby": sortby,
                "filterby": filterby,
                "search_in": search_in,
                "search": search,
            },
            total=tdm_secteur_activite_count,
            page=page,
            step=self._items_per_page,
        )

        # content according to pager and archive selected
        tdm_secteur_activites = TdmSecteurActivite.search(
            domain,
            order=order,
            limit=self._items_per_page,
            offset=pager["offset"],
        )
        request.session[
            "my_tdm_secteur_activites_history"
        ] = tdm_secteur_activites.ids[:100]

        values.update(
            {
                "date": date_begin,
                "date_end": date_end,
                "tdm_secteur_activites": tdm_secteur_activites,
                "page_name": "tdm_secteur_activite",
                "archive_groups": archive_groups,
                "default_url": "/my/tdm_secteur_activites",
                "pager": pager,
                "searchbar_sortings": searchbar_sortings,
                "searchbar_groupby": searchbar_groupby,
                "searchbar_inputs": searchbar_inputs,
                "search_in": search_in,
                "searchbar_filters": OrderedDict(
                    sorted(searchbar_filters.items())
                ),
                "sortby": sortby,
                "filterby": filterby,
            }
        )
        return request.render("tdm.portal_my_tdm_secteur_activites", values)

    @http.route(
        ["/my/tdm_secteur_activite/<int:tdm_secteur_activite_id>"],
        type="http",
        auth="public",
        website=True,
    )
    def portal_my_tdm_secteur_activite(
        self, tdm_secteur_activite_id=None, access_token=None, **kw
    ):
        try:
            tdm_secteur_activite_sudo = self._document_check_access(
                "tdm.secteur_activite", tdm_secteur_activite_id, access_token
            )
        except (AccessError, MissingError):
            return request.redirect("/my")

        values = self._tdm_secteur_activite_get_page_view_values(
            tdm_secteur_activite_sudo, access_token, **kw
        )
        return request.render("tdm.portal_my_tdm_secteur_activite", values)
