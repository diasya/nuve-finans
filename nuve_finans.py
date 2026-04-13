import streamlit as st
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import requests
import urllib3
import yfinance as yf
import time
from datetime import datetime, timedelta

# --- SSL SUSTURMA ---
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# --- SAYFA AYARLARI ---
st.set_page_config(page_title="Nüve Uzay Finans", page_icon="🚀", layout="wide")

# --- CSS (Makyaj) ---
st.markdown("""
<style>
    .metric-card {background-color: #0e1117; padding: 15px; border-radius: 10px; border: 1px solid #30333F;}
    h1 {color: #FF4B4B;}
    .basket-header { color: #4facfe; font-weight: bold; font-size: 1.5em; margin-top: 20px; border-bottom: 1px solid #333; padding-bottom: 5px; }
    .stPlotlyChart {text-align: center;}
</style>
""", unsafe_allow_html=True)

# ==========================================
# 1. VERİ MOTORLARI
# ==========================================
@st.cache_data(ttl=3600)
def fetch_chunk(fon_kodu, start_date, end_date):
    s_str = start_date.strftime("%d.%m.%Y")
    e_str = end_date.strftime("%d.%m.%Y")
    url = "https://www.tefas.gov.tr/api/DB/BindHistoryInfo"
    payload = {"fontip": "YAT", "fonkod": fon_kodu, "bastarih": s_str, "bittarih": e_str, "strperiod": "1,1,1,1,1,1,1"}
    headers = {
        "Origin": "https://www.tefas.gov.tr",
        "Referer": "https://www.tefas.gov.tr",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "X-Requested-With": "XMLHttpRequest"
    }
    
    for attempt in range(3):
        try:
            response = requests.post(url, data=payload, headers=headers, timeout=15, verify=False)
            data = response.json().get('data', [])
            if data: return data
            else: time.sleep(0.5)
        except:
            time.sleep(1)
            
    return []

@st.cache_data(ttl=3600)
def get_tefas_history(fon_kodu, start_date, end_date):
    all_data = []
    current_start = start_date
    while current_start < end_date:
        current_end = min(current_start + timedelta(days=80), end_date)
        chunk = fetch_chunk(fon_kodu, current_start, current_end)
        if chunk: all_data.extend(chunk)
        current_start = current_end + timedelta(days=1)
        time.sleep(0.1)
    
    if not all_data: return None
    df = pd.DataFrame(all_data)
    df = df.drop_duplicates(subset=['TARIH'])
    try: df['Date'] = pd.to_datetime(df['TARIH'], unit='ms')
    except: df['Date'] = pd.to_datetime(df['TARIH'])
    df.set_index('Date', inplace=True)
    df.sort_index(inplace=True)
    df['FIYAT'] = df['FIYAT'].astype(float)
    return df[['FIYAT']]

@st.cache_data(ttl=3600)
def get_market_data(symbol, start_date, end_date):
    try:
        df = yf.download(symbol, start=start_date, end=end_date + timedelta(days=5), progress=False, auto_adjust=True)
        if df.empty: return None
        if isinstance(df.columns, pd.MultiIndex):
            try: df = df.xs('Close', level=0, axis=1)
            except: df = df.iloc[:, 0].to_frame()
        else:
            if 'Close' in df.columns: df = df[['Close']]
            else: df = df.iloc[:, 0].to_frame()
        df.columns = ['FIYAT']
        df.index = df.index.tz_localize(None)
        df.dropna(inplace=True)
        return df
    except: return None

# ==========================================
# 2. SIDEBAR
# ==========================================
with st.sidebar:
    st.title("⚙️ Kontrol Paneli")
    date_start = st.date_input("Başlangıç", datetime.now() - timedelta(days=365))
    date_end = st.date_input("Bitiş", datetime.now())
    st.markdown("---")
    money = st.number_input("Ana Para (Her Sepet İçin)", value=4000000, step=100000)
    expense = st.number_input("Aylık Gider (TL)", value=140000, step=10000)
    st.markdown("---")
    
    sepet_input = st.text_area("Sepetler", 
"""B | KCV:25, KLU:75
A | KPC:25, KLU:75""")
    
    show_usd = st.checkbox("Dolar (Ref)", value=True)
    show_gold = st.checkbox("Altın (Ref)", value=True)
    show_details = st.checkbox("Sepet İçeriklerini (Fonları) Göster", value=True)
    
    btn_run = st.button("🚀 ANALİZİ BAŞLAT", type="primary", use_container_width=True)

