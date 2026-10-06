# Advanced MoMo - Module Summary

**MoMo QR Payment integration for Odoo 18 Point of Sale**

- **Version**: 0.2
- **Author**: Magenest
- **Category**: Point of Sale
- **Dependencies**: `base`, `point_of_sale`, `loyalty`

---

## Overview

The `advanced_momo` module integrates MoMo e-wallet payments into Odoo 18 POS. Cashiers can select MoMo as a payment method, a QR code is displayed for the customer to scan with the MoMo app, and the system automatically confirms payment via webhook (IPN) callback.

---

## Module Structure

```
advanced_momo/
├── __manifest__.py
├── __init__.py
├── controllers/
│   └── controllers.py            # HTTP endpoints (webhook, create payment, check status)
├── models/
│   ├── momo_transaction.py       # Core transaction model & MoMo API logic
│   ├── pos_payment_method_inherit.py  # Payment method config extension
│   ├── res_config_settings_inherit.py # Global MoMo settings
│   ├── loyalty_program_inherit.py     # Loyalty program customization
│   └── res_partner_inherit.py         # Customer loyalty points display
├── views/
│   ├── momo_transaction_views.xml     # Transaction list/form + menu
│   ├── pos_payment_method_views.xml   # Payment method MoMo fields
│   ├── res_config_settings_views.xml  # Settings UI
│   └── loyalty_program_inherit.xml    # Loyalty form tweak
├── static/src/app/
│   ├── momo_payment.js           # POS payment interface (PaymentMomo)
│   ├── momo_qr_popup.js          # QR popup with polling (MomoQRPopup)
│   └── momo_qr_popup.xml         # QR popup OWL template
├── data/
│   └── sequence.xml              # Transaction auto-numbering sequence
├── security/
│   └── ir.model.access.csv       # Access rights (POS user/manager)
└── test/
    └── test_signature.py         # Signature generation test utility
```

---

## Models

### `momo.transaction`
Core model that tracks all MoMo payment requests and responses.

**Key Fields**:
| Field | Type | Description |
|-------|------|-------------|
| `name` | Char | Auto-generated ID (e.g., `momo_20260217153045_0001`) |
| `request_id` | Char | UUID for MoMo API request |
| `amount` | Float | Payment amount |
| `qr_code_url` | Char | MoMo QR code image URL |
| `result_code` | Integer | MoMo response code (0 = success) |
| `trans_id` | Char | MoMo transaction ID |
| `state` | Selection | `draft` / `pending` / `done` / `failed` / `cancelled` |
| `pos_order_name` | Char | POS order reference |
| `callback_data` | Text | Raw IPN callback JSON |

**Key Methods**:
- `create_momo_payment()` - Builds payload, signs with HMAC-SHA256, calls MoMo API, generates QR code
- `check_transaction_status()` - Returns current state for frontend polling
- `generate_signature()` - HMAC-SHA256 signing with ordered fields
- `verify_callback_signature()` - Validates IPN webhook integrity

**MoMo API Endpoints**:
- Test: `https://test-payment.momo.vn/v2/gateway/api/create`
- Production: `https://payment.momo.vn/v2/gateway/api/create`

### `pos.payment.method` (inherited)
Extends POS payment methods with MoMo-specific configuration fields.

| Field | Description |
|-------|-------------|
| `momo_partner_code` | MoMo Partner Code (optional override) |
| `momo_access_key` | API Access Key (optional override) |
| `momo_secret_key` | API Secret Key (optional override) |
| `momo_environment` | `test` or `production` (optional override) |
| `momo_ipn_url` | IPN webhook base URL (optional override) |

Config resolution: Payment method level values take priority over global Settings.

### `res.config.settings` (inherited)
Global MoMo configuration under Settings > System > MoMo. Same 5 fields as above, stored as `ir.config_parameter`.

### `res.partner` (inherited)
Adds computed `points` field that sums active loyalty card points for each customer.

### `loyalty.program` (inherited)
Sets `program_type` default to `'loyalty'` and makes it readonly.

---

## Controllers (API Endpoints)

