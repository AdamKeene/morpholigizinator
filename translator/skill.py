"""
User skill profile for adaptive exercise selection.

SkillProfile tracks two layers of skill data:

  1. Coarse difficulty-level counters (attempts/correct per level 1–5).
     Used as a fast fallback when node data is sparse and to drive the
     difficulty mix for exercise selection.

  2. Per-node counters (node_data dict).
     Tracks receptive and productive accuracy for each grammar skill node
     defined in translator/nodes.py.  Nodes follow the key convention:
       Universal:   "tense.TPast", "polarity.PNeg", "struct.question", ...
       Language:    "es.copula", "de.konjunktiv2", "ja.particle_wa_ga", ...
     Receptive mode ('r'): recognising the correct form (translate FROM target).
     Productive mode ('p'): producing the correct form (translate TO target).

The profile is JSON-serializable for persistence between sessions.
All fields use standard Python types — no sets or numpy.

Difficulty levels correspond to CEFR bands:
    1 → A1  (NP fragments, copula present)
    2 → A2  (present/past simple, default persons)
    3 → B1  (future, negation, progressive, non-default persons)
    4 → B2  (conditional, perfect aspects)
    5 → C1  (combinations)
"""

import json
import sqlite3
import dataclasses
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

# Default SQLite DB path for skill profiles.
# The schema maps directly to a Django model when you migrate:
#   user_id TEXT  → user = OneToOneField(User, primary_key=True)
#   JSON columns  → JSONField(default=...)
#   updated_at    → DateTimeField(auto_now=True)
SKILL_DB_PATH = "./resources/skill_profiles.db"


