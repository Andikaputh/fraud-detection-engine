import json
import time
import random
from kafka import KafkaProducer
from datetime import datetime

# Menyambungkan Python ke mesin Kafka (Redpanda) lokal
producer = KafkaProducer(
    bootstrap_servers=['localhost:9092'],
    value_serializer=lambda v: json.dumps(v).encode('utf-8')
)

topic_name = 'transaksi-finansial'

print("Mengirim data transaksi ke Kafka. Tekan Ctrl+C untuk berhenti.")

while True:
    # Simulasi data transaksi normal
    amount = round(random.uniform(10.0, 500.0), 2)
    
    # Simulasi anomali: 5% kemungkinan transaksi bernilai sangat besar (indikasi fraud)
    if random.random() < 0.05:
        amount = round(random.uniform(5000.0, 10000.0), 2)

    data = {
        "transaction_id": random.randint(1000, 9999),
        "user_id": random.randint(1, 50),
        "amount": amount,
        "timestamp": datetime.now().isoformat()
    }

    # Mengirim data ke Kafka
    producer.send(topic_name, value=data)
    print(f"Terkirim: {data}")
    
    # Jeda 2 detik sebelum membuat transaksi berikutnya
    time.sleep(2)