"""Hinglish (Romanised Hindi + English) normalisation for the conversational copilot.

Staff in Indian hospitals commonly mix Hindi and English ("ICU mein kitne bed khali hain?").
This rule-based normaliser rewrites common Hindi phrases into English so the intent classifier and
entity extractors work unchanged. Pronouns ("usko", "him") become a marker that the copilot resolves
from conversation context.
"""
from __future__ import annotations

import re

PRONOUN = "__PATIENT__"

_RULES: list[tuple[str, str]] = [
    # questions about capacity / cost
    (r"\b(icu|hdu|ccu|isolation|general ward|ward|pediatric ward)\s+(?:mein|me|main)\s+kitne\s+beds?\s+khali\s+(?:hai|hain|he)\b", r"how many \1 beds are available"),
    (r"\bkitne\s+beds?\s+khali\s+(?:hai|hain|he)\b", "how many beds are available"),
    (r"\bbeds?\s+khali\s+(?:hai|hain|he)\b", "beds available"),
    (r"\bbill\s+kitna\s+(?:hua|hai|he|banega|bana)\b", "what is the bill"),
    (r"\bkitna\s+(?:kharcha|kharch|paisa)\s+(?:hoga|aayega|lagega|hai)\b", "estimate the cost"),
    (r"\b(?:kharcha|kharch)\b", "cost"),
    # clinical complaints
    (r"\b(?:saans|sans|saas)\s+(?:lene\s+)?(?:mein|me)\s+(?:dikkat|takleef|taklif|problem)\b", "breathing difficulty"),
    (r"\b(?:seene|chhati|chati|sine)\s+(?:mein|me)\s+dard\b", "chest pain"),
    (r"\bpet\s+(?:mein|me)\s+dard\b", "abdominal pain"),
    (r"\b(?:sar|sir)\s+(?:mein|me\s+)?dard\b", "headache"),
    (r"\bbukhar\b", "fever"), (r"\bbehosh\b", "unconscious"), (r"\bchakkar\b", "dizziness"), (r"\bulti\b", "vomiting"),
    (r"\bkhoon\s+(?:beh|bah)\s*raha\b", "bleeding heavily"), (r"\bdurghatna\b", "accident"),
    (r"\b(\d{1,3})\s+(?:saal|sal)\s+(?:ka|ki|ke)\b", r"\1 year old"),
    (r"\b(?:aadmi|purush|mard)\b", "man"), (r"\b(?:aurat|mahila)\b", "woman"), (r"\b(?:bachcha|bachha|bacche|baccha)\b", "child"),
    # actions
    (r"\b(?:ko\s+)?(icu|hdu|ccu|cardiac unit|general ward|isolation)\s+(?:mein|me)\s+(?:shift|daalo|dalo|bhejo|le\s*jao|transfer)(?:\s+(?:karo|kar\s*do|kijiye|karna))?\b", r"transfer to \1"),
    (r"\bambulance\s+(?:bhejo|bhej\s*do|chahiye|bulao)\b", "send an ambulance"),
    (r"\b(?:bharti|admit)\s+(?:karo|kar\s*do|karna|kijiye|karein|karen)\b", "admit"),
    (r"\b(?:discharge|chhutti)\s+(?:karo|kar\s*do|de\s*do|dedo|kijiye)\b", "discharge"),
    (r"\bappointment\s+(?:laga\s*do|lagao|book\s+karo|chahiye)\b", "book an appointment"),
    (r"\bbook\s+(?:karo|kar\s*do|kijiye|karna)\b", "book"),
    (r"\b(?:test|jaanch|janch)\s+(?:karao|karwao|kar\s*do|karo|likho)\b", "order test"),
    (r"\bjaanch\b|\bjanch\b", "test"),
    (r"\b(?:dawai|dawaai|dawa)\s+(?:do|de\s*do|likh\s*do|likho)\b", "prescribe"),
    (r"\b(?:dawai|dawaai|dawa|dawaiyan)\b", "medicine"),
    (r"\bbed\s+(?:chahiye|do|dedo|de\s*do)\b", "needs a bed"),
    (r"\bdo\s+(?:aur\s+)?(nurses?|doctors?)\b", r"two more \1"),
    (r"\bteen\s+(?:aur\s+)?(nurses?|doctors?)\b", r"three more \1"),
    (r"\b(nurses?|doctors?)\s+chahiye\b", r"need \1"),
    (r"\bkaun\s+(?:duty|on\s+duty)\s+(?:pe|par)\s+(?:hai|hain)\b", "who is on duty"),
    (r"\bkahan\s+(?:hai|hain|he)\b", "where is"),
    (r"\bkya\s+(?:pending|baaki|baki)\s+(?:hai|hain|he)\b", "what is pending"),
    (r"\b(?:baaki|baki)\b", "pending"),
    # time words
    (r"\bparso\b", "day after tomorrow"), (r"\bkal\b", "tomorrow"), (r"\baaj\b", "today"),
    (r"\bsubah\b", "morning"), (r"\bshaam\b|\bsham\b", "evening"), (r"\bdopahar\b", "afternoon"), (r"\braat\b", "tonight"),
    (r"\b(?:turant|fauran|abhi\s+ke\s+abhi)\b", "immediately"), (r"\bjaldi\b", "urgently"), (r"\babhi\b", "now"),
    # quantity / question words
    (r"\bkitne\b|\bkitni\b", "how many"), (r"\bkitna\b", "how much"), (r"\bkahan\b", "where"), (r"\bkaun\b", "who"),
    (r"\bkhali\b", "available"),
    # pronouns → resolved from conversation context
    (r"\b(?:usko|usse|isko|inko|unko|uska|uski|iska|iski|unka|unki|use)\b", PRONOUN),
    # fillers and grammatical particles
    (r"\b(?:bhai|bhaiya|yaar|ji|zara|please|pls|plz|na|toh|hai|hain|he|ho|hua|karo|kar\s*do|kijiye|chahiye)\b", ""),
    (r"\b(?:ka|ki|ke|ko|mein|main|par|pe|se)\b", ""),
    (r"\baur\b", "and"),
]
_COMPILED = [(re.compile(p, re.I), r) for p, r in _RULES]
_HINDI_MARKERS = re.compile(r"\b(?:hai|hain|karo|kar\s*do|mein|kitne|kitna|khali|chahiye|bhejo|usko|kal|aaj|saal|dard|bukhar|dawai|bharti|jaanch|kahan|kya|baaki|bhai)\b", re.I)


def _baje(m: re.Match) -> str:
    h = int(m.group(1))
    return f"{h} {'am' if 8 <= h <= 11 else 'pm'}"


def normalize(text: str) -> dict:
    """Return {"text": normalised English-ish text, "hinglish": bool, "has_pronoun": bool}."""
    is_hinglish = bool(_HINDI_MARKERS.search(text))
    out = re.sub(r"\b(\d{1,2})\s*baje\b", _baje, text, flags=re.I)
    if is_hinglish:
        for rx, rep in _COMPILED:
            out = rx.sub(rep, out)
    out = re.sub(r"\b(?:him|her|this patient|that patient|same patient|the patient)\b", PRONOUN, out, flags=re.I)
    out = re.sub(r"\s{2,}", " ", out).strip(" ,")
    out = re.sub(r"\s+([?,.!])", r"\1", out)
    return {"text": out, "hinglish": is_hinglish, "has_pronoun": PRONOUN in out}


def resolve_pronoun(text: str, patient_name: str | None) -> str:
    return text.replace(PRONOUN, patient_name or "the patient")
