"""
Unit tests for translator/pattern.py.

All tests use concrete tree strings taken directly from the generator.py
templates (with real GF function names filled in) so test inputs exactly
match production output.
"""
import pytest
from translator.pattern import GrammarPattern, analyze_tree, _compute_difficulty

# ---------------------------------------------------------------------------
# Canonical tree strings (from generator.py templates, vars substituted)
# ---------------------------------------------------------------------------

TREE_PRESENT_S_V    = "PhrUtt NoPConj (UttS (PredVPS (UsePron i_Pron) (MkVPS (TTAnt TPres ASimul) PPos (UseV run_1_V)))) NoVoc"
TREE_PAST_S_V       = "PhrUtt NoPConj (UttS (PredVPS (UsePron i_Pron) (MkVPS (TTAnt TPast ASimul) PPos (UseV run_1_V)))) NoVoc"
TREE_FUTURE_S_V     = "PhrUtt NoPConj (UttS (PredVPS (UsePron i_Pron) (MkVPS (TTAnt TFut ASimul) PPos (UseV run_1_V)))) NoVoc"
TREE_COND_S_V       = "PhrUtt NoPConj (UttS (PredVPS (UsePron i_Pron) (MkVPS (TTAnt TCond ASimul) PPos (UseV run_1_V)))) NoVoc"
TREE_PRES_PERF_S_V  = "PhrUtt NoPConj (UttS (PredVPS (UsePron i_Pron) (MkVPS (TTAnt TPres AAnter) PPos (UseV run_1_V)))) NoVoc"
TREE_PAST_PERF_S_V  = "PhrUtt NoPConj (UttS (PredVPS (UsePron i_Pron) (MkVPS (TTAnt TPast AAnter) PPos (UseV run_1_V)))) NoVoc"

TREE_NEG_PRES_V     = "PhrUtt NoPConj (UttS (PredVPS (UsePron i_Pron) (MkVPS (TTAnt TPres ASimul) PNeg (UseV run_1_V)))) NoVoc"
TREE_NEG_PAST_V     = "PhrUtt NoPConj (UttS (PredVPS (UsePron i_Pron) (MkVPS (TTAnt TPast ASimul) PNeg (UseV run_1_V)))) NoVoc"

TREE_PROG_PRES_V    = "PhrUtt NoPConj (UttS (PredVPS (UsePron i_Pron) (MkVPS (TTAnt TPres ASimul) PPos (ProgrVP (UseV run_1_V))))) NoVoc"

TREE_QUESTION_V     = "PhrUtt NoPConj (UttQS (UseQCl (TTAnt TPres ASimul) PPos (QuestCl (PredVP (UsePron youSg_Pron) (UseV run_1_V))))) NoVoc"

TREE_V2_PRESENT     = "PhrUtt NoPConj (UttS (PredVPS (UsePron i_Pron) (MkVPS (TTAnt TPres ASimul) PPos (ComplSlash (SlashV2a charge_3_V2) (UsePron it_Pron))))) NoVoc"

TREE_COPULA_PRES    = "PhrUtt NoPConj (UttS (PredVPS (UsePron it_Pron) (MkVPS (TTAnt TPres ASimul) PPos (UseComp (CompAP (PositA fast_1_A)))))) NoVoc"

TREE_NP_DEF_SG      = "PhrUtt NoPConj (UttNP (DetCN (DetQuant DefArt NumSg) (UseN battery_1_N))) NoVoc"
TREE_NP_INDEF_PL    = "PhrUtt NoPConj (UttNP (DetCN (DetQuant IndefArt NumPl) (UseN battery_1_N))) NoVoc"

TREE_ADV_BARE       = "PhrUtt NoPConj (UttAdv quickly_1_Adv) NoVoc"

TREE_ATTR_ADJ       = "PhrUtt NoPConj (UttNP (DetCN (DetQuant DefArt NumSg) (AdjCN (PositA fast_1_A) (UseN thing_1_N)))) NoVoc"

TREE_THEY_V         = "PhrUtt NoPConj (UttS (PredVPS (UsePron they_Pron) (MkVPS (TTAnt TPres ASimul) PPos (UseV run_1_V)))) NoVoc"
TREE_HE_V           = "PhrUtt NoPConj (UttS (PredVPS (UsePron he_Pron) (MkVPS (TTAnt TPres ASimul) PPos (UseV run_1_V)))) NoVoc"


