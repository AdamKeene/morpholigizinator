"""
Unit tests for translator/nodes.py and SkillProfile node tracking.
No Parse.pgf required — all tests are pure Python.
"""

import pytest
from translator.nodes import (
    pattern_to_node_keys,
    node_weakness_score,
    surface_node_keys,
    ALL_NODES,
    UNIVERSAL_NODES,
    SPANISH_NODES,
    GERMAN_NODES,
    JAPANESE_NODES,
    LANG_NODES,
)
from translator.skill import SkillProfile


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _pat(utt_type="UttS", tense="TPres", aspect="ASimul", polarity="PPos",
         person="i_Pron", verb_cat="UseV", progressive=False, attributive=False):
    """Build a plain dict pattern (mirrors stored JSON; avoids importing GrammarPattern)."""
    return dict(
        utt_type=utt_type, tense=tense, aspect=aspect, polarity=polarity,
        person=person, verb_cat=verb_cat, progressive=progressive,
        attributive=attributive, difficulty=2,
    )


# ---------------------------------------------------------------------------
# Taxonomy sanity
# ---------------------------------------------------------------------------

class TestTaxonomy:
    def test_all_nodes_nonempty(self):
        assert len(ALL_NODES) >= 30

    def test_no_duplicate_keys(self):
        all_keys = list(ALL_NODES.keys())
        assert len(all_keys) == len(set(all_keys))

    def test_lang_nodes_disjoint_from_each_other(self):
        es_keys = set(SPANISH_NODES)
        de_keys = set(GERMAN_NODES)
        ja_keys = set(JAPANESE_NODES)
        assert not (es_keys & de_keys)
        assert not (es_keys & ja_keys)
        assert not (de_keys & ja_keys)

    def test_lang_prefixes_match(self):
        for key in SPANISH_NODES:
            assert key.startswith("es.")
        for key in GERMAN_NODES:
            assert key.startswith("de.")
        for key in JAPANESE_NODES:
            assert key.startswith("ja.")


# ---------------------------------------------------------------------------
# Universal node extraction
# ---------------------------------------------------------------------------

class TestUniversalKeys:
    def test_past_tense(self):
        keys = pattern_to_node_keys(_pat(tense="TPast"), "de")
        assert "tense.TPast" in keys

    def test_future_tense(self):
        keys = pattern_to_node_keys(_pat(tense="TFut"), "es")
        assert "tense.TFut" in keys

    def test_conditional_tense(self):
        keys = pattern_to_node_keys(_pat(tense="TCond"), "es")
        assert "tense.TCond" in keys

    def test_perfect_aspect(self):
        keys = pattern_to_node_keys(_pat(aspect="AAnter"), "de")
        assert "aspect.AAnter" in keys

    def test_simul_aspect_not_emitted(self):
        keys = pattern_to_node_keys(_pat(aspect="ASimul"), "de")
        assert "aspect.ASimul" not in keys

    def test_negation(self):
        keys = pattern_to_node_keys(_pat(polarity="PNeg"), "ja")
        assert "polarity.PNeg" in keys

    def test_positive_polarity_not_emitted(self):
        keys = pattern_to_node_keys(_pat(polarity="PPos"), "es")
        assert "polarity.PPos" not in keys

    def test_question(self):
        keys = pattern_to_node_keys(_pat(utt_type="UttQS"), "de")
        assert "struct.question" in keys

    def test_np_fragment(self):
        keys = pattern_to_node_keys(_pat(utt_type="UttNP"), "es")
        assert "struct.NP_fragment" in keys

    def test_progressive(self):
        keys = pattern_to_node_keys(_pat(progressive=True), "de")
        assert "struct.progressive" in keys

    def test_3sg_person(self):
        for person in ("he_Pron", "she_Pron"):
            keys = pattern_to_node_keys(_pat(person=person), "es")
            assert "person.3sg" in keys, f"Expected person.3sg for {person}"

    def test_plural_person(self):
        for person in ("they_Pron", "youPl_Pron"):
            keys = pattern_to_node_keys(_pat(person=person), "es")
            assert "person.plural" in keys

    def test_1pl_person(self):
        keys = pattern_to_node_keys(_pat(person="we_Pron"), "es")
        assert "person.1pl" in keys

    def test_default_persons_not_emitted(self):
        for person in ("i_Pron", "youSg_Pron", "it_Pron"):
            keys = pattern_to_node_keys(_pat(person=person), "es")
            assert "person.3sg" not in keys
            assert "person.plural" not in keys
            assert "person.1pl" not in keys

    def test_no_duplicates_in_output(self):
        keys = pattern_to_node_keys(
            _pat(tense="TPast", polarity="PNeg", utt_type="UttQS"), "de"
        )
        assert len(keys) == len(set(keys))


