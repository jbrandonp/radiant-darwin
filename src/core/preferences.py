"""
Module de Gestion des Préférences Utilisateur et du Keymap (Pillar 8 & UI).
Persistance JSON robuste, configuration des unités par défaut (mm, inch, meter),
presets de navigation caméra 3D (Blender, FreeCAD, SolidWorks, Revit),
thèmes d'affichage (dark/light) et raccourcis clavier entièrement configurables.
Conforme aux standards de typage strict et SonarQube (complexité cognitive <= 25).
"""

from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
import json
import os
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple, Union


class UnitLength(str, Enum):
    """Unités de longueur par défaut supportées pour la modélisation CAO."""
    MM = "mm"
    INCH = "inch"
    METER = "m"

    @classmethod
    def from_string(cls, value: str) -> UnitLength:
        """Convertit et normalise une chaîne vers l'énumération UnitLength."""
        val = value.strip().lower()
        if val in ("mm", "millimeter", "millimètre", "millimetre"):
            return cls.MM
        if val in ("in", "inch", "pouce"):
            return cls.INCH
        if val in ("m", "meter", "mètre", "metre"):
            return cls.METER
        raise ValueError(f"Unité de longueur non reconnue : '{value}' (attendus: mm, inch, m)")


class CameraNavigationPreset(str, Enum):
    """Styles de navigation 3D conformes aux standards industriels CAO / DCC."""
    BLENDER = "blender"
    FREECAD = "freecad"
    SOLIDWORKS = "solidworks"
    REVIT = "revit"

    @classmethod
    def from_string(cls, value: str) -> CameraNavigationPreset:
        """Convertit et normalise un preset de navigation."""
        val = value.strip().lower()
        for preset in cls:
            if preset.value == val:
                return preset
        raise ValueError(f"Preset de navigation inconnu : '{value}'")


class ThemeMode(str, Enum):
    """Modes d'apparence de l'interface graphique."""
    DARK = "dark"
    LIGHT = "light"

    @classmethod
    def from_string(cls, value: str) -> ThemeMode:
        """Convertit et normalise un mode de thème."""
        val = value.strip().lower()
        if val in ("dark", "sombre", "noir"):
            return cls.DARK
        if val in ("light", "clair", "blanc"):
            return cls.LIGHT
        raise ValueError(f"Thème d'interface inconnu : '{value}' (attendus: dark, light)")


class NavigationAction(str, Enum):
    """Actions de manipulation de la caméra orbitale 3D."""
    NONE = "none"
    ORBIT = "orbit"
    PAN = "pan"
    ZOOM = "zoom"


def _resolve_blender(button: str, is_shift: bool, is_ctrl: bool, is_alt: bool) -> NavigationAction:
    """Résolution des actions de navigation style Blender (MMB=Orbit, Shift+MMB=Pan, Ctrl+MMB=Zoom)."""
    if button == "middle":
        if is_shift:
            return NavigationAction.PAN
        if is_ctrl:
            return NavigationAction.ZOOM
        return NavigationAction.ORBIT
    if button == "left" and is_alt:
        return NavigationAction.ORBIT
    return NavigationAction.NONE


def _resolve_freecad(button: str, is_shift: bool, is_ctrl: bool, is_alt: bool, is_left_held: bool) -> NavigationAction:
    """Résolution style FreeCAD CAD (MMB=Pan, MMB+LMB ou Shift+RMB=Orbit)."""
    if button == "middle":
        if is_left_held:
            return NavigationAction.ORBIT
        return NavigationAction.PAN
    if button == "right" and is_shift:
        return NavigationAction.ORBIT
    if button == "left" and is_alt:
        return NavigationAction.ORBIT
    return NavigationAction.NONE


def _resolve_solidworks(button: str, is_shift: bool, is_ctrl: bool, is_alt: bool) -> NavigationAction:
    """Résolution style SolidWorks (MMB=Orbit, Ctrl+MMB=Pan, Shift+MMB=Zoom)."""
    if button == "middle":
        if is_ctrl:
            return NavigationAction.PAN
        if is_shift:
            return NavigationAction.ZOOM
        return NavigationAction.ORBIT
    if button == "left" and is_alt:
        return NavigationAction.ORBIT
    return NavigationAction.NONE


