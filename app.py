import streamlit as st
import pandas as pd
from datetime import datetime

st.set_page_config(page_title="LSF Signal Tool", page_icon=":chart_with_upwards_trend:", layout="wide")

# =======================
# Minimal New-Age Styling (UI v4)
# =======================
UI_CSS = """
<style>
:root{
  --card-bg: rgba(255,255,255,0.65);
  --pill:#0ea5e9; --pill-soft: rgba(14,165,233,0.12);
  --success:#22c55e; --warn:#eab308; --danger:#ef4444;
  --muted:#6b7280; --shadow:0 10px 30px rgba(0,0,0,.08); --radius:16px;
}
@media (prefers-color-scheme: dark){
  :root{ --card-bg: rgba(17,17,27,.55); --muted:#9ca3af; --shadow:0 10px 30px rgba(0,0,0,.35); }
}
.block-container{ padding-top:1.5rem; } .small{ font-size:.86rem; color:var(--muted); }
.mono{ font-variant-numeric: tabular-nums; font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace; }
.hr{ height:1px; background:linear-gradient(90deg,transparent,rgba(125,125,255,.35),transparent); margin:10px 0 18px; }
.header{ border-radius:20px; padding:18px 22px;
  background:linear-gradient(135deg,#111827 0%,#1f2937 35%,#0ea5e9 100%);
  color:#fff; box-shadow:var(--shadow); display:flex; align-items:center; justify-content:space-between; }
.brand{ display:flex; gap:14px; align-items:center; }
.brand .logo{ width:42px; height:42px; border-radius:13px;
  background:radial-gradient(80% 80% at 30% 20%,#67e8f9,#0284c7);
  box-shadow: inset 0 1px 4px rgba(255,255,255,.25), 0 10px 30px rgba(14,165,233,.35); }
.brand h1{ margin:0; font-size:1.1rem; font-weight:700; letter-spacing:.3px; }
.header .meta{ font-size:.9rem; opacity:.9; }
.card{ background:var(--card-bg); backdrop-filter:blur(10px); -webkit-backdrop-filter:blur(10px);
  border:1px solid rgba(255,255,255,.08); border-radius:var(--radius); padding:16px; box-shadow:var(--shadow); margin-bottom:14px; }
.card h3{ margin:.2rem 0 0; font-size:1.05rem; }
.pills{ display:flex; gap:8px; flex-wrap:wrap; }
.pill{ display:inline-flex; align-items:center; gap:8px; background:var(--pill-soft); color:var(--pill);
  padding:6px 10px; border-radius:999px; font-size:.82rem; font-weight:600; border:1px solid rgba(14,165,233,.35); }
.pill-dot{ width:8px; height:8px; border-radius:50%; background:var(--pill); display:inline-block; }
.badges{ display:flex; gap:8px; flex-wrap:wrap; margin-top:8px; }
.badge{ background:rgba(255,255,255,.08); border:1px dashed rgba(255,255,255,.15); border-radius:10px; padding:6px 10px; font-size:.8rem; }
.success{ color:var(--success); border-color:rgba(34,197,94,.35)!important; }
.warn{ color:var(--warn); border-color:rgba(234,179,8,.35)!important; }
.danger{ color:var(--danger); border-color:rgba(239,68,68,.35)!important; }
.signal-grid{ display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:12px; }
.kv{ background:rgba(255,255,255,.06); border:1px solid rgba(255,255,255,.08); border-radius:12px; padding:10px 12px; }
.kv .k{ font-size:.8rem; color:var(--muted); } .kv .v{ font-size:1.05rem; font-weight:700; margin-top:4px; }
.footer{ color:var(--muted); font-size:.8rem; text-align:right; }
</style>
"""
st.markdown(UI_CSS, unsafe_allow_html=True)

