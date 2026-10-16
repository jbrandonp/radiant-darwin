"""
Module de Journalisation Transactionnelle et Récupération après Plantage (WAL & Crash Recovery).
Implémente un journal Write-Ahead Log (WAL) incrémental avec détection de plantage (crash detection),
tolérance aux écritures tronquées (torn-write resilience) et restauration automatique du modèle CAO.
Conforme aux standards de sécurité industrielle et typage statique strict (Zero Any).
"""

from __future__ import annotations
import glob
import json
import os
import time
import zlib
from enum import Enum
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Union, TextIO

from src.core.document import CADDocument
from src.core.sketch import Sketch2D
from src.core.feature import Feature
from src.core.serializer import SketchSerializer, ProjectSerializer, FeatureDeserializerRegistry

# Modèle de typage strict pour structures JSON
JSONPrimitive = Union[str, int, float, bool, None]
JSONValue = Union[
    JSONPrimitive,
    List[JSONPrimitive],
    Dict[str, JSONPrimitive],
    List[Dict[str, Union[JSONPrimitive, List[float], List[List[float]]]]],
    Dict[str, Union[JSONPrimitive, List[float], Dict[str, JSONPrimitive]]],
    List[Dict[str, Union[str, float, List[Dict[str, Union[str, bool, int, float, List[List[float]]]]]]]]
]


class JournalOpType(Enum):
    """Types d'opérations unitaires consignées dans le journal transactionnel (WAL)."""
    INIT = "INIT"
    ADD_FEATURE = "ADD_FEATURE"
    REMOVE_FEATURE = "REMOVE_FEATURE"
    MODIFY_PARAMETER = "MODIFY_PARAMETER"
    SET_FEATURE_SUPPRESSED = "SET_FEATURE_SUPPRESSED"
    ADD_SKETCH = "ADD_SKETCH"
    REMOVE_SKETCH = "REMOVE_SKETCH"
    SET_ROLLBACK = "SET_ROLLBACK"
    UNDO = "UNDO"
    REDO = "REDO"
    CHECKPOINT = "CHECKPOINT"
    CLEAN_CLOSE = "CLEAN_CLOSE"


class JournalStatus(Enum):
    """Statut de validité et d'intégrité d'un fichier journal."""
    CLEAN = "CLEAN"
    DIRTY = "DIRTY"
    CORRUPTED = "CORRUPTED"
    MISSING = "MISSING"


@dataclass(frozen=True)
class JournalRecord:
    """Enregistrement unitaire d'une transaction dans le journal."""
    seq: int
    timestamp: float
    op_type: JournalOpType
    payload: Dict[str, JSONValue]
    checksum: str


@dataclass(frozen=True)
class DirtyJournalInfo:
    """Informations sur un journal non finalisé détecté après incident."""
    journal_path: str
    doc_name: str
    base_file: Optional[str]
    last_seq: int
    modified_time: float
    is_corrupted: bool


@dataclass
class RecoveryResult:
    """Résultat complet de la procédure de restauration d'un document."""
    success: bool
    document: Optional[CADDocument] = None
    recovered_operations: int = 0
    base_file: Optional[str] = None
    errors: List[str] = field(default_factory=list)
    torn_write_detected: bool = False


