odoo.define('drgl.payment_info.widget', function (require) {
"use strict";

    var AbstractField = require('web.AbstractField');
    var fieldRegistry = require('web.field_registry');
    var Dialog = require('web.Dialog');
    var core = require('web.core');

    var QWeb = core.qweb;


    var PaymentInfo = AbstractField.extend({

        events: _.extend({
            'click .d_more_info': '_onClickInfo',
        }, AbstractField.prototype.events),

        _renderReadonly: function () {
            this._super();
            this.$el.append('<button type="button" class="btn btn-sm fa fa-info d_more_info" title="Info"></button>');
        },
        _onClickInfo: function (ev) {
            ev.stopPropagation();
            ev.preventDefault();
            var self = this;
            debugger;
            if (this.value) {
                var data = JSON.parse(this.value);
                var journal_id = this.recordData.journal_id && this.recordData.journal_id.res_id;
                if (data.mollie_order_id && journal_id) {
                    this._rpc({
                        route: '/get_mollie_order_info',
                        params: {
                            order_id: data.mollie_order_id,
                            journal_id: journal_id
                        },
                    }).then(function (result) {
                        self._openDialog(result);
                    });
                } else {
                    this._openDialog(data);
                }
            }
        },
        _openDialog: function (data) {
            function formatCamelCase(text) {
                var result = text.replace(/([A-Z])/g, " $1");
                return result.charAt(0).toUpperCase() + result.slice(1);
            }
            var dialog = new Dialog(this, {
                title: "Info",
                $content: QWeb.render('drg_payment_info', {
                    'data': data,
                    'formatCamelCase': formatCamelCase
                })
            });
            dialog.open();
        }
    });

    fieldRegistry.add('payment_info', PaymentInfo);

});
