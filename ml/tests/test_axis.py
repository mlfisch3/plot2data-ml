"""The joint decode of an axis: top-k readings, expected text, linear/log from two labels."""

from __future__ import annotations

import numpy as np
import pytest

from p2d.axis import TickRead, candidates, decode_axis, infer_style, log_like, nice_step, progression
from p2d.ocr import BLANK, CHARS, beam_decode, ctc_score, encode


def logits_for(text: str, weak: dict | None = None, T: int | None = None) -> np.ndarray:
    """CTC log-probs that read `text` confidently; `weak` maps a character index of the text to
    the log-prob of a competing character ('' for the blank) at that character's time step."""
    lab = encode(text)
    frames = []
    for i, c in enumerate(lab):
        frames += [BLANK, c, c]
    T = T or len(frames) + 2
    lp = np.full((T, len(CHARS) + 1), -12.0)
    for t, c in enumerate(frames):
        lp[t, c] = -0.02
    for t in range(len(frames), T):
        lp[t, BLANK] = -0.02
    if weak:
        for i, (comp, l) in weak.items():
            t = 3 * i + 1  # the first frame of character i
            c = BLANK if comp == "" else encode(comp)[0]
            lp[t, c] = l
            lp[t + 1, c] = l
    return lp - np.log(np.exp(lp).sum(1, keepdims=True))


def tick(pos: float, text: str, weak: dict | None = None, keep: int = 6) -> TickRead:
    lp = logits_for(text, weak)
    cands = candidates(lp, keep=keep)
    best = cands[0][0] if cands else ""
    return TickRead(pos, best, 1.0, cands[0][2] if cands else None, lp, cands)


def test_beam_and_forced_score_agree():
    lp = logits_for("-0.5", {0: ("", -0.3)})
    beams = dict(beam_decode(lp, beam=6))
    assert "-0.5" in beams and "0.5" in beams
    assert ctc_score(lp, "-0.5") == pytest.approx(beams["-0.5"], abs=0.05)
    assert ctc_score(lp, "0.5") == pytest.approx(beams["0.5"], abs=0.05)


def test_second_reading_is_taken_when_it_fits_the_axis():
    # "30" read as "80" with "30" a close second; the other labels pin the map down.
    reads = [tick(100, "0"), tick(200, "10"), tick(300, "20"), tick(400, "30", {0: ("8", 0.2)}), tick(500, "40")]
    assert reads[3].text == "80"
    f = decode_axis(reads)
    assert f.scale == "linear" and f.inliers == 5
    assert reads[3].text == "30" and reads[3].source == "beam"
    assert f.to_value(400) == pytest.approx(30, abs=1e-6)


def test_dropped_minus_is_restored_from_the_expected_text():
    # The minus of "-0.5" is missed and the beam kept only the greedy reading: the expected text brings it back.
    reads = [tick(100, "1.0"), tick(200, "0.5"), tick(300, "0.0"), tick(400, "-0.5", {0: ("", 3.0)}, keep=1),
             tick(500, "-1.0")]
    assert reads[3].text == "0.5" and len(reads[3].cands) == 1
    f = decode_axis(reads)
    assert f.inliers == 5
    assert reads[3].text == "-0.5" and reads[3].source == "expected"
    assert f.to_value(400) == pytest.approx(-0.5, abs=1e-6)


def test_three_ticks_one_confident_misread():
    # Either pair explains two labels; the third label's expected text decides which map is right.
    reads = [tick(100, "100", {1: ("8", 2.0)}), tick(200, "200"), tick(300, "300")]
    assert reads[0].text == "180"
    f = decode_axis(reads)
    assert f.to_value(100) == pytest.approx(100, abs=1e-6)
    assert reads[0].text == "100"


def test_two_labels_decide_linear_or_log_from_their_values():
    lin = decode_axis([tick(100, "10"), tick(200, "20")])
    assert lin.scale == "linear"
    lg = decode_axis([tick(100, "10"), tick(200, "100")])
    assert lg.scale == "log"
    pw = decode_axis([tick(100, "10^1"), tick(200, "10^2")])
    assert pw.scale == "log"
    yrs = decode_axis([tick(100, "2000"), tick(200, "2010")])
    assert yrs.scale == "linear"


def test_thin_one_lost_from_a_power_of_ten():
    reads = [tick(400, "10^0"), tick(300, "10^1"), tick(200, "10^2", {0: ("", 3.0)}), tick(100, "10^3")]
    assert reads[2].text in ("0^2", "10^2")
    f = decode_axis(reads)
    assert f.scale == "log" and f.inliers == 4
    assert f.to_value(200) == pytest.approx(100, rel=1e-6)


def test_garbage_label_stays_out():
    reads = [tick(100, "0"), tick(200, "10"), tick(300, "20"), tick(400, "77")]
    f = decode_axis(reads)
    assert f.inliers == 3 and reads[3].source == "outlier"
    assert any("disagreed" in w for w in f.warnings)


