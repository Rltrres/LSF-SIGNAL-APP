
# app.py — v3.7 (Session-aware automation + NY Low Reversal option)
import streamlit as st
import pandas as pd
from pathlib import Path
from signal_engine_v3_7 import (
    Inputs, evaluate_signal, SWEEP_PROFILES, SWEEP_TYPES, ARCHETYPES,
    load_profiles_from_excel, dump_profiles_to_json, load_profiles_from_json, log_signal_csv
)

st.set_page_config(page_title="LSF • Sweep Adaptive", page_icon="🧨", layout="wide")

st.markdown("""
<style>
div.block-container {padding-top: 1.2rem; max-width: 1200px;}
body {background: radial-gradient(1200px 700px at 10% -10%, rgba(0,255,255,.08), transparent),
                   radial-gradient(900px 600px at 110% 0%, rgba(255,0,255,.06), transparent),
                   #0f1115;}
h1.title-gradient {
  background: linear-gradient(90deg,#00e5ff,#ff5cf0,#00ffd5,#00e5ff);
  background-size: 300% 300%;
  -webkit-background-clip: text; -webkit-text-fill-color: transparent;
  animation: flow 10s ease infinite; font-weight:800; letter-spacing:.5px;
}
@keyframes flow {0%{background-position:0 50%}50%{background-position:100% 50%}100%{background-position:0 50%}}
.metric-card {padding: 1rem 1.25rem; border-radius: 16px; background: rgba(255,255,255,0.03); border: 1px solid rgba(255,255,255,0.10);}
.badge {display:inline-block; padding:.2rem .6rem; border-radius:12px; font-size:12px; border:1px solid rgba(255,255,255,.25); margin-right:.3rem;}
.badge.green {background: rgba(0,200,100,.18); border-color: rgba(0,200,100,.45);}
.badge.red {background: rgba(255,60,60,.18); border-color: rgba(255,60,60,.45);}
.small {opacity:.7; font-size:12px}
</style>
""", unsafe_allow_html=True)

st.markdown("<h1 class='title-gradient'>LSF — Sweep Adaptive Signal Tool</h1>", unsafe_allow_html=True)

with st.sidebar:
    st.header("Data & Model")
    tuning_path = Path("profiles_tuning.json")
    if tuning_path.exists(): load_profiles_from_json(str(tuning_path))

    uploaded = st.file_uploader("Optional: Load 'Model Summary' Excel", type=["xlsx"])
    if uploaded is not None:
        try:
            xls = pd.ExcelFile(uploaded)
            if "Model Summary" in xls.sheet_names:
                df = xls.parse("Model Summary")
                load_profiles_from_excel(df); st.success("Adaptive thresholds refreshed from Excel ✅")
        except Exception as e:
            st.error(f"Excel parse failed: {e}")

    model = st.selectbox("Liquidity Model", ARCHETYPES, index=0)
    session = st.selectbox("Session", ["Asia","London","NY"], index=2)
    sweep_type = st.selectbox("Liquidity Sweep", SWEEP_TYPES, index=0)
    prof = SWEEP_PROFILES[model]
    with st.expander("Model notes", expanded=False):
        st.write(prof.get("notes","—"))

    st.markdown("**Profile Defaults**")
    cA, cB = st.columns(2)
    with cA:
        st.write(f"- Bias mode: `{prof.get('bias_mode')}`")
        st.write(f"- ADX min: `{prof.get('adx_min')}`")
    with cB:
        st.write(f"- Delay: `{prof.get('post_sweep_delay',3)} bars`")
        st.write(f"- VWAP expectation: `{prof.get('expected_vwap','support')}`")
    st.markdown("---")
    st.header("Logging")
    enable_log = st.checkbox("Log 'Entry Ready = YES' to CSV", value=True)
    log_path = str(Path("logs/lsf_signal_log.csv"))

st.subheader("Market State")
c1,c2,c3,c4,c5,c6 = st.columns(6)
with c1:
    price = st.number_input("Price", value=25107.0, step=0.25)
with c2:
    vwap_side = st.selectbox("VWAP side", ["ABOVE","BELOW","TOUCHING"], index=0, key="vwap_side")
with c3:
    vwap_slope = st.selectbox("VWAP slope", ["UP","DOWN","FLAT"], index=0, key="vwap_slope")
with c4:
    adx_now = st.number_input("ADX now", value=31.0)
with c5:
    adx_sma3 = st.number_input("ADX SMA3", value=30.5)
with c6:
    adx_sma6 = st.number_input("ADX SMA6", value=28.8)

c7,c8,c9 = st.columns(3)
with c7:
    htf = st.selectbox("HTF 60m bias", ["BULL","BEAR","NEUTRAL"], index=1, key="htf")
