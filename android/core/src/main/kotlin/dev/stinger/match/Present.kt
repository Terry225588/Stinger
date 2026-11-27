package dev.stinger.match

import java.util.Locale

private val BANNERS = mapOf(
    "high" to "高相似",
    "partial" to "片段候选，不是逐字核对通过",
    "medium" to "仅供参考：题干不完全确定",
    "low" to "没有确定答案：只有一些弱相似的题",
    "ambiguous" to "不能确定：题干对应多道题，或几道题太接近",
    "none" to "没有匹配",
)
private const val NO_ANALYSIS = "题库未提供解析"
const val REVIEW_BADGE = "待确认"
const val SIMILARITY_HINT = "题干匹配度是题干相似度乘以 100，不是把握，也不是正确率。"
private const val STEM_EXCERPT = 12

fun showsCurrentAnswer(outcome: MatchOutcome): Boolean {
    if (outcome.needsReview) return false
    if (outcome.status != "high" || outcome.chosen == null || !outcome.verified) return false
    return true
}

fun needsReviewBadge(outcome: MatchOutcome): Boolean {
    if (outcome.needsReview || !outcome.verified) return true
    return outcome.status in setOf("partial", "ambiguous", "medium", "low", "none")
}

fun judgmentFace(question: Question): String? {
    if (question.qtype != "judgment") return null
    val text = normalizeMatchText(question.options[question.answer] ?: "")
    if (text in setOf("正确", "对")) return "对"
    if (text in setOf("错误", "错")) return "错"
    return (question.options[question.answer] ?: "").trim().ifEmpty { null }
}

fun stemExcerpt(stem: String, limit: Int = STEM_EXCERPT): String {
    val compact = stem.filter { !it.isWhitespace() }
    if (compact.length <= limit) return compact
    return compact.take(limit) + "…"
}

fun candidateWindow(outcome: MatchOutcome, expanded: Boolean): List<CandidateView> {
    val limit = if (expanded) 5 else 3
    return outcome.candidates.take(limit)
}

fun formatOutcome(outcome: MatchOutcome, ocrText: String = ""): String {
    val lines = ArrayList<String>()
    lines.add(BANNERS[outcome.status] ?: "没有匹配")
    lines.add("")
    lines.add("题干相似度 ${String.format(Locale.US, "%.2f", outcome.score)}（不是正确率，也不是把握）")
    if (outcome.needsReview || outcome.status in setOf("partial", "ambiguous", "medium", "low", "none")) {
        lines.add("待确认：这不是确定答案。")
    }
    if (outcome.verified) {
        if (outcome.chosen?.qtype == "judgment") {
            lines.add("题干与题库逐字一致。判断题只显示对或错，不显示 A、B。")
        } else {
            lines.add("题干与题库逐字一致。字母是否就是网页上的字母，要看下面有没有写明已经对应。")
        }
    } else if (showsCurrentAnswer(outcome)) {
        lines.add("这条按相似度列出，不是逐字确定。")
    } else {
        lines.add("当前没有可直接采用的答案。")
    }
    lines.addAll(outcome.reasons)
    lines.add("")
    if (showsCurrentAnswer(outcome)) lines.addAll(questionBlock(outcome))
    val shown = candidateWindow(outcome, expanded = true)
    if (shown.isNotEmpty()) {
        lines.add("候选题目（相似度够高才列出，不够的不凑数）")
        shown.forEachIndexed { index, candidate -> lines.addAll(candidateLines(candidate, index + 1)) }
        lines.add("")
    }
    lines.add("识别到的题干")
    lines.add(outcome.screenStem.ifEmpty { "（没有分离出题干）" })
    lines.add("")
    lines.add("识别原文")
    lines.add(ocrText.trim().ifEmpty { "（空）" })
    return lines.joinToString("\n").trimEnd() + "\n"
}

fun formatPanel(outcome: MatchOutcome?, expanded: Boolean, notice: String): String {
    if (outcome == null) {
        val status = shortPanelStatus(notice)
        return if (status.isEmpty()) "\n" else "$status\n"
    }
    val lines = ArrayList<String>()
    for (row in compactPanelRows(outcome, expanded)) {
        val badge = if (row.review) "  $REVIEW_BADGE" else ""
        val bank = if (row.bank.isNotEmpty()) "  ${row.bank}" else ""
        lines.add("题干匹配度 ${row.percent}%  ${row.excerpt}$bank$badge")
        lines.add(row.letterLine)
        lines.addAll(row.contents)
        lines.add("")
    }
    return lines.joinToString("\n").trimEnd() + "\n"
}

