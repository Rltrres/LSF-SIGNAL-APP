
import streamlit as st
from signal_engine import Inputs, evaluate_signal

st.set_page_config(page_title="LSF Signal Tool — Sweep Adaptive", layout="wide")

st.title("LSF Signal Tool — Sweep Adaptive")
st.caption("Sweep → MSS → VWAP side/flip → ADX slope. Built for London-sweep plays.")

with st.sidebar:
    st.header("Sweep & Rotation")
    sweep_type = st.selectbox("Sweep type", ["None","Asia Low","Asia High","London Low","London High","PDH","PDL"], index=3)
    post_sweep_delay = st.number_input("Post-sweep delay (bars)", 0, 10, 3)
    mss_tf = st.selectbox("Confirm MSS on", ["1m","3m","5m"], index=1)
    mss_dir_choice = st.selectbox("MSS direction", ["LONG","SHORT","None"], index=0)
    require_vwap_flip = st.checkbox("Require VWAP flip/side in trade direction", value=True)
    micro_fvg_present = st.checkbox("Require micro-FVG inside POI", value=True)

    st.header("ADX Controls")
    adx_min = st.number_input("ADX min", 0.0, 100.0, 28.0)
    adx_slope_min = st.number_input("ADX slope min (SMA3-SMA6)", -5.0, 5.0, 0.0)
    adx_kill = st.number_input("Kill-switch if ADX <", 0.0, 50.0, 20.0)

    st.header("Bias Mode")
    bias_mode = st.radio("Bias stacking rule", ["continuation","reversal"], index=0)

st.subheader("Market State (manual demo)")
c1, c2, c3, c4, c5, c6 = st.columns(6)
with c1:
    price = st.number_input("Price", value=25107.0, step=0.25)
with c2:
    vwap = st.number_input("VWAP", value=25080.0, step=0.25)
with c3:
    vwap_slope = st.selectbox("VWAP slope", ["UP","DOWN","FLAT"], index=0)
with c4:
    vwap_side = st.selectbox("VWAP side", ["ABOVE","BELOW","TOUCHING"], index=0)
with c5:
    adx_now = st.number_input("ADX now", value=31.0)
with c6:
    adx_sma3 = st.number_input("ADX SMA3", value=30.5)

c7, c8, c9 = st.columns(3)
with c7:
    adx_sma6 = st.number_input("ADX SMA6", value=28.8)
with c8:
    htf_60m = st.selectbox("HTF 60m bias", ["BULL","BEAR","NEUTRAL"], index=1)
with c9:
    ltf_15m = st.selectbox("LTF 15m bias", ["BULL","BEAR","NEUTRAL"], index=0)

c10, c11, c12 = st.columns(3)
with c10:
    ltf_3m = st.selectbox("LTF 3m bias", ["BULL","BEAR","NEUTRAL"], index=0)
with c11:
    bars_since_sweep = st.number_input("Bars since sweep", value=5, min_value=0)
with c12:
    poi_type = st.selectbox("POI type", ["15M_FVG","15M_OB","1H_FVG","1H_OB","Other"], index=0)

c13, c14 = st.columns(2)
with c13:
    poi_dir = st.selectbox("POI direction", ["LONG","SHORT"], index=0)
with c14:
    use_kill = st.checkbox("Use ADX kill-switch", value=True)

mss_dir_val = None if mss_dir_choice == "None" else mss_dir_choice

inp = Inputs(
    price=price, vwap=vwap, vwap_slope=vwap_slope, vwap_side=vwap_side,
    adx_now=adx_now, adx_sma3=adx_sma3, adx_sma6=adx_sma6, adx_kill=adx_kill if use_kill else 0.0,
    mss_tf=mss_tf, mss_dir=mss_dir_val,
    htf_60m_bias=htf_60m, ltf_15m_bias=ltf_15m, ltf_3m_bias=ltf_3m,
    sweep_type=sweep_type, bars_since_sweep=bars_since_sweep,
    post_sweep_delay=post_sweep_delay, require_vwap_flip=require_vwap_flip,
    poi_type=poi_type, poi_dir=poi_dir, micro_fvg_present=micro_fvg_present,
    adx_min=adx_min, adx_slope_min=adx_slope_min
)

desired = "LONG" if poi_dir == "LONG" else "SHORT"
res = evaluate_signal(desired, inp, bias_mode=bias_mode)

st.subheader("Signal Result")
colA, colB = st.columns([1,1])
with colA:
    st.metric("Entry Ready", "YES" if res["entry_ready"] else "NO")
with colB:
    st.metric("Grade (0–100)", res["grade"])

st.write("Components")
st.json(res["components"])

if res["banners"]:
    st.warning(" | ".join(res["banners"]))
