"""
Exercise generation for language learning lessons.

Exercises are derived entirely from the structured output of build_lesson():
  - Word translation MC  : "How do you say 'battery' in German?" (4 choices)
  - Sentence translation : "Translate to German:" (open-ended)
  - Sentence MC          : Pick the correct translation from 4 options

Distractor strategy:
  - Word MC: other entries with the same GF category
  - Sentence MC: sentences from OTHER entries at the same difficulty + verb_cat
    This makes distractors grammatically parallel — learners must identify
    the correct vocabulary, not a structural difference.

select_exercises() is the main entry point: given a lesson's entries and a
SkillProfile, it returns n Exercise objects tailored to the learner's level,
weighted toward patterns that appear in the source document if source_patterns
is provided.
"""

import random
import dataclasses
from collections import Counter
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional

from .pattern import GrammarPattern
from .skill import SkillProfile

# ---------------------------------------------------------------------------
# Sequencing constants
# ---------------------------------------------------------------------------

# Minimum receptive attempts on a node before interleaving it with others.
# Below this threshold the learner is in "blocking" mode: exercises focus on
# one structure at a time to build initial schema.
_BLOCK_MIN_ATTEMPTS = 6

# Maximum receptive-mode exercises selected from the same pattern in one call
# to select_exercises() when the learner is in blocking mode.  Once blocking
# is off (node has ≥ _BLOCK_MIN_ATTEMPTS), this cap is lifted.
_BLOCK_MAX_PER_PATTERN = 3


# ---------------------------------------------------------------------------
# Exercise types and data structure
# ---------------------------------------------------------------------------

class ExerciseType(Enum):
    WORD_TRANSLATION_MC  = "word_translation_mc"   # vocabulary recall, MC
    SENTENCE_TRANSLATION = "sentence_translation"  # produce target sentence, open
    SENTENCE_MC          = "sentence_mc"           # choose correct translation, MC


@dataclass
class Exercise:
    """
    A single renderable exercise.

    Fields
    ------
    exercise_type  : ExerciseType
    difficulty     : int  1–5
    prompt         : str  text shown to the learner
    prompt_lang    : str  ISO code of the prompt language
    target_lang    : str  ISO code the learner answers in
    correct        : str  correct answer
    choices        : list[str] | None  — 4 shuffled options for MC types, None for open
    metadata       : dict  — gf_function, gf_cat, pattern dict, label, etc.
    """
    exercise_type: ExerciseType
    difficulty:    int
    prompt:        str
    prompt_lang:   str
    target_lang:   str
    correct:       str
    choices:       Optional[List[str]]
    metadata:      Dict


# ---------------------------------------------------------------------------
# Individual exercise generators
# ---------------------------------------------------------------------------

def generate_word_translation_mc(
    entry: dict,
    all_entries: list,
    source_lang: str,
    target_lang: str,
    rng: Optional[random.Random] = None,
) -> Optional[Exercise]:
    """
    "How do you say '[word]' in [target_lang]?" with 3 distractors.

    Distractors are drawn from other entries that share the same GF category
    and have a different target-language translation.  Returns None if no
    distractors can be found.
    """
    rng = rng or random.Random()

    if not entry.get("in_wordnet"):
        return None
    correct = entry["translations"].get(target_lang)
    if not correct:
        return None

    prompt_word = entry["translations"].get(source_lang) or entry["word"]

    # Build distractor pool: same category, different gf_function, has target translation
    pool = [
        e["translations"][target_lang]
        for e in all_entries
        if (e.get("in_wordnet")
            and e.get("gf_function") != entry.get("gf_function")
            and e.get("gf_cat") == entry.get("gf_cat")
            and e["translations"].get(target_lang)
            and e["translations"][target_lang] != correct)
    ]

    if not pool:
        return None

    distractors = rng.sample(pool, min(3, len(pool)))
    choices = [correct] + distractors
    rng.shuffle(choices)

    return Exercise(
        exercise_type=ExerciseType.WORD_TRANSLATION_MC,
        difficulty=2,  # vocabulary recall is always A2 level
        prompt=prompt_word,
        prompt_lang=source_lang,
        target_lang=target_lang,
        correct=correct,
        choices=choices,
        metadata={
            "gf_function": entry.get("gf_function"),
            "gf_cat":      entry.get("gf_cat"),
            "word":        entry.get("word"),
        },
    )


def generate_sentence_translation(
    entry: dict,
    sentence: dict,
    source_lang: str,
    target_lang: str,
) -> Optional[Exercise]:
    """
    "Translate to [target_lang]:" with an open-ended answer.

    The prompt is the source-language linearization of the sentence.
    Correct is the target-language linearization.
    """
    prompt = sentence.get(source_lang)
    correct = sentence.get(target_lang)
    if not prompt or not correct:
        return None

    pat_dict = sentence.get("pattern", {})
    difficulty = pat_dict.get("difficulty", 2)

    return Exercise(
        exercise_type=ExerciseType.SENTENCE_TRANSLATION,
        difficulty=difficulty,
        prompt=prompt,
        prompt_lang=source_lang,
        target_lang=target_lang,
        correct=correct,
        choices=None,
        metadata={
            "gf_function": entry.get("gf_function"),
            "gf_cat":      entry.get("gf_cat"),
            "label":       sentence.get("label"),
            "pattern":     pat_dict,
            "tree":        sentence.get("tree"),
        },
    )


