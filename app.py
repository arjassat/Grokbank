import streamlit as st
import pandas as pd
from pdf2image import convert_from_bytes
import base64
import time
from datetime import datetime
import io
import groq

st.set_page_config(page_title="SA Bank Statement AI", layout="wide")
st.title("🧾 Free South African Bank Statement to CSV")
st.caption("✅ Supports FNB • Standard Bank • Nedbank | Scanned PDFs up to ~10MB")

# API Key
api_key = st.text_input("🔑 Groq API Key (Get free at console.groq.com)", type="password", help="Free tier is sufficient for personal use")

uploaded_files = st.file_uploader("Upload your PDF bank statements", type="pdf", accept_multiple_files=True)

if uploaded_files and st.button("🚀 Process with AI Vision"):
    if not api_key:
        st.error("❌ Please enter your Groq API Key")
        st.stop()

    client = groq.Groq(api_key=api_key)
    all_transactions = []
    progress_bar = st.progress(0)
    status = st.empty()

    total_files = len(uploaded_files)

    for idx, file in enumerate(uploaded_files):
        status.text(f"📄 Processing file {idx+1}/{total_files}: {file.name}")
        pdf_bytes = file.getvalue()
        
        try:
            # Convert PDF to images (lower DPI = faster + less memory)
            images = convert_from_bytes(pdf_bytes, dpi=200)
        except Exception as e:
            st.error(f"Failed to process {file.name} — possibly password protected or corrupted.")
            continue

        for page_num, image in enumerate(images):
            status.text(f"🔍 AI Analyzing page {page_num+1} of {file.name}...")
            
            # Convert image to base64
            buffered = io.BytesIO()
            image.save(buffered, format="JPEG")
            img_str = base64.b64encode(buffered.getvalue()).decode()

            prompt = """You are an expert at reading South African bank statements (FNB, Standard Bank, Nedbank).
Extract **every single transaction** from this page.

Return **ONLY** lines in this exact CSV format:
date,description,amount

Strict Rules:
- date must be in YYYY-MM-DD format
- amount: use negative sign for debits/expenses (example: -525.00), positive for credits/deposits
- description: clean merchant name or meaningful description
- One transaction per line
- Do NOT include headers, balances, totals, or any other text"""

            try:
                completion = client.chat.completions.create(
                    model="meta-llama/llama-4-scout-17b-16e-instruct",
                    messages=[{
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img_str}"}}
                        ]
                    }],
                    temperature=0.0,
                    max_tokens=2000
                )
                
                response_text = completion.choices[0].message.content
                
                # Parse the response
                lines = [line.strip() for line in response_text.split('\n') if ',' in line and any(c.isdigit() for c in line)]
                for line in lines:
                    try:
                        parts = [p.strip() for p in line.split(',', 2)]
                        if len(parts) == 3:
                            date_str = parts[0]
                            desc = parts[1]
                            amount_str = parts[2].replace('R', '').replace(',', '').strip()
                            amount = float(amount_str)
                            all_transactions.append({
                                "date": date_str,
                                "description": desc,
                                "amount": amount
                            })
                    except:
                        continue
            except Exception as e:
                st.warning(f"AI error on page {page_num+1} of {file.name}: {str(e)[:80]}")
            
            time.sleep(1.0)  # Respect free tier rate limits

        progress_bar.progress((idx + 1) / total_files)

    # Final Results
    if all_transactions:
        df = pd.DataFrame(all_transactions)
        df = df.drop_duplicates(ignore_index=True)
        
        # Try to sort by date
        try:
            df['date'] = pd.to_datetime(df['date'], errors='coerce')
            df = df.sort_values('date').reset_index(drop=True)
        except:
            pass

        st.success(f"🎉 Successfully extracted **{len(df)} transactions** from {total_files} file(s)!")
        
        csv_data = df.to_csv(index=False)
        
        st.download_button(
            label="📥 Download CSV for Budgeting App",
            data=csv_data,
            file_name=f"bank_transactions_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
            mime="text/csv"
        )
        
        st.dataframe(df, use_container_width=True)
    else:
        st.error("No transactions were extracted. Try higher quality scans or contact me for prompt improvement.")

st.info("💡 **How to get Groq API Key**: Go to https://console.groq.com → Sign up → Create API Key (Free)")
