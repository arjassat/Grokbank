import streamlit as st
import pandas as pd
from pdf2image import convert_from_bytes
from PIL import Image, ImageEnhance, ImageFilter
import pytesseract
import re
import io
from datetime import datetime

st.set_page_config(page_title="Standard Bank OCR", layout="wide")
st.title("📄 Standard Bank Statement → Clean CSV")
st.caption("Improved parser for 2022-2026 statements")

uploaded_files = st.file_uploader("Upload PDF(s)", type="pdf", accept_multiple_files=True)

def preprocess_image(image):
    gray = image.convert('L')
    enhancer = ImageEnhance.Contrast(gray)
    enhanced = enhancer.enhance(2.5)
    enhanced = enhanced.filter(ImageFilter.MedianFilter(size=3))
    return enhanced

def extract_transactions_from_text(text):
    transactions = []
    lines = text.split('\n')
    
    current_date = None
    balance_pattern = re.compile(r'(\d{1,3}(?:,\d{3})*\.\d{2})')
    
    for line in lines:
        line = line.strip()
        if not line or len(line) < 10:
            continue
        
        # === DATE DETECTION (DD MM) ===
        date_match = re.search(r'(\d{2})\s*(\d{2})\s*(?:20)?(\d{2})', line)
        if date_match:
            dd, mm, yy = date_match.groups()
            if len(yy) == 2 and int(mm) <= 12 and int(dd) <= 31:
                current_date = f"{dd}/{mm}/20{yy}"
        
        # === AMOUNT DETECTION ===
        amounts = re.findall(r'(\d{1,3}(?:,\d{3})*\.\d{2})', line)
        if not amounts:
            continue
        
        # Take the last realistic amount (usually the transaction amount)
        amt_str = amounts[-1].replace(',', '')
        try:
            amount = float(amt_str)
            if amount < 1:  # skip tiny numbers that are fees sometimes misread
                continue
        except:
            continue
        
        # Determine if Debit or Credit
        line_upper = line.upper()
        is_debit = False
        
        debit_keywords = ['PURCHASE', 'FEE', 'WITHDRAWAL', 'PAYMENT TO', 'DEBIT CARD', 'PRE-PAID']
        credit_keywords = ['DEPOSIT', 'CREDIT', 'TRANSFER FROM', 'MAGTAPE', 'REAL TIME TRANSFER']
        
        if any(kw in line_upper for kw in debit_keywords):
            is_debit = True
        elif any(kw in line_upper for kw in credit_keywords):
            is_debit = False
        else:
            # fallback: look for "-" near the amount
            if '-' in line[-30:]:  
                is_debit = True
        
        if is_debit:
            amount = -amount
        
        # Clean description
        desc = re.sub(r'\s+', ' ', line[:150]).strip()
        desc = re.sub(r'(\d{1,3}(?:,\d{3})*\.\d{2})', '', desc).strip()  # remove amounts from desc
        
        if current_date and len(desc) > 5:
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
            images = convert_from_bytes(file.read(), dpi=350)  # higher DPI for better OCR
            
            for page in images:
                processed = preprocess_image(page)
                text = pytesseract.image_to_string(processed, config='--psm 6 -c tessedit_char_blacklist=|')
                txns = extract_transactions_from_text(text)
                all_txns.extend(txns)
                
        except Exception as e:
            st.error(f"Failed on {file.name}: {e}")
        
        progress.progress((i+1)/len(uploaded_files))
    
    if all_txns:
        df = pd.DataFrame(all_txns)
        df = df.drop_duplicates(subset=['date', 'description', 'amount']).sort_values('date')
        
        st.success(f"✅ Extracted **{len(df)}** transactions!")
        st.dataframe(df.head(50), use_container_width=True)
        
        csv = df.to_csv(index=False)
        st.download_button("📥 Download CSV", csv, "standard_bank_clean.csv", "text/csv")
        
        # Excel too
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False)
        st.download_button("📥 Download Excel", output.getvalue(), "standard_bank_clean.xlsx", 
                          "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    else:
        st.error("Nothing extracted. Please try a clearer scan.")

st.info("**New version** — stronger date detection, better debit/credit logic, cleaner descriptions.")
