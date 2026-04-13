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
        if chunk:
            all_data.extend(chunk)
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
    
    st.info("💡 **Sepet Formatı:** `İsim | KOD:%, KOD:%`")
    sepet_input = st.text_area("Sepetler", 
"""B | KCV:25, KLU:25, KUT:50
A | KPC:25, KLU:25, KUT:50
C | KPC:10, KLU:30, KUT:50, KTJ:10""")
    
    show_usd = st.checkbox("Dolar (Ref)", value=True)
    show_gold = st.checkbox("Altın (Ref)", value=True)
    show_details = st.checkbox("Sepet İçeriklerini (Fonları) Göster", value=True)
    
    btn_run = st.button("🚀 ANALİZİ BAŞLAT", type="primary", use_container_width=True)

# ==========================================
# 3. ANA EKRAN
# ==========================================
st.title("🚀 Nüve Uzay | Varlık Yönetimi")

if btn_run:
    baskets = {}
    unique_assets = set()
    
    lines = sepet_input.strip().split('\n')
    for line in lines:
        line = line.strip()
        if not line: continue
        try:
            if "|" not in line: continue
            parts = line.split('|', 1) 
            name = parts[0].strip()
            content = parts[1].strip()
            assets = {}
            items = content.split(',')
            for item in items:
                item = item.strip()
                if not item or ":" not in item: continue
                k_parts = item.split(':', 1)
                code = k_parts[0].strip().upper()
                val_str = k_parts[1].strip().replace('%', '')
                try:
                    assets[code] = float(val_str)
                    unique_assets.add(code)
                except: pass
            if assets: baskets[name] = assets
        except: pass

    if not baskets:
        st.error("❌ Hiçbir geçerli sepet bulunamadı.")
        st.stop()

    t1, t2 = pd.to_datetime(date_start), pd.to_datetime(date_end)
    df_pool = pd.DataFrame()
    
    with st.spinner('Piyasa verileri toplanıyor...'):
        if show_usd and 'USD' not in unique_assets: unique_assets.add('USD')
        if show_gold and 'ALTIN' not in unique_assets: unique_assets.add('ALTIN')

        for kod in unique_assets:
            df_raw = None
            if kod == 'USD': 
                df_raw = get_market_data("TRY=X", t1, t2)
            elif kod == 'ALTIN': 
                d1 = get_market_data("GC=F", t1, t2)
                d2 = get_market_data("TRY=X", t1, t2)
                if d1 is not None and d2 is not None:
                    c = d1.index.intersection(d2.index)
                    gram = (d1.loc[c]['FIYAT'] * d2.loc[c]['FIYAT']) / 31.1035
                    df_raw = pd.DataFrame(gram, columns=['FIYAT'])
            else: 
                df_raw = get_tefas_history(kod, t1, t2)
            
            if df_raw is not None and not df_raw.empty:
                df_raw.columns = [kod]
                # Mükerrer indexleri temizle
                df_raw = df_raw[~df_raw.index.duplicated(keep='first')]
                if df_pool.empty: df_pool = df_raw
                else: df_pool = df_pool.join(df_raw, how='outer')

        # GÜNCELLENEN KISIM: ffill ve bfill yeni yöntem
        if not df_pool.empty:
            df_pool = df_pool.ffill().bfill()
            df_pool = df_pool.loc[t1:t2]

        if df_pool.empty:
            st.error("❌ Veri yok. Tarih aralığını kontrol edin.")
            st.stop()

    df_baskets = pd.DataFrame(index=df_pool.index)
    basket_metrics = {}

    for b_name, assets in baskets.items():
        valid_assets = {k:v for k,v in assets.items() if k in df_pool.columns}
        if not valid_assets: continue
        daily_vals = pd.Series(0.0, index=df_pool.index)
        for kod, oran in valid_assets.items():
            start_price = df_pool[kod].iloc[0]
            if start_price > 0:
                lot = (money * (oran/100)) / start_price
                daily_vals += df_pool[kod] * lot
        df_baskets[b_name] = daily_vals

    if 'USD' in df_pool.columns and show_usd:
        df_baskets['DOLAR (Ref)'] = (df_pool['USD'] / df_pool['USD'].iloc[0]) * money
    if 'ALTIN' in df_pool.columns and show_gold:
        df_baskets['ALTIN (Ref)'] = (df_pool['ALTIN'] / df_pool['ALTIN'].iloc[0]) * money

    df_assets_sim = pd.DataFrame(index=df_pool.index)
    if show_details:
        for col in df_pool.columns:
            if col in ['USD', 'ALTIN']: continue
            s_val = df_pool[col].iloc[0]
            if s_val > 0:
                df_assets_sim[f"{col} (Fon)"] = (df_pool[col] / s_val) * money

    df_all_values = pd.concat([df_baskets, df_assets_sim], axis=1)

    for col in df_baskets.columns:
        vals = df_baskets[col]
        son_brut = vals.iloc[-1]
        
        if "(Ref)" in col or any(x in col for x in ["USD", "DOLAR", "ALTIN"]):
            effective_stopaj = 0.0
        else:
            effective_stopaj = 0.175
        
        kar_brut = son_brut - money
        vergi = max(0, kar_brut * effective_stopaj)
        
        son_net = son_brut - vergi
        kar_net = son_net - money
        
        gunluk = vals.pct_change().mean()
        aylik_kazanc_brut = son_brut * (gunluk * 21) 
        
        if aylik_kazanc_brut > 0:
            aylik_kazanc_net = aylik_kazanc_brut * (1 - effective_stopaj)
        else:
            aylik_kazanc_net = aylik_kazanc_brut
            
        net_akis = aylik_kazanc_net - expense
        
        if net_akis > 0:
            omur, renk = "Sonsuz (Artıda) 🚀", "normal"
        else:
            omur = f"{(son_net / abs(net_akis)):.1f} Ay" if abs(net_akis) > 0 else "Hesaplanamadı"
            renk = "inverse"
        
        basket_metrics[col] = {
            "son": son_net, "kar": kar_net, "aylik_gelir": aylik_kazanc_net, 
            "net_akis": net_akis, "omur": omur, "renk": renk, "vergi": vergi
        }

    # GÖRSELLEŞTİRME
    color_map = {'DOLAR (Ref)': '#2ecc71', 'ALTIN (Ref)': '#f1c40f'}
    base_colors = ['#3498db', '#e74c3c', '#9b59b6', '#f39c12', '#1abc9c', '#34495e', '#d35400', '#7f8c8d']
    
    b_idx = 0
    for col in df_all_values.columns:
        if col not in color_map:
            color_map[col] = base_colors[b_idx % len(base_colors)]
            b_idx += 1

    df_norm = df_all_values.copy()
    for col in df_norm.columns:
        s_v = df_norm[col].iloc[0]
        if s_v > 0:
            df_norm[col] = ((df_norm[col] / s_v) - 1) * 100

    st.header("Geçmiş Performans Analizi (Brüt Değerler)")
    c1, c2 = st.columns([3, 1])
    
    with c1:
        st.subheader("🏁 1. Getiri Yarışı (%)")
        fig1, ax1 = plt.subplots(figsize=(10, 6))
        for col in df_norm.columns:
            is_ref, is_fon = "(Ref)" in col, "(Fon)" in col
            if is_ref: lw, ls, alpha = 2.5, '--', 0.9
            elif is_fon: lw, ls, alpha = 1.0, '-', 0.6
            else: lw, ls, alpha = 3.5, '-', 1.0
            ax1.plot(df_norm.index, df_norm[col], label=col, linewidth=lw, linestyle=ls, color=color_map.get(col, 'gray'), alpha=alpha)
        ax1.axhline(0, color='black', linewidth=1)
        ax1.grid(True, alpha=0.3)
        ax1.legend(loc='upper left', fontsize='small', framealpha=0.8) 
        st.pyplot(fig1)
        
    with c2:
        st.subheader("🏆 2. Sıralama")
        if not df_norm.empty:
            last_vals = df_norm.iloc[-1].sort_values(ascending=False)
            fig2, ax2 = plt.subplots(figsize=(5, 8))
            bar_colors = ['#27ae60' if x>=0 else '#c0392b' for x in last_vals.values]
            ax2.barh(last_vals.index, last_vals.values, color=bar_colors)
            ax2.axvline(0, color='black', linewidth=0.5)
            st.pyplot(fig2)

    st.subheader(f"💰 3. Net Nakit Durumu")
    if not df_all_values.empty:
        fig3, ax3 = plt.subplots(figsize=(15, 7))
        days_passed = (df_all_values.index - df_all_values.index[0]).days
        cumulative_expense = days_passed * (expense / 30)
        for col in df_all_values.columns:
            net_varlik = df_all_values[col] - cumulative_expense
            is_ref, is_fon = "(Ref)" in col, "(Fon)" in col
            lw, ls, alpha = (2, '--', 0.8) if is_ref else ((1, '-', 0.5) if is_fon else (3, '-', 1.0))
            ax3.plot(net_varlik.index, net_varlik, label=col, linewidth=lw, linestyle=ls, color=color_map.get(col, 'gray'), alpha=alpha)
        ax3.axhline(0, color='red', linestyle='--', linewidth=2)
        ax3.grid(True, alpha=0.3)
        st.pyplot(fig3)

    st.header("📊 Finansal Rapor")
    for b_name in [c for c in df_baskets.columns if c in basket_metrics]:
        m = basket_metrics[b_name]
        st.markdown(f"<div class='basket-header'>{b_name}</div>", unsafe_allow_html=True)
        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("Toplam Net", f"{m['son']:,.0f} ₺")
        c2.metric("Aylık Net Gelir", f"{m['aylik_gelir']:,.0f} ₺")
        c3.metric("Aylık Gider", f"{expense:,.0f} ₺")
        c4.metric("Net Akış", f"{m['net_akis']:,.0f} ₺", delta_color=m['renk'])
        c5.metric("Nakit Ömrü", m['omur'])
        st.divider()

    st.subheader("📉 4. Detaylı Düşüş Karnesi")
    for asset in df_all_values.columns:
        series = df_all_values[asset]
        roll_max = series.cummax()
        drawdown = (series - roll_max) / roll_max * 100
        mdd_val = drawdown.min()
        mdd_date = drawdown.idxmin()
        
        c_chart, c_stat = st.columns([3, 1])
        with c_chart:
            fig_sub, ax_sub = plt.subplots(figsize=(10, 2))
            ax_sub.plot(drawdown.index, drawdown, color=color_map.get(asset, 'gray'))
            ax_sub.fill_between(drawdown.index, drawdown, 0, color=color_map.get(asset, 'gray'), alpha=0.2)
            st.pyplot(fig_sub)
        with c_stat:
            st.metric(asset, f"%{mdd_val:.2f}")
        st.divider()