private data class PanelRow(
    val percent: Int,
    val excerpt: String,
    val letterLine: String,
    val contents: List<String>,
    val review: Boolean,
    val bank: String,
)

private fun compactPanelRows(outcome: MatchOutcome, expanded: Boolean): List<PanelRow> {
    val review = needsReviewBadge(outcome)
    val rows = ArrayList<PanelRow>()
    for (candidate in candidateWindow(outcome, expanded)) {
        val face = judgmentFace(candidate.question)
        val letterLine: String
        val texts: List<String>
        if (face != null) {
            letterLine = face
            texts = emptyList()
        } else {
            val letters = candidate.bankLetters.ifEmpty { candidate.question.answer }
            letterLine = if (candidate.screenLetters != null) "画面 ${candidate.screenLetters}" else "题库 $letters"
            val source = candidate.answerTexts.ifEmpty {
                candidate.question.answer.map { letter -> letter.toString() to (candidate.question.options[letter.toString()] ?: "") }
            }
            texts = source.map { it.second }.filter { it.isNotEmpty() }
        }
        rows.add(
            PanelRow(
                percent = kotlin.math.round(candidate.score * 100).toInt(),
                excerpt = stemExcerpt(candidate.question.stem),
                letterLine = letterLine,
                contents = texts,
                review = review,
                bank = candidate.question.bankName,
            ),
        )
    }
    return rows
}

private fun questionBlock(outcome: MatchOutcome): List<String> {
    val question = outcome.chosen ?: return emptyList()
    val face = judgmentFace(question)
    if (face != null) {
        val lines = arrayListOf(meta(question), "", question.stem, "", "答案", face, "", "解析", question.analysis.ifEmpty { NO_ANALYSIS })
        extraLine(question)?.let { lines.add(""); lines.add(it) }
        lines.add("")
        return lines
    }
    val lines = arrayListOf(meta(question), "", question.stem, "", "答案原文")
    if (outcome.remapped != null) lines.add("题库字母与画面字母都列在下面。请同时看选项原文。")
    for ((letter, text) in outcome.answerTexts) {
        val screenLetter = outcome.screenForAnswer[letter]
        if (screenLetter != null) lines.add("$letter. $text    （画面上的 $screenLetter）")
        else lines.add("$letter. $text")
    }
    lines.add("")
    lines.add("题库记录的字母：${question.answer}")
    if (outcome.remapped != null) lines.add("按当前画面选项对应的字母：${outcome.remapped}")
    else lines.add("未能对应到画面字母。")
    if (outcome.letterNote.isNotEmpty()) lines.add(outcome.letterNote)
    lines.add("")
    lines.add("题库选项")
    val answerSet = question.answer.toSet()
    for ((letter, text) in question.options) {
        val mark = if (letter[0] in answerSet) "    ← 题库答案" else ""
        lines.add("$letter. $text$mark")
    }
    lines.add("")
    lines.add("画面上识别到的选项")
    if (outcome.screenOptions.isNotEmpty()) {
        for ((letter, text) in outcome.screenOptions) lines.add("$letter. $text")
    } else {
        lines.add("（没有识别到选项）")
    }
    lines.add("")
    lines.add("解析")
    lines.add(question.analysis.ifEmpty { NO_ANALYSIS })
    extraLine(question)?.let { lines.add(""); lines.add(it) }
    lines.add("")
    return lines
}

private fun extraLine(question: Question): String? {
    val extra = ArrayList<String>()
    if (question.difficulty.isNotEmpty()) extra.add("难度：${question.difficulty}")
    if (question.basis.isNotEmpty()) extra.add("试题依据：${question.basis}")
    if (question.tag.isNotEmpty()) extra.add("保命题：${question.tag}")
    return extra.joinToString("  ").ifEmpty { null }
}

private fun candidateLines(candidate: CandidateView, index: Int): List<String> {
    val mark = if (candidate.lowMatch) "低匹配，不要当成同一题。 " else ""
    val lines = ArrayList<String>()
    lines.add("$index. ${candidate.question.typeLabel}  相似度 ${String.format(Locale.US, "%.2f", candidate.score)}（不是正确率）  $mark".trimEnd())
    lines.add("   " + shortStem(candidate.question.stem))
    val face = judgmentFace(candidate.question)
    if (face != null) {
        lines.add("   答案：$face")
    } else {
        val texts = candidate.answerTexts.ifEmpty {
            candidate.question.answer.map { letter -> letter.toString() to (candidate.question.options[letter.toString()] ?: "") }
        }
        lines.add("   答案原文：" + texts.joinToString("；") { (letter, text) -> "$letter. $text" })
        val letters = candidate.bankLetters.ifEmpty { candidate.question.answer }
        lines.add("   题库字母：$letters")
    }
    lines.add("   保命题：" + candidate.question.tag.ifEmpty { "（空）" })
    lines.add("   解析：" + candidate.question.analysis.ifEmpty { NO_ANALYSIS })
    if (candidate.screenLetters != null && face == null) {
        lines.add("   画面字母：${candidate.screenLetters}（选项文字已对应）")
    }
    return lines
}

