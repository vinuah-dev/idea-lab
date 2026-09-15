"""Audit logging and notification helpers shared by routers and agents."""
from __future__ import annotations

from sqlalchemy.orm import Session

from ..events import bus
from ..models import AuditLog, Notification


def log_audit(db: Session, actor: str, actor_type: str, action: str, entity: str = "",
              entity_id: int | None = None, details: dict | None = None) -> AuditLog:
    entry = AuditLog(actor=actor, actor_type=actor_type, action=action, entity=entity,
                     entity_id=entity_id, details=details or {})
    db.add(entry)
    return entry


def notify(db: Session, title: str, message: str, level: str = "info", category: str = "general",
           role: str | None = None, user_id: int | None = None, link: str | None = None,
           channel: str = "in-app") -> Notification:
    n = Notification(title=title, message=message, level=level, category=category, role=role,
                     user_id=user_id, link=link, channel=channel)
    db.add(n)
    db.flush()
    bus.publish("notification", {
        "id": n.id, "title": title, "message": message, "level": level, "category": category,
        "role": role, "user_id": user_id, "link": link, "channel": channel, "read": False,
        "created_at": n.created_at.isoformat() if n.created_at else None,
    })
    return n
