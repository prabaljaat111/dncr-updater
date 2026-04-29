import streamlit as st
import pandas as pd
import io
import re
from datetime import datetime

# ============================================
# PAGE CONFIG
# ============================================
st.set_page_config(
    page_title="DNCR Auto Updater",
    page_icon="📞",
    layout="wide"
)

# ============================================
# HEADER
# ============================================
st.markdown("""
    <div style="background: linear-gradient(90deg, #1e3a8a 0%, #3b82f6 100%); 
                padding: 25px; border-radius: 10px; margin-bottom: 25px;">
        <h1 style="color: white; margin: 0;">📞 DNCR Automatic File Check & Data Updater</h1>
        <p style="color: #e0e7ff; margin: 5px 0 0 0;">
            Automatically match DNCR results to your master lead sheet — no manual VLOOKUP needed!
        </p>
    </div>
""", unsafe_allow_html=True)

# ============================================
# HELPER FUNCTIONS
# ============================================
def normalize_uae_number(num):
    """Normalize UAE phone numbers to a standard 971XXXXXXXXX format."""
    if pd.isna(num):
        return None
    # Convert to string and remove all non-digits
    s = re.sub(r'\D', '', str(num))
    if not s:
        return None
    # Remove leading zeros
    s = s.lstrip('0')
    # Handle different formats
    if s.startswith('971'):
        return s
    elif len(s) == 9 and s.startswith('5'):  # 5XXXXXXXX
        return '971' + s
    elif len(s) == 10 and s.startswith('05'):  # 05XXXXXXXX
        return '971' + s[1:]
    else:
        return s  # Return as-is for non-standard

def load_file(uploaded_file):
    """Load CSV or Excel into a DataFrame."""
    name = uploaded_file.name.lower()
    if name.endswith('.csv'):
        return pd.read_csv(uploaded_file, dtype=str)
    elif name.endswith(('.xlsx', '.xls')):
        return pd.read_excel(uploaded_file, dtype=str)
    else:
        raise ValueError("Unsupported file format")

def to_excel_bytes(df):
    """Convert DataFrame to Excel bytes for download."""
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, sheet_name='Leads', index=False)
        # Auto-format
        workbook = writer.book
        worksheet = writer.sheets['Leads']
        header_fmt = workbook.add_format({
            'bold': True, 'bg_color': '#1e3a8a', 'font_color': 'white',
            'border': 1, 'align': 'center'
        })
        for col_num, value in enumerate(df.columns.values):
            worksheet.write(0, col_num, value, header_fmt)
            worksheet.set_column(col_num, col_num, 18)
    return output.getvalue()

# ============================================
# SIDEBAR — INSTRUCTIONS
# ============================================
with st.sidebar:
    st.header("📖 How to Use")
    st.markdown("""
    1. **Upload** your Main Lead Sheet (Excel/CSV)
    2. **Upload** one or more DNCR result CSV files from the portal
    3. **Select** the phone column & status column
    4. Click **Process & Update**
    5. **Download** the updated lead sheet ✅
    
    ---
    ### 🔑 Features
    - Handles multiple DNCR batches at once
    - Auto-normalizes UAE numbers (971/0/+971)
    - Preserves all existing lead data
    - Adds DNCR_Status + Last_Checked_Date columns
    - Reports unmatched numbers
    """)

# ============================================
# STEP 1 — UPLOAD MAIN LEAD SHEET
# ============================================
st.subheader("📋 Step 1: Upload Main Lead Sheet")
main_file = st.file_uploader(
    "Upload your master lead sheet (.xlsx or .csv)",
    type=['xlsx', 'xls', 'csv'],
    key='main'
)

main_df = None
if main_file:
    try:
        main_df = load_file(main_file)
        st.success(f"✅ Loaded: **{main_file.name}** — {len(main_df):,} rows, {len(main_df.columns)} columns")
        with st.expander("👀 Preview Main Lead Sheet"):
            st.dataframe(main_df.head(10))
    except Exception as e:
        st.error(f"Error loading file: {e}")

# ============================================
# STEP 2 — UPLOAD DNCR RESULT FILES
# ============================================
st.subheader("📥 Step 2: Upload DNCR Result CSV File(s)")
dncr_files = st.file_uploader(
    "Upload one or more DNCR result files exported from the portal",
    type=['csv', 'xlsx'],
    accept_multiple_files=True,
    key='dncr'
)

dncr_dfs = []
if dncr_files:
    for f in dncr_files:
        try:
            df = load_file(f)
            dncr_dfs.append((f.name, df))
            st.success(f"✅ {f.name} — {len(df):,} rows")
        except Exception as e:
            st.error(f"Error in {f.name}: {e}")

