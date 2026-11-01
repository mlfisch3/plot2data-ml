"""Decoding an axis as a whole: the labels of one axis are not independent readings.

The printed values on an axis form a progression, linear or logarithmic, with a
regular step, so one map from pixel position to value explains every label at
once. That is used three ways:

1. Each label keeps its top-k CTC readings, not only the greedy one, and the
   map is searched over pairs of readings (RANSAC in reading space): a label
   whose best reading is off by a digit, but whose second reading fits the map
   the other labels agree on, is read correctly.
2. Where no reading of a label fits, the map says what the label should say:
   its expected value is formatted in the style of the labels that did fit, and
   that text is scored under the label's own CTC log-probabilities. If the
   reader finds it plausible (a dropped minus, a thin "1" lost from "10^3", a
   decimal point missed), the label joins the fit at that value.
3. With only two usable labels, linear and log fit alike; the decision then
   follows the values: a nice linear step (1, 2, 2.5, 5 x 10^k) against powers
   of ten a decade or more apart.

Hypotheses are kept to the end: a three-label axis with one confident misread
ties in the pair search (either pair explains two labels), and only the
expected-text step, which reads the third label under each map, can tell them
apart.
"""

from __future__ import annotations

import itertools
import math
import re
from dataclasses import dataclass, field

import numpy as np

from .calibrate import AxisFit
from .ocr import beam_decode, ctc_score, parse_value


@dataclass
class TickRead:
    pos: float
    text: str  # the reading used (greedy at first, corrected by the decode)
    conf: float
    value: float | None
    logits: np.ndarray | None = None  # T x C log-probs from the reader
    cands: list[tuple[str, float, float]] = field(default_factory=list)  # (text, log P, value), parsable only
    source: str = "greedy"  # greedy | beam | expected | outlier | none

    def as_tuple(self) -> tuple[float, str, float, float | None]:
        return (self.pos, self.text, self.conf, self.value)


_LEADING_ZERO_INT = re.compile(r"^-?0[0-9]")


def _canonical_label(text: str) -> bool:
    """Reject uncanonical label texts that a chart tick locator would not produce.

    A matplotlib or Chart.js tick locator never prints "03" for the value 3, or
    "007" for 7, or "01.10" for 1.1: a leading zero before another digit is a
    reading artefact, not a label a chart draws. On a sparse axis (two labels
    read), such a reading poisons the fit and the correct beam alternative
    ("1", "1.10") sits a few log-prob below it; filtering here keeps the
    nice-step tiebreak honest without touching log-prob scoring.
    """
    t = text.strip()
    # Strip a leading currency sign or opening paren so "$01" and "(03" are caught.
    body = t.lstrip("$(")
    if _LEADING_ZERO_INT.match(body):
        return False
    return True


def candidates(logits: np.ndarray, beam: int = 8, keep: int = 6, floor: float = -14.0) -> list[tuple[str, float, float]]:
    """The parsable readings of one label from a beam search, best first."""
    out = []
    seen = set()
    for text, lp in beam_decode(logits, beam=beam):
        v = parse_value(text)
        if v is None or not math.isfinite(v) or text in seen:
            continue
        if not _canonical_label(text):
            continue
        if out and lp < out[0][1] + floor:
            break
        seen.add(text)
        out.append((text, lp, v))
        if len(out) >= keep:
            break
    return out


# --- the style of an axis's labels, to print what a label should say ----------

_SUFFIX = {"k": 1e3, "K": 1e3, "M": 1e6, "B": 1e9, "bn": 1e9, "G": 1e9, "T": 1e12}


@dataclass
class Style:
    decimals: int = 0
    thousands: bool = False
    dollar: bool = False
    percent: bool = False
    suffix: str = ""
    sci: str | None = None  # "e+" (1.5e+08), "e" (1e5), "pow" (10^3, 2x10^3)
    paren_neg: bool = False

    def format(self, v: float) -> list[str]:
        """The printed forms of value v in this style, the most likely first."""
        if self.sci == "pow":
            if v <= 0:
                return []
            e = int(math.floor(math.log10(v) + 1e-9))
            m = v / 10.0 ** e
            if abs(m - 1) < 1e-6:
                return [f"10^{e}"]
            ms = f"{m:.{self.decimals}f}" if self.decimals else f"{m:g}"
            return [f"{ms}x10^{e}"]
        if self.sci in ("e+", "e"):
            if v == 0:
                return ["0e+00", "0"]
            e = int(math.floor(math.log10(abs(v))))
            m = v / 10.0 ** e
            if round(abs(m), self.decimals) >= 10:
                e += 1
                m /= 10
            body = f"{abs(m):.{self.decimals}f}"
            sign = "-" if v < 0 else ""
            if self.sci == "e+":
                return [f"{sign}{body}e{'+' if e >= 0 else '-'}{abs(e):02d}", f"{sign}{body}e{e}"]
            return [f"{sign}{body}e{e}", f"{sign}{body}e{'+' if e >= 0 else '-'}{abs(e):02d}"]
        x = v / _SUFFIX[self.suffix] if self.suffix else v
        a = abs(x)
        body = f"{a:,.{self.decimals}f}" if self.thousands else f"{a:.{self.decimals}f}"
        if self.dollar:
            body = "$" + body
        body += self.suffix
        if self.percent:
            body += "%"
        neg = x < 0 and float(f"{a:.{self.decimals}f}") != 0
        if not neg:
            return [body]
        return [f"({body})", "-" + body] if self.paren_neg else ["-" + body]


