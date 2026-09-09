"""
Comprehensive unit and integration test suite for Messaging & 24-Hour Audio Stories Microservice (§3 #4, §5.4, §8).
"""
import os
import sys

# Re-export and delegate to services/messaging/tests/test_messaging.py
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../services/messaging/tests")))
from test_messaging import *

if __name__ == "__main__":
    import test_messaging
    test_messaging.__main__()
