import streamlit as st
import requests
import pandas as pd
import time

st.set_page_config(page_title="Real-Time Anomaly Detection Dashboard", layout="wide")

st.title("🛡️ Real-Time Anomaly Detection System")
st.markdown("Dashboard pemantauan transaksi *live stream* untuk mendeteksi potensi kecurangan secara otomatis.")

# Membuat tempat penampungan data sementara di memori browser
if 'history' not in st.session_state:
    st.session_state.history = []

placeholder = st.empty()

# Perulangan untuk menarik data terbaru setiap 1 detik
for i in range(200):
    try:
        response = requests.get("http://127.0.0.1:8000/api/data")
        data = response.json()
        
        if "jumlah_transaksi" in data:
            st.session_state.history.append(data)
            # Batasi hanya 20 data terakhir agar grafik tetap bersih
            if len(st.session_state.history) > 20:
                st.session_state.history.pop(0)
    except:
        pass

    with placeholder.container():
        if st.session_state.history:
            df = pd.DataFrame(st.session_state.history)
            
            # Metrik ringkasan
            st.metric(label="Total Data Dipantau", value=len(st.session_state.history))
            
            # --- FITUR BARU: GRAFIK TRANSAKSI ---
            st.subheader("📈 Pergerakan Nilai Transaksi Real-Time")
            # Membuat grafik yang akan otomatis naik-turun sesuai data
            st.line_chart(df['jumlah_transaksi'])
            
            # Tabel data terbaru
            st.subheader("📋 Aliran Transaksi Terkini")
            st.dataframe(df.tail(5), use_container_width=True)
            
            # Peringatan jika terdeteksi anomali pada data terakhir
            last_item = st.session_state.history[-1]
            if last_item.get("is_anomaly"):
                st.error(f"🚨 PERINGATAN! Terdeteksi Anomali pada Transaksi Senilai Rp {last_item['jumlah_transaksi']:,.2f} di Lokasi ID {last_item['lokasi_id']}!")
            else:
                st.success("✅ Status Transaksi Terakhir: Normal")
        else:
            st.info("Menunggu aliran data masuk dari Kafka... (Pastikan Data Generator dan API sudah menyala)")

    time.sleep(1)