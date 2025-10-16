# app.py — v3.11
import streamlit as st, pandas as pd
from pathlib import Path
from signal_engine_v3_11 import (
    Inputs, evaluate_signal, SWEEP_PROFILES, SWEEP_TYPES, ARCHETYPES,
    load_profiles_from_excel, dump_profiles_to_json, load_profiles_from_json, log_signal_csv,
    reset_model_to_defaults
)
import streamlit as st
st.markdown(
    """<style>""" + open("assets/neon_theme.css").read() + """</style>""",
    unsafe_allow_html=True,
)


st.set_page_config(page_title="LSF • Sweep Adaptive", page_icon="🪩", layout="wide")

st.markdown("""
<style>
div.block-container {padding-top: 1.2rem; max-width: 1200px;}
body {background: radial-gradient(1200px 700px at 10% -10%, rgba(0,255,255,.08), transparent),
                   radial-gradient(900px 600px at 110% 0%, rgba(255,0,255,.06), transparent),
                   #0f1115;}
h1.title-gradient {background: linear-gradient(90deg,#00e5ff,#ff5cf0,#00ffd5,#00e5ff);
  background-size: 300% 300%; -webkit-background-clip: text; -webkit-text-fill-color: transparent;
  animation: flow 10s ease infinite; font-weight:800;}
.metric-card {padding: 1rem 1.25rem; border-radius: 16px; background: rgba(255,255,255,0.03); border: 1px solid rgba(255,255,255,0.10);}
.badge {display:inline-block; padding:.2rem .6rem; border-radius:12px; font-size:12px; border:1px solid rgba(255,255,255,.25); margin-right:.3rem;}
.badge.green {background: rgba(0,200,100,.18); border-color: rgba(0,200,100,.45);} .badge.red {background: rgba(255,60,60,.18); border-color: rgba(255,60,60,.45);}
.small {opacity:.7; font-size:12px}
</style>
""", unsafe_allow_html=True)

st.markdown("<h1 class='title-gradient'>LSF — Sweep Adaptive Signal Tool</h1>", unsafe_allow_html=True)
st.caption("v3.11 — Adaptive Bias Logic + Transitional tag + VWAP close confirm (everything else preserved).")

with st.sidebar:
    st.header("Data & Model")
    tuning_path = Path("data") / "profiles_tuning.json"
    tuning_path.parent.mkdir(parents=True, exist_ok=True)
    if tuning_path.exists(): load_profiles_from_json(str(tuning_path))

    uploaded = st.file_uploader("Optional: Load 'Model Summary' Excel", type=["xlsx"])
    if uploaded is not None:
        try:
            xls = pd.ExcelFile(uploaded)
            if "Model Summary" in xls.sheet_names:
                df = xls.parse("Model Summary"); load_profiles_from_excel(df)
                st.success("Adaptive thresholds refreshed from Excel ✅")
        except Exception as e:
            st.error(f"Excel parse failed: {e}")

    model = st.selectbox("Liquidity Model", ARCHETYPES, index=0)
    session = st.selectbox("Session", ["Asia","London","NY"], index=2)
    sweep_type = st.selectbox("Liquidity Sweep", SWEEP_TYPES, index=0)
    prof = SWEEP_PROFILES[model]
    st.markdown("**Profile Defaults**")
    cA, cB = st.columns(2)
    with cA: st.write(f"- Bias mode: `{prof.get('bias_mode')}`"); st.write(f"- ADX min: `{prof.get('adx_min')}`")
    with cB: st.write(f"- Delay: `{prof.get('post_sweep_delay',3)} bars`"); st.write(f"- VWAP expectation: `{prof.get('expected_vwap','support')}`")
    st.markdown("---")
    st.header("Logging")
    enable_log = st.checkbox("Log 'Entry Ready = YES' to CSV", value=True)
    log_path = str(Path("logs/lsf_signal_log.csv"))

