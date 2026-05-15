import streamlit as st
import pandas as pd
from pdf2image import convert_from_bytes
from PIL import Image, ImageEnhance, ImageFilter
import pytesseract
import re
import io

st.set_page_config(page_title="Standard Bank OCR", layout="wide")
st.title("📄 Standard Bank Statement → Clean CSV")
st.caption("v6 - STRICT Date Detection (Fixed 10/05 issue)")

uploaded_files = st.file_uploader("Upload PDF(s)", type="pdf", accept_multiple_files=True)
default_year = st.number_input("Default Year", min_value=2022, max_value=2026, value=2022)

def preprocess_image(image):
    gray = image.convert('L')
    enhanced = ImageEnhance.Contrast(gray).enhance(3.5)
    enhanced = enhanced.filter(ImageFilter.MedianFilter(size=3))
    return enhanced

def get_year_from_text(text):
    match = re.search(r'Statement from .*?20(\d{2})', text) or re.search(r'20(\d{2})', text)
    if match:
        return int('20' + match.group(1))
    return default_year

def extract_transactions(text, default_year):
    transactions = []
    lines = [line.strip() for line in text.split('\n') if len(line.strip()) > 15]
    
    current_date = None
    year = get_year_from_text(text) or default_year
    
    for line in lines:
        # === VERY STRICT DATE DETECTION ===
        # Only match DD MM when it's likely a transaction date:
        # - Near start of line OR after common transaction words
        date_match = re.search(r'(?:^|\b(?:05|06|07)\s*)(\d{2})\s*(\d{2})\b', line)  # Only May-June-July for now
        if not date_match:
            # Alternative: look for DD MM near amount
            date_match = re.search(r'(\d{2})\s*(\d{2})\s*(?=\s*\d{1,3}(?:,\d{3})*\.\d{2})', line)
        
        if date_match:
            dd, mm = date_match.groups()
            if 1 <= int(mm) <= 12 and 1 <= int(dd) <= 31:
                current_date = f"{dd}/{mm}/{year}"
        
        # Amount extraction
        amounts = re.findall(r'(\d{1,3}(?:,\d{3})*\.\d{2})', line)
        if not amounts:
            continue
        amt_str = amounts[0].replace(',', '')
        try:
            amount = float(amt_str)
            if amount < 1.0:
                continue
        except:
            continue
        
        # Debit/Credit
        line_upper = line.upper()
        debit_kws = ['PURCHASE', 'FEE', 'WITHDRAWAL', 'PAYMENT TO', 'PRE-PAID', 'IMMEDIATE', 'MONTHLY']
        credit_kws = ['DEPOSIT', 'CREDIT', 'TRANSFER FROM', 'MAGTAPE', 'REAL TIME']
        
        is_debit = any(k in line_upper for k in debit_kws)
        if not is_debit and any(k in line_upper for k in credit_kws):
            is_debit = False
        elif '-' in line[-40:]:
            is_debit = True
        
        if is_debit:
            amount = -amount
        
        # Clean desc
        desc = re.sub(r'\d{1,3}(?:,\d{3})*\.\d{2}', '', line)
        desc = re.sub(r'\s+', ' ', desc).strip()[:140]
        
        if current_date and len(desc) > 12 and abs(amount) > 0.5:
            transactions.append({
                'date': current_date,
                'description': desc,
                'amount': round(amount, 2)
            })
    
    return transactions

if uploaded_files:
    all_txns = []
    progress = st.progress(0)
    
    for i, file in enumerate(uploaded_files):
        st.info(f"Processing {file.name}...")
        try:
            images = convert_from_bytes(file.read(), dpi=450)
            for page_num, img in enumerate(images):
                processed = preprocess_image(img)
                text = pytesseract.image_to_string(processed, config='--psm 6')
                txns = extract_transactions(text, default_year)
                all_txns.extend(txns)
        except Exception as e:
            st.error(f"Error: {e}")
        progress.progress((i + 1) / len(uploaded_files))
    
    if all_txns:
        df = pd.DataFrame(all_txns)
        # Strong garbage filter
        bad = ['BALANCE BROUGHT', 'TOTAL CHARGE', 'VAT', 'MONTH-END', 'BALANCE AT', 'STATEMENT', 'PAGE']
        df = df[~df['description'].str.contains('|'.join(bad), na=False, case=False)]
        
        df = df.drop_duplicates(subset=['date','description','amount']).sort_values('date').reset_index(drop=True)
        
        st.success(f"✅ Extracted **{len(df)}** transactions!")
        st.dataframe(df, use_container_width=True)
        
        csv = df.to_csv(index=False)
        st.download_button("📥 Download CSV", csv, "standard_bank_v6.csv", "text/csv")
        
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False)
        st.download_button("📥 Download Excel", output.getvalue(), "standard_bank_v6.xlsx", 
                          "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
