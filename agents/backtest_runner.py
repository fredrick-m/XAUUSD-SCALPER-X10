"""Backtest Runner agent: processes backtest tasks from the queue and runs strategy simulations.

Uses multiprocessing to run backtests in parallel across CPU cores.
"""
import hashlib
import importlib.util
import json
import traceback
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

from agents.base_agent import BaseAgent
from agents.validation_v2 import (
    build_anchored_walk_forward_ranges,
    assess_walk_forward,
    assess_holdout,
)
from core.config import (
    DATA_DIR, STRATEGIES_DIR, DEFAULT_RISK_PCT,
    HOLDOUT_MONTHS, HOLDOUT_MIN_PF, HOLDOUT_MIN_TRADES,
    PROBATION_MIN_TRADES, PROBATION_MIN_PF, PROBATION_MAX_DD,
    PROBATION_MIN_WR_LB, PROBATION_HOLDOUT_MIN_TRADES, PROBATION_HOLDOUT_MIN_PF,
)
from engine.backtest import run_simulation, validate, add_regime_indicators

MIN_SELECTION_SIGNALS = 30
MAX_SELECTION_SIGNALS = 2500


def _probation_ok(metrics: dict) -> bool:
    """Small sample, exceptional quality: stricter bars compensate low n.

    The 95% lower confidence bound on the win rate must still beat 50%,
    so the required WR rises automatically as the sample shrinks.
    """
    import math as _math

    n = metrics.get("total_trades", 0)
    wr = metrics.get("win_rate", 0.0)
    pf = metrics.get("profit_factor", 0.0)
    dd = metrics.get("max_drawdown", 1.0)

    if n < PROBATION_MIN_TRADES:
        return False
    if pf < PROBATION_MIN_PF or dd > PROBATION_MAX_DD:
        return False
    wr_lb = wr - 1.96 * _math.sqrt(max(wr * (1 - wr), 1e-9) / n)
    return wr_lb >= PROBATION_MIN_WR_LB


def _strip_equity(metrics: dict) -> dict:
    return {k: v for k, v in metrics.items() if k != "equity_curve"}


# ══════════════════════════════════════════════
# Standalone worker function (runs in subprocess)
# ══════════════════════════════════════════════

