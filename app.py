import streamlit as st
import pandas as pd
from datetime import datetime

st.set_page_config(page_title="LSF Signal Tool", page_icon="📈", layout="wide")

# --- Defaults / Config ---
TICK_SIZE_DEFAULT = 0.25    # MNQ
SIGMA_TICKS_DEFAULT = 40.0  # 1σ in ticks
ADX_THRESHOLD_DEFAULT = 22.5
DEFAULT_RISK_TICKS = 40.0

# --- Helper functions ---
def one_sigma_price(tick_size: float, sigma_ticks: float) -> float:
    return float(tick_size) * float(sigma_ticks)

def risk_ticks_used(user_ticks, default_ticks):
    try:
        if user_ticks is None or str(user_ticks).strip() == "":
            return float(default_ticks)
        return float(user_ticks)
    except:
        return float(default_ticks)

def decide_side(vals):
    """
    Decide trade side with a clear hierarchy:
    1) Base direction from HTF bias *if* CISD + POI are valid.
    2) Micro override: MSS vs VWAP (with matching VWAP side + slope).
    3) If CONTINUATION short valid, force SHORT.
    """
    side = "-"

    if vals["poi_validated"] == "YES" and vals["cisd_confirmed"] == "YES":
        side = "SHORT" if vals["htf_bias"] == "BEAR" else "LONG"

    # micro overrides
    if vals["mss_above_vwap"] == "YES" and vals["vwap_side"] == "ABOVE" and vals["vwap_slope"] == "UP":
        side = "LONG"
    if vals["mss_below_vwap"] == "YES" and vals["vwap_side"] == "BELOW" and vals["vwap_slope"] == "DOWN":
        side = "SHORT"

    # continuation short rule
    if (
        vals["mss_below_vwap"] == "YES"
        and vals["vwap_side"] == "BELOW"
        and vals["vwap_slope"] == "DOWN"
        and float(vals["adx_3m"]) > float(vals["adx_thr"])
    ):
        side = "SHORT"

    return side

def rot_valid(vals):
    return (
        vals["poi_validated"] == "YES"
        and vals["cisd_confirmed"] == "YES"
        and float(vals["adx_3m"]) > float(vals["adx_thr"])
    )

def cont_short_valid(vals):
    return (
        vals["mss_below_vwap"] == "YES"
        and vals["vwap_side"] == "BELOW"
        and vals["vwap_slope"] == "DOWN"
        and float(vals["adx_3m"]) > float(vals["adx_thr"])
    )

def compute_targets(side, basis_price, sigma_price):
    """
    basis_price: where to project deviations from (CISD, ENTRY, or VWAP)
    sigma_price: 1σ in price units
    """
    if side == "LONG":
        tp1 = basis_price + 2.5 * sigma_price
        tp2 = basis_price + 4.0  * sigma_price
    elif side == "SHORT":
        tp1 = basis_price - 2.5 * sigma_price
        tp2 = basis_price - 4.0  * sigma_price
    else:
        tp1 = tp2 = None
    return tp1, tp2

def compute_stop(side, entry, risk_ticks, tick_size):
    if side == "LONG":
        return entry - risk_ticks * tick_size
    elif side == "SHORT":
        return entry + risk_ticks * tick_size
    return None

def grade_signal(side, vals, fvg_stack_count, poi_type, adx_3m, adx_thr):
    """Return (score, letter). 0-100 scaled."""
    score = 0.0

    # CISD + POI gate
    if vals["cisd_confirmed"] == "YES" and vals["poi_validated"] == "YES":
        score += 30

    # ADX margin over threshold (cap 30)
    try:
        margin = max(0.0, float(adx_3m) - float(adx_thr))
    except:
        margin = 0.0
    score += min(30.0, margin * 1.5)  # 20 pts margin -> 30 score

    # FVG stack depth (cap 20)
    score += min(20.0, fvg_stack_count * 5.0)

    # VWAP + MSS alignment with side (cap 15; partial 7)
    vwap_side = vals["vwap_side"]; vwap_slope = vals["vwap_slope"]
    mss_above = vals["mss_above_vwap"] == "YES"
    mss_below = vals["mss_below_vwap"] == "YES"
    full = False; partial = False
    if side == "LONG":
        full = (vwap_side == "ABOVE" and vwap_slope in ("UP","FLAT") and mss_above)
        partial = (vwap_side == "ABOVE" and (vwap_slope in ("UP","FLAT") or mss_above))
    elif side == "SHORT":
        full = (vwap_side == "BELOW" and vwap_slope == "DOWN" and mss_below)
        partial = (vwap_side == "BELOW" and (vwap_slope == "DOWN" or mss_below))
    score += 15.0 if full else (7.0 if partial else 0.0)

    # HTF agreement bonus (cap 10)
    htf = vals["htf_bias"]
    if (htf == "BULL" and side == "LONG") or (htf == "BEAR" and side == "SHORT"):
        score += 10.0

    # POI strength kicker (cap 5)
    if poi_type in ("15M_FVG","1H_OB","4H_FVG","DO","VWAP"):
        score += 5.0

    # Clamp
    score = max(0.0, min(100.0, score))

    # Map to letters
    if score >= 85: letter = "A+"
    elif score >= 75: letter = "A"
    elif score >= 65: letter = "B"
    elif score >= 50: letter = "C"
    else: letter = "D"

    return round(score,1), letter