class TransactionJournal:
    """
    Journal transactionnel Write-Ahead Log (WAL) pour documents CAO.
    Écrit de façon synchrone et persistante (fsync) chaque delta d'opération sur disque.
    """

    def __init__(
        self,
        journal_path: str,
        document_name: str = "Untitled Document",
        base_file: Optional[str] = None
    ) -> None:
        self.journal_path: str = journal_path
        self.document_name: str = document_name
        self.base_file: Optional[str] = base_file
        self._seq: int = 0
        self._file_handle: Optional[TextIO] = None
        self._is_closed: bool = False
        self._fsync_supported: bool = True
        self._init_journal()

    def _init_journal(self) -> None:
        """Initialise le fichier journal avec l'en-tête obligatoire INIT."""
        parent_dir = os.path.dirname(self.journal_path)
        if parent_dir and not os.path.exists(parent_dir):
            os.makedirs(parent_dir, exist_ok=True)

        self._file_handle = open(self.journal_path, "w", encoding="utf-8")
        init_payload: Dict[str, JSONValue] = {
            "format_version": "1.0",
            "document_name": self.document_name,
            "base_file": self.base_file,
            "pid": os.getpid(),
        }
        self.append_operation(JournalOpType.INIT, init_payload)

    @staticmethod
    def compute_checksum(payload: Dict[str, JSONValue]) -> str:
        """Calcule une somme de contrôle CRC32 canonique sur la charge utile JSON."""
        canonical_str = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        crc = zlib.crc32(canonical_str.encode("utf-8")) & 0xFFFFFFFF
        return f"{crc:08x}"

    def append_operation(self, op_type: JournalOpType, payload: Dict[str, JSONValue]) -> int:
        """
        Ajoute une entrée unitaire dans le journal avec fsync immédiat.
        Retourne le numéro de séquence assigné.
        """
        if self._is_closed or self._file_handle is None:
            return -1

        current_seq = self._seq
        self._seq += 1
        record_dict: Dict[str, JSONValue] = {
            "seq": current_seq,
            "ts": time.time(),
            "op": op_type.value,
            "payload": payload,
            "checksum": self.compute_checksum(payload),
        }
        serialized_line = json.dumps(record_dict, ensure_ascii=False) + "\n"
        self._file_handle.write(serialized_line)
        self._file_handle.flush()
        try:
            os.fsync(self._file_handle.fileno())
        except (AttributeError, OSError):
            self._fsync_supported = False
        return current_seq

    def record_add_feature(self, feature: Feature) -> int:
        """Consigne l'ajout d'une fonctionnalité 3D."""
        feat_dict = ProjectSerializer._serialize_feature(feature)
        payload: Dict[str, JSONValue] = {"feature": feat_dict}
        return self.append_operation(JournalOpType.ADD_FEATURE, payload)

    def record_remove_feature(self, feature_id: str) -> int:
        """Consigne la suppression d'une fonctionnalité."""
        payload: Dict[str, JSONValue] = {"feature_id": feature_id}
        return self.append_operation(JournalOpType.REMOVE_FEATURE, payload)

    def record_modify_parameter(
        self, feature_id: str, param_name: str, new_value: float, old_value: float
    ) -> int:
        """Consigne la modification d'un paramètre numérique."""
        payload: Dict[str, JSONValue] = {
            "feature_id": feature_id,
            "param_name": param_name,
            "new_value": float(new_value),
            "old_value": float(old_value),
        }
        return self.append_operation(JournalOpType.MODIFY_PARAMETER, payload)

    def record_set_suppressed(self, feature_id: str, suppressed: bool) -> int:
        """Consigne l'activation ou désactivation d'une fonctionnalité."""
        payload: Dict[str, JSONValue] = {
            "feature_id": feature_id,
            "suppressed": bool(suppressed),
        }
        return self.append_operation(JournalOpType.SET_FEATURE_SUPPRESSED, payload)

    def record_add_sketch(self, sketch: Sketch2D) -> int:
        """Consigne l'ajout ou la mise à jour d'une esquisse 2D."""
        sk_dict = SketchSerializer.serialize(sketch)
        payload: Dict[str, JSONValue] = {"sketch": sk_dict}
        return self.append_operation(JournalOpType.ADD_SKETCH, payload)

    def record_remove_sketch(self, sketch_id: str) -> int:
        """Consigne la suppression d'une esquisse."""
        payload: Dict[str, JSONValue] = {"sketch_id": sketch_id}
        return self.append_operation(JournalOpType.REMOVE_SKETCH, payload)

    def record_set_rollback(self, index: int) -> int:
        """Consigne le déplacement du curseur de rollback temporel."""
        payload: Dict[str, JSONValue] = {"index": int(index)}
        return self.append_operation(JournalOpType.SET_ROLLBACK, payload)

    def record_checkpoint(self, saved_file_path: Optional[str] = None) -> int:
        """Consigne un point de contrôle (sauvegarde complète réalisée)."""
        if saved_file_path is not None:
            self.base_file = saved_file_path
        payload: Dict[str, JSONValue] = {
            "saved_file": self.base_file,
            "checkpoint_time": time.time(),
        }
        return self.append_operation(JournalOpType.CHECKPOINT, payload)

    def close(self, clean: bool = True) -> None:
        """Ferme le journal. Si clean est True, écrit CLEAN_CLOSE avant fermeture."""
        if self._is_closed:
            return
        if clean and self._file_handle is not None:
            clean_payload: Dict[str, JSONValue] = {"closed_cleanly": True}
            self.append_operation(JournalOpType.CLEAN_CLOSE, clean_payload)
        if self._file_handle is not None:
            try:
                self._file_handle.close()
            except OSError:
                self._file_handle = None
            self._file_handle = None
        self._is_closed = True


