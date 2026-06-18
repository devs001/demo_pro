"""
Broker facade — switch between Binance and Delta via EXCHANGE_BROKER env var.

  EXCHANGE_BROKER=binance   (default)
  EXCHANGE_BROKER=delta
"""

import os

from dotenv import load_dotenv

load_dotenv()

BROKER = os.environ.get("EXCHANGE_BROKER", "binance").strip().lower()

if BROKER == "delta":
    from .tasks import (  # noqa: F401
        QUANTITY,
        cancel_all_orders,
        cancel_all_orders_order_id,
        get_open_position,
        log,
        place_market_order,
        place_sl_with_retry,
        set_leverage,
        startup_check,
        verify_webhook,
    )
elif BROKER == "binance":
    from .binance_tasks import (  # noqa: F401
        QUANTITY,
        cancel_all_orders,
        cancel_all_orders_order_id,
        get_open_position,
        log,
        place_market_order,
        place_sl_with_retry,
        set_leverage,
        startup_check,
        verify_webhook,
    )
else:
    raise ValueError(
        f"Unknown EXCHANGE_BROKER={BROKER!r}. Use 'binance' or 'delta'."
    )
