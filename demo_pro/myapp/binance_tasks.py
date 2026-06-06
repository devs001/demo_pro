"""
Binance Futures (USDT-M) — XRP Algo Trading
=============================================
Environment variables:
  BINANCE_API_KEY          — Futures API key
  BINANCE_API_SECRET       — Futures API secret (HMAC SHA256 signing)
  BINANCE_WEBHOOK_SECRET   — X-Webhook-Secret header value (same pattern as Delta)
  BINANCE_SYMBOL           — e.g. XRPUSDT (default: XRPUSDT)
  BINANCE_QUANTITY         — order size in base asset (default: 10)
  BINANCE_LEVERAGE         — leverage multiplier (default: 10)
  SL_PIPS                  — stop distance in pips when SL_PERCENT unset (default: 25)
  PIP_VALUE                — price per pip (default: 0.0001)
  SL_PERCENT               — if > 0, SL distance as % of entry instead of pips
  EXCHANGE_BROKER          — set via broker.py; not read here directly

Optional:
  BINANCE_BASE_URL         — override API base (default: https://fapi.binance.com)
  BINANCE_RECV_WINDOW      — recvWindow ms (default: 5000)
"""

import hashlib
import hmac
import json
import logging
import os
import time
import traceback
from urllib.parse import urlencode

import requests
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.environ.get("BINANCE_API_KEY")
API_SECRET = os.environ.get("BINANCE_API_SECRET")
WEBHOOK_SECRET = os.environ.get("BINANCE_WEBHOOK_SECRET")

SYMBOL = os.environ.get("BINANCE_SYMBOL", "XRPUSDT")
QUANTITY = float(os.environ.get("BINANCE_QUANTITY", "10"))
LEVERAGE = int(os.environ.get("BINANCE_LEVERAGE", "10"))

SL_PIPS = int(os.environ.get("SL_PIPS", "25"))
PIP_VALUE = float(os.environ.get("PIP_VALUE", "0.0001"))
SL_PERCENT = float(os.environ.get("SL_PERCENT", "0") or "0")

