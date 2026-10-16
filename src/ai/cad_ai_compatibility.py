"""
Module d'interopérabilité et d'adaptation aux protocoles d'Intelligence Artificielle (AI Compatibility Matrix).
Résout les barrières de compatibilité entre CAD Studio et les différents agents/runtimes IA :
Claude Desktop, Cursor IDE, Google Antigravity, OpenAI Function Calling, LangChain, Ollama.
Fournit :
1. AIArgumentAdapter : désérialisation tolérante (JSON stringifié), coercition de type et extraction d'unités (mm, cm, N, kN, deg...).
2. AIParameterAliases : résolution dynamique des synonymes de paramètres (width vs width_mm vs largeur).
3. AICompactSerializer : sérialisation sûre en encodage ASCII/UTF-8 et tronquage respectant la fenêtre de contexte.
4. AIPlatformCompat : fiabilisation des flux STDIO Windows et encodage JSON-RPC.
Architecture 100% fortement typée sans Any ni object.
"""

from __future__ import annotations
import json
import math
import re
import sys
from typing import Dict, List, Optional, Tuple, Union

# Types stricts sans Any ni object
CompatScalar = Union[str, int, float, bool]
CompatSubDict = Dict[str, Union[str, int, float, bool]]
CompatList = List[Union[str, int, float, bool]]
CompatVal = Union[CompatScalar, CompatSubDict, CompatList, None]
CompatDict = Dict[str, CompatVal]


class AIParameterAliases:
    """Répertoire centralisé des alias de paramètres utilisés par les différents LLMs."""

    RESERVED_KEYS = {"name", "method", "id", "jsonrpc", "params", "arguments", "result", "error", "_meta"}

    ALIASES: Dict[str, List[str]] = {
        "target_body_id": ["target_body_id", "target_body", "target"],
        "tool_body_id": ["tool_body_id", "tool_body", "tool_solid", "cutting_body"],
        "body_id": ["body_id", "body", "piece_id", "part_id", "id"],
        "width_mm": ["width_mm", "width", "largeur", "largeur_mm", "w", "dim_x"],
        "length_mm": ["length_mm", "length", "longueur", "longueur_mm", "l", "len", "dim_y"],
        "height_mm": ["height_mm", "height", "hauteur", "hauteur_mm", "h", "dim_z"],
        "depth_mm": ["depth_mm", "depth", "profondeur", "profondeur_mm", "prof"],
        "thickness_mm": ["thickness_mm", "thickness", "epaisseur", "épaisseur", "epaisseur_mm", "t"],
        "flange_height_mm": ["flange_height_mm", "flange_height", "hauteur_rebord", "rebord_mm", "flange"],
        "radius_mm": ["radius_mm", "radius", "rayon", "rayon_mm", "r"],
        "diameter_mm": ["diameter_mm", "diameter", "diametre", "diamètre", "diametre_mm", "d"],
        "applied_force_n": ["applied_force_n", "applied_force", "force_n", "force", "charge", "charge_n", "effort"],
        "material_name": ["material_name", "material", "materiau", "matériau", "matiere", "matière", "mat"],
        "tool_diameter_mm": ["tool_diameter_mm", "tool_diameter", "fraise", "tool_dia", "diametre_outil"],
        "operation_type": ["operation_type", "operation", "type_operation", "op_type", "op"],
        "format_type": ["format_type", "format", "export_format"],
        "offset_mm": ["offset_mm", "offset", "distance_mm", "distance", "decalage"],
        "wall_thickness_mm": ["wall_thickness_mm", "wall_thickness", "epaisseur_paroi"],
        "script": ["script", "code", "python_code", "cmd", "command"],
        "prompt": ["prompt", "instruction", "query", "text", "description"],
        "shape_type": ["shape_type", "shape", "piece_type"],
        "primitive_type": ["primitive_type", "primitive"],
        "dimensions": ["dimensions", "dims"],
        "parameters": ["parameters", "params"],
        "part_name": ["part_name", "part_title", "titre", "nom_piece"],
        "axis": ["axis", "axe", "direction"]
    }

    @classmethod
    def get_canonical_key(cls, key: str) -> str:
        """Retourne la clé canonique correspondant à un alias donné."""
        k_lower = key.strip().lower()
        if k_lower in cls.RESERVED_KEYS:
            return k_lower
        for canonical, aliases in cls.ALIASES.items():
            if k_lower == canonical or k_lower in aliases:
                return canonical
        return k_lower


