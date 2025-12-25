import streamlit as st
import pandas as pd
from fpdf import FPDF
import base64

# --- CONFIG & LOAD DATA ---
st.set_page_config(page_title="Universal Wealth Planner", page_icon="🌌", layout="wide")

@st.cache_data
def load_data():
    try:
        df = pd.read_csv('universe_data.csv')
        # --- SAFETY FILTER ---
        # We filter out risky categories from recommendations, 
        # but keep them in the file for reference.
        risky_keywords = [
            'sector', 'thematic', 'international', 'global', 'gold', 'commodity',
            'tech', 'pharma', 'infra', 'psu', 'manufacturing', 'energy'
        ]
        # Create a "Safe" flag
        df['Is_Safe'] = ~df['Name'].str.lower().apply(lambda x: any(k in x for k in risky_keywords))
        return df
    except FileNotFoundError:
        return None

df = load_data()

if df is None:
    st.error("⚠️ 'universe_data.csv' not found! Please upload it to your GitHub repository.")
    st.stop()

# --- HELPER FUNCTIONS ---
def format_inr(number):
    if number >= 10000000: return f"₹{number/10000000:.2f} Cr"
    elif number >= 100000: return f"₹{number/100000:.2f} L"
    else: return f"₹{number:,.0f}"

if 'goals' not in st.session_state:
    st.session_state.goals = []

# --- UI HEADER ---
st.title("🌌 Universal Wealth Planner")
st.markdown(f"**Database:** {len(df)} Funds (Equity, Debt, Hybrid, Index).")
st.caption("Powered by 'God Mode' Analysis Engine")

# --- INPUT ---
with st.expander("➕ Add a Life Goal", expanded=True):
    c1, c2, c3 = st.columns(3)
    g_name = c1.text_input("Goal Name", placeholder="e.g. Retirement")
    g_input = c2.number_input("Target Amount", min_value=1, value=50, help="Enter in Lakhs (e.g., 100 = 1 Cr)")
    g_yrs = c3.slider("Years to Goal", 1, 30, 10)
    c2.caption(f"Target: {format_inr(g_input * 100000)}")

    if st.button("Add to Plan"):
        if g_name:
            st.session_state.goals.append({"name": g_name, "amt": g_input * 100000, "yrs": g_yrs})
            st.success(f"Added {g_name}")
            st.rerun()

# --- ENGINE ---
if st.session_state.goals:
    st.divider()
    st.header("Your Personalized Roadmap")
    
    total_sip = 0
    used_funds = []
    pdf_data = []

    for i, goal in enumerate(st.session_state.goals):
        c_head, c_del = st.columns([6, 1])
        c_head.subheader(f"{i+1}. {goal['name']} ({format_inr(goal['amt'])} in {goal['yrs']} Yrs)")
        if c_del.button("🗑️", key=f"del_{i}"):
            st.session_state.goals.pop(i)
            st.rerun()
        
        # STRATEGY SELECTOR
        if goal['yrs'] <= 3:
            strat, ret, note = "Conservative", 7, "Short term: Use Liquid/Ultra-Short Debt."
            # Filter: Debt/Liquid Keywords OR Low Risk
            candidates = df[df['Name'].str.lower().str.contains('liquid|debt|bond|overnight') | (df['Std_Dev'] < 5)]
            candidates = candidates.sort_values('Std_Dev', ascending=True)
            
        elif goal['yrs'] <= 7:
            strat, ret, note = "Balanced", 10, "Medium term: Use Hybrid or Large Cap."
            # Filter: Safe Equity only
            candidates = df[(df['Is_Safe'] == True) & (df['Risk_Grade'] != 'High')]
            candidates = candidates.sort_values('Freq_Score', ascending=False)
            
        else:
            strat, ret, note = "Aggressive", 13, "Long term: pure Equity wealth creation."
            # Filter: Safe Equity, sorted by Consistency + Return
            candidates = df[df['Is_Safe'] == True].sort_values(['Freq_Score', 'Avg_Return'], ascending=[False, False])
        
        # DIVERSIFICATION
        fresh = candidates[~candidates['Code'].isin(used_funds)]
        if fresh.empty: fresh = candidates
        recommendations = fresh.head(2)
        used_funds.extend(recommendations['Code'].tolist())

        # MATH
        r = ret / 100 / 12
        n = goal['yrs'] * 12
        sip = goal['amt'] * r / ((1+r)**n - 1)
        total_sip += sip
        
        # TAX (LTCG > 1.25L is 12.5%)
        gains = goal['amt'] - (sip * n)
        tax = (gains - 125000) * 0.125 if gains > 125000 else 0

        # DISPLAY
        with st.container():
            c1, c2 = st.columns([1, 1.5])
            with c1:
                st.metric("SIP Required", f"{format_inr(sip)}/mo")
                st.caption(f"Strategy: {strat} ({ret}%)")
                if tax > 50000: st.warning(f"⚠️ Est. Tax: {format_inr(tax)}")
                else: st.success("✅ Tax efficient")
            with c2:
                st.write("**Recommended Funds:**")
                for _, f in recommendations.iterrows():
                    st.markdown(f"**{f['Name']}**")
                    st.caption(f"Score: {int(f['Freq_Score'])}/5 | Risk: {f['Risk_Grade']} | Avg Ret: {f['Avg_Return']}%")
        st.divider()
        
        pdf_data.append({
            "goal": goal['name'], "target": format_inr(goal['amt']),
            "sip": format_inr(sip), "funds": list(recommendations['Name'])
        })

    st.markdown(f"### 💰 Total Monthly Investment: **{format_inr(total_sip)}**")

    # PDF GEN
    def create_pdf(data, total):
        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Arial", 'B', 16)
        pdf.cell(200, 10, txt="Financial Life Plan", ln=True, align='C')
        pdf.ln(10)
        pdf.set_font("Arial", size=12)
        for item in data:
            pdf.set_font("Arial", 'B', 12)
            pdf.cell(200, 10, txt=f"Goal: {item['goal']} ({item['target']})", ln=True)
            pdf.set_font("Arial", size=12)
            pdf.cell(200, 8, txt=f"SIP: {item['sip']}", ln=True)
            pdf.cell(200, 8, txt="Funds:", ln=True)
            for f in item['funds']: pdf.cell(200, 6, txt=f"- {f}", ln=True)
            pdf.ln(5)
        pdf.line(10, pdf.get_y(), 200, pdf.get_y())
        pdf.ln(5)
        pdf.set_font("Arial", 'B', 14)
        pdf.cell(200, 10, txt=f"Total Monthly: {format_inr(total)}", ln=True)
        return pdf.output(dest='S').encode('latin-1')

    if st.button("📄 Download Plan as PDF"):
        b64 = base64.b64encode(create_pdf(pdf_data, total_sip)).decode()
        st.markdown(f'<a href="data:application/pdf;base64,{b64}" download="Plan.pdf">Download PDF</a>', unsafe_allow_html=True)