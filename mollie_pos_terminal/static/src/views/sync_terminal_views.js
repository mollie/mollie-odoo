odoo.define('mollie.terminal.tree', function (require) {
    "use strict";
    var ListController = require('web.ListController');
    var ListView = require('web.ListView');

    var viewRegistry = require('web.view_registry');

    function renderSyncTerminalButton() {
        if (this.$buttons) {
            var self = this;
            this.$buttons.on('click', '.o_button_sync_terminal', function () {
                self.do_action({
                    name: 'Sync Terminal',
                    type: 'ir.actions.act_window',
                    res_model: 'sync.mollie.terminal',
                    target: 'new',
                    views: [[false, 'form']],
                    context: { 'is_modal': true},
                }, {
                    on_close: function () {
                        self.update({}, { reload: true });
                    }
                });
            });
        }
    }

    var SyncMollieTerminalController = ListController.extend({
        willStart: function () {
            this.buttons_template = 'SyncMollieTerminalView.buttons';
            return this._super.apply(this, arguments);
        },
        renderButtons: function () {
            this._super.apply(this, arguments);
            renderSyncTerminalButton.apply(this, arguments);
        }
    });


    var SyncMollieTerminalView = ListView.extend({
        config: _.extend({}, ListView.prototype.config, {
            Controller: SyncMollieTerminalController,
        }),
    });

    viewRegistry.add('mollie_sync_terminal_tree', SyncMollieTerminalView);
});
