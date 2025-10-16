
# signal_engine_v3.py
from __future__ import annotations
from dataclasses import dataclass
from typing import Literal, Optional, Dict, Any, Tuple
import csv
import os

Dir = Literal["LONG", "SHORT"]
TF  = Literal["1m", "3m", "5m"]

# Canonical archetypes you trade
ARCHETYPES = [
    "Asia_London_NY_Continuation",
    "London_High_Reversal",
    "PDH_PDL_Trap",
    "MidSession_Internal",
    "HTF_POI_Sweep",
]

@dataclass
class Inputs:
    # market state
    price: float
    vwap_side: Literal["ABOVE","BELOW","TOUCHING"]
    vwap_slope: Literal["UP","DOWN","FLAT"]
    adx_now: float
    adx_sma3: float
    adx_sma6: float
    adx_kill: float = 20.0

    # structure
    mss_tf: TF = "3m"
    mss_dir: Optional[Dir] = None  # "LONG" or "SHORT"
    htf_60m_bias: Literal["BULL","BEAR","NEUTRAL"] = "NEUTRAL"
    ltf_15m_bias: Literal["BULL","BEAR","NEUTRAL"] = "NEUTRAL"
    ltf_3m_bias:  Literal["BULL","BEAR","NEUTRAL"] = "NEUTRAL"

    # sweep/meta
    liquidity_model: str = "Asia_London_NY_Continuation"
    sweep_type: Optional[str] = None
    bars_since_sweep: int = 5
    post_sweep_delay: int = 3
    require_vwap_flip: bool = True

    # poi micro-confluence
    micro_fvg_present: bool = True

    # thresholds
    adx_min: float = 28.0
    adx_slope_min: float = 0.0

# Default, data-driven-ish profiles (will be overridden if Excel summary present)
SWEEP_PROFILES: Dict[str, Dict[str, Any]] = {
  "Asia_London_NY_Continuation": {
      "bias_mode": "continuation",
      "adx_min": 24, "post_sweep_delay": 3,
      "require_vwap_flip": False,
      "expected_vwap": "support",
      "grade_weights": {"sweep":30,"mss":20,"vwap":20,"adx":15,"bias":15}
  },
  "London_High_Reversal": {
      "bias_mode": "reversal",
      "adx_min": 25, "post_sweep_delay": 4,
      "require_vwap_flip": True,
      "expected_vwap": "resistance",
      "grade_weights": {"sweep":25,"mss":20,"vwap":25,"adx":15,"bias":15}
  },
  "PDH_PDL_Trap": {
      "bias_mode": "reversal",
      "adx_min": 27, "post_sweep_delay": 2,
      "require_vwap_flip": True,
      "expected_vwap": "flip",
      "grade_weights": {"sweep":35,"mss":25,"vwap":15,"adx":10,"bias":15}
  },
  "MidSession_Internal": {
      "bias_mode": "reversal",
      "adx_min": 24, "post_sweep_delay": 1,
      "require_vwap_flip": True,
      "expected_vwap": "flip",
      "grade_weights": {"sweep":25,"mss":20,"vwap":20,"adx":20,"bias":15}
  },
  "HTF_POI_Sweep": {
      "bias_mode": "reversal",
      "adx_min": 20, "post_sweep_delay": 4,
      "require_vwap_flip": True,
      "expected_vwap": "reclaim",
      "grade_weights": {"sweep":30,"mss":15,"vwap":20,"adx":20,"bias":15}
  }
}

def load_profiles_from_excel(summary_df) -> None:
    """
    Accepts a pandas DataFrame from the 'Model Summary' sheet
    with columns: Archetype, Avg_ADX_Entry, VWAP_* percentages, WinRate_%, etc.
    This will adapt SWEEP_PROFILES thresholds.
    """
    if summary_df is None or summary_df.empty:
        return
    for _, row in summary_df.iterrows():
        arche = row.get("Archetype")
        if not isinstance(arche, str):
            continue
        if arche not in SWEEP_PROFILES:
            continue
        prof = SWEEP_PROFILES[arche]
        # Adapt ADX min
        try:
            avg_adx = float(row.get("Avg_ADX_Entry"))
            if avg_adx > 0:
                prof["adx_min"] = max(19.0, round(avg_adx - 2))  # a tad below avg to allow ignition
        except Exception:
            pass
        # Decide VWAP expectation
        v_reclaim = float(row.get("VWAP_reclaim/support", 0) or 0)
        v_reject  = float(row.get("VWAP_rejection/resistance", 0) or 0)
        v_flip    = float(row.get("VWAP_flip/cross", 0) or 0)
        if v_reject >= v_reclaim and v_reject >= v_flip:
            prof["expected_vwap"] = "resistance"
            prof["require_vwap_flip"] = True
        elif v_flip >= v_reclaim and v_flip >= v_reject:
            prof["expected_vwap"] = "flip"
            prof["require_vwap_flip"] = True
        else:
            prof["expected_vwap"] = "support"
            # continuation models often don't require a strict flip
            if prof.get("bias_mode") == "continuation":
                prof["require_vwap_flip"] = False

