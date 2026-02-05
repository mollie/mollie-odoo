
# Mapping of payment method codes to Mollie codes.
PAYMENT_METHODS_MAPPING = {
    'apple_pay': 'applepay',
    'card': 'creditcard',
    'bank_transfer': 'banktransfer',
    'p24': 'przelewy24',
    'sepa_direct_debit': 'directdebit',
}

CAPTURE_METHODS = ['creditcard', 'klarna', 'billie', 'riverty', 'vipps', 'mobilepay']

# Payment methods that do not support partial payments
NON_PARTIAL_PAYMENT_METHODS = ['billie', 'in3', 'klarna', 'riverty', 'voucher']

# Payment methods that require multiple captures
MULTI_CAPTURE_METHODS = ['klarna', 'billie']

# Billing Address Requirement for specific payment methods
BILLING_ADDRESS_REQUIRED_METHODS = ['klarna', 'billie', 'riverty', 'in3']