def _backtest_worker(strategy_id: str, file_path: str, df_m5_bytes: bytes,
                     data_hash: str, slippage_override: float = None) -> dict:
    """Run a single backtest in an isolated process.

    Returns a result dict with status and metrics/reason.
    """
    import pickle
    df = pickle.loads(df_m5_bytes)

    p = Path(file_path)
    if not p.exists():
        return {"strategy_id": strategy_id, "status": "rejected", "reason": "file_missing"}

    try:
        spec = importlib.util.spec_from_file_location(f"strategy_{strategy_id.lower()}", str(p))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    except Exception as exc:
        return {"strategy_id": strategy_id, "status": "rejected", "reason": f"load_failed: {exc}"}

    params = getattr(module, "PARAMS", {})
    sl_atr = params.get("sl_atr", 1.5)
    tp_atr_val = params.get("tp_atr", 2.5)

    try:
        result_df = module.generate_signals(df.copy(), params)
    except Exception as exc:
        return {"strategy_id": strategy_id, "status": "rejected", "reason": f"signal_gen_failed: {exc}"}

    if "signal" not in result_df.columns or "ATR" not in result_df.columns:
        return {"strategy_id": strategy_id, "status": "rejected", "reason": "signal_gen_failed"}

    signals = result_df["signal"]
    atr = result_df["ATR"]
    close = result_df["Close"]

    sl_prices = pd.Series(np.nan, index=df.index)
    tp_prices = pd.Series(np.nan, index=df.index)
    directions = pd.Series(0, index=df.index)

    long_mask = signals == 1
    short_mask = signals == -1
    sl_prices[long_mask] = close[long_mask] - sl_atr * atr[long_mask]
    tp_prices[long_mask] = close[long_mask] + tp_atr_val * atr[long_mask]
    sl_prices[short_mask] = close[short_mask] + sl_atr * atr[short_mask]
    tp_prices[short_mask] = close[short_mask] - tp_atr_val * atr[short_mask]
    directions[long_mask] = 1
    directions[short_mask] = -1

    try:
        use_trailing = bool(params.get("trailing", 1))
        if params.get("tp_atr", 2.0) >= 3.0:
            use_trailing = False
    except Exception:
        use_trailing = False

    sess_start = int(params.get("session_start", 7))
    sess_end = int(params.get("session_end", 21))
    if not (0 <= sess_start < sess_end <= 24):
        sess_start, sess_end = 7, 21

    def _sim(a: int, b: int) -> dict:
        return run_simulation(
            df.iloc[a:b], signals.iloc[a:b], sl_prices.iloc[a:b],
            tp_prices.iloc[a:b], directions.iloc[a:b],
            risk_pct=DEFAULT_RISK_PCT, trailing_stop=use_trailing,
            max_bars_in_trade=200, session_filter=True,
            session_hours=(sess_start, sess_end),
            slippage_override=slippage_override,
        )

    times = pd.to_datetime(df["time"])
    holdout_start = times.iloc[-1] - pd.DateOffset(months=HOLDOUT_MONTHS)
    h_idx = int((times < holdout_start).sum())
    holdout_available = h_idx >= 5000 and (len(df) - h_idx) >= 1000
    if not holdout_available:
        h_idx = len(df)

    signal_count = int((signals.iloc[:h_idx] != 0).sum())
    if signal_count < MIN_SELECTION_SIGNALS:
        return {"strategy_id": strategy_id, "status": "rejected",
                "reason": f"too_few_signals ({signal_count} < {MIN_SELECTION_SIGNALS})",
                "signal_count": signal_count}
    if signal_count > MAX_SELECTION_SIGNALS:
        return {"strategy_id": strategy_id, "status": "rejected",
                "reason": f"too_many_signals ({signal_count} > {MAX_SELECTION_SIGNALS})",
                "signal_count": signal_count}

    selection_days = 1.0
    if h_idx >= 2:
        selection_days = max(
            1.0,
            (times.iloc[h_idx - 1] - times.iloc[0]).total_seconds() / 86400.0,
        )

    try:
        metrics = _sim(0, h_idx)
    except Exception as exc:
        return {"strategy_id": strategy_id, "status": "error",
                "reason": f"simulation_failed: {exc}"}

    regimes_tested = 1
    try:
        df_regime = add_regime_indicators(df.iloc[:h_idx])
        regimes_present = set(df_regime["regime"].dropna().unique()) - {"UNKNOWN", "MIXED"}
        regimes_tested = max(1, len(regimes_present))
    except Exception:
        pass

    probation = False
    passed, fails = validate(metrics, regimes_tested=regimes_tested, timeframe="M5")
    if not passed:
        only_trades_fail = all(f.startswith("trades") for f in fails)
        if only_trades_fail and _probation_ok(metrics):
            probation = True
        else:
            return {"strategy_id": strategy_id, "status": "failed_validation",
                    "metrics": metrics, "fails": fails, "data_hash": data_hash}

    wf_fold_payload = []
    wf_ranges = build_anchored_walk_forward_ranges(h_idx)
    wf_error = None
    if wf_ranges:
        try:
            for train_start, train_end, test_start, test_end in wf_ranges:
                train_metrics = _sim(train_start, train_end)
                test_metrics = _sim(test_start, test_end)
                wf_fold_payload.append({
                    "train_range": [train_start, train_end],
                    "test_range": [test_start, test_end],
                    "train": _strip_equity(train_metrics),
                    "test": _strip_equity(test_metrics),
                })
            walk_forward = assess_walk_forward(wf_fold_payload, probation=probation)
        except Exception as exc:
            wf_error = str(exc)
            walk_forward = {"model": "anchored_walk_forward_v2", "passed": False, "error": wf_error, "folds": []}
    else:
        walk_forward = {"model": "anchored_walk_forward_v2", "passed": False, "error": "insufficient_selection_history", "folds": []}
    wf_passed = bool(walk_forward.get("passed", False))

    holdout_passed = False
    holdout_clean = None
    holdout_validation = {"model": "locked_holdout_v2", "passed": False, "error": "holdout_unavailable"}
    if wf_passed and holdout_available:
        min_h_trades = PROBATION_HOLDOUT_MIN_TRADES if probation else HOLDOUT_MIN_TRADES
        min_h_pf = PROBATION_HOLDOUT_MIN_PF if probation else HOLDOUT_MIN_PF
        try:
            hm = _sim(h_idx, len(df))
            holdout_clean = _strip_equity(hm)
            holdout_validation = assess_holdout(hm, min_trades=min_h_trades, min_pf=min_h_pf, probation=probation)
            holdout_passed = bool(holdout_validation.get("passed", False))
        except Exception as exc:
            holdout_validation = {"model": "locked_holdout_v2", "passed": False, "error": str(exc)}
    elif wf_passed and not holdout_available:
        holdout_passed = False

    validation_v2 = {
        "model": "validation_v2",
        "walk_forward": walk_forward,
        "holdout": holdout_validation,
        "holdout_available": holdout_available,
        "passed": wf_passed and holdout_passed,
    }

    regime_perf = {}
    try:
        df_reg = add_regime_indicators(df.iloc[:h_idx])
        for reg in ("TREND", "RANGE", "HIGH_VOLATILITY"):
            sigs_r = signals.iloc[:h_idx].where(df_reg["regime"] == reg, 0)
            if int((sigs_r != 0).sum()) < 5:
                continue
            m_r = run_simulation(
                df.iloc[:h_idx], sigs_r, sl_prices.iloc[:h_idx], tp_prices.iloc[:h_idx], directions.iloc[:h_idx],
                risk_pct=DEFAULT_RISK_PCT, trailing_stop=use_trailing, max_bars_in_trade=200,
                session_filter=True, session_hours=(sess_start, sess_end), slippage_override=slippage_override,
            )
            regime_perf[reg] = {"trades": m_r.get("total_trades", 0), "pf": m_r.get("profit_factor", 0.0)}
    except Exception:
        regime_perf = {}

    metrics_clean = _strip_equity(metrics)
    scalping_frequency = {
        "model": "scalping_frequency_v1",
        "selection_days": round(selection_days, 2),
        "signals": signal_count,
        "signals_per_day": round(signal_count / selection_days, 4),
        "trades": int(metrics.get("total_trades", 0) or 0),
        "trades_per_day": round(float(metrics.get("total_trades", 0) or 0) / selection_days, 4),
    }

    return {
        "strategy_id": strategy_id, "status": "validated", "regime_perf": regime_perf,
        "wf_passed": wf_passed and holdout_passed, "wf_only": wf_passed,
        "holdout_passed": holdout_passed, "holdout_metrics": holdout_clean,
        "validation_v2": validation_v2, "probation": probation, "metrics": metrics,
        "metrics_clean": metrics_clean, "scalping_frequency": scalping_frequency,
        "data_hash": data_hash, "regimes_tested": regimes_tested,
    }


