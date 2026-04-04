"""
Integration tests for translator/generator.py.

Requires Parse.pgf on disk.  Run with:
    pytest -m integration
"""
import pytest


# ---------------------------------------------------------------------------
# Sense selection
# ---------------------------------------------------------------------------

@pytest.mark.integration
class TestSelectBestSense:
    def test_battery_selects_sense_1(self, grammar, concretes):
        from translator.generator import select_best_sense
        fn = select_best_sense(
            "battery", "N",
            src_concrete=concretes["en"],
            sentences_with_word=["The battery charges quickly."],
            grammar=grammar,
            all_concretes=concretes,
        )
        assert fn == "battery_1_N", f"Expected battery_1_N, got {fn!r}"

    def test_run_returns_v_sense(self, grammar, concretes):
        from translator.generator import select_best_sense
        fn = select_best_sense(
            "run", "V",
            src_concrete=concretes["en"],
            sentences_with_word=["The car runs fast."],
            grammar=grammar,
            all_concretes=concretes,
        )
        assert fn is not None
        assert fn.endswith("_V"), f"Expected _V suffix, got {fn!r}"

    def test_charge_avoids_high_sense(self, grammar, concretes):
        from translator.generator import select_best_sense, _extract_sense_number
        fn = select_best_sense(
            "charge", "V2",
            src_concrete=concretes["en"],
            sentences_with_word=["I charge the battery every day."],
            grammar=grammar,
            all_concretes=concretes,
        )
        assert fn is not None
        # charge_20_V2 = "mandar" — the default sense selection bug we fixed
        assert _extract_sense_number(fn) < 20, \
            f"Got unexpectedly high sense: {fn!r}"

    def test_unknown_word_returns_none(self, grammar, concretes):
        from translator.generator import select_best_sense
        fn = select_best_sense(
            "xyzxyzxyzqqqq", "N",
            src_concrete=concretes["en"],
            sentences_with_word=[],
            grammar=grammar,
            all_concretes=concretes,
        )
        assert fn is None

    def test_result_linearizes_in_all_langs(self, grammar, concretes):
        from translator.generator import select_best_sense, _lin_safe, _minimal_tree
        fn = select_best_sense(
            "battery", "N",
            src_concrete=concretes["en"],
            sentences_with_word=[],
            grammar=grammar,
            all_concretes=concretes,
        )
        assert fn is not None
        lins = _lin_safe(concretes, _minimal_tree(fn, "N"))
        assert lins is not None
        assert set(lins.keys()) == set(concretes.keys())


# ---------------------------------------------------------------------------
# _bare_word — dictionary form extraction
# ---------------------------------------------------------------------------

@pytest.mark.integration
class TestBareWord:
    def test_run_german_no_zu_prefix(self, concretes):
        from translator.generator import _bare_word
        result = _bare_word(concretes, "run_1_V", "V")
        de = result.get("de", "")
        # tabularLinearize should give "laufen", not "zu laufen"
        assert de == "laufen", f"Expected 'laufen', got {de!r}"

    def test_battery_german(self, concretes):
        from translator.generator import _bare_word
        result = _bare_word(concretes, "battery_1_N", "N")
        assert result.get("de") == "Batterie"

    def test_battery_spanish(self, concretes):
        from translator.generator import _bare_word
        result = _bare_word(concretes, "battery_1_N", "N")
        assert result.get("es") == "batería"

    def test_fast_adjective(self, concretes):
        from translator.generator import _bare_word
        result = _bare_word(concretes, "fast_1_A", "A")
        assert result.get("de") == "schnell"

    def test_returns_dict_with_all_langs(self, concretes):
        from translator.generator import _bare_word
        result = _bare_word(concretes, "battery_1_N", "N")
        for lang in concretes:
            assert lang in result, f"Missing lang {lang!r} in bare_word result"


# ---------------------------------------------------------------------------
# Sentence generation
# ---------------------------------------------------------------------------

