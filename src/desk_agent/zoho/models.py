from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class ZohoLabel:
    id: str
    name: str
    color: Optional[str] = None
