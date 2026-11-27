package dev.stinger.match

const val SHORT_STEM = 8
const val CANDIDATE_MIN = 0.72
const val MEDIUM_SCORE = 0.88
const val NEAR_RATIO = 0.94
const val OPTION_PAIR_MIN = 0.86
const val BAND = 0.02

const val LETTER_UNMAPPED =
    "画面上的选项文字没能和题库可靠对应。下面的字母是题库里原来记下的字母；网页如果打乱了选项，字母会不一样。请以答案原文为准。"
const val LETTER_REMAPPED = "已按当前画面里的选项文字对应字母。题库记录的字母是 %s。请仍核对答案原文。"
const val REASON_MEDIUM = "题干只是部分相符，或相似度有限。可以看答案原文，但不要把它当成唯一答案。"
const val REASON_SHORT = "识别到的题干很短，容易和别的题撞上。请对照完整题目。"
const val REASON_LOW = "只有较弱的相似题目。下面列出可能的题，没有确定答案。"
const val REASON_AMBIGUOUS =
    "同一题干在题库里对应多道题，或有几道题得分接近。只看题干不能确定答案。请用画面上的选项区分；在此之前不要采用其中任何一道的答案。"
const val REASON_SAME_ANSWER_NEAR =
    "这些题规范化之后题干相同，选项和答案也相同。答案原文可以对照，但每一行都要留下：保命题标记可能不同，不能合并成一条。"
const val REASON_SHORT_LIST = "题干太短，只按包含关系列出部分题目，没有确定答案。"
const val REASON_SIMILAR = "有一两处用字不同。上面的数字是相似度，不是逐字确定，也不是正确率。"
const val REASON_PARTIAL = "只对上了题干的一段。这是片段候选，不是逐字核对通过。"
const val REASON_REVIEW = "前几名相似度接近，但答案不一样。需要复核，先不要只采用第一条。"

private val NEG_PHRASES = listOf("不得", "不能", "不应", "不可以", "不可", "禁止", "不许", "严禁", "勿")
private val UNITS = listOf("千米", "厘米", "毫米", "公斤", "千克", "毫克", "千瓦", "千伏", "分钟", "小时", "米", "伏", "安", "瓦", "吨", "秒")
private val DIGITS = Regex("""\d+""")

data class StemScore(
    val score: Double,
    val exact: Boolean,
    val contained: Boolean,
    val cover: Double,
    val queryLen: Int,
    val bankLen: Int,
)

data class OptionPair(val bank: String, val screen: String, val sim: Double)

class Alignment(val pairs: List<OptionPair>) {
    fun mapping(): Map<String, String> = pairs.associate { it.bank to it.screen }
}

class CandidateView(
    val question: Question,
    val score: Double,
    val note: String,
    val answerTexts: List<Pair<String, String>>,
    val bankLetters: String,
    val screenLetters: String?,
    val lowMatch: Boolean,
)

class MatchOutcome(
    val status: String,
    val confident: Boolean,
    val chosen: Question?,
    val answerTexts: List<Pair<String, String>>,
    val remapped: String?,
    val screenForAnswer: Map<String, String>,
    val letterNote: String,
    val reasons: List<String>,
    val candidates: List<CandidateView>,
    val screenOptions: Map<String, String>,
    val screenStem: String,
    val verified: Boolean,
    val score: Double,
    val needsReview: Boolean,
)

fun matchText(bank: QuestionBank, text: String): MatchOutcome = matchParsed(bank, parseOcrText(text))

fun scoreStem(queryFp: String, bankFp: String): StemScore {
    val qlen = queryFp.length
    val blen = bankFp.length
    if (queryFp.isEmpty() || bankFp.isEmpty()) return StemScore(0.0, false, false, 0.0, qlen, blen)
    if (queryFp == bankFp) return StemScore(1.0, true, true, 1.0, qlen, blen)
    var contained = false
    var cover = 0.0
    var shorter = minOf(qlen, blen)
    if (qlen <= blen && queryFp in bankFp) {
        contained = true
        cover = qlen.toDouble() / blen
        shorter = qlen
    } else if (blen < qlen && bankFp in queryFp) {
        contained = true
        cover = blen.toDouble() / qlen
        shorter = blen
    }
    if (contained && shorter >= SHORT_STEM) {
        val score = when {
            shorter >= 18 && cover >= 0.70 -> 0.97
            shorter >= 12 && cover >= 0.45 -> 0.90
            else -> 0.78
        }
        return StemScore(score, false, true, cover, qlen, blen)
    }
    if (minOf(qlen, blen) < SHORT_STEM) return StemScore(0.0, false, false, 0.0, qlen, blen)
    val ratio = SequenceMatcher(queryFp, bankFp).ratio()
    return StemScore(ratio, false, false, 0.0, qlen, blen)
}

