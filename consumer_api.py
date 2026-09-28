from fastapi import FastAPI
from kafka import KafkaConsumer
import json
import joblib
import pandas as pd
import threading
import requests
import os
from dotenv import load_dotenv
from sqlalchemy import create_engine, Column, Integer, Float, Boolean, String
from sqlalchemy.orm import declarative_base, sessionmaker
from datetime import datetime

load_dotenv()

app = FastAPI(title="Fraud Detection Inference API")

# --- SETUP DATABASE SQLITE (LEVEL 2 INJECT) ---
DB_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), 'fraud_history.db'))
DATABASE_URL = f"sqlite:///{DB_PATH}"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class TransactionLog(Base):
    __tablename__ = 'transaction_logs'
    id = Column(Integer, primary_key=True, autoincrement=True)
    transaction_id = Column(Integer)
    jumlah_transaksi = Column(Float)
    lokasi_id = Column(Integer)
    is_anomaly = Column(Boolean)
    timestamp = Column(String)

Base.metadata.create_all(engine)

model = joblib.load('anomaly_model.pkl')
latest_data = {"status": "Belum ada aliran data masuk"}

# Parameter Sensitivitas Dinamis (Default Rp 5.000)
sensitivity_threshold = 5000.0

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

def send_telegram_alert(jumlah, lokasi):
    """Fungsi menembakkan pesan peringatan ke Telegram"""
    if not TELEGRAM_TOKEN or not CHAT_ID:
        return
        
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    pesan = f"🚨 **ALERT ANOMALI TERDETEKSI!** 🚨\n\nTransaksi senilai **Rp {jumlah:,.2f}** ditemukan di Lokasi ID **{lokasi}**.\nSistem menduga ini adalah aktivitas kecurangan. Segera periksa dashboard!"
    
    payload = {
        "chat_id": CHAT_ID,
        "text": pesan,
        "parse_mode": "Markdown"
    }
    try:
        requests.post(url, json=payload, timeout=5)
    except Exception as e:
        print(f"Gagal mengirim notifikasi Telegram: {e}")

def consume_messages():
    global latest_data
    try:
        print("Mencoba terhubung ke Kafka Consumer...")
        kafka_server = os.getenv('KAFKA_BOOTSTRAP_SERVERS', '127.0.0.1:9092')
        consumer = KafkaConsumer(
            'transaksi-finansial',
            bootstrap_servers=kafka_server,
            value_deserializer=lambda m: json.loads(m.decode('utf-8')),
            auto_offset_reset='latest',
            group_id='grup-pelacak-1'
        )
        print("Berhasil terhubung ke Kafka! Menunggu data mengalir...")
        
        for message in consumer:
            data = message.value
            
            data_untuk_ai = {
                'jumlah_transaksi': data['amount'],
                'lokasi_id': data['user_id']
            }
            
            df = pd.DataFrame([data_untuk_ai])
            prediksi = model.predict(df)[0]
            
            # Gabungan Prediksi AI + Ambang Batas Sensitivitas Dinamis
            is_anomaly_by_model = True if prediksi == -1 else False
            is_anomaly_by_threshold = data["amount"] >= sensitivity_threshold
            
            # Anomali jika terdeteksi oleh AI atau melewati ambang batas sensitivitas
            final_anomaly = is_anomaly_by_model or is_anomaly_by_threshold
            
            latest_data = {
                "transaction_id": data.get("transaction_id", "N/A"),
                "jumlah_transaksi": data["amount"],
                "lokasi_id": data["user_id"],
                "timestamp": data.get("timestamp", ""),
                "is_anomaly": final_anomaly
            }
            
            # --- PERSISTENCE INJECT (LEVEL 2) ---
            db_session = SessionLocal()
            try:
                log_entry = TransactionLog(
                    transaction_id=data.get("transaction_id", 0),
                    jumlah_transaksi=data["amount"],
                    lokasi_id=data["user_id"],
                    is_anomaly=final_anomaly,
                    timestamp=data.get("timestamp", datetime.now().isoformat())
                )
                db_session.add(log_entry)
                db_session.commit()
            except Exception as db_err:
                print(f"❌ DB Error: {db_err}")
            finally:
                db_session.close()
            # ------------------------------------
            
            if final_anomaly:
                print(f"🚨 Anomali Terdeteksi (Rp {data['amount']}): Sending Telegram Alert...")
                send_telegram_alert(data["amount"], data["user_id"])
                
    except Exception as e:
        print(f"❌ ERROR DI CONSUMER: {e}")

threading.Thread(target=consume_messages, daemon=True).start()

@app.get("/api/data")
def get_latest_data():
    return latest_data

@app.get("/api/history")
def get_transaction_history(limit: int = 50):
    """Endpoint Level 2: Mengambil riwayat transaksi dari Database SQLite"""
    db_session = SessionLocal()
    try:
        logs = db_session.query(TransactionLog).order_by(TransactionLog.id.desc()).limit(limit).all()
        history = [
            {
                "id": log.id,
                "transaction_id": log.transaction_id,
                "jumlah_transaksi": log.jumlah_transaksi,
                "lokasi_id": log.lokasi_id,
                "is_anomaly": log.is_anomaly,
                "timestamp": log.timestamp
            }
            for log in logs
        ]
        return {"total": len(history), "data": history}
    finally:
        db_session.close()