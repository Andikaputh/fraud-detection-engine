# Gunakan image Python resmi yang ringan
FROM python:3.10-slim

WORKDIR /app

# Salin berkas dependensi dan instal
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Salin seluruh berkas proyek
COPY . .

# Expose port FastAPI (8000) dan Streamlit (8501)
EXPOSE 8000 8501