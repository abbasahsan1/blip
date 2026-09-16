"""
copyright.py — Copyright Scanning Service

STATUS: NOT IMPLEMENTED.

 (formerly named ProductionCopyrightScanner) raises
NotImplementedError in all environments. The feature flag FEATURE_COPYRIGHT_SCAN_ENABLED
MUST remain False until a real external copyright scanning provider is integrated.

IMPORTANT: Do not describe this as implemented in status reports or documentation.
If the feature flag is ever set to True in production, all audio uploads will fail
with NotImplementedError — this is intentional (fail-closed) rather than silently
passing all content through.

To implement:
  1. Choose a provider (e.g. Audible Magic, ACRCloud, Gracenote).
  2. Implement StubCopyrightScanner.scan_audio() with real API calls.
  3. Remove this docstring's NOT IMPLEMENTED notice.
  4. Update FEATURE_COPYRIGHT_SCAN_ENABLED in environment config.
"""
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
        Raises NotImplementedError if the scanner is not integrated.
        """
        pass

class StubCopyrightScanner(CopyrightScanner):
    """
    Stub implementation — NOT production-ready.

    Formerly called ProductionCopyrightScanner. Renamed to Stub to prevent it from
    being confused with a real implementation. This class intentionally raises
    NotImplementedError rather than faking success, ensuring fail-closed behavior
    if the feature flag is accidentally enabled.

    DO NOT integrate this class with a real provider until external API credentials
    and a proper integration test are in place.
    """
    async def scan_audio(self, audio_url: str, duration_seconds: float) -> bool:
        logger.error(
            "Copyright scanning is NOT implemented. "
            "A real external service integration is required before this can be enabled. "
            "Set FEATURE_COPYRIGHT_SCAN_ENABLED=False to suppress this error."
        )
        raise NotImplementedError(
            "Copyright scanner stub: external service integration is missing. "
            "See services/moderation/app/services/copyright.py for instructions."
        )

class TestCopyrightScanner(CopyrightScanner):
    """
    Test-only implementation. Always clears copyright to allow test fixtures to pass.
    MUST NOT be used in production (use FEATURE_COPYRIGHT_SCAN_ENABLED=False instead).
    """
    async def scan_audio(self, audio_url: str, duration_seconds: float) -> bool:
        logger.warning("Using TEST copyright scanner. Only valid in dev/test environments.")
        return True

def get_copyright_scanner() -> CopyrightScanner:
    """
    Returns the appropriate copyright scanner for the current environment.

    Since copyright scanning is not yet implemented, this always returns
    StubCopyrightScanner regardless of environment. FEATURE_COPYRIGHT_SCAN_ENABLED
    must be False to prevent this from being called in the publish pipeline.
    """
    import os
    env = os.environ.get("ENV", "production").lower()
    if env in ("test", "dev", "development"):
        logger.info("Copyright scanner: using TestCopyrightScanner (dev/test mode)")
        return TestCopyrightScanner()
    logger.warning(
        "Copyright scanner: returning StubCopyrightScanner (NOT implemented). "
        "Ensure FEATURE_COPYRIGHT_SCAN_ENABLED=False in production."
    )
    return StubCopyrightScanner()