# --- UI ---
with st.sidebar:
    st.header("Config")
    tick_size = st.number_input("Tick Size", value=float(TICK_SIZE_DEFAULT), step=0.01, format="%.4f")
    sigma_ticks = st.number_input("Sigma (ticks) — 1σ", value=float(SIGMA_TICKS_DEFAULT), step=1.0, format="%.2f")
    adx_thr = st.number_input("ADX Threshold", value=float(ADX_THRESHOLD_DEFAULT), step=0.25, format="%.2f")
    default_risk_ticks = st.number_input("Default Risk (ticks)", value=float(DEFAULT_RISK_TICKS), step=1.0, format="%.0f")

st.title("LSF Signal Tool — CISD • POI • VWAP • ADX • Deviations")
st.subheader("Inputs")

c1,c2,c3,c4 = st.columns(4)
with c1:
    symbol = st.text_input("Symbol", value="MNQZ25")
    current_price = st.number_input("Current Price", value=0.0, step=0.25, format="%.2f")
with c2:
    vwap = st.number_input("VWAP (optional)", value=0.0, step=0.25, format="%.2f")
    vwap_side = st.selectbox("VWAP Side", ["ABOVE","BELOW"], index=0)
with c3:
    vwap_slope = st.selectbox("VWAP Slope", ["UP","DOWN","FLAT"], index=0)
    entry_type = st.selectbox("Entry Type", ["MARKET","LIMIT"], index=0)
with c4:
    planned_entry = st.number_input("Planned Entry (if LIMIT)", value=0.0, step=0.25, format="%.2f")
    risk_ticks_in = st.text_input("Risk (ticks) — leave blank to use default", value="")

c5,c6,c7,c8 = st.columns(4)
with c5:
    adx_1m = st.number_input("ADX 1m", value=0.0, step=0.25)
    htf_bias = st.selectbox("HTF Bias 60m", ["BULL","BEAR"], index=1)
with c6:
    adx_3m = st.number_input("ADX 3m", value=0.0, step=0.25)
    mtf_bias = st.selectbox("MTF Bias 15m", ["BULL","BEAR"], index=1)
with c7:
    adx_15m = st.number_input("ADX 15m", value=0.0, step=0.25)
    ltf_bias = st.selectbox("LTF Bias 1m", ["BULL","BEAR"], index=0)
with c8:
    adx_60m = st.number_input("ADX 60m", value=0.0, step=0.25)
    session_tag = st.text_input("Session Tag", value="NYKZ")

# POI + FVG stack
c9,c10,c11,c12 = st.columns(4)
with c9:
    poi_type = st.selectbox("POI Type", [
        "1M_FVG","3M_FVG","5M_FVG","15M_FVG",
        "1H_OB","4H_FVG","DO","VWAP","OTHER"
    ], index=3)
with c10:
    fvg_kind = st.selectbox("FVG Type", ["IFVG","FVG","IPDA_GAP","OTHER"], index=0)
with c11:
    poi_validated = st.selectbox("POI Validated", ["YES","NO"], index=0)
    cisd_confirmed = st.selectbox("CISD Confirmed", ["YES","NO"], index=0)
with c12:
    mss_above = st.selectbox("MSS Above VWAP", ["YES","NO"], index=0)
    mss_below = st.selectbox("MSS Below VWAP", ["YES","NO"], index=1)

c13,c14,c15,c16 = st.columns(4)
with c13:
    fvg_1m = st.checkbox("FVG 1m present", value=False)
with c14:
    fvg_3m = st.checkbox("FVG 3m present", value=True)
with c15:
    fvg_5m = st.checkbox("FVG 5m present", value=True)
with c16:
    fvg_15m = st.checkbox("FVG 15m present", value=True)

cisd_anchor = st.number_input("CISD Anchor (price)", value=0.0, step=0.25, format="%.2f")

# New controls for targets
deviation_basis = st.selectbox("Deviation Basis", ["CISD", "ENTRY", "VWAP"], index=0)
tp_policy = st.selectbox("TP Basis Policy", ["Ensure beyond entry", "Strict (use selected basis)"], index=0)

# Bundle values
vals = dict(
    vwap_side=vwap_side, vwap_slope=vwap_slope,
    adx_3m=adx_3m, adx_thr=adx_thr,
    cisd_confirmed=cisd_confirmed, poi_validated=poi_validated,
    mss_below_vwap=mss_below, mss_above_vwap=mss_above,
    htf_bias=htf_bias
)

sigma_price = one_sigma_price(tick_size, sigma_ticks)
risk_ticks = risk_ticks_used(risk_ticks_in, default_risk_ticks)

