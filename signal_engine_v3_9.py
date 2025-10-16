
# signal_engine_v3_9.py
from __future__ import annotations
from dataclasses import dataclass
from typing import Literal, Optional, Dict, Any
import os, csv, json, datetime as dt
import copy

Dir = Literal["LONG","SHORT"]
TF  = Literal["1m","3m","5m"]
Session = Literal["Asia","London","NY"]

ARCHETYPES = [
    "Asia_London_NY_Continuation",
    "London_High_Reversal",
    "PDH_PDL_Trap",
    "MidSession_Internal",
    "HTF_POI_Sweep",
    "NY_Low_Reversal",
]

SWEEP_TYPES = [
    "London_Low","London_High",
    "Asia_Low","Asia_High",
    "PDL","PDH",
    "Midnight_Low","Midnight_High",
    "Settlement_Low","Settlement_High",
    "Other"
]

_SWEEP_PROFILES_DEFAULT: Dict[str, Dict[str, Any]] = {
  "Asia_London_NY_Continuation": {
      "bias_mode":"continuation","adx_min":24,"post_sweep_delay":3,
      "require_vwap_flip":False,"expected_vwap":"support",
      "grade_weights":{"sweep":30,"mss":20,"vwap":20,"adx":15,"bias":15},
      "notes":"Asia/London sweep -> NY continuation. VWAP support; ADX>~24; delay≈3."
  },
  "London_High_Reversal": {
      "bias_mode":"reversal","adx_min":25,"post_sweep_delay":4,
      "require_vwap_flip":True,"expected_vwap":"resistance",
      "grade_weights":{"sweep":25,"mss":20,"vwap":25,"adx":15,"bias":15},
      "notes":"London premium -> NY fade. VWAP rejection; bearish MSS."
  },
  "PDH_PDL_Trap": {
      "bias_mode":"reversal","adx_min":27,"post_sweep_delay":2,
      "require_vwap_flip":True,"expected_vwap":"flip",
      "grade_weights":{"sweep":35,"mss":25,"vwap":15,"adx":10,"bias":15},
      "notes":"Prior Day extreme trap; flip back through VWAP + MSS."
  },
  "MidSession_Internal": {
      "bias_mode":"reversal","adx_min":24,"post_sweep_delay":1,
      "require_vwap_flip":True,"expected_vwap":"flip",
      "grade_weights":{"sweep":25,"mss":20,"vwap":20,"adx":20,"bias":15},
      "notes":"IB high/low sweep 10:15–10:45 ET; micro-FVG + VWAP flip + MSS."
  },
  "HTF_POI_Sweep": {
      "bias_mode":"reversal","adx_min":20,"post_sweep_delay":4,
      "require_vwap_flip":True,"expected_vwap":"reclaim",
      "grade_weights":{"sweep":30,"mss":15,"vwap":20,"adx":20,"bias":15},
      "notes":"HTF POI sweep (1H/4H). VWAP reclaim + structure shift."
  },
  "NY_Low_Reversal": {
      "bias_mode":"reversal","adx_min":20,"post_sweep_delay":3,
      "require_vwap_flip":True,"expected_vwap":"reclaim",
      "grade_weights":{"sweep":30,"mss":20,"vwap":20,"adx":20,"bias":10},
      "notes":"NY sweeps the London (or prior) Low, reclaims VWAP, then reverses LONG."
  }
}
SWEEP_PROFILES = copy.deepcopy(_SWEEP_PROFILES_DEFAULT)

def defaults_for(model:str)->Dict[str,Any]:
    return copy.deepcopy(_SWEEP_PROFILES_DEFAULT[model])

def reset_model_to_defaults(model:str):
    SWEEP_PROFILES[model] = defaults_for(model)

def load_profiles_from_excel(df):
    if df is None or df.empty: 
        return
    for _, row in df.iterrows():
        arche = row.get("Archetype")
        if not isinstance(arche, str) or arche not in SWEEP_PROFILES:
            continue
        prof = SWEEP_PROFILES[arche]
        try:
            avg_adx = float(row.get("Avg_ADX_Entry"))
            if avg_adx>0: prof["adx_min"] = max(18.0, round(avg_adx - 2))
        except: pass
        try:
            vrec = float(row.get("VWAP_reclaim/support") or 0)
            vrej = float(row.get("VWAP_rejection/resistance") or 0)
            vflip= float(row.get("VWAP_flip/cross") or 0)
            if vrej >= vrec and vrej >= vflip:
                prof["expected_vwap"] = "resistance"; prof["require_vwap_flip"]=True
            elif vflip >= vrec and vflip >= vrej:
                prof["expected_vwap"] = "flip"; prof["require_vwap_flip"]=True
            else:
                prof["expected_vwap"] = "support"; 
                if prof.get("bias_mode")=="continuation": prof["require_vwap_flip"]=False
        except: pass

def dump_profiles_to_json(path:str):
    dirpath = os.path.dirname(path)
    if dirpath and not os.path.exists(dirpath):
        os.makedirs(dirpath, exist_ok=True)
    with open(path,"w") as f: json.dump(SWEEP_PROFILES, f, indent=2)

def load_profiles_from_json(path:str):
    if not os.path.exists(path): return
    with open(path) as f: data = json.load(f)
    for k,v in data.items():
        if k in SWEEP_PROFILES and isinstance(v, dict):
            SWEEP_PROFILES[k].update(v)