private fun shortStem(stem: String, limit: Int = 32): String {
    val compact = stem.split(Regex("""\s+""")).filter { it.isNotEmpty() }.joinToString(" ")
    if (compact.length <= limit) return compact
    return compact.take(limit) + "…"
}

private fun meta(question: Question): String = listOf(question.typeLabel, "题库第 ${question.sourceRow} 行").joinToString("    ")

private fun shortPanelStatus(notice: String): String {
    if (notice.isEmpty()) return ""
    if ("暂停" in notice) return "已暂停"
    if ("没有识别" in notice || "无识别" in notice) return "无识别"
    if ("失败" in notice || "出错" in notice) return "出错"
    return "已作废"
}

data class CameraReadout(
    val answer: String?,
    val badge: String,
    val context: String,
)

fun cameraReadout(outcome: MatchOutcome): CameraReadout {
    val conflict = outcome.needsReview || outcome.status == "ambiguous"
    val strong = outcome.status == "high" && outcome.chosen != null && !conflict
    val answer = if (strong) adoptedAnswer(outcome) else null
    val review = answer == null || !outcome.verified || outcome.needsReview
    val badge = when {
        outcome.reasons.any { "导入题库" in it } -> "请先导入题库"
        outcome.status == "none" -> "没有匹配"
        review -> REVIEW_BADGE
        else -> ""
    }
    val percent = kotlin.math.round(outcome.score * 100).toInt()
    val context = buildString {
        if (outcome.score > 0.0 || outcome.chosen != null || outcome.candidates.isNotEmpty()) {
            append("题干匹配度 $percent%")
            val excerpt = stemExcerpt(outcome.screenStem.ifEmpty { outcome.chosen?.stem ?: "" })
            if (excerpt.isNotEmpty()) append("  ").append(excerpt)
            val bank = outcome.chosen?.bankName?.ifEmpty { null }
                ?: outcome.candidates.firstOrNull()?.question?.bankName?.ifEmpty { null }
            if (bank != null) append("  ").append(bank)
        }
        val reason = outcome.reasons.firstOrNull { it.isNotBlank() }
        if (reason != null) {
            if (isNotEmpty()) append('\n')
            append(reason)
        }
        if (answer != null && outcome.remapped == null && outcome.chosen?.qtype != "judgment") {
            if (isNotEmpty()) append('\n')
            append("未能对应画面字母，请以答案原文为准。")
        }
    }
    return CameraReadout(answer, badge, context)
}

fun adoptedAnswer(outcome: MatchOutcome): String? {
    val question = outcome.chosen ?: return null
    judgmentFace(question)?.let { return it }
    if (outcome.answerTexts.isEmpty()) return null
    return outcome.answerTexts.joinToString("；") { (letter, text) ->
        val screen = outcome.screenForAnswer[letter]
        if (screen != null && screen != letter) "$text（画面 $screen）" else text
    }
}

class LookupSession(private val bank: () -> QuestionBank) {
    private val lock = Any()
    private var lastKey: String? = null
    private var generation = 0

    fun begin(raw: String): Int? = synchronized(lock) {
        val key = recognitionKey(raw)
        if (key == lastKey) return null
        lastKey = key
        generation += 1
        generation
    }

    fun isCurrent(token: Int): Boolean = synchronized(lock) { token == generation }

    fun readout(raw: String): CameraReadout {
        if (recognitionKey(raw).isEmpty()) {
            return CameraReadout(answer = null, badge = "对准题目", context = "")
        }
        return cameraReadout(matchText(bank(), raw))
    }

    fun invalidate() = synchronized(lock) {
        lastKey = null
        generation += 1
    }
}

class FrameGate(
    private val minIntervalMs: Long = 450,
    private val clock: () -> Long = { System.currentTimeMillis() },
) {
    private val inFlight = java.util.concurrent.atomic.AtomicBoolean(false)
    private var lastStart = Long.MIN_VALUE / 4

    fun tryAcquire(): Boolean {
        val now = clock()
        if (now - lastStart < minIntervalMs) return false
        if (!inFlight.compareAndSet(false, true)) return false
        lastStart = now
        return true
    }

    fun release() {
        inFlight.set(false)
    }
}
