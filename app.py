import streamlit as st
import pandas as pd
from pdf2image import convert_from_bytes
from PIL import Image, ImageEnhance, ImageFilter
import pytesseract
import re
import io

st.set_page_config(page_title="Standard Bank OCR", layout="wide")
st.title("📄 Standard Bank Statement → Clean CSV")
st.caption("v3 - Tuned specifically for your 2022-2026 statements")

uploaded_files = st.file_uploader("Upload PDF(s)", type="pdf", accept_multiple_files=True)

def preprocess_image(image):
    gray = image.convert('L')
    enhanced = ImageEnhance.Contrast(gray).enhance(2.8)
    enhanced = enhanced.filter(ImageFilter.MedianFilter(size=3))
    return enhanced

def extract_transactions(text):
    transactions = []
    lines = [line.strip() for line in text.split('\n') if len(line.strip()) > 15]
    
    current_date = None
    
    for line in lines:
        # === DATE EXTRACTION (very robust) ===
        date_match = re.search(r'(\d{2})\s*(\d{2})(?=\s|$)', line)
        if date_match:
            dd, mm = date_match.groups()
            if 1 <= int(mm) <= 12 and 1 <= int(dd) <= 31:
                current_date = f"{dd}/{mm}/2022"  # You can adjust year per statement if needed
        
        # === AMOUNT EXTRACTION ===
        amounts = re.findall(r'(\d{1,3}(?:,\d{3})*\.\d{2})', line)
        if not amounts:
            continue
            
        # Use the transaction amount (usually before balance)
        amt_str = amounts[0].replace(',', '')   # First amount is usually the txn amount
        try:
            amount = float(amt_str)
            if amount < 0.5:
                continue
        except:
            continue
        
        # Debit / Credit logic
        line_upper = line.upper()
        is_debit = any(kw in line_upper for kw in [
            'PURCHASE', 'FEE', 'WITHDRAWAL', 'PAYMENT TO', 'PRE-PAID', 
            'IMMEDIATE PAYMENT', 'MONTHLY ACCOUNT FEE'
        ])
        
        if not is_debit and any(kw in line_upper for kw in [
            'DEPOSIT', 'CREDIT', 'TRANSFER FROM', 'MAGTAPE', 'REAL TIME'
        ]):
            is_debit = False
        elif '-' in line[-40:]:   # fallback
            is_debit = True
        
        if is_debit:
            amount = -amount
        
        # Clean description
        desc = re.sub(r'\d{1,3}(?:,\d{3})*\.\d{2}', '', line)   # remove amounts
        desc = re.sub(r'\s+', ' ', desc).strip()[:120]
        
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
        st.info(f"Processing: {file.name}")
        try:
            images = convert_from_bytes(file.read(), dpi=400)
            
            for img in images:
                processed = preprocess_image(img)
                text = pytesseract.image_to_string(processed, config='--psm 6')
                txns = extract_transactions(text)
                all_txns.extend(txns)
                
        except Exception as e:
            st.error(f"Error on {file.name}: {str(e)}")
        
        progress.progress((i + 1) / len(uploaded_files))
    
    if all_txns:
        df = pd.DataFrame(all_txns)
        # Remove obvious garbage
        df = df[~df['description'].str.contains('BALANCE BROUGHT|Total charge|VAT|Month-end|Statement', na=False)]
        df = df.drop_duplicates().sort_values('date').reset_index(drop=True)
        
        st.success(f"✅ Extracted **{len(df)}** transactions!")
        st.dataframe(df, use_container_width=True)
        
        csv = df.to_csv(index=False)
        st.download_button("📥 Download Final CSV", csv, "standard_bank_clean_v3.csv", "text/csv")
        
        # Excel
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False)
        st.download_button("📥 Download Excel", output.getvalue(), "standard_bank_clean_v3.xlsx", 
                          "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    else:
        st.warning("No transactions found. Upload a clearer PDF.")

st.info("**v3 Improvements**: Better date detection, first-amount logic, stronger cleaning, higher DPI.")
