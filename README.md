# 🛡️ Real-Time Fraud Detection Engine

An end-to-end real-time anomaly detection pipeline designed to process streaming financial transaction data, evaluate suspicious patterns using Machine Learning (Isolation Forest), issue automated Telegram alerts, and visualize live metrics through an interactive Command Center.

---

## 🏗️ System Architecture

```text
 ┌───────────────────────┐
 │ Data Generator        │ (producer.py)
 └───────────┬───────────┘
             │ Streaming Transactions
             ▼
 ┌───────────────────────┐
 │ Redpanda / Kafka      │ (Broker Port: 9092)
 └───────────┬───────────┘
             │ Consumed Messages
             ▼
 ┌───────────────────────┐       🚨 Telegram Bot
 │ FastAPI Consumer + ML │ ────────────────────────► Alert Notifications
 └───────────┬───────────┘
             │ DB Logging & API Metrics
             ▼
 ┌───────────────────────┐
 │ Streamlit Dashboard   │ (Live Command Center Port: 8501)
 └───────────────────────┘