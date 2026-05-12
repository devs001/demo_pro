from celery import shared_task
from django.utils import timezone
from datetime import timedelta
from .models import Subscription, Invoice
import logging

logger = logging.getLogger(__name__)

@shared_task
def create_invoice_for_subscription(subscription_id):
    """Create an invoice for a specific subscription"""
    try:
        subscription = Subscription.objects.get(id=subscription_id)

        # Create invoice
        invoice = Invoice.objects.create(
            user=subscription.user,
            subscription=subscription,
            plan=subscription.plan,
            amount=subscription.plan.price,
            due_date=timezone.now() + timedelta(days=7)
        )

        logger.info(f"Created invoice {invoice.invoice_number} for subscription {subscription_id}")
        return f"Invoice {invoice.invoice_number} created successfully"

    except Subscription.DoesNotExist:
        logger.error(f"Subscription {subscription_id} not found")
        return f"Subscription {subscription_id} not found"

@shared_task
def generate_monthly_invoices():
    """Generate invoices for all subscriptions due for billing"""
    today = timezone.now().date()

    # Find subscriptions that need billing today
    subscriptions_due = Subscription.objects.filter(
        status='active',
        next_billing_date__date=today
    )

    invoices_created = 0

    for subscription in subscriptions_due:
        # Check if invoice already exists for this billing cycle
        existing_invoice = Invoice.objects.filter(
            subscription=subscription,
            issue_date__date=today
        ).exists()

        if not existing_invoice:
            create_invoice_for_subscription.delay(str(subscription.id))

            # Update next billing date
            subscription.next_billing_date = subscription.next_billing_date + timedelta(
                days=subscription.plan.billing_cycle_days
            )
            subscription.save()

            invoices_created += 1

    logger.info(f"Generated {invoices_created} invoices")
    return f"Generated {invoices_created} invoices"

@shared_task
def mark_overdue_invoices():
    """Mark invoices as overdue if they're past due date"""
    overdue_invoices = Invoice.objects.filter(
        status='pending',
        due_date__lt=timezone.now()
    )

    count = 0
    for invoice in overdue_invoices:
        invoice.status = 'overdue'
        invoice.save()
        count += 1

        send_payment_reminder.delay(str(invoice.id))

    logger.info(f"Marked {count} invoices as overdue")
    return f"Marked {count} invoices as overdue"

@shared_task
def send_payment_reminder(invoice_id):
    """Send payment reminder for overdue invoice (mock implementation)"""
    try:
        invoice = Invoice.objects.get(id=invoice_id)

        # Mock email sending (in
        print(f"PAYMENT REMINDER EMAIL")
        print(f"To: {invoice.user.email}")
        print(f"Subject: Payment Overdue - Invoice {invoice.invoice_number}")
        print(f"Dear {invoice.user.first_name or invoice.user.username},")
        print(f"Your invoice {invoice.invoice_number} for ${invoice.amount} is overdue.")
        print(f"Please make payment as soon as possible to avoid service interruption.")
        print(f"Due date: {invoice.due_date.strftime('%Y-%m-%d')}")
        print(f"Amount: ${invoice.amount}")
        print("=" * 50)

        logger.info(f"Payment reminder sent for invoice {invoice_id}")
        return f"Payment reminder sent for invoice {invoice_id}"

    except Invoice.DoesNotExist:
        logger.error(f"Invoice {invoice_id} not found")
        return f"Invoice {invoice_id} not found"



"""
Delta Exchange India — XRP Futures Algo Trading Server
=====================================================
Rules implemented:
- Entry: TradingView signal → market order (one trade at a time)
- SL: Average fill price se 25 pips → Stop-Market order
- SL fail: 3 retry → position close
- Exit: TradingView signal → position close (skip if already closed)
- Server restart: existing position detect → SL check → handle
"""

import requests
import hmac
import hashlib
import time
import json
import logging




import os  # Add this import at the top

# ============================================================
# CONFIG — Now pulling from Railway Environment Variables
# ============================================================
# Use os.environ.get('KEY_NAME', 'DEFAULT_VALUE')
API_KEY        = os.environ.get("DELTA_API_KEY")
API_SECRET     = os.environ.get("DELTA_API_SECRET")
WEBHOOK_SECRET = os.environ.get("DELTA_WEBHOOK_SECRET")

# IMPORTANT: Environment variables are ALWAYS strings.
# You must wrap them in int() or float() for numeric values.
PRODUCT_ID  = int(os.environ.get("DELTA_PRODUCT_ID", "0"))
QUANTITY    = int(os.environ.get("DELTA_QUANTITY", "10"))
LEVERAGE    = int(os.environ.get("DELTA_LEVERAGE", "10"))

SL_PIPS     = int(os.environ.get("SL_PIPS", "25"))
PIP_VALUE   = float(os.environ.get("PIP_VALUE", "0.0001"))

# ============================================================
# CONFIG — Sirf yahan change karo
# ============================================================


BASE_URL = "https://api.india.delta.exchange"

# ============================================================
# Logging — har cheez record hogi trading.log mein
# ============================================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[
        logging.FileHandler("trading.log"),
        logging.StreamHandler()
    ]
)
log = logging.getLogger(__name__)


# ============================================================
# Delta Exchange Signature
# ============================================================
def get_headers(method, endpoint, payload=""):
    timestamp = str(int(time.time()))
    message   = method + timestamp + endpoint + payload

    signature = hmac.new(
        API_SECRET.encode(),
        message.encode(),
        hashlib.sha256
    ).hexdigest()

    return {
        "api-key"      : API_KEY,
        "signature"    : signature,
        "timestamp"    : timestamp,
        "Content-Type" : "application/json"
    }


