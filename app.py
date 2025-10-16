
# app.py (v3 polished) — LSF Signal Tool with multi-model adaptive engine
import streamlit as st
import pandas as pd
from pathlib import Path
from signal_engine_v3 import Inputs, evaluate_signal, SWEEP_PROFILES, load_profiles_from_excel, log_signal

st.set_page_config(page_title="LSF — Sweep Adaptive Signal Tool", page_icon="🎯", layout="wide")

# -------------- Branding / CSS --------------
st.markdown("""
<style>
/* Sleek dark cards */
div.block-container {padding-top: 1.5rem; max-width: 1200px;}
.metric-card {padding: 1rem 1.25rem; border-radius: 16px; background: rgba(255,255,255,0.03); border: 1px solid rgba(255,255,255,0.07);}
.small {font-size: 12px; opacity: .7;}
h1, h2, h3 {font-weight: 700;}
.badge {display:inline-block; padding:.2rem .6rem; border-radius:12px; font-size:12px; border:1px solid rgba(255,255,255,.2); margin-right:.4rem;}
.badge.green {background: rgba(0,200,100,.15); border-color: rgba(0,200,100,.35);}
.badge.red {background: rgba(255,60,60,.15); border-color: rgba(255,60,60,.35);}
.badge.blue {background: rgba(40,140,255,.15); border-color: rgba(40,140,255,.35);}
</style>
""", unsafe_allow_html=True)

st.title("🎯 LSF — Sweep Adaptive Signal Tool")
st.caption("London/Asia/PDH-PLD/IB/HTF POI sweeps → MSS → VWAP conditioning → ADX ignition, with your adaptive per-model thresholds.")

# -------------- Sidebar: Data & Model Selection --------------
with st.sidebar:
    st.header("Data & Model")
    uploaded = st.file_uploader("Optional: Load 'Model Summary' Excel to tune thresholds", type=["xlsx"])
    profiles = SWEEP_PROFILES.copy()
    if uploaded is not None:
        try:
            xls = pd.ExcelFile(uploaded)
            if "Model Summary" in xls.sheet_names:
                df = xls.parse("Model Summary")
                load_profiles_from_excel(df)
                st.success("Adaptive thresholds loaded from Excel ✅")
        except Exception as e:
            st.error(f"Could not read Excel: {e}")

    liquidity_model = st.selectbox("Liquidity Model", list(profiles.keys()), index=0)
    prof = profiles.get(liquidity_model, profiles["Asia_London_NY_Continuation"])

    st.markdown("**Profile Defaults**")
    cA, cB = st.columns(2)
    with cA:
        st.write(f"- Bias mode: `{prof.get('bias_mode')}`")
        st.write(f"- ADX min: `{prof.get('adx_min')}`")
    with cB:
        st.write(f"- Post-sweep delay: `{prof.get('post_sweep_delay', 3)}`")
        st.write(f"- VWAP expectation: `{prof.get('expected_vwap','support')}`")
    st.markdown("---")
    st.header("Logging")
    enable_log = st.checkbox("Log 'Entry Ready = YES' to CSV", value=True)
    log_path = str(Path("logs/lsf_signal_log.csv"))

# -------------- Market Inputs --------------
st.subheader("Market State")
c1,c2,c3,c4,c5,c6 = st.columns(6)
with c1:
    price = st.number_input("Price", value=25107.0, step=0.25)
with c2:
    vwap_side = st.selectbox("VWAP side", ["ABOVE","BELOW","TOUCHING"], index=0)
with c3:
    vwap_slope = st.selectbox("VWAP slope", ["UP","DOWN","FLAT"], index=0)
with c4:
    adx_now = st.number_input("ADX now", value=31.0)
with c5:
    adx_sma3 = st.number_input("ADX SMA3", value=30.5)
with c6:
    adx_sma6 = st.number_input("ADX SMA6", value=28.8)

c7,c8,c9 = st.columns(3)
with c7:
    htf = st.selectbox("HTF 60m bias", ["BULL","BEAR","NEUTRAL"], index=1)
