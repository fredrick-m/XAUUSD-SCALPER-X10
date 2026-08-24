"""Runtime wrapper for Windows MT5 bridge with resilient Exness symbol resolution."""
from __future__ import annotations

from scripts import windows_mt5_bridge as bridge


def mt5_snapshot(config: dict):
    import MetaTrader5 as mt5

    snap = {
        "mt5_connected": False,
        "demo": False,
        "symbol_ok": False,
        "trade_allowed": False,
        "trade_expert": False,
    }
    if not mt5.initialize():
        snap["error"] = f"initialize:{mt5.last_error()}"
        return snap, None, None

    account = mt5.account_info()
    if account is None:
        snap["error"] = f"account_info:{mt5.last_error()}"
        return snap, None, None

    snap.update({
        "mt5_connected": True,
        "login": int(getattr(account, "login", 0) or 0),
        "server": str(getattr(account, "server", "") or ""),
        "balance": float(getattr(account, "balance", 0.0) or 0.0),
        "equity": float(getattr(account, "equity", 0.0) or 0.0),
        "margin": float(getattr(account, "margin", 0.0) or 0.0),
        "free_margin": float(getattr(account, "margin_free", 0.0) or 0.0),
        "leverage": int(getattr(account, "leverage", 0) or 0),
        "demo": int(getattr(account, "trade_mode", -1)) == 0,
        "trade_allowed": bool(getattr(account, "trade_allowed", False)),
        "trade_expert": bool(getattr(account, "trade_expert", False)),
    })

    expected_login = int(config.get("expected_login") or 0)
    expected_server = str(config.get("expected_server") or "")
    snap["account_match"] = bool(
        expected_login > 0
        and snap["login"] == expected_login
        and expected_server
        and snap["server"] == expected_server
    )

    preferred = str(config.get("symbol", "XAUUSD") or "XAUUSD")
    candidates = [preferred]
    try:
        for item in mt5.symbols_get("*XAUUSD*") or ():
            name = str(getattr(item, "name", "") or "")
            if name and name not in candidates:
                candidates.append(name)
    except Exception:
        pass

    select_errors = {}
    for symbol in candidates:
        info = mt5.symbol_info(symbol)
        if info is None:
            continue

        # If Market Watch already exposes the symbol, do not call symbol_select:
        # some terminals return 'Terminal: Call failed' even though the visible
        # symbol has a valid live tick and is fully tradable.
        if not bool(getattr(info, "visible", False)):
            if not mt5.symbol_select(symbol, True):
                select_errors[symbol] = mt5.last_error()
                continue
            info = mt5.symbol_info(symbol)
            if info is None:
                continue

        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            continue
        ask = float(getattr(tick, "ask", 0.0) or 0.0)
        bid = float(getattr(tick, "bid", 0.0) or 0.0)
        if ask <= 0 or bid <= 0:
            continue

        snap.update({
            "symbol_ok": True,
            "symbol": symbol,
            "bid": bid,
            "ask": ask,
            "spread": ask - bid,
            "point": float(getattr(info, "point", 0.0) or 0.0),
            "volume_min": float(getattr(info, "volume_min", 0.0) or 0.0),
            "volume_step": float(getattr(info, "volume_step", 0.0) or 0.0),
            "volume_max": float(getattr(info, "volume_max", 0.0) or 0.0),
        })

        if symbol != preferred:
            config["symbol"] = symbol
            bridge.atomic_json(bridge.CONFIG_PATH, config)
        return snap, account, info

    snap["error"] = "XAUUSD symbol/tick unavailable"
    if select_errors:
        snap["symbol_select_errors"] = {k: str(v) for k, v in select_errors.items()}
    snap["symbol_candidates"] = candidates[:20]
    return snap, account, None


bridge.mt5_snapshot = mt5_snapshot


if __name__ == "__main__":
    raise SystemExit(bridge.main())
