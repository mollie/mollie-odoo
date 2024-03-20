# -*- coding: utf-8 -*-
import logging

_logger = logging.getLogger(__name__)


# -----------------------------------------------------------------
# Rename the fields based new terminology "acquirer" -> "provider"
# -----------------------------------------------------------------

def migrate(cr, version):

    cr.execute("""
        DO $$
        BEGIN
        IF EXISTS(SELECT *
            FROM information_schema.columns
            WHERE table_name='mollie_payment_method' and column_name='acquirer_id')
        THEN
            ALTER TABLE "mollie_payment_method" RENAME COLUMN "acquirer_id" TO "provider_id";
        END IF;
        END $$;
    """)
    _logger.info("Renamed field acquirer_id -> provider_id (mollie.payment.method)")

    cr.execute("""
        DO $$
        BEGIN
        IF EXISTS(SELECT *
            FROM information_schema.columns
            WHERE table_name='mollie_payment_method_issuer' and column_name='acquirer_id')
        THEN
            ALTER TABLE "mollie_payment_method_issuer" RENAME COLUMN "acquirer_id" TO "provider_id";
        END IF;
        END $$;
    """)
    _logger.info("Renamed field acquirer_id -> provider_id (mollie.payment.method.issuer)")
