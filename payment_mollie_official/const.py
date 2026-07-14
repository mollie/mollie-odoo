
# Mapping of payment method codes to Mollie codes.
# NOTE: The mapping for KBC/CBC is avoided due to the issuer display logic.
PAYMENT_METHODS_MAPPING = {
    'apple_pay': 'applepay',
    'card': 'creditcard',
    'bank_transfer': 'banktransfer',
    'p24': 'przelewy24',
    'sepa_direct_debit': 'directdebit',
    'afterpay_riverty': 'riverty'
}

CAPTURE_METHODS = ['creditcard', 'klarna', 'billie', 'riverty', 'vipps', 'mobilepay']

# Payment methods that do not support partial payments
NON_PARTIAL_PAYMENT_METHODS = ['billie', 'in3', 'klarna', 'riverty', 'voucher']

# Payment methods that require multiple captures
MULTI_CAPTURE_METHODS = ['klarna', 'billie']

# Billing Address Requirement for specific payment methods
BILLING_ADDRESS_REQUIRED_METHODS = ['klarna', 'billie', 'riverty', 'in3']

# TODO: Develop logic to include the 'bacs' method for mandate support, as it requires a 0.00 amount for the first payment.
# Payment methods that support mandate payments
MANDATE_METHODS = ['card', 'paypal', 'belfius', 'bancontact', 'eps', 'ideal', 'kbc', 'paybybank', 'trustly']
