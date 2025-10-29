import streamlit as st
import pandas as pd
import numpy as np
import os
from io import BytesIO
from datetime import datetime

st.set_page_config(page_title="ભાડા મેનેજર", layout="wide")

st.title("📒 ભાડા મેનેજર — Gujarati")

# Default filenames (expected to be placed in the same folder as app.py)
DEFAULT_CONTROL = "Control Panel.xlsx"
DEFAULT_LEDGER = "Copy of હિસાબ (1).xlsx"

st.sidebar.header("ફાઇલ સેટિંગ")
uploaded_control = st.sidebar.file_uploader("Control Panel અપલોડ કરો (.xlsx)", type=["xlsx"], key="u1")
uploaded_ledger = st.sidebar.file_uploader("Ledger Excel અપલોડ કરો (.xlsx)", type=["xlsx"], key="u2")
use_uploaded = st.sidebar.checkbox("Upload use as primary (temporary)", value=False)

# Decide which file paths to use
app_dir = os.path.dirname(__file__) if "__file__" in globals() else os.getcwd()
control_path = os.path.join(app_dir, DEFAULT_CONTROL)
ledger_path = os.path.join(app_dir, DEFAULT_LEDGER)

# If user uploaded and chose to use uploaded, save temp copies and use them
if use_uploaded and uploaded_control is not None:
    tmpc = os.path.join(app_dir, "uploaded_control.xlsx")
    with open(tmpc, "wb") as f:
        f.write(uploaded_control.getbuffer())
    control_path = tmpc

if use_uploaded and uploaded_ledger is not None:
    tmpl = os.path.join(app_dir, "uploaded_ledger.xlsx")
    with open(tmpl, "wb") as f:
        f.write(uploaded_ledger.getbuffer())
    ledger_path = tmpl

st.sidebar.markdown("---")
st.sidebar.write("Control:", control_path if os.path.exists(control_path) else "(Control file not found)")
st.sidebar.write("Ledger:", ledger_path if os.path.exists(ledger_path) else " (Ledger file not found)")
st.sidebar.markdown("---")

def load_sheets(path):
    if path is None or not os.path.exists(path):
        return {}
    try:
        xls = pd.ExcelFile(path, engine="openpyxl")
        sheets = {name: pd.read_excel(xls, sheet_name=name) for name in xls.sheet_names}
        return sheets
    except Exception as e:
        st.error("Excel લોડ કરવામાં ત્રુટી: " + str(e))
        return {}

def save_sheets(path, sheets_dict):
    # write multiple sheets to a single workbook
    try:
        with pd.ExcelWriter(path, engine="openpyxl") as writer:
            for name, df in sheets_dict.items():
                df.to_excel(writer, sheet_name=str(name)[:31], index=False)
        return True, None
    except Exception as e:
        return False, str(e)

# Load data
sheets = load_sheets(control_path)
ledger_sheets = load_sheets(ledger_path)
# Merge control into sheets if separate file provided
control_df = None
if os.path.exists(control_path):
    tmp = load_sheets(control_path)
    # If control file contains a sheet named like "Control Panel" or first sheet, use it
    if len(tmp)>0:
        first = list(tmp.keys())[0]
        control_df = tmp[first].copy()
if control_df is None:
    # try to find control inside ledger workbook
    for name, df in ledger_sheets.items():
        cols = [str(c).strip() for c in df.columns]
        if any("સામાન" in c or "ભાડું" in c or "મિનિમમ" in c for c in cols):
            control_df = df.copy()
            break

if control_df is None:
    control_df = pd.DataFrame(columns=["સામાનનું નામ","સાઈઝ","નંગ દીઠ ભાડું (₹)","મિનિમમ દિવસ","ભાડું ગણવાની રીત","નોંધ"])

# Detect customer sheets in ledger_sheets
expected_cols = {"જાવક નંગ","જમા નંગ","આઈટમ","જાવક તા.","જમા તા.","નંગ દીઠ ભાડું"}
customer_sheets = []
for name, df in ledger_sheets.items():
    cols = set([str(c).strip() for c in df.columns.tolist()])
    if len(cols & expected_cols) >= 3:
        customer_sheets.append(name)
# if none found, consider all sheets as customers
if len(customer_sheets)==0 and len(ledger_sheets)>0:
    customer_sheets = list(ledger_sheets.keys())

