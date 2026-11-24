import logging
from collections import defaultdict

from odoo import models
from odoo.exceptions import UserError, ValidationError
from odoo.fields import Domain

_logger = logging.getLogger(__name__)


class MollieSyncTerminal(models.TransientModel):
    _inherit = "sync.mollie.terminal"

    def sync_now(self):
        """Sync terminals once per unique POS Mollie API key.

        Each key is synced inside its own savepoint so that a failing key
        (invalid credentials, unreachable Mollie, an inactive currency, ...)
        only rolls back its own work and never aborts the other keys. Failures
        are collected and reported afterwards instead of raising immediately.
        """
        pos_configs = self.env["pos.config"].search(
            Domain("mollie_terminal_api_key", "!=", False)
            & Domain("company_id", "in", self.env.companies.ids)
        )

        if not pos_configs:
            raise ValidationError(
                self.env._("Set a Mollie Terminal API key on at least one POS.")
            )

        configs_by_key = defaultdict(lambda: self.env["pos.config"])
        for config in pos_configs:
            configs_by_key[config.mollie_terminal_api_key] |= config

        synced_count = 0
        errors = []
        for api_key, configs in configs_by_key.items():
            try:
                with self.env.cr.savepoint():
                    self.env["mollie.pos.terminal"].with_context(
                        mollie_api_key=api_key
                    )._sync_mollie_terminals()
                synced_count += 1
            except (UserError, ValidationError) as error:
                # Drop the cache of anything rolled back with the savepoint,
                # then keep going with the remaining keys.
                self.env.invalidate_all()
                labels = ", ".join(configs.mapped("name"))
                message = error.args[0] if error.args else str(error)
                _logger.warning(
                    "Mollie terminal sync failed for %s: %s", labels, message
                )
                errors.append((labels, message))

        # Every key failed: nothing to keep, so surface the errors as an error.
        if errors and not synced_count:
            raise ValidationError(
                self.env._(
                    "Terminal sync failed for every configured API key:\n\n%s",
                    "\n".join(f"- {labels}: {message}" for labels, message in errors),
                )
            )

        # Some keys failed while others succeeded: keep the successful ones and
        # report the rest with a non-blocking notification (no rollback).
        if errors:
            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "type": "warning",
                    "title": self.env._("Some Mollie profiles could not be synced"),
                    "message": self.env._(
                        "Synced %(ok)s of %(total)s keys. Failed:\n\n%(errors)s",
                        ok=synced_count,
                        total=synced_count + len(errors),
                        errors="\n".join(
                            f"- {labels}: {message}" for labels, message in errors
                        ),
                    ),
                    "sticky": True,
                },
            }