def infer_style(texts: list[str]) -> Style:
    """The common printing style of the labels that fit the map."""
    st = Style()
    if not texts:
        return st
    if any("^" in t for t in texts):
        st.sci = "pow"
        mant = [t.split("x10^")[0] for t in texts if "x10^" in t]
        st.decimals = max((len(m.split(".")[1]) if "." in m else 0) for m in mant) if mant else 0
        return st
    if any(re.search(r"\d[eE][-+]?\d", t) for t in texts):
        st.sci = "e+" if any(re.search(r"[eE][-+]\d\d", t) for t in texts) else "e"
        bodies = [re.split(r"[eE]", t)[0] for t in texts]
        st.decimals = max((len(b.split(".")[1]) if "." in b else 0) for b in bodies)
        return st
    st.dollar = any("$" in t for t in texts)
    st.percent = any(t.endswith("%") for t in texts)
    st.paren_neg = any(t.startswith("(") for t in texts)
    for suf in ("bn", "k", "K", "M", "B", "G", "T"):
        if any(t.rstrip("%)").endswith(suf) for t in texts):
            st.suffix = suf
            break
    st.thousands = any("," in t for t in texts)
    decs = []
    for t in texts:
        body = re.sub(r"[^\d.]", "", t)
        decs.append(len(body.split(".")[1]) if "." in body else 0)
    st.decimals = max(decs)
    return st


# --- the decode --------------------------------------------------------------

def nice_step(s: float) -> bool:
    """A step a tick locator would choose: 1, 2, 2.5, 5 x 10^k, and the looser ones some charts use.

    The step comes from a fit to pixel positions, so it is close to the printed step but not
    exact: a label step of 0.1 may come back as 0.09997, whose log10 floors a decade below and
    whose mantissa then reads as 9.997. The floor is nudged up by 1e-3 so a step just under
    the decade boundary stays in its own decade; the mantissa is compared to a 2% tolerance.
    """
    if not (s > 0 and math.isfinite(s)):
        return False
    e = math.floor(math.log10(s) + 1e-3)
    m = s / 10.0 ** e
    return any(abs(m - k) <= 0.02 * k for k in (1, 1.5, 2, 2.5, 3, 4, 5, 6, 7.5, 8))


def log_like(v1: float, v2: float) -> bool:
    """Two values a log axis would print a decade or more apart: k x 10^n with k in 1, 2, 5."""
    if v1 <= 0 or v2 <= 0:
        return False
    for v in (v1, v2):
        m = v / 10.0 ** math.floor(math.log10(v) + 1e-9)
        if not any(abs(m - k) < 1e-6 * k for k in (1, 2, 5)):
            return False
    return max(v1, v2) / min(v1, v2) >= 10 - 1e-9


def progression(values, scale: str) -> bool:
    """Do these label values (three or more) form the progression a `scale` axis prints?

    Linear: constant differences. Log: constant ratios, or the 1-2-5 decade
    pattern. A linear axis's labels can also be nearly collinear in log space
    over a short range (1960, 1980, 2000), which is why the fit alone cannot
    decide and the values must.
    """
    v = np.sort(np.asarray(values, float))
    if len(v) < 3:
        return False
    if scale == "linear":
        d = np.diff(v)
        return bool(np.all(np.abs(d - d[0]) <= 1e-6 * max(abs(v[-1] - v[0]), 1e-300)))
    if np.any(v <= 0):
        return False
    r = np.diff(np.log10(v))
    if np.all(np.abs(r - r[0]) <= 1e-6) and r[0] >= 0.3 - 1e-9:
        return True
    m = v / 10.0 ** np.floor(np.log10(v) + 1e-9)
    ok = np.all([any(abs(x - k) < 1e-6 * k for k in (1, 2, 5)) for x in m])
    return bool(ok and v[-1] / v[0] >= 10 - 1e-9)


def _tf(v: np.ndarray, scale: str) -> np.ndarray:
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.log10(np.where(v > 0, v, np.nan)) if scale == "log" else np.asarray(v, float)