fun classify(stemScore: StemScore, gap: Double): String {
    if (stemScore.queryLen < SHORT_STEM) {
        if (stemScore.exact && gap >= 0.05) return "medium"
        if (stemScore.score >= CANDIDATE_MIN) return "low"
        return "none"
    }
    if (gap < 0.03 && stemScore.score >= MEDIUM_SCORE) return "ambiguous"
    if (gap < 0.04) return if (stemScore.score >= CANDIDATE_MIN) "low" else "none"
    if (stemScore.exact) return "high"
    if (stemScore.contained && stemScore.queryLen >= 18 && stemScore.cover >= 0.70) return "partial"
    if (!stemScore.contained && stemScore.score >= NEAR_RATIO && stemScore.queryLen >= 10) return "high"
    if (stemScore.contained && stemScore.queryLen >= 12 && stemScore.cover >= 0.45) return "medium"
    if (stemScore.score >= MEDIUM_SCORE) return "medium"
    if (stemScore.score >= CANDIDATE_MIN) return "low"
    return "none"
}

fun alignOptions(screen: Map<String, String>, bank: Map<String, String>): Alignment {
    val used = HashSet<String>()
    val pairs = ArrayList<OptionPair>()
    for ((bankLetter, bankText) in bank) {
        val bankNorm = normalizeMatchText(bankText)
        var bestLetter: String? = null
        var bestSim = 0.0
        for ((screenLetter, screenText) in screen) {
            if (screenLetter in used) continue
            val screenNorm = normalizeMatchText(screenText)
            if (bankNorm.isEmpty() || screenNorm.isEmpty()) continue
            val sim = if (bankNorm == screenNorm) 1.0 else SequenceMatcher(bankNorm, screenNorm).ratio()
            if (sim > bestSim) {
                bestSim = sim
                bestLetter = screenLetter
            }
        }
        if (bestLetter != null && bestSim >= OPTION_PAIR_MIN) {
            used.add(bestLetter)
            pairs.add(OptionPair(bankLetter, bestLetter, bestSim))
        }
    }
    return Alignment(pairs)
}

fun isSufficient(alignment: Alignment, bankOptions: Map<String, String>): Boolean {
    val total = bankOptions.size
    val matched = alignment.pairs.size
    if (total == 0 || matched == 0) return false
    if (total <= 2) return matched == total && alignment.pairs.minOf { it.sim } >= 0.9
    val mean = alignment.pairs.sumOf { it.sim } / matched
    return matched >= 2 && (matched.toDouble() / total) >= 0.5 && mean >= 0.88
}

fun remapAnswer(answer: String, alignment: Alignment, sufficient: Boolean): String? {
    if (!sufficient) return null
    val mapping = alignment.mapping()
    val screenLetters = ArrayList<String>()
    for (letter in answer) {
        val screenLetter = mapping[letter.toString()] ?: return null
        screenLetters.add(screenLetter)
    }
    val remapped = screenLetters.toSortedSet().joinToString("")
    if (remapped.length != answer.toSet().size) return null
    return remapped
}

fun describeConflict(query: String, bank: String, contained: Boolean): String? {
    if (query == bank) return null
    if (numberConflict(query, bank, contained)) return "题干里的数字对不上"
    if (contained) return null
    if (("正确" in query) != ("正确" in bank) || ("错误" in query) != ("错误" in bank)) {
        return "题干里的「正确」或「错误」不一致"
    }
    for (phrase in NEG_PHRASES) {
        if ((phrase in query) != (phrase in bank)) return "否定说法不一致（$phrase）"
    }
    if (bareBu(query) != bareBu(bank)) return "否定词「不」不一致"
    if (unitList(query) != unitList(bank)) return "题干里的单位不一致"
    return null
}

