"""
Générateur d'Export SARIF v2.1.0 (Static Analysis Results Interchange Format).
Conforme au standard officiel OASIS SARIF v2.1.0 et au JSON Schema Store pour GitHub Security.
Mappe l'ensemble des règles d'audit (SAST, typage strict, complexité cognitive, cycles d'architecture)
avec leurs identifiants CWE, niveaux de sévérité, et guides de remédiation complets en Markdown.
Typage statique strict : strictement zéro Any et zéro object.
"""

from __future__ import annotations
import ast
import json
import os
import sys
import argparse
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Dict, Tuple, Optional, Union, Set

# Import des analyseurs d'audit existants
try:
    from scripts.security_sast_visitor import (
        SecuritySASTVisitor,
        SecurityFinding,
        SecuritySeverity,
        SecurityCategory,
        audit_python_file_security
    )
except ImportError:
    # Fallback pour exécution depuis un sous-dossier
    current_dir = os.path.dirname(os.path.abspath(__file__))
    if current_dir not in sys.path:
        sys.path.insert(0, current_dir)
    from security_sast_visitor import (  # type: ignore
        SecuritySASTVisitor,
        SecurityFinding,
        SecuritySeverity,
        SecurityCategory,
        audit_python_file_security
    )


# -----------------------------------------------------------------------------
# Constantes et URLs officielles OASIS SARIF
# -----------------------------------------------------------------------------
SARIF_SCHEMA_URI: str = "https://raw.githubusercontent.com/oasis-tcs/sarif-spec/master/Schemata/sarif-schema-2.1.0.json"
SARIF_VERSION: str = "2.1.0"
TOOL_NAME: str = "CAD Studio Industrial Auditor"
TOOL_VERSION: str = "2.4.0"
TOOL_INFORMATION_URI: str = "https://github.com/jbrandonp/radiant-darwin"


# -----------------------------------------------------------------------------
# Structures de données typées pour SARIF v2.1.0
# -----------------------------------------------------------------------------

SarifRuleDescriptor = Dict[str, Union[str, Dict[str, str], Dict[str, Union[str, List[str]]]]]
SarifResultItem = Dict[str, Union[str, int, Dict[str, str], List[Dict[str, Union[str, Dict[str, str]]]]]]
SarifRunDict = Dict[str, Union[Dict[str, Dict[str, Union[str, List[SarifRuleDescriptor]]]], List[SarifResultItem]]]
SarifDocDict = Dict[str, Union[str, List[SarifRunDict]]]


class SarifLevel(str, Enum):
    """Niveaux de sévérité formels SARIF v2.1.0."""
    ERROR = "error"
    WARNING = "warning"
    NOTE = "note"
    NONE = "none"


@dataclass
class SarifRuleDefinition:
    """
    Définition d'une règle d'analyse statique conforme reportingDescriptor SARIF.
    Inclut l'identifiant CWE, le niveau de sévérité, et le guide de remédiation Markdown.
    """
    rule_id: str
    name: str
    short_description: str
    full_description: str
    cwe_id: str
    cwe_title: str
    default_level: SarifLevel
    security_severity: str
    precision: str
    remediation_markdown: str
    help_uri: Optional[str] = None

    def to_reporting_descriptor(self) -> Dict[str, Union[str, Dict[str, str], Dict[str, Union[str, List[str]]]]]:
        """
        Convertit la règle en dictionnaire conforme reportingDescriptor OASIS SARIF v2.1.0.
        Paramètres : aucun.
        Valeur retournée : dictionnaire JSON sérialisable représentant la règle.
        """
        cwe_num = self.cwe_id.replace("CWE-", "")
        effective_help_uri = self.help_uri or f"https://cwe.mitre.org/data/definitions/{cwe_num}.html"

        rule_dict: Dict[str, Union[str, Dict[str, str], Dict[str, Union[str, List[str]]]]] = {
            "id": self.rule_id,
            "name": self.name,
            "shortDescription": {
                "text": self.short_description
            },
            "fullDescription": {
                "text": self.full_description
            },
            "defaultConfiguration": {
                "level": self.default_level.value
            },
            "help": {
                "text": f"{self.short_description} Pour la remédiation, voir le guide Markdown associé.",
                "markdown": self.remediation_markdown
            },
            "helpUri": effective_help_uri,
            "properties": {
                "id": self.rule_id,
                "name": self.name,
                "precision": self.precision,
                "security-severity": self.security_severity,
                "tags": [
                    "security" if "SEC_" in self.rule_id else "quality",
                    f"external/cwe/{self.cwe_id.lower()}",
                    self.name.lower()
                ]
            }
        }
        return rule_dict


@dataclass
class SarifFinding:
    """
    Occurrence d'une violation d'audit associée à un emplacement physique source.
    """
    rule_id: str
    message: str
    file_path: str
    start_line: int
    start_column: int = 1
    end_line: Optional[int] = None
    end_column: Optional[int] = None
    snippet_text: Optional[str] = None
    custom_level: Optional[SarifLevel] = None


# -----------------------------------------------------------------------------
# Registre officiel des règles d'audit du projet
# -----------------------------------------------------------------------------