### `POST /api/momo/call_back_data` (Public, CSRF disabled)
**MoMo IPN Webhook** - Receives payment notifications from MoMo servers.
- Finds transaction by `orderId`
- Verifies HMAC-SHA256 signature
- Updates transaction state: `resultCode == 0` → `done`, otherwise → `failed`
- Logs all callback data to `ir.logging`

### `POST /api/momo/create_payment` (Auth: user)
**Create Payment** - Called by POS frontend to initiate a MoMo payment.
- Params: `payment_method_id`, `amount`, `order_name`, `session_id`
- Validates config, calls `create_momo_payment()`, returns QR code base64

### `POST /api/momo/check_status` (Auth: user)
**Status Polling** - Called by frontend every 3 seconds to check payment state.
- Params: `transaction_id`
- Returns: `state`, `trans_id`, `message`, `result_code`

---

## POS Frontend (JavaScript/OWL)

### `PaymentMomo` (extends `PaymentInterface`)
Registers `'momo'` as a POS payment terminal type.
- On payment request: calls `/api/momo/create_payment`, then shows QR popup
- On success: sets `transaction_id` and `card_type` on payment line

### `MomoQRPopup` (extends `ConfirmationDialog`)
Displays QR code and polls for payment confirmation.
- **Polling interval**: 3 seconds
- **Timeout**: 5 minutes (300 seconds)
- **States**: `waiting` → `success` / `failed` / `timeout`
- Auto-confirms after 1.5 seconds on success
- Shows countdown timer in `MM:SS` format

**UI States**:
- **Waiting**: QR image (220x220, pink border), spinner, countdown
- **Success**: Green check icon, "Payment Successful!"
- **Failed**: Red X icon, error message
- **Timeout**: Orange clock icon, "Payment Timed Out"

---

## Security (Access Rights)

| Role | Read | Write | Create | Delete |
|------|------|-------|--------|--------|
| POS User | Yes | Yes | Yes | No |
| POS Manager | Yes | Yes | Yes | Yes |

---

## Configuration

### Global Settings (Settings > System > MoMo)
1. **Partner Code** - MoMo merchant code
2. **Access Key** - API access key
3. **Secret Key** - API secret key
4. **Environment** - `test` or `production`
5. **IPN Base URL** - Webhook URL (defaults to `web.base.url`)

### Per Payment Method Override
Each POS payment method can override the global settings with its own MoMo credentials, allowing multi-merchant configurations.

---

## Payment Flow

```
┌─────────┐     ┌──────────┐     ┌──────────┐     ┌──────┐
│ POS UI  │     │  Backend │     │ MoMo API │     │ User │
└────┬────┘     └────┬─────┘     └────┬─────┘     └──┬───┘
     │               │                │               │
     │ create_payment │                │               │
     │──────────────>│ sign & POST    │               │
     │               │───────────────>│               │
     │               │   QR + URLs    │               │
     │               │<───────────────│               │
     │  qr_base64    │                │               │
     │<──────────────│                │               │
     │               │                │               │
     │ Show QR popup │                │    Scan QR    │
     │───────────────────────────────────────────────>│
     │               │                │               │
     │               │                │    Pay        │
     │               │                │<──────────────│
     │               │   IPN callback │               │
     │               │<───────────────│               │
     │               │ verify & update│               │
     │               │   state=done   │               │
     │               │                │               │
     │ poll status   │                │               │
     │──────────────>│                │               │
     │  state=done   │                │               │
     │<──────────────│                │               │
     │               │                │               │
     │ Payment OK!   │                │               │
     │               │                │               │
```

1. Cashier selects MoMo payment in POS
2. Frontend calls `/api/momo/create_payment`
3. Backend signs payload (HMAC-SHA256), calls MoMo API
4. MoMo returns QR code URL, backend generates QR image
5. Frontend displays QR popup with countdown (5 min)
6. Customer scans QR and pays via MoMo app
7. MoMo sends IPN to `/api/momo/call_back_data`
8. Backend verifies signature and updates transaction to `done`
9. Frontend polling detects `done` state, auto-confirms payment

---

## Transaction Sequence

Transactions are auto-numbered with the pattern:
```
momo_{YYYYMMDD}{HHMMSS}_{NNNN}
```
Example: `momo_20260217153045_0001`

Sequences reset daily (date range enabled, 4-digit padding).
