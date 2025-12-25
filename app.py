import streamlit as st
import pandas as pd
from fpdf import FPDF
import base64

# Load the CSV you generated in Phase 1
# Ensure 'universe_data.csv' is in the same folder as this script
try:
    df = pd.read_csv('universe_data.csv')
except FileNotFoundError:
    st.error("Error: 'universe_data.csv' not found. Please upload the data file.")
    st.stop()

st.set_page_config(page_title="Universal Wealth Planner", page_icon="🌌", layout="wide")

if 'goals' not in st.session_state:
    st.session_state.goals = []

st.title("🌌 Universal Wealth Planner")
st.markdown(f"**Database:** {len(df)} Equity Funds Analyzed (Direct/Growth).")
st.markdown("This tool builds a diversified, tax-efficient portfolio tailored to your life goals.")

# --- INPUT SECTION ---
with st.expander("➕ Add a Life Goal", expanded=True):
    c1, c2, c3 = st.columns(3)
    g_name = c1.text_input("Goal Name", placeholder="e.g. Dream Home")
    g_amt = c2.number_input("Target Amount (₹ Lakhs)", 1, 5000, 50)
    g_yrs = c3.slider("Years to Goal", 1, 30, 10)
    
    if st.button("Add to Plan"):
        if g_name:
            st.session_state.goals.append({"name": g_name, "amt": g_amt*100000, "yrs": g_yrs})
            st.success(f"Added {g_name}")
            st.rerun()

# --- LOGIC ENGINE ---
if st.session_state.goals:
    st.divider()
    st.header("Your Personalized Roadmap")
    
    total_sip = 0
    used_funds = []
    pdf_data = []

    for i, goal in enumerate(st.session_state.goals):
        c_head, c_del = st.columns([6, 1])
        c_head.subheader(f"{i+1}. {goal['name']} (₹{goal['amt']/100000}L in {goal['yrs']} Yrs)")
        
        if c_del.button("🗑️", key=f"del_{i}", help="Remove Goal"):
            st.session_state.goals.pop(i)
            st.rerun()
        
        # Strategy Selector
        if goal['yrs'] <= 3:
            strat, ret, note = "Conservative (Debt/Hybrid Focus)", 9, "Move to FD 6-12 months before goal."
            # Prioritize Low Volatility (Risk < Avg)
            candidates = df.sort_values('Std_Dev', ascending=True)
        elif goal['yrs'] <= 7:
            strat, ret, note = "Balanced (Growth + Stability)", 12, "Start SWP 18 months before goal."
            # Exclude High Risk, Prioritize Consistency
            candidates = df[df['Risk_Grade'] != 'High'].sort_values('Freq_Score', ascending=False)
        else:
            strat, ret, note = "Aggressive (Wealth Creation)", 14, "Stay Invested. Ignore short-term volatility."
            # Prioritize Consistency + High Returns
            candidates = df.sort_values(['Freq_Score', 'Avg_Return'], ascending=[False, False])
        
        # Smart Diversification (Avoid Repeats)
        fresh_picks = candidates[~candidates['Code'].isin(used_funds)]
        if fresh_picks.empty: fresh_picks = candidates
        recommendations = fresh_picks.head(2)
        used_funds.extend(recommendations['Code'].tolist())

        # SIP Math
        r = ret / 100 / 12
        n = goal['yrs'] * 12
        sip = goal['amt'] * r / ((1+r)**n - 1)
        total_sip += sip
        
        # Display
        with st.container():
            c1, c2 = st.columns([1, 2])
            with c1:
                st.metric("SIP Required", f"₹{sip:,.0f}/mo")
                st.caption(f"Strategy: {strat}")
                st.info(f"💡 {note}")
            with c2:
                st.write("**Recommended Funds:**")
                for _, f in recommendations.iterrows():
                    st.markdown(f"- **{f['Name']}**")
                    st.caption(f"Score: {int(f['Freq_Score'])}/5 | Risk: {f['Risk_Grade']} | Avg Ret: {f['Avg_Return']}%")
        st.divider()
        
        pdf_data.append({
            "goal": goal['name'], "sip": f"Rs {sip:,.0f}", 
            "funds": [f"{f['Name']} (Score: {int(f['Freq_Score'])})" for _, f in recommendations.iterrows()]
        })

    st.markdown(f"### 💰 Total Monthly Investment: **₹{total_sip:,.0f}**")

    # PDF Logic
    def create_pdf(data_list, total):
        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Arial", 'B', 16)
        pdf.cell(200, 10, txt="Financial Life Plan", ln=True, align='C')
        pdf.ln(10)
        pdf.set_font("Arial", size=12)
        for item in data_list:
            pdf.set_font("Arial", 'B', 12)
            pdf.cell(200, 10, txt=f"Goal: {item['goal']}", ln=True)
            pdf.set_font("Arial", size=12)
            pdf.cell(200, 8, txt=f"Required SIP: {item['sip']}", ln=True)
            pdf.cell(200, 8, txt=f"Strategy Funds:", ln=True)
            for fund in item['funds']:
                pdf.cell(200, 6, txt=f" - {fund}", ln=True)
            pdf.ln(5)
        pdf.line(10, pdf.get_y(), 200, pdf.get_y())
        pdf.ln(5)
        pdf.set_font("Arial", 'B', 14)
        pdf.cell(200, 10, txt=f"Total Monthly Investment: Rs {total:,.0f}", ln=True)
        return pdf.output(dest='S').encode('latin-1')

    if st.button("📄 Download Plan as PDF"):
        pdf_bytes = create_pdf(pdf_data, total_sip)
        b64 = base64.b64encode(pdf_bytes).decode()
        href = f'<a href="data:application/pdf;base64,{b64}" download="Wealth_Plan.pdf">Click here to download PDF</a>'
        st.markdown(href, unsafe_allow_html=True)