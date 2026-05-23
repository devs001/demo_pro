import os
import traceback

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




from dotenv import load_dotenv

# This loads the .env file if you are running locally.
# On Railway, it safely ignores this and uses the dashboard variables.
load_dotenv()

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
    query_string = f"?product_id={PRODUCT_ID}"
    endpoint = "/v2/positions"
    endpoint = endpoint + query_string
    headers  = get_headers("GET", endpoint)
    log.info(" checking any open position")
    try:
        res       = requests.get(BASE_URL + endpoint, headers=headers, timeout=10)
        positions = res.json().get("result", [])
        log.info(f"position found for {PRODUCT_ID} is {positions} and all data {res.json()}")
        if float(positions["size"]) != 0:
            log.info(f" returning position found {positions}")
            return positions
    except Exception as e:
        log.error(f"Position check exception: {e} {traceback.format_exc()}")
    log.info(" found none position retuing none")
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


def cancel_all_orders(product_id=PRODUCT_ID):
    """
    Cancels all open orders (including stop-losses) for the specified product.
    """
    # The query string to target only open orders for our specific coin
    query_string = f"?product_id={product_id}"
    endpoint = "/v2/orders/all"
    full_endpoint = endpoint + query_string
    log.info(f" cancel all orders endpoint_full {full_endpoint} ")
    # We use a DELETE request for this action
    headers = get_headers("DELETE", endpoint)

    log.info(f"Attempting to cancel all open orders for {product_id}...")

    try:
        res = requests.delete(BASE_URL + full_endpoint, headers=headers, timeout=10)
        data = res.json()

        if data.get("success"):
            log.info(f"Successfully cancelled orders: {data}")
            return True
        else:
            log.error(f"Failed to cancel orders. API Response: {data}")
            return False

    except Exception as e:
        log.error(f"Exception during order cancellation: {e}")
        return False

# ============================================================
# SL Price Calculate
# ============================================================
def calculate_sl_price(avg_fill_price, side):
    sl_distance = SL_PIPS * PIP_VALUE  # 25 * 0.0001 = 0.0025
    if side == "buy":
        return round(avg_fill_price - sl_distance, 4)
    else:
        return round(avg_fill_price + sl_distance, 4)


def stop_loss_in_percent(entry_price,entry_side,sl_percent=1.0):

    if entry_side == "buy":
        # Math: Price drops by 2%
        # 1.3567 * (1 - 0.02) = 1.3295
        raw_sl_price = entry_price * (1 - (sl_percent / 100))
        sl_side = "sell" # To close a buy, we must sell

    elif entry_side == "sell":
        # Math: Price goes up by 2% (for short selling)
        raw_sl_price = entry_price * (1 + (sl_percent / 100))
        sl_side = "buy"

    # Round it to 4 decimal places so the exchange accepts it
    sl_price = round(raw_sl_price, 4)
    return sl_price

# ============================================================
# Place Stop-Market SL Order
# ============================================================
def place_sl_order(entry_side, sl_price):
    sl_side  = "sell" if entry_side == "buy" else "buy"
    endpoint = "/v2/orders"
    payload  = json.dumps({
        "product_id"      : PRODUCT_ID,
        "order_type"      : "market_order",         # FIXED: Must be 'market_order'
        "stop_order_type" : "stop_loss_order",      # ADDED: This makes it a Stop Loss
        "side"            : sl_side,
        "size"            : QUANTITY,
        "stop_price"      : str(sl_price),          # Cast to string to prevent JSON float issues
        "reduce_only"     : True
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
        log.warning(f"Unauthorized webhook — wrong or missing secret token {token} WEBHOOK_SECRET {WEBHOOK_SECRET}")
        return False
    return True


def get_pending_stop_orders(product_id=PRODUCT_ID):
    """
    Fetches all open, pending, or untriggered orders for a specific product.
    """
    # 1. Base endpoint for signature
    base_endpoint = "/v2/orders"
    headers = get_headers("GET", base_endpoint)
    # 2. Full URL (Notice we ask for all 3 states just to be safe)
    full_url_path = f"{base_endpoint}?product_id={product_id}&state=open,pending,untriggered"



    try:
        res = requests.get(BASE_URL + full_url_path, headers=headers, timeout=10)
        data = res.json()

        if data.get("success"):
            orders = data.get("result", [])
            if orders:
                log.info(f"Found {len(orders)} pending orders to cancel.")
            else:
                log.info("No pending orders found.")
            return orders
        else:
            log.error(f"Failed to fetch orders: {data}")
            return []

    except Exception as e:
        log.error(f"Exception checking for orders: {e}")
        return []


def cancel_all_orders_order_id(product_id=PRODUCT_ID):
    """
    Guaranteed cancellation: Finds every specific order ID and deletes them one by one.
    """
    log.info(f"Initiating full sweep of all orders for {product_id}...")

    # Step 1: Find all the stubborn orders
    pending_orders = get_pending_stop_orders(product_id)

    if not pending_orders:
        log.info("Order book is already clean.")
        return True

    all_successful = True

    # Step 2: Loop through and kill them by ID
    for order in pending_orders:
        order_id = order.get("id")

        if not order_id:
            continue

        log.info(f"Targeting specific order ID: {order_id}...")

        # Base endpoint for signature
        base_endpoint = "/v2/orders"

        # We pass the specific order ID to delete it
        full_url_path = f"{base_endpoint}?id={order_id}&product_id={product_id}"

        headers = get_headers("DELETE", base_endpoint)

        try:
            res = requests.delete(BASE_URL + full_url_path, headers=headers, timeout=10)
            data = res.json()

            if data.get("success"):
                log.info(f"Successfully killed order ID {order_id}")
            else:
                log.error(f"Failed to kill order ID {order_id}: {data}")
                all_successful = False

        except Exception as e:
            log.error(f"Exception killing order {order_id}: {e}")
            all_successful = False

    return all_successful



# ============================================================
# Start
# ============================================================
if __name__ == "__main__":
    startup_check()
    set_leverage()