def generate_sentence_mc(
    entry: dict,
    sentence: dict,
    all_entries: list,
    source_lang: str,
    target_lang: str,
    rng: Optional[random.Random] = None,
) -> Optional[Exercise]:
    """
    Sentence translation as multiple-choice: pick the correct target translation.

    Distractors are sentences from OTHER entries that have the same GrammarPattern
    difficulty and verb_cat.  This ensures distractors are grammatically parallel —
    learners must identify the correct vocabulary, not a structural difference.

    Returns None if fewer than 1 distractor can be found.
    """
    rng = rng or random.Random()

    prompt = sentence.get(source_lang)
    correct = sentence.get(target_lang)
    if not prompt or not correct:
        return None

    pat_dict = sentence.get("pattern", {})
    if not pat_dict:
        return None

    try:
        target_pat = GrammarPattern(**pat_dict)
    except (TypeError, Exception):
        return None

    # Build distractor pool: different entry, same difficulty + verb_cat,
    # has target translation, not identical to correct answer
    distractors = []
    for other in all_entries:
        if other.get("gf_function") == entry.get("gf_function"):
            continue
        for other_sent in other.get("sentences", []):
            other_text = other_sent.get(target_lang)
            if not other_text or other_text == correct:
                continue
            other_pat_dict = other_sent.get("pattern", {})
            if not other_pat_dict:
                continue
            try:
                other_pat = GrammarPattern(**other_pat_dict)
            except Exception:
                continue
            if (other_pat.difficulty == target_pat.difficulty
                    and other_pat.verb_cat == target_pat.verb_cat):
                distractors.append(other_text)

    if not distractors:
        return None

    # Deduplicate and sample
    distractors = list(dict.fromkeys(distractors))
    sampled = rng.sample(distractors, min(3, len(distractors)))
    choices = [correct] + sampled
    rng.shuffle(choices)

    return Exercise(
        exercise_type=ExerciseType.SENTENCE_MC,
        difficulty=target_pat.difficulty,
        prompt=prompt,
        prompt_lang=source_lang,
        target_lang=target_lang,
        correct=correct,
        choices=choices,
        metadata={
            "gf_function": entry.get("gf_function"),
            "gf_cat":      entry.get("gf_cat"),
            "label":       sentence.get("label"),
            "pattern":     pat_dict,
        },
    )


# ---------------------------------------------------------------------------
# Adaptive exercise selection
# ---------------------------------------------------------------------------

