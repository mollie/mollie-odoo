def post_init_hook(env):
    companies = env["res.company"].search([])
    for company in companies:
        if company.mollie_terminal_api_key:
            pos_configs = env["pos.config"].search([("company_id", "=", company.id)])
            pos_configs.write(
                {
                    "mollie_terminal_api_key": company.mollie_terminal_api_key,
                }
            )