def _resolve_revit(button: str, is_shift: bool, is_ctrl: bool, is_alt: bool) -> NavigationAction:
    """Résolution style Autodesk Revit (MMB=Pan, Shift+MMB=Orbit)."""
    if button == "middle":
        if is_shift:
            return NavigationAction.ORBIT
        if is_ctrl:
            return NavigationAction.ZOOM
        return NavigationAction.PAN
    if button == "left" and is_alt:
        return NavigationAction.ORBIT
    return NavigationAction.NONE


def resolve_navigation_press(
    preset: CameraNavigationPreset,
    button: str,
    is_shift: bool = False,
    is_ctrl: bool = False,
    is_alt: bool = False,
    is_left_held: bool = False
) -> NavigationAction:
    """
    Détermine l'action de navigation selon le preset actif et l'état des modificateurs.
    button: 'left', 'middle' ou 'right'.
    """
    btn = button.lower()
    if preset == CameraNavigationPreset.BLENDER:
        return _resolve_blender(btn, is_shift, is_ctrl, is_alt)
    if preset == CameraNavigationPreset.FREECAD:
        return _resolve_freecad(btn, is_shift, is_ctrl, is_alt, is_left_held)
    if preset == CameraNavigationPreset.SOLIDWORKS:
        return _resolve_solidworks(btn, is_shift, is_ctrl, is_alt)
    if preset == CameraNavigationPreset.REVIT:
        return _resolve_revit(btn, is_shift, is_ctrl, is_alt)
    return NavigationAction.NONE


# Table des raccourcis par défaut
DEFAULT_KEYMAP: Dict[str, str] = {
    # Fichier & Configuration
    "file.save": "Ctrl+S",
    "file.open": "Ctrl+O",
    "file.parameters": "Ctrl+P",
    "file.preferences": "Ctrl+,",
    # Modélisation 3D (PartDesign)
    "part.extrude": "E",
    "part.revolve": "R",
    "part.press_pull": "Q",
    "part.fillet": "Ctrl+F",
    "part.chamfer": "Ctrl+Shift+C",
    "part.hole": "H",
    "part.shell": "Shift+S",
    "part.combine": "Ctrl+B",
    # Esquisse 2D
    "sketch.toggle_mode": "Shift+K",
    "sketch.solve": "Ctrl+Return",
    # Inspection & Métrologie
    "inspect.measure": "Ctrl+M",
    "render.studio": "Ctrl+R",
    # Navigation & Viewport
    "view.fit": "F",
    "view.home": "Home",
    "view.shading_cycle": "M",
    "view.toggle_snap": "S",
    "view.toggle_gizmo": "G",
    # Assistant IA
    "ai.palette": "Ctrl+K",
}