BASE_URL = os.environ.get("BINANCE_BASE_URL", "https://fapi.binance.com")
RECV_WINDOW = int(os.environ.get("BINANCE_RECV_WINDOW", "5000"))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[
        logging.FileHandler("trading.log"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger(__name__)

_symbol_filters = None


def _sign_params(params):
    query = urlencode(params)
    signature = hmac.new(
        API_SECRET.encode("utf-8"),
        query.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    params["signature"] = signature
    return params


def _request(method, endpoint, params=None):
    params = dict(params or {})
    params["timestamp"] = int(time.time() * 1000)
    params["recvWindow"] = RECV_WINDOW
    signed = _sign_params(params)
    headers = {"X-MBX-APIKEY": API_KEY}
    url = BASE_URL + endpoint

    try:
        if method == "GET":
            res = requests.get(url, params=signed, headers=headers, timeout=10)
        elif method == "POST":
            res = requests.post(url, params=signed, headers=headers, timeout=10)
        elif method == "DELETE":
            res = requests.delete(url, params=signed, headers=headers, timeout=10)
        else:
            raise ValueError(f"Unsupported HTTP method: {method}")

        data = res.json()
        if res.status_code >= 400:
            log.error(f"Binance API error {res.status_code}: {data}")
            return {"success": False, "error": data}
        return {"success": True, "result": data}
    except Exception as exc:
        log.error(f"Binance request exception: {exc} {traceback.format_exc()}")
        return {"success": False, "error": str(exc)}


def _load_symbol_filters():
    global _symbol_filters
    if _symbol_filters is not None:
        return _symbol_filters

    try:
        res = requests.get(f"{BASE_URL}/fapi/v1/exchangeInfo", timeout=10)
        info = res.json()
        for sym in info.get("symbols", []):
            if sym.get("symbol") == SYMBOL:
                filters = {f["filterType"]: f for f in sym.get("filters", [])}
                _symbol_filters = filters
                return _symbol_filters
    except Exception as exc:
        log.warning(f"Could not load exchange info: {exc}")

    _symbol_filters = {}
    return _symbol_filters


def _round_price(price):
    filters = _load_symbol_filters()
    tick = filters.get("PRICE_FILTER", {}).get("tickSize", "0.0001")
    tick_f = float(tick)
    if tick_f <= 0:
        return round(price, 4)
    precision = max(0, len(tick.rstrip("0").split(".")[-1]) if "." in tick else 0)
    rounded = round(round(price / tick_f) * tick_f, precision)
    return float(f"{rounded:.{precision}f}")


def _format_quantity(qty):
    filters = _load_symbol_filters()
    step = filters.get("LOT_SIZE", {}).get("stepSize", "1")
    step_f = float(step)
    if step_f <= 0:
        return str(int(qty) if qty == int(qty) else qty)
    precision = max(0, len(step.rstrip("0").split(".")[-1]) if "." in step else 0)
    rounded = round(round(float(qty) / step_f) * step_f, precision)
    if precision == 0:
        return str(int(rounded))
    return f"{rounded:.{precision}f}"


def set_leverage():
    result = _request(
        "POST",
        "/fapi/v1/leverage",
        {"symbol": SYMBOL, "leverage": LEVERAGE},
    )
    if result.get("success"):
        log.info(f"Leverage set to {LEVERAGE}x on {SYMBOL} — OK")
    else:
        log.error(f"Leverage set FAILED: {result}")


def get_open_position():
    log.info("checking any open position")
    try:
        result = _request("GET", "/fapi/v2/positionRisk", {"symbol": SYMBOL})
        if not result.get("success"):
            log.error(f"Position check failed: {result}")
            return None

        positions = result["result"]
        if isinstance(positions, dict):
            positions = [positions]

        for pos in positions:
            if pos.get("symbol") != SYMBOL:
                continue
            amt = float(pos.get("positionAmt", 0))
            if amt != 0:
                mapped = {
                    "size": amt,
                    "entry_price": pos.get("entryPrice", "0"),
                    "symbol": SYMBOL,
                    "_raw": pos,
                }
                log.info(f"position found for {SYMBOL}: {mapped}")
                return mapped
    except Exception as exc:
        log.error(f"Position check exception: {exc} {traceback.format_exc()}")

    log.info("found none position returning none")
    return None


def sl_exists():
    try:
        result = _request("GET", "/fapi/v1/openOrders", {"symbol": SYMBOL})
        if not result.get("success"):
            return False

        for order in result["result"]:
            if order.get("type") in ("STOP_MARKET", "STOP"):
                return True
    except Exception as exc:
        log.error(f"SL check exception: {exc}")

    return False


def _is_close_order(side):
    position = get_open_position()
    if not position:
        return False
    amt = float(position["size"])
    return (amt > 0 and side == "sell") or (amt < 0 and side == "buy")


def _normalize_side(side):
    return "BUY" if side.lower() == "buy" else "SELL"


def place_market_order(side, size):
    log.info(f"placing order {side} and {size}")
    params = {
        "symbol": SYMBOL,
        "side": _normalize_side(side),
        "type": "MARKET",
        "quantity": _format_quantity(size),
    }
    if _is_close_order(side):
        params["reduceOnly"] = "true"

    try:
        result = _request("POST", "/fapi/v1/order", params)
        if not result.get("success"):
            log.error(f"Market order failed: {result}")
            return {"success": False, "result": result.get("error")}

        order = result["result"]
        avg_price = float(order.get("avgPrice") or 0)

        if avg_price <= 0:
            order_id = order.get("orderId")
            if order_id:
                detail = _request(
                    "GET",
                    "/fapi/v1/order",
                    {"symbol": SYMBOL, "orderId": order_id},
                )
                if detail.get("success"):
                    avg_price = float(detail["result"].get("avgPrice") or 0)

        if avg_price <= 0:
            trades = _request("GET", "/fapi/v1/userTrades", {"symbol": SYMBOL, "limit": 5})
            if trades.get("success") and trades["result"]:
                last = trades["result"][-1]
                avg_price = float(last.get("price", 0))

        log.info(f"Market order - {side} {size} — avg fill: {avg_price}")
        return {
            "success": True,
            "result": {
                "average_fill_price": avg_price,
                "order_id": order.get("orderId"),
                "_raw": order,
            },
        }
    except Exception as exc:
        log.error(f"Market order exception: {exc}")
        return {"success": False}


def cancel_all_orders(product_id=None):
    """Cancel all open orders for configured symbol (product_id ignored, Delta compat)."""
    log.info(f"cancel all orders for {SYMBOL}")
    try:
        result = _request("DELETE", "/fapi/v1/allOpenOrders", {"symbol": SYMBOL})
        if result.get("success"):
            log.info(f"Successfully cancelled all orders for {SYMBOL}")
            return True
        log.error(f"Failed to cancel orders: {result}")
        return False
    except Exception as exc:
        log.error(f"Exception during order cancellation: {exc}")
        return False


def get_pending_stop_orders(product_id=None):
    try:
        result = _request("GET", "/fapi/v1/openOrders", {"symbol": SYMBOL})
        if result.get("success"):
            orders = result["result"]
            if orders:
                log.info(f"Found {len(orders)} pending orders to cancel.")
            else:
                log.info("No pending orders found.")
            return orders
        log.error(f"Failed to fetch orders: {result}")
        return []
    except Exception as exc:
        log.error(f"Exception checking for orders: {exc}")
        return []


def cancel_all_orders_order_id(product_id=None):
    log.info(f"Initiating full sweep of all orders for {SYMBOL}...")
    pending_orders = get_pending_stop_orders()

    if not pending_orders:
        log.info("Order book is already clean.")
        return True

    all_successful = True
    for order in pending_orders:
        order_id = order.get("orderId")
        if not order_id:
            continue

        log.info(f"Targeting specific order ID: {order_id}...")
        try:
            result = _request(
                "DELETE",
                "/fapi/v1/order",
                {"symbol": SYMBOL, "orderId": order_id},
            )
            if result.get("success"):
                log.info(f"Successfully killed order ID {order_id}")
            else:
                log.error(f"Failed to kill order ID {order_id}: {result}")
                all_successful = False
        except Exception as exc:
            log.error(f"Exception killing order {order_id}: {exc}")
            all_successful = False

    return all_successful


def calculate_sl_price(avg_fill_price, side):
    if SL_PERCENT > 0:
        return stop_loss_in_percent(avg_fill_price, side, SL_PERCENT)

    sl_distance = SL_PIPS * PIP_VALUE
    if side == "buy":
        return _round_price(avg_fill_price - sl_distance)
    return _round_price(avg_fill_price + sl_distance)


def stop_loss_in_percent(entry_price, entry_side, sl_percent=1.0):
    if entry_side == "buy":
        raw_sl_price = entry_price * (1 - (sl_percent / 100))
    elif entry_side == "sell":
        raw_sl_price = entry_price * (1 + (sl_percent / 100))
    else:
        raise ValueError(f"Invalid entry side: {entry_side}")
    return _round_price(raw_sl_price)


def place_sl_order(entry_side, sl_price):
    sl_side = "sell" if entry_side == "buy" else "buy"
    params = {
        "symbol": SYMBOL,
        "side": _normalize_side(sl_side),
        "type": "STOP_MARKET",
        "stopPrice": str(_round_price(sl_price)),
        "quantity": _format_quantity(QUANTITY),
        "reduceOnly": "true",
        "workingType": "CONTRACT_PRICE",
    }

    try:
        result = _request("POST", "/fapi/v1/order", params)
        if result.get("success"):
            log.info(f"SL order @ {sl_price} | Response: {result['result']}")
            return {"success": True, "result": result["result"]}
        log.error(f"SL order failed: {result}")
        return {"success": False, "result": result.get("error")}
    except Exception as exc:
        log.error(f"SL order exception: {exc}")
        return {"success": False}


def place_sl_with_retry(entry_side, avg_fill_price):
    sl_price = calculate_sl_price(avg_fill_price, entry_side)
    mode = f"{SL_PERCENT}%" if SL_PERCENT > 0 else f"{SL_PIPS} pips"
    log.info(f"SL price calculated: {sl_price} ({mode} from {avg_fill_price})")

    for attempt in range(1, 4):
        result = place_sl_order(entry_side, sl_price)
        if result.get("success"):
            log.info(f"SL placed on attempt {attempt}")
            return True
        log.warning(f"SL attempt {attempt}/3 failed")
        if attempt < 3:
            time.sleep(1)

    log.error("SL failed 3 times — closing position via market order")
    close_side = "sell" if entry_side == "buy" else "buy"
    place_market_order(close_side, QUANTITY)
    return False


def startup_check():
    log.info("=== Server started — startup check (Binance) ===")
    _load_symbol_filters()
    position = get_open_position()

    if not position:
        log.info("No open position — ready for signals")
        return

    log.warning(
        f"Open position detected: size={position['size']} | entry={position['entry_price']}"
    )

    if sl_exists():
        log.info("SL already active — waiting for exit signal")
    else:
        log.warning("No SL found — placing SL now")
        side = "buy" if float(position["size"]) > 0 else "sell"
        avg_price = float(position["entry_price"])
        place_sl_with_retry(side, avg_price)


def verify_webhook(req):
    token = req.headers.get("X-Webhook-Secret")
    if token != WEBHOOK_SECRET:
        log.warning(
            f"Unauthorized webhook — wrong or missing secret token {token} "
            f"WEBHOOK_SECRET configured={'yes' if WEBHOOK_SECRET else 'no'}"
        )
        return False
    return True


if __name__ == "__main__":
    startup_check()
    set_leverage()
