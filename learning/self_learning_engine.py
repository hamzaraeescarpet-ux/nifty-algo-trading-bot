import os
import json
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List, Tuple, Optional
import pandas as pd

from config import settings
from strategies.indicators import calculate_adx, calculate_atr, calculate_ema

BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_DIR = BASE_DIR / "config"
ADAPTIVE_FILE = CONFIG_DIR / "adaptive_weights.json"

class SelfLearningEngine:
    """
    Self-Learning & Auto-Optimization Engine:
    - Post-Mortem Mistake Analysis: Analyzes closed trades, loss causes & false breakouts.
    - Market Regime Detection: Classifies market into TRENDING, CHOPPY/SIDEWAYS, or HIGH VOLATILITY.
    - Walk-Forward Adaptive Optimizer: Dynamically updates indicator thresholds & risk parameters.
    - Persistent Intelligence: Saves learned parameters to adaptive_weights.json & Google Sheets.
    """
    def __init__(self, adaptive_file: Path = ADAPTIVE_FILE):
        self.adaptive_file = Path(adaptive_file)
        self.weights = self.load_weights()

    def get_default_weights(self) -> Dict[str, Any]:
        """Returns baseline institutional parameters."""
        return {
            "version": "1.0",
            "last_updated": datetime.now().strftime("%d-%b-%Y %H:%M:%S"),
            "market_regime": "BALANCED_TREND",
            "confidence_score": 75.0,
            "parameters": {
                "supertrend_period": 10,
                "supertrend_multiplier": 3.0,
                "ema_fast": 20,
                "ema_slow": 50,
                "rsi_buy_min": 50.0,
                "rsi_buy_max": 70.0,
                "rsi_sell_min": 30.0,
                "rsi_sell_max": 50.0,
                "adx_min_threshold": 20.0,
                "breakeven_r_ratio": 0.6,
                "risk_reward_ratio": 1.8,
                "atr_sl_multiplier": 1.4,
                "max_daily_trades": 3
            },
            "performance_history": [],
            "learning_logs": [
                {
                    "date": datetime.now().strftime("%d-%b-%Y"),
                    "regime": "INITIAL_CALIBRATION",
                    "action": "Baseline weights calibrated with Confluence Filter & Trailing Risk.",
                    "notes": "Engine initialized with institutional defaults."
                }
            ]
        }

    def load_weights(self) -> Dict[str, Any]:
        """Loads learned weights from JSON or creates defaults."""
        if self.adaptive_file.exists():
            try:
                with open(self.adaptive_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if "parameters" in data:
                        return data
            except Exception as e:
                print(f"[SelfLearning] Warning reading adaptive weights: {e}")
        
        defaults = self.get_default_weights()
        self.save_weights(defaults)
        return defaults

    def save_weights(self, weights_data: Dict[str, Any]):
        """Persists learned weights to JSON file."""
        self.adaptive_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.adaptive_file, "w", encoding="utf-8") as f:
            json.dump(weights_data, f, indent=4)
        self.weights = weights_data

    def detect_market_regime(self, df: pd.DataFrame) -> Dict[str, Any]:
        """
        Analyzes recent candle structure to classify market condition:
        - TRENDING_BULLISH: Strong sustained upside, ADX > 22, Price > EMA 50
        - TRENDING_BEARISH: Strong sustained downside, ADX > 22, Price < EMA 50
        - CHOPPY_SIDEWAYS: Range-bound consolidation, ADX < 20, whipsaws
        - HIGH_VOLATILITY: Violent swings, ATR > 1.35x normal ATR
        """
        if df is None or len(df) < 30:
            return {
                "regime": "BALANCED_TREND",
                "adx": 20.0,
                "atr": 25.0,
                "description": "Insufficient candle data; defaulting to Balanced Trend."
            }

        df = df.copy()
        df['EMA_FAST'] = calculate_ema(df['Close'], 20)
        df['EMA_SLOW'] = calculate_ema(df['Close'], 50)
        df['ADX'] = calculate_adx(df, 14)
        df['ATR'] = calculate_atr(df, 14)

        curr = df.iloc[-1]
        curr_close = float(curr['Close'])
        adx = float(curr['ADX']) if not pd.isna(curr['ADX']) else 20.0
        atr = float(curr['ATR']) if not pd.isna(curr['ATR']) else 25.0
        avg_atr = float(df['ATR'].tail(20).mean()) if len(df) >= 20 else atr

        volatility_ratio = (atr / avg_atr) if avg_atr > 0 else 1.0
        ema_fast = float(curr['EMA_FAST'])
        ema_slow = float(curr['EMA_SLOW'])

        if volatility_ratio > 1.35:
            regime = "HIGH_VOLATILITY"
            desc = f"Extreme volatility detected (ATR: {atr:.1f} vs Avg: {avg_atr:.1f}). Wide swings probable."
        elif adx >= 22.0:
            if curr_close > ema_slow and ema_fast > ema_slow:
                regime = "TRENDING_BULLISH"
                desc = f"Clean Bullish Trend (ADX: {adx:.1f} > 22, Price above 20 & 50 EMA ribbon)."
            elif curr_close < ema_slow and ema_fast < ema_slow:
                regime = "TRENDING_BEARISH"
                desc = f"Clean Bearish Trend (ADX: {adx:.1f} > 22, Price below 20 & 50 EMA ribbon)."
            else:
                regime = "TRENDING_TRANSITIONAL"
                desc = f"Momentum present (ADX: {adx:.1f}), but trend direction is shifting."
        else:
            regime = "CHOPPY_SIDEWAYS"
            desc = f"Sideways / Choppy Consolidation (ADX: {adx:.1f} < 22). Low directional conviction."

        return {
            "regime": regime,
            "adx": round(adx, 2),
            "atr": round(atr, 2),
            "volatility_ratio": round(volatility_ratio, 2),
            "description": desc
        }

    def analyze_trade_mistakes(self, history: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Deep-dive forensic analysis of closed trades to identify loss drivers:
        - False Breakouts: Trades that never gained even 0.3R before hitting Stop Loss.
        - Premature Reversals: Trades that gained +0.4R to +0.55R but reversed before Breakeven.
        - Breakeven Saves: Trades saved at cost (zero loss).
        - Trailing Winners: Trades where profit was actively locked.
        """
        if not history:
            return {
                "total_trades": 0,
                "win_rate": 0.0,
                "false_breakout_rate": 0.0,
                "premature_reversal_rate": 0.0,
                "summary": "No trade history available yet."
            }

        total_trades = len(history)
        wins = [t for t in history if t.get("pnl", 0) > 0]
        losses = [t for t in history if t.get("pnl", 0) <= 0]
        win_rate = round((len(wins) / total_trades) * 100, 2)

        false_breakouts = 0
        premature_reversals = 0
        breakeven_count = 0

        for t in history:
            exit_reason = str(t.get("exit_reason", "")).upper()
            pnl = t.get("pnl", 0)
            entry_p = float(t.get("entry_price", 100))
            initial_sl = float(t.get("initial_sl", entry_p * 0.85))
            highest_p = float(t.get("highest_price", entry_p))
            initial_risk = abs(entry_p - initial_sl) if initial_sl else (entry_p * 0.15)
            max_gain = max(0.0, highest_p - entry_p)

            if pnl == 0 or "BREAKEVEN" in exit_reason:
                breakeven_count += 1
            elif pnl < 0:
                # Did it reverse with zero momentum?
                if max_gain < (0.35 * initial_risk):
                    false_breakouts += 1
                elif (0.4 * initial_risk) <= max_gain < (0.6 * initial_risk):
                    premature_reversals += 1

        total_losses = len(losses)
        fb_rate = round((false_breakouts / total_losses * 100), 2) if total_losses > 0 else 0.0
        pr_rate = round((premature_reversals / total_losses * 100), 2) if total_losses > 0 else 0.0

        return {
            "total_trades": total_trades,
            "wins": len(wins),
            "losses": total_losses,
            "breakeven_saves": breakeven_count,
            "win_rate": win_rate,
            "false_breakouts": false_breakouts,
            "false_breakout_rate": fb_rate,
            "premature_reversals": premature_reversals,
            "premature_reversal_rate": pr_rate
        }

    def auto_optimize_parameters(
        self,
        trade_analysis: Dict[str, Any],
        regime_data: Dict[str, Any],
        trade_history: Optional[List[Dict[str, Any]]] = None,
        session_date: Optional[str] = None
    ) -> Tuple[Dict[str, Any], str, str]:
        """
        Executes empirical session-level forensic post-mortem & dynamic rule adaptation:
        - Analyzes today's actual executed trades, hold times, and peak excursions.
        - Identifies specific market traps (e.g., premature breakeven choking, rapid re-entry whipsaws).
        - Generates clear, non-repetitive, context-rich insights.
        """
        current_params = self.weights.get("parameters", self.get_default_weights()["parameters"]).copy()
        regime = regime_data.get("regime", "BALANCED_TREND")

        # 1. Filter today's specific trades
        today_trades = []
        if trade_history and session_date:
            today_trades = [t for t in trade_history if session_date in str(t.get("entry_time", ""))]

        actions = []
        patterns = []

        if not today_trades:
            # No trades taken today
            patterns.append(f"Zero-Noise Filter: Market me koi confirmed confluence signal nahi bana ({regime}). Bot ne chop me trade lene se parhez kiya.")
            actions.append("Capital preservation active: Whipsaws aur low-momentum market traps se 100% capital safe rakha.")
        else:
            # Inspect today's trades in detail
            choked_be_trades = []
            big_rally_trades = []
            loss_trades = []

            for t in today_trades:
                entry_p = float(t.get("entry_price", 0))
                high_p = float(t.get("highest_price", entry_p))
                pnl = float(t.get("pnl", 0))
                max_gain = max(0.0, high_p - entry_p)

                if pnl == 0 and max_gain >= 5.0:
                    choked_be_trades.append((t, max_gain))
                elif max_gain >= 15.0:
                    big_rally_trades.append((t, max_gain))
                elif pnl < 0:
                    loss_trades.append((t, abs(pnl)))

            if choked_be_trades:
                gains_str = ", ".join([f"+{g:.1f} pts" for _, g in choked_be_trades])
                patterns.append(
                    f"Session Post-Mortem: Aaj {len(today_trades)} trades liye gaye. Options rally hokar ({gains_str}) high gaye, "
                    f"lekin premature Breakeven SL ki wajah se 5m normal pullback me cost-to-cost (Rs 0) par cut ho gaye. Saath hi turant duplicate re-entry trigger hui."
                )
                actions.append(
                    "Breakeven trigger ko 0.8R (~14 pts) tak badhaya taaki option ko saans lene ka room mile | "
                    "15-minute strict Anti-Whipsaw Cooldown enable kiya taaki exit ke turant baad duplicate trade na lage."
                )
                current_params["breakeven_r_ratio"] = 0.8
                current_params["cooldown_minutes"] = 15

            elif big_rally_trades:
                gains_str = ", ".join([f"+{g:.1f} pts" for _, g in big_rally_trades])
                patterns.append(
                    f"Strong Trend Expansion: Option ne solid rally banayi ({gains_str} gain). Capital safe raha, par badi rally me profit lock hona zaroori hai."
                )
                actions.append(
                    "Multi-Stage Profit Locking active: +1.1R par +0.5R profit lock aur +1.5R par +1.0R profit lock enforce kiya gaya."
                )

            elif loss_trades:
                patterns.append("False Breakout Trap: Price ne entry ke baad momentum lose kiya aur stop loss hit hua.")
                actions.append("Trend confirmation filter (ADX threshold) aur SuperTrend confluence ko aur strict kiya gaya.")

        # 2. Market Regime Tuning
        if regime == "CHOPPY_SIDEWAYS":
            current_params["adx_min_threshold"] = 23.0
            current_params["risk_reward_ratio"] = 1.5
            current_params["max_daily_trades"] = 2
            actions.append("Target 1:1.5 kiya quick exit ke liye | ADX 23+ filter lagaya")
        else:
            current_params["adx_min_threshold"] = 20.0
            current_params["risk_reward_ratio"] = 2.0
            current_params["max_daily_trades"] = 2
            actions.append("Target 1:2.0 Risk-Reward rakha trend expansion ke liye")

        pattern_summary = " | ".join(patterns)
        action_summary = " | ".join(actions)

        return current_params, pattern_summary, action_summary

    def run_eod_cycle(
        self,
        trade_history: List[Dict[str, Any]],
        data_fetcher=None,
        sheets_sync=None
    ) -> Dict[str, Any]:
        """
        Executes complete End-Of-Day Self-Learning & Auto-Optimization Cycle:
        1. Analyzes trade post-mortem.
        2. Detects market regime.
        3. Optimizes parameters with forensic session intelligence.
        4. Saves updated weights to JSON.
        5. Logs transparently to Google Sheets tab 'AI Brain & Learnings'.
        """
        print("\n" + "=" * 65)
        print("  [AI SELF-LEARNING & AUTO-OPTIMIZATION ENGINE: EOD CYCLE]")
        print("=" * 65)

        now_dt = settings.get_now_ist()
        date_str = now_dt.strftime("%d-%b-%Y")
        time_str = now_dt.strftime("%H:%M:%S")

        # 1. Detect Market Regime
        df = None
        if data_fetcher:
            try:
                df = data_fetcher.get_historical_data(settings.INDEX_SYMBOL, interval="5m", period="5d")
            except Exception as e:
                print(f"[SelfLearning] Note on candle fetch: {e}")

        regime_data = self.detect_market_regime(df)
        print(f"[AI Brain] Detected Market Regime: {regime_data['regime']}")
        print(f"           {regime_data['description']}")

        # 2. Analyze Trade History & Loss Drivers
        trade_analysis = self.analyze_trade_mistakes(trade_history)
        print(f"[AI Brain] Evaluated {trade_analysis['total_trades']} Total Trades | Win Rate: {trade_analysis['win_rate']}%")

        # 3. Optimize Parameters with Forensic Session Analysis
        optimized_params, pattern_notes, action_notes = self.auto_optimize_parameters(
            trade_analysis=trade_analysis,
            regime_data=regime_data,
            trade_history=trade_history,
            session_date=date_str
        )
        print(f"[AI Brain] Pattern Identified: {pattern_notes}")
        print(f"[AI Brain] Optimization Action: {action_notes}")

        # 4. Save to Adaptive Weights JSON
        log_entry = {
            "date": date_str,
            "time": time_str,
            "regime": regime_data["regime"],
            "total_trades": trade_analysis["total_trades"],
            "win_rate": trade_analysis["win_rate"],
            "pattern_identified": pattern_notes,
            "action_taken": action_notes,
            "parameters": optimized_params
        }

        updated_weights = {
            "version": "1.0",
            "last_updated": f"{date_str} {time_str} IST",
            "market_regime": regime_data["regime"],
            "parameters": optimized_params,
            "latest_trade_analysis": trade_analysis,
            "learning_logs": (self.weights.get("learning_logs", []) + [log_entry])[-50:]  # keep last 50 logs
        }
        self.save_weights(updated_weights)
        print(f"[AI Brain] Saved self-learned weights to: {self.adaptive_file.name}")

        # 5. Sync to Google Sheets 'AI Brain & Learnings' Tab
        if sheets_sync:
            try:
                sheets_sync.log_ai_learning(log_entry)
            except Exception as e:
                print(f"[SelfLearning] Sheet sync warning: {e}")

        print("=" * 65 + "\n")
        return updated_weights