st.subheader("Market State")
c1,c2,c3,c4,c5,c6 = st.columns(6)
with c1: price = st.number_input("Price", value=25107.0, step=0.25)
with c2: vwap_side = st.selectbox("VWAP side", ["ABOVE","BELOW","TOUCHING"], index=0, key="vwap_side")
with c3: vwap_slope = st.selectbox("VWAP slope", ["UP","DOWN","FLAT"], index=0, key="vwap_slope")
with c4: adx_now = st.number_input("ADX now", value=31.0)
with c5: adx_sma3 = st.number_input("ADX SMA3", value=30.5)
with c6: adx_sma6 = st.number_input("ADX SMA6", value=28.8)

c7,c8,c9 = st.columns(3)
with c7: htf = st.selectbox("HTF 60m bias", ["BULL","BEAR","NEUTRAL"], index=1, key="htf")
with c8: l15 = st.selectbox("LTF 15m bias", ["BULL","BEAR","NEUTRAL"], index=0, key="l15")
with c9: l3 = st.selectbox("LTF 3m bias", ["BULL","BEAR","NEUTRAL"], index=0, key="l3")

c10,c11,c12 = st.columns(3)
with c10: bars_since_sweep = st.number_input("Bars since sweep", value=5, min_value=0)
with c11: mss_dir = st.selectbox("MSS direction", ["LONG","SHORT","None"], index=0, key="mss")
with c12: micro_fvg = st.checkbox("Micro-FVG present (1m)", value=True)

st.subheader("Direction & Thresholds")
d1,d2,d3 = st.columns(3)
with d1: desired = st.selectbox("Trade Direction", ["LONG","SHORT"], index=0)
with d2: adx_kill = st.number_input("Kill-switch if ADX <", value=20.0, min_value=0.0, max_value=50.0)
with d3: adx_slope_min = st.number_input("ADX slope min (SMA3-SMA6)", value=0.0, min_value=-5.0, max_value=5.0)

st.subheader("Bias Logic")
b1,b2 = st.columns(2)
with b1: bias_logic_mode = st.selectbox("Bias logic mode", ["auto","adaptive","strict"], index=0)
with b2: vwap_close_confirm = st.checkbox("Require VWAP close-confirm when flip/reclaim", value=True)

# Trade Ticket — with auto targets (kept)
st.subheader("Trade Ticket — Entry / Risk / Targets")
tt1, tt2, tt3, tt4 = st.columns(4)
with tt1: entry_price = st.number_input("Entry", value=float(price), step=0.25, format="%.2f")
with tt2: stop_loss = st.number_input("Stop (SL)", value=float(price-20 if desired=='LONG' else price+20), step=0.25, format="%.2f")
with tt3: tp1 = st.number_input("TP1", value=float(price+30 if desired=='LONG' else price-30), step=0.25, format="%.2f")
with tt4: tp2 = st.number_input("TP2", value=float(price+60 if desired=='LONG' else price-60), step=0.25, format="%.2f")

st.markdown("**Auto targets — CISD Deviation**")
at1, at2, at3, at4 = st.columns(4)
with at1: cisd_anchor = st.number_input("CISD Anchor (price)", value=float(price), step=0.25, format="%.2f")
with at2: dev_per_sigma = st.number_input("Deviation size (1σ, points)", value=12.5, step=0.25, format="%.2f")
with at3: mult1 = st.number_input("TP1 multiplier (σ)", value=2.5, step=0.25)
with at4: mult2 = st.number_input("TP2 multiplier (σ)", value=4.0, step=0.5)
pol1, pol2, pol3 = st.columns(3)
with pol1: ensure_beyond = st.checkbox("Ensure targets beyond entry", value=True)
with pol2: preset = st.selectbox("Presets", ["—","2σ/3σ","2.5σ/4σ","3σ/5σ"], index=2)
with pol3: apply_auto = st.button("Apply auto targets")