@pytest.mark.integration
class TestSentenceGeneration:
    """
    Tests for the profile-driven generate_sentences() / _dispatch_generate().

    All tests use either a default (None = new-learner) or a level-5 profile
    (full range of patterns) to control how many sentences are generated.
    """

    def _full_profile(self):
        """Return a SkillProfile that has mastered all lower levels."""
        from translator.skill import SkillProfile
        p = SkillProfile(
            attempts=[10, 10, 10, 10, 0],
            correct=[10, 10, 10, 10, 0],
            vocab_seen=[],
            exercises_completed=[10, 10, 10, 10, 0],
        )
        return p

    def test_generate_v_nonempty(self, concretes):
        from translator.generator import generate_sentences, select_generation_patterns
        patterns = select_generation_patterns("V", None, None)
        sents = generate_sentences("run_1_V", "V", concretes, patterns)
        assert sents, "Expected non-empty sentence list for V"

    def test_generate_v2_nonempty(self, concretes):
        from translator.generator import generate_sentences, select_generation_patterns
        patterns = select_generation_patterns("V2", None, None)
        sents = generate_sentences("charge_3_V2", "V2", concretes, patterns)
        assert sents, "Expected non-empty sentence list for V2"

    def test_generate_n_nonempty(self, concretes):
        from translator.generator import generate_sentences, select_generation_patterns
        patterns = select_generation_patterns("N", None, None)
        sents = generate_sentences("battery_1_N", "N", concretes, patterns)
        assert sents, "Expected non-empty sentence list for N"

    def test_generate_a_nonempty(self, concretes):
        from translator.generator import generate_sentences, select_generation_patterns
        patterns = select_generation_patterns("A", None, None)
        sents = generate_sentences("fast_1_A", "A", concretes, patterns)
        assert sents, "Expected non-empty sentence list for A"

    def test_sentences_have_label(self, concretes):
        from translator.generator import generate_sentences, select_generation_patterns
        patterns = select_generation_patterns("V", None, None)
        sents = generate_sentences("run_1_V", "V", concretes, patterns)
        for s in sents:
            assert "label" in s, f"Sentence missing 'label': {s}"

    def test_sentences_have_all_lang_keys(self, concretes):
        from translator.generator import generate_sentences, select_generation_patterns
        patterns = select_generation_patterns("V", None, None)
        sents = generate_sentences("run_1_V", "V", concretes, patterns)
        for s in sents:
            for lang in concretes:
                assert lang in s, f"Sentence missing lang {lang!r}: {s}"

    def test_no_bracket_markers_in_output(self, concretes):
        from translator.generator import generate_sentences, select_generation_patterns
        _NON_TEXT_KEYS = {"label", "tree", "pattern"}
        patterns = select_generation_patterns("N", None, None)
        sents = generate_sentences("battery_1_N", "N", concretes, patterns)
        for s in sents:
            for lang, text in s.items():
                if lang in _NON_TEXT_KEYS:
                    continue
                assert isinstance(text, str), f"Expected str for {lang!r}, got {type(text)}"
                assert "[" not in text, \
                    f"Unresolved GF token in {lang!r}: {text!r}"

    @pytest.mark.parametrize("fn,cat,min_count", [
        ("run_1_V",     "V",  8),   # full profile: many tense/person combos
        ("charge_3_V2", "V2", 8),
        ("battery_1_N", "N",  5),   # 3 NP fragments + copula + object patterns
        ("fast_1_A",    "A",  3),   # 1 attributive + copula patterns
    ])
    def test_sentence_count_minimum(self, concretes, fn, cat, min_count):
        from translator.generator import _dispatch_generate
        sents = _dispatch_generate(fn, cat, concretes, profile=self._full_profile())
        assert len(sents) >= min_count, \
            f"{fn} generated only {len(sents)} sentences (expected >= {min_count})"

    def test_new_learner_gets_fewer_sentences(self, concretes):
        """A new learner (None profile) gets fewer sentences than a full profile."""
        from translator.generator import _dispatch_generate
        new_sents  = _dispatch_generate("run_1_V", "V", concretes, profile=None)
        full_sents = _dispatch_generate("run_1_V", "V", concretes,
                                        profile=self._full_profile())
        assert len(full_sents) > len(new_sents), (
            f"Expected full profile to generate more sentences than new learner: "
            f"full={len(full_sents)}, new={len(new_sents)}"
        )

    def test_source_pattern_boost(self, concretes):
        """A pattern present in source_patterns is included in output."""
        from collections import Counter
        from translator.generator import _dispatch_generate
        from translator.pattern import GrammarPattern, _compute_difficulty

        # Build a pattern that would normally be filtered out at level 2 (max_diff=2)
        # but is in the source — it's still filtered (source cannot override ceiling)
        # So instead test that source boost affects ordering within allowed range.
        # Use a level-3 profile where difficulty 3 is in the mix.
        from translator.skill import SkillProfile
        p3 = SkillProfile(
            attempts=[10, 10, 0, 0, 0],
            correct=[10, 10, 0, 0, 0],
            vocab_seen=[], exercises_completed=[10, 10, 0, 0, 0],
        )
        # Create a B1 pattern matching TPast+ASimul+PPos+they_Pron (difficulty 3)
        boosted = GrammarPattern(
            utt_type="UttS", tense="TPast", aspect="ASimul",
            polarity="PPos", person="they_Pron", verb_cat="UseV",
            progressive=False, attributive=False,
            difficulty=_compute_difficulty("UttS","TPast","ASimul","PPos","they_Pron",False),
        )
        sp = Counter({boosted: 5})
        sents = _dispatch_generate("run_1_V", "V", concretes, profile=p3,
                                   source_patterns=sp)
        trees = [s["tree"] for s in sents]
        assert any("they_Pron" in t and "TPast" in t for t in trees), \
            "Boosted source pattern should appear in output"


# ---------------------------------------------------------------------------
# build_lesson — full entry structure
# ---------------------------------------------------------------------------