def _ensure_db(db_path: str) -> sqlite3.Connection:
    """Open (or create) the skill profiles DB and ensure the schema exists."""
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS skill_profiles (
            user_id              TEXT PRIMARY KEY,
            attempts             TEXT NOT NULL DEFAULT '[]',
            correct              TEXT NOT NULL DEFAULT '[]',
            vocab_seen           TEXT NOT NULL DEFAULT '[]',
            exercises_completed  TEXT NOT NULL DEFAULT '[]',
            node_data            TEXT NOT NULL DEFAULT '{}',
            updated_at           TEXT NOT NULL
                DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
        )
    """)
    conn.commit()
    return conn

# Coarse-level mastery thresholds
MIN_ATTEMPTS = 10
MASTERY_THRESHOLD = 0.80

# Node-level mastery thresholds (lower bar — nodes accumulate slower)
NODE_MIN_ATTEMPTS = 8
NODE_MASTERY_THRESHOLD = 0.80


@dataclass
class SkillProfile:
    """
    Persistent model of a learner's current abilities.

    All list fields have exactly 5 elements (one per difficulty level 1–5).
    Index i corresponds to difficulty level i+1.

    Persistence
    -----------
    Instances can be "bound" to a user by setting user_id (and optionally
    db_path).  Once bound, every record_*() / mark_vocab_seen() call
    automatically persists to SQLite (write-through).

    When migrating to Django:
      - user_id  → OneToOneField(User, primary_key=True)
      - db_path  → removed; Django's DB router handles routing
      - save()   → replaced by super().save() / self.full_clean() etc.
      - load()   → replaced by SkillProfile.objects.get(user=user)

    Unbound profiles (user_id=None) work as in-memory objects with no I/O,
    which is useful for tests and for building profiles before a user exists.
    """
    # Coarse per-level counters (difficulty 1–5, index = difficulty - 1)
    attempts:  List[int] = field(default_factory=lambda: [0, 0, 0, 0, 0])
    correct:   List[int] = field(default_factory=lambda: [0, 0, 0, 0, 0])

    # GF function names the learner has been exposed to
    vocab_seen: List[str] = field(default_factory=list)

    # Number of exercises completed per level (used for pacing display)
    exercises_completed: List[int] = field(default_factory=lambda: [0, 0, 0, 0, 0])

    # Per-node tracking — keyed by node key (see translator/nodes.py)
    # Each value: {"attempts_r": int, "correct_r": int,
    #              "attempts_p": int, "correct_p": int}
    node_data: Dict[str, Dict[str, int]] = field(default_factory=dict)

    # Identity / persistence binding.
    # user_id=None → unbound; write-through is disabled.
    # compare=False so two profiles with identical data but different user_ids
    # can be compared purely on their learning data (useful for testing).
    user_id: Optional[str]  = field(default=None,           compare=False)
    db_path: str             = field(default=SKILL_DB_PATH, compare=False)

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def accuracy(self, difficulty: int) -> Optional[float]:
        """Fraction correct at this difficulty level, or None if untested."""
        idx = difficulty - 1
        if self.attempts[idx] == 0:
            return None
        return self.correct[idx] / self.attempts[idx]

    def current_level(self) -> int:
        """
        The lowest unmastered difficulty level (1–5).

        A level is mastered when:
          - at least MIN_ATTEMPTS exercises attempted
          - accuracy >= MASTERY_THRESHOLD

        Returns the lowest level that does not yet meet both conditions.
        If all five levels are mastered, returns 5.
        """
        for level in range(1, 6):
            acc = self.accuracy(level)
            if acc is None or acc < MASTERY_THRESHOLD:
                return level
            if self.attempts[level - 1] < MIN_ATTEMPTS:
                return level
        return 5

    def recommend_difficulty_mix(self) -> Dict[int, float]:
        """
        Return a probability distribution over difficulty levels for
        exercise selection.

        Distribution:
          - 60% at current level (primary focus)
          - 25% at level + 1 (stretch / preview)
          - 15% at level - 1 (consolidation / review)

        Edge cases: at level 1, no level-0 exists so we give 75%/25%.
        At level 5, no level-6 exists so we give 80%/20%.
        """
        level = self.current_level()
        raw: Dict[int, float] = {}
        if level > 1:
            raw[level - 1] = 0.15
        raw[level] = 0.60
        if level < 5:
            raw[level + 1] = 0.25

        total = sum(raw.values())
        return {k: v / total for k, v in raw.items()}

    # ------------------------------------------------------------------
    # Updates
    # ------------------------------------------------------------------

    def _autosave(self) -> None:
        """Write-through: persist immediately if this profile is bound to a user."""
        if self.user_id is not None:
            self.save()

    def record_attempt(self, difficulty: int, is_correct: bool) -> None:
        """Record one exercise outcome and persist (write-through)."""
        idx = difficulty - 1
        self.attempts[idx] += 1
        self.exercises_completed[idx] += 1
        if is_correct:
            self.correct[idx] += 1
        self._autosave()

    def mark_vocab_seen(self, gf_function: str) -> None:
        """Record that the learner has been exposed to this GF function."""
        if gf_function not in self.vocab_seen:
            self.vocab_seen.append(gf_function)
            self._autosave()

    # ------------------------------------------------------------------
    # Per-node tracking
    # ------------------------------------------------------------------

    def record_node_attempt(
        self,
        node_key: str,
        is_correct: bool,
        mode: str = "r",
    ) -> None:
        """
        Record one attempt for a grammar skill node and persist (write-through).

        mode : "r" (receptive — recognise correct form)
             | "p" (productive — produce correct form)
        """
        if node_key not in self.node_data:
            self.node_data[node_key] = {
                "attempts_r": 0, "correct_r": 0,
                "attempts_p": 0, "correct_p": 0,
            }
        entry = self.node_data[node_key]
        entry[f"attempts_{mode}"] += 1
        if is_correct:
            entry[f"correct_{mode}"] += 1
        self._autosave()

    def node_accuracy(self, node_key: str, mode: str = "r") -> Optional[float]:
        """Fraction correct for this node in this mode, or None if untested."""
        entry = self.node_data.get(node_key)
        if not entry:
            return None
        attempts = entry.get(f"attempts_{mode}", 0)
        if attempts == 0:
            return None
        return entry.get(f"correct_{mode}", 0) / attempts

    def node_attempts_count(self, node_key: str, mode: str = "r") -> int:
        """Number of attempts recorded for this node in this mode."""
        entry = self.node_data.get(node_key)
        if not entry:
            return 0
        return entry.get(f"attempts_{mode}", 0)

    def node_mastered(
        self,
        node_key: str,
        mode: str = "r",
    ) -> bool:
        """Whether this node meets the mastery threshold in the given mode."""
        if self.node_attempts_count(node_key, mode) < NODE_MIN_ATTEMPTS:
            return False
        acc = self.node_accuracy(node_key, mode)
        return acc is not None and acc >= NODE_MASTERY_THRESHOLD

    def weakest_nodes(self, mode: str = "r", n: int = 5) -> List[str]:
        """
        Return the n most-practiced but lowest-accuracy node keys.

        These are the nodes where the learner has enough data to assess
        weakness but has not yet reached mastery — the highest-priority
        candidates for targeted practice.
        """
        scored = []
        for key, entry in self.node_data.items():
            attempts = entry.get(f"attempts_{mode}", 0)
            if attempts < 3:       # not enough data to assess
                continue
            correct = entry.get(f"correct_{mode}", 0)
            acc = correct / attempts
            # Weight by both weakness and exposure (more practiced = more signal)
            weight = (1.0 - acc) * min(attempts, 20) / 20.0
            scored.append((weight, key))
        scored.sort(reverse=True)
        return [key for _, key in scored[:n]]

    def unmastered_nodes(self, mode: str = "r") -> List[str]:
        """Return all node keys that have been attempted but not yet mastered."""
        return [
            key for key in self.node_data
            if not self.node_mastered(key, mode)
            and self.node_attempts_count(key, mode) > 0
        ]

    def de_pt_stage(self, mode: str = "r") -> int:
        """
        Return the learner's Processability Theory stage for German word order (1–5).

        PT stages are implicational — a learner at stage N has implicitly passed
        through all earlier stages.  We use receptive mastery by default since
        learners typically recognise a structure before producing it.

            1  Canonical SVO (default starting point)
            2  Agreement morphology (article gender, 3sg verb ending)
            3  Separable verb prefix separation  (de.wo_sep)
            4  Subject–verb inversion after fronting  (de.wo_inv)
            5  Verb-final in subordinate clauses  (de.wo_v_end)
        """
        if self.node_mastered("de.wo_v_end", mode):
            return 5
        if self.node_mastered("de.wo_inv", mode):
            return 4
        if self.node_mastered("de.wo_sep", mode):
            return 3
        if (self.node_mastered("de.article_gender", mode)
                and self.node_mastered("person.3sg", mode)):
            return 2
        return 1

    def recommend_mode(self, node_key: str) -> str:
        """
        Return the recommended practice mode for this node.

        Receptive mastery gates productive introduction:
            'r'      — not yet mastered receptively; practise recognition first
            'p'      — receptive mastery achieved; begin productive practice
            'review' — both modes mastered; include only for spaced review
        """
        if not self.node_mastered(node_key, "r"):
            return "r"
        if not self.node_mastered(node_key, "p"):
            return "p"
        return "review"

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def save(self) -> None:
        """
        Upsert this profile to the SQLite skill_profiles table.

        Requires user_id to be set (raises ValueError otherwise).
        Called automatically by record_*() / mark_vocab_seen() when bound.

        When migrating to Django this becomes super().save() on the model
        instance — the signature and semantics are identical.
        """
        if self.user_id is None:
            raise ValueError(
                "Cannot save an unbound SkillProfile. "
                "Set user_id first or use SkillProfile.load(db_path, user_id)."
            )
        d = dataclasses.asdict(self)
        conn = _ensure_db(self.db_path)
        conn.execute(
            """
            INSERT INTO skill_profiles
                (user_id, attempts, correct, vocab_seen, exercises_completed,
                 node_data, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
            ON CONFLICT(user_id) DO UPDATE SET
                attempts            = excluded.attempts,
                correct             = excluded.correct,
                vocab_seen          = excluded.vocab_seen,
                exercises_completed = excluded.exercises_completed,
                node_data           = excluded.node_data,
                updated_at          = excluded.updated_at
            """,
            (
                self.user_id,
                json.dumps(d["attempts"]),
                json.dumps(d["correct"]),
                json.dumps(d["vocab_seen"]),
                json.dumps(d["exercises_completed"]),
                json.dumps(d["node_data"]),
            ),
        )
        conn.commit()
        conn.close()

    @classmethod
    def load(cls, db_path: str, user_id: str) -> "SkillProfile":
        """
        Load a profile from the SQLite DB and bind it to user_id.

        Returns a fresh default profile bound to user_id if no stored data
        exists yet — analogous to get_or_create() in Django.
        Forward-compatible: missing / null JSON fields get defaults.
        Once loaded, any record_*() call auto-persists (write-through).
        """
        conn = _ensure_db(db_path)
        row = conn.execute(
            "SELECT attempts, correct, vocab_seen, exercises_completed, node_data "
            "FROM skill_profiles WHERE user_id = ?",
            (user_id,),
        ).fetchone()
        conn.close()

        if row is None:
            return cls(user_id=user_id, db_path=db_path)

        attempts, correct, vocab_seen, exercises_completed, node_data_raw = row
        data: dict = {
            "attempts":            json.loads(attempts or "[]"),
            "correct":             json.loads(correct or "[]"),
            "vocab_seen":          json.loads(vocab_seen or "[]"),
            "exercises_completed": json.loads(exercises_completed or "[]"),
            "node_data":           json.loads(node_data_raw or "{}"),
        }
        for key in ("attempts", "correct", "exercises_completed"):
            v = data.get(key, [])
            data[key] = (v + [0, 0, 0, 0, 0])[:5]
        data["vocab_seen"] = list(dict.fromkeys(data["vocab_seen"]))
        raw_nodes = data["node_data"]
        for entry in raw_nodes.values():
            for k in ("attempts_r", "correct_r", "attempts_p", "correct_p"):
                entry.setdefault(k, 0)
        data["node_data"] = raw_nodes
        return cls(user_id=user_id, db_path=db_path,
                   **{k: v for k, v in data.items() if k in cls.__dataclass_fields__})

    @classmethod
    def exists(cls, db_path: str, user_id: str) -> bool:
        """Return True if a stored profile exists for this user_id."""
        conn = _ensure_db(db_path)
        row = conn.execute(
            "SELECT 1 FROM skill_profiles WHERE user_id = ?", (user_id,)
        ).fetchone()
        conn.close()
        return row is not None

    @classmethod
    def default(cls) -> "SkillProfile":
        """Return a fresh zeroed profile."""
        return cls()