# =======================
# Logic (v3.3 + TP policy + grading + POI/FVG/OB direction)
# =======================
TICK_SIZE_DEFAULT = 0.25
SIGMA_TICKS_DEFAULT = 40.0
ADX_THRESHOLD_DEFAULT = 22.5
DEFAULT_RISK_TICKS = 40.0

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
    side = "-"
    if vals["poi_validated"] == "YES" and vals["cisd_confirmed"] == "YES":
        side = "SHORT" if vals["htf_bias"] == "BEAR" else "LONG"
    if vals["mss_above_vwap"] == "YES" and vals["vwap_side"] == "ABOVE" and vals["vwap_slope"] == "UP":
        side = "LONG"
    if vals["mss_below_vwap"] == "YES" and vals["vwap_side"] == "BELOW" and vals["vwap_slope"] == "DOWN":
        side = "SHORT"
    if (vals["mss_below_vwap"] == "YES" and vals["vwap_side"] == "BELOW"
        and vals["vwap_slope"] == "DOWN" and float(vals["adx_3m"]) > float(vals["adx_thr"])):
        side = "SHORT"
    return side

def rot_valid(vals):
    return (vals["poi_validated"] == "YES" and vals["cisd_confirmed"] == "YES" and float(vals["adx_3m"]) > float(vals["adx_thr"]))

def cont_short_valid(vals):
    return (vals["mss_below_vwap"] == "YES" and vals["vwap_side"] == "BELOW" and vals["vwap_slope"] == "DOWN" and float(vals["adx_3m"]) > float(vals["adx_thr"]))

def compute_targets(side, basis_price, sigma_price):
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

def grade_signal(side, vals, fvg_stack_count, poi_type, adx_3m, adx_thr, poi_dir):
    score = 0.0
    if vals["cisd_confirmed"] == "YES" and vals["poi_validated"] == "YES":
        score += 30
    try:
        margin = max(0.0, float(adx_3m) - float(adx_thr))
    except:
        margin = 0.0
    score += min(30.0, margin * 1.5)
    score += min(20.0, fvg_stack_count * 5.0)
    vwap_side = vals["vwap_side"]; vwap_slope = vals["vwap_slope"]
    mss_above = vals["mss_above_vwap"] == "YES"
    mss_below = vals["mss_below_vwap"] == "YES"
    full = partial = False
    if side == "LONG":
        full = (vwap_side == "ABOVE" and vwap_slope in ("UP","FLAT") and mss_above)
        partial = (vwap_side == "ABOVE" and (vwap_slope in ("UP","FLAT") or mss_above))
    elif side == "SHORT":
        full = (vwap_side == "BELOW" and vwap_slope == "DOWN" and mss_below)
        partial = (vwap_side == "BELOW" and (vwap_slope == "DOWN" or mss_below))
    score += 15.0 if full else (7.0 if partial else 0.0)
    htf = vals["htf_bias"]
    if (htf == "BULL" and side == "LONG") or (htf == "BEAR" and side == "SHORT"):
        score += 10.0
    strong_poi = ("FVG" in poi_type and poi_type in ("15M_FVG","4H_FVG")) or ("OB" in poi_type) or (poi_type in ("DO","VWAP"))
    if strong_poi: score += 5.0
    if poi_dir in ("BULLISH","BEARISH"):
        if (poi_dir == "BULLISH" and side == "LONG") or (poi_dir == "BEARISH" and side == "SHORT"):
            score += 5.0
        else:
            score -= 5.0
    score = max(0.0, min(100.0, score))
    if score >= 85: letter = "A+"
    elif score >= 75: letter = "A"
    elif score >= 65: letter = "B"
    elif score >= 50: letter = "C"
    else: letter = "D"
    return round(score,1), letter

# =======================
# Header
# =======================
st.markdown(f'''
<div class="header">
  <div class="brand">
    <div class="logo"></div>
    <div>
      <h1>Neural-LSF Signal Engine</h1>
      <div class="small">CISD / POI / VWAP / ADX / Deviations</div>
    </div>
  </div>
  <div class="meta mono">{datetime.utcnow().strftime("%Y-%m-%d %H:%M:%SZ")} UTC</div>
</div>
''', unsafe_allow_html=True)

