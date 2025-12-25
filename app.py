import streamlit as st
import pandas as pd
from fpdf import FPDF
import base64

# --- PAGE CONFIG ---
st.set_page_config(page_title="Universal Wealth Planner", page_icon="🌌", layout="wide")

# --- DATA LOADING & CLEANING ---
@st.cache_data
def load_data():
    try:
        df = pd.read_csv('universe_data.csv')
        
        # 1. REMOVE DUPLICATES (Keep Growth only, remove Bonus/Dividend)
        df = df[~df['Name'].str.lower().str.contains('bonus|dividend')]
        
        # 2. REMOVE "ZOMBIE" FUNDS (Old/Closed/Dead Schemes)
        # 'Reliance' is now Nippon. 'Fixed Tenure'/'Dual Advantage' are closed.
        zombies = [
            'reliance', 'fixed tenure', 'dual advantage', 'capital protection',
            'interval', 'quarterly', 'series', 'closed ended'
        ]
        df = df[~df['Name'].str.lower().apply(lambda x: any(z in x for z in zombies))]
        
        # 3. SAFETY TAGGING
        # We flag sector funds so we can exclude them from general recommendations
        risky_keywords = ['sector', 'thematic', 'international', 'global', 'gold', 'commodity', 'psu', 'infra', 'tech']
        
        def is_safe(row):
            n = row['Name'].lower()
            # If it's an Equity fund, check for risky keywords. 
            # (Debt funds with 'PSU' in name are actually safe, so we ignore them here)
            if row['Category'] == 'Equity':
                return not any(k in n for k in risky_keywords)
            return True 
            
        df['Is_Safe'] = df.apply(is_safe, axis=1)
        return df
    except: return None

df = load_data()

if df is None:
    st.error("⚠️ 'universe_data.csv' not found. Please upload it to your GitHub repository.")
    st.stop()

# --- HELPER FUNCTIONS ---
def format_inr(number):
    if number >= 10000000: return f"₹{number/10000000:.2f} Cr"
    elif number >= 100000: return f"₹{number/100000:.2f} L"
    else: return f"₹{number:,.0f}"

if 'goals' not in st.session_state: st.session_state.goals = []

# --- UI HEADER ---
st.title("🌌 Universal Wealth Planner")
st.caption(f"Database: {len(df)} Funds | Cleaned & Verified")

# --- INPUT SECTION ---
with st.expander("➕ Add a Life Goal", expanded=True):
    c1, c2, c3 = st.columns(3)
    g_name = c1.text_input("Goal Name", placeholder="e.g. Retirement")
    g_amt = c2.number_input("Target Amount (Lakhs)", 1, 5000, 50, help="100 = 1 Crore")
    g_yrs = c3.slider("Years to Goal", 1, 30, 10)
    
    if st.button("Add to Plan"):
        if g_name:
            st.session_state.goals.append({"name": g_name, "amt": g_amt*100000, "yrs": g_yrs})
            st.rerun()

# --- PLANNER ENGINE ---
if st.session_state.goals:
    st.divider()
    total_sip = 0
    used_funds = [] # Global list to avoid repeating a fund across different goals
    pdf_data = []

    for i, goal in enumerate(st.session_state.goals):
        c_head, c_del = st.columns([6, 1])
        c_head.subheader(f"{i+1}. {goal['name']} ({format_inr(goal['amt'])} in {goal['yrs']} Yrs)")
        if c_del.button("🗑️", key=f"del_{i}"):
            st.session_state.goals.pop(i)
            st.rerun()
        
        # --- STRATEGY SELECTOR ---
        
        # 1. SHORT TERM (< 3 Years) -> DEBT ONLY
        if goal['yrs'] <= 3:
            strat, ret = "Conservative (Safe Debt)", 7
            # Logic: Must be 'Safe_Debt' OR Low Risk + No Equity in name
            candidates = df[
                (df['Category'] == 'Safe_Debt') | 
                ((df['Std_Dev'] < 3) & (~df['Name'].str.lower().str.contains('equity')))
            ].sort_values('Std_Dev', ascending=True)

        # 2. MEDIUM TERM (4-7 Years) -> HYBRID / BALANCED
        elif goal['yrs'] <= 7:
            strat, ret = "Balanced (Hybrid/Large Cap)", 10
            # Logic: Safe Equity/Hybrid + Not High Risk
            candidates = df[
                (df['Is_Safe']) & 
                (df['Risk_Grade'] != 'High') &
                (df['Name'].str.lower().str.contains('hybrid|large|balanced|bluechip'))
            ].sort_values('Freq_Score', ascending=False)

        # 3. LONG TERM (8+ Years) -> PURE EQUITY
        else:
            strat, ret = "Aggressive (Wealth Equity)", 13
            # Logic: Pure Equity only. EXCLUDE Debt/Income keywords to prevent "Franklin Debt" issue.
            candidates = df[
                (df['Is_Safe']) & 
                (df['Category'] == 'Equity') & 
                (~df['Name'].str.lower().str.contains('debt|bond|income'))
            ].sort_values(['Freq_Score', 'Avg_Return'], ascending=[False, False])
        
        # --- DIVERSIFICATION LOGIC ---
        # 1. Filter out funds already used in previous goals (Global uniqueness)
        # 2. Ensure we don't pick two funds from the same AMC for THIS goal (Local uniqueness)
        
        recs = []
        current_goal_amcs = []
        
        # Iterate through candidates
        for _, fund in candidates.iterrows():
            if len(recs) >= 2: break # We only need 2 recommendations
            
            # Extract AMC Name (First word usually, e.g., "Nippon", "HDFC", "ICICI")
            amc_name = fund['Name'].split()[0]
            
            # Check if used globally OR if AMC is already used in this specific goal
            if fund['Code'] not in used_funds and amc_name not in current_goal_amcs:
                recs.append(fund)
                used_funds.append(fund['Code'])
                current_goal_amcs.append(amc_name)
        
        recs_df = pd.DataFrame(recs)

        # --- MATH & TAX ---
        r = ret/1200
        n = goal['yrs']*12
        sip = goal['amt'] * r / ((1+r)**n - 1)
        total_sip += sip
        gains = goal['amt'] - (sip*n)
        tax = (gains - 125000) * 0.125 if gains > 125000 else 0

        # --- DISPLAY ---
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
    
    # --- PDF GENERATION ---
    def create_pdf(data, total):
        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Arial", 'B', 16)
        pdf.cell(200, 10, "Personalized Wealth Plan", ln=True, align='C')
        pdf.ln(10)
        pdf.set_font("Arial", size=12)
        for d in data:
            pdf.set_font("Arial", 'B', 12)
            pdf.cell(200, 8, f"Goal: {d['goal']} | SIP: {d['sip']}", ln=True)
            pdf.set_font("Arial", size=10) 
            for f in d['funds']: pdf.cell(200, 6, f" - {f}", ln=True)
            pdf.ln(5)
        pdf.line(10, pdf.get_y(), 200, pdf.get_y())
        pdf.ln(5)
        pdf.set_font("Arial", 'B', 14)
        pdf.cell(200, 10, f"Total Monthly Investment: {format_inr(total)}", ln=True)
        return pdf.output(dest='S').encode('latin-1')

    if st.button("📄 Download Plan as PDF"):
        b64 = base64.b64encode(create_pdf(pdf_data, total_sip)).decode()
        st.markdown(f'<a href="data:application/pdf;base64,{b64}" download="My_Wealth_Plan.pdf">Click here to Download PDF</a>', unsafe_allow_html=True)