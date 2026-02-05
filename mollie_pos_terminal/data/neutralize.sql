UPDATE mollie_pos_terminal
   SET status = 'inactive';
UPDATE res_company
   SET mollie_terminal_api_key = NULL;
UPDATE pos_payment_method
   SET mollie_pos_terminal_id = NULL;