# Determine scenario + side
scenario = "WAIT"
if rot_valid(vals):
    scenario = "CISD_ROTATION"
elif cont_short_valid(vals):
    scenario = "CONTINUATION"

side = decide_side(vals) if scenario != "WAIT" else "-"

entry = current_price if entry_type == "MARKET" else (planned_entry if planned_entry else 0.0)
stop = compute_stop(side, entry, risk_ticks, tick_size) if side in ("LONG","SHORT") else None

# Choose basis for targets
if deviation_basis == "ENTRY" and entry:
    basis_price = entry
elif deviation_basis == "VWAP" and vwap:
    basis_price = vwap
else:
    basis_price = cisd_anchor  # default CISD

# Safety policy: ensure TPs are beyond entry in the direction of the trade
exec_basis = basis_price
if tp_policy.startswith("Ensure") and side in ("LONG","SHORT"):
    if side == "LONG" and entry:
        exec_basis = max(basis_price, entry)
    elif side == "SHORT" and entry:
        exec_basis = min(basis_price, entry)

tp1, tp2 = compute_targets(side, exec_basis, sigma_price)

# --- Grading ---
fvg_stack_count = int(fvg_1m) + int(fvg_3m) + int(fvg_5m) + int(fvg_15m)
grade_score, grade_letter = (None, None)
if scenario != "WAIT" and side in ("LONG","SHORT") and poi_validated == "YES" and cisd_confirmed == "YES" and float(adx_3m) > float(adx_thr):
    grade_score, grade_letter = grade_signal(side, vals, fvg_stack_count, poi_type, adx_3m, adx_thr)

# Display Signal Card
st.markdown("---")
st.subheader("Signal Card")

colA,colB,colC,colD = st.columns(4)
with colA:
    st.write("**Scenario**"); st.write(scenario)
    st.write("**Side**"); st.write(side)
with colB:
    st.write("**Entry**"); st.write(f"{entry:.2f}" if entry else "-")
    st.write("**Stop**"); st.write(f"{stop:.2f}" if stop else "-")
with colC:
    st.write("**TP1 (2.5σ)**"); st.write(f"{tp1:.2f}" if tp1 else "-")
    st.write("**TP2 (4σ)**"); st.write(f"{tp2:.2f}" if tp2 else "-")
with colD:
    st.write("**1σ (price)**"); st.write(f"{sigma_price:.4f}")
    st.write("**Risk Ticks Used**"); st.write(risk_ticks)

anchor_txt = f"Selected basis: {deviation_basis} ({basis_price:.2f})"
if tp_policy.startswith("Ensure") and exec_basis != basis_price:
    anchor_txt += f" → Exec basis: {exec_basis:.2f} (safety)"
st.caption(f"Targets projected from: **{anchor_txt}**")

# Notes banner matches actual side
if scenario == "WAIT":
    st.info("Filters not met — check CISD, POI validation, VWAP position/slope or ADX expansion.")
else:
    if side == "LONG":
        st.success("Long allowed when POI + CISD + ADX expansion align with VWAP reclaim / MSS above.")
    elif side == "SHORT":
        st.success("Short allowed when POI + CISD + ADX expansion align with VWAP rejection / MSS below.")
    else:
        st.warning("Direction unclear — verify MSS vs VWAP and HTF bias.")

# Grade badge
if grade_letter:
    st.markdown(f"**Setup Grade:** {grade_letter}  "+ f"(*score {grade_score}*)")

# Show stack hints
confs = []
if fvg_1m: confs.append("1m FVG")
if fvg_3m: confs.append("3m FVG")
if fvg_5m: confs.append("5m FVG")
if fvg_15m: confs.append("15m FVG")
st.caption("FVG stack: " + (", ".join(confs) if confs else "none") + f" | POI={poi_type} ({fvg_kind})")

# Make a log row and let user download
if st.button("Add to Log / Download CSV Row"):
    log = pd.DataFrame([{
        "timestamp": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "symbol": symbol,
        "scenario": scenario,
        "side": side,
        "entry": entry,
        "stop": stop,
        "tp1": tp1,
        "tp2": tp2,
        "risk_ticks": risk_ticks,
        "adx_3m": adx_3m,
        "poi": poi_type,
        "fvg_type": fvg_kind,
        "fvg_stack": "|".join([s for s,b in zip(["1m","3m","5m","15m"], [fvg_1m,fvg_3m,fvg_5m,fvg_15m]) if b]),
        "cisd_anchor": cisd_anchor,
        "deviation_basis": deviation_basis,
        "basis_price": exec_basis,
        "grade_score": grade_score,
        "grade_letter": grade_letter,
        "session": session_tag
    }])
    st.download_button("Download Log Row (CSV)", log.to_csv(index=False).encode("utf-8"),
                       file_name=f"lsf_log_{symbol}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.csv",
                       mime="text/csv")

st.markdown("---")
st.caption("Neural-LSF | NY Bias Framework v2.6 — Web Tool (v3.2)")
