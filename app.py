import streamlit as st
import pandas as pd
from fpdf import FPDF
import base64
from mftool import Mftool
import datetime
import altair as alt

# --- CONFIG ---
st.set_page_config(page_title="Universal Wealth Manager", page_icon="📈", layout="wide")
mf = Mftool()

# --- OPTIMIZED DATA LOADER (Cache: ON) ---
@st.cache_data
def get_cleaned_data():
    try:
        df = pd.read_csv('universe_data.csv')
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

if 'master_df' not in st.session_state:
    with st.spinner("Booting up the Wealth Engine..."):
        st.session_state.master_df = get_cleaned_data()

df = st.session_state.master_df
if df is None: st.error("⚠️ Database missing. Please upload 'universe_data.csv'."); st.stop()

# --- HELPER FUNCTIONS ---
def format_inr(number):
    if number >= 10000000: return f"₹{number/10000000:.2f} Cr"
    elif number >= 100000: return f"₹{number/100000:.2f} L"
    else: return f"₹{number:,.0f}"

# --- OPTIMIZED API FETCHER (Cache: ON) ---
@st.cache_data
def get_sip_history(code, monthly_amt, years):
    try:
        data = mf.get_scheme_historical_nav(str(code), as_json=False)
        if not data: return None
        nav_df = pd.DataFrame(data['data'])
        nav_df['nav'] = pd.to_numeric(nav_df['nav'])
        nav_df['date'] = pd.to_datetime(nav_df['date'], format='%d-%m-%Y')
        nav_df = nav_df.sort_values('date')
        
        start_date = datetime.datetime.now() - datetime.timedelta(days=years*365)
        nav_df = nav_df[nav_df['date'] >= start_date]
        
        nav_df.set_index('date', inplace=True)
        monthly_data = nav_df.resample('MS').first().dropna()
        
        total_units = 0; invested = 0
        for nav in monthly_data['nav']:
            total_units += monthly_amt / nav
            invested += monthly_amt
            
        latest_nav = nav_df.iloc[-1]['nav']
        current_value = total_units * latest_nav
        return invested, current_value, (current_value - invested), ((current_value/invested)-1)*100
    except: return None

# --- APP UI ---
st.title("📈 Universal Wealth Manager")
st.caption(f"Database: {len(df)} Verified Funds | Speed Optimized ⚡")

tab1, tab2 = st.tabs(["🎯 Plan Future Goals", "📊 Track Past Investments"])

