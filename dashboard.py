import streamlit as st
import requests
import pandas as pd
import time

# Konfigurasi Halaman (Harus di baris paling atas)
st.set_page_config(page_title="Fraud Detection Center", page_icon="🛡️", layout="wide")

# --- SIDEBAR PENGATURAN KENDALI ---
st.sidebar.title("⚙️ Control Panel")
st.sidebar.markdown("Sesuaikan sensitivitas dan tampilan pemantauan.")

# Fitur Quick Win 1: Filter Interaktif
show_only_anomalies = st.sidebar.checkbox("🚨 Hanya Tampilkan Anomali di Tabel", value=False)

# Fitur Quick Win 2: Kontrol Jumlah Riwayat Grafik
max_history = st.sidebar.slider("Kapasitas Riwayat Grafik", min_value=10, max_value=100, value=30, step=10)

st.sidebar.markdown("---")
st.sidebar.caption("Sistem terhubung ke aliran Kafka secara real-time.")

# --- TAMPILAN UTAMA ---
st.title("🛡️ Real-Time Fraud Detection Engine")
st.markdown("Pusat pemantauan aliran transaksi finansial untuk mendeteksi potensi kecurangan secara proaktif.")
st.markdown("---")

# Menyiapkan memori penyimpanan sementara
if 'history' not in st.session_state:
    st.session_state.history = []

# Menyiapkan wadah (placeholder) agar elemen bisa di-update tanpa me-refresh seluruh halaman
col1, col2, col3 = st.columns(3)
metrik_total = col1.empty()
metrik_anomali = col2.empty()
metrik_status = col3.empty()

placeholder_grafik = st.empty()
placeholder_tabel = st.empty()
placeholder_alert = st.empty()

# Perulangan utama penarikan data (simulasi berjalan 200 detik)
for i in range(200):
    try:
        response = requests.get("http://127.0.0.1:8000/api/data")
        data = response.json()
        
        # Jika data valid, masukkan ke memori
        if "jumlah_transaksi" in data:
            st.session_state.history.append(data)
            
            # Batasi panjang memori sesuai slider di sidebar
            if len(st.session_state.history) > max_history:
                st.session_state.history.pop(0)
    except:
        pass # Abaikan jika API terputus sedetik

    # Jika memori sudah terisi, mulai menggambar visualnya
    if st.session_state.history:
        df = pd.DataFrame(st.session_state.history)
        
        # 1. Update Kartu Metrik
        total_data = len(df)
        total_anomali = df['is_anomaly'].sum()
        
        metrik_total.metric(label="Total Transaksi Dipantau", value=total_data)
        metrik_anomali.metric(label="Total Indikasi Fraud", value=total_anomali)
        
        last_item = st.session_state.history[-1]
        if last_item.get("is_anomaly"):
            metrik_status.metric(label="Status Terkini", value="🚨 WASPADA")
        else:
            metrik_status.metric(label="Status Terkini", value="✅ AMAN")

        # 2. Update Grafik Garis
        with placeholder_grafik.container():
            st.subheader("📈 Pergerakan Nilai Transaksi")
            st.line_chart(df['jumlah_transaksi'], height=300)
            
        # 3. Update Tabel dengan Logika Filter Sidebar
        with placeholder_tabel.container():
            st.subheader("📋 Log Transaksi Terkini")
            df_tampil = df.copy()
            
            # Jika kotak di sidebar dicentang, buang data yang normal
            if show_only_anomalies:
                df_tampil = df_tampil[df_tampil['is_anomaly'] == True]
                
            # Balik urutan agar data terbaru ada di baris paling atas
            st.dataframe(df_tampil.iloc[::-1].head(10), use_container_width=True)
            
        # 4. Update Spanduk Peringatan
        with placeholder_alert.container():
            if last_item.get("is_anomaly"):
                st.error(f"🚨 **FRAUD ALERT!** Terdeteksi transaksi mencurigakan senilai **Rp {last_item['jumlah_transaksi']:,.2f}** dari Lokasi ID **{last_item['lokasi_id']}**!")
            else:
                st.success(f"✅ Transaksi terakhir senilai Rp {last_item['jumlah_transaksi']:,.2f} terverifikasi aman.")
    else:
        placeholder_grafik.info("Menunggu aliran data masuk dari API...")

    time.sleep(1) # Jeda 1 detik sebelum menarik data baru