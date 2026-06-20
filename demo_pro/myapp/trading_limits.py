"""
Per-hour buy-call throttling for the webhook trading flow.

Rules (confirmed):
  - Only BUY entries are limited. SELL / flip / exit are never blocked
    (they still log the current buy count before executing).
  - A buy counts toward the quota only when the market order FILLED.
    Ignored / duplicate / failed buys do not consume the quota.
  - The window is rolling (default: last 60 minutes from "now").
  - State is persisted in the BuyCall table so it survives restarts/deploys.

Config (env-overridable, mirrors the os.environ pattern used elsewhere):
  MAX_BUYS_PER_HOUR   — max successful buys allowed per window (default: 2)
  BUY_WINDOW_MINUTES  — rolling window length in minutes (default: 60)
"""

import logging
import os
from datetime import timedelta

from django.utils import timezone

from .models import BuyCall

log = logging.getLogger(__name__)

MAX_BUYS_PER_HOUR = int(os.environ.get("MAX_BUYS_PER_HOUR", "2"))
WINDOW_MINUTES = int(os.environ.get("BUY_WINDOW_MINUTES", "60"))


def _symbol():
    """Active trading symbol from the broker facade (Binance or Delta)."""
    # Imported lazily so this module can be loaded during migrations
    # before the broker package is fully initialised.
    try:
        from .broker import SYMBOL
        return SYMBOL
    except Exception:
        return None


def count_recent_buys():
    """Number of successful buys recorded in the current rolling window."""
    cutoff = timezone.now() - timedelta(minutes=WINDOW_MINUTES)
    qs = BuyCall.objects.filter(created_at__gte=cutoff)
    symbol = _symbol()
    if symbol:
        qs = qs.filter(symbol=symbol)
    return qs.count()


def can_place_buy():
    """True if we are still allowed to place another buy this window."""
    return count_recent_buys() < MAX_BUYS_PER_HOUR


def record_buy(side, quantity, fill_price=None, order_id=""):
    """
    Persist a successfully filled BUY entry. Called only after the market
    order has filled, so failures never consume the quota.
    """
    if str(side).lower() != "buy":
        return None
    try:
        return BuyCall.objects.create(
            symbol=_symbol() or "",
            quantity=quantity,
            fill_price=fill_price,
            order_id=str(order_id or ""),
        )
    except Exception as exc:
        # Throttling must never break order placement — just log.
        log.error(f"Failed to record buy call: {exc}")
        return None
