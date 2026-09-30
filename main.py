import yfinance as yf
import pandas as pd
import json
from datetime import datetime, timedelta
import pytz
import os
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# ชื่อไฟล์ Google Sheets ของคุณ
SHEET_NAME = "OilTracker_DB"

def get_google_sheet_client():
    # โหลด Credentials จาก GitHub Secrets
    creds_json = os.environ.get('GCP_CREDENTIALS')
    if not creds_json:
        raise ValueError("ไม่พบ GCP_CREDENTIALS ใน Environment")
    
    creds_dict = json.loads(creds_json)
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    client = gspread.authorize(creds)
    return client

def fetch_market_data():
    bkk_tz = pytz.timezone('Asia/Bangkok')
    now = datetime.now(bkk_tz)
    
    try:
        usd_sgd = yf.Ticker("SGD=X").history(period="1d")['Close'].iloc[-1]
        sgd_thb = yf.Ticker("SGDTHB=X").history(period="1d")['Close'].iloc[-1]
    except:
        usd_sgd, sgd_thb = 1.32, 26.1346
        
    mops_diesel, mops_g95 = 0.00, 0.00
    try:
        data = yf.download(["HO=F", "RB=F"], period="5d", interval="1h", progress=False)
        df_close = data['Close'].copy()
        df_close.index = df_close.index.tz_convert('Asia/Bangkok')
        df_1500 = df_close[df_close.index.hour == 15]
        
        if len(df_1500) >= 2:
            prev = df_1500.iloc[-2]
            curr = df_close.iloc[-1] 
            diff_ho = curr['HO=F'] - prev['HO=F']
            diff_rb = curr['RB=F'] - prev['RB=F']
            mops_diesel = diff_ho * 42 * usd_sgd
            mops_g95 = diff_rb * 42 * usd_sgd
    except Exception as e:
        print(f"Futures Error: {e}")

    return sgd_thb, usd_sgd, mops_diesel, mops_g95, now

def update_sheets_and_generate_json():
    print("กำลังเชื่อมต่อ Google Sheets...")
    client = get_google_sheet_client()
    sheet_file = client.open(SHEET_NAME)
    
    # 1. อ่าน Config
    config_sheet = sheet_file.worksheet("Config")
    config_records = config_sheet.get_all_records()
    if config_records:
        latest_config = config_records[-1] # เอาแถวล่าสุด
        diesel_margin = float(latest_config.get('Diesel_Margin', 2.0000))
        g95_margin = float(latest_config.get('G95_Margin', 3.3500))
    else:
        diesel_margin, g95_margin = 2.0000, 3.3500

    # 2. ดึงข้อมูลตลาด
    print("กำลังดึงข้อมูลตลาด...")
    sgd_thb, usd_sgd, mops_diesel, mops_g95, now = fetch_market_data()
    timestamp_str = now.strftime('%Y-%m-%d %H:%M:%S')

    # 3. อัปเดต Market_Log (Rolling 7 วัน)
    print("กำลังอัปเดต Market_Log...")
    log_sheet = sheet_file.worksheet("Market_Log")
    
    # ดึงข้อมูลเก่ามาทั้งหมด
    all_logs = log_sheet.get_all_values()
    headers = all_logs[0] if all_logs else ["Timestamp", "SGD_THB", "USD_SGD", "MOPS_Diesel_Proxy", "MOPS_G95_Proxy"]
    
    # แปลงแถวเก่าเป็น Dataframe เพื่อกรองวันที่
    rows = all_logs[1:]
    new_row = [timestamp_str, round(sgd_thb, 4), round(usd_sgd, 4), round(mops_diesel, 2), round(mops_g95, 2)]
    
    valid_rows = []
    cutoff_date = now - timedelta(days=7) # ตัดที่ 7 วันที่แล้ว
    
    for row in rows:
        if not row or not row[0]: continue
        try:
            row_date = datetime.strptime(row[0], '%Y-%m-%d %H:%M:%S')
            row_date = pytz.timezone('Asia/Bangkok').localize(row_date)
            if row_date >= cutoff_date:
                valid_rows.append(row)
        except:
            pass # ข้ามแถวที่วันที่พัง
            
    # เอาแถวใหม่ต่อท้าย
    valid_rows.append(new_row)
    
    # ลบข้อมูลเก่าทิ้งหมด แล้วเขียนใหม่เฉพาะที่อยู่ในช่วง 7 วัน
    log_sheet.clear()
    log_sheet.update(range_name='A1', values=[headers] + valid_rows)

    # 4. สร้างไฟล์ data.json เพื่อให้ HTML ไปใช้งาน
    print("กำลังสร้าง data.json...")
    data = {
        "timestamp": timestamp_str,
        "thbSgdRate": round(sgd_thb, 4),
        "dFx": 0.0000,
        "dieselMopsDiff": round(mops_diesel, 2),
        "g95MopsDiff": round(mops_g95, 2),
        "eppoDieselMargin": diesel_margin,
        "eppoG95Margin": g95_margin
    }

    with open('data.json', 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print("สำเร็จ!")

if __name__ == "__main__":
    update_sheets_and_generate_json()