private fun matchParsed(bank: QuestionBank, parsed: ParsedScreen): MatchOutcome {
    if (bank.questions.isEmpty()) return emptyOutcome("none", "请先导入题库（Excel）。", parsed)
    if (parsed.fingerprint.isEmpty()) return emptyOutcome("none", "没有识别到可以用来匹配的题干。", parsed)
    val scored = ArrayList<Pair<Question, StemScore>>()
    for (question in bank.questions) {
        val stemScore = scoreStem(parsed.fingerprint, question.fingerprint)
        if (stemScore.exact || stemScore.score >= CANDIDATE_MIN) scored.add(question to stemScore)
    }
    scored.sortWith(compareByDescending<Pair<Question, StemScore>> { it.second.score }.thenBy { it.first.sourceRow })
    if (scored.isEmpty()) {
        return shortFragment(bank, parsed) ?: emptyOutcome("none", "没有在题库里找到足够接近的题干。", parsed)
    }
    val best = scored[0].second.score
    val band = scored.filter { best - it.second.score <= BAND }
    if (band.size > 1) {
        val picked = distinguish(band.map { it.first }, parsed)
        if (picked == null) return ambiguous(band, parsed, REASON_AMBIGUOUS)
        val (question, alignment) = picked
        val stemScore = band.first { it.first === question }.second
        val status = statusAfterSplit(stemScore)
        return finalize(question, stemScore, alignment, parsed, scored, status, distinguished = true)
    }
    val (question, stemScore) = scored[0]
    val status = classify(stemScore, gap(scored))
    if (status == "ambiguous") return ambiguous(scored.take(5), parsed, REASON_AMBIGUOUS)
    if (status == "low") return low(scored.take(5), parsed, REASON_LOW)
    if (status == "none") return emptyOutcome("none", "没有在题库里找到足够接近的题干。", parsed)
    val alignment = alignOptions(parsed.options, question.options)
    return finalize(question, stemScore, alignment, parsed, scored, status, distinguished = false)
}

private fun statusAfterSplit(stemScore: StemScore): String {
    if (stemScore.queryLen < SHORT_STEM) return if (stemScore.exact) "medium" else "low"
    if (stemScore.exact) return "high"
    if (stemScore.contained && stemScore.queryLen >= 18 && stemScore.cover >= 0.70) return "partial"
    if (stemScore.score >= NEAR_RATIO) return "high"
    return "medium"
}

private fun numberConflict(query: String, bank: String, contained: Boolean): Boolean {
    val queryNumbers = DIGITS.findAll(query).map { it.value }.toList()
    val bankNumbers = DIGITS.findAll(bank).map { it.value }.toList()
    if (queryNumbers == bankNumbers) return false
    if (queryNumbers.any { it !in bankNumbers }) return true
    return !contained
}

private fun bareBu(text: String): Int {
    var stripped = text
    for (phrase in NEG_PHRASES) stripped = stripped.replace(phrase, "")
    return stripped.count { it == '不' }
}

private fun unitList(text: String): List<String> {
    val found = ArrayList<String>()
    var rest = text
    for (unit in UNITS) {
        while (unit in rest) {
            found.add(unit)
            rest = rest.replaceFirst(unit, "")
        }
    }
    return found
}

private fun closeAnswerConflict(scored: List<Pair<Question, StemScore>>): Boolean {
    if (scored.size < 2) return false
    val (firstQuestion, firstScore) = scored[0]
    val (secondQuestion, secondScore) = scored[1]
    if (firstScore.score - secondScore.score > 0.08) return false
    if (secondScore.score < 0.80) return false
    return firstQuestion.answer != secondQuestion.answer || firstQuestion.qtype != secondQuestion.qtype
}