# ============================================================
# Leverage Set — Server start hone pe ek baar
# ============================================================
def set_leverage():
    endpoint = f"/v2/products/{PRODUCT_ID}/orders/leverage"
    payload  = json.dumps({"leverage": LEVERAGE})
    headers  = get_headers("POST", endpoint, payload)

    try:
        res    = requests.post(BASE_URL + endpoint, data=payload, headers=headers, timeout=10)
        result = res.json()
        if result.get("success"):
            log.info(f"Leverage set to {LEVERAGE}x — OK")
        else:
            log.error(f"Leverage set FAILED: {result}")
    except Exception as e:
        log.error(f"Leverage set exception: {e}")


# ============================================================
# Open Position Check
# ============================================================
def get_open_position():
    endpoint = "/v2/positions"
    headers  = get_headers("GET", endpoint)

    try:
        res       = requests.get(BASE_URL + endpoint, headers=headers, timeout=10)
        positions = res.json().get("result", [])

        for pos in positions:
            if pos["product_id"] == PRODUCT_ID and float(pos["size"]) != 0:
                return pos
    except Exception as e:
        log.error(f"Position check exception: {e}")

    return None


# ============================================================
# SL Order Exists Check
# ============================================================
def sl_exists():
    endpoint = "/v2/orders?state=open"
    headers  = get_headers("GET", endpoint)

    try:
        res    = requests.get(BASE_URL + endpoint, headers=headers, timeout=10)
        orders = res.json().get("result", [])

        for order in orders:
            if (order["product_id"] == PRODUCT_ID and
                    order["order_type"] == "stop_market_order"):
                return True
    except Exception as e:
        log.error(f"SL check exception: {e}")

    return False


# ============================================================
# Place Market Order
# ============================================================
def place_market_order(side, size):
    log.info(f"placing order {side} and {size}")
    endpoint = "/v2/orders"
    payload  = json.dumps({
        "product_id" : PRODUCT_ID,
        "order_type" : "market_order",
        "side"       : side,
        "size"       : size
    })
    headers = get_headers("POST", endpoint, payload)
    log.info(f"placing order BASE_URL + endpoint {BASE_URL + endpoint} headers {headers} payload {payload}")
    try:
        res    = requests.post(BASE_URL + endpoint, data=payload, headers=headers, timeout=10)
        result = res.json()
        log.info(f"Market order - {side} {size} lots - Response: {result}")
        return result
    except Exception as e:
        log.error(f"Market order exception: {e}")
        return {"success": False}


# ============================================================
# SL Price Calculate
# ============================================================
def calculate_sl_price(avg_fill_price, side):
    sl_distance = SL_PIPS * PIP_VALUE  # 25 * 0.0001 = 0.0025
    if side == "buy":
        return round(avg_fill_price - sl_distance, 4)
    else:
        return round(avg_fill_price + sl_distance, 4)


# ============================================================
# Place Stop-Market SL Order
# ============================================================
def place_sl_order(entry_side, sl_price):
    sl_side  = "sell" if entry_side == "buy" else "buy"
    endpoint = "/v2/orders"
    payload  = json.dumps({
        "product_id"  : PRODUCT_ID,
        "order_type"  : "stop_market_order",
        "side"        : sl_side,
        "size"        : QUANTITY,
        "stop_price"  : sl_price,
        "reduce_only" : True
    })
    headers = get_headers("POST", endpoint, payload)

    try:
        res    = requests.post(BASE_URL + endpoint, data=payload, headers=headers, timeout=10)
        result = res.json()
        log.info(f"SL order @ {sl_price} | Response: {result}")
        return result
    except Exception as e:
        log.error(f"SL order exception: {e}")
        return {"success": False}


# ============================================================
# SL Place with Retry — Fail pe position close
# ============================================================
def place_sl_with_retry(entry_side, avg_fill_price):
    sl_price = calculate_sl_price(avg_fill_price, entry_side)
    log.info(f"SL price calculated: {sl_price} ({SL_PIPS} pips from {avg_fill_price})")

    for attempt in range(1, 4):
        result = place_sl_order(entry_side, sl_price)
        if result.get("success"):
            log.info(f"SL placed on attempt {attempt}")
            return True
        log.warning(f"SL attempt {attempt}/3 failed")
        if attempt < 3:
            time.sleep(1)

    # 3 baar fail — position close karo
    log.error("SL failed 3 times — closing position via market order")
    close_side = "sell" if entry_side == "buy" else "buy"
    place_market_order(close_side, QUANTITY)
    return False


# ============================================================
# Server Startup Check
# ============================================================
def startup_check():
    log.info("=== Server started — startup check ===")
    position = get_open_position()

    if not position:
        log.info("No open position — ready for signals")
        return

    log.warning(f"Open position detected: size={position['size']} | entry={position['entry_price']}")

    if sl_exists():
        log.info("SL already active — waiting for exit signal")
    else:
        log.warning("No SL found — placing SL now")
        side      = "buy" if float(position["size"]) > 0 else "sell"
        avg_price = float(position["entry_price"])
        place_sl_with_retry(side, avg_price)


# ============================================================
# Webhook Secret Verify
# ============================================================
def verify_webhook(req):
    token = req.headers.get("X-Webhook-Secret")
    if token != WEBHOOK_SECRET:
        log.warning("Unauthorized webhook — wrong or missing secret")
        return False
    return True






# ============================================================
# Start
# ============================================================
if __name__ == "__main__":
    startup_check()
    set_leverage()