from dataclasses import dataclass
@dataclass
class Inputs:
    price: float; vwap_side: Literal["ABOVE","BELOW","TOUCHING"]; vwap_slope: Literal["UP","DOWN","FLAT"]
    adx_now: float; adx_sma3: float; adx_sma6: float; adx_kill: float = 20.0
    session: Session = "NY"; mss_tf: TF = "3m"; mss_dir: Optional[Dir] = None
    htf_60m_bias: Literal["BULL","BEAR","NEUTRAL"] = "NEUTRAL"
    ltf_15m_bias: Literal["BULL","BEAR","NEUTRAL"] = "NEUTRAL"
    ltf_3m_bias:  Literal["BULL","BEAR","NEUTRAL"] = "NEUTRAL"
    liquidity_model: str = "Asia_London_NY_Continuation"
    sweep_type: Optional[str] = None; bars_since_sweep: int = 5; post_sweep_delay: int = 3
    require_vwap_flip: bool = True; micro_fvg_present: bool = True; adx_min: float = 28.0; adx_slope_min: float = 0.0

def vwap_gate(expected, side, slope): 
    if expected=="support": return side=="ABOVE"
    if expected=="resistance": return side=="BELOW"
    if expected in ("flip","reclaim"): return slope in ("UP","DOWN")
    return True

def bias_gate(htf,l15,l3,mode,desired):
    if mode=="continuation":
        return (desired=="LONG" and l15=="BULL" and l3=="BULL") or (desired=="SHORT" and l15=="BEAR" and l3=="BEAR")
    return (desired=="LONG" and l15=="BULL" and l3=="BULL" and htf!="BULL") or (desired=="SHORT" and l15=="BEAR" and l3=="BEAR" and htf!="BEAR")

def auto_model_from_context(session, sweep_type, desired):
    if session=="NY" and sweep_type in ("London_Low","PDL","Midnight_Low","Settlement_Low") and desired=="LONG": return "NY_Low_Reversal"
    if session=="NY" and sweep_type in ("London_High","PDH","Midnight_High","Settlement_High") and desired=="SHORT": return "London_High_Reversal"
    if session=="NY" and sweep_type in ("Asia_Low","Asia_High"): return "Asia_London_NY_Continuation"
    return None

def evaluate_signal(desired, inp:Inputs, profiles=None):
    profiles = profiles or SWEEP_PROFILES
    rec = auto_model_from_context(inp.session, inp.sweep_type or "Other", desired)
    model_name = rec or inp.liquidity_model
    prof = profiles.get(model_name, SWEEP_PROFILES["Asia_London_NY_Continuation"])
    adx_slope = inp.adx_sma3 - inp.adx_sma6
    adx_ok = (inp.adx_now >= max(inp.adx_min, prof.get("adx_min",24))) and (adx_slope >= inp.adx_slope_min)
    delay_ok = inp.bars_since_sweep >= prof.get("post_sweep_delay", inp.post_sweep_delay)
    mss_ok = (inp.mss_dir == desired)
    vwap_ok = vwap_gate(prof.get("expected_vwap","support"), inp.vwap_side, inp.vwap_slope) if prof.get("require_vwap_flip", True) else True
    bias_ok = bias_gate(inp.htf_60m_bias, inp.ltf_15m_bias, inp.ltf_3m_bias, prof.get("bias_mode","continuation"), desired)
    micro_ok = bool(inp.micro_fvg_present)
    entry_ready = all([delay_ok, mss_ok, vwap_ok, adx_ok, bias_ok, micro_ok])
    w = prof.get("grade_weights", {"sweep":30,"mss":20,"vwap":20,"adx":15,"bias":15})
    grade = min(100, int(round(w["sweep"]*1 + w["mss"]*int(mss_ok) + w["vwap"]*int(vwap_ok) + w["adx"]*int(adx_ok) + w["bias"]*int(bias_ok))))
    return {"model_used": model_name, "entry_ready": entry_ready, "grade": grade,
            "components": {"delay_ok":delay_ok,"mss_ok":mss_ok,"vwap_ok":vwap_ok,"adx_ok":adx_ok,
                           "bias_ok":bias_ok,"micro_ok":micro_ok,"adx_slope":round(adx_slope,2),
                           "profile_adx_min":prof.get("adx_min"),"expected_vwap":prof.get("expected_vwap")},
            "profile": prof}

def log_signal_csv(path, model, desired, res, inp:Inputs):
    dirp = os.path.dirname(path)
    if dirp and not os.path.exists(dirp):
        os.makedirs(dirp, exist_ok=True)
    headers = ["timestamp","session","model","sweep_type","direction","grade","entry_ready",
               "adx_now","adx_slope","vwap_side","vwap_slope","htf","l15","l3"]
    row = {"timestamp": dt.datetime.utcnow().isoformat(),
        "session": inp.session, "model": res.get("model_used", model),
        "sweep_type": inp.sweep_type, "direction": desired,
        "grade": res.get("grade"), "entry_ready": res.get("entry_ready"),
        "adx_now": inp.adx_now, "adx_slope": round(inp.adx_sma3 - inp.adx_sma6,2),
        "vwap_side": inp.vwap_side, "vwap_slope": inp.vwap_slope,
        "htf": inp.htf_60m_bias, "l15": inp.ltf_15m_bias, "l3": inp.ltf_3m_bias}
    write_header = not os.path.exists(path)
    with open(path,"a",newline="") as f:
        w = csv.DictWriter(f, fieldnames=headers)
        if write_header: w.writeheader()
        w.writerow(row)
