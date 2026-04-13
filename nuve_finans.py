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
# 1. VERİ MOTORLARI (GÜÇLENDİRİLMİŞ)
# ==========================================
@st.cache_data(ttl=3600)
def fetch_chunk(fon_kodu, start_date, end_date):
    """
    TEFAS'tan veri çekerken hata olursa 3 kez tekrar dener (Retry Logic).
    """
    s_str = start_date.strftime("%d.%m.%Y")
    e_str = end_date.strftime("%d.%m.%Y")
    url = "https://www.tefas.gov.tr/api/DB/BindHistoryInfo"
    payload = {"fontip": "YAT", "fonkod": fon_kodu, "bastarih": s_str, "bittarih": e_str, "strperiod": "1,1,1,1,1,1,1"}
    headers = {
        "Referer": "https://www.tefas.gov.tr", 
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36", 
        "X-Requested-With": "XMLHttpRequest"
    }
    
    # 3 Kez Deneme Hakkı
    for attempt in range(3):
        try:
            response = requests.post(url, data=payload, headers=headers, timeout=15, verify=False)
            data = response.json().get('data', [])
            if data: # Veri geldiyse döndür
                return data
            else:
                time.sleep(0.5) # Boş geldiyse az bekle tekrar dene
        except:
            time.sleep(1) # Hata aldıysa 1 sn bekle tekrar dene
            
    return [] # 3 kere denedi yine olmadıysa boş dön

