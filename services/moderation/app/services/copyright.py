import logging
from typing import Dict, Any
from abc import ABC, abstractmethod

logger = logging.getLogger("moderation.services.copyright")

class CopyrightScanner(ABC):
    @abstractmethod
    async def scan_audio(self, audio_url: str, duration_seconds: float) -> bool:
        """
        Scans audio for copyright infringement.
        Returns True if cleared (no infringement), False if infringed.
        Raises NotImplementedError if the scanner is not available in the current environment.
        """
        pass

class ProductionCopyrightScanner(CopyrightScanner):
    """
    Production implementation for copyright scanning.
    A fake production implementation MUST NOT report success.
    Since we do not have an actual external copyright service integrated yet,
    this intentionally fails.
    """
    async def scan_audio(self, audio_url: str, duration_seconds: float) -> bool:
        logger.error("Production copyright scanning is not implemented. Refusing to fake success.")
        raise NotImplementedError("Production copyright scanner is missing actual external service integration.")

class TestCopyrightScanner(CopyrightScanner):
    """
    Test-only implementation.
    Always clears the copyright to allow test fixtures to pass.
    """
    async def scan_audio(self, audio_url: str, duration_seconds: float) -> bool:
        logger.warning("Using TEST copyright scanner. This should only be seen in DEV/TEST environments.")
        return True

def get_copyright_scanner() -> CopyrightScanner:
    import os
    env = os.environ.get("ENV", "production").lower()
    if env in ("test", "dev", "development"):
        return TestCopyrightScanner()
    return ProductionCopyrightScanner()
