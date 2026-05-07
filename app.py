import streamlit as st
import pandas as pd
from pdf2image import convert_from_bytes
import base64
import time
from datetime import datetime
import groq

st.set_page_config(page_title="Bank Statement AI Extractor", layout="wide")
st.title("🧾 Free Bank Statement to CSV Converter")
st.write("Supports **FNB, Standard Bank, Nedbank** scanned PDFs up to ~10MB. Powered by Groq Vision AI (free tier).")

# Groq API Key input (free)
if "groq_key" not in st.session_state:
    st.session_state.groq_key = ""

api_key = st.text_input("Enter your free Groq API Key", value=st.session_state.groq_key, type="password")
if api_key:
    st.session_state.groq_key = api_key

uploaded_files = st.file_uploader("Upload PDF Bank Statements (max 10MB each)", type="pdf", accept_multiple_files=True)

if uploaded_files and st.button("🚀 Process with AI"):
    if not api_key:
        st.error("Please enter your Groq API Key")
        st.stop()

    client = groq.Groq(api_key=api_key)
    all_transactions = []
    progress_bar = st.progress(0)
    status = st.empty()

    for idx, file in enumerate(uploaded_files):
        status.text(f"Processing {file.name}...")
        
        # Convert PDF to images
        pdf_bytes = file.getvalue()
        images = convert_from_bytes(pdf_bytes, dpi=250)
        
        for page_num, image in enumerate(images):
            status.text(f"Analyzing page {page_num+1} of {file.name} with AI...")
            
            # Convert image to base64
            import io
            buffered = io.BytesIO()
            image.save(buffered, format="JPEG")
            img_str = base64.b64encode(buffered.getvalue()).decode()

            prompt = """You are an expert bank statement parser for South African banks (FNB, Standard Bank, Nedbank).
Extract every transaction from this statement page.

Return ONLY CSV format with exactly these columns:
date,description,amount

Rules:
- date: YYYY-MM-DD format
- amount: Use negative sign for debits/charges (e.g. -125.50), positive for credits
- description: Clean merchant name or full description
- One transaction per line
- Ignore headers, footers, balances, and totals

Example:
2025-03-04,KEYMED PR3202291,821.20
2025-03-04,C M R GOLF CLU,-525.00"""

            try:
                completion = client.chat.completions.create(
                    model="llama-4-scout-17b-16e-instruct",  # or latest vision model on Groq
                    messages=[
                        {"role": "user", "content": [
                            {"type": "text", "text": prompt},
                            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img_str}"}}
                        ]}
                    ],
                    temperature=0.0,
                    max_tokens=2000
                )
                
                response_text = completion.choices[0].message.content
                
                # Parse response
                lines = [line.strip() for line in response_text.split('\n') if ',' in line and any(char.isdigit() for char in line)]
                for line in lines:
                    try:
                        parts = [p.strip() for p in line.split(',', 2)]
                        if len(parts) == 3:
                            date = parts[0]
                            desc = parts[1]
                            amount = float(parts[2].replace('R', '').replace(',', '').strip())
                            all_transactions.append({"date": date, "description": desc, "amount": amount})
                    except:
                        continue
            except Exception as e:
                st.warning(f"Error on page {page_num+1}: {str(e)}")
            
            time.sleep(1)  # Respect rate limits
        
        progress_bar.progress((idx + 1) / len(uploaded_files))

    if all_transactions:
        df = pd.DataFrame(all_transactions)
        df = df.drop_duplicates()
        try:
            df['date'] = pd.to_datetime(df['date'], errors='coerce')
            df = df.sort_values('date')
        except:
            pass

        csv_data = df.to_csv(index=False)
        
        st.success(f"✅ Successfully extracted {len(df)} transactions!")
        st.download_button(
            label="📥 Download CSV",
            data=csv_data,
            file_name=f"bank_transactions_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
            mime="text/csv"
        )
        st.dataframe(df, use_container_width=True)
    else:
        st.error("No transactions found. Try better quality scans or different model.")
