"""
Moteur d'Analyse Comportementale CodeScene SOTA 2026 (Behavioral Code Analysis).
Conforme aux principes d'Adam Tornhill (Your Code as a Crime Scene & Software Design X-Rays)
et aux standards industriels d'architecture logicielle prédictive.

Piliers majeurs implémentés :
1. Calcul du Churn Volumétrique Réel via 'git log --numstat' (lignes ajoutées et supprimées).
2. Décroissance Temporelle Exponentielle par Demi-Vie (Half-Life Decay avec T_1/2 = 90 jours).
3. Détection du Couplage Temporel Masqué (Hidden Temporal Coupling) via l'indice de Jaccard (J >= 0.35)
   sans importation directe dans l'AST.
4. Analyse d'Entropie de Propriété de Shannon (Code Ownership) pour quantifier le risque
   de diffusion de responsabilité sur les Hotspots d'architecture.
"""

from __future__ import annotations

import ast
import json
import math
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple


@dataclass
class AuthorContribution:
    """Contribution volumétrique et temporelle d'un auteur sur un fichier."""
    author_name: str
    author_email: str
    lines_added: int = 0
    lines_deleted: int = 0
    raw_churn: int = 0
    decayed_churn: float = 0.0
    commit_count: int = 0
    decayed_commits: float = 0.0


@dataclass
class CodeOwnershipMetrics:
    """
    Métriques d'entropie de Shannon et de diffusion de responsabilité (Code Ownership).
    Quantifie mathématiquement si la maintenance d'un fichier est unifiée ou fragmentée.
    """
    file_path: str
    authors_count: int
    primary_owner: str
    primary_owner_email: str
    primary_owner_ratio: float      # Fraction de churn détenue par l'auteur principal [0.0 - 1.0]
    shannon_entropy: float          # Entropie de Shannon en bits : H = -sum(p_i * log2(p_i))
    max_possible_entropy: float     # Entropie maximale théorique pour k auteurs : log2(k)
    normalized_entropy: float       # Entropie normalisée : H / log2(k) dans l'intervalle [0.0 - 1.0]
    diffusion_risk_level: str       # "LOW", "MODERATE", "HIGH", "CRITICAL"
    is_diffused: bool               # True si entropie normalisée >= 0.6 et au moins 2 auteurs
    author_distribution: Dict[str, float] = field(default_factory=dict)


@dataclass
class FileBehavioralMetrics:
    """Métriques comportementales et volumétriques complètes d'un fichier source."""
    file_path: str
    lines_added: int = 0
    lines_deleted: int = 0
    raw_volumetric_churn: int = 0
    decayed_volumetric_churn: float = 0.0
    commit_count: int = 0
    decayed_commits: float = 0.0
    first_commit_timestamp: float = 0.0
    latest_commit_timestamp: float = 0.0
    cognitive_complexity: int = 0
    hotspot_index: float = 0.0      # Churn volumétrique pondéré * Complexité cognitive
    hotspot_defect_risk: float = 0.0  # HotspotIndex * (1.0 + NormalizedEntropy)
    ownership: Optional[CodeOwnershipMetrics] = None
    authors: Dict[str, AuthorContribution] = field(default_factory=dict)


@dataclass
class TemporalCouplingPair:
    """
    Couplage temporel entre deux fichiers co-évoluant dans l'historique Git.
    Mesure la probabilité conditionnelle et la similitude de co-modification.
    """
    file_a: str
    file_b: str
    shared_commits: int
    commits_a: int
    commits_b: int
    jaccard_similarity: float       # J = |A inter B| / |A union B|
    coupling_percent_a: float       # |A inter B| / |A| * 100
    coupling_percent_b: float       # |A inter B| / |B| * 100
    has_direct_import: bool         # True si A importe B ou B importe A dans le code
    is_hidden: bool                 # True si J >= seuil et has_direct_import est False


@dataclass
class CommitFileDiff:
    """Modification d'un fichier au sein d'un commit spécifique."""
    file_path: str
    lines_added: int
    lines_deleted: int