# Pages
page = st.sidebar.radio("પેજ પસંદ કરો", ["Dashboard","મુખ્ય હિસાબ","કંટ્રોલ પેનલ"])

# Utility functions for rules
def lookup_rule(item):
    if item is None or pd.isna(item): return None
    nm = str(item).strip().lower()
    for idx, row in control_df.iterrows():
        if str(row.get("સામાનનું નામ","")).strip().lower() == nm:
            return row.to_dict()
    # partial match
    for idx, row in control_df.iterrows():
        if nm in str(row.get("સામાનનું નામ","")).strip().lower():
            return row.to_dict()
    return None

def calculate_days_and_total(row):
    item = row.get("આઈટમ")
    size = row.get("સાઈઝ", 0)
    rule = lookup_rule(item)
    # determine days (per your control rules)
    if rule is None:
        days = row.get("દિવસ", 0) or 0
    else:
        method = str(rule.get("ભાડું ગણવાની રીત","")).strip().lower()
        try:
            sz = float(size) if size!="" and not pd.isna(size) else 0.0
        except:
            sz = 0.0
        try:
            fixed = float(rule.get("નંગ દીઠ ભાડું (₹)") or rule.get("નક્કી ભાડું (₹)") or 0)
        except:
            fixed = 0.0
        try:
            factor = float(rule.get("સાઈઝ પ્રમાણે ગુણાંક") or rule.get("નંગ દીઠ ભાડું (₹)") or 0)
        except:
            factor = 0.0
        try:
            min_days = int(rule.get("મિનિમમ દિવસ") or 0)
        except:
            min_days = 0
        if "નક્કી" in method:
            days = fixed
        else:
            days = sz * factor
        if min_days and days < min_days:
            days = min_days
    # compute total rent using your formula rules approx
    E = float(row.get("જાવક નંગ") or 0)
    H = float(row.get("જમા નંગ") or 0)
    rate = float(row.get("નંગ દીઠ ભાડું") or 0)
    J = float(days or 0)
    # date difference
    G = row.get("જમા તા.")
    F = row.get("જાવક તા.")
    if pd.isna(item) or str(item).strip()=="":
        total = "-"
    else:
        # replicate earlier logic
        if H==0 and E>0:
            total = E*rate*J
        elif E==H:
            total = E*rate*J
        else:
            db = None
            try:
                if pd.notna(G) and pd.notna(F):
                    db = (pd.to_datetime(G) - pd.to_datetime(F)).days + 1
            except:
                db = None
            threshold = 5 if str(item).strip().lower()=="સિકંજા" else 10
            if E>H:
                if db is None:
                    total = H*rate*J
                else:
                    if db < threshold:
                        total = H*rate*J
                    else:
                        total = E*rate*J
            else:
                total = E*rate*J
    return days, total

# Dashboard page
if page == "Dashboard":
    st.header("Dashboard - સારાંશ")
    st.write("ग्रાહક সংখ্যা:", len(customer_sheets))
    total_rent = 0.0
    total_baki = 0.0
    for name in customer_sheets:
        df = ledger_sheets.get(name, pd.DataFrame()).copy()
        if "કુલ રકમ" in df.columns:
            vals = pd.to_numeric(df["કુલ રકમ"], errors='coerce')
            total_rent += vals.sum(skipna=True)
    st.metric("કુલ ભાડું", f"{total_rent:.2f}")
    st.info("Control Panel માં ફેરફાર કરવા 'કંટ્રોલ પેનલ' પેજ પર જાઓ.")

