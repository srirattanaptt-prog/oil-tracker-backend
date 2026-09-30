import yfinance as yf
import pandas as pd
import json
from datetime import datetime
import pytz

# 1. ใส่ลิงก์ CSV จาก Google Sheets ของคุณที่นี่
SHEET_CSV_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vQ3rStQJbI2nzZ83S4dS2Zl5GVM1ZMlu96XN4h7TVncFCNsB0AODIPfd3aiIV300sMCJPKeqkb_xfpJ/pub?gid=0&single=true&output=csv"

def get_margins_from_sheet():
    try:
        df = pd.read_csv(SHEET_CSV_URL)
        latest = df.iloc[-1] # ดึงแถวล่าสุด
        return float(latest['Diesel_Margin']), float(latest['G95_Margin'])
    except Exception as e:
        print(f"Sheet Error: {e}")
        return 2.0000, 3.3500 # ค่า Default สำรอง

def fetch_market_data():
    bkk_tz = pytz.timezone('Asia/Bangkok')
    now = datetime.now(bkk_tz)
    
    # 2. ดึงค่าอัตราแลกเปลี่ยนปัจจุบัน
    try:
        usd_sgd = yf.Ticker("SGD=X").history(period="1d")['Close'].iloc[-1]
        sgd_thb = yf.Ticker("SGDTHB=X").history(period="1d")['Close'].iloc[-1]
    except:
        usd_sgd, sgd_thb = 1.32, 26.1346
        
    # 3. ดึง Futures อเมริกา และกรองเวลา Platts Window (15:30 ไทย = 08:00 UTC)
    mops_diesel, mops_g95 = 0.00, 0.00
    try:
        data = yf.download(["HO=F", "RB=F"], period="5d", interval="1h", progress=False)
        df_close = data['Close'].copy()
        df_close.index = df_close.index.tz_convert('Asia/Bangkok')
        
        # กรองแท่ง 15:00 น.
        df_1500 = df_close[df_close.index.hour == 15]
        
        if len(df_1500) >= 2:
            prev = df_1500.iloc[-2]
            # ใช้ราคาล่าสุดเทียบกับ 15:30 เมื่อวาน (Intraday)
            curr = df_close.iloc[-1] 
            
            diff_ho = curr['HO=F'] - prev['HO=F']
            diff_rb = curr['RB=F'] - prev['RB=F']
            
            mops_diesel = diff_ho * 42 * usd_sgd
            mops_g95 = diff_rb * 42 * usd_sgd
    except Exception as e:
        print(f"Futures Error: {e}")

    return sgd_thb, mops_diesel, mops_g95, now.strftime('%Y-%m-%d %H:%M:%S')

def main():
    diesel_margin, g95_margin = get_margins_from_sheet()
    thb_rate, mops_diesel, mops_g95, timestamp = fetch_market_data()

    # 4. สร้างโครงสร้าง JSON ให้ตรงกับที่ HTML ต้องการ
    data = {
        "timestamp": timestamp,
        "thbSgdRate": round(thb_rate, 4),
        "dFx": 0.0000, # คงไว้ที่ 0 หรือใส่ logic เพิ่มตามต้องการ
        "dieselMopsDiff": round(mops_diesel, 2),
        "g95MopsDiff": round(mops_g95, 2),
        "eppoDieselMargin": diesel_margin,
        "eppoG95Margin": g95_margin
    }

    # 5. เขียนลงไฟล์
    with open('data.json', 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print("บันทึก data.json สำเร็จ")

if __name__ == "__main__":
    main()