class CrashRecoveryManager:
    """
    Moteur de détection des pannes et restauration des sessions CAO interrompues.
    Analyse les fichiers .journal présents, isole les corruptions de fin de fichier
    et rejoue séquentiellement les transactions valides.
    """

    @classmethod
    def detect_dirty_journals(cls, search_directory: str) -> List[DirtyJournalInfo]:
        """Recherche tous les journaux dirty ou non finalisés dans un dossier."""
        pattern = os.path.join(search_directory, "**", "*.journal")
        found_paths = glob.glob(pattern, recursive=True)
        results: List[DirtyJournalInfo] = []

        for p in found_paths:
            info = cls.inspect_journal_file(p)
            if info is not None:
                results.append(info)

        return results

    @classmethod
    def inspect_journal_file(cls, journal_path: str) -> Optional[DirtyJournalInfo]:
        """Inspecte un journal et détermine s'il correspond à un crash à restaurer."""
        if not os.path.exists(journal_path) or os.path.getsize(journal_path) == 0:
            return None

        records, torn_write, parse_error = cls._read_raw_records(journal_path)
        if len(records) == 0:
            return None

        # Si le journal s'est terminé proprement avec CLEAN_CLOSE, il n'est pas dirty
        last_rec = records[-1]
        if last_rec.op_type == JournalOpType.CLEAN_CLOSE and not torn_write:
            return None

        # Si la dernière action est un CHECKPOINT sans opération postérieure, il est à jour
        if last_rec.op_type == JournalOpType.CHECKPOINT and not torn_write:
            return None

        init_rec = records[0]
        doc_name = str(init_rec.payload.get("document_name", "Document Inconnu"))
        raw_base = init_rec.payload.get("base_file")
        base_file = str(raw_base) if raw_base is not None else None
        mod_time = os.path.getmtime(journal_path)

        return DirtyJournalInfo(
            journal_path=journal_path,
            doc_name=doc_name,
            base_file=base_file,
            last_seq=last_rec.seq,
            modified_time=mod_time,
            is_corrupted=(torn_write or parse_error),
        )

    @classmethod
    def recover_document(cls, journal_path: str) -> RecoveryResult:
        """Restaure un document CAO complet à partir de son journal de transactions."""
        if not os.path.exists(journal_path):
            return RecoveryResult(success=False, errors=[f"Fichier journal introuvable : {journal_path}"])

        records, torn_write, parse_err = cls._read_raw_records(journal_path)
        if len(records) == 0:
            return RecoveryResult(success=False, errors=["Journal vide ou complètement illisible"])

        init_rec = records[0]
        if init_rec.op_type != JournalOpType.INIT:
            return RecoveryResult(success=False, errors=["En-tête INIT manquant dans le journal"])

        doc, base_file = cls._instantiate_base_document(init_rec)
        applied_count = 0
        errors: List[str] = []

        # Rejouer chaque transaction post-INIT
        for rec in records[1:]:
            if rec.op_type in (JournalOpType.CLEAN_CLOSE, JournalOpType.INIT):
                continue
            ok, err_msg = cls._apply_transaction(doc, rec)
            if ok:
                applied_count += 1
            elif err_msg:
                errors.append(err_msg)

        doc.rebuild()
        return RecoveryResult(
            success=True,
            document=doc,
            recovered_operations=applied_count,
            base_file=base_file,
            errors=errors,
            torn_write_detected=torn_write,
        )

    @classmethod
    def _instantiate_base_document(cls, init_rec: JournalRecord) -> Tuple[CADDocument, Optional[str]]:
        """Instancie le document de départ (soit chargé depuis base_file, soit nouveau)."""
        raw_base = init_rec.payload.get("base_file")
        base_file = str(raw_base) if raw_base is not None else None
        doc_name = str(init_rec.payload.get("document_name", "Document Restauré"))

        if base_file and os.path.exists(base_file):
            loaded = ProjectSerializer.load_project(base_file)
            if loaded is not None:
                return loaded, base_file

        return CADDocument(name=doc_name), base_file

    @classmethod
    def _apply_transaction(cls, doc: CADDocument, rec: JournalRecord) -> Tuple[bool, Optional[str]]:
        """Achemine et exécute une transaction delta sur le document en cours de reconstruction."""
        p = rec.payload
        op = rec.op_type

        if op == JournalOpType.ADD_FEATURE:
            return cls._apply_add_feature(doc, p)
        if op == JournalOpType.REMOVE_FEATURE:
            return cls._apply_remove_feature(doc, p)
        if op == JournalOpType.MODIFY_PARAMETER:
            return cls._apply_modify_param(doc, p)
        if op == JournalOpType.SET_FEATURE_SUPPRESSED:
            return cls._apply_set_suppressed(doc, p)
        if op == JournalOpType.ADD_SKETCH:
            return cls._apply_add_sketch(doc, p)
        if op == JournalOpType.REMOVE_SKETCH:
            return cls._apply_remove_sketch(doc, p)
        if op == JournalOpType.SET_ROLLBACK:
            return cls._apply_set_rollback(doc, p)
        if op == JournalOpType.CHECKPOINT:
            return True, None

        return False, f"Opération non prise en charge : {op.value}"

    @staticmethod
    def _apply_add_feature(doc: CADDocument, p: Dict[str, JSONValue]) -> Tuple[bool, Optional[str]]:
        feat_data = p.get("feature")
        if isinstance(feat_data, dict):
            feat = FeatureDeserializerRegistry.deserialize(feat_data)
            if feat is not None:
                feat.is_suppressed = bool(feat_data.get("is_suppressed", False))
                doc.features.append(feat)
                doc.rollback_index = len(doc.features) - 1
                return True, None
        return False, "Données de feature invalides"

    @staticmethod
    def _apply_remove_feature(doc: CADDocument, p: Dict[str, JSONValue]) -> Tuple[bool, Optional[str]]:
        feat_id = p.get("feature_id")
        if feat_id:
            doc.features = [f for f in doc.features if f.feature_id != str(feat_id)]
            if doc.rollback_index >= len(doc.features):
                doc.rollback_index = len(doc.features) - 1
            return True, None
        return False, "Identifiant de feature manquant"

    @staticmethod
    def _apply_modify_param(doc: CADDocument, p: Dict[str, JSONValue]) -> Tuple[bool, Optional[str]]:
        feat_id = p.get("feature_id")
        param_name = p.get("param_name")
        new_val = p.get("new_value")
        if feat_id and param_name and new_val is not None:
            feat = doc.get_feature(str(feat_id))
            if feat is not None:
                feat.parameters[str(param_name)] = float(new_val)
                return True, None
        return False, "Paramètre ou feature introuvable"

    @staticmethod
    def _apply_set_suppressed(doc: CADDocument, p: Dict[str, JSONValue]) -> Tuple[bool, Optional[str]]:
        feat_id = p.get("feature_id")
        supp = p.get("suppressed")
        if feat_id and supp is not None:
            feat = doc.get_feature(str(feat_id))
            if feat is not None:
                feat.is_suppressed = bool(supp)
                return True, None
        return False, "Suppression feature introuvable"

    @staticmethod
    def _apply_add_sketch(doc: CADDocument, p: Dict[str, JSONValue]) -> Tuple[bool, Optional[str]]:
        sk_data = p.get("sketch")
        if isinstance(sk_data, dict):
            sketch = SketchSerializer.deserialize(sk_data)
            if sketch is not None:
                doc.sketches[sketch.sketch_id] = sketch
                return True, None
        return False, "Données d'esquisse invalides"

    @staticmethod
    def _apply_remove_sketch(doc: CADDocument, p: Dict[str, JSONValue]) -> Tuple[bool, Optional[str]]:
        sk_id = p.get("sketch_id")
        if sk_id and str(sk_id) in doc.sketches:
            del doc.sketches[str(sk_id)]
            return True, None
        return False, "Identifiant d'esquisse introuvable"

    @staticmethod
    def _apply_set_rollback(doc: CADDocument, p: Dict[str, JSONValue]) -> Tuple[bool, Optional[str]]:
        raw_idx = p.get("index")
        if raw_idx is not None:
            doc.rollback_index = int(raw_idx)
            return True, None
        return False, "Index de rollback manquant"

    @classmethod
    def _read_raw_records(cls, journal_path: str) -> Tuple[List[JournalRecord], bool, bool]:
        """
        Lit le fichier journal ligne par ligne avec résilience aux écritures tronquées.
        Retourne (enregistrements_valides, torn_write_détecté, parse_error_intermédiaire).
        """
        records: List[JournalRecord] = []
        torn_write = False
        parse_error = False

        with open(journal_path, "r", encoding="utf-8") as f:
            lines = f.readlines()

        total_lines = len(lines)
        for idx, line in enumerate(lines):
            stripped = line.strip()
            if not stripped:
                continue

            rec = cls._parse_single_line(stripped)
            if rec is not None:
                records.append(rec)
            else:
                # Si la dernière ligne est corrompue, c'est un torn-write dû au crash
                if idx == total_lines - 1:
                    torn_write = True
                else:
                    parse_error = True

        return records, torn_write, parse_error

    @classmethod
    def _parse_single_line(cls, line_str: str) -> Optional[JournalRecord]:
        """Valide le format JSON, les champs obligatoires et le checksum d'une ligne de journal."""
        try:
            raw = json.loads(line_str)
            if not isinstance(raw, dict):
                return None

            seq = int(raw["seq"])
            ts = float(raw["ts"])
            op_str = str(raw["op"])
            payload = raw.get("payload")
            checksum = str(raw["checksum"])

            if not isinstance(payload, dict) or op_str not in JournalOpType._value2member_map_:
                return None

            expected_checksum = TransactionJournal.compute_checksum(payload)
            if checksum.lower() != expected_checksum.lower():
                return None

            return JournalRecord(
                seq=seq,
                timestamp=ts,
                op_type=JournalOpType(op_str),
                payload=payload,
                checksum=checksum
            )
        except Exception:
            return None
