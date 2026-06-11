from __future__ import annotations

import os
from typing import Mapping, Any


PAPER_TRADING_MODE = "paper"

LIVE_TRADING_FLAG_KEYS = (
    "ENABLE_LIVE_TRADING",
    "POLYMARKET_ENABLE_LIVE_TRADING",
    "LIVE_TRADING_ENABLED",
    "POLYMARKET_ORDER_EXECUTION",
)

WALLET_SECRET_KEYS = (
    "POLYMARKET_PRIVATE_KEY",
    "POLYMARKET_WALLET_PRIVATE_KEY",
    "POLYMARKET_SIGNING_KEY",
    "CLOB_PRIVATE_KEY",
    "WALLET_PRIVATE_KEY",
)


class SafetyGateError(RuntimeError):
    """Raised when runtime configuration attempts to leave paper-trading mode."""


def _truthy(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on", "enabled"}


def paper_trading_safety_report(env: Mapping[str, str] | None = None) -> dict[str, Any]:
    source = env or os.environ
    enabled_live_flags = [key for key in LIVE_TRADING_FLAG_KEYS if _truthy(source.get(key))]
    configured_wallet_keys = [key for key in WALLET_SECRET_KEYS if source.get(key)]
    ok = not enabled_live_flags and not configured_wallet_keys
    return {
        "ok": ok,
        "mode": PAPER_TRADING_MODE,
        "paperTradingOnly": True,
        "liveTradingEnabled": False,
        "orderExecutionEnabled": False,
        "walletSigningEnabled": False,
        "enabledLiveFlags": enabled_live_flags,
        "configuredWalletKeyNames": configured_wallet_keys,
        "blockedReason": _blocked_reason(enabled_live_flags, configured_wallet_keys),
    }


def assert_paper_trading_only(env: Mapping[str, str] | None = None) -> dict[str, Any]:
    report = paper_trading_safety_report(env)
    if not report["ok"]:
        raise SafetyGateError(report["blockedReason"])
    return report


def _blocked_reason(enabled_live_flags: list[str], configured_wallet_keys: list[str]) -> str | None:
    if enabled_live_flags:
        return f"Live-trading flags are not allowed in this research-only runtime: {', '.join(enabled_live_flags)}"
    if configured_wallet_keys:
        return f"Wallet/signing secrets are not allowed in this research-only runtime: {', '.join(configured_wallet_keys)}"
    return None