@pytest.mark.integration
class TestBuildLesson:
    def test_returns_correct_count(self, lesson_entries):
        assert len(lesson_entries) == 4

    def test_all_words_present(self, lesson_entries):
        words = {e["word"] for e in lesson_entries}
        assert words == {"battery", "charge", "run", "fast"}

    def test_wordnet_words_have_translations(self, lesson_entries):
        for entry in lesson_entries:
            if entry["in_wordnet"]:
                assert entry["translations"], \
                    f"'{entry['word']}' in WordNet but no translations"

    def test_wordnet_words_have_sentences(self, lesson_entries):
        for entry in lesson_entries:
            if entry["in_wordnet"]:
                assert entry["sentences"], \
                    f"'{entry['word']}' in WordNet but no sentences"

    def test_all_entries_have_alternates_field(self, lesson_entries):
        for entry in lesson_entries:
            assert "alternates" in entry, f"Missing 'alternates' on '{entry['word']}'"
            assert isinstance(entry["alternates"], list)

    def test_all_entries_have_source_count(self, lesson_entries):
        for entry in lesson_entries:
            assert "source_count" in entry, f"Missing 'source_count' on '{entry['word']}'"
            assert isinstance(entry["source_count"], int)
            assert entry["source_count"] >= 0

    def test_alternates_have_required_fields(self, lesson_entries):
        for entry in lesson_entries:
            for alt in entry["alternates"]:
                assert "gf_function" in alt
                assert "translations" in alt
                assert "source_count" in alt
                assert isinstance(alt["source_count"], int)

    def test_alternates_differ_from_primary(self, lesson_entries):
        """Each alternate must produce a different target-language translation."""
        from translator.generator import _translation_fingerprint
        for entry in lesson_entries:
            if not entry["in_wordnet"] or not entry["alternates"]:
                continue
            primary_fp = _translation_fingerprint(entry["translations"], "en")
            for alt in entry["alternates"]:
                alt_fp = _translation_fingerprint(alt["translations"], "en")
                assert alt_fp != primary_fp, (
                    f"'{entry['word']}': alternate {alt['gf_function']!r} "
                    f"has same translations as primary {entry['gf_function']!r}"
                )

    def test_sentences_include_target_langs(self, lesson_entries):
        for entry in lesson_entries:
            for sent in entry["sentences"]:
                assert "de" in sent, f"Missing 'de' in sentence: {sent}"
                assert "es" in sent, f"Missing 'es' in sentence: {sent}"

    def test_source_examples_match_source_text(self, lesson_entries):
        battery = next(e for e in lesson_entries if e["word"] == "battery")
        texts = [ex["text"] for ex in battery["source_examples"]]
        assert texts, "Expected at least one source example for 'battery'"
        assert any("battery" in t.lower() for t in texts)

    def test_charge_has_alternates(self, lesson_entries):
        """'charge' has 40+ WordNet senses — should always yield alternates."""
        charge = next(e for e in lesson_entries if e["word"] == "charge")
        if charge["in_wordnet"]:
            assert charge["alternates"], \
                "Expected alternates for 'charge' (40+ senses in WordNet)"

    def test_oov_word_structure(self, grammar, parse_pgf_path):
        from translator.generator import build_lesson
        entries = build_lesson(
            {"xyzxyz": "N"},
            "xyzxyz is a made-up word.",
            "en", ["es", "de"],
            pgf_path=parse_pgf_path,
        )
        assert len(entries) == 1
        e = entries[0]
        assert e["in_wordnet"] is False
        assert e["gf_function"] is None
        assert e["sentences"] == []
        assert e["translations"] == {}
        assert e["alternates"] == []

    def test_battery_primary_is_battery_1_N(self, lesson_entries):
        battery = next(e for e in lesson_entries if e["word"] == "battery")
        assert battery["in_wordnet"]
        assert battery["gf_function"] == "battery_1_N", \
            f"Expected battery_1_N, got {battery['gf_function']!r}"

    def test_sentences_have_tree_and_pattern(self, lesson_entries):
        for entry in lesson_entries:
            for sent in entry["sentences"]:
                assert "tree" in sent, f"Missing 'tree' key on sentence: {sent['label']}"
                assert "pattern" in sent, f"Missing 'pattern' key on sentence: {sent['label']}"
                assert isinstance(sent["tree"], str)
                assert isinstance(sent["pattern"], dict)

    def test_pattern_has_difficulty(self, lesson_entries):
        for entry in lesson_entries:
            for sent in entry["sentences"]:
                d = sent["pattern"].get("difficulty")
                assert d is not None, f"Pattern missing 'difficulty': {sent['label']}"
                assert 1 <= d <= 5, f"Difficulty out of range: {d}"

    def test_run_bare_word_german_is_laufen(self, lesson_entries):
        run = next(e for e in lesson_entries if e["word"] == "run")
        if run["in_wordnet"]:
            assert run["translations"].get("de") == "laufen", \
                f"Expected 'laufen', got {run['translations'].get('de')!r}"
