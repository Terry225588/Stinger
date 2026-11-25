"""用题干找到题库条目，再用选项文字对应画面上的字母。

评分是内部排序用的，不是识别正确率，也不是答对率。
同一题干有多道题、题干太短、或选项对不上时，不给出确定答案。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from difflib import SequenceMatcher

from screenmatch.bank import Question, QuestionBank
from screenmatch.normalize import normalize_match_text
from screenmatch.ocr_text import ParsedScreen, parse_ocr_text

SHORT_STEM = 8
CANDIDATE_MIN = 0.72
MEDIUM_SCORE = 0.88
NEAR_RATIO = 0.94
OPTION_PAIR_MIN = 0.86
BAND = 0.02

LETTER_UNMAPPED = (
    "画面上的选项文字没能和题库可靠对应。"
    "下面的字母是题库里原来记下的字母；网页如果打乱了选项，字母会不一样。"
    "请以答案原文为准。"
)
LETTER_REMAPPED = "已按当前画面里的选项文字对应字母。题库记录的字母是 {stored}。请仍核对答案原文。"
REASON_MEDIUM = "题干只是部分相符，或相似度有限。可以看答案原文，但不要把它当成唯一答案。"
REASON_SHORT = "识别到的题干很短，容易和别的题撞上。请对照完整题目。"
REASON_LOW = "只有较弱的相似题目。下面列出可能的题，没有确定答案。"
REASON_AMBIGUOUS = (
    "同一题干在题库里对应多道题，或有几道题得分接近。"
    "只看题干不能确定答案。请用画面上的选项区分；在此之前不要采用其中任何一道的答案。"
)
REASON_SAME_ANSWER_NEAR = (
    "这些题规范化之后题干相同，选项和答案也相同。"
    "答案原文可以对照，但每一行都要留下：保命题标记可能不同，不能合并成一条。"
)
REASON_SHORT_LIST = "题干太短，只按包含关系列出部分题目，没有确定答案。"
REASON_SIMILAR = "有一两处用字不同。上面的数字是相似度，不是逐字确定，也不是正确率。"
REASON_PARTIAL = "只对上了题干的一段。这是片段候选，不是逐字核对通过。"
REASON_REVIEW = "前几名相似度接近，但答案不一样。需要复核，先不要只采用第一条。"
_NEG_PHRASES = ("不得", "不能", "不应", "不可以", "不可", "禁止", "不许", "严禁", "勿")
_UNITS = ("千米", "厘米", "毫米", "公斤", "千克", "毫克", "千瓦", "千伏", "分钟", "小时", "米", "伏", "安", "瓦", "吨", "秒")


@dataclass(frozen=True)
class StemScore:
    score: float
    exact: bool
    contained: bool
    cover: float
    query_len: int
    bank_len: int


@dataclass(frozen=True)
class OptionPair:
    bank: str
    screen: str
    sim: float


@dataclass(frozen=True)
class Alignment:
    pairs: tuple[OptionPair, ...]

    def mapping(self) -> dict[str, str]:
        return {pair.bank: pair.screen for pair in self.pairs}


@dataclass
class CandidateView:
    question: Question
    score: float
    note: str
    answer_texts: tuple[tuple[str, str], ...] = ()
    bank_letters: str = ""
    screen_letters: str | None = None
    low_match: bool = False


@dataclass
class MatchOutcome:
    status: str
    confident: bool
    chosen: Question | None
    answer_texts: list[tuple[str, str]]
    remapped: str | None
    screen_for_answer: dict[str, str]
    letter_note: str
    reasons: list[str] = field(default_factory=list)
    candidates: list[CandidateView] = field(default_factory=list)
    screen_options: dict[str, str] = field(default_factory=dict)
    screen_stem: str = ""
    verified: bool = False
    score: float = 0.0
    needs_review: bool = False
    needs_more: bool = False
    early: bool = False


def match_text(bank: QuestionBank, text: str) -> MatchOutcome:
    return match_parsed(bank, parse_ocr_text(text))


def match_stem_prefix(bank: QuestionBank, text: str, ready_at: int = 10) -> MatchOutcome | None:
    """约 10 个汉字就可以先查。前缀不唯一时不猜，交给后续完整识别。"""
    import re

    parsed = parse_ocr_text(text or "")
    fingerprint = parsed.fingerprint or stem_fingerprint(text or "")
    han = len(re.findall(r"[\u4e00-\u9fff]", fingerprint))
    if han < ready_at:
        return None
    hits = [question for question in bank.questions if question.fingerprint.startswith(fingerprint)]
    if not hits:
        return None
    if len(hits) > 1:
        rows = [(question, score_stem(fingerprint, question.fingerprint)) for question in hits]
        outcome = _ambiguous(rows, parsed, REASON_AMBIGUOUS)
        outcome.needs_more = True
        outcome.early = True
        outcome.verified = False
        return outcome
    question = hits[0]
    if question.fingerprint == fingerprint:
        outcome = match_parsed(bank, parsed)
        outcome.early = True
        outcome.needs_more = False
        return outcome
    stem_score = score_stem(fingerprint, question.fingerprint)
    outcome = _build(
        question,
        stem_score,
        Alignment(()),
        parsed,
        [(question, stem_score)],
        "partial",
        similar_note=REASON_PARTIAL,
    )
    outcome.early = True
    outcome.needs_more = False
    outcome.verified = False
    return outcome


def match_parsed(bank: QuestionBank, parsed: ParsedScreen) -> MatchOutcome:
    if not bank.questions:
        return _empty("none", "请先导入题库（Excel）。", parsed)
    if not parsed.fingerprint:
        return _empty("none", "没有识别到可以用来匹配的题干。", parsed)

    scored: list[tuple[Question, StemScore]] = []
    for question in bank.questions:
        stem_score = score_stem(parsed.fingerprint, question.fingerprint)
        if stem_score.exact or stem_score.score >= CANDIDATE_MIN:
            scored.append((question, stem_score))
    scored.sort(key=lambda item: (-item[1].score, item[0].source_row))

    if not scored:
        return _short_fragment(bank, parsed) or _empty(
            "none", "没有在题库里找到足够接近的题干。", parsed
        )

    best = scored[0][1].score
    band = [item for item in scored if best - item[1].score <= BAND]
    if len(band) > 1:
        picked = _distinguish([question for question, _score in band], parsed)
        if picked is None:
            return _ambiguous(band, parsed, REASON_AMBIGUOUS)
        question, alignment = picked
        stem_score = next(score for item, score in band if item is question)
        status = _status_after_split(stem_score)
        return _finalize(question, stem_score, alignment, parsed, scored, status, distinguished=True)

    question, stem_score = scored[0]
    status = classify(stem_score, _gap(scored))
    if status == "ambiguous":
        return _ambiguous(scored[:5], parsed, REASON_AMBIGUOUS)
    if status == "low":
        return _low(scored[:5], parsed, REASON_LOW)
    if status == "none":
        return _empty("none", "没有在题库里找到足够接近的题干。", parsed)
    alignment = align_options(parsed.options, question.options)
    return _finalize(question, stem_score, alignment, parsed, scored, status, distinguished=False)


def score_stem(query_fp: str, bank_fp: str) -> StemScore:
    qlen, blen = len(query_fp), len(bank_fp)
    if not query_fp or not bank_fp:
        return StemScore(0.0, False, False, 0.0, qlen, blen)
    if query_fp == bank_fp:
        return StemScore(1.0, True, True, 1.0, qlen, blen)
    contained = False
    cover = 0.0
    shorter = min(qlen, blen)
    if qlen <= blen and query_fp in bank_fp:
        contained = True
        cover = qlen / blen
        shorter = qlen
    elif blen < qlen and bank_fp in query_fp:
        contained = True
        cover = blen / qlen
        shorter = blen
    if contained and shorter >= SHORT_STEM:
        if shorter >= 18 and cover >= 0.70:
            score = 0.97
        elif shorter >= 12 and cover >= 0.45:
            score = 0.90
        else:
            score = 0.78
        return StemScore(score, False, True, cover, qlen, blen)
    if min(qlen, blen) < SHORT_STEM:
        return StemScore(0.0, False, False, 0.0, qlen, blen)
    ratio = SequenceMatcher(None, query_fp, bank_fp).ratio()
    return StemScore(ratio, False, False, 0.0, qlen, blen)


def classify(stem_score: StemScore, gap: float) -> str:
    if stem_score.query_len < SHORT_STEM:
        if stem_score.exact and gap >= 0.05:
            return "medium"
        if stem_score.score >= CANDIDATE_MIN:
            return "low"
        return "none"
    if gap < 0.03 and stem_score.score >= MEDIUM_SCORE:
        return "ambiguous"
    if gap < 0.04:
        return "low" if stem_score.score >= CANDIDATE_MIN else "none"
    if stem_score.exact:
        return "high"
    if stem_score.contained and stem_score.query_len >= 18 and stem_score.cover >= 0.70:
        return "partial"
    if (not stem_score.contained) and stem_score.score >= NEAR_RATIO and stem_score.query_len >= 10:
        return "high"
    if stem_score.contained and stem_score.query_len >= 12 and stem_score.cover >= 0.45:
        return "medium"
    if stem_score.score >= MEDIUM_SCORE:
        return "medium"
    if stem_score.score >= CANDIDATE_MIN:
        return "low"
    return "none"


def align_options(screen: dict[str, str], bank: dict[str, str]) -> Alignment:
    used: set[str] = set()
    pairs: list[OptionPair] = []
    for bank_letter, bank_text in bank.items():
        bank_norm = normalize_match_text(bank_text)
        best_letter = None
        best_sim = 0.0
        for screen_letter, screen_text in screen.items():
            if screen_letter in used:
                continue
            screen_norm = normalize_match_text(screen_text)
            if not bank_norm or not screen_norm:
                continue
            if bank_norm == screen_norm:
                sim = 1.0
            else:
                sim = SequenceMatcher(None, bank_norm, screen_norm).ratio()
            if sim > best_sim:
                best_sim = sim
                best_letter = screen_letter
        if best_letter is not None and best_sim >= OPTION_PAIR_MIN:
            used.add(best_letter)
            pairs.append(OptionPair(bank_letter, best_letter, best_sim))
    return Alignment(tuple(pairs))


def is_sufficient(alignment: Alignment, bank_options: dict[str, str]) -> bool:
    total = len(bank_options)
    matched = len(alignment.pairs)
    if total == 0 or matched == 0:
        return False
    if total <= 2:
        return matched == total and min(pair.sim for pair in alignment.pairs) >= 0.9
    mean = sum(pair.sim for pair in alignment.pairs) / matched
    return matched >= 2 and (matched / total) >= 0.5 and mean >= 0.88


def remap_answer(answer: str, alignment: Alignment, sufficient: bool) -> str | None:
    if not sufficient:
        return None
    mapping = alignment.mapping()
    screen_letters: list[str] = []
    for letter in answer:
        screen_letter = mapping.get(letter)
        if not screen_letter:
            return None
        screen_letters.append(screen_letter)
    remapped = "".join(sorted(set(screen_letters)))
    if len(remapped) != len(set(answer)):
        return None
    return remapped


def score_stem_for_question(query: str, question: Question) -> StemScore:
    return score_stem(query, question.fingerprint)


def _status_after_split(stem_score: StemScore) -> str:
    if stem_score.query_len < SHORT_STEM:
        return "medium" if stem_score.exact else "low"
    if stem_score.exact:
        return "high"
    if stem_score.contained and stem_score.query_len >= 18 and stem_score.cover >= 0.70:
        return "partial"
    if stem_score.score >= NEAR_RATIO:
        return "high"
    return "medium"


def _number_conflict(query: str, bank: str, contained: bool) -> bool:
    import re

    query_numbers = re.findall(r"\d+", query)
    bank_numbers = re.findall(r"\d+", bank)
    if query_numbers == bank_numbers:
        return False
    if any(number not in bank_numbers for number in query_numbers):
        return True
    return not contained


def _bare_bu(text: str) -> int:
    stripped = text
    for phrase in _NEG_PHRASES:
        stripped = stripped.replace(phrase, "")
    return stripped.count("不")


def _unit_list(text: str) -> list[str]:
    found: list[str] = []
    rest = text
    for unit in _UNITS:
        while unit in rest:
            found.append(unit)
            rest = rest.replace(unit, "", 1)
    return found


def describe_conflict(query: str, bank: str, contained: bool) -> str | None:
    """否定、数字或单位变了就不要当成无害错字。片段里仅仅少了一截，不算否定被改掉。"""
    if query == bank:
        return None
    if _number_conflict(query, bank, contained):
        return "题干里的数字对不上"
    if contained:
        return None
    if ("正确" in query) != ("正确" in bank) or ("错误" in query) != ("错误" in bank):
        return "题干里的「正确」或「错误」不一致"
    for phrase in _NEG_PHRASES:
        if (phrase in query) != (phrase in bank):
            return f"否定说法不一致（{phrase}）"
    if _bare_bu(query) != _bare_bu(bank):
        return "否定词「不」不一致"
    if _unit_list(query) != _unit_list(bank):
        return "题干里的单位不一致"
    return None


def edit_size(query: str, bank: str) -> int:
    total = 0
    for tag, i1, i2, j1, j2 in SequenceMatcher(None, query, bank).get_opcodes():
        if tag == "equal":
            continue
        total += max(i2 - i1, j2 - j1)
    return total


def _close_answer_conflict(scored: list[tuple[Question, StemScore]]) -> bool:
    if len(scored) < 2:
        return False
    first_question, first_score = scored[0]
    second_question, second_score = scored[1]
    if first_score.score - second_score.score > 0.08:
        return False
    if second_score.score < 0.80:
        return False
    return first_question.answer != second_question.answer or first_question.qtype != second_question.qtype


def _distinguish(
    questions: list[Question], parsed: ParsedScreen
) -> tuple[Question, Alignment] | None:
    if not parsed.options:
        return None
    ranked: list[tuple[float, Question, Alignment]] = []
    for question in questions:
        alignment = align_options(parsed.options, question.options)
        quality = _quality(alignment, question.options)
        ranked.append((quality, question, alignment))
    ranked.sort(key=lambda item: (-item[0], item[1].source_row))
    best_quality, question, alignment = ranked[0]
    second = ranked[1][0] if len(ranked) > 1 else 0.0
    if best_quality >= 0.88 and best_quality - second >= 0.15:
        return question, alignment
    return None


def _quality(alignment: Alignment, bank_options: dict[str, str]) -> float:
    if not is_sufficient(alignment, bank_options):
        return 0.0
    return sum(pair.sim for pair in alignment.pairs) / len(alignment.pairs)


def _gap(scored: list[tuple[Question, StemScore]]) -> float:
    if len(scored) < 2:
        return 1.0
    return scored[0][1].score - scored[1][1].score


def _view(question: Question, stem_score: StemScore, parsed: ParsedScreen) -> CandidateView:
    alignment = align_options(parsed.options, question.options) if parsed.options else Alignment(())
    sufficient = bool(parsed.options) and is_sufficient(alignment, question.options)
    remapped = remap_answer(question.answer, alignment, sufficient)
    low_match = (not stem_score.exact) and stem_score.score < 0.80
    return CandidateView(
        question=question,
        score=stem_score.score,
        note="低匹配" if low_match else "",
        answer_texts=tuple((letter, question.options.get(letter, "")) for letter in question.answer),
        bank_letters=question.answer,
        screen_letters=remapped,
        low_match=low_match,
    )


def _views(scored: list[tuple[Question, StemScore]], parsed: ParsedScreen) -> list[CandidateView]:
    views: list[CandidateView] = []
    for question, stem_score in scored:
        if not stem_score.exact and stem_score.score < CANDIDATE_MIN:
            continue
        views.append(_view(question, stem_score, parsed))
        if len(views) >= 5:
            break
    return views


def _finalize(
    question: Question,
    stem_score: StemScore,
    alignment: Alignment,
    parsed: ParsedScreen,
    scored: list[tuple[Question, StemScore]],
    status: str,
    *,
    distinguished: bool,
) -> MatchOutcome:
    conflict = describe_conflict(parsed.fingerprint, question.fingerprint, stem_score.contained)
    if conflict and status in {"high", "partial", "medium"}:
        return _ambiguous(scored[:5], parsed, conflict + "。不能把这道题当成已经核对通过。")
    similar_note = None
    if status == "high" and not stem_score.exact:
        if stem_score.contained:
            status = "partial"
        elif edit_size(parsed.fingerprint, question.fingerprint) > 2:
            status = "medium"
        else:
            similar_note = REASON_SIMILAR
    if status == "partial":
        similar_note = REASON_PARTIAL
    needs_review = _close_answer_conflict(scored) and not distinguished
    if needs_review and not stem_score.exact:
        return _ambiguous(scored[:5], parsed, REASON_REVIEW)
    return _build(
        question,
        stem_score,
        alignment,
        parsed,
        scored,
        status,
        similar_note=similar_note,
        needs_review=needs_review,
    )


def _build(
    question: Question,
    stem_score: StemScore,
    alignment: Alignment,
    parsed: ParsedScreen,
    scored: list[tuple[Question, StemScore]],
    status: str,
    *,
    similar_note: str | None = None,
    needs_review: bool = False,
) -> MatchOutcome:
    sufficient = bool(parsed.options) and is_sufficient(alignment, question.options)
    remapped = remap_answer(question.answer, alignment, sufficient)
    mapping = alignment.mapping()
    screen_for = {letter: mapping[letter] for letter in question.answer if remapped and letter in mapping}
    if remapped:
        letter_note = LETTER_REMAPPED.format(stored=question.answer)
    else:
        letter_note = LETTER_UNMAPPED
    reasons: list[str] = []
    if similar_note:
        reasons.append(similar_note)
    if status == "medium":
        reasons.append(REASON_MEDIUM)
    if stem_score.query_len < SHORT_STEM:
        reasons.append(REASON_SHORT)
    if needs_review:
        reasons.append(REASON_REVIEW)
    views = _views(scored, parsed)
    verified = status == "high" and stem_score.exact
    return MatchOutcome(
        status=status,
        confident=status == "high" and verified and not needs_review,
        chosen=question,
        answer_texts=[(letter, question.options.get(letter, "")) for letter in question.answer],
        remapped=remapped,
        screen_for_answer=screen_for,
        letter_note=letter_note,
        reasons=reasons,
        candidates=views,
        screen_options=dict(parsed.options),
        screen_stem=parsed.stem,
        verified=verified,
        score=stem_score.score,
        needs_review=needs_review,
    )


def _same_answer_and_options(questions: list[Question]) -> bool:
    if len(questions) < 2:
        return False
    answers = {question.answer for question in questions}
    option_sets = {
        tuple((letter, normalize_match_text(text)) for letter, text in question.options.items())
        for question in questions
    }
    return len(answers) == 1 and len(option_sets) == 1


def _ambiguous(
    rows: list[tuple[Question, StemScore]], parsed: ParsedScreen, reason: str
) -> MatchOutcome:
    reasons = [reason]
    questions = [question for question, _score in rows]
    if _same_answer_and_options(questions):
        reasons.append(REASON_SAME_ANSWER_NEAR)
    answers = {question.answer for question in questions}
    needs_review = len(answers) > 1 or reason == REASON_REVIEW
    if needs_review and REASON_REVIEW not in reasons and len(answers) > 1:
        reasons.insert(0, REASON_REVIEW)
    views = _views(rows, parsed)
    top_score = rows[0][1].score if rows else 0.0
    return MatchOutcome(
        status="ambiguous",
        confident=False,
        chosen=None,
        answer_texts=[],
        remapped=None,
        screen_for_answer={},
        letter_note="",
        reasons=reasons,
        candidates=views,
        screen_options=dict(parsed.options),
        screen_stem=parsed.stem,
        verified=False,
        score=top_score,
        needs_review=needs_review,
    )


def _low(
    rows: list[tuple[Question, StemScore]], parsed: ParsedScreen, reason: str
) -> MatchOutcome:
    return MatchOutcome(
        status="low",
        confident=False,
        chosen=None,
        answer_texts=[],
        remapped=None,
        screen_for_answer={},
        letter_note="",
        reasons=[reason],
        candidates=_views(rows, parsed),
        screen_options=dict(parsed.options),
        screen_stem=parsed.stem,
        verified=False,
        score=rows[0][1].score if rows else 0.0,
        needs_review=False,
    )


def _short_fragment(bank: QuestionBank, parsed: ParsedScreen) -> MatchOutcome | None:
    query = parsed.fingerprint
    if not (4 <= len(query) < SHORT_STEM):
        return None
    hits = [question for question in bank.questions if query in question.fingerprint]
    if not hits:
        return None
    hits.sort(key=lambda question: (question.source_row, -len(question.fingerprint)))
    rows = [(question, StemScore(0.74, False, True, 0.0, len(query), len(question.fingerprint))) for question in hits[:5]]
    if len(hits) > 1:
        return _ambiguous(rows, parsed, REASON_SHORT_LIST)
    return _low(rows, parsed, REASON_SHORT_LIST)


def _empty(status: str, reason: str, parsed: ParsedScreen) -> MatchOutcome:
    return MatchOutcome(
        status=status,
        confident=False,
        chosen=None,
        answer_texts=[],
        remapped=None,
        screen_for_answer={},
        letter_note="",
        reasons=[reason],
        screen_options=dict(parsed.options),
        screen_stem=parsed.stem,
        verified=False,
        score=0.0,
        needs_review=False,
    )