# =======================
# Sidebar (Config)
# =======================
with st.sidebar:
    st.markdown("### Config")
    tick_size = st.number_input("Tick Size", value=float(TICK_SIZE_DEFAULT), step=0.01, format="%.4f")
    sigma_ticks = st.number_input("Sigma (ticks) — 1σ", value=float(SIGMA_TICKS_DEFAULT), step=1.0, format="%.2f")
    adx_thr = st.number_input("ADX Threshold", value=float(ADX_THRESHOLD_DEFAULT), step=0.25, format="%.2f")
    default_risk_ticks = st.number_input("Default Risk (ticks)", value=float(DEFAULT_RISK_TICKS), step=1.0, format="%.0f")
    st.markdown('<div class="hr"></div>', unsafe_allow_html=True)
    st.caption("Tip: keep sigma manual for consistent grading; bump on high-vol sessions.")

# =======================
# Inputs
# =======================
st.markdown('<div class="card"><h3>Inputs</h3>', unsafe_allow_html=True)
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
st.markdown('</div>', unsafe_allow_html=True)

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

# =======================
# POI & Structure
# =======================
st.markdown('<div class="card"><h3>POI & Structure</h3>', unsafe_allow_html=True)
c9,c10,c11,c12 = st.columns(4)
with c9:
    poi_type = st.selectbox("POI Type", [
        "1M_FVG","3M_FVG","5M_FVG","15M_FVG",
        "1M_OB","3M_OB","5M_OB","15M_OB","1H_OB","4H_OB",
        "DO","VWAP","OTHER"
    ], index=3)
with c10:
    poi_direction = st.selectbox("POI Direction", ["NEUTRAL","BULLISH","BEARISH"], index=0)
with c11:
    fvg_kind = st.selectbox("FVG Type", ["IFVG","FVG","IPDA_GAP","OTHER"], index=0)
    poi_validated = st.selectbox("POI Validated", ["YES","NO"], index=0)
with c12:
    cisd_confirmed = st.selectbox("CISD Confirmed", ["YES","NO"], index=0)

c13,c14,c15,c16 = st.columns(4)
with c13:
    mss_above = st.selectbox("MSS Above VWAP", ["YES","NO"], index=0)
with c14:
    mss_below = st.selectbox("MSS Below VWAP", ["YES","NO"], index=1)
with c15:
    fvg_3m = st.checkbox("FVG 3m present", value=True)
with c16:
    fvg_5m = st.checkbox("FVG 5m present", value=True)
fvg_1m = st.checkbox("FVG 1m present", value=False)
fvg_15m = st.checkbox("FVG 15m present", value=True)
st.markdown('</div>', unsafe_allow_html=True)

# =======================
# Targets
# =======================
st.markdown('<div class="card"><h3>Targets</h3>', unsafe_allow_html=True)
cisd_anchor = st.number_input("CISD Anchor (price)", value=0.0, step=0.25, format="%.2f")
deviation_basis = st.selectbox("Deviation Basis", ["CISD", "ENTRY", "VWAP"], index=0)
tp_policy = st.selectbox("TP Basis Policy", ["Ensure beyond entry", "Strict (use selected basis)"], index=0)
st.markdown('</div>', unsafe_allow_html=True)

# =======================
# Logic execution
# =======================
vals = dict(
    vwap_side=vwap_side, vwap_slope=vwap_slope,
    adx_3m=adx_3m, adx_thr=adx_thr,
    cisd_confirmed=cisd_confirmed, poi_validated=poi_validated,
    mss_below_vwap=mss_below, mss_above_vwap=mss_above,
    htf_bias=htf_bias
)
sigma_price = one_sigma_price(tick_size, sigma_ticks)
risk_ticks = risk_ticks_used(risk_ticks_in, DEFAULT_RISK_TICKS)

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
    basis_price = cisd_anchor