# 1) replace the function
def compute_targets(anchor, dev, m1, m2, side, entry, ensure):
    """
    If 'ensure' is True, use ENTRY as the base so TP is always away from entry.
    Otherwise, use the provided anchor (legacy behavior).
    """
    base = entry if ensure else anchor
    sign = 1 if side == "LONG" else -1
    t1 = base + sign * (m1 * dev)
    t2 = base + sign * (m2 * dev)

    # one-tick safety nudge
    tick = 0.25
    if ensure:
        if side == "LONG":
            t1 = max(t1, entry + tick)
            t2 = max(t2, entry + tick)
        else:
            t1 = min(t1, entry - tick)
            t2 = min(t2, entry - tick)

    return round(t1, 2), round(t2, 2)


# 2) replace the apply call (where we compute TPs) with entry-aware version
if apply_auto:
    t1, t2 = compute_targets(
        cisd_anchor, dev_per_sigma, mult1, mult2,
        desired, entry_price, ensure_beyond
    )
    st.session_state["TP1_auto"] = t1
    st.session_state["TP2_auto"] = t2
    st.success(f"Auto TP1={t1:.2f} | TP2={t2:.2f}")


def rr(entry, sl, tp, side):
    risk = (entry - sl) if side=="LONG" else (sl - entry)
    reward = (tp - entry) if side=="LONG" else (entry - tp)
    if risk <= 0: return None
    return round(reward / risk, 2)

rr1 = rr(entry_price, stop_loss, st.session_state.get("TP1_auto", tp1), desired)
rr2 = rr(entry_price, stop_loss, st.session_state.get("TP2_auto", tp2), desired)
c_rr1, c_rr2 = st.columns(2)
with c_rr1: st.markdown(f"<div class='metric-card'><h3>R:R to TP1</h3><h2>{'—' if rr1 is None else rr1}</h2></div>", unsafe_allow_html=True)
with c_rr2: st.markdown(f"<div class='metric-card'><h3>R:R to TP2</h3><h2>{'—' if rr2 is None else rr2}</h2></div>", unsafe_allow_html=True)

# Evaluate
inp = Inputs(price=price, vwap_side=vwap_side, vwap_slope=vwap_slope,
             adx_now=adx_now, adx_sma3=adx_sma3, adx_sma6=adx_sma6, adx_kill=adx_kill,
             session=session, mss_dir=None if mss_dir=='None' else mss_dir, mss_tf='3m',
             htf_60m_bias=htf, ltf_15m_bias=l15, ltf_3m_bias=l3,
             liquidity_model=model, sweep_type=sweep_type, bars_since_sweep=bars_since_sweep,
             post_sweep_delay=SWEEP_PROFILES[model].get('post_sweep_delay',3),
             require_vwap_flip=SWEEP_PROFILES[model].get('require_vwap_flip', True),
             micro_fvg_present=micro_fvg,
             adx_min=SWEEP_PROFILES[model].get('adx_min', 28), adx_slope_min=adx_slope_min,
             bias_logic_mode=bias_logic_mode, vwap_close_confirm=vwap_close_confirm)
res = evaluate_signal(desired, inp, profiles=SWEEP_PROFILES)

st.subheader("Signal Result")
m1, m2, m3 = st.columns([1,1,1])
with m1: st.markdown(f"<div class='metric-card'><h3>Entry Ready</h3><h2>{'✅ YES' if res['entry_ready'] else '❌ NO'}</h2></div>", unsafe_allow_html=True)
with m2: st.markdown(f"<div class='metric-card'><h3>Grade</h3><h2>{res['grade']}</h2><div class='small'>0–100</div></div>", unsafe_allow_html=True)
with m3: st.markdown(f"<div class='metric-card'><h3>ADX Slope</h3><h2>{res['components']['adx_slope']}</h2></div>", unsafe_allow_html=True)
st.info(f"Model used: **{res.get('model_used')}**  •  Tag: **{res.get('tag')}**")

