"""Always-on Windows MT5 execution bridge.

The Linux VPS is the source of truth. This node:
- pulls a signed-by-transport deployment manifest over a pinned SSH/SFTP link;
- downloads only Portfolio-selected strategy modules and verifies SHA-256;
- reports MT5 demo heartbeat/equity back to the VPS;
- fails closed on stale manifests, wrong SSH host key, non-demo accounts,
  disabled algo trading, invalid XAUUSD ticks, risk breaker or news/entry gate;
- places orders only when BOTH execution_enabled and entry_allowed are true.

No trading-account password is stored in this project. MT5 must already be
logged into the intended demo account on the Windows VPS.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import importlib.util
import json
import math
import os
import socket
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

CONFIG_PATH = Path(os.environ.get("XAUUSD_BRIDGE_CONFIG", Path(__file__).with_name("bridge_node.json")))
RUNTIME_DIR = Path(os.environ.get("XAUUSD_BRIDGE_RUNTIME", Path(__file__).resolve().parent.parent / "bridge_runtime"))
STRATEGY_DIR = RUNTIME_DIR / "strategies"
STATE_PATH = RUNTIME_DIR / "state.json"
MANIFEST_PATH = RUNTIME_DIR / "deployment.json"


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def load_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def atomic_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, sort_keys=True)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def ssh_fingerprint_sha256(key) -> str:
    digest = hashlib.sha256(key.asbytes()).digest()
    return "SHA256:" + base64.b64encode(digest).decode("ascii").rstrip("=")


def ensure_runtime() -> None:
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    STRATEGY_DIR.mkdir(parents=True, exist_ok=True)


def generate_bridge_key(config: dict) -> str:
    """Generate an unattended, restricted-purpose RSA key and return public line."""
    import paramiko

    key_path = Path(config.get("ssh_key") or (RUNTIME_DIR / "mt5_bridge_rsa"))
    key_path.parent.mkdir(parents=True, exist_ok=True)
    if not key_path.exists():
        key = paramiko.RSAKey.generate(bits=3072)
        key.write_private_key_file(str(key_path))
    else:
        key = paramiko.RSAKey.from_private_key_file(str(key_path))
    config["ssh_key"] = str(key_path)
    blob = key.get_base64()
    return f"ssh-rsa {blob} xauusd-mt5-bridge"


def connect_sftp(config: dict):
    import paramiko

    host = str(config["vps_host"])
    port = int(config.get("vps_port", 22))
    user = str(config.get("vps_user", "mt5bridge"))
    key_path = str(config["ssh_key"])
    expected_fp = str(config.get("vps_host_key_sha256", "")).strip()
    if not expected_fp.startswith("SHA256:"):
        raise RuntimeError("missing pinned VPS SSH host-key fingerprint")

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(
        hostname=host,
        port=port,
        username=user,
        key_filename=key_path,
        allow_agent=False,
        look_for_keys=False,
        timeout=10,
        banner_timeout=10,
        auth_timeout=10,
    )
    transport = client.get_transport()
    if transport is None:
        client.close()
        raise RuntimeError("SSH transport unavailable")
    actual_fp = ssh_fingerprint_sha256(transport.get_remote_server_key())
    if actual_fp != expected_fp:
        client.close()
        raise RuntimeError(f"VPS SSH host-key mismatch: {actual_fp}")
    return client, client.open_sftp()


def sftp_download_atomic(sftp, remote: str, local: Path) -> None:
    local.parent.mkdir(parents=True, exist_ok=True)
    tmp = local.with_suffix(local.suffix + ".download")
    sftp.get(remote, str(tmp))
    os.replace(tmp, local)


def sftp_upload_json(sftp, remote: str, payload: dict) -> None:
    raw = (json.dumps(payload, sort_keys=True) + "\n").encode("utf-8")
    remote_tmp = remote + f".tmp.{os.getpid()}"
    with sftp.file(remote_tmp, "wb") as f:
        f.write(raw)
        f.flush()
    try:
        sftp.remove(remote)
    except Exception:
        pass
    sftp.rename(remote_tmp, remote)


def parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def pull_manifest_and_strategies(config: dict) -> dict:
    client, sftp = connect_sftp(config)
    try:
        outbox = str(config.get("remote_outbox", "/opt/xauusd-scalper-x10/bridge/outbox")).rstrip("/")
        sftp_download_atomic(sftp, outbox + "/deployment.json", MANIFEST_PATH)
        manifest = load_json(MANIFEST_PATH, {})
        if manifest.get("schema") != "xauusd-mt5-bridge-v1":
            raise RuntimeError("unsupported or missing bridge manifest schema")
        for item in manifest.get("strategies", []):
            rel = str(item.get("file", ""))
            expected = str(item.get("sha256", ""))
            if not rel.startswith("strategies/") or len(expected) != 64:
                raise RuntimeError("invalid strategy manifest entry")
            local = STRATEGY_DIR / Path(rel).name
            if not local.exists() or sha256_file(local) != expected:
                sftp_download_atomic(sftp, outbox + "/" + rel, local)
            if sha256_file(local) != expected:
                raise RuntimeError(f"strategy checksum mismatch: {item.get('id')}")
        return manifest
    finally:
        try:
            sftp.close()
        finally:
            client.close()


def mt5_snapshot(config: dict) -> tuple[dict, object | None, object | None]:
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

    symbol = str(config.get("symbol", "XAUUSD"))
    if not mt5.symbol_select(symbol, True):
        snap["error"] = f"symbol_select:{mt5.last_error()}"
        return snap, account, None
    info = mt5.symbol_info(symbol)
    tick = mt5.symbol_info_tick(symbol)
    if info is not None and tick is not None and float(tick.ask or 0) > 0 and float(tick.bid or 0) > 0:
        snap.update({
            "symbol_ok": True,
            "symbol": symbol,
            "bid": float(tick.bid),
            "ask": float(tick.ask),
            "spread": float(tick.ask - tick.bid),
            "point": float(getattr(info, "point", 0.0) or 0.0),
            "volume_min": float(getattr(info, "volume_min", 0.0) or 0.0),
            "volume_step": float(getattr(info, "volume_step", 0.0) or 0.0),
            "volume_max": float(getattr(info, "volume_max", 0.0) or 0.0),
        })
        return snap, account, info
    snap["error"] = "XAUUSD tick unavailable"
    return snap, account, info


def update_risk_state(state: dict, equity: float, policy: dict) -> dict:
    now = utcnow()
    day = now.strftime("%Y-%m-%d")
    week = now.strftime("%Y-%W")
    if state.get("daily_date") != day:
        state["daily_date"] = day
        state["daily_start_equity"] = equity
        state["daily_peak_equity"] = equity
        state["daily_breaker"] = False
    if state.get("weekly_date") != week:
        state["weekly_date"] = week
        state["weekly_start_equity"] = equity
        state["weekly_peak_equity"] = equity
        state["weekly_breaker"] = False
    state["daily_peak_equity"] = max(float(state.get("daily_peak_equity") or equity), equity)
    state["weekly_peak_equity"] = max(float(state.get("weekly_peak_equity") or equity), equity)
    daily_ref = max(float(state.get("daily_start_equity") or equity), float(state["daily_peak_equity"]))
    weekly_ref = max(float(state.get("weekly_start_equity") or equity), float(state["weekly_peak_equity"]))
    daily_dd = max(0.0, (daily_ref - equity) / daily_ref) if daily_ref > 0 else 1.0
    weekly_dd = max(0.0, (weekly_ref - equity) / weekly_ref) if weekly_ref > 0 else 1.0
    state["daily_dd"] = daily_dd
    state["weekly_dd"] = weekly_dd
    if daily_dd >= float(policy.get("max_daily_dd", 0.0) or 0.0):
        state["daily_breaker"] = True
    if weekly_dd >= float(policy.get("max_weekly_dd", 0.0) or 0.0):
        state["weekly_breaker"] = True
    state["circuit_breaker"] = bool(state.get("daily_breaker") or state.get("weekly_breaker"))
    return state


def manifest_fresh(manifest: dict, max_age_seconds: int) -> tuple[bool, float | None]:
    generated = parse_iso(manifest.get("generated_at"))
    if generated is None:
        return False, None
    age = (utcnow() - generated).total_seconds()
    return 0 <= age <= max_age_seconds, age


def load_strategy(item: dict):
    local = STRATEGY_DIR / Path(str(item["file"])).name
    if sha256_file(local) != str(item["sha256"]):
        raise RuntimeError(f"checksum mismatch for {item.get('id')}")
    module_name = "bridge_strategy_" + str(item["id"]).lower()
    spec = importlib.util.spec_from_file_location(module_name, local)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {item.get('id')}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if not hasattr(module, "generate_signals"):
        raise RuntimeError(f"strategy {item.get('id')} lacks generate_signals")
    return module


def open_bridge_positions(mt5, symbol: str):
    positions = mt5.positions_get(symbol=symbol)
    if positions is None:
        return []
    return [p for p in positions if str(getattr(p, "comment", "")).startswith("X10_")]


def existing_for_strategy(positions, strategy_id: str) -> bool:
    comment = "X10_" + strategy_id
    return any(str(getattr(p, "comment", "")) == comment for p in positions)


def portfolio_heat(mt5, positions, equity: float) -> float:
    if equity <= 0:
        return 1.0
    total = 0.0
    for p in positions:
        sl = float(getattr(p, "sl", 0.0) or 0.0)
        if sl <= 0:
            return 1.0
        order_type = mt5.ORDER_TYPE_BUY if int(p.type) == mt5.POSITION_TYPE_BUY else mt5.ORDER_TYPE_SELL
        loss = mt5.order_calc_profit(order_type, p.symbol, float(p.volume), float(p.price_open), sl)
        if loss is None:
            return 1.0
        total += abs(min(float(loss), 0.0))
    return total / equity


def normalized_lot(info, raw: float) -> float:
    step = float(getattr(info, "volume_step", 0.01) or 0.01)
    vmin = float(getattr(info, "volume_min", step) or step)
    vmax = float(getattr(info, "volume_max", raw) or raw)
    if raw < vmin:
        return 0.0
    units = math.floor((raw + 1e-12) / step)
    lot = units * step
    lot = min(lot, vmax)
    decimals = max(0, int(round(-math.log10(step)))) if step < 1 else 0
    return round(lot, decimals)


def execute_new_bar(config: dict, manifest: dict, snap: dict, account, info, state: dict) -> list[dict]:
    import MetaTrader5 as mt5
    import pandas as pd
    import ta

    events = []
    symbol = str(config.get("symbol", "XAUUSD"))
    rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M5, 1, int(config.get("m5_lookback", 600)))
    if rates is None or len(rates) < 120:
        return [{"type": "blocked", "reason": "insufficient_m5_bars"}]
    df = pd.DataFrame(rates)
    df["time"] = pd.to_datetime(df["time"], unit="s", utc=True)
    df = df.rename(columns={"open": "Open", "high": "High", "low": "Low", "close": "Close", "tick_volume": "Volume"})
    last_bar = df["time"].iloc[-1].isoformat()
    if state.get("last_closed_m5") == last_bar:
        return []
    state["last_closed_m5"] = last_bar

    policy = manifest.get("risk_policy") or {}
    positions = open_bridge_positions(mt5, symbol)
    if len(positions) >= int(policy.get("max_open_trades", 1) or 1):
        return [{"type": "blocked", "reason": "max_open_trades"}]
    heat = portfolio_heat(mt5, positions, float(snap["equity"]))
    if heat >= float(policy.get("max_portfolio_heat", 0.0) or 0.0):
        return [{"type": "blocked", "reason": "portfolio_heat", "heat": heat}]

    tick = mt5.symbol_info_tick(symbol)
    if tick is None:
        return [{"type": "blocked", "reason": "tick_unavailable"}]
    current_spread = float(tick.ask - tick.bid)
    point = float(getattr(info, "point", 0.0) or 0.0)
    if "spread" in df.columns and point > 0:
        typical_spread = float(df["spread"].tail(500).median()) * point
    else:
        typical_spread = 0.10
    max_spread = max(2.0 * typical_spread, 0.20)
    if current_spread > max_spread:
        return [{"type": "blocked", "reason": "spread", "spread": current_spread, "ceiling": max_spread}]

    for item in manifest.get("strategies", []):
        sid = str(item.get("id", ""))
        if not sid or existing_for_strategy(positions, sid):
            continue
        try:
            module = load_strategy(item)
            work = module.generate_signals(df.copy())
            signal = int(work["signal"].iloc[-1])
            if signal == 0:
                continue
            direction = "buy" if signal > 0 else "sell"
            params = dict(getattr(module, "PARAMS", {}) or {})
            atr_period = int(params.get("atr_period", 14) or 14)
            atr_series = ta.volatility.average_true_range(work["High"], work["Low"], work["Close"], window=atr_period)
            atr = float(atr_series.iloc[-1])
            if not math.isfinite(atr) or atr <= 0:
                continue
            sl_atr = float(params.get("sl_atr", 1.5) or 1.5)
            tp_atr = float(params.get("tp_atr", 2.5) or 2.5)
            if direction == "buy":
                order_type = mt5.ORDER_TYPE_BUY
                price = float(tick.ask)
                sl = price - sl_atr * atr
                tp = price + tp_atr * atr
            else:
                order_type = mt5.ORDER_TYPE_SELL
                price = float(tick.bid)
                sl = price + sl_atr * atr
                tp = price - tp_atr * atr

            loss_one_lot = mt5.order_calc_profit(order_type, symbol, 1.0, price, sl)
            if loss_one_lot is None or float(loss_one_lot) >= 0:
                events.append({"type": "blocked", "strategy": sid, "reason": "risk_calc_failed"})
                continue
            risk_budget = float(snap["equity"]) * float(policy.get("risk_per_trade", 0.0) or 0.0)
            raw_lot = risk_budget / abs(float(loss_one_lot))
            lot = normalized_lot(info, raw_lot)
            if lot <= 0:
                events.append({"type": "blocked", "strategy": sid, "reason": "broker_min_lot_exceeds_risk"})
                continue
            actual_loss = abs(float(loss_one_lot)) * lot
            projected_heat = heat + actual_loss / float(snap["equity"])
            if projected_heat > float(policy.get("max_portfolio_heat", 0.0) or 0.0):
                events.append({"type": "blocked", "strategy": sid, "reason": "projected_portfolio_heat"})
                continue
            margin = mt5.order_calc_margin(order_type, symbol, lot, price)
            if margin is None or float(margin) > float(snap["free_margin"]) * 0.70:
                events.append({"type": "blocked", "strategy": sid, "reason": "margin_guard"})
                continue

            request = {
                "action": mt5.TRADE_ACTION_DEAL,
                "symbol": symbol,
                "volume": lot,
                "type": order_type,
                "price": price,
                "sl": sl,
                "tp": tp,
                "deviation": int(config.get("max_deviation_points", 20)),
                "magic": 424242,
                "comment": "X10_" + sid,
                "type_time": mt5.ORDER_TIME_GTC,
                "type_filling": int(getattr(info, "filling_mode", mt5.ORDER_FILLING_IOC)),
            }
            check = mt5.order_check(request)
            if check is None or int(getattr(check, "retcode", -1)) not in (0,):
                events.append({"type": "order_check_failed", "strategy": sid, "retcode": getattr(check, "retcode", None), "comment": getattr(check, "comment", None)})
                continue
            result = mt5.order_send(request)
            ok = result is not None and int(getattr(result, "retcode", -1)) == mt5.TRADE_RETCODE_DONE
            events.append({
                "type": "trade_open" if ok else "order_failed",
                "strategy": sid,
                "direction": direction,
                "lot": lot,
                "price": price,
                "sl": sl,
                "tp": tp,
                "retcode": getattr(result, "retcode", None),
                "comment": getattr(result, "comment", None),
                "ticket": getattr(result, "order", None),
            })
            if ok:
                positions = open_bridge_positions(mt5, symbol)
                heat = portfolio_heat(mt5, positions, float(snap["equity"]))
        except Exception as exc:
            events.append({"type": "strategy_error", "strategy": sid, "error": str(exc)[:300]})
    return events


def upload_heartbeat(config: dict, payload: dict, events: list[dict]) -> None:
    client, sftp = connect_sftp(config)
    try:
        inbox = str(config.get("remote_inbox", "/opt/xauusd-scalper-x10/bridge/inbox")).rstrip("/")
        sftp_upload_json(sftp, inbox + "/heartbeat.json", payload)
        for event in events:
            stamp = utcnow().strftime("%Y%m%dT%H%M%S%fZ")
            sftp_upload_json(sftp, inbox + f"/event_{stamp}_{os.getpid()}.json", {"at": utcnow().isoformat(), **event})
    finally:
        try:
            sftp.close()
        finally:
            client.close()


def init_config(args) -> int:
    ensure_runtime()
    config = load_json(CONFIG_PATH, {})
    config.update({
        "vps_host": args.vps_host,
        "vps_port": 22,
        "vps_user": "mt5bridge",
        "vps_host_key_sha256": args.host_key,
        "remote_outbox": "/opt/xauusd-scalper-x10/bridge/outbox",
        "remote_inbox": "/opt/xauusd-scalper-x10/bridge/inbox",
        "symbol": "XAUUSD",
        "poll_seconds": 30,
        "heartbeat_seconds": 30,
        "max_manifest_age_seconds": 180,
        "m5_lookback": 600,
        "max_deviation_points": 20,
    })
    public = generate_bridge_key(config)
    try:
        import MetaTrader5 as mt5
        if mt5.initialize():
            account = mt5.account_info()
            if account is not None:
                if int(getattr(account, "trade_mode", -1)) != 0:
                    raise RuntimeError("Refusing initialization: current MT5 account is not demo")
                config["expected_login"] = int(account.login)
                config["expected_server"] = str(account.server)
            mt5.shutdown()
    except ImportError:
        pass
    atomic_json(CONFIG_PATH, config)
    print("BRIDGE PUBLIC KEY (safe to copy):")
    print(public)
    print(f"Config: {CONFIG_PATH}")
    if not config.get("expected_login"):
        print("WARNING: MT5 demo account was not detected; run --bind-account after MT5 login.")
    else:
        print(f"Bound to demo MT5 #{config['expected_login']} on {config['expected_server']}")
    return 0


def bind_account() -> int:
    config = load_json(CONFIG_PATH, {})
    import MetaTrader5 as mt5
    if not mt5.initialize():
        raise RuntimeError(f"MT5 initialize failed: {mt5.last_error()}")
    try:
        account = mt5.account_info()
        if account is None or int(getattr(account, "trade_mode", -1)) != 0:
            raise RuntimeError("Current MT5 account is unavailable or not demo")
        config["expected_login"] = int(account.login)
        config["expected_server"] = str(account.server)
        atomic_json(CONFIG_PATH, config)
        print(f"Bound to demo MT5 #{account.login} on {account.server}")
    finally:
        mt5.shutdown()
    return 0


def run_forever() -> int:
    ensure_runtime()
    config = load_json(CONFIG_PATH, {})
    required = ["vps_host", "vps_user", "ssh_key", "vps_host_key_sha256", "expected_login", "expected_server"]
    missing = [k for k in required if not config.get(k)]
    if missing:
        raise RuntimeError("bridge config incomplete: " + ",".join(missing))

    state = load_json(STATE_PATH, {})
    last_manifest_pull = 0.0
    manifest = load_json(MANIFEST_PATH, {})
    while True:
        started = time.time()
        events: list[dict] = []
        errors: list[str] = []
        if started - last_manifest_pull >= float(config.get("poll_seconds", 30)) or not manifest:
            try:
                manifest = pull_manifest_and_strategies(config)
                last_manifest_pull = started
            except Exception as exc:
                errors.append("manifest:" + str(exc)[:300])

        try:
            snap, account, info = mt5_snapshot(config)
        except Exception as exc:
            snap, account, info = {"mt5_connected": False, "error": str(exc)[:300]}, None, None
        policy = manifest.get("risk_policy") or {}
        if snap.get("equity", 0) and policy:
            state = update_risk_state(state, float(snap["equity"]), policy)

        fresh, age = manifest_fresh(manifest, int(config.get("max_manifest_age_seconds", 180)))
        execution_ready = bool(
            fresh
            and manifest.get("execution_enabled") is True
            and manifest.get("entry_allowed") is True
            and snap.get("mt5_connected")
            and snap.get("demo")
            and snap.get("account_match")
            and snap.get("trade_allowed")
            and snap.get("trade_expert")
            and snap.get("symbol_ok")
            and not state.get("circuit_breaker", False)
        )

        if execution_ready and account is not None and info is not None:
            try:
                events.extend(execute_new_bar(config, manifest, snap, account, info, state))
            except Exception as exc:
                errors.append("execute:" + str(exc)[:300])

        heartbeat = {
            "schema": "xauusd-mt5-heartbeat-v1",
            "at": utcnow().isoformat(),
            "node": socket.gethostname(),
            "manifest_generated_at": manifest.get("generated_at"),
            "manifest_age_seconds": age,
            "manifest_fresh": fresh,
            "execution_manifest_enabled": manifest.get("execution_enabled") is True,
            "entry_allowed": manifest.get("entry_allowed") is True,
            "execution_ready": execution_ready,
            "selected_strategies": [x.get("id") for x in manifest.get("strategies", [])],
            "risk": state,
            "errors": errors,
            **snap,
        }
        atomic_json(STATE_PATH, state)
        try:
            upload_heartbeat(config, heartbeat, events)
        except Exception as exc:
            print(f"heartbeat upload failed: {exc}", file=sys.stderr, flush=True)
        print(json.dumps({"at": heartbeat["at"], "ready": execution_ready, "equity": snap.get("equity"), "strategies": heartbeat["selected_strategies"], "errors": errors}), flush=True)

        elapsed = time.time() - started
        time.sleep(max(1.0, float(config.get("heartbeat_seconds", 30)) - elapsed))


def main() -> int:
    parser = argparse.ArgumentParser(description="XAUUSD Windows MT5 bridge")
    sub = parser.add_subparsers(dest="command", required=True)
    p_init = sub.add_parser("init")
    p_init.add_argument("--vps-host", required=True)
    p_init.add_argument("--host-key", required=True)
    sub.add_parser("bind-account")
    sub.add_parser("run")
    args = parser.parse_args()
    if args.command == "init":
        return init_config(args)
    if args.command == "bind-account":
        return bind_account()
    if args.command == "run":
        return run_forever()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
