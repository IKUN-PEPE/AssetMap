from typing import Dict, Type

from .base import BaseCollector
from .fofa import FOFACollector
from .hunter import HunterCollector
from .oneforall import OneForAllCollector
from .quake import QuakeCollector
from .zoomeye import ZoomEyeCollector

COLLECTOR_MAP: Dict[str, Type[BaseCollector]] = {
    "fofa": FOFACollector,
    "oneforall": OneForAllCollector,
    "hunter": HunterCollector,
    "zoomeye": ZoomEyeCollector,
    "quake": QuakeCollector,
}


def get_collector(name: str) -> BaseCollector:
    collector_cls = COLLECTOR_MAP.get(name.lower())
    if not collector_cls:
        raise ValueError(f"Unknown collector: {name}")
    return collector_cls()