# Main ledger page
elif page == "મુખ્ય હિસાબ":
    st.header("મુખ્ય હિસાબ (Customer Ledger)")
    if len(customer_sheets)==0:
        st.info("Ledger workbook માં કોઈ customer sheet મળી નથી. કૃપા કરીને Excel ચેક કરો.")
    else:
        customer = st.selectbox("ગ્રાહક પસંદ કરો", options=customer_sheets)
        df = ledger_sheets.get(customer, pd.DataFrame()).copy()
        # ensure expected cols exist
        expected = ["ક્રમ","એક દિવસ","આઈટમ","સાઈઝ","જાવક નંગ","જાવક તા.","જમા તા.","જમા નંગ","નંગ દીઠ ભાડું","દિવસ","કુલ રકમ","જમા તા(જમા રકમ માટે)","જમા રકમ","તા Xથી બાકી"]
        for c in expected:
            if c not in df.columns:
                df[c] = ""

        # numeric conversions
        for c in ["જાવક નંગ","જમા નંગ","નંગ દીઠ ભરુ","નંગ દીઠ ભાડું","સાઈઝ"]:
            if c in df.columns:
                df[c] = pd.to_numeric(df[c], errors='coerce').fillna(0)
        for c in ["જાવક તા.","જਮਾ તા.","જમા તા(જમા રકમ માટે)"]:
            if c in df.columns:
                df[c] = pd.to_datetime(df[c], dayfirst=True, errors='coerce')

        # compute days and totals
        days_list = []
        totals = []
        for idx, row in df.iterrows():
            d, t = calculate_days_and_total(row)
            days_list.append(d)
            totals.append(t)
        df["દિવસ"] = days_list
        df["કુલ રકમ"] = totals

        # insert baki rows
        out_rows = []
        for idx, row in df.iterrows():
            out_rows.append(row.to_dict())
            E = float(row.get("જાવક નંગ") or 0)
            H = float(row.get("જમા નંગ") or 0)
            if E > H:
                remaining = E - H
                new_row = {c: "" for c in df.columns}
                new_row["ક્રમ"] = "બાકી"
                new_row["આઈટમ"] = row.get("આઈટમ")
                new_row["સાઈઝ"] = row.get("સાઈઝ")
                new_row["જાવક નંગ"] = remaining
                new_row["જાવક તા."] = row.get("જાવક તા.")
                new_row["જમા નંગ"] = 0
                new_row["નંગ દીઠ ભાડું"] = row.get("નંગ દીઠ ભાડું")
                new_row["એક દિવસ"] = row.get("એક દિવસ")
                new_row["દિવસ"] = row.get("દિવસ")
                G = row.get("જમા તા.")
                if pd.notna(G):
                    try:
                        new_row["તા Xથી બાકી"] = (pd.to_datetime(G) + pd.Timedelta(days=1)).date()
                    except:
                        new_row["તા Xથી બાકી"] = ""
                else:
                    new_row["તા Xથી બાકી"] = ""
                out_rows.append(new_row)
        result_df = pd.DataFrame(out_rows, columns=df.columns.tolist())

        edited = st.data_editor(result_df, use_container_width=True, num_rows="dynamic")

        # Save edited sheet back to excel
        if st.button("💾 Save changes to Excel"):
            # update in-memory ledger_sheets and write back
            ledger_sheets[customer] = edited.copy()
            # merge control_df into a dict to save as separate file if needed; we'll write ledger workbook
            ok, err = save_sheets(ledger_path, ledger_sheets)
            if ok:
                st.success("Excel ફાઇલમાં ફેરફારો સાચવ્યાં.")
            else:
                st.error("સેવ કરવામાં ત્રુટી: " + str(err))

        # Download updated customer excel
        if st.button("⬇️ Download this customer as Excel"):
            buf = BytesIO()
            with pd.ExcelWriter(buf, engine="openpyxl") as writer:
                edited.to_excel(writer, sheet_name=customer, index=False)
                control_df.to_excel(writer, sheet_name="Control Panel", index=False)
            buf.seek(0)
            st.download_button("Download .xlsx", data=buf.getvalue(), file_name=f"{customer}_updated.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

# Control Panel page
elif page == "કંટ્રોલ પેનલ":
    st.header("કંટ્રોલ પેનલ")
    st.write("અહીંથી ભાડાના નિયમો બદલો — પછી Save કરો.")
    control_edit = st.data_editor(control_df, use_container_width=True, num_rows="dynamic")
    if st.button("💾 Save Control Panel to file"):
        # save control to separate control workbook if desired
        ok, err = save_sheets(control_path, {"Control Panel": control_edit})
        if ok:
            st.success("Control Panel સાચવાયું.")
        else:
            st.error("સેવ થઈ ન શક્યું: " + str(err))
    if st.button("🔁 Apply rules (recalculate)"):
        st.rerun()

st.caption("Notes: Save changes to persist in Excel. Mobile users can open this URL in Chrome and use 'Add to Home screen' to pin the app.")