class AIArgumentAdapter:
    """Adaptateur universel pour les arguments d'outils passés par les modèles d'IA."""

    _UNIT_CONVERSIONS: Dict[str, float] = {
        # Longueurs / distances vers mm
        "mm": 1.0,
        "cm": 10.0,
        "m": 1000.0,
        "in": 25.4,
        "inch": 25.4,
        "inches": 25.4,
        "um": 0.001,
        "µm": 0.001,
        # Forces vers Newtons (N)
        "n": 1.0,
        "kn": 1000.0,
        "mn": 1000000.0,
        "lbf": 4.44822,
        # Angles vers degrés
        "deg": 1.0,
        "degre": 1.0,
        "degré": 1.0,
        "degres": 1.0,
        "degrés": 1.0,
        "°": 1.0,
        "rad": 180.0 / math.pi,
        # Pression / Contraintes vers MPa
        "mpa": 1.0,
        "gpa": 1000.0,
        "kpa": 0.001,
        "bar": 0.1
    }

    @classmethod
    def parse_raw_arguments(cls, raw: Union[str, CompatDict, None]) -> CompatDict:
        """Désérialise les arguments bruts en tolérant les chaînes JSON et blocs Markdown."""
        if raw is None:
            return {}
        if isinstance(raw, dict):
            return cls._normalize_dict(raw)
        if isinstance(raw, str):
            clean_str = raw.strip()
            # Nettoyage des blocs de code Markdown ```json ... ```
            if clean_str.startswith("```"):
                lines = clean_str.splitlines()
                if len(lines) >= 2 and lines[-1].strip() == "```":
                    clean_str = "\n".join(lines[1:-1]).strip()

            try:
                decoded = json.loads(clean_str)
                if isinstance(decoded, dict):
                    return cls._normalize_dict(decoded)
            except (json.JSONDecodeError, ValueError, TypeError):
                return {}

        return {}

    @classmethod
    def _normalize_sub_dict(cls, sub_data: Dict[str, CompatVal]) -> CompatSubDict:
        """Normalise un dictionnaire imbriqué."""
        sub_norm: CompatSubDict = {}
        for sk, sv in sub_data.items():
            if isinstance(sv, (str, int, float, bool)):
                sub_norm[str(sk)] = sv
        return sub_norm

    @classmethod
    def _normalize_list(cls, list_data: List[CompatVal]) -> CompatList:
        """Normalise une liste imbriquée."""
        sub_list: CompatList = []
        for item in list_data:
            if isinstance(item, (str, int, float, bool)):
                sub_list.append(item)
        return sub_list

    @classmethod
    def _normalize_dict(cls, data: Dict[str, CompatVal]) -> CompatDict:
        """Normalise récursivement les clés et types d'un dictionnaire d'arguments."""
        normalized: CompatDict = {}
        for key, val in data.items():
            canon_key = AIParameterAliases.get_canonical_key(key)
            if isinstance(val, dict):
                normalized[canon_key] = cls._normalize_sub_dict(val)
            elif isinstance(val, list):
                normalized[canon_key] = cls._normalize_list(val)
            elif isinstance(val, (str, int, float, bool)):
                normalized[canon_key] = val
        return normalized

    @classmethod
    def get_float(cls, args: CompatDict, canonical_key: str, default: float = 0.0) -> float:
        """Extrait une valeur flottante avec résolution d'alias et extraction d'unités physiques."""
        raw_val = cls._find_value(args, canonical_key)
        if raw_val is None:
            return default
        if isinstance(raw_val, (int, float)):
            return float(raw_val)
        if isinstance(raw_val, bool):
            return 1.0 if raw_val else 0.0
        if isinstance(raw_val, str):
            parsed = cls._parse_numeric_string(raw_val)
            if parsed is not None:
                return parsed
        return default

    @classmethod
    def get_int(cls, args: CompatDict, canonical_key: str, default: int = 0) -> int:
        """Extrait un entier avec tolérance aux chaînes et arrondis."""
        flt_val = cls.get_float(args, canonical_key, default=float(default))
        return int(round(flt_val))

    @classmethod
    def get_str(cls, args: CompatDict, canonical_key: str, default: str = "") -> str:
        """Extrait une chaîne de caractères épurée."""
        raw_val = cls._find_value(args, canonical_key)
        if raw_val is None:
            return default
        if isinstance(raw_val, str):
            return raw_val.strip().strip("\"'")
        if isinstance(raw_val, (int, float, bool)):
            return str(raw_val)
        return default

    @classmethod
    def get_bool(cls, args: CompatDict, canonical_key: str, default: bool = False) -> bool:
        """Extrait un booléen en tolérant 'true', 'false', 'oui', 'non', '1', '0'."""
        raw_val = cls._find_value(args, canonical_key)
        if raw_val is None:
            return default
        if isinstance(raw_val, bool):
            return raw_val
        if isinstance(raw_val, (int, float)):
            return raw_val != 0
        if isinstance(raw_val, str):
            clean = raw_val.strip().lower()
            if clean in ("true", "1", "yes", "oui", "on", "vrai"):
                return True
            if clean in ("false", "0", "no", "non", "off", "faux"):
                return False
        return default

    @classmethod
    def get_sub_dict(cls, args: CompatDict, canonical_key: str) -> CompatSubDict:
        """Extrait un sous-dictionnaire, y compris si passé sous forme de chaîne JSON."""
        raw_val = cls._find_value(args, canonical_key)
        if isinstance(raw_val, dict):
            res: CompatSubDict = {}
            for k, v in raw_val.items():
                if isinstance(v, (str, int, float, bool)):
                    res[str(k)] = v
            return res
        if isinstance(raw_val, str):
            try:
                dec = json.loads(raw_val)
                if isinstance(dec, dict):
                    res = {}
                    for k, v in dec.items():
                        if isinstance(v, (str, int, float, bool)):
                            res[str(k)] = v
                    return res
            except (json.JSONDecodeError, ValueError, TypeError):
                return {}
        return {}

    @classmethod
    def _find_value(cls, args: CompatDict, canonical_key: str) -> CompatVal:
        """Recherche une valeur dans le dictionnaire d'arguments par clé canonique ou alias."""
        if canonical_key in args:
            return args[canonical_key]

        aliases = AIParameterAliases.ALIASES.get(canonical_key, [])
        for alias in aliases:
            if alias in args:
                return args[alias]

        if canonical_key == "target_body_id" and "body_id" in args:
            return args["body_id"]
        if canonical_key == "body_id" and "target_body_id" in args:
            return args["target_body_id"]

        return None

    @classmethod
    def _parse_numeric_string(cls, text: str) -> Optional[float]:
        """Extrait un nombre et applique le facteur de conversion d'unité si présent."""
        cleaned = text.strip().replace(",", ".")
        # Expression régulière pour capturer le nombre et le suffixe d'unité
        match = re.match(r"^([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)\s*([a-zA-Zµ°%]*)$", cleaned)
        if not match:
            # Recherche d'un premier flottant valide dans la chaîne
            sub_match = re.search(r"([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)", cleaned)
            if sub_match:
                try:
                    return float(sub_match.group(1))
                except ValueError:
                    return None
            return None

        num_str = match.group(1)
        unit_str = match.group(2).lower()

        try:
            val = float(num_str)
        except ValueError:
            return None

        if unit_str and unit_str in cls._UNIT_CONVERSIONS:
            val *= cls._UNIT_CONVERSIONS[unit_str]

        return val