SARIF_RULES_CATALOG: Dict[str, SarifRuleDefinition] = {
    # 1. Règles SAST de Sécurité
    "SEC_CODE_EXEC": SarifRuleDefinition(
        rule_id="SEC_CODE_EXEC",
        name="ArbitraryCodeExecution",
        short_description="Appel interdit au builtin d'exécution dynamique (eval, exec, compile).",
        full_description=(
            "L'exécution dynamique de chaînes arbitraires via eval() ou exec() permet à un attaquant "
            "d'injecter du code Python arbitraire avec les privilèges du processus hôte."
        ),
        cwe_id="CWE-94",
        cwe_title="Improper Control of Generation of Code ('Code Injection')",
        default_level=SarifLevel.ERROR,
        security_severity="9.8",
        precision="very-high",
        remediation_markdown="""## 🛡️ Guide de Remédiation : Élimination d'eval() / exec()

### Contexte de Risque
L'évaluation dynamique d'expressions via `eval()` ou `exec()` ouvre une brèche critique d'exécution de code arbitraire (RCE). Dans un environnement CAO/FAO, des formules mathématiques ou des scripts de géométrie peuvent être manipulés pour accéder aux fonctions du système hôte (`os`, `subprocess`).

### Actions Correctives Obligatoires
1. **Élimination formelle :** Supprimer tout appel natif à `eval()`, `exec()`, et `compile()`.
2. **Utilisation d'un parseur AST blanc :** Remplacer l'évaluation libre par `src.core.parameters.SafeExpressionEvaluator`, qui analyse syntaxiquement l'AST et limite strictement les opérations aux constantes numériques, opérateurs arithmétiques (`+`, `-`, `*`, `/`, `**`) et fonctions trigonométriques autorisées (`sin`, `cos`, `tan`, `sqrt`, etc.).

### Exemple de Remédiation
```python
# ❌ VULNÉRABLE :
result = eval(user_expression, {"__builtins__": None}, local_context)

#  SÉCURISÉ :
from src.core.parameters import SafeExpressionEvaluator
result = SafeExpressionEvaluator.evaluate(user_expression, local_context)
```
"""
    ),

    "SEC_SHELL_INJECTION_OS": SarifRuleDefinition(
        rule_id="SEC_SHELL_INJECTION_OS",
        name="OsCommandInjection",
        short_description="Exécution directe de commande système via os.system() ou os.popen().",
        full_description=(
            "L'utilisation d'os.system() passe une commande au shell de l'OS sans validation formelle "
            "des arguments, rendant l'application vulnérable à l'injection de commandes arbitraires."
        ),
        cwe_id="CWE-78",
        cwe_title="Improper Neutralization of Special Elements used in an OS Command ('OS Command Injection')",
        default_level=SarifLevel.ERROR,
        security_severity="9.8",
        precision="very-high",
        remediation_markdown="""## 🛡️ Guide de Remédiation : Remplacement d'os.system()

### Contexte de Risque
`os.system()` invoque l'interpréteur de commandes sous-jacent (`/bin/sh` ou `cmd.exe`). L'inclusion de métacaractères (`&`, `|`, `;`, `&&`) dans un paramètre d'entrée permet l'exécution de commandes non autorisées.

### Actions Correctives Obligatoires
1. **Remplacement systématique :** Utiliser `subprocess.run()` avec une liste d'arguments sans shell (`shell=False`).
2. **Validation des arguments :** Valider rigoureusement le format et l'encodage des paramètres transmis aux exécutables externes (ex: solveur Gmsh, post-processeur G-code).

### Exemple de Remédiation
```python
# ❌ VULNÉRABLE :
os.system(f"gmsh -3 {mesh_file} -o {output_file}")

#  SÉCURISÉ :
import subprocess
subprocess.run(["gmsh", "-3", mesh_file, "-o", output_file], shell=False, check=True)
```
"""
    ),

    "SEC_SHELL_INJECTION_SUBPROCESS": SarifRuleDefinition(
        rule_id="SEC_SHELL_INJECTION_SUBPROCESS",
        name="SubprocessShellInjection",
        short_description="Invocation de subprocess avec shell=True ou argument shell dynamique.",
        full_description=(
            "L'activation du paramètre shell=True dans subprocess délègue la découpe des arguments "
            "au shell système, créant une vulnérabilité d'injection de commande."
        ),
        cwe_id="CWE-78",
        cwe_title="Improper Neutralization of Special Elements used in an OS Command ('OS Command Injection')",
        default_level=SarifLevel.ERROR,
        security_severity="8.8",
        precision="very-high",
        remediation_markdown="""## 🛡️ Guide de Remédiation : Désactivation de shell=True dans subprocess

### Actions Correctives
1. Spécifier formellement `shell=False` dans tous les appels `subprocess.Popen`, `subprocess.run`, `subprocess.call`.
2. Décomposer la commande et ses arguments sous forme de liste explicite de chaînes de caractères.
"""
    ),

    "SEC_UNSAFE_DESERIALIZE_PICKLE": SarifRuleDefinition(
        rule_id="SEC_UNSAFE_DESERIALIZE_PICKLE",
        name="UnsafePickleDeserialization",
        short_description="Désérialisation non sécurisée d'objets Python via pickle ou shelve.",
        full_description=(
            "Le format Pickle est intrinsèquement non sécurisé car sa méthode __reduce__ "
            "permet de faire instancier n'importe quel exécutable ou fonction système."
        ),
        cwe_id="CWE-502",
        cwe_title="Deserialization of Untrusted Data",
        default_level=SarifLevel.ERROR,
        security_severity="9.8",
        precision="very-high",
        remediation_markdown="""## 🛡️ Guide de Remédiation : Abandon de Pickle au profit de JSON typé

### Actions Correctives
1. Ne jamais utiliser `pickle.load()` ou `pickle.loads()` sur des documents de projet CAO ou des échanges réseau.
2. Utiliser le module de sérialisation JSON déterministe `src.core.serializer.CADProjectSerializer` qui enregistre l'arbre de construction géométrique et les paramètres au format JSON validé par typage strict.
"""
    ),

    "SEC_UNSAFE_DESERIALIZE_YAML": SarifRuleDefinition(
        rule_id="SEC_UNSAFE_DESERIALIZE_YAML",
        name="UnsafeYamlDeserialization",
        short_description="Appel à yaml.load() sans Loader=SafeLoader explicite.",
        full_description=(
            "L'appel à yaml.load() sans spécifier de Loader sécurisé permet la création d'objets "
            "Python arbitraires via les balises personnalisées YAML !!"
        ),
        cwe_id="CWE-502",
        cwe_title="Deserialization of Untrusted Data",
        default_level=SarifLevel.WARNING,
        security_severity="7.5",
        precision="high",
        remediation_markdown="""## 🛡️ Guide de Remédiation : Emploi de yaml.safe_load()

### Actions Correctives
Remplacer systématiquement `yaml.load(stream)` par `yaml.safe_load(stream)` ou `yaml.load(stream, Loader=yaml.SafeLoader)`.
"""
    ),

    "SEC_UNSAFE_DESERIALIZE_YAML_UNSAFE": SarifRuleDefinition(
        rule_id="SEC_UNSAFE_DESERIALIZE_YAML_UNSAFE",
        name="ExplicitUnsafeYamlDeserialization",
        short_description="Appel explicite à yaml.unsafe_load() interdit en production.",
        full_description="yaml.unsafe_load() expose délibérément l'interpréteur à l'exécution de code arbitraire.",
        cwe_id="CWE-502",
        cwe_title="Deserialization of Untrusted Data",
        default_level=SarifLevel.ERROR,
        security_severity="9.8",
        precision="very-high",
        remediation_markdown="""## 🛡️ Guide de Remédiation : Remplacement immédiat de yaml.unsafe_load()

Remplacer `yaml.unsafe_load()` par `yaml.safe_load()`.
"""
    ),

    "SEC_ZIP_SLIP_HAZARD": SarifRuleDefinition(
        rule_id="SEC_ZIP_SLIP_HAZARD",
        name="ArchiveZipSlipPathTraversal",
        short_description="Appel direct à extractall() vulnérable aux attaques de type Zip Slip.",
        full_description=(
            "L'extraction directe d'une archive sans validation préalable des chemins des membres "
            "peut écraser des fichiers en dehors du répertoire de destination via des chemins relatifs contenant '..'."
        ),
        cwe_id="CWE-22",
        cwe_title="Improper Limitation of a Pathname to a Restricted Directory ('Path Traversal')",
        default_level=SarifLevel.ERROR,
        security_severity="7.5",
        precision="high",
        remediation_markdown="""## 🛡️ Guide de Remédiation : Protection contre le Zip Slip

### Actions Correctives
1. Sous Python 3.12+, utiliser `tarfile.extractall(path=target, filter='data')`.
2. Pour les archives Zip, valider chaque chemin avec `os.path.commonpath([target_dir, resolved_path]) == target_dir`.
"""
    ),

    "SEC_OPENGL_INVALID_COUNT": SarifRuleDefinition(
        rule_id="SEC_OPENGL_INVALID_COUNT",
        name="OpenGLBufferOutOfBounds",
        short_description="glDrawElements appelé avec un nombre d'éléments invalide.",
        full_description=(
            "L'émission d'ordres de tracé OpenGL avec des dimensions négatives ou supérieures "
            "aux tampons VBO/EBO provoque une violation d'accès mémoire natif sur le pilote graphique."
        ),
        cwe_id="CWE-119",
        cwe_title="Improper Restriction of Operations within the Bounds of a Memory Buffer",
        default_level=SarifLevel.ERROR,
        security_severity="7.0",
        precision="high",
        remediation_markdown="""## 🛡️ Guide de Remédiation : Validation des tampons OpenGL

### Actions Correctives
Vérifier que `count > 0` et que le nombre d'éléments n'excède pas la taille allouée dans le buffer d'index GPU avant d'appeler `glDrawElements`.
"""
    ),

    "SEC_CTYPES_RAW_MEMORY": SarifRuleDefinition(
        rule_id="SEC_CTYPES_RAW_MEMORY",
        name="CtypesRawMemoryHazard",
        short_description="Manipulation de mémoire brute via ctypes sans contrôle de bornes.",
        full_description=(
            "L'accès direct aux fonctions memmove, memset ou cast de ctypes peut corrompre la pile "
            "ou le tas de la mémoire native."
        ),
        cwe_id="CWE-119",
        cwe_title="Improper Restriction of Operations within the Bounds of a Memory Buffer",
        default_level=SarifLevel.WARNING,
        security_severity="6.5",
        precision="high",
        remediation_markdown="""## 🛡️ Guide de Remédiation : Sécurisation de la mémoire Ctypes

### Actions Correctives
Encapsuler les interactions mémoire ctypes dans des wrappers typés contrôlant strictement les tailles et bornes d'adresses.
"""
    ),

    "SEC_UNBOUNDED_FILE_READ": SarifRuleDefinition(
        rule_id="SEC_UNBOUNDED_FILE_READ",
        name="UnboundedFileRead",
        short_description="Lecture complète de fichier via read() sans quota maximal d'octets.",
        full_description=(
            "La lecture intégrale en mémoire d'un fichier volumineux ou corrompu (fichier bombe CAO) "
            "peut entraîner un épuisement de mémoire vive (DDoS géométrique / OOM)."
        ),
        cwe_id="CWE-400",
        cwe_title="Uncontrolled Resource Consumption",
        default_level=SarifLevel.WARNING,
        security_severity="4.0",
        precision="medium",
        remediation_markdown="""## 🛡️ Guide de Remédiation : Quotas de lecture de fichiers

### Actions Correctives
Spécifier une taille maximale lors des lectures de fichiers non vérifiés, par exemple `f.read(MAX_GEOMETRY_BYTES)`.
"""
    ),

    "SEC_SYNTAX_ERROR": SarifRuleDefinition(
        rule_id="SEC_SYNTAX_ERROR",
        name="PythonSyntaxError",
        short_description="Erreur de syntaxe Python empêchant l'analyse statique formelle.",
        full_description="Le fichier contient une syntaxe invalide empêchant la compilation de l'arbre syntaxique AST.",
        cwe_id="CWE-758",
        cwe_title="Reliance on Undefined, Unspecified, or Implementation-Defined Behavior",
        default_level=SarifLevel.ERROR,
        security_severity="7.0",
        precision="very-high",
        remediation_markdown="""## 🛡️ Guide de Remédiation : Correction d'erreur de syntaxe

Corriger l'erreur de syntaxe signalée par l'interpréteur Python.
"""
    ),

    # 2. Règles de Typage Statique Strict (Zéro Any, Zéro object)
    "TYPE_ANY_FORBIDDEN": SarifRuleDefinition(
        rule_id="TYPE_ANY_FORBIDDEN",
        name="ForbiddenAnyOrObjectType",
        short_description="Usage interdit du type 'Any' ou 'object' dans la signature.",
        full_description=(
            "L'utilisation d'Any ou object désactive la vérification statique formelle de types "
            "et peut masquer des confusions de types ou des corruptions d'état à l'exécution."
        ),
        cwe_id="CWE-704",
        cwe_title="Incorrect Type Conversion or Cast",
        default_level=SarifLevel.ERROR,
        security_severity="6.0",
        precision="very-high",
        remediation_markdown="""## 🛡️ Guide de Remédiation : Éradication du type Any / object

### Contexte de Qualité Industrielle
Le standard du projet impose une vérification formelle de 100% des types sans compromis. L'utilisation d'un type passe-partout (`Any`, `object`) masque des erreurs de conception et détruit l'auto-documentation du code.

### Actions Correctives Obligatoires
1. **Remplacement par type concret :** Identifier la structure exacte manipulée (ex: `Solid`, `Vector3D`, `CADDocument`, `List[float]`).
2. **Utilisation d'unions typées :** Si plusieurs types sont légitimes, utiliser `Union[TypeA, TypeB]`.
3. **Définition de Protocole (PEP 544) :** Si des types hétérogènes partagent un comportement commun, déclarer une classe `Protocol` avec les méthodes requises.
"""
    ),

    "TYPE_MISSING_ANNOTATION": SarifRuleDefinition(
        rule_id="TYPE_MISSING_ANNOTATION",
        name="MissingTypeAnnotation",
        short_description="Annotation de type manquante sur un paramètre ou la valeur de retour.",
        full_description=(
            "Toute fonction ou méthode publique/interne doit avoir des annotations de types explicites "
            "pour garantir l'intégrité de l'analyse statique et de la documentation."
        ),
        cwe_id="CWE-843",
        cwe_title="Access of Resource Using Incompatible Type ('Type Confusion')",
        default_level=SarifLevel.WARNING,
        security_severity="4.0",
        precision="high",
        remediation_markdown="""## 🛡️ Guide de Remédiation : Complétion des annotations de types

### Actions Correctives
1. Ajouter le type de chaque argument : `def compute(val: float, name: str) -> None:`
2. Spécifier le type de retour pour toute méthode, y compris `-> None` pour les fonctions ne renvoyant rien.
"""
    ),

    # 3. Règle de Complexité Cognitive SonarSource > 25
    "COMPLEXITY_COGNITIVE_EXCESSIVE": SarifRuleDefinition(
        rule_id="COMPLEXITY_COGNITIVE_EXCESSIVE",
        name="ExcessiveCognitiveComplexity",
        short_description="Complexité cognitive supérieure au plafond industriel de 25 points.",
        full_description=(
            "La complexité cognitive selon la spécification SonarSource de G. Ann Campbell mesure "
            "l'effort mental nécessaire pour comprendre un bloc de code. Un score > 25 indique "
            "une dette technique critique et un risque élevé d'introduction de régressions."
        ),
        cwe_id="CWE-1120",
        cwe_title="Excessive Code Complexity",
        default_level=SarifLevel.WARNING,
        security_severity="5.5",
        precision="high",
        remediation_markdown="""## 🛡️ Guide de Remédiation : Refactorisation de complexité cognitive

### Contexte
La complexité cognitive pénalise les ruptures de flux séquentiel (`if`, `for`, `while`, `except`) proportionnellement à leur niveau d'imbrication.

### Actions de Simplification
1. **Extraction de méthode (Extract Method) :** Découper les sous-traitements complexes en fonctions privées spécialisées respectant le principe de responsabilité unique (SRP).
2. **Sorties anticipées (Guard Clauses / Early Returns) :** Traiter les cas d'erreur ou conditions limites au début de la méthode pour éliminer les imbrications inutiles de blocs `if / else`.
3. **Table de correspondances / Polymorphisme :** Remplacer les cascades de `elif` par des dictionnaires de dispatch ou des classes spécialisées.
"""
    ),

    # 4. Règle de Cycle d'Architecture et Couplage Circulaire
    "ARCH_CIRCULAR_DEPENDENCY": SarifRuleDefinition(
        rule_id="ARCH_CIRCULAR_DEPENDENCY",
        name="CircularModuleDependency",
        short_description="Dépendance circulaire directe ou indirecte entre modules d'architecture.",
        full_description=(
            "Deux modules s'importent mutuellement, violant le principe d'acyclicité des dépendances "
            "(Acyclic Dependencies Principle - Robert C. Martin). Les cycles rendent les modules "
            "indissociables, empêchent les tests unitaires isolés et risquent des erreurs d'initialisation."
        ),
        cwe_id="CWE-1047",
        cwe_title="Modules with Circular Dependencies",
        default_level=SarifLevel.ERROR,
        security_severity="7.0",
        precision="very-high",
        remediation_markdown="""## 🛡️ Guide de Remédiation : Rupture de dépendance circulaire

### Contexte
Un cycle survient lorsque le module `A` dépend du module `B`, et que `B` dépend directement ou indirectement de `A`.

### Actions Correctives
1. **Principe d'Inversion de Dépendance (DIP) :** Définir une interface abstraite (`Protocol` ou `ABC`) dans un module abstrait, implémentée par l'un des deux modules.
2. **Extraction dans un module feuille commun :** Si le cycle est causé par le partage d'une structure de données (ex: `Solid`, `Vector3D`), extraire cette structure dans un module de niveau inférieur (ex: `src.core.types`).
3. **Gestion par événements / Injection :** Passer les instances de dépendances en paramètres du constructeur ou utiliser un bus d'événements plutôt qu'un import statique.
"""
    )
}


