from fastapi import FastAPI
from kafka import KafkaConsumer
import json
import joblib
import pandas as pd
import threading

app = FastAPI()

model = joblib.load('anomaly_model.pkl')
latest_data = {"status": "Belum ada aliran data masuk"}

def consume_messages():
    global latest_data
    try:
        print("Mencoba terhubung ke Kafka Consumer...")
        consumer = KafkaConsumer(
            'transaksi-finansial',
            bootstrap_servers='127.0.0.1:9092',
            value_deserializer=lambda m: json.loads(m.decode('utf-8')),
            auto_offset_reset='earliest',
            group_id='grup-pelacak-1'
        )
        print("Berhasil terhubung ke Kafka! Menunggu data mengalir...")
        
        for message in consumer:
            data = message.value
            print(f"📥 Data ditangkap dari Kafka: {data}")

            data_untuk_ai = {
                'jumlah_transaksi': data['amount'],
                'lokasi_id': data['user_id']
            }
            
            # Pastikan urutan kolom sama persis dengan saat training
            df = pd.DataFrame([data_untuk_ai])
            prediksi = model.predict(df)[0]
            
            # Memperbarui data untuk dikirim ke Dashboard Streamlit
            latest_data = {
                "jumlah_transaksi": data["amount"],
                "lokasi_id": data["user_id"],
                "is_anomaly": True if prediksi == -1 else False
            }
            print(f"🔄 Status terupdate: {latest_data}")
            
    except Exception as e:
        print(f"❌ ERROR DI CONSUMER: {e}")

threading.Thread(target=consume_messages, daemon=True).start()

@app.get("/api/data")
def get_latest_data():
    return latest_data