@st.cache_data(ttl=3600)
def get_tefas_history(fon_kodu, start_date, end_date):
    all_data = []
    current_start = start_date
    while current_start < end_date:
        # TEFAS genelde 90 gün üstünü tek seferde vermez, 80 güne bölelim garanti olsun
        current_end = min(current_start + timedelta(days=80), end_date)
        chunk = fetch_chunk(fon_kodu, current_start, current_end)
        if chunk:
            all_data.extend(chunk)
        current_start = current_end + timedelta(days=1)
        time.sleep(0.1) # Seri istek atıp IP ban yemeyelim
    
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
    # Varsayılan tarihi biraz geriye çektim ki grafik düzgün oluşsun
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
    # --- 1. SEPETLERİ PARSE ET ---
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

    # --- 2. VERİLERİ ÇEK ---
    t1, t2 = pd.to_datetime(date_start), pd.to_datetime(date_end)
    df_pool = pd.DataFrame()
    
    with st.spinner('Piyasa verileri toplanıyor... (Hata olursa otomatik tekrar denenecek)'):
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
                if df_pool.empty: df_pool = df_raw
                else: df_pool = df_pool.join(df_raw, how='outer')

        # Eksik verileri doldurma (ffill: önceki günü kopyala)
        df_pool = df_pool.ffill()
        df_pool = df_pool.bfill()
        df_pool = df_pool.loc[t1:t2]

        if df_pool.empty:
            st.error("❌ Veri yok. Tarih aralığını kontrol edin.")
            st.stop()

    # --- 3. HESAPLAMALAR ---
    df_baskets = pd.DataFrame(index=df_pool.index)
    basket_metrics = {}

    # -- A. Sepet Hesapları --
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

    # -- B. Referanslar --
    if 'USD' in df_pool.columns and show_usd:
        df_baskets['DOLAR (Ref)'] = (df_pool['USD'] / df_pool['USD'].iloc[0]) * money
    if 'ALTIN' in df_pool.columns and show_gold:
        df_baskets['ALTIN (Ref)'] = (df_pool['ALTIN'] / df_pool['ALTIN'].iloc[0]) * money

    # -- C. Tekil Fonların Performansı (Kıyaslama İçin) --
    df_assets_sim = pd.DataFrame(index=df_pool.index)
    if show_details:
        for col in df_pool.columns:
            if col in ['USD', 'ALTIN']: continue
            s_val = df_pool[col].iloc[0]
            if s_val > 0:
                df_assets_sim[f"{col} (Fon)"] = (df_pool[col] / s_val) * money

    # Birleştirilmiş Dataframe
    df_all_values = pd.concat([df_baskets, df_assets_sim], axis=1)

    # Metrikleri Hesapla
    report_cols = df_baskets.columns 
    
    for col in report_cols:
        vals = df_baskets[col]
        son_brut = vals.iloc[-1]
        
        # --- STOPAJ HESABI (YENİ VE DÜZELTİLMİŞ) ---
        # 1. Referanslarda (Dolar, Altın) Stopaj Yok
        if "(Ref)" in col or "USD" in col or "DOLAR" in col or "ALTIN" in col:
            effective_stopaj = 0.0
        else:
            # 2. Fon Sepetlerinde %17.5 Stopaj
            effective_stopaj = 0.175
        
        kar_brut = son_brut - money
        vergi = 0
        if kar_brut > 0:
            vergi = kar_brut * effective_stopaj
        
        son_net = son_brut - vergi
        kar_net = son_net - money
        
        # --- AYLIK GELİR VE NET AKIŞ ---
        gunluk = vals.pct_change().mean()
        
        # Aylık BRÜT Kazanç
        aylik_kazanc_brut = son_brut * (gunluk * 21) 
        
        # Aylık NET Kazanç
        aylik_kazanc_net = 0
        if aylik_kazanc_brut > 0:
            aylik_kazanc_net = aylik_kazanc_brut * (1 - effective_stopaj)
        else:
            aylik_kazanc_net = aylik_kazanc_brut # Zararsa vergi yok
            
        net_akis = aylik_kazanc_net - expense
        
        if net_akis > 0:
            omur, renk = "Sonsuz (Artıda) 🚀", "normal"
        else:
            # Ömür hesabında net varlığı, net akışa bölüyoruz
            omur = f"{(son_net / abs(net_akis)):.1f} Ay" if abs(net_akis) > 0 else "Hesaplanamadı"
            renk = "inverse"
        
        basket_metrics[col] = {
            "son": son_net, 
            "kar": kar_net, 
            "aylik_gelir": aylik_kazanc_net, 
            "net_akis": net_akis, 
            "omur": omur, 
            "renk": renk,
            "vergi": vergi
        }

    # ==========================================
    # 4. GÖRSELLEŞTİRME
    # ==========================================
    
    color_map = {'DOLAR (Ref)': '#2ecc71', 'ALTIN (Ref)': '#f1c40f'}
    base_colors = ['#3498db', '#e74c3c', '#9b59b6', '#f39c12', '#1abc9c', '#34495e', '#d35400', '#7f8c8d']
    
    b_idx = 0
    for col in df_all_values.columns:
        if col not in color_map:
            color_map[col] = base_colors[b_idx % len(base_colors)]
            b_idx += 1

    # --- Yüzdesel Normalize Et ---
    df_norm = df_all_values.copy()
    for col in df_norm.columns:
        s_v = df_norm[col].iloc[0]
        if s_v > 0:
            df_norm[col] = ((df_norm[col] / s_v) - 1) * 100

    st.header("Geçmiş Performans Analizi (Brüt Değerler)")

    # --- GRAFİK 1 & 2 ---
    c1, c2 = st.columns([3, 1])
    
    with c1:
        st.subheader("🏁 1. Getiri Yarışı (%) - Sepetler ve İçerikleri")
        fig1, ax1 = plt.subplots(figsize=(10, 6))
        
        for col in df_norm.columns:
            is_ref = "(Ref)" in col
            is_fon = "(Fon)" in col
            
            if is_ref: lw, ls, alpha = 2.5, '--', 0.9
            elif is_fon: lw, ls, alpha = 1.0, '-', 0.6
            else: lw, ls, alpha = 3.5, '-', 1.0
            
            c = color_map.get(col, 'gray')
            ax1.plot(df_norm.index, df_norm[col], label=col, linewidth=lw, linestyle=ls, color=c, alpha=alpha)
        
        ax1.axhline(0, color='black', linewidth=1)
        ax1.grid(True, alpha=0.3)
        ax1.legend(loc='upper left', fontsize='small', framealpha=0.8) 
        ax1.set_ylabel("Getiri (%)")
        st.pyplot(fig1)
        
    with c2:
        st.subheader("🏆 2. Sıralama")
        if not df_norm.empty:
            last_vals = df_norm.iloc[-1].sort_values(ascending=False)
            fig2, ax2 = plt.subplots(figsize=(5, 8))
            bar_colors = ['#27ae60' if x>=0 else '#c0392b' for x in last_vals.values]
            bars = ax2.barh(last_vals.index, last_vals.values, color=bar_colors)
            ax2.axvline(0, color='black', linewidth=0.5)
            for bar in bars:
                width = bar.get_width()
                label_x_pos = width + 1 if width >= 0 else width - 5
                ax2.text(label_x_pos, bar.get_y() + bar.get_height()/2, f"%{width:.1f}", va='center', fontweight='bold', fontsize=9)
            ax2.grid(axis='x', alpha=0.3)
            st.pyplot(fig2)

    st.markdown("---")

    # --- GRAFİK 3: NAKİT DURUMU ---
    st.subheader(f"💰 3. Net Nakit Durumu (Ana Para: {money:,.0f} TL | Aylık Gider: {expense:,.0f} TL Düşülmüş)")
    st.caption("Not: İnce çizgiler tekil fonları, kalın çizgiler sepetlerinizi temsil eder. (Grafik Brüt Piyasa Değeridir)")
    
    if not df_all_values.empty:
        fig3, ax3 = plt.subplots(figsize=(15, 7))
        days_passed = (df_all_values.index - df_all_values.index[0]).days
        cumulative_expense = days_passed * (expense / 30)

        sorted_cols = [c for c in df_all_values.columns if "(Fon)" in c] + \
                      [c for c in df_all_values.columns if "(Ref)" in c] + \
                      [c for c in df_all_values.columns if "(Ref)" not in c and "(Fon)" not in c]

        for col in sorted_cols:
            net_varlik = df_all_values[col] - cumulative_expense
            son_durum = net_varlik.iloc[-1]
            c = color_map.get(col, 'gray')
            is_fon = "(Fon)" in col
            is_ref = "(Ref)" in col
            
            if is_ref: lw, ls, alpha = 2, '--', 0.8
            elif is_fon: lw, ls, alpha = 1, '-', 0.5
            else: lw, ls, alpha = 3, '-', 1.0
            
            ax3.plot(net_varlik.index, net_varlik, label=f"{col}", linewidth=lw, linestyle=ls, color=c, alpha=alpha)

        ax3.axhline(0, color='red', linestyle='--', linewidth=2, label='İflas Hattı (0 TL)')
        ax3.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: format(int(x), ',')))
        ax3.grid(True, alpha=0.3)
        ax3.legend(bbox_to_anchor=(1.01, 1), loc='upper left', borderaxespad=0.)
        st.pyplot(fig3)
    
    st.markdown("---")

    # --- RAPOR ---
    st.header("📊 Finansal Rapor (Aylık Gelir ve Net Akış)")
    st.info("ℹ️ **Aylık Gelir (Tahmini):** Portföyün geçmiş performansına göre 1 ayda ürettiği karın **Net (Vergi Düşülmüş)** halidir. \n\n"
            "ℹ️ **Vergi Oranları:** Fon Sepetleri: **%17.5** | Dolar/Altın (Ref): **%0**")
    rapor_cols = [c for c in df_baskets.columns if c in basket_metrics]
    
    for b_name in rapor_cols:
        m = basket_metrics[b_name]
        
        if "(Ref)" in b_name: 
            style = "color: #f1c40f;" if "ALTIN" in b_name else "color: #2ecc71;"
            header_html = f"<div style='{style} font-weight: bold; font-size: 1.5em; margin-top: 20px; border-bottom: 1px solid #333; padding-bottom: 5px;'>{b_name}</div>"
        else:
            header_html = f"<div class='basket-header'>{b_name}</div>"

        st.markdown(header_html, unsafe_allow_html=True)
        # SÜTUNLARI 5'e ÇIKARDIM (Daha net olsun diye)
        c1, c2, c3, c4, c5 = st.columns(5)
        
        c1.metric("Toplam Varlık (Net)", f"{m['son']:,.0f} ₺", f"{m['kar']:,.0f} ₺ Net Kar")
        c2.metric("Aylık Gelir (Net)", f"{m['aylik_gelir']:,.0f} ₺", "Ortalama Getiri")
        c3.metric("Aylık Gider", f"{expense:,.0f} ₺", "Sabit", delta_color="inverse")
        
        delta_text = "Artıda" if m['net_akis'] > 0 else "Ekside"
        c4.metric(f"Net Nakit Akışı", f"{m['net_akis']:,.0f} ₺", delta_text, delta_color=m['renk'])
        
        c5.metric("Nakit Ömrü", m['omur'])
        st.caption(f"📝 Kesilen Toplam Stopaj: **{m['vergi']:,.0f} TL**")
        st.divider()

    # ==========================================
    # 4. DETAYLI ERİME ANALİZİ (AYRI AYRI)
    # ==========================================
    st.markdown("---")
    st.subheader("📉 4. Detaylı Düşüş Karnesi (Risk Analizi)")

    if not df_all_values.empty:
        # Sıralama: Sepetler -> Refler -> Fonlar
        baskets_list = [c for c in df_baskets.columns if "(Ref)" not in c]
        refs_list = [c for c in df_baskets.columns if "(Ref)" in c]
        funds_list = [c for c in df_assets_sim.columns] if show_details else []
        
        sorted_assets = baskets_list + refs_list + funds_list

        for asset in sorted_assets:
            if asset not in df_all_values.columns: continue
            
            series = df_all_values[asset]
            # Drawdown Hesapla
            roll_max = series.cummax()
            drawdown = (series - roll_max) / roll_max * 100
            
            # --- İSTATİSTİKLER ---
            # 1. Max Drawdown (En dip)
            mdd_val = drawdown.min()
            mdd_date = drawdown.idxmin()
            
            # 2. En Uzun Sualtı Süresi (Longest Underwater Duration)
            is_under = drawdown < -0.01 
            blocks = (is_under != is_under.shift()).cumsum()
            underwater_groups = series[is_under].groupby(blocks[is_under])
            
            max_days = 0
            max_period_msg = "Süper (Hiç Düşmedi)"
            
            if underwater_groups.ngroups > 0:
                durations = []
                for _, g in underwater_groups:
                    d0, d1 = g.index[0], g.index[-1]
                    delta = (d1 - d0).days
                    durations.append((delta, d0, d1))
                
                if durations:
                    longest = max(durations, key=lambda x: x[0])
                    max_days = longest[0]
                    s_str = longest[1].strftime("%d.%m.%Y")
                    e_str = longest[2].strftime("%d.%m.%Y")
                    max_period_msg = f"{s_str} - {e_str}"

            # --- GÖRSELLEŞTİRME ---
            c_title, c_dummy = st.columns([3,1])
            with c_title:
                st.markdown(f"#### 🔹 {asset}")

            c_chart, c_stat = st.columns([3, 1])
            
            with c_chart:
                fig_sub, ax_sub = plt.subplots(figsize=(10, 3)) 
                col_code = color_map.get(asset, 'gray')
                
                ax_sub.plot(drawdown.index, drawdown, color=col_code, linewidth=1.5)
                ax_sub.fill_between(drawdown.index, drawdown, 0, color=col_code, alpha=0.3)
                ax_sub.axhline(0, color='black', linestyle='--', linewidth=1)
                
                # En dip noktayı işaretle
                ax_sub.scatter([mdd_date], [mdd_val], color='red', s=30, zorder=5)
                if not pd.isnull(mdd_val):
                     ax_sub.text(mdd_date, mdd_val - (abs(mdd_val)*0.1), f"%{mdd_val:.1f}", 
                           ha='center', va='top', fontsize=9, color='red', fontweight='bold')
                
                ax_sub.set_ylabel("Kayıp (%)")
                ax_sub.grid(True, alpha=0.2)
                ax_sub.spines['top'].set_visible(False)
                ax_sub.spines['right'].set_visible(False)
                
                st.pyplot(fig_sub)
            
            with c_stat:
                st.markdown("##### 📊 Risk Karnesi")
                st.metric("En Büyük Erime", f"%{mdd_val:.2f}", f"{mdd_date.strftime('%d.%m.%Y')}", delta_color="inverse")
                st.metric("Zararda Beklenen En Uzun Süre", f"{max_days} Gün", max_period_msg, delta_color="off")
                
            st.divider()
