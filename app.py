import streamlit as st
import pandas as pd
from pdf2image import convert_from_bytes
import pytesseract
from PIL import Image
import re
from datetime import datetime
import io

st.set_page_config(page_title="Standard Bank Statement OCR", layout="wide")
st.title("📄 Standard Bank Statement to CSV Converter")
st.markdown("Upload your scanned Standard Bank PDF statements (2022-2026 format).")

uploaded_files = st.file_uploader("Upload PDF(s)", type="pdf", accept_multiple_files=True)

def parse_standard_bank_text(text):
    transactions = []
    lines = text.split('\n')
    
    date_pattern = r'(\d{2})\s*(\d{2})\s*(\d{4}|\d{2})'  # Handles various date formats in OCR
    amount_pattern = r'([\d,]+\.?\d*)-?'  # Amounts with possible minus
    
    current_date = None
    
    for line in lines:
        line = line.strip()
        if not line or len(line) < 5:
            continue
            
        # Look for date in DD MM or similar (common in statements)
        date_match = re.search(r'(\d{2})\s*(\d{2})\s*(?:20)?(\d{2})', line)
        if date_match:
            try:
                dd = date_match.group(1)
                mm = date_match.group(2)
                yy = date_match.group(3)
                if len(yy) == 2:
                    yy = '20' + yy
                current_date = f"{dd}/{mm}/{yy}"
            except:
                pass
        
        # Look for debit/credit lines with amounts
        if any(keyword in line.upper() for keyword in ['DEBIT CARD', 'CASH DEPOSIT', 'PAYMENT', 'PURCHASE', 'TRANSFER', 'WITHDRAWAL', 'FEE']):
            # Extract description and amount
            desc = line[:100]  # Truncate long desc
            # Find amounts
            amounts = re.findall(r'([\d,]+\.\d{2})-?', line)
            if amounts:
                amt_str = amounts[-1].replace(',', '')
                try:
                    amt = float(amt_str)
                    # Debit if - or typical debit keywords
                    if '-' in line or any(k in line.upper() for k in ['PURCHASE', 'FEE', 'WITHDRAWAL']):
                        amt = -amt
                    if current_date:
                        transactions.append({
                            'date': current_date,
                            'description': desc,
                            'amount': amt
                        })
                except:
                    pass
    
    return transactions

if uploaded_files:
    all_transactions = []
    
    progress_bar = st.progress(0)
    for idx, uploaded_file in enumerate(uploaded_files):
        st.info(f"Processing {uploaded_file.name}...")
        
        # Convert PDF to images
        images = convert_from_bytes(uploaded_file.read())
        
        for page_num, image in enumerate(images):
            # OCR
            text = pytesseract.image_to_string(image, config='--psm 6')
            
            # Parse
            txns = parse_standard_bank_text(text)
            all_transactions.extend(txns)
            
            progress_bar.progress((idx + 1) / len(uploaded_files))
    
    if all_transactions:
        df = pd.DataFrame(all_transactions)
        # Clean up duplicates / sort
        df = df.drop_duplicates().sort_values('date')
        
        st.success(f"Extracted {len(df)} transactions!")
        
        # Preview
        st.dataframe(df.head(20))
        
        # Download CSV
        csv = df.to_csv(index=False)
        st.download_button(
            label="📥 Download CSV",
            data=csv,
            file_name="bank_transactions.csv",
            mime="text/csv"
        )
        
        # Optional: Excel too
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False)
        st.download_button(
            label="📥 Download Excel",
            data=output.getvalue(),
            file_name="bank_transactions.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
    else:
        st.warning("No transactions found. Try improving scan quality or contact for parser tweaks.")

st.markdown("---")
st.info("**Tips for best results:**\n"
        "- Use clear, high-contrast scans.\n"
        "- One statement per PDF is ideal but multiple works.\n"
        "- The parser is tuned specifically for Standard Bank layout.")
