"""
Delivery layer. Where a finished ModuleOutput goes. Nothing here posts back to a
source system; the human approval gate is the PX opening the report.

  file      write html, md, and facts json to a directory
  webhook   post the summary and attention list to a Slack or Teams incoming webhook
  email     send the HTML report by SMTP
"""
from __future__ import annotations

import importlib
import json
import pkgutil
import smtplib
import urllib.request
from email.message import EmailMessage
from pathlib import Path
from typing import Protocol

from ..modules import ModuleOutput


class Delivery(Protocol):
    kind: str

    def send(self, output: ModuleOutput) -> str: ...


REGISTRY: dict[str, type] = {}


def register_delivery(kind: str):
    def deco(cls):
        cls.kind = kind
        REGISTRY[kind] = cls
        return cls
    return deco


@register_delivery("file")
class FileDelivery:
    def __init__(self, settings: dict):
        self.dir = Path(settings.get("dir", "out"))

    def send(self, output: ModuleOutput) -> str:
        self.dir.mkdir(parents=True, exist_ok=True)
        (self.dir / f"{output.file_stem}.html").write_text(output.html, encoding="utf-8")
        (self.dir / f"{output.file_stem}.md").write_text(output.markdown, encoding="utf-8")
        (self.dir / f"{output.file_stem}.facts.json").write_text(json.dumps(output.facts, indent=2, default=str), encoding="utf-8")
        return str(self.dir / f"{output.file_stem}.html")


@register_delivery("webhook")
class WebhookDelivery:
    """Slack and Teams incoming webhooks both accept {"text": ...}."""

    def __init__(self, settings: dict):
        self.url = settings["url"]
        self.link = settings.get("report_link", "")

    def send(self, output: ModuleOutput) -> str:
        text = f"*{output.title}*\n{output.summary}"
        if self.link:
            text += f"\n{self.link}"
        req = urllib.request.Request(self.url, data=json.dumps({"text": text}).encode("utf-8"),
                                     headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=30) as resp:
            return f"webhook {resp.status}"


@register_delivery("email")
class EmailDelivery:
    def __init__(self, settings: dict):
        self.host = settings["host"]
        self.port = int(settings.get("port", 587))
        self.user = settings.get("user", "")
        self.password = settings.get("password", "")
        self.sender = settings.get("from", self.user)
        self.to = settings["to"] if isinstance(settings["to"], list) else [settings["to"]]

    def send(self, output: ModuleOutput) -> str:
        msg = EmailMessage()
        msg["Subject"] = output.title
        msg["From"] = self.sender
        msg["To"] = ", ".join(self.to)
        msg.set_content(output.summary)
        msg.add_alternative(output.html, subtype="html")
        with smtplib.SMTP(self.host, self.port, timeout=30) as s:
            s.starttls()
            if self.user:
                s.login(self.user, self.password)
            s.send_message(msg)
        return f"email to {len(self.to)} recipient(s)"


def build(kind: str, settings: dict) -> Delivery:
    if kind not in REGISTRY:
        for m in pkgutil.iter_modules(__path__):
            importlib.import_module(f"{__name__}.{m.name}")
    if kind not in REGISTRY:
        raise KeyError(f"unknown delivery kind '{kind}'. Known: {sorted(REGISTRY)}")
    return REGISTRY[kind](settings)
