import streamlit as st
import pandas as pd
from fpdf import FPDF
import base64

st.set_page_config(page_title="Universal Wealth Planner", page_icon="🌌", layout="wide")

@st.cache_data
def load_data():
    try:
        df = pd.read_csv('universe_data.csv')
        
        # 1. REMOVE DUPLICATES (Keep only one variant per fund code)
        # We prefer 'Growth' over 'Bonus' or 'Dividend'
        df = df[~df['Name'].str.lower().str.contains('bonus|dividend')]
        
        # 2. SAFETY FILTER
        risky_keywords = ['sector', 'thematic', 'international', 'global', 'gold', 'commodity', 'psu', 'infra', 'tech']
        # Note: We apply this mainly to Equity. For Debt, 'PSU' is actually safe (Banking & PSU Debt).
        
        def is_safe(row):
            n = row['Name'].lower()
            # If it's an Equity fund, check for risky keywords
            if row['Category'] == 'Equity':
                return not any(k in n for k in risky_keywords)
            return True # Debt/Liquid is generally safe from "Sector" risks
            
        df['Is_Safe'] = df.apply(is_safe, axis=1)
        return df
    except: return None

df = load_data()
if df is None:
    st.error("⚠️ Data file not found.")
    st.stop()

# --- HELPER ---
def format_inr(number):
    if number >= 10000000: return f"₹{number/10000000:.2f} Cr"
    elif number >= 100000: return f"₹{number/100000:.2f} L"
    else: return f"₹{number:,.0f}"

if 'goals' not in st.session_state: st.session_state.goals = []

st.title("🌌 Universal Wealth Planner")
st.caption(f"Database: {len(df)} Clean Funds | 'Bonus' Options Removed")

# --- INPUT ---
with st.expander("➕ Add a Life Goal", expanded=True):
    c1, c2, c3 = st.columns(3)
    g_name = c1.text_input("Goal Name")
    g_amt = c2.number_input("Target (Lakhs)", 1, 5000, 50)
    g_yrs = c3.slider("Years", 1, 30, 10)
    if st.button("Add"):
        st.session_state.goals.append({"name": g_name, "amt": g_amt*100000, "yrs": g_yrs})
        st.rerun()

# --- ENGINE ---
if st.session_state.goals:
    st.divider()
    total_sip = 0
    used_funds = [] # Global list to avoid repeats across DIFFERENT goals
    pdf_data = []

    for i, goal in enumerate(st.session_state.goals):
        c_head, c_del = st.columns([6, 1])
        c_head.subheader(f"{i+1}. {goal['name']} ({format_inr(goal['amt'])} in {goal['yrs']} Yrs)")
        if c_del.button("🗑️", key=f"del_{i}"):
            st.session_state.goals.pop(i)
            st.rerun()
        
        # STRATEGY
        if goal['yrs'] <= 3:
            strat, ret = "Conservative (Safe Debt)", 7
            candidates = df[
                (df['Category'] == 'Safe_Debt') | 
                ((df['Std_Dev'] < 3) & (~df['Name'].str.lower().str.contains('equity')))
            ].sort_values('Std_Dev', ascending=True)

        elif goal['yrs'] <= 7:
            strat, ret = "Balanced (Hybrid/Large Cap)", 10
            candidates = df[
                (df['Is_Safe']) & 
                (df['Risk_Grade'] != 'High') &
                (df['Name'].str.lower().str.contains('hybrid|large|balanced|bluechip'))
            ].sort_values('Freq_Score', ascending=False)

        else:
            strat, ret = "Aggressive (Wealth Equity)", 13
            candidates = df[
                (df['Is_Safe']) & 
                (df['Category'] == 'Equity') & 
                (~df['Name'].str.lower().str.contains('debt|bond|income'))
            ].sort_values(['Freq_Score', 'Avg_Return'], ascending=[False, False])
        
        # DIVERSIFICATION LOGIC
        # 1. Remove funds used in previous goals
        # 2. Remove funds from same AMC in current goal (e.g. don't pick 2 Nippon funds)
        
        recs = []
        current_goal_amcs = []
        
        # Iterate through candidates
        for _, fund in candidates.iterrows():
            if len(recs) >= 2: break # We only need 2
            
            # Extract AMC Name (First word usually, e.g., "Nippon", "HDFC")
            amc_name = fund['Name'].split()[0]
            
            if fund['Code'] not in used_funds and amc_name not in current_goal_amcs:
                recs.append(fund)
                used_funds.append(fund['Code'])
                current_goal_amcs.append(amc_name)
        
        recs_df = pd.DataFrame(recs)

        # MATH
        r = ret/1200
        n = goal['yrs']*12
        sip = goal['amt'] * r / ((1+r)**n - 1)
        total_sip += sip
        gains = goal['amt'] - (sip*n)
        tax = (gains - 125000) * 0.125 if gains > 125000 else 0

        # DISPLAY
        with st.container():
            c1, c2 = st.columns([1, 1.5])
            with c1:
                st.metric("SIP Required", f"{format_inr(sip)}/mo")
                st.caption(f"Strategy: {strat}")
                if tax > 50000: st.warning(f"⚠️ Est. Tax: {format_inr(tax)}")
                else: st.success("✅ Tax efficient")
            with c2:
                for _, f in recs_df.iterrows():
                    st.markdown(f"**{f['Name']}**")
                    st.caption(f"Score: {int(f['Freq_Score'])}/5 | Risk: {f['Risk_Grade']} | Avg Ret: {f['Avg_Return']}%")
        st.divider()
        pdf_data.append({"goal": goal['name'], "sip": format_inr(sip), "funds": list(recs_df['Name'])})

    st.markdown(f"### 💰 Total Monthly Investment: **{format_inr(total_sip)}**")
    
    # PDF
    def create_pdf(data, total):
        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Arial", 'B', 16)
        pdf.cell(200, 10, "Wealth Plan", ln=True, align='C')
        pdf.ln(10)
        pdf.set_font("Arial", size=12)
        for d in data:
            pdf.cell(200, 8, f"Goal: {d['goal']} | SIP: {d['sip']}", ln=True)
            for f in d['funds']: pdf.cell(200, 6, f" - {f}", ln=True)
            pdf.ln(5)
        return pdf.output(dest='S').encode('latin-1')

    if st.button("📄 Download Plan as PDF"):
        b64 = base64.b64encode(create_pdf(pdf_data, total_sip)).decode()
        st.markdown(f'<a href="data:application/pdf;base64,{b64}" download="Plan.pdf">Click to Download PDF</a>', unsafe_allow_html=True)