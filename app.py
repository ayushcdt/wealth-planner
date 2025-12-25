import streamlit as st
import pandas as pd
from fpdf import FPDF
import base64
from mftool import Mftool
import datetime

# --- CONFIG ---
st.set_page_config(page_title="Universal Wealth Manager", page_icon="📈", layout="wide")
mf = Mftool()

# --- LOAD DATABASE ---
@st.cache_data
def load_data():
    try:
        df = pd.read_csv('universe_data.csv')
        # Cleaning & Safety Filters
        df = df[~df['Name'].str.lower().str.contains('bonus|dividend')]
        zombies = ['reliance', 'fixed tenure', 'dual advantage', 'capital protection', 'interval', 'quarterly', 'series']
        df = df[~df['Name'].str.lower().apply(lambda x: any(z in x for z in zombies))]
        
        risky_keywords = ['sector', 'thematic', 'international', 'global', 'gold', 'commodity', 'psu', 'infra', 'tech']
        def is_safe(row):
            if row['Category'] == 'Equity':
                return not any(k in row['Name'].lower() for k in risky_keywords)
            return True
            
        df['Is_Safe'] = df.apply(is_safe, axis=1)
        return df
    except: return None

df = load_data()
if df is None: st.error("⚠️ Database missing. Please upload 'universe_data.csv'."); st.stop()

# --- HELPER FUNCTIONS ---
def format_inr(number):
    if number >= 10000000: return f"₹{number/10000000:.2f} Cr"
    elif number >= 100000: return f"₹{number/100000:.2f} L"
    else: return f"₹{number:,.0f}"

def get_sip_history(code, monthly_amt, years):
    try:
        # Live Fetch for specific fund accuracy
        data = mf.get_scheme_historical_nav(str(code), as_json=False)
        if not data: return None
        
        nav_df = pd.DataFrame(data['data'])
        nav_df['nav'] = pd.to_numeric(nav_df['nav'])
        nav_df['date'] = pd.to_datetime(nav_df['date'], format='%d-%m-%Y')
        nav_df = nav_df.sort_values('date') # Oldest to Newest
        
        # Filter for duration
        start_date = datetime.datetime.now() - datetime.timedelta(days=years*365)
        nav_df = nav_df[nav_df['date'] >= start_date]
        
        # Simulate Monthly SIP (Resample to Business Month Start)
        nav_df.set_index('date', inplace=True)
        # We take the 1st available NAV of every month
        monthly_data = nav_df.resample('MS').first().dropna()
        
        total_units = 0
        invested = 0
        
        # Calculate Accumulation
        for nav in monthly_data['nav']:
            units = monthly_amt / nav
            total_units += units
            invested += monthly_amt
            
        latest_nav = nav_df.iloc[-1]['nav']
        current_value = total_units * latest_nav
        
        return invested, current_value, (current_value - invested), ((current_value/invested)-1)*100
    except: return None

# --- APP UI ---
st.title("📈 Universal Wealth Manager")
st.caption(f"Database: {len(df)} Verified Funds")

# --- TABS ---
tab1, tab2 = st.tabs(["🎯 Plan Future Goals", "📊 Track Past Investments"])

