# Copyright Scanning

## Status: NOT IMPLEMENTED

Copyright scanning is explicitly out of scope for the current milestone.

StubCopyrightScanner in services/moderation/app/services/copyright.py raises
NotImplementedError by design (fail-closed). The feature flag
FEATURE_COPYRIGHT_SCAN_ENABLED MUST remain False in all environments.

## What Would Be Required to Implement

1. Select an external provider (e.g. ACRCloud, Audible Magic, Gracenote)
2. Obtain API credentials and a commercial license
3. Implement StubCopyrightScanner.scan_audio() with real provider API calls
4. Write integration tests against the provider's sandbox API
5. Set FEATURE_COPYRIGHT_SCAN_ENABLED=True only after tests pass
6. Update this document and remove the StubCopyrightScanner rename

## Why It Raises NotImplementedError

A fake pass (returning True unconditionally) would silently clear all content for
copyright, creating legal exposure. The fail-closed behavior ensures no content
is published through a fake copyright check if the flag is accidentally enabled.
