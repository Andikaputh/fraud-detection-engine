from fastapi import FastAPI
from kafka import KafkaConsumer
import json
import joblib
import pandas as pd
import threading
import requests

app = FastAPI()

model = joblib.load('anomaly_model.pkl')
latest_data = {"status": "Belum ada aliran data masuk"}

# --- KONFIGURASI TELEGRAM ---
TELEGRAM_TOKEN = "8974888802:AAHVeA--ysGJg3b1ZUsAHy_8bQ6glc7pHoQ"
CHAT_ID = "1144968384"

def send_telegram_alert(jumlah, lokasi):
    """Fungsi menembakkan pesan peringatan ke Telegram"""
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    pesan = f"🚨 **ALERT ANOMALI TERDETEKSI!** 🚨\n\nTransaksi senilai **Rp {jumlah:,.2f}** ditemukan di Lokasi ID **{lokasi}**.\nSistem menduga ini adalah aktivitas kecurangan. Segera periksa dashboard!"
    
    payload = {
        "chat_id": CHAT_ID,
        "text": pesan,
        "parse_mode": "Markdown"
    }
    try:
        requests.post(url, json=payload)
    except Exception as e:
        print(f"Gagal mengirim notifikasi Telegram: {e}")
# -----------------------------

def consume_messages():
    global latest_data
    try:
        print("Mencoba terhubung ke Kafka Consumer...")
        consumer = KafkaConsumer(
            'transaksi-finansial', # Pastikan nama topik sama dengan Producer
            bootstrap_servers='127.0.0.1:9092',
            value_deserializer=lambda m: json.loads(m.decode('utf-8')),
            auto_offset_reset='earliest',
            group_id='grup-pelacak-1'
        )
        print("Berhasil terhubung ke Kafka! Menunggu data mengalir...")
        
        for message in consumer:
            data = message.value
            
            # Menerjemahkan data dari Producer agar sesuai dengan bahasa AI
            data_untuk_ai = {
                'jumlah_transaksi': data['amount'],
                'lokasi_id': data['user_id']
            }
            
            df = pd.DataFrame([data_untuk_ai])
            prediksi = model.predict(df)[0]
            
            is_anomaly = True if prediksi == -1 else False
            
            latest_data = {
                "jumlah_transaksi": data["amount"],
                "lokasi_id": data["user_id"],
                "is_anomaly": is_anomaly
            }
            
            print(f"🔄 Status terupdate: {latest_data}")
            
            # --- JIKA ANOMALI, TEMBAK NOTIFIKASI KE TELEGRAM ---
            if is_anomaly:
                print("🚨 Anomali terdeteksi! Mengirim pesan ke Telegram...")
                send_telegram_alert(data["amount"], data["user_id"])
                
    except Exception as e:
        print(f"❌ ERROR DI CONSUMER: {e}")

threading.Thread(target=consume_messages, daemon=True).start()

@app.get("/api/data")
def get_latest_data():
    return latest_data