private fun distinguish(questions: List<Question>, parsed: ParsedScreen): Pair<Question, Alignment>? {
    if (parsed.options.isEmpty()) return null
    val ranked = questions.map { question ->
        val alignment = alignOptions(parsed.options, question.options)
        Triple(quality(alignment, question.options), question, alignment)
    }.sortedWith(compareByDescending<Triple<Double, Question, Alignment>> { it.first }.thenBy { it.second.sourceRow })
    val (bestQuality, question, alignment) = ranked[0]
    val second = if (ranked.size > 1) ranked[1].first else 0.0
    if (bestQuality >= 0.88 && bestQuality - second >= 0.15) return question to alignment
    return null
}

private fun quality(alignment: Alignment, bankOptions: Map<String, String>): Double {
    if (!isSufficient(alignment, bankOptions)) return 0.0
    return alignment.pairs.sumOf { it.sim } / alignment.pairs.size
}

private fun gap(scored: List<Pair<Question, StemScore>>): Double {
    if (scored.size < 2) return 1.0
    return scored[0].second.score - scored[1].second.score
}

private fun view(question: Question, stemScore: StemScore, parsed: ParsedScreen): CandidateView {
    val alignment = if (parsed.options.isNotEmpty()) alignOptions(parsed.options, question.options) else Alignment(emptyList())
    val sufficient = parsed.options.isNotEmpty() && isSufficient(alignment, question.options)
    val remapped = remapAnswer(question.answer, alignment, sufficient)
    val lowMatch = !stemScore.exact && stemScore.score < 0.80
    return CandidateView(
        question = question,
        score = stemScore.score,
        note = if (lowMatch) "低匹配" else "",
        answerTexts = question.answer.map { letter -> letter.toString() to (question.options[letter.toString()] ?: "") },
        bankLetters = question.answer,
        screenLetters = remapped,
        lowMatch = lowMatch,
    )
}

private fun views(scored: List<Pair<Question, StemScore>>, parsed: ParsedScreen): List<CandidateView> {
    val result = ArrayList<CandidateView>()
    for ((question, stemScore) in scored) {
        if (!stemScore.exact && stemScore.score < CANDIDATE_MIN) continue
        result.add(view(question, stemScore, parsed))
        if (result.size >= 5) break
    }
    return result
}

private fun finalize(
    question: Question,
    stemScore: StemScore,
    alignment: Alignment,
    parsed: ParsedScreen,
    scored: List<Pair<Question, StemScore>>,
    statusIn: String,
    distinguished: Boolean,
): MatchOutcome {
    var status = statusIn
    val conflict = describeConflict(parsed.fingerprint, question.fingerprint, stemScore.contained)
    if (conflict != null && status in setOf("high", "partial", "medium")) {
        return ambiguous(scored.take(5), parsed, conflict + "。不能把这道题当成已经核对通过。")
    }
    var similarNote: String? = null
    if (status == "high" && !stemScore.exact) {
        when {
            stemScore.contained -> status = "partial"
            SequenceMatcher(parsed.fingerprint, question.fingerprint).editSize() > 2 -> status = "medium"
            else -> similarNote = REASON_SIMILAR
        }
    }
    if (status == "partial") similarNote = REASON_PARTIAL
    val needsReview = closeAnswerConflict(scored) && !distinguished
    if (needsReview && !stemScore.exact) return ambiguous(scored.take(5), parsed, REASON_REVIEW)
    return build(question, stemScore, alignment, parsed, scored, status, similarNote, needsReview)
}

private fun build(
    question: Question,
    stemScore: StemScore,
    alignment: Alignment,
    parsed: ParsedScreen,
    scored: List<Pair<Question, StemScore>>,
    status: String,
    similarNote: String?,
    needsReview: Boolean,
): MatchOutcome {
    val sufficient = parsed.options.isNotEmpty() && isSufficient(alignment, question.options)
    val remapped = remapAnswer(question.answer, alignment, sufficient)
    val mapping = alignment.mapping()
    val screenFor = LinkedHashMap<String, String>()
    if (remapped != null) {
        for (letter in question.answer) {
            val mapped = mapping[letter.toString()]
            if (mapped != null) screenFor[letter.toString()] = mapped
        }
    }
    val letterNote = if (remapped != null) LETTER_REMAPPED.format(question.answer) else LETTER_UNMAPPED
    val reasons = ArrayList<String>()
    if (similarNote != null) reasons.add(similarNote)
    if (status == "medium") reasons.add(REASON_MEDIUM)
    if (stemScore.queryLen < SHORT_STEM) reasons.add(REASON_SHORT)
    if (needsReview) reasons.add(REASON_REVIEW)
    val verified = status == "high" && stemScore.exact
    return MatchOutcome(
        status = status,
        confident = status == "high" && verified && !needsReview,
        chosen = question,
        answerTexts = question.answer.map { letter -> letter.toString() to (question.options[letter.toString()] ?: "") },
        remapped = remapped,
        screenForAnswer = screenFor,
        letterNote = letterNote,
        reasons = reasons,
        candidates = views(scored, parsed),
        screenOptions = LinkedHashMap(parsed.options),
        screenStem = parsed.stem,
        verified = verified,
        score = stemScore.score,
        needsReview = needsReview,
    )
}