@dataclass
class _Hyp:
    scale: str
    chosen: dict  # tick index -> (text, log P, value)
    score: float
    fit: AxisFit | None = None


def _search(reads: list[TickRead], idx: list[int], tol_px: float, outlier_cost: float, keep: int) -> list[_Hyp]:
    """RANSAC over pairs of readings: the maps that explain the most readings, best `keep` of them."""
    ti, tv, tl, tt = [], [], [], []
    for i in idx:
        for text, lp, v in reads[i].cands:
            ti.append(i)
            tv.append(v)
            tl.append(lp)
            tt.append(text)
    ti = np.array(ti)
    tv = np.array(tv, float)
    tl = np.array(tl, float)
    pos = np.array([r.pos for r in reads], float)
    hyps: dict[tuple, _Hyp] = {}
    for scale in ("linear", "log"):
        t_all = _tf(tv, scale)
        ok_c = np.isfinite(t_all)
        for i, j in itertools.combinations(idx, 2):
            if abs(pos[i] - pos[j]) < 3:
                continue
            ci = np.nonzero((ti == i) & ok_c)[0]
            cj = np.nonzero((ti == j) & ok_c)[0]
            for a_i in ci:
                for b_j in cj:
                    if t_all[a_i] == t_all[b_j]:
                        continue
                    b = (t_all[b_j] - t_all[a_i]) / (pos[j] - pos[i])
                    a = t_all[a_i] - b * pos[i]
                    err = np.abs((t_all - a) / b - pos[ti])
                    fit = ok_c & (err <= tol_px)
                    chosen = {i: a_i, j: b_j}
                    score = tl[a_i] + tl[b_j]
                    for k in idx:
                        if k == i or k == j:
                            continue
                        ck = np.nonzero(fit & (ti == k))[0]
                        if len(ck):
                            c = ck[np.argmax(tl[ck])]
                            chosen[k] = c
                            score += tl[c]
                        else:
                            score -= outlier_cost
                    key = (scale, tuple(sorted(chosen.items())))
                    if key not in hyps:
                        hyps[key] = _Hyp(scale, {k: (tt[c], float(tl[c]), float(tv[c])) for k, c in chosen.items()}, score)
    out = sorted(hyps.values(), key=lambda h: -h.score)
    return out[:keep]


def _refit(reads: list[TickRead], values: dict, scale: str) -> AxisFit | None:
    which = sorted(values)
    p = np.array([reads[i].pos for i in which], float)
    t = _tf(np.array([values[i] for i in which], float), scale)
    ok = np.isfinite(t)
    if ok.sum() < 2:
        return None
    A = np.column_stack([np.ones(ok.sum()), p[ok]])
    (a, b), *_ = np.linalg.lstsq(A, t[ok], rcond=None)
    if b == 0 or not np.isfinite(b):
        return None
    resid = float(np.sqrt(np.mean(((t[ok] - a) / b - p[ok]) ** 2)))
    return AxisFit(scale=scale, a=float(a), b=float(b), inliers=int(ok.sum()), used=len(reads), resid_px=resid,
                   warnings=[])


def expected_text(r: TickRead, fit: AxisFit, style: Style, tol_px: float, margin: float) -> tuple[str, float, float] | None:
    """What the label at r.pos should print under `fit`, if the reader finds that text plausible.

    Returns (text, value, log P) or None.
    """
    t = fit.a + fit.b * r.pos
    if fit.scale == "log":
        e = math.floor(t)
        opts = sorted([e, e + 1] + [e + math.log10(k) for k in (2, 5)], key=lambda x: abs(x - t))
        values = [10.0 ** o for o in opts[:2]]
    elif style.sci in ("e+", "e"):
        values = [float(f"{t:.{style.decimals}e}")]
    elif style.suffix:
        u = _SUFFIX[style.suffix]
        values = [float(f"{t / u:.{style.decimals}f}") * u]
    else:
        values = [float(f"{t:.{style.decimals}f}")]
    top = max((lp for _, lp, _ in r.cands), default=None)
    ref = top if top is not None else (ctc_score(r.logits, r.text) if r.text else -30.0)
    best = None
    for v in values:
        if abs(float(fit.to_pos(v)) - r.pos) > tol_px:
            continue
        for s in style.format(v):
            sc = ctc_score(r.logits, s)
            if best is None or sc > best[2]:
                best = (s, v, sc)
    if best is None or best[2] < ref - margin:
        return None
    return best


