import streamlit as st
import requests
import pandas as pd
import time
import os

st.set_page_config(page_title="Fraud Detection Center", page_icon="🛡️", layout="wide")

# ==========================================
# SIDEBAR CONTROL PANEL (LEVEL 1 UPGRADE)
# ==========================================
st.sidebar.title("⚙️ Engine Control Panel")
st.sidebar.markdown("Sesuaikan sensitivitas AI & Filter Tampilan secara Real-Time.")

# 1. Dynamic Sensitivity Slider
sensitivity = st.sidebar.slider(
    "🎯 Ambang Batas Sensitivitas Fraud (Rp)",
    min_value=1000.0,
    max_value=10000.0,
    value=5000.0,
    step=500.0,
    help="Transaksi di atas nilai ini atau yang dianggap aneh oleh ML akan memicu alarm."
)

# Kirim pembaruan sensitivitas ke API
try:
    requests.post(f"http://127.0.0.1:8000/api/sensitivity?threshold={sensitivity}")
except:
    pass

st.sidebar.markdown("---")

# 2. Interactive Sidebar Filters
show_only_anomalies = st.sidebar.checkbox("🚨 Filter: Hanya Tampilkan Anomali", value=False)
selected_user = st.sidebar.number_input("🔍 Filter Lokasi/User ID (0 = Semua)", min_value=0, max_value=50, value=0)
max_history = st.sidebar.slider("Kapasitas Riwayat Grafik", min_value=10, max_value=100, value=30, step=10)

st.sidebar.markdown("---")
st.sidebar.caption("Status Sistem: Terkoneksi ke Redpanda Kafka Broker")

# ==========================================
# MAIN DASHBOARD UI
# ==========================================
st.title("🛡️ Real-Time Fraud Detection Engine")
st.markdown("Pusat pemantauan aliran transaksi finansial dengan kontrol sensitivitas dinamik.")

if 'history' not in st.session_state:
    st.session_state.history = []

col1, col2, col3 = st.columns(3)
metrik_total = col1.empty()
metrik_anomali = col2.empty()
metrik_status = col3.empty()

placeholder_grafik = st.empty()
placeholder_tabel = st.empty()
placeholder_alert = st.empty()

for i in range(200):
    try:
        # Penarikan data real-time terkini
        API_BASE_URL = os.getenv('API_URL', 'http://127.0.0.1:8000')
        response = requests.get(f"{API_BASE_URL}/api/data", timeout=2)
        data = response.json()
        
        if "jumlah_transaksi" in data:
            if not st.session_state.history or st.session_state.history[-1].get("timestamp") != data.get("timestamp"):
                st.session_state.history.append(data)
                
            if len(st.session_state.history) > max_history:
                st.session_state.history.pop(0)
    except:
        pass

    # --- LEVEL 2 INJECT: Tampilkan Opsi Riwayat DB di Sidebar ---
    try:
        db_response = requests.get("http://127.0.0.1:8000/api/history?limit=100", timeout=2)
        if db_response.status_code == 200:
            st.sidebar.success(f"💾 DB Saved: {db_response.json().get('total', 0)} Records")
    except:
        st.sidebar.warning("💾 DB Connection: Pending")

    if st.session_state.history:
        df = pd.DataFrame(st.session_state.history)
        
        total_data = len(df)
        total_anomali = df['is_anomaly'].sum() if 'is_anomaly' in df.columns else 0
        
        metrik_total.metric(label="Total Transaksi Dipantau", value=total_data)
        metrik_anomali.metric(label="Total Indikasi Fraud", value=total_anomali)
        
        last_item = st.session_state.history[-1]
        if last_item.get("is_anomaly"):
            metrik_status.metric(label="Status Terkini", value="🚨 WASPADA / FRAUD")
        else:
            metrik_status.metric(label="Status Terkini", value="✅ AMAN")

        # Visualisasi Grafik Line Chart
        with placeholder_grafik.container():
            st.subheader("📈 Pergerakan Nilai Transaksi Real-Time")
            st.line_chart(df['jumlah_transaksi'], height=280)
            
        # Tabel Log Transaksi Terkini + Filter Logic
        with placeholder_tabel.container():
            st.subheader("📋 Log Transaksi Terkini")
            df_tampil = df.copy()
            
            # Filter 1: Hanya Anomali
            if show_only_anomalies and 'is_anomaly' in df_tampil.columns:
                df_tampil = df_tampil[df_tampil['is_anomaly'] == True]
                
            # Filter 2: Spesifik Lokasi/User ID
            if selected_user > 0 and 'lokasi_id' in df_tampil.columns:
                df_tampil = df_tampil[df_tampil['lokasi_id'] == selected_user]
                
            st.dataframe(df_tampil.iloc[::-1].head(10), use_container_width=True)
            
        # Alert Box
        with placeholder_alert.container():
            if last_item.get("is_anomaly"):
                st.error(f"🚨 **FRAUD ALERT!** Transaksi senilai **Rp {last_item['jumlah_transaksi']:,.2f}** pada Lokasi ID **{last_item['lokasi_id']}** melebihi ambang batas aman (Rp {sensitivity:,.2f})!")
            else:
                st.success(f"✅ Transaksi terakhir Rp {last_item['jumlah_transaksi']:,.2f} terverifikasi dalam rentang normal.")
    else:
        placeholder_grafik.info("Menunggu aliran data masuk dari Kafka... Pastikan Docker, FastAPI, dan Producer sudah menyala.")

    time.sleep(1)