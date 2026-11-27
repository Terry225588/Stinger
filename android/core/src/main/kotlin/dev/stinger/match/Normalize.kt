package dev.stinger.match

private val EMPTY_BRACKETS = Regex("""[(（\[【〔{｛]\s*[)）\]】〕}｝]""")
private val LEADING_INDEX = Regex("""^\s*(?:第\s*)?\d{1,3}\s*[.、．:：)\]】]\s*(?!\d)""")
private val LEADING_PAREN_INDEX = Regex("""^\s*[（(]\s*\d{1,3}\s*[)）]\s*""")
private val LEADING_TYPE = Regex(
    """^\s*(?:【\s*(?:单项选择题|多项选择题|单选题|多选题|判断题|单选|多选|判断)\s*】|(?:单项选择题|多项选择题|单选题|多选题|判断题)(?=\s|[:：.、]))\s*""",
)
private val DECIMAL = Regex("""\d+\.\d+""")
private val DROP = Regex("""[^\u4e00-\u9fffa-z0-9]+""")
private val OPTION_PREFIX = Regex("""^[A-F]\s*[.、．:：)）]\s*""", RegexOption.IGNORE_CASE)
private val ANALYSIS_PLACEHOLDERS = setOf(
    "",
    "无",
    "【无】",
    "暂无",
    "暂无解析",
    "无解析",
    "未提供",
    "none",
    "null",
    "n/a",
    "na",
    "-",
    "—",
)

fun toHalfwidth(text: String): String = buildString(text.length) {
    for (ch in text) {
        val code = ch.code
        when {
            code == 0x3000 -> append(' ')
            code in 0xFF01..0xFF5E -> append((code - 0xFEE0).toChar())
            else -> append(ch)
        }
    }
}

fun stripEmptyBrackets(text: String): String {
    var current = text
    var previous: String? = null
    while (previous != current) {
        previous = current
        current = EMPTY_BRACKETS.replace(current, "")
    }
    return current
}

fun canonicalizeDecimals(text: String): String {
    return DECIMAL.replace(text) { match ->
        val raw = match.value
        val value = raw.toDoubleOrNull()
        if (value == null || !value.isFinite()) {
            raw
        } else if (value % 1.0 == 0.0) {
            value.toLong().toString()
        } else {
            String.format(java.util.Locale.US, "%f", value).trimEnd('0').trimEnd('.').ifEmpty { "0" }
        }
    }
}

fun normalizeMatchText(text: Any?): String {
    if (text == null) return ""
    var cleaned = toHalfwidth(text.toString())
    cleaned = stripEmptyBrackets(cleaned)
    cleaned = canonicalizeDecimals(cleaned)
    cleaned = cleaned.lowercase()
    cleaned = Regex("""\s+""").replace(cleaned, "")
    cleaned = DROP.replace(cleaned, "")
    return cleaned
}

fun stemFingerprint(text: Any?): String {
    if (text == null) return ""
    var cleaned = toHalfwidth(text.toString()).trim()
    cleaned = stripEmptyBrackets(cleaned)
    var previous: String? = null
    while (previous != cleaned) {
        previous = cleaned
        cleaned = LEADING_INDEX.replace(cleaned, "").trim()
        cleaned = LEADING_PAREN_INDEX.replace(cleaned, "").trim()
        cleaned = LEADING_TYPE.replace(cleaned, "").trim()
    }
    return normalizeMatchText(cleaned)
}

fun cellToStr(value: Any?): String {
    return when (value) {
        null -> ""
        is Boolean -> if (value) "是" else "否"
        is Double -> if (!value.isFinite()) "" else pythonNumber(value)
        is Float -> cellToStr(value.toDouble())
        is Int -> value.toString()
        is Long -> value.toString()
        else -> value.toString().trim()
    }
}

fun pythonNumber(value: Double): String {
    if (value % 1.0 == 0.0 && value <= Long.MAX_VALUE.toDouble() && value >= Long.MIN_VALUE.toDouble()) {
        return value.toLong().toString()
    }
    return String.format(java.util.Locale.US, "%.12f", value).trimEnd('0').trimEnd('.')
}

fun stripOptionPrefix(text: String): String {
    return OPTION_PREFIX.replaceFirst(text.trim(), "").trim()
}

fun cleanAnalysis(value: Any?): String {
    val text = cellToStr(value).trim()
    if (text.lowercase() in ANALYSIS_PLACEHOLDERS || text in ANALYSIS_PLACEHOLDERS) return ""
    return text
}

fun recognitionKey(text: String?): String = normalizeMatchText(text ?: "")