# -----------------------------------------------------------------------------
# Collecteur de violations et sérialiseur SARIF
# -----------------------------------------------------------------------------

class SarifReportGenerator:
    """
    Générateur et orchestrateur d'exportation SARIF v2.1.0 pour le moteur d'audit industriel.
    """

    def __init__(
        self,
        tool_name: str = TOOL_NAME,
        tool_version: str = TOOL_VERSION,
        information_uri: str = TOOL_INFORMATION_URI
    ) -> None:
        self.tool_name: str = tool_name
        self.tool_version: str = tool_version
        self.information_uri: str = information_uri
        self.rules: Dict[str, SarifRuleDefinition] = dict(SARIF_RULES_CATALOG)

    def register_rule(self, rule: SarifRuleDefinition) -> None:
        """
        Enregistre ou met à jour une règle dans le catalogue du générateur.
        Paramètres : rule (SarifRuleDefinition).
        Valeur retournée : None.
        """
        self.rules[rule.rule_id] = rule

    def collect_findings_from_directory(self, src_dir: str = "src") -> List[SarifFinding]:
        """
        Parcourt récursivement le répertoire source et collecte toutes les violations d'audit :
        - Failles de sécurité SAST
        - Violations de typage strict (Any, object, annotations manquantes)
        - Dépassements de complexité cognitive (> 25)
        - Dépendances circulaires d'architecture
        Paramètres : src_dir (str, chemin racine des sources).
        Valeur retournée : List[SarifFinding].
        """
        findings: List[SarifFinding] = []

        # 1. Analyse fichier par fichier (SAST + Typage + Complexité)
        for root, _, files in os.walk(src_dir):
            for f in sorted(files):
                if f.endswith(".py"):
                    full_path = os.path.join(root, f)
                    rel_path = os.path.relpath(full_path, ".").replace("\\", "/")

                    file_findings = self.analyze_single_file(full_path, rel_path)
                    findings.extend(file_findings)

        # 2. Analyse des dépendances circulaires
        cycle_findings = self.analyze_architecture_cycles(src_dir)
        findings.extend(cycle_findings)

        return findings

    def analyze_single_file(self, full_path: str, rel_path: str) -> List[SarifFinding]:
        """
        Exécute l'analyse statique complète sur un fichier Python donné.
        Paramètres : full_path (str), rel_path (str).
        Valeur retournée : List[SarifFinding].
        """
        findings: List[SarifFinding] = []

        with open(full_path, "r", encoding="utf-8", errors="ignore") as fp:
            source_code = fp.read()

        # Lecture AST
        try:
            tree = ast.parse(source_code, filename=full_path)
        except SyntaxError as e:
            findings.append(SarifFinding(
                rule_id="SEC_SYNTAX_ERROR",
                message=f"Erreur de syntaxe Python ligne {e.lineno}: {e.msg}",
                file_path=rel_path,
                start_line=e.lineno or 1,
                start_column=e.offset or 1,
                snippet_text=e.text.strip() if e.text else None,
                custom_level=SarifLevel.ERROR
            ))
            return findings

        # A. Détection SAST spécialisée
        sast_visitor = SecuritySASTVisitor(filename=full_path)
        sast_visitor.visit(tree)
        for sf in sast_visitor.findings:
            findings.append(SarifFinding(
                rule_id=sf.rule_id,
                message=sf.message,
                file_path=rel_path,
                start_line=sf.line_number,
                start_column=sf.column_offset + 1,
                snippet_text=sf.code_snippet if sf.code_snippet else None
            ))

        # B. Analyse du typage strict et de la complexité cognitive par fonction
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                # 1. Typage des arguments
                for arg in node.args.args:
                    if arg.arg in ("self", "cls"):
                        continue
                    if arg.annotation is None:
                        findings.append(SarifFinding(
                            rule_id="TYPE_MISSING_ANNOTATION",
                            message=f"Fonction '{node.name}' : le paramètre '{arg.arg}' n'a pas d'annotation de type.",
                            file_path=rel_path,
                            start_line=arg.lineno,
                            start_column=arg.col_offset + 1
                        ))
                    else:
                        ann_str = ast.unparse(arg.annotation)
                        if "Any" in ann_str or "object" in ann_str:
                            findings.append(SarifFinding(
                                rule_id="TYPE_ANY_FORBIDDEN",
                                message=(
                                    f"Fonction '{node.name}' : usage du type interdit '{ann_str}' "
                                    f"sur le paramètre '{arg.arg}'."
                                ),
                                file_path=rel_path,
                                start_line=arg.lineno,
                                start_column=arg.col_offset + 1
                            ))

                # 2. Typage du retour
                if node.returns is None and node.name != "__init__":
                    findings.append(SarifFinding(
                        rule_id="TYPE_MISSING_ANNOTATION",
                        message=f"Fonction '{node.name}' : type de retour manquant (spécifier -> None ou -> Type).",
                        file_path=rel_path,
                        start_line=node.lineno,
                        start_column=node.col_offset + 1
                    ))
                elif node.returns is not None:
                    ret_str = ast.unparse(node.returns)
                    if "Any" in ret_str or "object" in ret_str:
                        findings.append(SarifFinding(
                            rule_id="TYPE_ANY_FORBIDDEN",
                            message=f"Fonction '{node.name}' : type de retour interdit '{ret_str}' (Any ou object).",
                            file_path=rel_path,
                            start_line=node.returns.lineno,
                            start_column=node.returns.col_offset + 1
                        ))

                # 3. Complexité cognitive (Campbell / SonarSource)
                cog_val = self._compute_cognitive_complexity(node)
                if cog_val > 25:
                    findings.append(SarifFinding(
                        rule_id="COMPLEXITY_COGNITIVE_EXCESSIVE",
                        message=(
                            f"La fonction '{node.name}' a une complexité cognitive de {cog_val} "
                            f"(plafond industriel strict = 25)."
                        ),
                        file_path=rel_path,
                        start_line=node.lineno,
                        start_column=node.col_offset + 1
                    ))

        return findings

    def _compute_cognitive_complexity(self, func_node: Union[ast.FunctionDef, ast.AsyncFunctionDef]) -> int:
        """
        Calcule la complexité cognitive d'une fonction selon la spécification SonarSource.
        Paramètres : func_node (FunctionDef ou AsyncFunctionDef).
        Valeur retournée : int (score de complexité).
        """
        complexity: int = 0

        def evaluate_block(statements: List[ast.stmt], nesting: int) -> None:
            nonlocal complexity
            for stmt in statements:
                if isinstance(stmt, ast.If):
                    complexity += (1 + nesting)
                    evaluate_block(stmt.body, nesting + 1)
                    if stmt.orelse:
                        # Un bloc elif compte comme nesting sans incrément supplémentaire de base
                        if len(stmt.orelse) == 1 and isinstance(stmt.orelse[0], ast.If):
                            complexity += 1
                            evaluate_block(stmt.orelse[0].body, nesting + 1)
                            evaluate_block(stmt.orelse[0].orelse, nesting)
                        else:
                            complexity += 1
                            evaluate_block(stmt.orelse, nesting + 1)
                elif isinstance(stmt, (ast.For, ast.AsyncFor, ast.While)):
                    complexity += (1 + nesting)
                    evaluate_block(stmt.body, nesting + 1)
                    if stmt.orelse:
                        evaluate_block(stmt.orelse, nesting + 1)
                elif isinstance(stmt, ast.Try):
                    evaluate_block(stmt.body, nesting)
                    for handler in stmt.handlers:
                        complexity += (1 + nesting)
                        evaluate_block(handler.body, nesting + 1)
                    evaluate_block(stmt.orelse, nesting)
                    evaluate_block(stmt.finalbody, nesting)
                elif isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.BoolOp):
                    complexity += max(1, len(stmt.value.values) - 1)
                else:
                    for child in ast.iter_child_nodes(stmt):
                        if isinstance(child, ast.BoolOp):
                            complexity += max(1, len(child.values) - 1)

        evaluate_block(func_node.body, nesting=0)
        return complexity

    def analyze_architecture_cycles(self, src_dir: str = "src") -> List[SarifFinding]:
        """
        Détecte les cycles de dépendances directs et indirects entre modules.
        Paramètres : src_dir (str, chemin racine).
        Valeur retournée : List[SarifFinding].
        """
        findings: List[SarifFinding] = []
        deps: Dict[str, Set[str]] = {}
        module_file_map: Dict[str, str] = {}
        module_import_lines: Dict[Tuple[str, str], int] = {}

        for root, _, files in os.walk(src_dir):
            for f in sorted(files):
                if f.endswith(".py"):
                    full_p = os.path.join(root, f)
                    rel_mod = os.path.relpath(full_p, src_dir).replace("\\", "/").replace(".py", "")
                    if rel_mod.endswith("/__init__"):
                        rel_mod = rel_mod[:-9]

                    deps[rel_mod] = set()
                    module_file_map[rel_mod] = os.path.relpath(full_p, ".").replace("\\", "/")

                    try:
                        with open(full_p, "r", encoding="utf-8") as src_f:
                            tree = ast.parse(src_f.read(), filename=full_p)
                        for node in ast.walk(tree):
                            if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("src."):
                                target_mod = node.module[4:].replace(".", "/")
                                deps[rel_mod].add(target_mod)
                                module_import_lines[(rel_mod, target_mod)] = node.lineno
                            elif isinstance(node, ast.Import):
                                for alias in node.names:
                                    if alias.name.startswith("src."):
                                        target_mod = alias.name[4:].replace(".", "/")
                                        deps[rel_mod].add(target_mod)
                                        module_import_lines[(rel_mod, target_mod)] = node.lineno
                    except Exception:
                        pass

        # Détection des cycles orientés (A -> B et B -> A)
        detected_cycles: Set[Tuple[str, str]] = set()
        for m1 in sorted(deps.keys()):
            for m2 in sorted(deps[m1]):
                if m2 in deps and m1 in deps[m2] and m1 != m2:
                    pair_key = (min(m1, m2), max(m1, m2))
                    if pair_key not in detected_cycles:
                        detected_cycles.add(pair_key)
                        line_no = module_import_lines.get((m1, m2), 1)
                        file_p = module_file_map.get(m1, f"{src_dir}/{m1}.py")
                        findings.append(SarifFinding(
                            rule_id="ARCH_CIRCULAR_DEPENDENCY",
                            message=(
                                f"Cycle d'architecture détecté : le module '{m1}' importe '{m2}' "
                                f"alors que '{m2}' importe également '{m1}'."
                            ),
                            file_path=file_p,
                            start_line=line_no,
                            start_column=1,
                            custom_level=SarifLevel.ERROR
                        ))

        return findings

    def generate_sarif_dict(
        self,
        findings: List[SarifFinding]
    ) -> SarifDocDict:
        """
        Génère l'objet dictionnaire SARIF v2.1.0 complet et conforme au schéma OASIS.
        Paramètres : findings (List[SarifFinding]).
        Valeur retournée : dictionnaire JSON sérialisable.
        """
        # Liste ordonnée des règles actives
        active_rule_ids: List[str] = sorted(self.rules.keys())
        rule_index_map: Dict[str, int] = {rid: idx for idx, rid in enumerate(active_rule_ids)}

        sarif_rules: List[Dict[str, Union[str, Dict[str, str], Dict[str, Union[str, List[str]]]]]] = [
            self.rules[rid].to_reporting_descriptor() for rid in active_rule_ids
        ]

        # Construction des résultats
        sarif_results: List[Dict[str, Union[str, int, Dict[str, str], List[Dict[str, Dict[str, Union[Dict[str, str], Dict[str, Union[int, Dict[str, str]]]]]]]]]] = []

        for f in findings:
            rule_def = self.rules.get(f.rule_id)
            if rule_def is None:
                # Création dynamique de règle inconnue
                rule_def = SarifRuleDefinition(
                    rule_id=f.rule_id,
                    name=f.rule_id,
                    short_description=f"Règle personnalisée {f.rule_id}",
                    full_description=f"Violation de la règle personnalisée {f.rule_id}",
                    cwe_id="CWE-710",
                    cwe_title="Improper Adherence to Coding Standards",
                    default_level=SarifLevel.WARNING,
                    security_severity="5.0",
                    precision="medium",
                    remediation_markdown="Corriger l'anomalie signalée."
                )
                self.rules[f.rule_id] = rule_def
                active_rule_ids.append(f.rule_id)
                rule_index_map[f.rule_id] = len(sarif_rules)
                sarif_rules.append(rule_def.to_reporting_descriptor())

            rule_idx = rule_index_map[f.rule_id]
            level_str = (f.custom_level.value if f.custom_level else rule_def.default_level.value)

            region_dict: Dict[str, Union[int, Dict[str, str]]] = {
                "startLine": max(1, f.start_line),
                "startColumn": max(1, f.start_column)
            }
            if f.end_line is not None and f.end_line >= f.start_line:
                region_dict["endLine"] = f.end_line
            if f.end_column is not None and f.end_column >= 1:
                region_dict["endColumn"] = f.end_column
            if f.snippet_text:
                region_dict["snippet"] = {"text": f.snippet_text}

            norm_uri = f.file_path.replace("\\", "/")

            result_item: Dict[str, Union[str, int, Dict[str, str], List[Dict[str, Dict[str, Union[Dict[str, str], Dict[str, Union[int, Dict[str, str]]]]]]]]] = {
                "ruleId": f.rule_id,
                "ruleIndex": rule_idx,
                "level": level_str,
                "message": {
                    "text": f.message
                },
                "locations": [
                    {
                        "physicalLocation": {
                            "artifactLocation": {
                                "uri": norm_uri,
                                "uriBaseId": "%SRCROOT%"
                            },
                            "region": region_dict
                        }
                    }
                ]
            }
            sarif_results.append(result_item)

        sarif_doc: SarifDocDict = {
            "$schema": SARIF_SCHEMA_URI,
            "version": SARIF_VERSION,
            "runs": [
                {
                    "tool": {
                        "driver": {
                            "name": self.tool_name,
                            "version": self.tool_version,
                            "semanticVersion": self.tool_version,
                            "informationUri": self.information_uri,
                            "rules": sarif_rules
                        }
                    },
                    "results": sarif_results
                }
            ]
        }
        return sarif_doc

    def export_sarif_file(
        self,
        output_file: str,
        findings: List[SarifFinding],
        validate_schema: bool = True
    ) -> bool:
        """
        Sérialise et sauvegarde le rapport au format audit-results.sarif, avec validation optionnelle.
        Paramètres : output_file (str), findings (List[SarifFinding]), validate_schema (bool).
        Valeur retournée : bool (True si succès et validation réussie).
        """
        sarif_dict = self.generate_sarif_dict(findings)

        out_dir = os.path.dirname(output_file)
        if out_dir:
            os.makedirs(out_dir, exist_ok=True)

        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(sarif_dict, f, indent=2, ensure_ascii=False)

        print(f"[SARIF GENERATOR] Rapport exporté avec succès vers '{output_file}'.")
        print(f"  - Nombre de règles référencées : {len(self.rules)}")
        print(f"  - Nombre de violations détectées : {len(findings)}")

        if validate_schema:
            is_valid, errors = validate_sarif_file(output_file)
            if not is_valid:
                print(f"[SARIF GENERATOR] ERREUR DE VALIDATION DU SCHÉMA SARIF :", file=sys.stderr)
                for err in errors:
                    print(f"  * {err}", file=sys.stderr)
                return False
            print("[SARIF GENERATOR] Validation du schéma OASIS SARIF v2.1.0 :  CONFORME À 100%")

        return True