class KeymapManager:
    """Gestionnaire de table de raccourcis avec validation et détection de conflits."""

    def __init__(self, keymap: Optional[Dict[str, str]] = None) -> None:
        self._keymap: Dict[str, str] = dict(DEFAULT_KEYMAP)
        if keymap is not None:
            self._keymap.update(keymap)

    def get_shortcut(self, action_id: str) -> Optional[str]:
        """Retourne le raccourci associé à l'action ou None."""
        return self._keymap.get(action_id)

    def set_shortcut(self, action_id: str, shortcut: str) -> bool:
        """Définit un raccourci après normalisation."""
        norm = self.normalize_shortcut(shortcut)
        if not norm:
            return False
        self._keymap[action_id] = norm
        return True

    def remove_shortcut(self, action_id: str) -> bool:
        """Supprime l'assignation d'un raccourci."""
        if action_id in self._keymap:
            del self._keymap[action_id]
            return True
        return False

    def reset_defaults(self) -> None:
        """Rétablit la configuration d'usine des raccourcis."""
        self._keymap = dict(DEFAULT_KEYMAP)

    def get_all(self) -> Dict[str, str]:
        """Retourne une copie intégrale du dictionnaire des raccourcis."""
        return dict(self._keymap)

    def normalize_shortcut(self, shortcut: str) -> str:
        """Normalise une chaîne de raccourci (ex: 'ctrl + s' -> 'Ctrl+S')."""
        clean = shortcut.strip()
        if not clean:
            return ""
        parts = [p.strip() for p in clean.split("+") if p.strip()]
        if not parts:
            return ""
        modifiers: List[str] = []
        key: str = ""
        for p in parts:
            p_upper = p.upper()
            if p_upper in ("CTRL", "CONTROL"):
                modifiers.append("Ctrl")
            elif p_upper == "SHIFT":
                modifiers.append("Shift")
            elif p_upper == "ALT":
                modifiers.append("Alt")
            elif p_upper in ("META", "CMD", "COMMAND", "WIN"):
                modifiers.append("Meta")
            else:
                key = p.capitalize() if len(p) > 1 else p.upper()
        if not key:
            return ""
        sort_order = ["Ctrl", "Alt", "Shift", "Meta"]
        ordered_mods = sorted(
            set(modifiers),
            key=lambda m: sort_order.index(m) if m in sort_order else 99
        )
        return "+".join(ordered_mods + [key])

    def find_conflicts(self, shortcut: str, exclude_action: str = "") -> List[str]:
        """Identifie les actions entrant en collision avec la séquence de touches spécifiée."""
        norm = self.normalize_shortcut(shortcut)
        if not norm:
            return []
        conflicts: List[str] = []
        for action_id, sc in self._keymap.items():
            if action_id != exclude_action and self.normalize_shortcut(sc) == norm:
                conflicts.append(action_id)
        return conflicts


@dataclass
class UserPreferences:
    """Structure de données des préférences persistantes de CAD Studio."""
    unit_length: UnitLength = UnitLength.MM
    navigation_preset: CameraNavigationPreset = CameraNavigationPreset.BLENDER
    theme: ThemeMode = ThemeMode.DARK
    keymap: Dict[str, str] = field(default_factory=lambda: dict(DEFAULT_KEYMAP))
    invert_zoom_wheel: bool = False
    orbit_sensitivity: float = 0.45
    pan_sensitivity: float = 1.0
    auto_save_interval_sec: int = 300
    recent_files_max: int = 10

    def to_dict(self) -> Dict[str, Union[str, bool, float, int, Dict[str, str]]]:
        """Exporte l'état en dictionnaire strictement typé sérialisable en JSON."""
        return {
            "unit_length": self.unit_length.value,
            "navigation_preset": self.navigation_preset.value,
            "theme": self.theme.value,
            "keymap": dict(self.keymap),
            "invert_zoom_wheel": self.invert_zoom_wheel,
            "orbit_sensitivity": float(self.orbit_sensitivity),
            "pan_sensitivity": float(self.pan_sensitivity),
            "auto_save_interval_sec": int(self.auto_save_interval_sec),
            "recent_files_max": int(self.recent_files_max),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Union[str, bool, float, int, Dict[str, str]]]) -> UserPreferences:
        """Instancie UserPreferences à partir d'un dictionnaire typé."""
        unit_val = str(data.get("unit_length", "mm"))
        unit = UnitLength.from_string(unit_val)

        nav_val = str(data.get("navigation_preset", "blender"))
        nav = CameraNavigationPreset.from_string(nav_val)

        theme_val = str(data.get("theme", "dark"))
        theme = ThemeMode.from_string(theme_val)

        raw_keymap = data.get("keymap")
        keymap: Dict[str, str] = dict(DEFAULT_KEYMAP)
        if isinstance(raw_keymap, dict):
            for k, v in raw_keymap.items():
                if isinstance(k, str) and isinstance(v, str):
                    keymap[k] = v

        invert_wheel = bool(data.get("invert_zoom_wheel", False))
        orbit_sens = float(str(data.get("orbit_sensitivity", 0.45)))
        pan_sens = float(str(data.get("pan_sensitivity", 1.0)))
        auto_save = int(str(data.get("auto_save_interval_sec", 300)))
        recent_max = int(str(data.get("recent_files_max", 10)))

        return cls(
            unit_length=unit,
            navigation_preset=nav,
            theme=theme,
            keymap=keymap,
            invert_zoom_wheel=invert_wheel,
            orbit_sensitivity=orbit_sens,
            pan_sensitivity=pan_sens,
            auto_save_interval_sec=auto_save,
            recent_files_max=recent_max,
        )