def select_exercises(
    entries: list,
    profile: SkillProfile,
    n: int,
    source_lang: str,
    target_lang: str,
    source_patterns: Optional[Counter] = None,
    rng: Optional[random.Random] = None,
) -> List[Exercise]:
    """
    Return up to n Exercise objects tailored to the learner's skill profile.

    Selection algorithm
    -------------------
    1. Compute difficulty mix from profile.recommend_difficulty_mix().
    2. Bucket all sentences by difficulty.
    3. Score sentences by how often their GrammarPattern appears in the
       source document (source_patterns boost) and whether the vocabulary
       word is already known (vocab_seen boost — reinforcement).
    4. Allocate exercise slots per difficulty level according to the mix.
    5. For each slot: try sentence_mc first (richer exercise), fall back to
       sentence_translation if no distractors available.
    6. Pad any remaining slots with word_translation_mc exercises.
    7. Shuffle and return.

    Parameters
    ----------
    entries         : build_lesson() output
    profile         : SkillProfile — drives difficulty targeting
    n               : number of exercises to return
    source_lang     : ISO code of the source/prompt language
    target_lang     : ISO code the learner answers in
    source_patterns : Counter[GrammarPattern] from patterns_in_source()
                      — boosts exercises matching the source document's structures
    rng             : for deterministic output in tests
    """
    rng = rng or random.Random()

    # ------------------------------------------------------------------
    # 1. Build sentence pool bucketed by difficulty
    # ------------------------------------------------------------------
    by_difficulty: Dict[int, list] = {i: [] for i in range(1, 6)}
    wordnet_entries = []

    for entry in entries:
        if not entry.get("in_wordnet"):
            continue
        wordnet_entries.append(entry)
        for sent in entry.get("sentences", []):
            pat = sent.get("pattern", {})
            d = pat.get("difficulty", 2)
            by_difficulty[d].append((entry, sent))

    # ------------------------------------------------------------------
    # 2. Score sentences
    # ------------------------------------------------------------------
    from .nodes import node_weakness_score as _node_weakness

    def _sentence_score(entry_sent_pair) -> float:
        entry, sent = entry_sent_pair
        score = 0.0
        pat_dict = sent.get("pattern", {})
        # Source pattern frequency boost
        if source_patterns and pat_dict:
            try:
                pat = GrammarPattern(**pat_dict)
                score += source_patterns.get(pat, 0) * 0.5
            except Exception:
                pass
        # Node weakness boost — prefer sentences that exercise weak/unseen nodes
        if pat_dict:
            score += _node_weakness(pat_dict, profile, target_lang) * 0.8
        # Vocab reinforcement: slightly prefer words the learner has already seen
        fn = entry.get("gf_function", "")
        if fn in (profile.vocab_seen or []):
            score += 0.3
        return score

    for d in by_difficulty:
        by_difficulty[d].sort(key=_sentence_score, reverse=True)

    # ------------------------------------------------------------------
    # 3. Allocate slots per difficulty level
    # ------------------------------------------------------------------
    mix = profile.recommend_difficulty_mix()
    # Round allocations; give any remainder to the primary level
    primary = profile.current_level()
    slots: Dict[int, int] = {}
    allocated = 0
    sorted_mix = sorted(mix.items(), key=lambda kv: -kv[1])
    for i, (level, fraction) in enumerate(sorted_mix):
        if i < len(sorted_mix) - 1:
            count = round(fraction * n)
        else:
            count = n - allocated  # give remainder to last bucket
        slots[level] = max(0, count)
        allocated += slots[level]

    # ------------------------------------------------------------------
    # 4. Generate exercises per level
    #    Receptive→productive gating + block→interleave sequencing:
    #
    #    - For each sentence, look at its primary grammar nodes.
    #    - If any node is in productive mode (receptive mastered), prefer
    #      open sentence_translation (productive exercise).
    #    - Otherwise use sentence_mc (receptive / recognition exercise).
    #    - Blocking: while a node has < _BLOCK_MIN_ATTEMPTS, cap reuse of
    #      that exact pattern across this exercise set to _BLOCK_MAX_PER_PATTERN
    #      so the learner sees focused repetition without being stuck in a loop.
    # ------------------------------------------------------------------
    from .nodes import pattern_to_node_keys as _pat_keys

    exercises: List[Exercise] = []
    pattern_use_count: Counter = Counter()  # pattern-key → times used this call

    for level in sorted(slots.keys()):
        needed = slots[level]
        if needed == 0:
            continue

        candidates = by_difficulty.get(level, [])
        added = 0

        for entry, sent in candidates:
            if added >= needed:
                break

            pat_dict = sent.get("pattern", {})

            # --- Block→interleave: skip if this pattern is over-represented ---
            if pat_dict:
                node_keys = _pat_keys(pat_dict, target_lang)
                # Build a canonical pattern key from the most distinctive node
                pattern_key = "|".join(sorted(node_keys))
                # While any of this pattern's nodes is in early blocking phase
                # (< _BLOCK_MIN_ATTEMPTS seen), cap reuse within this selection
                in_blocking = any(
                    profile.node_attempts_count(k, "r") < _BLOCK_MIN_ATTEMPTS
                    for k in node_keys
                )
                if (in_blocking
                        and pattern_use_count[pattern_key] >= _BLOCK_MAX_PER_PATTERN):
                    continue
            else:
                node_keys = []
                pattern_key = ""

            # --- Receptive→productive gating ---
            # If any of this sentence's nodes has reached productive phase,
            # the learner should now be producing, not just recognising.
            needs_productive = any(
                profile.recommend_mode(k) == "p" for k in node_keys
            )

            ex: Optional[Exercise] = None
            if needs_productive:
                # Productive: open-ended sentence translation
                ex = generate_sentence_translation(entry, sent, source_lang, target_lang)
            else:
                # Receptive: multiple-choice, fall back to translation if no distractors
                ex = generate_sentence_mc(entry, sent, entries, source_lang, target_lang, rng)
                if ex is None:
                    ex = generate_sentence_translation(entry, sent, source_lang, target_lang)

            if ex:
                exercises.append(ex)
                profile.mark_vocab_seen(entry.get("gf_function", ""))
                if pattern_key:
                    pattern_use_count[pattern_key] += 1
                added += 1

    # ------------------------------------------------------------------
    # 5. Pad remaining slots with word translation MC
    # ------------------------------------------------------------------
    remaining = n - len(exercises)
    if remaining > 0 and wordnet_entries:
        rng.shuffle(wordnet_entries)
        for entry in wordnet_entries:
            if remaining <= 0:
                break
            ex = generate_word_translation_mc(entry, entries, source_lang, target_lang, rng)
            if ex:
                exercises.append(ex)
                remaining -= 1

    # ------------------------------------------------------------------
    # 6. Shuffle and return
    # ------------------------------------------------------------------
    rng.shuffle(exercises)
    return exercises[:n]