# ---------------------------------------------------------------------------
# Spanish-specific keys
# ---------------------------------------------------------------------------

class TestSpanishKeys:
    def test_copula(self):
        keys = pattern_to_node_keys(_pat(verb_cat="UseComp"), "es")
        assert "es.copula" in keys

    def test_non_copula_no_es_copula(self):
        keys = pattern_to_node_keys(_pat(verb_cat="UseV"), "es")
        assert "es.copula" not in keys

    def test_attributive_adjective(self):
        keys = pattern_to_node_keys(_pat(attributive=True, utt_type="UttNP"), "es")
        assert "es.gender_agreement" in keys

    def test_non_attributive_no_gender(self):
        keys = pattern_to_node_keys(_pat(attributive=False), "es")
        assert "es.gender_agreement" not in keys

    def test_es_keys_not_in_de_output(self):
        keys = pattern_to_node_keys(_pat(verb_cat="UseComp", attributive=True), "de")
        assert "es.copula" not in keys
        assert "es.gender_agreement" not in keys


# ---------------------------------------------------------------------------
# German-specific keys
# ---------------------------------------------------------------------------

class TestGermanKeys:
    def test_konjunktiv2(self):
        keys = pattern_to_node_keys(_pat(tense="TCond"), "de")
        assert "de.konjunktiv2" in keys
        # The universal tense.TCond key should also be present
        assert "tense.TCond" in keys

    def test_partizip2(self):
        keys = pattern_to_node_keys(_pat(aspect="AAnter"), "de")
        assert "de.partizip2" in keys
        assert "aspect.AAnter" in keys

    def test_de_keys_not_in_es_output(self):
        keys = pattern_to_node_keys(_pat(tense="TCond", aspect="AAnter"), "es")
        assert "de.konjunktiv2" not in keys
        assert "de.partizip2" not in keys


# ---------------------------------------------------------------------------
# Japanese-specific keys
# ---------------------------------------------------------------------------

class TestJapaneseKeys:
    def test_polite_register_always_present(self):
        # GF generates polite forms for Japanese by default
        keys = pattern_to_node_keys(_pat(), "ja")
        assert "ja.register_polite" in keys

    def test_progressive_te_iru(self):
        keys = pattern_to_node_keys(_pat(progressive=True), "ja")
        assert "ja.te_iru_prog" in keys
        assert "struct.progressive" in keys

    def test_ja_keys_not_in_de_output(self):
        keys = pattern_to_node_keys(_pat(progressive=True), "de")
        assert "ja.te_iru_prog" not in keys
        assert "ja.register_polite" not in keys


# ---------------------------------------------------------------------------
# SkillProfile node tracking
# ---------------------------------------------------------------------------