class PreferencesManager:
    """
    Gestionnaire centralisé de persistance JSON et de distribution des préférences.
    Fournit l'écriture atomique et le pattern Observateur pour la réactivité de l'UI.
    """

    def __init__(self, config_path: Optional[Union[str, Path]] = None) -> None:
        if config_path is None:
            self._config_path: Path = Path.home() / ".radiant_cad" / "preferences.json"
        elif isinstance(config_path, str):
            self._config_path = Path(config_path)
        else:
            self._config_path = config_path

        self._preferences: UserPreferences = UserPreferences()
        self._keymap_mgr: KeymapManager = KeymapManager()
        self._listeners: List[Callable[[UserPreferences], None]] = []
        if self._config_path.exists():
            self.load()

    @property
    def config_path(self) -> Path:
        """Chemin du fichier JSON de configuration."""
        return self._config_path

    @property
    def preferences(self) -> UserPreferences:
        """Préférences en mémoire actuelles."""
        return self._preferences

    @property
    def keymap_manager(self) -> KeymapManager:
        """Gestionnaire de table de raccourcis associé."""
        return self._keymap_mgr

    def add_listener(self, listener: Callable[[UserPreferences], None]) -> None:
        """Enregistre un observateur notifié lors de tout changement."""
        if listener not in self._listeners:
            self._listeners.append(listener)

    def remove_listener(self, listener: Callable[[UserPreferences], None]) -> None:
        """Supprime un observateur enregistré."""
        if listener in self._listeners:
            self._listeners.remove(listener)

    def notify_listeners(self) -> None:
        """Notifie l'ensemble des composants observateurs."""
        for listener in self._listeners:
            try:
                listener(self._preferences)
            except Exception as err:
                print(f"Erreur notification listener préférences : {err}")

    def load(self) -> UserPreferences:
        """Charge les préférences depuis le fichier JSON avec repli automatique."""
        if not self._config_path.exists():
            self._preferences = UserPreferences()
            self._keymap_mgr = KeymapManager(self._preferences.keymap)
            return self._preferences

        try:
            with open(self._config_path, "r", encoding="utf-8") as f:
                content = f.read(10 * 1024 * 1024)
            raw_data = json.loads(content)
            if isinstance(raw_data, dict):
                self._preferences = UserPreferences.from_dict(raw_data)
            else:
                self._preferences = UserPreferences()
        except Exception as err:
            print(f"Avertissement lecture préférences ({err}) : valeurs par défaut utilisées.")
            self._preferences = UserPreferences()

        self._keymap_mgr = KeymapManager(self._preferences.keymap)
        return self._preferences

    def save(self) -> bool:
        """Sauvegarde atomique sur disque (écriture temporaire puis remplacement)."""
        try:
            self._config_path.parent.mkdir(parents=True, exist_ok=True)
            temp_path = self._config_path.with_suffix(".tmp")
            payload = self._preferences.to_dict()
            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2, ensure_ascii=False)
            temp_path.replace(self._config_path)
            return True
        except Exception as err:
            print(f"Erreur écriture atomique préférences : {err}")
            return False

    def update_preferences(self, new_prefs: UserPreferences, auto_save: bool = True) -> None:
        """Met à jour les préférences, resynchronise le keymap, sauvegarde et notifie."""
        self._preferences = new_prefs
        self._keymap_mgr = KeymapManager(new_prefs.keymap)
        if auto_save:
            self.save()
        self.notify_listeners()

    def reset_to_defaults(self, auto_save: bool = True) -> UserPreferences:
        """Rétablit les valeurs par défaut et notifie l'application."""
        default_prefs = UserPreferences()
        self.update_preferences(default_prefs, auto_save=auto_save)
        return default_prefs
