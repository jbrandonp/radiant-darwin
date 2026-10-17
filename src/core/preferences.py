"""
Shim de rétrocompatibilité pour les préférences utilisateur et keymaps.
Redirige de manière transparente vers src.system.preferences.
"""

from __future__ import annotations
from src.system.preferences import (
    UnitLength,
    CameraNavigationPreset,
    ThemeMode,
    NavigationAction,
    resolve_navigation_press,
    KeymapManager,
    UserPreferences,
    CADPreferences,
    PreferencesManager,
)

__all__ = [
    "UnitLength",
    "CameraNavigationPreset",
    "ThemeMode",
    "NavigationAction",
    "resolve_navigation_press",
    "KeymapManager",
    "UserPreferences",
    "CADPreferences",
    "PreferencesManager",
]
