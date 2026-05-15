import streamlit as st
import pandas as pd
from pdf2image import convert_from_bytes
import pytesseract
from PIL import Image, ImageEnhance, ImageFilter
import re
import io

st.set_page_config(page_title="Standard Bank OCR", layout="wide")
st.title("📄 Standard Bank Statement to CSV")
st.caption("Scanned PDFs → Clean CSV for budget apps")

uploaded_files = st.file_uploader("Upload Standard Bank PDF statement(s)", type="pdf", accept_multiple_files=True)

def preprocess_image(image):
    """Improve OCR quality"""
    gray = image.convert('L')
    enhancer = ImageEnhance.Contrast(gray)
    enhanced = enhancer.enhance(2.0)
    enhanced = enhanced.filter(ImageFilter.MedianFilter())
    return enhanced

def parse_standard_bank_text(text):
    transactions = []
    lines = [line.strip() for line in text.split('\n') if line.strip()]
    
    current_date = None
    
    for line in lines:
        # Extract date (common formats in your statements)
        date_match = re.search(r'(\d{2})\s*(\d{2})\s*(?:20)?(\d{2})', line)
        if date_match:
            try:
                dd, mm, yy = date_match.groups()
                if len(yy) == 2:
                    yy = '20' + yy
                current_date = f"{dd}/{mm}/{yy}"
            except:
                pass
        
        # Look for transaction lines with amounts
        if re.search(r'\d{1,3}(?:,\d{3})*\.\d{2}', line):
            # Extract amount (last number in line)
            amounts = re.findall(r'([\d,]+\.\d{2})', line)
            if amounts:
                amt_str = amounts[-1].replace(',', '')
                try:
                    amt = float(amt_str)
                    
                    # Determine debit/credit
                    line_upper = line.upper()
                    if any(word in line_upper for word in ['PURCHASE', 'FEE', 'WITHDRAWAL', 'DEBIT', 'PAYMENT']):
                        amt = -amt
                    
                    # Description
                    desc = line[:120].strip()
                    
                    if current_date and abs(amt) > 0.01:
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
        st.info(f"Processing: {uploaded_file.name}")
        
        try:
            images = convert_from_bytes(uploaded_file.read(), dpi=300)
            
            for page_num, img in enumerate(images):
                processed_img = preprocess_image(img)
                text = pytesseract.image_to_string(processed_img, config='--psm 6')
                txns = parse_standard_bank_text(text)
                all_transactions.extend(txns)
                
        except Exception as e:
            st.error(f"Error processing {uploaded_file.name}: {str(e)}")
        
        progress_bar.progress((idx + 1) / len(uploaded_files))
    
    if all_transactions:
        df = pd.DataFrame(all_transactions)
        df = df.drop_duplicates().sort_values('date').reset_index(drop=True)
        
        st.success(f"✅ Extracted **{len(df)}** transactions successfully!")
        st.dataframe(df.head(30), use_container_width=True)
        
        # CSV Download
        csv = df.to_csv(index=False)
        st.download_button("📥 Download CSV", csv, "bank_transactions.csv", "text/csv")
        
        # Excel Download
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='Transactions')
        st.download_button("📥 Download Excel", output.getvalue(), "bank_transactions.xlsx", 
                          "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    else:
        st.warning("No transactions found. Try higher quality scans.")

st.markdown("---")
st.info("**Tips:** High-contrast scans work best. The app is tuned specifically for Standard Bank statements like the one you shared.")
