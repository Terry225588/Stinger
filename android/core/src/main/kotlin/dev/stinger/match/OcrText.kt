package dev.stinger.match

private val CHROME = setOf("上一题", "下一题", "提交", "提交答案", "收藏", "收藏本题", "标记本题")
private val CHROME_NORM = CHROME.map { normalizeMatchText(it) }.toSet()
private val LINE_OPTION = Regex("""^\s*([A-F])\s*[.、．:：)）]\s*(.*)$""", RegexOption.IGNORE_CASE)
private val INLINE_OPTION = Regex("""([A-F])\s*[.、．:：)）]\s*""", RegexOption.IGNORE_CASE)
private val STOP_LINE = Regex("""^(?:解析|试题解析|答案|我的答案|正确答案)\s*[:：]""")
private val LEADING_NUMBERED = Regex("""^\d{1,3}\s*[.、．]""")
private val JUDGMENT_WORD = mapOf(
    "正确" to "正确",
    "对" to "正确",
    "错误" to "错误",
    "错" to "错误",
)

data class ParsedScreen(
    val raw: String,
    val stem: String,
    val options: LinkedHashMap<String, String>,
    val fingerprint: String,
)

fun parseOcrText(raw: String?): ParsedScreen {
    val source = raw ?: ""
    val lines = prepareLines(source)
    val (lineOptions, firstIndex) = optionsFromLines(lines)
    val options: LinkedHashMap<String, String>
    val stem: String
    if (lineOptions.size >= 2 && firstIndex != null) {
        options = lineOptions
        stem = lines.subList(0, firstIndex).joinToString("\n").trim()
    } else {
        val (inlineOptions, inlineStem) = optionsInline(lines.joinToString("\n"))
        if (inlineOptions.size >= 2) {
            options = inlineOptions
            stem = inlineStem.trim()
        } else {
            val judged = judgmentOptions(lines)
            if (judged.size >= 2) {
                options = judged
                stem = lines.filter { normalizeMatchText(it) !in JUDGMENT_WORD }.joinToString("\n").trim()
            } else {
                stem = lines.joinToString("\n").trim()
                options = if (lineOptions.size >= 2) lineOptions else LinkedHashMap()
            }
        }
    }
    return ParsedScreen(source, stem, options, stemFingerprint(stem))
}

private fun prepareLines(raw: String): List<String> {
    val text = toHalfwidth(raw).replace("\r\n", "\n").replace("\r", "\n")
    val lines = ArrayList<String>()
    for (line in text.split('\n')) {
        val stripped = line.trim()
        if (stripped.isEmpty()) continue
        if (normalizeMatchText(stripped) in CHROME_NORM) continue
        lines.add(stripped)
    }
    return lines
}

private fun explode(letter: String, body: String): List<Pair<String, String>> {
    val matches = INLINE_OPTION.findAll(body).toList()
    if (matches.isEmpty()) {
        val text = body.trim()
        return if (text.isEmpty()) emptyList() else listOf(letter to text)
    }
    val parts = ArrayList<Pair<String, String>>()
    val head = body.substring(0, matches[0].range.first).trim()
    parts.add(letter to head)
    for (index in matches.indices) {
        val match = matches[index]
        val next = if (index + 1 < matches.size) matches[index + 1].range.first else body.length
        parts.add(match.groupValues[1].uppercase() to body.substring(match.range.last + 1, next).trim())
    }
    return parts.filter { it.second.isNotEmpty() }
}

private fun optionsFromLines(lines: List<String>): Pair<LinkedHashMap<String, String>, Int?> {
    val found = LinkedHashMap<String, String>()
    var first: Int? = null
    var last: String? = null
    for ((index, line) in lines.withIndex()) {
        val match = LINE_OPTION.matchEntire(line)
        if (match != null) {
            if (first == null) first = index
            for ((letter, body) in explode(match.groupValues[1].uppercase(), match.groupValues[2])) {
                found[letter] = body
                last = letter
            }
            continue
        }
        if (found.isNotEmpty() && STOP_LINE.containsMatchIn(line)) break
        if (last != null && line.isNotEmpty() && !LEADING_NUMBERED.containsMatchIn(line)) {
            found[last] = "${found[last]} $line".trim()
        }
    }
    return found to first
}

private fun optionsInline(text: String): Pair<LinkedHashMap<String, String>, String> {
    val matches = INLINE_OPTION.findAll(text).toList()
    if (matches.size < 2) return LinkedHashMap<String, String>() to text
    var start = 0
    for (index in matches.indices) {
        if (matches[index].groupValues[1].uppercase() == "A") {
            start = index
            break
        }
    }
    val chosen = ArrayList<Triple<String, Int, Int>>()
    for (match in matches.subList(start, matches.size)) {
        val letter = match.groupValues[1].uppercase()
        if (chosen.any { it.first == letter }) break
        if (chosen.isNotEmpty() && letter[0] < chosen.last().first[0]) break
        chosen.add(Triple(letter, match.range.first, match.range.last + 1))
        if (chosen.size == 6) break
    }
    if (chosen.size < 2) return LinkedHashMap<String, String>() to text
    val options = LinkedHashMap<String, String>()
    for (index in chosen.indices) {
        val (letter, _, end) = chosen[index]
        val next = if (index + 1 < chosen.size) chosen[index + 1].second else text.length
        val body = text.substring(end, next).trim(' ', '\t', '\n')
        if (body.isNotEmpty()) options[letter] = body
    }
    val stem = text.substring(0, chosen[0].second).trim()
    return options to stem
}

private fun judgmentOptions(lines: List<String>): LinkedHashMap<String, String> {
    val ordered = ArrayList<String>()
    for (line in lines) {
        val label = JUDGMENT_WORD[normalizeMatchText(line)] ?: continue
        if (label !in ordered) ordered.add(label)
    }
    if (ordered != listOf("正确", "错误") && ordered != listOf("错误", "正确")) {
        return LinkedHashMap()
    }
    val mapped = LinkedHashMap<String, String>()
    ordered.forEachIndexed { index, label ->
        mapped[('A' + index).toString()] = label
    }
    return mapped
}