with st.expander("Component Checks"):
    comp = res["components"]
    chips = []
    for key,label in [("delay_ok","DELAY OK"),("mss_ok","MSS OK"),("vwap_ok","VWAP OK"),("adx_ok","ADX OK"),("bias_ok","BIAS OK"),("micro_ok","MICRO OK")]:
        ok = comp.get(key, False); cls = "green" if ok else "red"
        chips.append(f"<span class='badge {cls}'>{label}</span>")
    chips.append(f"<span class='badge'>{'bias:'+comp.get('bias_note','')}</span>")
    st.markdown(' '.join(chips), unsafe_allow_html=True)

# Logging
if res["entry_ready"] and enable_log:
    try:
        log_signal_csv(log_path, model, desired, res, inp)
        tlog = Path("logs/trade_tickets.csv"); tlog.parent.mkdir(parents=True, exist_ok=True)
        import csv, datetime as dt
        with open(tlog, "a", newline="") as f:
            w = csv.writer(f)
            if not tlog.exists() or tlog.stat().st_size == 0:
                w.writerow(["timestamp","session","model","sweep_type","side","entry","sl","tp1","tp2","rr1","rr2","grade","tag"])
            w.writerow([dt.datetime.utcnow().isoformat(), session, res.get("model_used"), sweep_type, desired,
                        entry_price, stop_loss, st.session_state.get("TP1_auto", tp1),
                        st.session_state.get("TP2_auto", tp2), rr1, rr2, res["grade"], res["tag"]])
        st.success("Logged to CSV ✔")
    except Exception as e:
        st.error(f"Logging failed: {e}")

for name, path in [("Signal Log", log_path), ("Trade Tickets", "logs/trade_tickets.csv")]:
    p = Path(path)
    if Path(p).exists():
        with open(p, "rb") as f:
            st.download_button(f"Download {name} (CSV)", f, file_name=Path(p).name, mime="text/csv")

st.markdown('---')
st.subheader("Tuning (per-model)")
tc1, tc2, tc3 = st.columns(3)
with tc1: SWEEP_PROFILES[model]["adx_min"] = st.number_input("ADX min (model)", value=float(SWEEP_PROFILES[model]["adx_min"]), step=1.0)
with tc2: SWEEP_PROFILES[model]["post_sweep_delay"] = st.number_input("Post-sweep delay (bars, model)", value=int(SWEEP_PROFILES[model].get("post_sweep_delay",3)), step=1)
with tc3: SWEEP_PROFILES[model]["require_vwap_flip"] = st.checkbox("Require VWAP flip", value=bool(SWEEP_PROFILES[model].get("require_vwap_flip", True)))
tw1, tw2, tw3, tw4, tw5 = st.columns(5)
gw = SWEEP_PROFILES[model]["grade_weights"]
with tw1: gw["sweep"] = st.number_input("Weight: Sweep", value=int(gw.get("sweep",30)), min_value=0, max_value=50)
with tw2: gw["mss"] = st.number_input("Weight: MSS", value=int(gw.get("mss",20)), min_value=0, max_value=50)
with tw3: gw["vwap"] = st.number_input("Weight: VWAP", value=int(gw.get("vwap",20)), min_value=0, max_value=50)
with tw4: gw["adx"] = st.number_input("Weight: ADX", value=int(gw.get("adx",15)), min_value=0, max_value=50)
with tw5: gw["bias"] = st.number_input("Weight: Bias", value=int(gw.get("bias",15)), min_value=0, max_value=50)

btn1, btn2 = st.columns([1,1])
with btn1:
    if st.button("💾 Save tuning"):
        tuning_path = Path("data") / "profiles_tuning.json"
        tuning_path.parent.mkdir(parents=True, exist_ok=True)
        dump_profiles_to_json(str(tuning_path)); st.success("Saved tuning to data/profiles_tuning.json")
with btn2:
    if st.button("♻️ Reset this model to defaults"):
        reset_model_to_defaults(model); st.success(f"{model} reset to defaults (not saved yet). Click 💾 Save to persist.")