# ---------------------------------------------------------------------------
# Feature extraction
# ---------------------------------------------------------------------------

class TestAnalyzeTreeFeatures:
    def test_utterance_type_S(self):
        p = analyze_tree(TREE_PRESENT_S_V)
        assert p.utt_type == "UttS"

    def test_utterance_type_QS(self):
        p = analyze_tree(TREE_QUESTION_V)
        assert p.utt_type == "UttQS"

    def test_utterance_type_NP(self):
        p = analyze_tree(TREE_NP_DEF_SG)
        assert p.utt_type == "UttNP"

    def test_utterance_type_Adv(self):
        p = analyze_tree(TREE_ADV_BARE)
        assert p.utt_type == "UttAdv"

    def test_tense_present(self):
        p = analyze_tree(TREE_PRESENT_S_V)
        assert p.tense == "TPres"
        assert p.aspect == "ASimul"

    def test_tense_past(self):
        p = analyze_tree(TREE_PAST_S_V)
        assert p.tense == "TPast"
        assert p.aspect == "ASimul"

    def test_tense_future(self):
        p = analyze_tree(TREE_FUTURE_S_V)
        assert p.tense == "TFut"

    def test_tense_conditional(self):
        p = analyze_tree(TREE_COND_S_V)
        assert p.tense == "TCond"

    def test_aspect_perfect(self):
        p = analyze_tree(TREE_PRES_PERF_S_V)
        assert p.aspect == "AAnter"

    def test_polarity_positive(self):
        p = analyze_tree(TREE_PRESENT_S_V)
        assert p.polarity == "PPos"

    def test_polarity_negative(self):
        p = analyze_tree(TREE_NEG_PRES_V)
        assert p.polarity == "PNeg"

    def test_person_1sg(self):
        p = analyze_tree(TREE_PRESENT_S_V)
        assert p.person == "i_Pron"

    def test_person_2sg_question(self):
        p = analyze_tree(TREE_QUESTION_V)
        assert p.person == "youSg_Pron"

    def test_person_3pl(self):
        p = analyze_tree(TREE_THEY_V)
        assert p.person == "they_Pron"

    def test_person_3sgm(self):
        p = analyze_tree(TREE_HE_V)
        assert p.person == "he_Pron"

    def test_verb_cat_V(self):
        p = analyze_tree(TREE_PRESENT_S_V)
        assert p.verb_cat == "UseV"

    def test_verb_cat_V2(self):
        p = analyze_tree(TREE_V2_PRESENT)
        assert p.verb_cat == "SlashV2a"

    def test_verb_cat_copula(self):
        p = analyze_tree(TREE_COPULA_PRES)
        assert p.verb_cat == "UseComp"

    def test_progressive_true(self):
        p = analyze_tree(TREE_PROG_PRES_V)
        assert p.progressive is True
        assert p.verb_cat == "UseV"  # ProgrVP wraps UseV — should not become verb_cat

    def test_progressive_false(self):
        p = analyze_tree(TREE_PRESENT_S_V)
        assert p.progressive is False

    def test_attributive_true(self):
        p = analyze_tree(TREE_ATTR_ADJ)
        assert p.attributive is True

    def test_attributive_false(self):
        p = analyze_tree(TREE_COPULA_PRES)
        assert p.attributive is False

    def test_np_has_no_tense(self):
        p = analyze_tree(TREE_NP_DEF_SG)
        assert p.tense is None
        assert p.aspect is None

    def test_adv_has_no_tense(self):
        p = analyze_tree(TREE_ADV_BARE)
        assert p.tense is None


# ---------------------------------------------------------------------------
# Difficulty scoring
# ---------------------------------------------------------------------------