# ==========================================
# TAB 1: FUTURE PLANNER
# ==========================================
with tab1:
    if 'goals' not in st.session_state: st.session_state.goals = []
    
    with st.expander("➕ Create New Goal", expanded=not st.session_state.goals):
        c1, c2, c3 = st.columns(3)
        g_name = c1.text_input("Goal Name", placeholder="e.g. Dream Home")
        g_amt = c2.number_input("Target Amount (Lakhs)", 1, 5000, 50)
        g_yrs = c3.slider("Time Horizon (Years)", 1, 30, 10)
        if st.button("Add to Dashboard"):
            st.session_state.goals.append({"name": g_name, "amt": g_amt*100000, "yrs": g_yrs})
            st.rerun()

    if st.session_state.goals:
        st.divider()
        total_sip = 0
        used_funds = []
        pdf_data = []

        for i, goal in enumerate(st.session_state.goals):
            
            # --- CARD HEADER ---
            c_title, c_del = st.columns([8, 1])
            with c_title:
                st.subheader(f"📌 {goal['name']}")
            with c_del:
                if st.button("🗑️", key=f"del_{i}", help="Delete Goal"):
                    st.session_state.goals.pop(i)
                    st.rerun()

            # --- CALCULATIONS ---
            current_amt = goal['amt'] / 100000
            current_yrs = goal['yrs']
            
            if current_yrs <= 3:
                strat, ret = "Conservative (Safe Debt)", 7
                candidates = df[(df['Category'] == 'Safe_Debt') | ((df['Std_Dev'] < 3) & (~df['Name'].str.lower().str.contains('equity')))].sort_values('Std_Dev', ascending=True)
            elif current_yrs <= 7:
                strat, ret = "Balanced (Hybrid/Large Cap)", 10
                candidates = df[(df['Is_Safe']) & (df['Risk_Grade'] != 'High') & (df['Name'].str.lower().str.contains('hybrid|large|balanced|bluechip'))].sort_values('Freq_Score', ascending=False)
            else:
                strat, ret = "Aggressive (Wealth Equity)", 13
                candidates = df[(df['Is_Safe']) & (df['Category'] == 'Equity') & (~df['Name'].str.lower().str.contains('debt|bond|income'))].sort_values(['Freq_Score', 'Avg_Return'], ascending=[False, False])
            
            # --- LAYOUT: 3 COLUMNS WITH BORDERS ---
            col1, col2, col3 = st.columns([1, 1.2, 1.3])
            
            # --- COL 1: SETTINGS & INPUTS ---
            with col1:
                with st.container(border=True):
                    st.markdown("##### ⚙️ Settings")
                    new_amt = st.number_input("Target (₹ Lakhs)", 1, 5000, int(current_amt), key=f"amt_{i}")
                    new_yrs = st.slider("Duration (Years)", 1, 30, int(current_yrs), key=f"yrs_{i}")
                    
                    st.session_state.goals[i]['amt'] = new_amt * 100000
                    st.session_state.goals[i]['yrs'] = new_yrs
                    
                    # Calc
                    r = ret/1200; n = new_yrs*12
                    target = new_amt * 100000
                    sip = target * r / ((1+r)**n - 1)
                    total_sip += sip
                    
                    st.divider()
                    st.metric("SIP Required", format_inr(sip))
                    st.caption(f"**Strategy:** {strat}")

            # --- COL 2: VISUALS (With Fixed Tooltip) ---
            with col2:
                with st.container(border=True):
                    st.markdown("##### 📊 Projection")
                    
                    total_invested = sip * n
                    est_gain = target - total_invested
                    
                    # Create Data with Pre-Formatted Label for Tooltip
                    chart_data = pd.DataFrame({
                        "Category": ["Invested", "Profit"],
                        "Amount": [total_invested, est_gain],
                        "Label": [format_inr(total_invested), format_inr(est_gain)] # This string will show in tooltip
                    })
                    
                    base = alt.Chart(chart_data).encode(theta=alt.Theta("Amount", stack=True))
                    pie = base.mark_arc(innerRadius=60, outerRadius=85).encode(
                        color=alt.Color("Category", scale=alt.Scale(domain=["Invested", "Profit"], range=['#34495E', '#2ECC71']), legend=None),
                        tooltip=["Category", alt.Tooltip("Label", title="Amount")] # Use Label instead of raw Amount
                    )
                    st.altair_chart(pie, use_container_width=True)
                    
                    # Profit Metric
                    st.metric("Estimated Profit", format_inr(est_gain), delta=f"{int((est_gain/total_invested)*100)}% Returns")
                    
                    # Inflation Reality
                    inflation_adjusted = target / ((1.06)**new_yrs)
                    st.caption(f"📉 **Inflation Reality:** {format_inr(target)} in {datetime.datetime.now().year + new_yrs} ≈ **{format_inr(inflation_adjusted)}** today.")

            # --- COL 3: FUNDS ---
            with col3:
                with st.container(border=True):
                    st.markdown("##### 🚀 Recommended Funds")
                    
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
                    
                    for _, f in recs_df.iterrows():
                        st.markdown(f"**{f['Name']}**")
                        if strat.startswith("Conservative") and f['Freq_Score'] < 3:
                            st.caption(f"🛡️ Safe Choice | Risk: {f['Risk_Grade']}")
                        else:
                            st.caption(f"⭐ Score: {int(f['Freq_Score'])}/5 | Avg Ret: {f['Avg_Return']}%")
                        st.divider()

            st.divider()
            
            pdf_data.append({
                "goal": goal['name'], "sip": format_inr(sip), 
                "invested": format_inr(total_invested), "gain": format_inr(est_gain),
                "funds": list(recs_df['Name'])
            })

        # TOTAL FOOTER
        st.success(f"### 💰 Total Monthly Investment: **{format_inr(total_sip)}**")
        
        # PDF GENERATOR
        def create_pdf(data, total):
            pdf = FPDF()
            pdf.add_page()
            pdf.set_font("Arial", 'B', 16); pdf.cell(200, 10, "Wealth Plan Breakdown", ln=True, align='C'); pdf.ln(10)
            pdf.set_font("Arial", size=12)
            for d in data:
                pdf.set_font("Arial", 'B', 12)
                pdf.cell(200, 8, f"Goal: {d['goal']}", ln=True)
                pdf.set_font("Arial", size=11)
                pdf.cell(200, 6, f" - SIP Required: {d['sip']}", ln=True)
                pdf.cell(200, 6, f" - You Invest: {d['invested']}", ln=True)
                pdf.cell(200, 6, f" - Est. Profit: {d['gain']}", ln=True)
                pdf.ln(2)
                pdf.set_font("Arial", 'I', 10)
                pdf.cell(200, 6, "Recommended Funds:", ln=True)
                for f in d['funds']: pdf.cell(200, 6, f"   {f}", ln=True)
                pdf.ln(5); pdf.set_font("Arial", size=12)
            pdf.line(10, pdf.get_y(), 200, pdf.get_y()); pdf.ln(5); pdf.set_font("Arial", 'B', 14)
            pdf.cell(200, 10, f"Total Monthly Investment: {format_inr(total)}", ln=True)
            return pdf.output(dest='S').encode('latin-1')

        if st.button("Download Detailed PDF"):
            b64 = base64.b64encode(create_pdf(pdf_data, total_sip)).decode()
            st.markdown(f'<a href="data:application/pdf;base64,{b64}" download="Plan.pdf">Click to Download PDF</a>', unsafe_allow_html=True)

# ==========================================
# TAB 2: PORTFOLIO TRACKER
# ==========================================
with tab2:
    st.header("📊 Check Your SIP Performance")
    fund_list = df['Name'].tolist()
    selected_fund_name = st.selectbox("Select Fund:", fund_list)
    c1, c2 = st.columns(2)
    sip_amt = c1.number_input("Monthly SIP (₹)", 500, 100000, 5000)
    years_ago = c2.slider("Started (Years ago)", 1, 10, 3)
    
    if st.button("Analyze Returns"):
        with st.spinner("Fetching data..."):
            fund_code = df[df['Name'] == selected_fund_name]['Code'].values[0]
            fund_stats = df[df['Code'] == fund_code].iloc[0]
            result = get_sip_history(fund_code, sip_amt, years_ago)
            
            if result:
                invested, current, gain, abs_ret = result
                m1, m2, m3 = st.columns(3)
                m1.metric("Total Invested", format_inr(invested))
                m2.metric("Current Value", format_inr(current), delta=f"{abs_ret:.1f}%")
                m3.metric("Net Profit", format_inr(gain))
                
                st.subheader("🏥 Health Check")
                score = int(fund_stats['Freq_Score'])
                if score >= 4: st.success("🌟 Excellent Fund! Keep investing.")
                elif score == 3: st.info("✅ Good Fund. Hold.")
                elif fund_stats['Category'] == 'Safe_Debt': st.success("🛡️ Safe Debt Fund.")
                else: st.error("⚠️ Underperformer. Consider switching.")
            else: st.error("Data unavailable.")