# ==========================================
# 3. ANA EKRAN VE ANALİZ
# ==========================================
st.title("🚀 Nüve Uzay | Varlık Yönetimi")

if btn_run:
    baskets = {}
    unique_assets = set()
    
    lines = sepet_input.strip().split('\n')
    for line in lines:
        if "|" not in line: continue
        name, content = line.split('|', 1)
        assets = {}
        for item in content.split(','):
            if ":" not in item: continue
            code, val = item.split(':', 1)
            code = code.strip().upper()
            try:
                assets[code] = float(val.strip().replace('%', ''))
                unique_assets.add(code)
            except: pass
        if assets: baskets[name.strip()] = assets

    if not baskets:
        st.error("❌ Geçerli sepet bulunamadı.")
        st.stop()

    t1, t2 = pd.to_datetime(date_start), pd.to_datetime(date_end)
    df_pool = pd.DataFrame()
    
    status_col = st.expander("📥 Veri Çekme Durumu", expanded=False)
    
    with st.spinner('Veriler toplanıyor...'):
        fetch_assets = list(unique_assets)
        if show_usd: fetch_assets.append('USD')
        if show_gold: fetch_assets.append('ALTIN')

        for kod in fetch_assets:
            df_raw = None
            if kod == 'USD': df_raw = get_market_data("TRY=X", t1, t2)
            elif kod == 'ALTIN':
                d1 = get_market_data("GC=F", t1, t2)
                d2 = get_market_data("TRY=X", t1, t2)
                if d1 is not None and d2 is not None:
                    c = d1.index.intersection(d2.index)
                    gram = (d1.loc[c]['FIYAT'] * d2.loc[c]['FIYAT']) / 31.1035
                    df_raw = pd.DataFrame(gram, columns=['FIYAT'])
            else: df_raw = get_tefas_history(kod, t1, t2)
            
            if df_raw is not None and not df_raw.empty:
                df_raw.columns = [kod]
                if df_pool.empty: df_pool = df_raw
                else: df_pool = df_pool.join(df_raw, how='outer')
                status_col.write(f"✅ {kod} yüklendi.")
            else:
                status_col.error(f"❌ {kod} verisi alınamadı!")

        # --- KRİTİK DÜZELTME (PANDAS v2+) ---
        df_pool = df_pool.ffill().bfill()
        df_pool = df_pool.loc[t1:t2]

    if df_pool.empty:
        st.error("❌ Veri havuzu boş. Lütfen tarihleri veya fon kodlarını kontrol edin.")
        st.stop()

    # Sepet Hesaplamaları
    df_baskets = pd.DataFrame(index=df_pool.index)
    for b_name, assets in baskets.items():
        daily_vals = pd.Series(0.0, index=df_pool.index)
        for kod, oran in assets.items():
            if kod in df_pool.columns:
                start_price = df_pool[kod].iloc[0]
                lot = (money * (oran/100)) / start_price
                daily_vals += df_pool[kod] * lot
        df_baskets[b_name] = daily_vals

    if show_usd and 'USD' in df_pool.columns:
        df_baskets['DOLAR (Ref)'] = (df_pool['USD'] / df_pool['USD'].iloc[0]) * money
    if show_gold and 'ALTIN' in df_pool.columns:
        df_baskets['ALTIN (Ref)'] = (df_pool['ALTIN'] / df_pool['ALTIN'].iloc[0]) * money

    # --- GÖRSELLEŞTİRME ---
    st.header("🏁 Performans Getiri (%)")
    df_norm = ((df_baskets / money) - 1) * 100
    st.line_chart(df_norm)

    # --- RAPORLAMA ---
    st.header("📊 Finansal Rapor")
    cols = st.columns(len(baskets))
    for i, (b_name, b_val) in enumerate(df_baskets.items()):
        if "(Ref)" in b_name: continue
        son_deger = b_val.iloc[-1]
        toplam_kar = son_deger - money
        aylik_getiri_oran = b_val.pct_change().mean() * 21
        aylik_nakit = son_deger * aylik_getiri_oran * 0.825 # Stopaj sonrası
        
        with st.container():
            st.markdown(f"### {b_name}")
            c1, c2, c3 = st.columns(3)
            c1.metric("Net Varlık", f"{son_deger:,.0f} ₺")
            c2.metric("Aylık Net Gelir", f"{aylik_nakit:,.0f} ₺")
            net_akis = aylik_nakit - expense
            c3.metric("Net Akış", f"{net_akis:,.0f} ₺", delta=f"{net_akis:,.0f}", delta_color="normal" if net_akis > 0 else "inverse")
            st.divider()