def decode_axis(reads: list[TickRead], tol_px: float = 3.0, hint: str | None = None, outlier_cost: float = 7.0,
                expect_margin: float = 12.0, keep_hyps: int = 6, prog_bonus: float = 8.0) -> AxisFit | None:
    """Fit the axis to the readings of its labels jointly; `reads` are updated in place with what was used."""
    for r in reads:
        r.source = "greedy" if r.cands else "none"
    idx = [i for i, r in enumerate(reads) if r.cands]
    if len(idx) < 2:
        return None
    hyps = _search(reads, idx, tol_px, outlier_cost, keep_hyps)
    if not hyps:
        return None
    pos = np.array([r.pos for r in reads], float)
    spacing = float(np.median(np.diff(np.sort(pos)))) if len(pos) > 1 else 0.0
    final = []
    for h in hyps:
        values = {k: v for k, (_, _, v) in h.chosen.items()}
        fit = _refit(reads, values, h.scale)
        if fit is None:
            continue
        style = infer_style([t for t, _, _ in h.chosen.values()])
        score = sum(lp for _, lp, _ in h.chosen.values())
        extra = {}
        for k, r in enumerate(reads):
            if k in values or r.logits is None:
                continue
            got = expected_text(r, fit, style, tol_px, expect_margin)
            if got is not None:
                extra[k] = got
                score += got[2]
            else:
                score -= outlier_cost
        if extra:
            fit2 = _refit(reads, {**values, **{k: v for k, (_, v, _) in extra.items()}}, h.scale)
            if fit2 is not None:
                fit = fit2
        # Regular progressions are what tick locators make. Labels in an arithmetic progression are a
        # linear axis even where log explains one more (misplaced) label; a geometric one is log.
        all_values = list(values.values()) + [v for _, v, _ in extra.values()]
        if progression(all_values, h.scale):
            score += prog_bonus
        if h.scale == "log":
            # A log axis spans decades by construction: tick labels run through powers of ten
            # (optionally with 2x and 5x intra-decade ticks), and a locator that emits labels all
            # within one decade is a linear axis. Year labels (1970, 1980, ..., 2021) are near-
            # linear in log over a short range and so can inlier a log fit by coincidence; the
            # 2-tick tiebreaker already requires `max/min >= 10` via `log_like`, extend the same
            # physical sanity to multi-tick fits so a near-flat log slope can never beat a true
            # linear fit whose values live within a single decade.
            pos_vals = [v for v in all_values if v > 0]
            if pos_vals and max(pos_vals) / min(pos_vals) < 10 - 1e-9:
                score -= prog_bonus
        if h.scale == "linear" and spacing > 0:
            # Tick locators (matplotlib, Chart.js, D3) only emit nice steps - 1, 2, 2.5, 5 x 10^k.
            # On a sparse axis (two chosen labels, no third confirming), a 2-tick fit whose
            # implied step is NOT nice is almost always a misread of one of the two labels,
            # and the right beam alternative (whose step IS nice) is only a few log-prob behind.
            # Weight the nice-step prior strongly in that regime; keep the mild +1 bonus for
            # three-or-more-tick fits, where RANSAC inlier counts already dominate.
            is_nice = nice_step(abs(fit.b) * spacing)
            sparse = len(h.chosen) <= 2 and not extra
            if is_nice:
                score += 5.0 if sparse else 1.0
            elif sparse:
                score -= 3.0
        final.append((score, h, fit, extra))
    if not final:
        return None
    final.sort(key=lambda f: -f[0])
    score, h, fit, extra = final[0]
    scale = h.scale
    used = dict(h.chosen)
    # Both scales explain the same two labels: decide on the values.
    if len(used) + len(extra) == 2 and len(h.chosen) == 2:
        (t1, _, v1), (t2, _, v2) = h.chosen.values()
        texts = [t1, t2]
        looks_log = hint == "log" or any("^" in t for t in texts) or (log_like(v1, v2) and not nice_step(abs(v2 - v1)))
        if any(re.search(r"\d[eE][-+]?\d", t) for t in texts) and log_like(v1, v2):
            looks_log = True
        want = "log" if looks_log else "linear"
        if want != scale:
            alt = next((f for f in final if f[1].scale == want and set(f[1].chosen) == set(h.chosen)), None)
            if alt is not None:
                score, h, fit, extra = alt
                scale, used = h.scale, dict(h.chosen)
            else:
                f2 = _refit(reads, {k: v for k, (_, _, v) in h.chosen.items()}, want)
                if f2 is not None:
                    fit, scale = f2, want
        fit.warnings.append("only two ticks read: linear/log decided from the labels")
    for k, r in enumerate(reads):
        if k in used:
            t, _, v = used[k]
            r.text, r.value = t, v
            r.source = "greedy" if r.cands and r.cands[0][0] == t else "beam"
        elif k in extra:
            r.text, r.value, r.source = extra[k][0], extra[k][1], "expected"
        elif r.cands:
            r.source = "outlier"
    unused = sum(1 for r in reads if r.logits is not None) - len(used) - len(extra)
    if unused > 0:
        fit.warnings.append(f"{unused} tick label(s) disagreed with the rest and were ignored")
    fit.used = len(reads)
    return fit