def test_style_inference_and_formatting():
    st = infer_style(["$1,000", "$2,000"])
    assert st.dollar and st.thousands and st.decimals == 0
    assert st.format(3000) == ["$3,000"]
    st = infer_style(["0.25", "0.50"])
    assert st.format(0.75) == ["0.75"] and st.format(-0.25) == ["-0.25"]
    st = infer_style(["1e5", "1e6"])
    assert st.format(1e7)[0] == "1e7"
    st = infer_style(["20%", "40%"])
    assert st.format(60) == ["60%"]
    st = infer_style(["1.5k", "2.0k"])
    assert st.format(2500) == ["2.5k"]


def test_arithmetic_progression_beats_a_log_fit_that_absorbs_a_misplaced_label():
    # News graphics put the latest year at the right edge: 2021 drawn where 2020 belongs. Log, slightly
    # concave, explains all six; linear has five and the values are an arithmetic progression: linear.
    reads = [tick(29, "1970"), tick(81, "1980"), tick(133, "1990"), tick(184, "2000"), tick(236, "2010"),
             tick(288, "2021")]
    f = decode_axis(reads, tol_px=3.0)
    assert f.scale == "linear"
    assert reads[5].source == "outlier"


def test_years_are_linear_even_when_log_fits_them_too():
    # Over a short range log10 is nearly straight, so the fit cannot tell; the values can.
    reads = [tick(100, "1960"), tick(200, "1980"), tick(300, "2000")]
    assert decode_axis(reads).scale == "linear"
    assert progression([1960, 1980, 2000], "linear") and not progression([1960, 1980, 2000], "log")
    assert progression([1, 10, 100], "log") and progression([1, 2, 5, 10, 20], "log")
    assert not progression([1, 2, 5], "log") and not progression([0, 10, 100], "log")


def test_nice_steps_and_log_pairs():
    assert nice_step(2.5) and nice_step(0.02) and nice_step(500)
    assert not nice_step(90) and not nice_step(0.7)
    assert log_like(10, 100) and log_like(0.01, 1) and log_like(2, 2000)
    assert not log_like(10, 20) and not log_like(0, 100) and not log_like(3, 30)


def test_sparse_two_tick_prefers_nice_step_over_narrow_label_misread():
    # FRED's DGS10 y-axis: labels 0 through 6 at ~98 px apart, but only "0" and the "1" tick are
    # detected. The "1" crop is 3 px wide; the OCR's top beam is "13" (confident but wrong),
    # with "1" sitting a couple of log-prob below. A 2-tick fit on (0, 13) implies a step of 13
    # per 93-px spacing, which is NOT a nice-locator step; (0, 1) is. Pick the nice-step pair.
    # weak {1: ("", -1.0)} keeps "13" as greedy but lets the beam reach "1" (via a blanked "3")
    # about 2.5 log-prob behind - the gap matches the real FRED-DGS10 OCR failure.
    reads = [tick(633, "0"), tick(541, "13", {1: ("", -1.0)}, keep=8)]
    cand_texts = [t for t, _, _ in reads[1].cands]
    assert "13" in cand_texts and "1" in cand_texts
    # And "13" sits above "1" in log-prob, as in the real failure.
    lp_by_text = {t: lp for t, lp, _ in reads[1].cands}
    assert lp_by_text["13"] > lp_by_text["1"]
    f = decode_axis(reads)
    assert f is not None and f.scale == "linear"
    assert f.to_value(541) == pytest.approx(1.0, abs=1e-6)
    assert f.to_value(633) == pytest.approx(0.0, abs=1e-6)
    assert reads[1].text == "1"


def test_leading_zero_integer_candidates_are_filtered():
    # "03" never comes out of a tick locator - it would read as "3". If the beam surfaces it
    # (one leading-zero wrong beam over the correct "3"), the sparse-axis tiebreak must not
    # pick it over the canonical "3".
    from p2d.axis import _canonical_label

    assert _canonical_label("0") and _canonical_label("0.95")
    assert _canonical_label("10") and _canonical_label("100")
    assert _canonical_label("1e5") and _canonical_label("-5.0")
    assert not _canonical_label("03") and not _canonical_label("007")
    assert not _canonical_label("-03") and not _canonical_label("01.10")


def test_two_tick_axis_still_picks_sensible_fit_when_both_steps_are_nice():
    # The usual 2-tick case must still work: "0" and "6" give step 6 (nice) and read as 6 per tick,
    # not something exotic. Guards against the sparse-axis bonus swinging a well-posed case.
    f = decode_axis([tick(500, "0"), tick(100, "6")])
    assert f is not None and f.scale == "linear"
    assert f.to_value(100) == pytest.approx(6, abs=1e-6)
    assert f.to_value(500) == pytest.approx(0, abs=1e-6)