class TestSkillProfileNodes:
    def test_record_node_attempt_receptive(self):
        p = SkillProfile.default()
        p.record_node_attempt("tense.TPast", True, "r")
        p.record_node_attempt("tense.TPast", False, "r")
        assert p.node_accuracy("tense.TPast", "r") == 0.5
        assert p.node_attempts_count("tense.TPast", "r") == 2

    def test_record_node_attempt_productive(self):
        p = SkillProfile.default()
        p.record_node_attempt("polarity.PNeg", True, "p")
        assert p.node_accuracy("polarity.PNeg", "p") == 1.0
        assert p.node_accuracy("polarity.PNeg", "r") is None

    def test_unseen_node_returns_none(self):
        p = SkillProfile.default()
        assert p.node_accuracy("tense.TFut", "r") is None

    def test_node_mastered_below_threshold(self):
        p = SkillProfile.default()
        for _ in range(8):
            p.record_node_attempt("tense.TPast", True, "r")
        assert p.node_mastered("tense.TPast", "r")

    def test_node_not_mastered_low_accuracy(self):
        p = SkillProfile.default()
        for i in range(8):
            p.record_node_attempt("tense.TPast", i < 4, "r")  # 50% accuracy
        assert not p.node_mastered("tense.TPast", "r")

    def test_node_not_mastered_too_few_attempts(self):
        p = SkillProfile.default()
        for _ in range(5):  # below NODE_MIN_ATTEMPTS=8
            p.record_node_attempt("tense.TPast", True, "r")
        assert not p.node_mastered("tense.TPast", "r")

    def test_weakest_nodes_ordering(self):
        p = SkillProfile.default()
        # tense.TPast: 5 attempts, 2 correct (40%)
        for i in range(5):
            p.record_node_attempt("tense.TPast", i < 2, "r")
        # polarity.PNeg: 5 attempts, 4 correct (80%)
        for i in range(5):
            p.record_node_attempt("polarity.PNeg", i < 4, "r")
        weak = p.weakest_nodes("r", n=2)
        assert weak[0] == "tense.TPast", "Lower accuracy should rank first"

    def test_weakest_nodes_excludes_sparse(self):
        p = SkillProfile.default()
        p.record_node_attempt("tense.TPast", False, "r")  # 1 attempt — too sparse
        weak = p.weakest_nodes("r")
        assert "tense.TPast" not in weak

    def test_unmastered_nodes(self):
        p = SkillProfile.default()
        for _ in range(4):
            p.record_node_attempt("tense.TPast", True, "r")
        result = p.unmastered_nodes("r")
        assert "tense.TPast" in result

    def test_serialization_roundtrip(self):
        import dataclasses
        p = SkillProfile.default()
        p.record_node_attempt("de.konjunktiv2", True, "r")
        p.record_node_attempt("de.konjunktiv2", False, "p")
        d = dataclasses.asdict(p)
        p2 = SkillProfile(**{k: v for k, v in d.items()
                             if k in SkillProfile.__dataclass_fields__})
        assert p2.node_accuracy("de.konjunktiv2", "r") == 1.0
        assert p2.node_accuracy("de.konjunktiv2", "p") == 0.0

    def test_sqlite_write_through(self, tmp_path):
        """record_*() auto-persists when profile is bound via load()."""
        db = str(tmp_path / "test_skills.db")
        p = SkillProfile.load(db, "user_42")   # new user → default profile, bound
        p.record_node_attempt("tense.TPast", True, "r")
        p.record_node_attempt("polarity.PNeg", False, "p")
        p.record_attempt(2, True)
        p.mark_vocab_seen("run_1_V")
        # No explicit save() — write-through handled it

        p2 = SkillProfile.load(db, "user_42")
        assert p2.node_accuracy("tense.TPast", "r") == 1.0
        assert p2.node_accuracy("polarity.PNeg", "p") == 0.0
        assert p2.attempts[1] == 1
        assert "run_1_V" in p2.vocab_seen

    def test_sqlite_unbound_no_autosave(self, tmp_path):
        """default() returns unbound profile; record_*() does not hit the DB."""
        db = str(tmp_path / "test_skills.db")
        p = SkillProfile.default()             # user_id=None → unbound
        p.record_node_attempt("tense.TPast", True, "r")
        # Nothing was written — DB shouldn't even have the table yet touched
        assert not SkillProfile.exists(db, "any_user")

    def test_sqlite_load_missing_user_returns_default(self, tmp_path):
        db = str(tmp_path / "test_skills.db")
        p = SkillProfile.load(db, "nonexistent_user")
        assert p.attempts == [0, 0, 0, 0, 0]
        assert p.node_data == {}
        assert p.user_id == "nonexistent_user"   # bound, ready for write-through

    def test_sqlite_exists(self, tmp_path):
        db = str(tmp_path / "test_skills.db")
        assert not SkillProfile.exists(db, "u1")
        p = SkillProfile.load(db, "u1")
        p.record_attempt(1, True)              # write-through creates the row
        assert SkillProfile.exists(db, "u1")

    def test_sqlite_upsert_overwrites(self, tmp_path):
        db = str(tmp_path / "test_skills.db")
        p = SkillProfile.load(db, "u1")
        p.record_attempt(1, True)              # attempts[0] = 1, saved

        p2 = SkillProfile.load(db, "u1")
        p2.record_attempt(1, False)            # attempts[0] = 2, saved

        p3 = SkillProfile.load(db, "u1")
        assert p3.attempts[0] == 2