with c8:
    l15 = st.selectbox("LTF 15m bias", ["BULL","BEAR","NEUTRAL"], index=0, key="l15")
with c9:
    l3 = st.selectbox("LTF 3m bias", ["BULL","BEAR","NEUTRAL"], index=0, key="l3")

c10,c11,c12 = st.columns(3)
with c10:
    bars_since_sweep = st.number_input("Bars since sweep", value=5, min_value=0)
with c11:
    mss_dir = st.selectbox("MSS direction", ["LONG","SHORT","None"], index=0, key="mss")
with c12:
    micro_fvg = st.checkbox("Micro-FVG present (1m)", value=True)

st.subheader("Direction & Thresholds")
d1,d2,d3 = st.columns(3)
with d1:
    desired = st.selectbox("Trade Direction", ["LONG","SHORT"], index=0)
with d2:
    adx_kill = st.number_input("Kill-switch if ADX <", value=20.0, min_value=0.0, max_value=50.0)
with d3:
    adx_slope_min = st.number_input("ADX slope min (SMA3-SMA6)", value=0.0, min_value=-5.0, max_value=5.0)

# Evaluate
inp = Inputs(
    price=price, vwap_side=vwap_side, vwap_slope=vwap_slope,
    adx_now=adx_now, adx_sma3=adx_sma3, adx_sma6=adx_sma6, adx_kill=adx_kill,
    session=session,
    mss_dir=None if mss_dir=="None" else mss_dir, mss_tf="3m",
    htf_60m_bias=htf, ltf_15m_bias=l15, ltf_3m_bias=l3,
    liquidity_model=model, sweep_type=sweep_type, bars_since_sweep=bars_since_sweep,
    post_sweep_delay=SWEEP_PROFILES[model].get("post_sweep_delay",3),
    require_vwap_flip=SWEEP_PROFILES[model].get("require_vwap_flip", True),
    micro_fvg_present=micro_fvg,
    adx_min=SWEEP_PROFILES[model].get("adx_min", 28), adx_slope_min=adx_slope_min
)
res = evaluate_signal(desired, inp, profiles=SWEEP_PROFILES)

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

st.info(f"Model used: **{res.get('model_used')}**")

with st.expander("Component Checks"):
    comp = res["components"]
    badges = []
    for k in ["delay_ok","mss_ok","vwap_ok","adx_ok","bias_ok","micro_ok"]:
        ok = comp.get(k, False); cls = "green" if ok else "red"
        badges.append(f"<span class='badge {cls}'>{k.replace('_',' ').upper()}</span>")
    st.markdown(" ".join(badges), unsafe_allow_html=True)
    st.json(res["components"])

# Logging
log_path = Path("logs/lsf_signal_log.csv")
if res["entry_ready"] and st.sidebar.checkbox("Log 'Entry Ready = YES' to CSV", value=True, key="logyes"):
    try:
        log_signal_csv(str(log_path), model, desired, res, inp); st.success("Logged to CSV ✔")
    except Exception as e:
        st.error(f"Logging failed: {e}")

# Tuning
st.markdown("---")
st.subheader("Tuning (per-model)")
tc1, tc2, tc3 = st.columns(3)
prof = SWEEP_PROFILES[model]
with tc1:
    prof["adx_min"] = st.number_input("ADX min (model)", value=float(prof["adx_min"]), step=1.0)
with tc2:
    prof["post_sweep_delay"] = st.number_input("Post-sweep delay (bars, model)", value=int(prof.get("post_sweep_delay",3)), step=1)
with tc3:
    prof["require_vwap_flip"] = st.checkbox("Require VWAP flip", value=bool(prof.get("require_vwap_flip", True)))
# grade weights
tw1, tw2, tw3, tw4, tw5 = st.columns(5)
gw = prof["grade_weights"]
with tw1:
    gw["sweep"] = st.number_input("Weight: Sweep", value=int(gw.get("sweep",30)), min_value=0, max_value=50)
with tw2:
    gw["mss"] = st.number_input("Weight: MSS", value=int(gw.get("mss",20)), min_value=0, max_value=50)
with tw3:
    gw["vwap"] = st.number_input("Weight: VWAP", value=int(gw.get("vwap",20)), min_value=0, max_value=50)
with tw4:
    gw["adx"] = st.number_input("Weight: ADX", value=int(gw.get("adx",15)), min_value=0, max_value=50)
with tw5:
    gw["bias"] = st.number_input("Weight: Bias", value=int(gw.get("bias",15)), min_value=0, max_value=50)

if st.button("💾 Save tuning"):
    dump_profiles_to_json(str(tuning_path)); st.success("Saved tuning to profiles_tuning.json")
    with open(tuning_path, "rb") as f:
        st.download_button("Download profiles_tuning.json", f, file_name="profiles_tuning.json", mime="application/json")
