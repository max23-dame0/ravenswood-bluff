from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ParsedRoleStatement:
    role_id: str
    claim_type: str
    subject_player_ids: tuple[str, ...]
    source_text: str


class Persona:
    """Agent的人格配方"""
    def __init__(
        self,
        description: str,
        speaking_style: str,
        voice_anchor: str = "",
        decision_style: str = "",
        archetype: str = "logic",
    ):
        self.description = description
        self.speaking_style = speaking_style
        self.voice_anchor = voice_anchor
        self.decision_style = decision_style
        self.archetype_key = archetype
