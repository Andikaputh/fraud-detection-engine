from kafka import KafkaConsumer
import json

print("Mencari jejak data di Kafka...")
consumer = KafkaConsumer(
    'transaksi-stream',
    bootstrap_servers='127.0.0.1:9092',
    auto_offset_reset='earliest',
    value_deserializer=lambda m: json.loads(m.decode('utf-8'))
)

print("Terhubung! Menunggu data lewat...")
for msg in consumer:
    print(f"🎉 KETEMU: {msg.value}")