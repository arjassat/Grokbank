import streamlit as st
import pandas as pd
from pdf2image import convert_from_bytes
from PIL import Image, ImageEnhance, ImageFilter
import pytesseract
import re
import io

st.set_page_config(page_title="Standard Bank OCR", layout="wide")
st.title("📄 Standard Bank Statement → Clean CSV")
st.caption("v4 - Better dates + more complete extraction")

uploaded_files = st.file_uploader("Upload PDF(s)", type="pdf", accept_multiple_files=True)

# Allow user to specify year if not detected
year_input = st.number_input("Statement Year (if not auto-detected)", min_value=2022, max_value=2026, value=2022)

def preprocess_image(image):
    gray = image.convert('L')
    enhanced = ImageEnhance.Contrast(gray).enhance(3.0)
    enhanced = enhanced.filter(ImageFilter.MedianFilter(size=3))
    return enhanced

def extract_year_from_header(text):
    """Try to detect year from statement header"""
    year_match = re.search(r'20(\d{2})', text)
    if year_match:
        return int('20' + year_match.group(1))
    return None

def extract_transactions(text, default_year):
    transactions = []
    lines = [line.strip() for line in text.split('\n') if len(line.strip()) > 10]
    
    current_date = None
    detected_year = extract_year_from_header(text) or default_year
    
    for line in lines:
        # Robust Date Detection: DD MM format
        date_match = re.search(r'(\d{2})\s*(\d{2})\b', line)
        if date_match:
            dd, mm = date_match.groups()
            if 1 <= int(mm) <= 12 and 1 <= int(dd) <= 31:
                current_date = f"{dd}/{mm}/{detected_year}"
        
        # Amount extraction - prioritize transaction amount
        amounts = re.findall(r'(\d{1,3}(?:,\d{3})*\.\d{2})', line)
        if not amounts:
            continue
        
        # Take first substantial amount (usually txn amount)
        amt_str = amounts[0].replace(',', '')
        try:
            amount = float(amt_str)
            if amount < 1.0:
                continue
        except:
            continue
        
        # Debit/Credit classification
        line_upper = line.upper()
        debit_keywords = ['PURCHASE', 'FEE', 'WITHDRAWAL', 'PAYMENT TO', 'PRE-PAID', 'IMMEDIATE', 'MONTHLY ACCOUNT']
        credit_keywords = ['DEPOSIT', 'CREDIT', 'TRANSFER FROM', 'MAGTAPE', 'REAL TIME']
        
        is_debit = any(k in line_upper for k in debit_keywords)
        if not is_debit and any(k in line_upper for k in credit_keywords):
            is_debit = False
        elif '-' in line[-50:]:
            is_debit = True
        
        if is_debit:
            amount = -amount
        
        # Clean description
        desc = re.sub(r'\d{1,3}(?:,\d{3})*\.\d{2}', '', line)
        desc = re.sub(r'\s+', ' ', desc).strip()[:150]
        
        if current_date and len(desc) > 8 and abs(amount) > 0.5:
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
        st.info(f"Processing: {file.name} (Year: {year_input})")
        try:
            images = convert_from_bytes(file.read(), dpi=400)
            
            for page_num, img in enumerate(images):
                st.caption(f"Page {page_num+1}/{len(images)}")
                processed = preprocess_image(img)
                text = pytesseract.image_to_string(processed, config='--psm 6')
                
                txns = extract_transactions(text, year_input)
                all_txns.extend(txns)
                
        except Exception as e:
            st.error(f"Error processing {file.name}: {e}")
        
        progress.progress((i + 1) / len(uploaded_files))
    
    if all_txns:
        df = pd.DataFrame(all_txns)
        # Filter garbage
        df = df[~df['description'].str.contains('BALANCE BROUGHT|Total charge|VAT|Month-end|Statement|Balance at date', na=False, case=False)]
        df = df.drop_duplicates().sort_values('date').reset_index(drop=True)
        
        st.success(f"✅ Extracted **{len(df)}** transactions!")
        st.dataframe(df.head(100), use_container_width=True)
        
        csv = df.to_csv(index=False)
        st.download_button("📥 Download CSV", csv, "standard_bank_final.csv", "text/csv")
        
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False)
        st.download_button("📥 Download Excel", output.getvalue(), "standard_bank_final.xlsx", 
                          "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    else:
        st.warning("No transactions found.")

st.info("**v4 Changes**: Year detection from header + manual override, higher contrast, better filtering.")