@dataclass
class ParsedCommit:
    """Données extraites d'un commit Git."""
    commit_hash: str
    timestamp: float
    author_name: str
    author_email: str
    files: List[CommitFileDiff] = field(default_factory=list)


@dataclass
class BehavioralAnalysisReport:
    """Bilan complet de l'analyse comportementale CodeScene SOTA."""
    total_commits: int
    total_files_analyzed: int
    reference_timestamp: float
    half_life_days: float
    jaccard_threshold: float
    file_metrics: Dict[str, FileBehavioralMetrics]
    top_hotspots: List[FileBehavioralMetrics]
    all_couplings: List[TemporalCouplingPair]
    hidden_couplings: List[TemporalCouplingPair]
    high_risk_ownership_files: List[FileBehavioralMetrics]


class CodeSceneSOTAAnalyzer:
    """
    Moteur d'analyse comportementale avancé intégrant :
    - Numstat Git volumétrique (lignes réelles ajoutées/supprimées)
    - Décroissance exponentielle par demi-vie (T_1/2 = 90 jours)
    - Entropie de Shannon pour la propriété de code (Code Ownership)
    - Couplage temporel masqué basé sur Jaccard (J >= 0.35 sans import statique direct)
    """

    DEFAULT_HALF_LIFE_DAYS: float = 90.0
    DEFAULT_JACCARD_THRESHOLD: float = 0.35
    DEFAULT_MIN_SHARED_COMMITS: int = 2
    MAX_BULK_COMMIT_FILES: int = 150  # Filtrer les commits de masse (ex. reformatage global)

    @staticmethod
    def calculate_half_life_weight(
        commit_timestamp: float,
        reference_timestamp: float,
        half_life_days: float = 90.0
    ) -> float:
        """
        Calcule le coefficient de décroissance exponentielle par demi-vie :
        w(t) = 2^(-delta_t / T_half) = exp(- ln(2) * delta_t / T_half)

        Arguments :
            commit_timestamp : Horodatage UNIX du commit en secondes.
            reference_timestamp : Horodatage UNIX de référence (ex. date d'analyse ou dernier commit).
            half_life_days : Durée de demi-vie en jours (par défaut 90.0 jours).

        Valeurs caractéristiques :
            delta_t = 0 jour   -> w = 1.0 (100% du poids)
            delta_t = 90 jours -> w = 0.5 (50% du poids)
            delta_t = 180 jours -> w = 0.25 (25% du poids)
        """
        delta_seconds = max(0.0, reference_timestamp - commit_timestamp)
        delta_days = delta_seconds / 86400.0
        if half_life_days <= 0.0:
            return 1.0
        weight = math.pow(2.0, -(delta_days / half_life_days))
        return min(1.0, max(0.0, float(weight)))

    @staticmethod
    def calculate_shannon_entropy(
        contributions: Dict[str, float]
    ) -> Tuple[float, float, float, str, float]:
        """
        Calcule l'Entropie de Shannon d'une distribution de contribution entre auteurs :
        H = - sum_{i=1}^k (p_i * log2(p_i))

        Arguments :
            contributions : Dictionnaire associant chaque auteur à son churn (ou nombre de commits).

        Retourne :
            (shannon_entropy, max_entropy, normalized_entropy, primary_owner, primary_owner_share)
            - shannon_entropy : Entropie en bits [0.0 - log2(k)]
            - max_entropy : Entropie maximale théorique log2(k)
            - normalized_entropy : Ratio normalisé dans [0.0 - 1.0] (0 = monopropriété, 1 = diffusion totale)
            - primary_owner : Nom de l'auteur ayant la plus forte proportion
            - primary_owner_share : Fraction de contribution de l'auteur principal [0.0 - 1.0]
        """
        total = sum(contributions.values())
        if total <= 1e-9:
            return 0.0, 0.0, 0.0, "", 1.0

        probabilities: Dict[str, float] = {}
        primary_owner = ""
        max_share = -1.0

        for author, value in contributions.items():
            if value > 0.0:
                p = value / total
                probabilities[author] = p
                if p > max_share:
                    max_share = p
                    primary_owner = author

        k = len(probabilities)
        if k <= 1:
            return 0.0, 0.0, 0.0, primary_owner, 1.0

        shannon_h = 0.0
        for p in probabilities.values():
            if p > 1e-12:
                shannon_h -= p * math.log2(p)

        max_h = math.log2(float(k))
        normalized_h = (shannon_h / max_h) if max_h > 1e-12 else 0.0
        normalized_h = min(1.0, max(0.0, float(normalized_h)))

        return float(shannon_h), float(max_h), normalized_h, primary_owner, float(max_share)

    @classmethod
    def clean_git_path(cls, path_str: str) -> str:
        """
        Normalise un chemin de fichier retourné par 'git log --numstat'.
        Gère les syntaxes de renommage Git (ex. 'src/{old => new}/file.py' ou 'old.py => new.py').
        """
        raw = path_str.strip()
        if " => " in raw:
            if "{" in raw and "}" in raw:
                # Format: dir/{old => new}/file.py
                raw = re.sub(r"\{[^{}]* => ([^{}]*)\}", r"\1", raw).replace("//", "/")
            else:
                # Format: old_file.py => new_file.py
                raw = raw.split(" => ")[-1]
        # Standardisation des séparateurs avec forward slashes pour compatibilité universelle
        return raw.replace("\\", "/").strip()

    @classmethod
    def parse_numstat_log(
        cls,
        raw_log: str,
        src_dir: str = "src",
        reference_timestamp: Optional[float] = None,
        half_life_days: float = 90.0
    ) -> List[ParsedCommit]:
        """
        Parse la sortie brute de 'git log --numstat --format=COMMIT|%H|%at|%an|%ae'.
        Extrait les commits et les deltas volumétriques des fichiers.
        """
        commits: List[ParsedCommit] = []
        current_commit: Optional[ParsedCommit] = None
        norm_src_dir = src_dir.replace("\\", "/").rstrip("/")

        for line in raw_log.splitlines():
            line_str = line.strip()
            if not line_str:
                continue

            if line_str.startswith("COMMIT|"):
                # Sauvegarder le commit précédent s'il existe
                if current_commit is not None:
                    commits.append(current_commit)

                parts = line_str.split("|")
                commit_hash = parts[1] if len(parts) > 1 else ""
                raw_time = float(parts[2]) if len(parts) > 2 and parts[2].isdigit() else time.time()
                author_name = parts[3] if len(parts) > 3 else "Unknown"
                author_email = parts[4] if len(parts) > 4 else ""

                current_commit = ParsedCommit(
                    commit_hash=commit_hash,
                    timestamp=raw_time,
                    author_name=author_name,
                    author_email=author_email,
                    files=[]
                )
                continue

            # Traitement des lignes numstat : '<added>\t<deleted>\t<filepath>'
            if current_commit is not None and "\t" in line:
                tokens = line.split("\t")
                if len(tokens) >= 3:
                    added_str, deleted_str, raw_filepath = tokens[0], tokens[1], tokens[2]
                    # Ignorer les binaires représentés par '-'
                    added = int(added_str) if added_str.isdigit() else 0
                    deleted = int(deleted_str) if deleted_str.isdigit() else 0
                    clean_path = cls.clean_git_path(raw_filepath)

                    # Filtrer selon le répertoire source
                    if norm_src_dir and not clean_path.startswith(norm_src_dir):
                        continue

                    current_commit.files.append(CommitFileDiff(
                        file_path=clean_path,
                        lines_added=added,
                        lines_deleted=deleted
                    ))

        if current_commit is not None:
            commits.append(current_commit)

        return commits

    @classmethod
    def extract_static_imports(cls, src_dir: str = "src") -> Set[Tuple[str, str]]:
        """
        Analyse l'AST de tous les fichiers Python dans 'src_dir' pour extraire les dépendances
        d'importation statiques directes.
        Retourne un ensemble de paires ordonnées (fichier_source, fichier_cible) normalisées.
        """
        direct_imports: Set[Tuple[str, str]] = set()
        norm_src = src_dir.replace("\\", "/").rstrip("/")

        # Table de correspondance module -> chemin normalisé (ex. 'src.core.geometry' -> 'src/core/geometry.py')
        module_to_path: Dict[str, str] = {}
        for root, _, files in os.walk(src_dir):
            for f in files:
                if f.endswith(".py"):
                    full_p = os.path.join(root, f)
                    rel_p = os.path.relpath(full_p, ".").replace("\\", "/")
                    if rel_p.endswith(".py"):
                        mod_name = rel_p[:-3].replace("/", ".")
                        module_to_path[mod_name] = rel_p
                        # Support avec ou sans préfixe src
                        if mod_name.startswith(norm_src + "."):
                            sub_mod = mod_name[len(norm_src) + 1:]
                            module_to_path[sub_mod] = rel_p

        for root, _, files in os.walk(src_dir):
            for f in files:
                if f.endswith(".py"):
                    full_p = os.path.join(root, f)
                    rel_source = os.path.relpath(full_p, ".").replace("\\", "/")
                    try:
                        with open(full_p, "r", encoding="utf-8") as py_file:
                            tree = ast.parse(py_file.read(), filename=full_p)
                        for node in ast.walk(tree):
                            if isinstance(node, ast.Import):
                                for alias in node.names:
                                    target_p = module_to_path.get(alias.name)
                                    if target_p and target_p != rel_source:
                                        direct_imports.add((rel_source, target_p))
                            elif isinstance(node, ast.ImportFrom):
                                mod = node.module or ""
                                target_p = module_to_path.get(mod)
                                if target_p and target_p != rel_source:
                                    direct_imports.add((rel_source, target_p))
                                # Gestion des imports relatifs (ex. 'from .types import ...')
                                elif node.level and node.level > 0:
                                    source_parts = rel_source.split("/")[:-1]
                                    trim_levels = node.level - 1
                                    if trim_levels <= len(source_parts):
                                        base_dir = "/".join(source_parts[:len(source_parts) - trim_levels])
                                        candidate = f"{base_dir}/{mod}.py" if mod else f"{base_dir}.py"
                                        if os.path.exists(candidate):
                                            direct_imports.add((rel_source, candidate))
                    except Exception:
                        pass

        return direct_imports

    @classmethod
    def analyze_git_repository(
        cls,
        src_dir: str = "src",
        repo_dir: str = ".",
        cognitive_complexities: Optional[Dict[str, int]] = None,
        reference_timestamp: Optional[float] = None,
        half_life_days: float = 90.0,
        jaccard_threshold: float = 0.35,
        min_shared_commits: int = 2
    ) -> BehavioralAnalysisReport:
        """
        Exécute l'analyse comportementale complète sur le dépôt Git local.
        """
        # 1. Extraction du log Git numstat
        raw_log = ""
        try:
            cmd = [
                "git", "log",
                "--numstat",
                "--format=COMMIT|%H|%at|%an|%ae"
            ]
            raw_log = subprocess.check_output(
                cmd,
                cwd=repo_dir,
                text=True,
                stderr=subprocess.DEVNULL
            )
        except Exception:
            raw_log = ""

        return cls.analyze_from_log_string(
            raw_log=raw_log,
            src_dir=src_dir,
            cognitive_complexities=cognitive_complexities,
            reference_timestamp=reference_timestamp,
            half_life_days=half_life_days,
            jaccard_threshold=jaccard_threshold,
            min_shared_commits=min_shared_commits
        )

    @classmethod
    def analyze_from_log_string(
        cls,
        raw_log: str,
        src_dir: str = "src",
        cognitive_complexities: Optional[Dict[str, int]] = None,
        reference_timestamp: Optional[float] = None,
        half_life_days: float = 90.0,
        jaccard_threshold: float = 0.35,
        min_shared_commits: int = 2
    ) -> BehavioralAnalysisReport:
        """
        Effectue l'analyse complète à partir d'une chaîne brute de log Git (permet les tests déterministes).
        """
        commits = cls.parse_numstat_log(raw_log, src_dir=src_dir)
        cog_map = cognitive_complexities or {}

        # Déterminer le timestamp de référence (dernier commit ou date courante)
        if reference_timestamp is None:
            if commits:
                reference_timestamp = max(c.timestamp for c in commits)
            else:
                reference_timestamp = time.time()

        # Structures d'accumulation
        file_metrics: Dict[str, FileBehavioralMetrics] = {}
        # Traçabilité des commits par fichier pour l'analyse Jaccard
        file_commits_map: Dict[str, Set[str]] = {}

        for commit in commits:
            # Calcul du poids temporel par demi-vie pour ce commit
            w = cls.calculate_half_life_weight(
                commit.timestamp,
                reference_timestamp,
                half_life_days=half_life_days
            )

            # Ne pas retenir les commits de masse (> MAX_BULK_COMMIT_FILES) pour le couplage temporel
            is_bulk_commit = len(commit.files) > cls.MAX_BULK_COMMIT_FILES

            author_key = f"{commit.author_name} <{commit.author_email}>" if commit.author_email else commit.author_name

            for diff in commit.files:
                fpath = diff.file_path
                vol_churn = diff.lines_added + diff.lines_deleted

                if fpath not in file_metrics:
                    cog = cog_map.get(fpath, cog_map.get(fpath.replace("/", os.sep), 0))
                    file_metrics[fpath] = FileBehavioralMetrics(
                        file_path=fpath,
                        cognitive_complexity=cog,
                        first_commit_timestamp=commit.timestamp,
                        latest_commit_timestamp=commit.timestamp
                    )
                    file_commits_map[fpath] = set()

                fm = file_metrics[fpath]
                fm.lines_added += diff.lines_added
                fm.lines_deleted += diff.lines_deleted
                fm.raw_volumetric_churn += vol_churn
                fm.decayed_volumetric_churn += vol_churn * w
                fm.commit_count += 1
                fm.decayed_commits += 1.0 * w

                if commit.timestamp < fm.first_commit_timestamp:
                    fm.first_commit_timestamp = commit.timestamp
                if commit.timestamp > fm.latest_commit_timestamp:
                    fm.latest_commit_timestamp = commit.timestamp

                if not is_bulk_commit:
                    file_commits_map[fpath].add(commit.commit_hash)

                # Contribution par auteur
                if author_key not in fm.authors:
                    fm.authors[author_key] = AuthorContribution(
                        author_name=commit.author_name,
                        author_email=commit.author_email
                    )
                ac = fm.authors[author_key]
                ac.lines_added += diff.lines_added
                ac.lines_deleted += diff.lines_deleted
                ac.raw_churn += vol_churn
                ac.decayed_churn += vol_churn * w
                ac.commit_count += 1
                ac.decayed_commits += 1.0 * w

        # Calcul de l'entropie de Shannon et des Hotspots
        for fpath, fm in file_metrics.items():
            # Distribution des auteurs basée sur le churn volumétrique pondéré (ou brut si 0)
            author_weights: Dict[str, float] = {}
            for auth_key, ac in fm.authors.items():
                val = ac.decayed_churn if ac.decayed_churn > 0.0 else float(ac.raw_churn)
                if val == 0.0:
                    val = float(ac.commit_count)
                author_weights[auth_key] = val

            shannon_h, max_h, norm_h, primary_owner, owner_share = cls.calculate_shannon_entropy(author_weights)

            # Évaluation du risque de diffusion
            k = len(author_weights)
            if norm_h >= 0.7 and k >= 3:
                risk_lvl = "CRITICAL"
            elif norm_h >= 0.5 and k >= 2:
                risk_lvl = "HIGH"
            elif norm_h >= 0.3:
                risk_lvl = "MODERATE"
            else:
                risk_lvl = "LOW"

            primary_email = fm.authors[primary_owner].author_email if primary_owner in fm.authors else ""

            # Distribution normalisée
            tot_w = sum(author_weights.values())
            dist = {k_auth: (v / tot_w) for k_auth, v in author_weights.items()} if tot_w > 0.0 else {}

            fm.ownership = CodeOwnershipMetrics(
                file_path=fpath,
                authors_count=k,
                primary_owner=primary_owner,
                primary_owner_email=primary_email,
                primary_owner_ratio=owner_share,
                shannon_entropy=shannon_h,
                max_possible_entropy=max_h,
                normalized_entropy=norm_h,
                diffusion_risk_level=risk_lvl,
                is_diffused=(norm_h >= 0.6 and k >= 2),
                author_distribution=dist
            )

            # Hotspot Index = Decayed Churn Volumétrique * Complexité Cognitive
            # (Si la complexité n'est pas encore fournie, elle pourra être injectée plus tard)
            fm.hotspot_index = fm.decayed_volumetric_churn * float(fm.cognitive_complexity)
            # Risque combiné dette technique + diffusion de responsabilité
            fm.hotspot_defect_risk = fm.hotspot_index * (1.0 + norm_h)

        # 3. Détection du Couplage Temporel Masqué via Indice de Jaccard
        direct_imports = cls.extract_static_imports(src_dir=src_dir)

        all_couplings: List[TemporalCouplingPair] = []
        hidden_couplings: List[TemporalCouplingPair] = []

        active_files = sorted(file_commits_map.keys())
        n = len(active_files)

        for i in range(n):
            for j in range(i + 1, n):
                f_a, f_b = active_files[i], active_files[j]
                c_a, c_b = file_commits_map[f_a], file_commits_map[f_b]

                inter_len = len(c_a & c_b)
                if inter_len < min_shared_commits:
                    continue

                union_len = len(c_a | c_b)
                if union_len == 0:
                    continue

                jaccard = float(inter_len) / float(union_len)
                pct_a = (float(inter_len) / float(len(c_a))) * 100.0 if len(c_a) > 0 else 0.0
                pct_b = (float(inter_len) / float(len(c_b))) * 100.0 if len(c_b) > 0 else 0.0

                # Vérifier si un import direct existe entre A et B
                has_import = (
                    (f_a, f_b) in direct_imports
                    or (f_b, f_a) in direct_imports
                    or (f_a.replace("/", os.sep), f_b.replace("/", os.sep)) in direct_imports
                    or (f_b.replace("/", os.sep), f_a.replace("/", os.sep)) in direct_imports
                )

                is_hidden = (jaccard >= jaccard_threshold) and (not has_import)

                pair = TemporalCouplingPair(
                    file_a=f_a,
                    file_b=f_b,
                    shared_commits=inter_len,
                    commits_a=len(c_a),
                    commits_b=len(c_b),
                    jaccard_similarity=jaccard,
                    coupling_percent_a=pct_a,
                    coupling_percent_b=pct_b,
                    has_direct_import=has_import,
                    is_hidden=is_hidden
                )

                if jaccard >= jaccard_threshold:
                    all_couplings.append(pair)
                    if is_hidden:
                        hidden_couplings.append(pair)

        # Tri des résultats
        all_couplings.sort(key=lambda p: p.jaccard_similarity, reverse=True)
        hidden_couplings.sort(key=lambda p: p.jaccard_similarity, reverse=True)

        hotspots = sorted(file_metrics.values(), key=lambda m: m.hotspot_index, reverse=True)
        high_risk_diffusion = [
            m for m in hotspots
            if m.ownership and m.ownership.is_diffused
        ]

        return BehavioralAnalysisReport(
            total_commits=len(commits),
            total_files_analyzed=len(file_metrics),
            reference_timestamp=reference_timestamp,
            half_life_days=half_life_days,
            jaccard_threshold=jaccard_threshold,
            file_metrics=file_metrics,
            top_hotspots=hotspots,
            all_couplings=all_couplings,
            hidden_couplings=hidden_couplings,
            high_risk_ownership_files=high_risk_diffusion
        )

    @classmethod
    def get_git_churn_dict(
        cls,
        src_dir: str = "src",
        repo_dir: str = ".",
        decayed: bool = True
    ) -> Dict[str, int]:
        """
        Méthode de compatibilité directe avec le moteur d'audit industriel existant.
        Retourne un dictionnaire {chemin_fichier: churn_volumétrique}.
        """
        report = cls.analyze_git_repository(src_dir=src_dir, repo_dir=repo_dir)
        result: Dict[str, int] = {}
        for fpath, metrics in report.file_metrics.items():
            # Utilise le churn volumétrique pondéré par demi-vie (ou brut)
            val = int(round(metrics.decayed_volumetric_churn)) if decayed else metrics.raw_volumetric_churn
            result[fpath] = val
            # Support du séparateur natif OS
            result[fpath.replace("/", os.sep)] = val
        return result