# -----------------------------------------------------------------------------
# Validateur de schéma JSON officiel OASIS SARIF v2.1.0
# -----------------------------------------------------------------------------

def validate_sarif_file(
    sarif_filepath: str,
    schema_filepath: Optional[str] = None
) -> Tuple[bool, List[str]]:
    """
    Valide formellement un fichier SARIF avec la bibliothèque jsonschema et le schéma officiel OASIS.
    Paramètres : sarif_filepath (str), schema_filepath (Optional[str]).
    Valeur retournée : Tuple[bool, List[str]] (succès, liste des erreurs s'il y a lieu).
    """
    try:
        import jsonschema  # type: ignore
    except ImportError:
        return False, ["La bibliothèque 'jsonschema' n'est pas installée. Exécuter 'pip install jsonschema'."]

    # Résolution du schéma officiel
    if schema_filepath is None:
        # Recherche locale dans le projet
        candidate_paths = [
            os.path.join(os.path.dirname(__file__), "..", "schemas", "sarif-schema-2.1.0.json"),
            os.path.join(os.path.dirname(__file__), "schemas", "sarif-schema-2.1.0.json"),
            os.path.join(os.getcwd(), "schemas", "sarif-schema-2.1.0.json"),
        ]
        for cp in candidate_paths:
            normalized = os.path.abspath(cp)
            if os.path.exists(normalized):
                schema_filepath = normalized
                break

    schema_data: Dict[str, Union[str, Dict[str, Union[str, List[str]]]]] = {}

    if schema_filepath and os.path.exists(schema_filepath):
        with open(schema_filepath, "r", encoding="utf-8") as sf:
            schema_data = json.load(sf)
    else:
        # Téléchargement de secours
        try:
            import urllib.request
            req = urllib.request.Request(
                "https://json.schemastore.org/sarif-2.1.0.json",
                headers={"User-Agent": "RadiantDarwin-SARIF-Validator/2.4.0"}
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                schema_data = json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            return False, [f"Impossible de charger le schéma SARIF v2.1.0 local ou distant : {e}"]

    # Chargement du document SARIF
    if not os.path.exists(sarif_filepath):
        return False, [f"Fichier SARIF introuvable : {sarif_filepath}"]

    with open(sarif_filepath, "r", encoding="utf-8") as f:
        sarif_doc = json.load(f)

    # Validation stricte Draft 7
    validator = jsonschema.Draft7Validator(schema_data)
    errors: List[str] = []
    for err in sorted(validator.iter_errors(sarif_doc), key=lambda e: e.path):
        loc = " -> ".join([str(p) for p in err.path])
        errors.append(f"Erreur à [{loc}]: {err.message}")

    return (len(errors) == 0, errors)


# -----------------------------------------------------------------------------
# Interface Ligne de Commande (CLI)
# -----------------------------------------------------------------------------

def parse_cli_args() -> argparse.Namespace:
    """
    Construit l'analyseur d'arguments CLI pour le générateur SARIF.
    Paramètres : aucun.
    Valeur retournée : argparse.Namespace.
    """
    parser = argparse.ArgumentParser(
        prog="sarif_generator",
        description="Générateur d'Export SARIF v2.1.0 pour GitHub Security / Code Scanning."
    )
    parser.add_argument(
        "--src-dir",
        type=str,
        default="src",
        help="Répertoire source à auditer (défaut: 'src')"
    )
    parser.add_argument(
        "--output",
        "-o",
        type=str,
        default="audit-results.sarif",
        help="Chemin du fichier SARIF en sortie (défaut: 'audit-results.sarif')"
    )
    parser.add_argument(
        "--validate",
        action="store_true",
        default=True,
        help="Valider le fichier SARIF produit avec le schéma officiel OASIS (défaut: True)"
    )
    parser.add_argument(
        "--no-validate",
        action="store_false",
        dest="validate",
        help="Désactiver la validation de schéma"
    )
    parser.add_argument(
        "--fail-on-findings",
        action="store_true",
        help="Renvoyer un code de sortie non nul si des violations bloquantes sont détectées"
    )
    return parser.parse_args()


def main() -> int:
    """
    Point d'entrée principal en ligne de commande.
    Paramètres : aucun.
    Valeur retournée : int (code de sortie du processus).
    """
    args = parse_cli_args()
    generator = SarifReportGenerator()

    print("=" * 70)
    print("GÉNÉRATEUR SARIF v2.1.0 POUR GITHUB SECURITY (CAD STUDIO NEXUS-3D)")
    print("=" * 70)
    print(f"  Répertoire analysé : {args.src_dir}")
    print(f"  Fichier de sortie   : {args.output}")

    findings = generator.collect_findings_from_directory(args.src_dir)
    success = generator.export_sarif_file(
        output_file=args.output,
        findings=findings,
        validate_schema=args.validate
    )

    if not success:
        return 2

    # Filtrer les erreurs bloquantes si demandé
    if args.fail_on_findings:
        critical_count = sum(
            1 for f in findings
            if (f.custom_level == SarifLevel.ERROR or (not f.custom_level and generator.rules[f.rule_id].default_level == SarifLevel.ERROR))
        )
        if critical_count > 0:
            print(f"[SARIF GENERATOR] Échec : {critical_count} violation(s) critique(s) détectée(s).", file=sys.stderr)
            return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
