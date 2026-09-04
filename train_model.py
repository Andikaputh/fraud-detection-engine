import pandas as pd
import numpy as np
from sklearn.ensemble import IsolationForest
import joblib

print("Mulai membuat data simulasi untuk melatih AI...")
# Membuat 1000 contoh data transaksi wajar
np.random.seed(42)
normal_data = pd.DataFrame({
    'jumlah_transaksi': np.random.normal(50000, 10000, 1000), # Rata-rata transaksi 50 ribu
    'lokasi_id': np.random.randint(1, 10, 1000)
})

# Membuat 50 contoh data transaksi aneh / mencurigakan
anomaly_data = pd.DataFrame({
    'jumlah_transaksi': np.random.uniform(500000, 1000000, 50), # Transaksi mendadak jutaan
    'lokasi_id': np.random.randint(90, 100, 50) # Lokasi yang tidak biasa
})

# Menggabungkan data normal dan anomali menjadi satu buku pelajaran untuk AI
X_train = pd.concat([normal_data, anomaly_data])

print("Melatih model Isolation Forest...")
# Membangun model AI. 'contamination' adalah perkiraan rasio data anomali (5%)
model = IsolationForest(n_estimators=100, contamination=0.05, random_state=42)
model.fit(X_train)

# Menyimpan "otak" AI yang sudah pintar ke dalam file berekstensi .pkl
joblib.dump(model, 'anomaly_model.pkl')
print("Latihan Selesai! Model AI berhasil disimpan sebagai 'anomaly_model.pkl'")