class TestDifficulty:
    @pytest.mark.parametrize("tree, expected_range", [
        (TREE_NP_DEF_SG,     (1, 1)),  # A1 fragment
        (TREE_ADV_BARE,      (1, 1)),  # A1 fragment
        (TREE_COPULA_PRES,   (1, 2)),  # copula present = A1-A2
        (TREE_PRESENT_S_V,   (2, 2)),  # A2 present simple
        (TREE_PAST_S_V,      (2, 2)),  # A2 past simple
        (TREE_FUTURE_S_V,    (3, 3)),  # B1 future
        (TREE_NEG_PRES_V,    (3, 3)),  # B1 negation
        (TREE_PROG_PRES_V,   (3, 3)),  # B1 progressive
        (TREE_COND_S_V,      (4, 4)),  # B2 conditional
        (TREE_PRES_PERF_S_V, (4, 4)),  # B2 present perfect
        (TREE_PAST_PERF_S_V, (4, 4)),  # B2 past perfect
        (TREE_QUESTION_V,    (3, 3)),  # B1 question
        (TREE_THEY_V,        (3, 3)),  # B1 non-default person
        (TREE_NEG_PAST_V,    (3, 3)),  # negation + past = 2+1 = 3
    ])
    def test_difficulty_range(self, tree, expected_range):
        p = analyze_tree(tree)
        lo, hi = expected_range
        assert lo <= p.difficulty <= hi, \
            f"{tree[:60]!r} → difficulty {p.difficulty}, expected [{lo},{hi}]"

    def test_difficulty_capped_at_5(self):
        # Past perfect + negative + non-default person + question → many modifiers
        tree = ("PhrUtt NoPConj (UttQS (UseQCl (TTAnt TPast AAnter) PNeg "
                "(QuestCl (PredVP (UsePron they_Pron) (UseV run_1_V))))) NoVoc")
        p = analyze_tree(tree)
        assert p.difficulty == 5

    def test_difficulty_minimum_1(self):
        p = analyze_tree(TREE_NP_DEF_SG)
        assert p.difficulty >= 1


# ---------------------------------------------------------------------------
# GrammarPattern properties
# ---------------------------------------------------------------------------

class TestGrammarPatternProperties:
    def test_cefr_band_mapping(self):
        for diff, band in [(1, "A1"), (2, "A2"), (3, "B1"), (4, "B2"), (5, "C1")]:
            p = analyze_tree(TREE_PRESENT_S_V)
            # Build a pattern directly with known difficulty
            gp = GrammarPattern(
                utt_type="UttS", tense="TPres", aspect="ASimul",
                polarity="PPos", person="i_Pron", verb_cat="UseV",
                progressive=False, attributive=False, difficulty=diff,
            )
            assert gp.cefr_band == band

    def test_label_present_simple(self):
        p = analyze_tree(TREE_PRESENT_S_V)
        assert "present" in p.label
        assert "simple" in p.label

    def test_label_past_negative(self):
        p = analyze_tree(TREE_NEG_PAST_V)
        assert "past" in p.label
        assert "negative" in p.label

    def test_label_np_fragment(self):
        p = analyze_tree(TREE_NP_DEF_SG)
        assert "NP" in p.label or "fragment" in p.label

    def test_label_progressive(self):
        p = analyze_tree(TREE_PROG_PRES_V)
        assert "progressive" in p.label

    def test_label_question(self):
        p = analyze_tree(TREE_QUESTION_V)
        assert "question" in p.label

    def test_hashable_usable_as_dict_key(self):
        p = analyze_tree(TREE_PRESENT_S_V)
        d = {p: 1}
        d[p] += 1
        assert d[p] == 2

    def test_same_tree_same_pattern(self):
        p1 = analyze_tree(TREE_PRESENT_S_V)
        p2 = analyze_tree(TREE_PRESENT_S_V)
        assert p1 == p2

    def test_different_trees_different_patterns(self):
        p1 = analyze_tree(TREE_PRESENT_S_V)
        p2 = analyze_tree(TREE_PAST_S_V)
        assert p1 != p2

    def test_usable_in_counter(self):
        from collections import Counter
        patterns = [analyze_tree(t) for t in [
            TREE_PRESENT_S_V, TREE_PRESENT_S_V, TREE_PAST_S_V
        ]]
        counts = Counter(patterns)
        assert counts[analyze_tree(TREE_PRESENT_S_V)] == 2
        assert counts[analyze_tree(TREE_PAST_S_V)] == 1
