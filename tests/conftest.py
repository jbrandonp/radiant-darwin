"""
Configuration globale pytest et profils de tests par propriétés (Hypothesis).
"""
from __future__ import annotations
import os
import pytest

try:
    from hypothesis import settings, HealthCheck

    settings.register_profile(
        "dev",
        max_examples=15,
        deadline=None,
        suppress_health_check=[HealthCheck.too_slow, HealthCheck.filter_too_much]
    )
    settings.register_profile(
        "ci",
        max_examples=50,
        deadline=None,
        suppress_health_check=[HealthCheck.too_slow, HealthCheck.filter_too_much]
    )
    settings.register_profile(
        "fuzz",
        max_examples=200,
        deadline=None,
        suppress_health_check=[HealthCheck.too_slow, HealthCheck.filter_too_much]
    )

    settings.load_profile(os.getenv("HYPOTHESIS_PROFILE", "dev"))
except ImportError:
    pass
