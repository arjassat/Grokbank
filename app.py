import streamlit as st
import pandas as pd
from pdf2image import convert_from_bytes
from PIL import Image, ImageEnhance, ImageFilter
import pytesseract
import re
import io

st.set_page_config(page_title="Standard Bank OCR", layout="wide")
st.title("📄 Standard Bank Statement → Clean CSV")
st.caption("v8 - Better Page Coverage + Amount Accuracy")

uploaded_files = st.file_uploader("Upload PDF(s)", type="pdf", accept_multiple_files=True)
default_year = st.number_input("Default Year", min_value=2022, max_value=2026, value=2022)

def preprocess_image(image):
    gray = image.convert('L')
    enhanced = ImageEnhance.Contrast(gray).enhance(4.0)      # Stronger contrast
    enhanced = enhanced.filter(ImageFilter.MedianFilter(size=3))
    return enhanced

def get_year_from_text(text):
    match = re.search(r'20(\d{2})', text)
    return int('20' + match.group(1)) if match else default_year

def extract_transactions(text, default_year):
    transactions = []
    lines = [line.strip() for line in text.split('\n') if len(line.strip()) > 8]
    year = get_year_from_text(text)
    
    i = 0
    while i < len(lines):
        line = lines[i]
        
        # === DATE DETECTION (strict) ===
        date_match = re.search(r'(?:^|\s)(\d{2})\s*(\d{2})\b', line)
        current_date = None
        if date_match:
            dd, mm = date_match.groups()
            if 1 <= int(mm) <= 12 and 1 <= int(dd) <= 31:
                current_date = f"{dd}/{mm}/{year}"
        
        # === AMOUNT DETECTION - Improved ===
        amounts = re.findall(r'(\d{1,3}(?:,\d{3})*\.\d{2})', line)
        if not amounts:
            i += 1
            continue
        
        # Take the **second** amount if there are multiple (often txn amount, first might be fee)
        amt_str = amounts[0].replace(',', '') if len(amounts) == 1 else amounts[1].replace(',', '')
        try:
            amount = float(amt_str)
            if amount < 1.0:
                i += 1
                continue
        except:
            i += 1
            continue
        
        # Multi-line description
        desc = line
        if i + 1 < len(lines):
            next_line = lines[i + 1]
            if not re.search(r'\d{1,3}(?:,\d{3})*\.\d{2}', next_line) and len(next_line.strip()) > 8:
                desc = line + " " + next_line
                i += 1
        
        # Debit / Credit
        full_text = (desc + " " + line).upper()
        debit_kws = ['PURCHASE', 'FEE', 'WITHDRAWAL', 'PAYMENT TO', 'PRE-PAID', 'IMMEDIATE', 'MONTHLY ACCOUNT']
        credit_kws = ['DEPOSIT', 'CREDIT', 'TRANSFER FROM', 'MAGTAPE', 'REAL TIME']
        
        is_debit = any(k in full_text for k in debit_kws)
        if not is_debit and any(k in full_text for k in credit_kws):
            is_debit = False
        elif '-' in line[-50:]:
            is_debit = True
        
        if is_debit:
            amount = -amount
        
        clean_desc = re.sub(r'\d{1,3}(?:,\d{3})*\.\d{2}', '', desc)
        clean_desc = re.sub(r'\s+', ' ', clean_desc).strip()[:200]
        
        if current_date and len(clean_desc) > 10 and abs(amount) > 0.5:
            transactions.append({
                'date': current_date,
                'description': clean_desc,
                'amount': round(amount, 2)
            })
        
        i += 1
    return transactions

if uploaded_files:
    all_txns = []
    progress = st.progress(0)
    
    for idx, file in enumerate(uploaded_files):
        st.info(f"Processing: {file.name}")
        try:
            images = convert_from_bytes(file.read(), dpi=500)   # Higher DPI for skipped pages
            
            for page_num, img in enumerate(images):
                st.caption(f"Processing page {page_num+1} of {len(images)}")
                processed = preprocess_image(img)
                
                # Try two OCR modes per page for maximum coverage
                text1 = pytesseract.image_to_string(processed, config='--psm 6')
                text2 = pytesseract.image_to_string(processed, config='--psm 4')  # Alternative mode
                
                txns1 = extract_transactions(text1, default_year)
                txns2 = extract_transactions(text2, default_year)
                
                # Combine and deduplicate
                all_txns.extend(txns1)
                all_txns.extend(txns2)
                
        except Exception as e:
            st.error(f"Error on {file.name} page {page_num+1}: {e}")
        
        progress.progress((idx + 1) / len(uploaded_files))
    
    if all_txns:
        df = pd.DataFrame(all_txns)
        bad = ['BALANCE BROUGHT', 'TOTAL CHARGE', 'VAT', 'MONTH-END', 'BALANCE AT', 'PAGE', 'STATEMENT']
        df = df[~df['description'].str.contains('|'.join(bad), na=False, case=False)]
        
        df = df.drop_duplicates(subset=['date', 'description', 'amount']).sort_values('date').reset_index(drop=True)
        
        st.success(f"✅ Extracted **{len(df)}** transactions!")
        st.dataframe(df, use_container_width=True)
        
        csv = df.to_csv(index=False)
        st.download_button("📥 Download CSV", csv, "standard_bank_v8.csv", "text/csv")
        
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False)
        st.download_button("📥 Download Excel", output.getvalue(), "standard_bank_v8.xlsx", 
                          "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