exec_basis = basis_price
if tp_policy.startswith("Ensure") and side in ("LONG","SHORT"):
    if side == "LONG" and entry:
        exec_basis = max(basis_price, entry)
    elif side == "SHORT" and entry:
        exec_basis = min(basis_price, entry)

tp1, tp2 = compute_targets(side, exec_basis, sigma_price)

# =======================
# Grading
# =======================
fvg_stack_count = int(fvg_1m) + int(fvg_3m) + int(fvg_5m) + int(fvg_15m)
grade_score, grade_letter = (None, None)
if scenario != "WAIT" and side in ("LONG","SHORT") and poi_validated == "YES" and cisd_confirmed == "YES" and float(adx_3m) > float(adx_thr):
    grade_score, grade_letter = grade_signal(side, vals, fvg_stack_count, poi_type, adx_3m, adx_thr, poi_direction)

# =======================
# Signal Card
# =======================
st.markdown('<div class="card"><h3>Signal</h3>', unsafe_allow_html=True)
st.markdown('<div class="pills">', unsafe_allow_html=True)
st.markdown(f'<span class="pill"><span class="pill-dot"></span>{scenario}</span>', unsafe_allow_html=True)
st.markdown(f'<span class="pill"><span class="pill-dot"></span>{side}</span>', unsafe_allow_html=True)
if grade_letter:
    st.markdown(
        f'<span class="pill" style="color:#22c55e;border-color:rgba(34,197,94,.35);background:rgba(34,197,94,.08)"><span class="pill-dot" style="background:#22c55e"></span>Grade {grade_letter} · {grade_score}</span>',
        unsafe_allow_html=True
    )
st.markdown('</div>', unsafe_allow_html=True)

def kv(k, v): return f'<div class="kv"><div class="k">{k}</div><div class="v mono">{v}</div></div>'
grid_html = "<div class='signal-grid'>"
grid_html += kv("Entry", f"{entry:.2f}" if entry else "-")
grid_html += kv("Stop", f"{stop:.2f}" if stop else "-")
grid_html += kv("TP1 · 2.5σ", f"{tp1:.2f}" if tp1 else "-")
grid_html += kv("TP2 · 4σ", f"{tp2:.2f}" if tp2 else "-")
grid_html += kv("1σ (price)", f"{sigma_price:.4f}")
grid_html += kv("Risk (ticks)", f"{risk_ticks:.0f}")
grid_html += kv("Basis", f"{deviation_basis} → {exec_basis:.2f}" if side in ("LONG","SHORT") and exec_basis else deviation_basis)
grid_html += kv("POI", f"{poi_type} · {poi_direction} · {fvg_kind}")
grid_html += "</div>"
st.markdown(grid_html, unsafe_allow_html=True)
st.markdown('</div>', unsafe_allow_html=True)

# Status badges
if scenario == "WAIT":
    st.markdown('<div class="badges"><div class="badge warn">Waiting — verify CISD + POI + ADX + VWAP</div></div>', unsafe_allow_html=True)
elif side == "LONG":
    st.markdown('<div class="badges"><div class="badge success">Long enabled — POI + CISD + ADX with VWAP reclaim / MSS above</div></div>', unsafe_allow_html=True)
elif side == "SHORT":
    st.markdown('<div class="badges"><div class="badge danger">Short enabled — POI + CISD + ADX with VWAP rejection / MSS below</div></div>', unsafe_allow_html=True)

# =======================
# Export
# =======================
st.markdown('<div class="card"><h3>Export</h3>', unsafe_allow_html=True)
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
        "poi_direction": poi_direction,
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
st.markdown('</div>', unsafe_allow_html=True)

st.markdown('<div class="footer">Neural-LSF · NY Bias Framework — UI v4</div>', unsafe_allow_html=True)