# ---------------------------------------------------------------------------
# node_weakness_score
# ---------------------------------------------------------------------------

class TestNodeWeaknessScore:
    def test_none_profile_returns_zero(self):
        assert node_weakness_score(_pat(tense="TPast"), None, "de") == 0.0

    def test_unseen_nodes_positive_score(self):
        p = SkillProfile.default()
        # tense.TPast has never been seen — should contribute 1.0
        score = node_weakness_score(_pat(tense="TPast"), p, "de")
        assert score > 0.0

    def test_mastered_nodes_contribute_less(self):
        p = SkillProfile.default()
        # Fully master tense.TPast
        for _ in range(10):
            p.record_node_attempt("tense.TPast", True, "r")
        score_mastered = node_weakness_score(_pat(tense="TPast"), p, "de")

        p2 = SkillProfile.default()  # tense.TPast unseen
        score_unseen = node_weakness_score(_pat(tense="TPast"), p2, "de")

        assert score_mastered < score_unseen

    def test_struggling_nodes_boost(self):
        p = SkillProfile.default()
        for i in range(6):
            p.record_node_attempt("polarity.PNeg", i < 2, "r")  # ~33% accuracy
        score = node_weakness_score(_pat(polarity="PNeg"), p, "es")
        assert score > 1.0  # substantial boost for struggling node


# ---------------------------------------------------------------------------
# surface_node_keys — Tier-2 detection
# ---------------------------------------------------------------------------

class TestSurfaceNodeKeysGerman:
    def _s(self, de_text):
        return {"de": de_text}

    def test_sep_prefix_at_end(self):
        keys = surface_node_keys(self._s("Ich rufe dich an"), "de")
        assert "de.wo_sep" in keys

    def test_no_sep_prefix_in_middle(self):
        # "nach" in "nach Hause" is a preposition, not a trailing prefix
        keys = surface_node_keys(self._s("Ich gehe nach Hause"), "de")
        assert "de.wo_sep" not in keys

    def test_inversion_after_adverb(self):
        keys = surface_node_keys(self._s("Heute arbeite ich"), "de")
        assert "de.wo_inv" in keys

    def test_no_inversion_in_plain_sentence(self):
        keys = surface_node_keys(self._s("Ich arbeite heute"), "de")
        assert "de.wo_inv" not in keys

    def test_subordinate_clause_triggers_v_end(self):
        keys = surface_node_keys(self._s("Er sagt, dass er arbeitet"), "de")
        assert "de.wo_v_end" in keys

    def test_weil_triggers_v_end(self):
        keys = surface_node_keys(self._s("Sie bleibt zuhause weil sie müde ist"), "de")
        assert "de.wo_v_end" in keys

    def test_article_gender_detected(self):
        keys = surface_node_keys(self._s("Das Kind spielt"), "de")
        assert "de.article_gender" in keys

    def test_accusative_detected(self):
        keys = surface_node_keys(self._s("Ich sehe den Mann"), "de")
        assert "de.case_acc" in keys

    def test_dative_detected(self):
        keys = surface_node_keys(self._s("Er hilft dem Kind"), "de")
        assert "de.case_dat" in keys

    def test_genitive_detected_des(self):
        keys = surface_node_keys(self._s("Das Buch des Mannes"), "de")
        assert "de.case_gen" in keys

    def test_genitive_detected_eines(self):
        keys = surface_node_keys(self._s("Das Ende eines Tages"), "de")
        assert "de.case_gen" in keys

    def test_genitive_not_triggered_by_accusative(self):
        keys = surface_node_keys(self._s("Ich sehe den Mann"), "de")
        assert "de.case_gen" not in keys

    def test_empty_text_returns_empty(self):
        assert surface_node_keys({"de": ""}, "de") == []

    def test_missing_lang_key_returns_empty(self):
        assert surface_node_keys({"es": "Hola"}, "de") == []