private fun sameAnswerAndOptions(questions: List<Question>): Boolean {
    if (questions.size < 2) return false
    val answers = questions.map { it.answer }.toSet()
    val optionSets = questions.map { question ->
        question.options.map { (letter, text) -> letter to normalizeMatchText(text) }
    }.toSet()
    return answers.size == 1 && optionSets.size == 1
}

private fun ambiguous(
    rows: List<Pair<Question, StemScore>>,
    parsed: ParsedScreen,
    reason: String,
): MatchOutcome {
    val reasons = ArrayList<String>()
    reasons.add(reason)
    val questions = rows.map { it.first }
    if (sameAnswerAndOptions(questions)) reasons.add(REASON_SAME_ANSWER_NEAR)
    val answers = questions.map { it.answer }.toSet()
    val needsReview = answers.size > 1 || reason == REASON_REVIEW
    if (needsReview && REASON_REVIEW !in reasons && answers.size > 1) reasons.add(0, REASON_REVIEW)
    return MatchOutcome(
        status = "ambiguous",
        confident = false,
        chosen = null,
        answerTexts = emptyList(),
        remapped = null,
        screenForAnswer = emptyMap(),
        letterNote = "",
        reasons = reasons,
        candidates = views(rows, parsed),
        screenOptions = LinkedHashMap(parsed.options),
        screenStem = parsed.stem,
        verified = false,
        score = rows.firstOrNull()?.second?.score ?: 0.0,
        needsReview = needsReview,
    )
}

private fun low(rows: List<Pair<Question, StemScore>>, parsed: ParsedScreen, reason: String): MatchOutcome {
    return MatchOutcome(
        status = "low",
        confident = false,
        chosen = null,
        answerTexts = emptyList(),
        remapped = null,
        screenForAnswer = emptyMap(),
        letterNote = "",
        reasons = listOf(reason),
        candidates = views(rows, parsed),
        screenOptions = LinkedHashMap(parsed.options),
        screenStem = parsed.stem,
        verified = false,
        score = rows.firstOrNull()?.second?.score ?: 0.0,
        needsReview = false,
    )
}

private fun shortFragment(bank: QuestionBank, parsed: ParsedScreen): MatchOutcome? {
    val query = parsed.fingerprint
    if (query.length !in 4 until SHORT_STEM) return null
    val hits = bank.questions.filter { query in it.fingerprint }
        .sortedWith(compareBy<Question> { it.sourceRow }.thenByDescending { it.fingerprint.length })
    if (hits.isEmpty()) return null
    val rows = hits.take(5).map { question ->
        question to StemScore(0.74, false, true, 0.0, query.length, question.fingerprint.length)
    }
    if (hits.size > 1) return ambiguous(rows, parsed, REASON_SHORT_LIST)
    return low(rows, parsed, REASON_SHORT_LIST)
}

private fun emptyOutcome(status: String, reason: String, parsed: ParsedScreen): MatchOutcome {
    return MatchOutcome(
        status = status,
        confident = false,
        chosen = null,
        answerTexts = emptyList(),
        remapped = null,
        screenForAnswer = emptyMap(),
        letterNote = "",
        reasons = listOf(reason),
        candidates = emptyList(),
        screenOptions = LinkedHashMap(parsed.options),
        screenStem = parsed.stem,
        verified = false,
        score = 0.0,
        needsReview = false,
    )
}