def print_codescene_terminal_report(report: BehavioralAnalysisReport) -> None:
    """Affiche un rapport terminal formaté selon les standards CodeScene Enterprise."""
    print("=" * 80)
    print("CODESEN-SOTA 2026 : RAPPORT D'ANALYSE COMPORTEMENTALE & ARCHITECTURELLE")
    print("=" * 80)
    print(f"  Commits Git analysés              : {report.total_commits}")
    print(f"  Fichiers sources suivis           : {report.total_files_analyzed}")
    print(f"  Décroissance temporelle (Demi-Vie): T_1/2 = {report.half_life_days:.0f} jours (Exponentielle)")
    print(f"  Seuil de Couplage Temporel (J)    : Jaccard >= {report.jaccard_threshold:.2f}")

    print("\n" + "-" * 80)
    print("1. TOP 5 ARCHITECTURAL HOTSPOTS (Decayed Churn Volumétrique x Complexité)")
    print("-" * 80)
    for idx, h in enumerate(report.top_hotspots[:5], start=1):
        own = h.ownership
        owner_str = f"{own.primary_owner} ({own.primary_owner_ratio * 100:.0f}%)" if own and own.primary_owner else "N/A"
        entropy_str = f"{own.shannon_entropy:.2f} bits (Norm: {own.normalized_entropy:.2f})" if own else "N/A"
        print(
            f"  {idx}. {h.file_path:35} | Vol Churn: {h.decayed_volumetric_churn:6.1f} L (Raw: {h.raw_volumetric_churn:4d}) | "
            f"Cog: {h.cognitive_complexity:3d} | Hotspot: {h.hotspot_index:7.1f} | Owner: {owner_str} | H: {entropy_str}"
        )

    print("\n" + "-" * 80)
    print("2. COUPLAGE TEMPOREL MASQUÉ (HIDDEN TEMPORAL COUPLING - SANS IMPORT DIRECT)")
    print("-" * 80)
    if report.hidden_couplings:
        print(f"  [ATTENTION] {len(report.hidden_couplings)} couplages temporels masqués identifiés (J >= {report.jaccard_threshold:.2f}) :")
        for idx, c in enumerate(report.hidden_couplings[:8], start=1):
            print(
                f"  {idx}. J={c.jaccard_similarity:.2f} ({c.shared_commits} commits communs) | "
                f"{c.file_a} <====> {c.file_b} [Co-évolution masquée sans import]"
            )
    else:
        print("  [OK] Aucun couplage temporel masqué critique détecté.")

    print("\n" + "-" * 80)
    print("3. ANALYSE D'ENTROPIE DE PROPRIÉTÉ DE SHANNON (CODE OWNERSHIP & DIFFUSION RISK)")
    print("-" * 80)
    diffused_files = [m for m in report.top_hotspots if m.ownership and m.ownership.authors_count > 1]
    if diffused_files:
        for idx, m in enumerate(diffused_files[:5], start=1):
            own = m.ownership
            assert own is not None
            badge = f"[{own.diffusion_risk_level}]"
            print(
                f"  {idx}. {badge:10} {m.file_path:35} | Auteurs: {own.authors_count} | "
                f"Entropie: {own.shannon_entropy:.2f} bits / {own.max_possible_entropy:.2f} (Norm: {own.normalized_entropy:.2f}) | "
                f"Propriétaire: {own.primary_owner} ({own.primary_owner_ratio * 100:.1f}%)"
            )
    else:
        print("  [INFO] Tous les fichiers sont maintenus par un auteur unique (Entropie = 0.00 bits - Monopropriété).")

    print("=" * 80)


if __name__ == "__main__":
    report = CodeSceneSOTAAnalyzer.analyze_git_repository(src_dir="src", repo_dir=".")
    print_codescene_terminal_report(report)