with c8:
    l15 = st.selectbox("LTF 15m bias", ["BULL","BEAR","NEUTRAL"], index=0)
with c9:
    l3 = st.selectbox("LTF 3m bias", ["BULL","BEAR","NEUTRAL"], index=0)

c10,c11,c12 = st.columns(3)
with c10:
    bars_since_sweep = st.number_input("Bars since sweep", value=5, min_value=0)
with c11:
    mss_dir = st.selectbox("MSS direction", ["LONG","SHORT","None"], index=0)
with c12:
    micro_fvg = st.checkbox("Micro-FVG present (1m)", value=True)

# -------------- Direction choice --------------
st.subheader("Direction & Thresholds")
d1, d2, d3 = st.columns([1,1,1])
with d1:
    desired = st.selectbox("Trade Direction", ["LONG","SHORT"], index=0)
with d2:
    adx_kill = st.number_input("Kill-switch if ADX <", value=20.0, min_value=0.0, max_value=50.0)
with d3:
    adx_slope_min = st.number_input("ADX slope min (SMA3-SMA6)", value=0.0, min_value=-5.0, max_value=5.0)

# -------------- Evaluate --------------
inp = Inputs(
    price=price, vwap_side=vwap_side, vwap_slope=vwap_slope,
    adx_now=adx_now, adx_sma3=adx_sma3, adx_sma6=adx_sma6, adx_kill=adx_kill,
    mss_dir=None if mss_dir=="None" else mss_dir, mss_tf="3m",
    htf_60m_bias=htf, ltf_15m_bias=l15, ltf_3m_bias=l3,
    liquidity_model=liquidity_model, bars_since_sweep=bars_since_sweep,
    post_sweep_delay=SWEEP_PROFILES[liquidity_model].get("post_sweep_delay",3),
    require_vwap_flip=SWEEP_PROFILES[liquidity_model].get("require_vwap_flip", True),
    micro_fvg_present=micro_fvg,
    adx_min=SWEEP_PROFILES[liquidity_model].get("adx_min", 28), adx_slope_min=adx_slope_min
)

res = evaluate_signal(desired, inp, profiles=SWEEP_PROFILES)

# -------------- Metrics Cards --------------
st.subheader("Signal Result")
m1, m2, m3 = st.columns([1,1,1])
with m1:
    st.markdown(f"<div class='metric-card'><h3>Entry Ready</h3><h2>{'✅ YES' if res['entry_ready'] else '❌ NO'}</h2></div>", unsafe_allow_html=True)
with m2:
    st.markdown(f"<div class='metric-card'><h3>Grade</h3><h2>{res['grade']}</h2><div class='small'>0–100 adaptive</div></div>", unsafe_allow_html=True)
with m3:
    st.markdown(f"<div class='metric-card'><h3>ADX Slope</h3><h2>{res['components']['adx_slope']}</h2><div class='small'>SMA3 - SMA6</div></div>", unsafe_allow_html=True)

if res["banners"]:
    st.warning(" | ".join(res["banners"]))

# -------------- Components Breakdown --------------
with st.expander("Component Checks", expanded=False):
    comp = res["components"]
    badges = []
    for k in ["sweep_ok","delay_ok","mss_ok","vwap_ok","adx_ok","bias_ok","micro_ok"]:
        ok = comp.get(k, False)
        cls = "green" if ok else "red"
        badges.append(f"<span class='badge {cls}'>{k.replace('_',' ').upper()}</span>")
    st.markdown(" ".join(badges), unsafe_allow_html=True)
    st.json(res["components"])

# -------------- Logging --------------
if res["entry_ready"] and enable_log:
    try:
        log_signal(log_path, liquidity_model, desired, res, inp)
        st.success("Logged to CSV ✔")
    except Exception as e:
        st.error(f"Logging failed: {e}")

# -------------- Download log --------------
log_file = Path(log_path)
if log_file.exists():
    with open(log_file, "rb") as f:
        st.download_button("Download Signal Log (CSV)", f, file_name="lsf_signal_log.csv", mime="text/csv")
