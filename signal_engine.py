
from dataclasses import dataclass
from typing import Literal, Optional, Dict, Any

Dir = Literal["LONG", "SHORT"]
TF  = Literal["1m", "3m", "5m"]
Sweep = Literal["None","Asia Low","Asia High","London Low","London High","PDH","PDL"]

@dataclass
class Inputs:
    price: float
    vwap: float
    vwap_slope: Literal["UP","DOWN","FLAT"]
    vwap_side: Literal["ABOVE","BELOW","TOUCHING"]
    adx_now: float
    adx_sma3: float
    adx_sma6: float
    adx_kill: float = 20.0
    mss_tf: TF = "3m"
    mss_dir: Optional[Dir] = None
    htf_60m_bias: Literal["BULL","BEAR","NEUTRAL"] = "NEUTRAL"
    ltf_15m_bias: Literal["BULL","BEAR","NEUTRAL"] = "NEUTRAL"
    ltf_3m_bias:  Literal["BULL","BEAR","NEUTRAL"] = "NEUTRAL"
    sweep_type: Sweep = "None"
    bars_since_sweep: int = 99
    post_sweep_delay: int = 3
    require_vwap_flip: bool = True
    poi_type: Literal["15M_FVG","15M_OB","1H_FVG","1H_OB","Other"] = "15M_FVG"
    poi_dir: Optional[Dir] = None
    micro_fvg_present: bool = True
    adx_min: float = 28.0
    adx_slope_min: float = 0.0

def vwap_flip_in_dir(vwap_side: str, desired: Dir) -> bool:
    return (vwap_side == "ABOVE" and desired == "LONG") or (vwap_side == "BELOW" and desired == "SHORT")

def score_adx(adx_now: float, slope: float, adx_min: float) -> int:
    lvl = max(0.0, min(1.0, (adx_now - adx_min) / 10.0))
    slp = 1.0 if slope > 0 else 0.0
    return int(round(10*lvl + 5*slp))

def bias_rule_ok(htf: str, l15: str, l3: str, mode: Literal["continuation","reversal"]) -> bool:
    if mode == "continuation":
        return not ({l15, l3} & {"NEUTRAL"}) and l15 == l3
    else:
        return (l15 == l3) and (htf != l15)

def evaluate_signal(desired: Dir, inp: Inputs, bias_mode: Literal["continuation","reversal"]="continuation") -> Dict[str, Any]:
    sweep_ok = inp.sweep_type != "None"
    delay_ok = inp.bars_since_sweep >= inp.post_sweep_delay
    mss_ok   = (inp.mss_dir == desired)
    vwap_ok  = (not inp.require_vwap_flip) or vwap_flip_in_dir(inp.vwap_side, desired)
    adx_slope = inp.adx_sma3 - inp.adx_sma6
    adx_ok   = (inp.adx_now >= inp.adx_min) and (adx_slope >= inp.adx_slope_min)
    poi_ok   = (inp.poi_dir == desired) and (inp.micro_fvg_present)
    bias_ok  = bias_rule_ok(inp.htf_60m_bias, inp.ltf_15m_bias, inp.ltf_3m_bias, bias_mode)

    entry_ready = all([sweep_ok, delay_ok, mss_ok, vwap_ok, adx_ok, poi_ok, bias_ok])

    grade = (
        30*int(sweep_ok) +
        20*int(mss_ok) +
        20*int(vwap_ok) +
        score_adx(inp.adx_now, adx_slope, inp.adx_min) +
        15*int(bias_ok) +
        5*int(delay_ok) +
        5*int(poi_ok)
    )
    grade = min(100, grade)

    banners = []
    if inp.adx_now < inp.adx_kill:
        banners.append("Avoid/Exit: ADX below kill threshold")
    if inp.vwap_slope == "FLAT":
        banners.append("Chop risk: VWAP flat")
    if not sweep_ok:
        banners.append("No active sweep set")

    return {
        "entry_ready": entry_ready,
        "grade": grade,
        "components": {
            "sweep_ok": sweep_ok, "delay_ok": delay_ok, "mss_ok": mss_ok,
            "vwap_ok": vwap_ok, "adx_ok": adx_ok, "poi_ok": poi_ok, "bias_ok": bias_ok,
            "adx_slope": adx_slope
        },
        "banners": banners
    }