class AICompactSerializer:
    """Sérialiseur compact limitant la consommation de contexte des LLMs."""

    @staticmethod
    def compact_text(text: str, max_chars: int = 1500) -> str:
        """Tronque intelligemment un texte verbeux en insérant un indicateur de troncature."""
        if len(text) <= max_chars:
            return text
        half = max_chars // 2
        return text[:half] + "\n\n... [Contenu tronqué pour respecter la fenêtre de contexte IA] ...\n\n" + text[-half:]

    @staticmethod
    def compact_gcode(gcode: str, max_lines: int = 40) -> str:
        """Génère un aperçu concis de programme G-Code."""
        lines = gcode.splitlines()
        if len(lines) <= max_lines:
            return gcode
        header_lines = lines[:20]
        tail_lines = lines[-15:]
        skipped = len(lines) - 35
        return "\n".join(header_lines) + f"\n; ... ({skipped} lignes de trajectoire CNC omises) ...\n" + "\n".join(tail_lines)

    @staticmethod
    def safe_json_rpc_dumps(data: Union[CompatDict, List[CompatVal]], ensure_ascii: bool = True) -> str:
        """Sérialise un payload JSON-RPC en ASCII sécurisé pour immuniser contre les encodages Windows cp1252."""
        return json.dumps(data, ensure_ascii=ensure_ascii)


class AIPlatformCompat:
    """Utilitaires de compatibilité système et terminaux Windows pour l'IA."""

    @staticmethod
    def configure_stdio_utf8() -> bool:
        """Reconfigure stdin et stdout en UTF-8 sous Windows pour éviter les plantages charmap."""
        success = True
        try:
            if hasattr(sys.stdin, "reconfigure"):
                sys.stdin.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            success = False

        try:
            if hasattr(sys.stdout, "reconfigure"):
                sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            success = False

        return success

    @staticmethod
    def format_json_rpc_error(code: int, message: str, req_id: str) -> Dict[str, Union[str, Dict[str, Union[int, str]]]]:
        """Formate une erreur JSON-RPC 2.0 standardisée et conforme MCP."""
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {
                "code": code,
                "message": message
            }
        }