class BacktestRunner(BaseAgent):
    name = "backtest_runner"

    def __init__(self, db):
        super().__init__(agent_id="backtest_runner", db=db)
        self._data_cache: Optional[pd.DataFrame] = None
        self._data_cache_m5: Optional[pd.DataFrame] = None
        self._data_hash: Optional[str] = None
        self._df_m5_pickle: Optional[bytes] = None
        self._regime_cache: Optional[int] = None

    def setup(self):
        self.logger.info("Backtest Runner ready (parallel mode, Validation V2)")

    def tick(self):
        self._process_untested_parallel(batch_size=12)
        self._process_task_queue(max_per_tick=5)
        self._revalidate_deployed()

    def tick_interval(self) -> float:
        return self.get_config("tick_interval", 5)

    def _process_task_queue(self, max_per_tick: int = 5):
        tasks = self.get_pending_tasks()
        processed = 0
        for task in tasks:
            if processed >= max_per_tick:
                break
            task_id = task["id"]
            if task.get("task_type", "") != "backtest":
                continue
            try:
                payload = json.loads(task["payload"]) if isinstance(task["payload"], str) else task["payload"]
                strategy_id = payload.get("strategy_id")
                if not strategy_id:
                    self.fail_task(task_id, "Missing strategy_id in payload")
                    continue
                result = self.run_single_backtest(strategy_id)
                self.complete_task(task_id, result or {})
                processed += 1
            except Exception as exc:
                self.logger.error(f"Task {task_id} failed: {exc}")
                self.fail_task(task_id, traceback.format_exc())
                processed += 1

    def _process_untested_parallel(self, batch_size: int = 12):
        df_m5 = self._load_data_m5()
        if df_m5 is None:
            return
        if self._df_m5_pickle is None:
            import pickle
            self._df_m5_pickle = pickle.dumps(df_m5)
            self.logger.info(f"M5 data serialized: {len(self._df_m5_pickle) / 1024 / 1024:.1f} MB")
        rows = self.db.fetchall(
            "SELECT s.id, s.file_path FROM strategies s LEFT JOIN backtest_results b ON s.id = b.strategy_id "
            "WHERE s.status = 'candidate' AND b.id IS NULL "
            "ORDER BY CASE WHEN s.id LIKE 'T%' THEN 0 WHEN s.id LIKE 'G%' THEN 1 ELSE 2 END, s.id DESC "
            f"LIMIT {batch_size}",
        )
        if not rows:
            return
        jobs=[]
        for row in rows:
            fp=row["file_path"]
            if fp and not Path(fp).exists():
                self._mark_rejected(row["id"], "file_missing")
                continue
            jobs.append((row["id"],fp))
        if not jobs:
            return
        self.logger.info(f"Submitting {len(jobs)} backtests to parallel pool")
        slip=self._measured_slippage(); results=[]
        try:
            with ProcessPoolExecutor(max_workers=3) as pool:
                futures={pool.submit(_backtest_worker,sid,fp,self._df_m5_pickle,self._data_hash,slip):sid for sid,fp in jobs}
                for future in as_completed(futures,timeout=300):
                    sid=futures[future]
                    try: results.append(future.result(timeout=60))
                    except Exception as exc:
                        self.logger.error(f"Worker failed for {sid}: {exc}"); self._mark_rejected(sid,str(exc)[:200])
        except Exception as exc:
            self.logger.error(f"ProcessPool error: {exc}"); return
        validated=rejected=0
        for r in results:
            status=self._apply_worker_result(r)
            if status=="validated" and r.get("wf_passed",False): validated+=1
            else: rejected+=1
        if validated>0 or rejected>0:
            self.logger.info(f"Batch complete: {validated} validated, {rejected} rejected/failed")

    def _apply_worker_result(self,r:dict)->str:
        sid=r["strategy_id"]; status=r["status"]
        if status in ("rejected","error"):
            self._mark_rejected(sid,r.get("reason","unknown")); self.logger.info(f"Strategy {sid} rejected: {r.get('reason','unknown')}")
        elif status=="failed_validation":
            metrics=r.get("metrics",{}); self._store_results(sid,metrics,{}); self._update_strategy_metrics(sid,metrics)
            self.logger.info(f"Strategy {sid} did not pass validation: {r.get('fails')}")
        elif status=="validated":
            metrics=r.get("metrics",{}); self._store_results(sid,metrics,{}); self._update_strategy_metrics(sid,metrics)
            if r.get("regime_perf"): self._merge_best_config(sid,"regime_perf",r["regime_perf"])
            if r.get("validation_v2"): self._merge_best_config(sid,"validation_v2",r["validation_v2"])
            if r.get("scalping_frequency"): self._merge_best_config(sid,"scalping_frequency",r["scalping_frequency"])
            if r.get("wf_passed",False):
                self.db.execute("UPDATE strategies SET status = 'validated', walk_forward_passed = 1 WHERE id = ?",(sid,))
                probation=r.get("probation",False)
                if probation: self._mark_probation(sid)
                label="PROBATION (reduced size)" if probation else "full"
                self.emit_event("milestone",f"Strategy {sid} passed Validation V2 + locked holdout [{label}]",
                    metadata={"strategy_id":sid,"probation":probation,"metrics":r.get("metrics_clean",{}),"validation_v2":r.get("validation_v2",{})})
                self.logger.info(f"Strategy {sid} VALIDATED [{label}] (Validation V2 passed)")
            else:
                self.db.execute("UPDATE strategies SET status = 'validated', walk_forward_passed = 0 WHERE id = ?",(sid,))
                self.logger.info(f"Strategy {sid} passed WF V2 but FAILED locked holdout" if r.get("wf_only",False) and not r.get("holdout_passed",True) else f"Strategy {sid} FAILED Walk-Forward V2")
        return status

    def _load_data(self)->Optional[pd.DataFrame]:
        raw_dir=DATA_DIR/"raw"; candidates=sorted(raw_dir.glob("XAUUSD_M1*.csv"),key=lambda p:p.stat().st_size,reverse=True)
        if not candidates: self.logger.warning("No XAUUSD_M1*.csv found in data/raw/"); return None
        csv_path=candidates[0]; mtime=csv_path.stat().st_mtime
        if self._data_cache is not None:
            if getattr(self,"_data_mtime",None)==mtime: return self._data_cache
            self._data_cache=None; self._data_cache_m5=None; self._df_m5_pickle=None
        self._data_mtime=mtime; df=pd.read_csv(csv_path,parse_dates=["time"])
        rename_map={"open":"Open","high":"High","low":"Low","close":"Close","tick_volume":"Volume","volume":"Volume"}
        df=df.rename(columns={k:v for k,v in rename_map.items() if k in df.columns}).sort_values("time").reset_index(drop=True)
        self._data_hash=hashlib.md5(csv_path.read_bytes()).hexdigest(); self._data_cache=df; return df

    def _load_data_m5(self)->Optional[pd.DataFrame]:
        df_m1=self._load_data()
        if df_m1 is None:return None
        if self._data_cache_m5 is not None:return self._data_cache_m5
        df=df_m1.copy().set_index("time"); agg={"Open":"first","High":"max","Low":"min","Close":"last","Volume":"sum"}
        if "spread" in df.columns:agg["spread"]="max"
        self._data_cache_m5=df.resample("5min").agg(agg).dropna().reset_index(); return self._data_cache_m5

    def _is_m5_strategy(self,strategy_id:str)->bool:return True

    def _measured_slippage(self)->Optional[float]:
        import time as _time
        now=_time.time()
        if getattr(self,"_slip_cache_time",0)>now-3600:return getattr(self,"_slip_cache",None)
        vals=[]
        for r in self.db.fetchall("SELECT metadata FROM events WHERE event_type = 'trade_open' AND metadata LIKE '%\"slippage\"%'"):
            try:
                m=json.loads(r["metadata"]) if r["metadata"] else {}; s=m.get("slippage")
                if s is not None:vals.append(float(s))
            except (json.JSONDecodeError,TypeError,ValueError):continue
        self._slip_cache=float(np.median(vals)) if len(vals)>=20 else None; self._slip_cache_time=now; return self._slip_cache

    def _resolve_strategy_path(self,strategy_id:str)->Optional[Path]:
        row=self.db.fetchone("SELECT file_path FROM strategies WHERE id = ?",(strategy_id,)); candidate_paths=[]
        if row and row["file_path"]:
            db_path=Path(row["file_path"]); candidate_paths.extend([db_path,DATA_DIR.parent/db_path])
        candidate_paths.append(STRATEGIES_DIR/f"strategy_{strategy_id.lower()}.py")
        return next((p for p in candidate_paths if p.exists()),None)

    def _load_strategy_module(self,strategy_id:str):
        module_path=self._resolve_strategy_path(strategy_id)
        if module_path is None:return None
        try:
            spec=importlib.util.spec_from_file_location(f"strategy_{strategy_id.lower()}",str(module_path)); module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module); return module
        except Exception:return None

    def _build_signal_series(self,df:pd.DataFrame,module)->tuple:
        params=getattr(module,"PARAMS",{}); sl_atr=params.get("sl_atr",1.5); tp_atr=params.get("tp_atr",2.5); result_df=module.generate_signals(df.copy(),params)
        if "signal" not in result_df.columns or "ATR" not in result_df.columns:return None
        signals=result_df["signal"]; atr=result_df["ATR"]; close=result_df["Close"]
        sl_prices=pd.Series(np.nan,index=df.index); tp_prices=pd.Series(np.nan,index=df.index); directions=pd.Series(0,index=df.index)
        long_mask=signals==1; short_mask=signals==-1
        sl_prices[long_mask]=close[long_mask]-sl_atr*atr[long_mask]; tp_prices[long_mask]=close[long_mask]+tp_atr*atr[long_mask]
        sl_prices[short_mask]=close[short_mask]+sl_atr*atr[short_mask]; tp_prices[short_mask]=close[short_mask]-tp_atr*atr[short_mask]
        directions[long_mask]=1; directions[short_mask]=-1; return signals,sl_prices,tp_prices,directions

    def run_single_backtest(self,strategy_id:str)->Optional[dict]:
        row_check=self.db.fetchone("SELECT status FROM strategies WHERE id = ?",(strategy_id,))
        if row_check and row_check["status"] in ("validated","rejected","retired","portfolio_reserve"):return None
        df=self._load_data_m5()
        if df is None:return None
        if self._df_m5_pickle is None:
            import pickle; self._df_m5_pickle=pickle.dumps(df)
        file_path=self._resolve_strategy_path(strategy_id)
        if file_path is None:self._mark_rejected(strategy_id,"file_missing");return None
        result=_backtest_worker(strategy_id,str(file_path),self._df_m5_pickle,self._data_hash,self._measured_slippage()); self._apply_worker_result(result); return _strip_equity(result.get("metrics") or {})

    def _revalidate_deployed(self):
        from core.config import REVALIDATION_DAYS
        row=self.db.fetchone("SELECT s.id FROM strategies s WHERE s.status = 'validated' AND s.walk_forward_passed = 1 AND NOT EXISTS (SELECT 1 FROM backtest_results b WHERE b.strategy_id = s.id " f"AND b.run_at >= datetime('now', '-{int(REVALIDATION_DAYS)} days')) LIMIT 1")
        if not row:return
        sid=row["id"]; df=self._load_data_m5()
        if df is None:return
        if self._df_m5_pickle is None:
            import pickle; self._df_m5_pickle=pickle.dumps(df)
        file_path=self._resolve_strategy_path(sid)
        if file_path is None:self._demote_deployed(sid,"revalidation: file_missing");return
        result=_backtest_worker(sid,str(file_path),self._df_m5_pickle,self._data_hash,self._measured_slippage()); status=result.get("status"); metrics=result.get("metrics") or {}; still_good=status=="validated" and result.get("wf_passed",False)
        self._store_results(sid,metrics,{})
        if metrics:self._update_strategy_metrics(sid,metrics)
        if result.get("validation_v2"):self._merge_best_config(sid,"validation_v2",result["validation_v2"])
        if not still_good:self._demote_deployed(sid,f"revalidation_failed: {result.get('reason') or ', '.join(result.get('fails',[])) or status}")

    def _demote_deployed(self,strategy_id:str,reason:str):
        self.db.execute("UPDATE strategies SET walk_forward_passed = 0 WHERE id = ?",(strategy_id,)); self.emit_event("warning",f"Strategy {strategy_id} UNDEPLOYED: failed periodic re-validation ({reason})",metadata={"strategy_id":strategy_id,"reason":reason})

    def _merge_best_config(self,strategy_id:str,key:str,value):
        row=self.db.fetchone("SELECT best_config FROM strategies WHERE id = ?",(strategy_id,)); config={}
        if row and row["best_config"]:
            try:config=json.loads(row["best_config"]) if isinstance(row["best_config"],str) else row["best_config"]
            except (json.JSONDecodeError,TypeError):pass
        config[key]=value
        if key=="validation_v2" and value.get("passed"):config["metric_refresh_pending"]=False
        self.db.execute("UPDATE strategies SET best_config = ? WHERE id = ?",(json.dumps(config),strategy_id))

    def _mark_probation(self,strategy_id:str):
        row=self.db.fetchone("SELECT best_config FROM strategies WHERE id = ?",(strategy_id,)); config={}
        if row and row["best_config"]:
            try:config=json.loads(row["best_config"]) if isinstance(row["best_config"],str) else row["best_config"]
            except (json.JSONDecodeError,TypeError):pass
        config["probation"]=True; self.db.execute("UPDATE strategies SET best_config = ? WHERE id = ?",(json.dumps(config),strategy_id)); self.db.execute("INSERT INTO strategy_live_stats (strategy_id, confidence_score) VALUES (?, 40.0) ON CONFLICT(strategy_id) DO UPDATE SET confidence_score = 40.0",(strategy_id,))

    def _mark_rejected(self,strategy_id:str,reason:str):
        self.db.execute("UPDATE strategies SET status = 'rejected' WHERE id = ?",(strategy_id,))

    def _store_results(self,strategy_id:str,metrics:dict,regime_results:dict):
        self.db.execute("INSERT INTO backtest_results (strategy_id, risk_pct, config, total_trades, win_rate, profit_factor, max_drawdown, x10_count, final_balance, return_pct, blown_account, regime_results, walk_forward, data_hash) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",(
            strategy_id,DEFAULT_RISK_PCT,None,metrics.get("total_trades",0),metrics.get("win_rate",0.0),metrics.get("profit_factor",0.0),metrics.get("max_drawdown",0.0),metrics.get("x10_count",0),metrics.get("final_balance",0.0),metrics.get("return_pct",0.0),1 if metrics.get("blown_account") else 0,json.dumps(regime_results),0,self._data_hash))

    def _update_strategy_metrics(self,strategy_id:str,metrics:dict):
        row=self.db.fetchone("SELECT best_win_rate, best_profit_factor, best_max_drawdown, best_x10_count, best_final_balance FROM strategies WHERE id = ?",(strategy_id,))
        if row is None:return
        current_pf=row["best_profit_factor"] or 0.0; new_pf=metrics.get("profit_factor",0.0)
        if new_pf>current_pf:
            self.db.execute("UPDATE strategies SET best_win_rate = ?, best_profit_factor = ?, best_max_drawdown = ?, best_x10_count = ?, best_final_balance = ? WHERE id = ?",(metrics.get("win_rate"),metrics.get("profit_factor"),metrics.get("max_drawdown"),metrics.get("x10_count"),metrics.get("final_balance"),strategy_id))