# ============================================
# STEP 3 — CONFIGURE COLUMNS
# ============================================
if main_df is not None and dncr_dfs:
    st.subheader("⚙️ Step 3: Configure Columns")

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("**Main Lead Sheet**")
        main_phone_col = st.selectbox(
            "Phone Number Column",
            options=main_df.columns.tolist(),
            key='main_phone'
        )

    with col2:
        st.markdown("**DNCR Result Files**")
        sample_dncr = dncr_dfs[0][1]
        dncr_phone_col = st.selectbox(
            "Phone Number Column (in DNCR file)",
            options=sample_dncr.columns.tolist(),
            key='dncr_phone'
        )
        dncr_status_col = st.selectbox(
            "DNCR Status Column (Y/N)",
            options=sample_dncr.columns.tolist(),
            key='dncr_status'
        )

    output_col_name = st.text_input(
        "Name of the DNCR Status column to add/update in Main Sheet",
        value="DNCR_Status"
    )

    add_date = st.checkbox("Also add 'Last_Checked_Date' column", value=True)

    # ============================================
    # STEP 4 — PROCESS
    # ============================================
    st.subheader("🚀 Step 4: Process & Update")

    if st.button("▶ PROCESS & UPDATE LEAD SHEET", type="primary", use_container_width=True):
        with st.spinner("Processing... please wait..."):

            # Build lookup dictionary from ALL DNCR files
            lookup = {}
            duplicate_count = 0
            for fname, df in dncr_dfs:
                for _, row in df.iterrows():
                    norm = normalize_uae_number(row[dncr_phone_col])
                    if norm:
                        if norm in lookup and lookup[norm] != row[dncr_status_col]:
                            duplicate_count += 1
                        lookup[norm] = str(row[dncr_status_col]).strip().upper()

            # Apply lookup to main sheet
            updated_df = main_df.copy()
            updated_df['_normalized'] = updated_df[main_phone_col].apply(normalize_uae_number)
            updated_df[output_col_name] = updated_df['_normalized'].map(lookup)

            if add_date:
                today = datetime.now().strftime("%Y-%m-%d")
                updated_df['Last_Checked_Date'] = updated_df[output_col_name].apply(
                    lambda x: today if pd.notna(x) else ''
                )

            # Stats
            matched = updated_df[output_col_name].notna().sum()
            unmatched = len(updated_df) - matched
            y_count = (updated_df[output_col_name] == 'Y').sum()
            n_count = (updated_df[output_col_name] == 'N').sum()

            # Drop helper column
            updated_df = updated_df.drop(columns=['_normalized'])

            # Show results
            st.success("✅ Processing Complete!")

            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Total Leads", f"{len(updated_df):,}")
            m2.metric("✅ Matched", f"{matched:,}")
            m3.metric("⚠️ Unmatched", f"{unmatched:,}")
            m4.metric("DNCR Lookup Size", f"{len(lookup):,}")

            c1, c2 = st.columns(2)
            c1.metric("🟢 Y (On DNCR)", f"{y_count:,}")
            c2.metric("🔴 N (Not on DNCR)", f"{n_count:,}")

            if duplicate_count > 0:
                st.warning(f"⚠️ {duplicate_count} numbers had conflicting statuses across files (latest used).")

            # Preview
            with st.expander("👀 Preview Updated Lead Sheet"):
                st.dataframe(updated_df.head(20))

            # Unmatched numbers report
            if unmatched > 0:
                with st.expander(f"⚠️ View {unmatched} Unmatched Numbers"):
                    unmatched_df = updated_df[updated_df[output_col_name].isna()][[main_phone_col]]
                    st.dataframe(unmatched_df)

            # Download buttons
            st.subheader("⬇️ Download Updated Files")
            d1, d2 = st.columns(2)

            with d1:
                excel_bytes = to_excel_bytes(updated_df)
                st.download_button(
                    label="📥 Download Updated Lead Sheet (.xlsx)",
                    data=excel_bytes,
                    file_name=f"updated_leads_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True
                )

            with d2:
                csv_bytes = updated_df.to_csv(index=False).encode('utf-8')
                st.download_button(
                    label="📥 Download Updated Lead Sheet (.csv)",
                    data=csv_bytes,
                    file_name=f"updated_leads_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                    mime="text/csv",
                    use_container_width=True
                )

else:
    st.info("👆 Please upload both the Main Lead Sheet and at least one DNCR Result file to proceed.")

# ============================================
# FOOTER
# ============================================
st.markdown("---")
st.caption("DNCR Auto Updater v1.0 | Built with Streamlit 🚀")