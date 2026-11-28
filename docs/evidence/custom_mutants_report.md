# Custom mutation operators report

Mutants: 10, killed: 10, survived: 0, score: 100%

| # | Operator | Function | Line | Original code | Result |
|---|---|---|---|---|---|
| 0 | LOCK_NEGATE | transfer_item | 267 | `Admin.is_edit_locked()` | killed |
| 1 | PERMISSION_FLIP | transfer_item | 275 | `not request.user.groups.filter(name='shop_users').exists()` | killed |
| 2 | LIMIT_BOUNDARY | transfer_item | 290 | `transfer_quantity <= 0` | killed |
| 3 | LOCK_NEGATE | submit_transfer_request | 369 | `Admin.is_edit_locked()` | killed |
| 4 | STATE_ORDERED_FLIP | submit_transfer_request | 371 | `ordered=False` | killed |
| 5 | STATE_ORDERED_FLIP | submit_transfer_request | 389 | `ordered=True` | killed |
| 6 | CANCEL_FLAG_FLIP | complete_transfer | 420 | `request.data.get('cancel') == 'true'` | killed |
| 7 | PERMISSION_FLIP | complete_transfer | 430 | `not is_manager` | killed |
| 8 | PERMISSION_FLIP | complete_transfer | 439 | `shop_user != request.user` | killed |
| 9 | LIMIT_BOUNDARY | complete_transfer | 454 | `quantity <= 0` | killed |
