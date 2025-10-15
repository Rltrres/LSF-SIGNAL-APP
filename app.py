
import streamlit as st
import pandas as pd
from datetime import datetime

st.set_page_config(page_title="LSF Signal Tool", page_icon="📈", layout="wide")

# --- Defaults / Config ---
TICK_SIZE_DEFAULT = 0.25    # MNQ
SIGMA_TICKS_DEFAULT = 40.0  # 1σ in ticks
ADX_THRESHOLD_DEFAULT = 22.5
DEFAULT_RISK_TICKS = 40

# --- Helper functions ---
def one_sigma_price(tick_size: float, sigma_ticks: float) -> float:
    return tick_size * sigma_ticks

def risk_ticks_used(user_ticks, default_ticks):
    try:
        return float(user_ticks) if user_ticks not in (None, "", 0) else float(default_ticks)
    except:
        return float(default_ticks)

def cisd_rotation_long_valid(vals) -> bool:
    return (
        vals["cisd_confirmed"] == "YES"
        and vals["poi_validated"] == "YES"
        and vals["vwap_side"] == "ABOVE"
        and vals["vwap_slope"] in ("UP","FLAT")
        and float(vals["adx_3m"]) > float(vals["adx_thr"])
    )

def continuation_short_valid(vals) -> bool:
    return (
        vals["mss_below_vwap"] == "YES"
        and vals["vwap_side"] == "BELOW"
        and vals["vwap_slope"] == "DOWN"
        and float(vals["adx_3m"]) > float(vals["adx_thr"])
    )

def compute_targets(side, cisd_anchor, sigma_price):
    if side == "LONG":
        tp1 = cisd_anchor + 2.5 * sigma_price
        tp2 = cisd_anchor + 4.0 * sigma_price
    elif side == "SHORT":
        tp1 = cisd_anchor - 2.5 * sigma_price
        tp2 = cisd_anchor - 4.0 * sigma_price
    else:
        tp1 = tp2 = None
    return tp1, tp2

def compute_stop(side, entry, risk_ticks, tick_size):
    if side == "LONG":
        return entry - risk_ticks * tick_size
    elif side == "SHORT":
        return entry + risk_ticks * tick_size
    return None

st.title("LSF Signal Tool — CISD • POI • VWAP • ADX • Deviations")
with st.sidebar:
    st.header("Config")
    tick_size = st.number_input(
        "Tick Size", value=float(TICK_SIZE_DEFAULT), step=0.01, format="%.4f"
    )
    sigma_ticks = st.number_input(
        "Sigma (ticks) — 1σ", value=float(SIGMA_TICKS_DEFAULT), step=1.0, format="%.2f"
    )
    adx_thr = st.number_input(
        "ADX Threshold", value=float(ADX_THRESHOLD_DEFAULT), step=0.25, format="%.2f"
    )
    # 👇 make the value a float so it matches the float step (prevents MixedNumericTypesError)
    default_risk_ticks = st.number_input(
        "Default Risk (ticks)", value=float(DEFAULT_RISK_TICKS), step=1.0, format="%.0f"
    )


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
    bias_60 = st.selectbox("HTF Bias 60m", ["BULL","BEAR"], index=1)
with c6:
    adx_3m = st.number_input("ADX 3m", value=0.0, step=0.25)
    bias_15 = st.selectbox("MTF Bias 15m", ["BULL","BEAR"], index=1)
with c7:
    adx_15m = st.number_input("ADX 15m", value=0.0, step=0.25)
    bias_1 = st.selectbox("LTF Bias 1m", ["BULL","BEAR"], index=0)
with c8:
    adx_60m = st.number_input("ADX 60m", value=0.0, step=0.25)
    session_tag = st.text_input("Session Tag", value="NYKZ")

c9,c10,c11,c12 = st.columns(4)
with c9:
    poi_type = st.selectbox("POI Type", ["4H_FVG","1H_OB","DO","VWAP","OTHER"], index=0)
with c10:
    poi_validated = st.selectbox("POI Validated", ["YES","NO"], index=0)
with c11:
    cisd_confirmed = st.selectbox("CISD Confirmed", ["YES","NO"], index=0)
    mss_above = st.selectbox("MSS Above VWAP", ["YES","NO"], index=0)
with c12:
    mss_below = st.selectbox("MSS Below VWAP", ["YES","NO"], index=1)
    cisd_anchor = st.number_input("CISD Anchor (price)", value=0.0, step=0.25, format="%.2f")

# Bundle values
vals = dict(
    vwap_side=vwap_side, vwap_slope=vwap_slope, adx_3m=adx_3m, adx_thr=adx_thr,
    cisd_confirmed=cisd_confirmed, poi_validated=poi_validated,
    mss_below_vwap=mss_below
)

sigma_price = one_sigma_price(tick_size, sigma_ticks)
risk_ticks = risk_ticks_used(risk_ticks_in, default_risk_ticks)

# Determine scenario
rot_valid = cisd_rotation_long_valid(vals)
cont_short_valid = continuation_short_valid(vals)

if rot_valid:
    scenario = "CISD_ROTATION"
    side = "LONG"
elif cont_short_valid:
    scenario = "CONTINUATION"
    side = "SHORT"
else:
    scenario = "WAIT"
    side = "-"

entry = current_price if entry_type == "MARKET" else (planned_entry if planned_entry else 0.0)
stop = compute_stop(side, entry, risk_ticks, tick_size) if side in ("LONG","SHORT") else None
tp1, tp2 = compute_targets(side, cisd_anchor, sigma_price)

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

# Notes
if scenario == "WAIT":
    st.info("Filters not met — check CISD, POI validation, VWAP position/slope or ADX expansion.")
elif scenario == "CISD_ROTATION":
    st.success("Long allowed under HTF bearish when POI + CISD + ADX expansion are satisfied.")
elif scenario == "CONTINUATION":
    st.success("Continuation short with trend — MSS below VWAP + down slope + ADX expansion.")

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
        "poi": poi_type if poi_validated == "YES" else "NONE",
        "cisd_anchor": cisd_anchor,
        "session": session_tag
    }])
    st.download_button("Download Log Row (CSV)", log.to_csv(index=False).encode("utf-8"),
                       file_name=f"lsf_log_{symbol}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.csv",
                       mime="text/csv")

st.markdown("---")
st.caption("Neural-LSF | NY Bias Framework v2.4.1 — Web Tool")