def vwap_ok(expected: str, vwap_side: str, vwap_slope: str, desired: Dir) -> bool:
    if expected == "support":
        return vwap_side == "ABOVE"
    if expected == "resistance":
        return vwap_side == "BELOW"
    if expected in ("flip","reclaim"):
        # Accept either side if slope is changing away from flat
        return vwap_slope in ("UP","DOWN")
    return True

def bias_rule_ok(htf: str, l15: str, l3: str, mode: Literal["continuation","reversal"], desired: Dir) -> bool:
    if mode == "continuation":
        # LTFs aligned with desired direction; HTF may disagree
        if desired == "LONG":
            return (l15 == "BULL" and l3 == "BULL")
        else:
            return (l15 == "BEAR" and l3 == "BEAR")
    else:
        # HTF opposite of LTFs
        if desired == "LONG":
            return (l15 == "BULL" and l3 == "BULL" and htf != "BULL")
        else:
            return (l15 == "BEAR" and l3 == "BEAR" and htf != "BEAR")

def evaluate_signal(desired: Dir, inp: Inputs, profiles: Dict[str, Dict[str, Any]]|None=None):
    prof = (profiles or SWEEP_PROFILES).get(inp.liquidity_model, SWEEP_PROFILES["Asia_London_NY_Continuation"])

    adx_slope = inp.adx_sma3 - inp.adx_sma6
    adx_ok    = (inp.adx_now >= max(inp.adx_min, prof.get("adx_min", 24))) and (adx_slope >= inp.adx_slope_min)

    # Sweep gates
    sweep_ok  = True  # you already pre-tag the liquidity model and sweep event in your process
    delay_ok  = inp.bars_since_sweep >= prof.get("post_sweep_delay", inp.post_sweep_delay)

    # VWAP gate
    expected_vwap = prof.get("expected_vwap", "support")
    vwap_gate = vwap_ok(expected_vwap, inp.vwap_side, inp.vwap_slope, desired)
    vwap_flip_req = prof.get("require_vwap_flip", inp.require_vwap_flip)
    vwap_okay = (not vwap_flip_req) or vwap_gate

    # MSS gate
    mss_ok = (inp.mss_dir == desired)

    # Bias gate
    bias_ok = bias_rule_ok(inp.htf_60m_bias, inp.ltf_15m_bias, inp.ltf_3m_bias, prof.get("bias_mode","continuation"), desired)

    # Micro confluence
    micro_ok = bool(inp.micro_fvg_present)

    # Kill switch
    banners = []
    if inp.adx_kill and inp.adx_now < inp.adx_kill:
        banners.append("Avoid/Exit: ADX below kill threshold")
    if inp.vwap_slope == "FLAT":
        banners.append("Chop risk: VWAP flat")

    entry_ready = all([sweep_ok, delay_ok, mss_ok, vwap_okay, adx_ok, bias_ok, micro_ok])

    # Adaptive grade
    w = prof.get("grade_weights", {"sweep":30,"mss":20,"vwap":20,"adx":15,"bias":15})
    grade = (
        w["sweep"]*int(sweep_ok) +
        w["mss"]*int(mss_ok) +
        w["vwap"]*int(vwap_okay) +
        w["adx"] *int(adx_ok) +
        w["bias"]*int(bias_ok)
    )
    grade = min(100, int(round(grade)))

    components = {
        "sweep_ok": sweep_ok, "delay_ok": delay_ok, "mss_ok": mss_ok,
        "vwap_ok": vwap_okay, "adx_ok": adx_ok, "bias_ok": bias_ok,
        "micro_ok": micro_ok, "adx_slope": round(adx_slope,2),
        "expected_vwap": expected_vwap, "profile_adx_min": prof.get("adx_min")
    }
    return {"entry_ready": entry_ready, "grade": grade, "components": components, "banners": banners, "profile": prof}

def log_signal(log_path: str, liquidity_model: str, desired: Dir, result: Dict[str,Any], inp: Inputs) -> None:
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    headers = ["liquidity_model","direction","grade","entry_ready","adx_now","adx_slope","vwap_side","vwap_slope","htf","l15","l3"]
    row = {
        "liquidity_model": liquidity_model,
        "direction": desired,
        "grade": result.get("grade"),
        "entry_ready": result.get("entry_ready"),
        "adx_now": inp.adx_now,
        "adx_slope": round(inp.adx_sma3 - inp.adx_sma6,2),
        "vwap_side": inp.vwap_side, "vwap_slope": inp.vwap_slope,
        "htf": inp.htf_60m_bias, "l15": inp.ltf_15m_bias, "l3": inp.ltf_3m_bias
    }
    write_header = not os.path.exists(log_path)
    with open(log_path, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=headers)
        if write_header:
            w.writeheader()
        w.writerow(row)
