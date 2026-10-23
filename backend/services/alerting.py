"""Outbound alert delivery (Telegram + generic webhook).

Delivery happens on a separate worker with a small queue so a slow third-party
API cannot slow down authorisation. Messages are throttled and include enough
context to act without opening the console.
"""

from __future__ import annotations

import html
import queue
import threading
import time

import requests

from backend.config import settings
from backend.core.logging import get_logger
from backend.core.settings_store import get_engine_config

logger = get_logger("sentinel.alerts")


class AlertDispatcher:
    def __init__(self) -> None:
        self.queue: queue.Queue = queue.Queue(maxsize=500)
        self.sent = 0
        self.failed = 0
        self.skipped = 0
        self.last_error: str | None = None
        self._last_sent_at = 0.0
        self._thread = threading.Thread(target=self._run, name="alert-dispatcher", daemon=True)
        self._stop = threading.Event()

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._thread.join(timeout=5)

    def submit(self, txn: dict) -> None:
        if not (settings.telegram_token and settings.telegram_chat_id) and not settings.alert_webhook_url:
            return
        try:
            self.queue.put_nowait(txn)
        except queue.Full:
            self.skipped += 1

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                txn = self.queue.get(timeout=0.5)
            except queue.Empty:
                continue
            cfg = get_engine_config()
            if not cfg.get("telegram_enabled"):
                self.skipped += 1
                self.queue.task_done()
                continue
            now = time.monotonic()
            if now - self._last_sent_at < 3.0:
                self.skipped += 1
                self.queue.task_done()
                continue
            self._send(txn)
            self._last_sent_at = time.monotonic()
            self.queue.task_done()

    def _send(self, txn: dict) -> None:
        text = self._format(txn)
        delivered = False
        if settings.telegram_token and settings.telegram_chat_id:
            try:
                response = requests.post(
                    f"https://api.telegram.org/bot{settings.telegram_token}/sendMessage",
                    json={
                        "chat_id": settings.telegram_chat_id,
                        "text": text,
                        "parse_mode": "HTML",
                        "disable_web_page_preview": True,
                    },
                    timeout=5,
                )
                if response.ok:
                    delivered = True
                else:
                    self.last_error = f"telegram http {response.status_code}"
            except Exception as exc:
                self.last_error = str(exc)
                logger.warning("telegram delivery failed: %s", exc)

        if settings.alert_webhook_url:
            try:
                response = requests.post(settings.alert_webhook_url, json=txn, timeout=5)
                if response.ok:
                    delivered = True
                else:
                    self.last_error = f"webhook http {response.status_code}"
            except Exception as exc:
                self.last_error = str(exc)
                logger.warning("webhook delivery failed: %s", exc)

        if delivered:
            self.sent += 1
        else:
            self.failed += 1

    @staticmethod
    def _format(txn: dict) -> str:
        reasons = txn.get("reasons") or []
        lines = []
        for reason in reasons[:4]:
            lines.append(f"• {html.escape(reason.get('label', 'Signal'))}")
        link = (
            f'\n<a href="{settings.public_base_url}/alerts/{txn.get("alert_id", "")}">Open in console</a>'
            if settings.public_base_url
            else ""
        )
        return (
            f"<b>Blocked authorisation</b>\n"
            f"Risk <b>{txn['risk_score']}/100</b> · {html.escape(txn.get('decision', 'block')).upper()}\n\n"
            f"Amount: <b>Rp {txn['amount']:,.0f}</b>\n"
            f"Merchant: {html.escape(str(txn.get('merchant_name', '')))}\n"
            f"Customer: {html.escape(str(txn.get('customer_id', '')))}\n"
            f"Country: {html.escape(str(txn.get('merchant_country', '')))}\n\n"
            + ("\n".join(lines) + "\n" if lines else "")
            + link
        )

    def stats(self) -> dict:
        return {
            "configured": bool(settings.telegram_token and settings.telegram_chat_id)
            or bool(settings.alert_webhook_url),
            "telegram_configured": bool(settings.telegram_token and settings.telegram_chat_id),
            "webhook_configured": bool(settings.alert_webhook_url),
            "sent": self.sent,
            "failed": self.failed,
            "skipped": self.skipped,
            "queued": self.queue.qsize(),
            "last_error": self.last_error,
        }


dispatcher = AlertDispatcher()