class TestSurfaceNodeKeysJapanese:
    def _s(self, ja_text):
        return {"ja": ja_text}

    def test_object_particle_wo(self):
        keys = surface_node_keys(self._s("私は本を読む"), "ja")
        assert "ja.particle_wo" in keys

    def test_locative_ni_with_existence(self):
        keys = surface_node_keys(self._s("本は机の上にあります"), "ja")
        assert "ja.particle_ni_loc" in keys

    def test_directional_ni_without_existence(self):
        keys = surface_node_keys(self._s("東京に行く"), "ja")
        assert "ja.particle_ni_dir" in keys

    def test_de_particle(self):
        keys = surface_node_keys(self._s("図書館で勉強する"), "ja")
        assert "ja.particle_de_loc" in keys

    def test_wa_ga_contrast(self):
        keys = surface_node_keys(self._s("私は魚が好きです"), "ja")
        assert "ja.particle_wa_ga" in keys

    def test_no_wa_ga_if_only_wa(self):
        keys = surface_node_keys(self._s("私は学生です"), "ja")
        assert "ja.particle_wa_ga" not in keys


class TestSurfaceNodeKeysSpanish:
    def _s(self, es_text):
        return {"es": es_text}

    def test_ser_estar_contrast_both_present(self):
        # A single sentence with both ser and estar — rare but tests detection
        keys = surface_node_keys(self._s("Ella está cansada pero es fuerte"), "es")
        assert "es.ser_estar" in keys

    def test_only_ser_no_contrast(self):
        # Only ser — not a ser/estar contrast exercise
        keys = surface_node_keys(self._s("Él es médico"), "es")
        assert "es.ser_estar" not in keys

    def test_direct_object_clitic(self):
        keys = surface_node_keys(self._s("Lo veo todos los días"), "es")
        assert "es.clitic_do" in keys

    def test_indirect_object_clitic(self):
        keys = surface_node_keys(self._s("Le doy el libro"), "es")
        assert "es.clitic_io" in keys

    def test_no_clitics_in_plain_sentence(self):
        keys = surface_node_keys(self._s("Yo como manzanas"), "es")
        assert "es.clitic_do" not in keys
        assert "es.clitic_io" not in keys


# ---------------------------------------------------------------------------
# SkillProfile.de_pt_stage and recommend_mode
# ---------------------------------------------------------------------------

def _master(profile, node_key, mode="r", n=8):
    for _ in range(n):
        profile.record_node_attempt(node_key, True, mode)


class TestDePTStage:
    def test_default_stage_is_1(self):
        p = SkillProfile.default()
        assert p.de_pt_stage() == 1

    def test_stage_2_requires_gender_and_3sg(self):
        p = SkillProfile.default()
        _master(p, "de.article_gender")
        _master(p, "person.3sg")
        assert p.de_pt_stage() == 2

    def test_stage_3_requires_wo_sep(self):
        p = SkillProfile.default()
        _master(p, "de.article_gender")
        _master(p, "person.3sg")
        _master(p, "de.wo_sep")
        assert p.de_pt_stage() == 3

    def test_stage_4_requires_wo_inv(self):
        p = SkillProfile.default()
        _master(p, "de.wo_sep")
        _master(p, "de.wo_inv")
        assert p.de_pt_stage() == 4

    def test_stage_5_requires_wo_v_end(self):
        p = SkillProfile.default()
        _master(p, "de.wo_sep")
        _master(p, "de.wo_inv")
        _master(p, "de.wo_v_end")
        assert p.de_pt_stage() == 5

    def test_implicational_scale_skipping_still_capped(self):
        # Even if wo_v_end is somehow mastered, we report stage 5
        p = SkillProfile.default()
        _master(p, "de.wo_v_end")
        assert p.de_pt_stage() == 5


class TestRecommendMode:
    def test_unseen_returns_r(self):
        p = SkillProfile.default()
        assert p.recommend_mode("tense.TPast") == "r"

    def test_partial_receptive_returns_r(self):
        p = SkillProfile.default()
        for i in range(8):
            p.record_node_attempt("tense.TPast", i < 6, "r")  # 75%, below threshold
        assert p.recommend_mode("tense.TPast") == "r"

    def test_receptive_mastered_returns_p(self):
        p = SkillProfile.default()
        _master(p, "tense.TPast", "r")
        assert p.recommend_mode("tense.TPast") == "p"

    def test_both_mastered_returns_review(self):
        p = SkillProfile.default()
        _master(p, "tense.TPast", "r")
        _master(p, "tense.TPast", "p")
        assert p.recommend_mode("tense.TPast") == "review"
