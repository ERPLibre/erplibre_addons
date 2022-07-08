odoo.define('erplibre_snippet_simple_service.widgets', function (require) {
    "use strict";

    var ajax = require("web.ajax");
    var core = require('web.core');
    var widget = require("web_editor.widget");
    var _t = core._t;
    var Dialog = widget.Dialog;
    var options = require('web_editor.snippets.options');
    var sAnimation = require('website.content.snippets.animation');
    var rpc = require('web.rpc');
    var weContext = require("web_editor.context");

    let list_rooms = [];
    let list_users = [];

    var result = $.Deferred(),
        _templates_loaded = ajax.loadXML(
            "/erplibre_snippet_simple_service/static/src/xml/widgets.xml",
            core.qweb
        );
    function available_channels() {
        let _channels_def = $.Deferred()

        rpc.query({
            model: 'sinerkia_jitsi_meet.jitsi_meet',
            method: 'search_read',
            kwargs: {
                fields: [
                    "name",
                    "roomName",
                    "domaineName",
                    "url",
                    "id",
                ],
                context: weContext.get()
            },
        }).then(function (channels_list) {
            console.log("rooms: " + JSON.stringify(channels_list));
            list_rooms = channels_list;

            _channels_def.resolve(channels_list);

        });
        return _channels_def;
    }

    function available_users(meet) {
        let _users_def = $.Deferred()

        rpc.query({
            model: 'sinerkia_jitsi_meet.external_user',
            method: 'search_read',
            kwargs: {
                domain: [
                    ["meet", "=", parseInt(meet)],
                ],
                fields: [
                    "name",
                    "id"
                ]
            },
        }).then(function (users_list) {
            console.log("users: " + JSON.stringify(users_list));

            list_users = users_list;
            _users_def.resolve(users_list);

        });
        return _users_def;
    }

    var ParamsForm = Dialog.extend({
        template: "erplibre_snippet_simple_service.ParamsForm",

        /**
         * Store models info before creating widget
         *
         * @param {Object} parent Widget where this dialog is attached
         * @param {Object} options Dialog creation options
         * @param {Object} rooms rooms list
         * @param {String} chosen Prechosen model
         * @returns {Dialog} New Dialog object
         */
        init: function (parent, options, rooms, chosen) {
            this.chosen = chosen;
            this.rooms = rooms;

            var _options = $.extend({}, {
                title: _t("Form Settings"),
                size: "small",
            }, options);
            return this._super(parent, _options);
        },

        /**
         * Save data
         */
        save: function () {
            this.final_data = this.$("#model").val();
            console.log("save: " + this.final_data);


            available_users(this.final_data).done(function (){
                var usersDialog = new UsersParamsForm(
                    $(".simple_service"), {}, list_users, ""
                );
                usersDialog.open();
            })

            this._super.apply(this, arguments);
        },
    });
    var UsersParamsForm = Dialog.extend({
        template: "erplibre_snippet_simple_service.UsersParamsForm",

        /**
         * Store models info before creating widget
         *
         * @param {Object} parent Widget where this dialog is attached
         * @param {Object} options Dialog creation options
         * @param {Object} users users list
         * @param {String} chosen Prechosen model
         * @returns {Dialog} New Dialog object
         */
        init: function (parent, options, users, chosen) {
            this.chosen = chosen;
            this.users = users;

            var _options = $.extend({}, {
                title: _t("Form Settings"),
                size: "small",
            }, options);

            return this._super(parent, _options);
        },

        /**
         * Save data
         */
        save: function () {
            this.final_data = this.$("#model").val();
            console.log("save: " + this.final_data);

            document.getElementById("message").innerHTML = "Jitsi url: " + this.final_data;


            this._super.apply(this, arguments);
        },
    });


    _templates_loaded.done(function () {
        result.resolve({
            ParamsForm: ParamsForm,
        });
    });

    sAnimation.registry.simple_service = sAnimation.Class.extend({
        selector: '.simple_service',

        /**
         * @override
         */
        start: function () {

            available_channels().done(function (){
                var dialog = new ParamsForm(
                    $(".simple_service"), {}, list_rooms, ""
                );
                dialog.open();
            })


            return $.when(this._super.apply(this, arguments));

        },
    });


});
