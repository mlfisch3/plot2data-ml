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


def test_sub_decade_log_never_wins_when_a_linear_fit_also_explains_the_labels():
    # 03-women-men-percent in the real set: six year labels with the current year drawn at the
    # right edge (1970, 1980, 1990, 2000, 2010, 2021). Over a 50-year window log10(year) is near
    # linear, so a log fit through two years happens to inlier the other four within half a pixel
    # of the linear fit's inliers; the specific tick positions matter. The real-world positions
    # (fractional, from the detection head) are such that NO linear pair inliers all six at
    # tol_px=3 - the best linear fit has to drop one tick as an outlier, or force "2020" via
    # expected_text (which pays a steep ctc penalty vs the actual "2021" greedy). Log, in
    # contrast, inliers all six because log10's slight curvature over 50 years happens to make
    # up for the single-pixel jitter the detections sit on. Without a sub-decade physical sanity
    # check, log wins even though no chart author would draw a log axis across a 1.03x range.
    # The crucial trigger is the "2021" tick having enough log-prob mass on "2020" that the
    # expected-text branch accepts the forced value, which turns linear's score from
    # (5-chosen - outlier_cost + prog + step) into (5-chosen + weak_extra + prog + step), the
    # weak_extra bringing linear below log 6-chosen's score.
    reads = [tick(29.034, "1970"), tick(80.861, "1980"), tick(132.389, "1990"),
             tick(183.828, "2000"), tick(235.835, "2010"),
             tick(288.055, "2021", {3: ("0", -6.0)})]
    f = decode_axis(reads, tol_px=3.0)
    assert f is not None
    assert f.scale == "linear", f"expected linear, got {f.scale} (b={f.b}, inliers={f.inliers})"
    # The axis is read at ~0.19 years/px (the real chart is a 50-year span over ~260 px).
    assert 0.15 < f.b < 0.25


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


def test_tick_values_offset_from_step_grid_lose_to_aligned_alternative():
    # owid-co2-per-capita y-axis: labels "5 t", "10 t", "15 t", "20 t", "25 t" with the lowercase
    # 't' misread as a digit '1'. The beam carries both the misread "N1" and the stripped "N"
    # for every tick. Both readings form a nice-step linear progression (step 50 vs step 5), but
    # the step-50 fit's values are consistently offset by +1 from k*50 - the signature of OCR
    # trailing-digit noise. The alignment-to-step prior in `decode_axis` lets the aligned step-5
    # fit win when the per-tick CTC gap is comparable to the real-chart gap (around 0.3 nats).
    # Here we hand-craft the candidate lists to keep this test independent of beam-decoder noise.
    pos = [530, 430, 330, 230, 130]  # bottom to top, 100 px apart
    pairs = [("51", 51, "5", 5), ("101", 101, "10", 10), ("151", 151, "15", 15),
             ("201", 201, "20", 20), ("251", 251, "25", 25)]
    reads = []
    for p, (big, bv, sm, sv) in zip(pos, pairs):
        lp_big, lp_sm = -0.3, -1.0  # beam LPs: big is ahead per tick, matching real-OCR gap
        # Any logits array is fine as long as it is finite; `cands` is what `decode_axis` reads.
        logits = np.full((8, len(CHARS) + 1), -12.0)
        logits -= np.log(np.exp(logits).sum(1, keepdims=True))
        tr = TickRead(p, big, 1.0, bv, logits, [(big, lp_big, float(bv)), (sm, lp_sm, float(sv))])
        reads.append(tr)
    f = decode_axis(reads)
    assert f is not None and f.scale == "linear"
    # Fit should give step 5 (values 5, 10, 15, 20, 25), not step 50 (values 51, 101, 151, 201, 251).
    assert f.to_value(530) == pytest.approx(5, abs=1e-6)
    assert f.to_value(130) == pytest.approx(25, abs=1e-6)


def test_billion_scale_fit_survives_the_keep_hyps_cut_against_two_tick_small_values():
    # owid-cumulative-co2 y-axis: five billion-scale ticks ("100 billion t", "200 billion t", ...,
    # "500 billion t") plus one spurious small-value tick ("0" from OCR noise). The billion-scale
    # readings have deeply negative CTC log-prob (long noisy text), so a 2-tick small-value fit
    # has higher per-tick confidence; the dedup-by-value + widened keep_hyps + progression bonus
    # keep the 5-tick billion fit in the pool and let it win on inlier count.
    pos = [530, 430, 330, 230, 130]
    reads = [tick(p, s) for p, s in zip(pos, ["100b n", "200b n", "300b n", "400b n", "500b n"])]
    # Plus one noise tick with value "5" at pos 630 (what used to be the OCR'd "0 t" bottom tick).
    reads.append(tick(630, "5"))
    f = decode_axis(reads)
    assert f is not None and f.scale == "linear"
    # The axis should map pos 130 to about 500e9 and pos 530 to about 100e9.
    assert f.to_value(130) == pytest.approx(5e11, rel=0.02)
    assert f.to_value(530) == pytest.approx(1e11, rel=0.02)
