"""Agent framework primitives: blackboard context, FIPA-ACL style messages, results and proposed actions."""
from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from typing import Any, Callable

from sqlalchemy.orm import Session

from ..models import AgentRequest, Patient, User


@dataclass
class Recommendation:
    title: str
    detail: str = ""
    score: float | None = None
    factors: list[dict] = field(default_factory=list)


@dataclass
class ProposedAction:
    """An effect on the hospital state. Safety-critical actions are gated behind human approval."""

    action_type: str
    title: str
    payload: dict
    agent: str = ""
    risk: str = "low"  # low|medium|high|critical
    category: str = "operations"  # clinical|nursing|pharmacy|operations|staffing (-> approver roles)
    requires_approval: bool = False
    rationale: list[str] = field(default_factory=list)
    description: str = ""


@dataclass
class AgentResult:
    agent: str
    status: str = "success"  # success|partial|failed|skipped
    summary: str = ""
    data: dict = field(default_factory=dict)
    recommendations: list[Recommendation] = field(default_factory=list)
    actions: list[ProposedAction] = field(default_factory=list)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["actions"] = [
            {k: v for k, v in a.items() if k in ("action_type", "title", "risk", "requires_approval", "category", "rationale")}
            for a in d["actions"]
        ]
        return d


class AgentContext:
    """Shared blackboard for one orchestrated request. Agents read each other's findings here."""

    def __init__(self, db: Session, request: AgentRequest, intents: list[str], entities: dict,
                 user: User | None, emit: Callable[..., None]):
        self.db = db
        self.request = request
        self.intents = intents
        self.entities = entities
        self.user = user
        self.blackboard: dict[str, Any] = {}
        self._emit = emit
        self.patient: Patient | None = None

    @property
    def requester_role(self) -> str:
        return self.user.role if self.user else "system"

    @property
    def requester_name(self) -> str:
        return self.user.full_name if self.user else "System"

    def post(self, agent: str, key: str, value: Any) -> None:
        self.blackboard[key] = value
        self._emit("blackboard", agent=agent, title=f"posted '{key}' to shared context")

    def send(self, sender: str, receiver: str, performative: str, content: str) -> None:
        """Inter-agent message (FIPA-ACL performatives: INFORM, REQUEST, PROPOSE, AGREE, REFUSE)."""
        self._emit("message", agent=sender, title=f"{performative} → {receiver}", detail=content,
                   data={"from": sender, "to": receiver, "performative": performative})

    def log(self, agent: str, text: str, data: dict | None = None) -> None:
        self._emit("thought", agent=agent, title=text, data=data)


class BaseAgent:
    key: str = "base"
    name: str = "Base Agent"
    description: str = ""
    capabilities: list[str] = []
    icon: str = "bot"
    color: str = "slate"

    def __init__(self) -> None:
        self.stats = {"tasks": 0, "success": 0, "failed": 0, "total_ms": 0.0}
        self.last_active: float | None = None

    def run(self, action: str, ctx: AgentContext, params: dict | None = None) -> AgentResult:
        handler = getattr(self, f"act_{action}", None)
        if handler is None:
            return AgentResult(agent=self.key, status="failed", summary=f"{self.name} cannot perform '{action}'")
        t0 = time.perf_counter()
        self.stats["tasks"] += 1
        try:
            result: AgentResult = handler(ctx, **(params or {}))
        except Exception as exc:  # an agent failure must never crash the orchestrator
            ctx.db.rollback()
            self.stats["failed"] += 1
            result = AgentResult(agent=self.key, status="failed", summary=f"{self.name} error: {exc}")
        else:
            if result.status in ("success", "partial"):
                self.stats["success"] += 1
            elif result.status == "failed":
                self.stats["failed"] += 1
        for a in result.actions:
            a.agent = a.agent or self.key
        self.stats["total_ms"] += (time.perf_counter() - t0) * 1000
        self.last_active = time.time()
        return result

    def info(self) -> dict:
        tasks = self.stats["tasks"]
        return {
            "key": self.key, "name": self.name, "description": self.description, "capabilities": self.capabilities,
            "icon": self.icon, "color": self.color, "tasks": tasks, "success": self.stats["success"],
            "failed": self.stats["failed"], "avg_ms": round(self.stats["total_ms"] / tasks, 1) if tasks else 0,
            "last_active": self.last_active,
        }
