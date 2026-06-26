"""Force a test BUY trade on MT5 demo to verify the end-to-end pipeline."""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import MetaTrader5 as mt5
import pandas as pd
import ta

SYMBOL = "XAUUSD"
MAGIC_NUMBER = 424242
SL_ATR = 1.5
TP_ATR = 3.0
RISK_PCT = 0.04
PIP_VALUE = 100.0
MIN_LOT = 0.001
MAX_LOT = 100.0

def main():
    # 1. Connect
    if not mt5.initialize():
        print(f"MT5 init failed: {mt5.last_error()}")
        return

    account = mt5.account_info()
    if account is None:
        print("No account info")
        mt5.shutdown()
        return

    print(f"Account: #{account.login} | Balance: ${account.balance:.2f} | Mode: {'DEMO' if account.trade_mode == 0 else 'LIVE'}")

    if account.trade_mode != 0:
        print("REFUSING: This is a LIVE account, not demo!")
        mt5.shutdown()
        return

    # 2. Get current price
    tick = mt5.symbol_info_tick(SYMBOL)
    if tick is None:
        print(f"Cannot get tick for {SYMBOL}")
        mt5.shutdown()
        return

    print(f"Price: bid={tick.bid:.2f}, ask={tick.ask:.2f}, spread={tick.ask - tick.bid:.2f}")

    # 3. Calculate ATR from M5 bars
    rates = mt5.copy_rates_from_pos(SYMBOL, mt5.TIMEFRAME_M5, 0, 200)
    if rates is None or len(rates) < 50:
        print("Cannot fetch M5 bars")
        mt5.shutdown()
        return

    df = pd.DataFrame(rates)
    df["time"] = pd.to_datetime(df["time"], unit="s")
    df = df.rename(columns={"open": "Open", "high": "High", "low": "Low", "close": "Close"})

    atr_series = ta.volatility.average_true_range(df["High"], df["Low"], df["Close"], window=14)
    atr_val = atr_series.iloc[-1]
    print(f"ATR(14): {atr_val:.2f}")

    # 4. BUY setup (bull stack confirmed in previous check)
    price = tick.ask
    sl = round(price - SL_ATR * atr_val, 2)
    tp = round(price + TP_ATR * atr_val, 2)

    # 5. Lot sizing: 4% risk
    sl_distance = abs(price - sl)
    if sl_distance <= 0:
        print("SL distance is zero")
        mt5.shutdown()
        return

    lot = (account.balance * RISK_PCT) / (sl_distance * PIP_VALUE)
    lot = max(MIN_LOT, min(MAX_LOT, round(lot, 2)))

    print(f"\n=== TEST TRADE ===")
    print(f"Direction: BUY")
    print(f"Entry:     {price:.2f}")
    print(f"SL:        {sl:.2f} ({SL_ATR}x ATR = {SL_ATR * atr_val:.2f})")
    print(f"TP:        {tp:.2f} ({TP_ATR}x ATR = {TP_ATR * atr_val:.2f})")
    print(f"Lot:       {lot}")
    print(f"Risk:      ${account.balance * RISK_PCT:.2f} ({RISK_PCT*100}% of ${account.balance:.2f})")

    # 6. Send order
    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": SYMBOL,
        "volume": lot,
        "type": mt5.ORDER_TYPE_BUY,
        "price": price,
        "sl": sl,
        "tp": tp,
        "deviation": 20,
        "magic": MAGIC_NUMBER,
        "comment": "TEST_I003_forced",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }

    result = mt5.order_send(request)
    if result is None:
        print(f"\nOrder send returned None. Last error: {mt5.last_error()}")
    elif result.retcode == mt5.TRADE_RETCODE_DONE:
        print(f"\n*** TRADE OPENED ***")
        print(f"Order:  #{result.order}")
        print(f"Deal:   #{result.deal}")
        print(f"Volume: {result.volume}")
        print(f"Price:  {result.price:.2f}")

        # Log to database
        try:
            from core.db import AgentDB
            from core.config import DB_PATH
            db = AgentDB(str(DB_PATH))
            db.execute(
                "INSERT INTO agent_events (agent_id, event_type, message, metadata) "
                "VALUES (?, ?, ?, ?)",
                (
                    "paper_trade",
                    "trade_open",
                    f"FORCED TEST: BUY @ {result.price:.2f}, SL={sl:.2f}, TP={tp:.2f}, lot={lot}",
                    f'{{"strategy_id":"i003","direction":"buy","price":{result.price},"sl":{sl},"tp":{tp},"lot":{lot},"test":true}}',
                ),
            )
            print("Trade logged to agent_events DB")
        except Exception as e:
            print(f"DB logging failed (non-critical): {e}")
    else:
        print(f"\nOrder FAILED: retcode={result.retcode}, comment={result.comment}")

    # Show open positions
    positions = mt5.positions_get(symbol=SYMBOL)
    if positions:
        print(f"\n=== OPEN POSITIONS ({len(positions)}) ===")
        for p in positions:
            print(f"  #{p.ticket} | {'BUY' if p.type == 0 else 'SELL'} | {p.volume} lot @ {p.price_open:.2f} | P&L: ${p.profit:.2f}")
    else:
        print("\nNo open positions on XAUUSD")

    mt5.shutdown()

if __name__ == "__main__":
    main()