# ==========================================
# TAB 1: FUTURE PLANNER (Your Existing Tool)
# ==========================================
with tab1:
    if 'goals' not in st.session_state: st.session_state.goals = []
    
    with st.expander("➕ Add a Life Goal", expanded=True):
        c1, c2, c3 = st.columns(3)
        g_name = c1.text_input("Goal Name")
        g_amt = c2.number_input("Target (Lakhs)", 1, 5000, 50)
        g_yrs = c3.slider("Years", 1, 30, 10)
        if st.button("Add Goal"):
            st.session_state.goals.append({"name": g_name, "amt": g_amt*100000, "yrs": g_yrs})
            st.rerun()

    if st.session_state.goals:
        st.divider()
        total_sip = 0
        used_funds = []
        pdf_data = []

        for i, goal in enumerate(st.session_state.goals):
            c_head, c_del = st.columns([6, 1])
            c_head.subheader(f"{i+1}. {goal['name']} ({format_inr(goal['amt'])})")
            if c_del.button("🗑️", key=f"del_{i}"):
                st.session_state.goals.pop(i)
                st.rerun()
            
            # STRATEGY ENGINE
            if goal['yrs'] <= 3:
                strat, ret = "Conservative (Safe Debt)", 7
                candidates = df[(df['Category'] == 'Safe_Debt') | ((df['Std_Dev'] < 3) & (~df['Name'].str.lower().str.contains('equity')))].sort_values('Std_Dev', ascending=True)
            elif goal['yrs'] <= 7:
                strat, ret = "Balanced (Hybrid/Large Cap)", 10
                candidates = df[(df['Is_Safe']) & (df['Risk_Grade'] != 'High') & (df['Name'].str.lower().str.contains('hybrid|large|balanced|bluechip'))].sort_values('Freq_Score', ascending=False)
            else:
                strat, ret = "Aggressive (Wealth Equity)", 13
                candidates = df[(df['Is_Safe']) & (df['Category'] == 'Equity') & (~df['Name'].str.lower().str.contains('debt|bond|income'))].sort_values(['Freq_Score', 'Avg_Return'], ascending=[False, False])
            
            # DIVERSIFICATION
            recs = []
            curr_amcs = []
            for _, fund in candidates.iterrows():
                if len(recs) >= 2: break
                amc = fund['Name'].split()[0]
                if fund['Code'] not in used_funds and amc not in curr_amcs:
                    recs.append(fund)
                    used_funds.append(fund['Code'])
                    curr_amcs.append(amc)
            recs_df = pd.DataFrame(recs)

            # CALC
            r = ret/1200; n = goal['yrs']*12
            sip = goal['amt'] * r / ((1+r)**n - 1)
            total_sip += sip
            
            # DISPLAY
            with st.container():
                c1, c2 = st.columns([1, 1.5])
                with c1:
                    st.metric("SIP Required", f"{format_inr(sip)}/mo")
                    st.caption(f"Strategy: {strat}")
                with c2:
                    for _, f in recs_df.iterrows():
                        st.markdown(f"**{f['Name']}**")
                        # Contextual Explainer
                        if strat.startswith("Conservative") and f['Freq_Score'] < 3:
                            st.caption(f"🛡️ Safe Choice (Low Volatility) | Risk: {f['Risk_Grade']}")
                        else:
                            st.caption(f"Score: {int(f['Freq_Score'])}/5 | Avg Ret: {f['Avg_Return']}%")
            st.divider()
            pdf_data.append({"goal": goal['name'], "sip": format_inr(sip), "funds": list(recs_df['Name'])})

        st.markdown(f"### 💰 Total Monthly Investment: **{format_inr(total_sip)}**")
        
        # PDF GENERATOR
        def create_pdf(data, total):
            pdf = FPDF()
            pdf.add_page()
            pdf.set_font("Arial", 'B', 16); pdf.cell(200, 10, "Wealth Plan", ln=True, align='C'); pdf.ln(10)
            pdf.set_font("Arial", size=12)
            for d in data:
                pdf.cell(200, 8, f"Goal: {d['goal']} | SIP: {d['sip']}", ln=True)
                pdf.set_font("Arial", size=10)
                for f in d['funds']: pdf.cell(200, 6, f" - {f}", ln=True)
                pdf.ln(5); pdf.set_font("Arial", size=12)
            pdf.line(10, pdf.get_y(), 200, pdf.get_y()); pdf.ln(5); pdf.set_font("Arial", 'B', 14)
            pdf.cell(200, 10, f"Total Monthly: {format_inr(total)}", ln=True)
            return pdf.output(dest='S').encode('latin-1')

        if st.button("Download PDF"):
            b64 = base64.b64encode(create_pdf(pdf_data, total_sip)).decode()
            st.markdown(f'<a href="data:application/pdf;base64,{b64}" download="Plan.pdf">Click to Download PDF</a>', unsafe_allow_html=True)

# ==========================================
# TAB 2: PORTFOLIO TRACKER (The New Feature)
# ==========================================
with tab2:
    st.header("📊 Check Your SIP Performance")
    st.markdown("Analyze how your existing investments have performed over time.")
    
    # 1. Select Fund
    fund_list = df['Name'].tolist()
    selected_fund_name = st.selectbox("Select Fund you Invested in:", fund_list)
    
    c1, c2 = st.columns(2)
    sip_amt = c1.number_input("Monthly SIP Amount (₹)", 500, 100000, 5000)
    years_ago = c2.slider("Started how many years ago?", 1, 10, 3)
    
    if st.button("Analyze Returns"):
        with st.spinner("Fetching historical data..."):
            # Find the code for the selected name
            fund_code = df[df['Name'] == selected_fund_name]['Code'].values[0]
            fund_stats = df[df['Code'] == fund_code].iloc[0]
            
            # Calculate Backtest
            result = get_sip_history(fund_code, sip_amt, years_ago)
            
            if result:
                invested, current, gain, abs_ret = result
                
                # A. The Numbers
                m1, m2, m3 = st.columns(3)
                m1.metric("Total Invested", format_inr(invested))
                m2.metric("Current Value", format_inr(current), delta=f"{abs_ret:.1f}%")
                m3.metric("Net Profit", format_inr(gain))
                
                st.divider()
                
                # B. The Health Check (Consistency Audit)
                st.subheader("🏥 Portfolio Health Check")
                score = int(fund_stats['Freq_Score'])
                
                col_score, col_advice = st.columns([1, 3])
                
                with col_score:
                    st.metric("Quality Score", f"{score}/5")
                
                with col_advice:
                    if score >= 4:
                        st.success("🌟 **Excellent Fund!** This fund is a consistent winner. Keep investing.")
                    elif score == 3:
                        st.info("✅ **Good Fund.** It performs reasonably well. Hold.")
                    elif fund_stats['Category'] == 'Safe_Debt':
                         st.success("🛡️ **Safe Debt Fund.** Ignore the score. It is doing its job of keeping money safe.")
                    else:
                        st.error("⚠️ **Underperformer.** This fund has rarely beaten the market. Consider switching to a 4/5 or 5/5 fund.")
                
            else:
                st.error("Could not fetch historical data for this fund. Try a different one.")