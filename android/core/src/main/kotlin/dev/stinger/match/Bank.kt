package dev.stinger.match

import org.json.JSONArray
import org.json.JSONObject
import java.io.File

val TYPE_ORDER = listOf(
    "单项选择题",
    "多项选择题",
    "单选题",
    "多选题",
    "判断题",
    "单选",
    "多选",
    "判断",
    "single",
    "multi",
    "judgment",
)

val TYPE_MAP = mapOf(
    "单项选择题" to "single",
    "多项选择题" to "multi",
    "单选题" to "single",
    "多选题" to "multi",
    "判断题" to "judgment",
    "单选" to "single",
    "多选" to "multi",
    "判断" to "judgment",
    "single" to "single",
    "multi" to "multi",
    "judgment" to "judgment",
)

val TYPE_LABEL = mapOf("single" to "单选题", "multi" to "多选题", "judgment" to "判断题")

private val HEADER_ALIASES = buildMap {
    put("题目", "题目")
    put("题干", "题目")
    put("试题内容", "题目")
    put("题型", "题型")
    put("类型", "题型")
    put("答案", "答案")
    put("正确答案", "答案")
    put("难度", "难度")
    put("试题依据", "试题依据")
    put("依据", "试题依据")
    put("试题解析", "试题解析")
    put("解析", "试题解析")
    put("保命题", "保命题")
    for (letter in "ABCDEF") put(letter.toString(), letter.toString())
}

private val ENGLISH_FIELDS = mapOf(
    "type" to "题型",
    "qtype" to "题型",
    "stem" to "题目",
    "answer" to "答案",
    "difficulty" to "难度",
    "basis" to "试题依据",
    "analysis" to "试题解析",
    "tag" to "保命题",
)

class Question(
    val qtype: String,
    val typeLabel: String,
    val stem: String,
    val options: LinkedHashMap<String, String>,
    val answer: String,
    val difficulty: String,
    val basis: String,
    val analysis: String,
    val tag: String,
    val sourceRow: Int,
    val fingerprint: String,
    val bankName: String = "",
) {
    fun withBankName(name: String): Question = Question(
        qtype, typeLabel, stem, options, answer, difficulty, basis, analysis, tag, sourceRow, fingerprint, name,
    )
}

data class RejectedRow(val row: Int, val reason: String)

class ImportReport(
    val sourceName: String,
    val questions: List<Question>,
    val rejected: List<RejectedRow> = emptyList(),
) {
    val validCount: Int get() = questions.size

    fun counts(): Map<String, Int> {
        val totals = linkedMapOf("single" to 0, "multi" to 0, "judgment" to 0)
        for (question in questions) totals[question.qtype] = (totals[question.qtype] ?: 0) + 1
        return totals
    }
}

class QuestionBank(questions: List<Question>, val sourceName: String = "") {
    val questions: List<Question> = questions.toList()

    fun counts(): Map<String, Int> {
        val totals = linkedMapOf("single" to 0, "multi" to 0, "judgment" to 0)
        for (question in questions) totals[question.qtype] = (totals[question.qtype] ?: 0) + 1
        return totals
    }
}

fun canonicalType(raw: Any?): String? {
    var text = toHalfwidth(cellToStr(raw)).trim()
    text = text.replace("【", "").replace("】", "").trim()
    TYPE_MAP[text]?.let { return it }
    for (key in TYPE_ORDER) {
        if (key in text) return TYPE_MAP[key]
    }
    return null
}

fun loadBankBytes(bytes: ByteArray, filename: String): Pair<QuestionBank, ImportReport> {
    val lower = filename.lowercase()
    val report = when {
        lower.endsWith(".xlsx") -> loadXlsx(bytes, filename)
        lower.endsWith(".json") -> loadJson(bytes, filename)
        else -> throw BankFormatException("只支持 .xlsx 和 .json。请直接选择 Excel，不必先转换。")
    }
    return QuestionBank(report.questions, report.sourceName) to report
}

fun bankDisplayName(filename: String): String {
    val stem = filename.substringAfterLast('/').substringAfterLast('\\').substringBeforeLast('.')
    return stem.trim().ifEmpty { "未命名题库" }
}

const val ALL_BANKS = "全部题库"

class BankCatalog {
    val entries: LinkedHashMap<String, QuestionBank> = LinkedHashMap()
    var mode: String = ALL_BANKS
        private set

    @Synchronized
    fun addBytes(filename: String, bytes: ByteArray): ImportReport {
        val (loaded, report) = loadBankBytes(bytes, filename)
        val name = bankDisplayName(filename)
        val tagged = loaded.questions.map { it.withBankName(name) }
        entries[name] = QuestionBank(tagged, name)
        return report
    }

    @Synchronized
    fun names(): List<String> = entries.keys.sorted()

    @Synchronized
    fun use(next: String) {
        if (next == ALL_BANKS || next in entries) mode = next
    }

    @Synchronized
    fun active(): QuestionBank {
        if (mode != ALL_BANKS && mode in entries) return entries.getValue(mode)
        val questions = ArrayList<Question>()
        for (bank in entries.values) questions.addAll(bank.questions)
        return QuestionBank(questions, ALL_BANKS)
    }

    @Synchronized
    fun isEmpty(): Boolean = entries.isEmpty() || entries.values.all { it.questions.isEmpty() }

    @Synchronized
    fun save(directory: File) {
        val folder = File(directory, "banks")
        folder.mkdirs()
        val kept = ArrayList<String>()
        for ((name, bank) in entries) {
            val slug = bankSlug(name)
            File(folder, "$slug.json").writeText(bankToJson(bank).toString(2))
            kept.add(slug)
        }
        folder.listFiles()?.forEach { file ->
            if (file.extension == "json" && file.nameWithoutExtension !in kept) file.delete()
        }
        val payload = JSONObject()
        payload.put("mode", mode)
        payload.put("order", JSONArray(names()))
        File(directory, "catalog.json").writeText(payload.toString(2))
    }

    companion object {
        fun load(directory: File): BankCatalog {
            val catalog = BankCatalog()
            val folder = File(directory, "banks")
            if (folder.isDirectory) {
                folder.listFiles()?.sortedBy { it.name }?.forEach { file ->
                    if (file.extension != "json") return@forEach
                    val bank = bankFromJson(file.readText(), file.nameWithoutExtension)
                    val name = bank.sourceName.ifEmpty { file.nameWithoutExtension }
                    catalog.entries[name] = bank
                }
            }
            val meta = File(directory, "catalog.json")
            if (meta.isFile) {
                try {
                    val payload = JSONObject(meta.readText())
                    catalog.use(payload.optString("mode", ALL_BANKS))
                } catch (_: Exception) {
                    catalog.mode = ALL_BANKS
                }
            }
            return catalog
        }
    }
}

fun formatBatchLine(name: String, report: ImportReport?, error: String): String {
    if (report == null) return "$name：失败。$error"
    if (report.validCount == 0) {
        val why = report.rejected.firstOrNull()?.let { "第 ${it.row} 行：${it.reason}" } ?: "没有找到可导入的题目"
        return "$name：失败。没有导入题目。$why"
    }
    return "$name：成功 ${report.validCount} 题，跳过 ${report.rejected.size} 行。"
}

private fun bankSlug(name: String): String {
    val cleaned = Regex("""[^\w\u4e00-\u9fff.\-]+""").replace(name, "_").trim('.', '_')
    return cleaned.take(80).ifEmpty { "bank" }
}

private fun loadXlsx(bytes: ByteArray, filename: String): ImportReport {
    val sheets = try {
        readXlsxRows(bytes)
    } catch (exc: BankFormatException) {
        throw exc
    } catch (exc: Exception) {
        throw BankFormatException("Excel 无法读取。")
    }
    var best: Triple<List<List<String?>>, Int, Map<String, Int>>? = null
    for (rows in sheets) {
        val found = findHeader(rows) ?: continue
        if (best == null || rows.size > best.first.size) {
            best = Triple(rows, found.first, found.second)
        }
    }
    if (best == null) {
        throw BankFormatException("前 10 行里没有找到表头。至少需要：题型、题目、答案，以及选项 A–F。")
    }
    val (questions, rejected) = consumeRows(best.first, best.second, best.third)
    return ImportReport(filename.substringAfterLast('/'), questions, rejected)
}

private fun findHeader(rows: List<List<String?>>): Pair<Int, Map<String, Int>>? {
    for (index in 0 until minOf(10, rows.size)) {
        val mapping = LinkedHashMap<String, Int>()
        rows[index].forEachIndexed { col, value ->
            val name = HEADER_ALIASES[cellToStr(value).trim()]
            if (name != null && name !in mapping) mapping[name] = col
        }
        if (setOf("题型", "题目", "答案").all { it in mapping }) return index to mapping
    }
    return null
}

private fun consumeRows(
    rows: List<List<String?>>,
    headerIndex: Int,
    columns: Map<String, Int>,
): Pair<List<Question>, List<RejectedRow>> {
    val questions = ArrayList<Question>()
    val rejected = ArrayList<RejectedRow>()
    for (offset in (headerIndex + 1) until rows.size) {
        val row = rows[offset]
        val record = LinkedHashMap<String, String?>()
        for ((name, col) in columns) record[name] = row.getOrNull(col)
        if (record.values.none { cellToStr(it).isNotBlank() }) continue
        val (question, reason) = questionFromRecord(record, offset + 1)
        if (question == null) rejected.add(RejectedRow(offset + 1, reason ?: "无法导入"))
        else questions.add(question)
    }
    return questions to rejected
}

private fun loadJson(bytes: ByteArray, filename: String): ImportReport {
    val payload = try {
        val text = bytes.toString(Charsets.UTF_8).trim()
        if (text.startsWith("[")) JSONArray(text) else JSONObject(text)
    } catch (exc: Exception) {
        throw BankFormatException("JSON 无法解析：${exc.message}")
    }
    val rows: JSONArray = when (payload) {
        is JSONArray -> payload
        is JSONObject -> payload.optJSONArray("questions") ?: payload.optJSONArray("data")
        else -> null
    } ?: throw BankFormatException("JSON 需要是题目数组，或包含 questions 数组的对象。")
    val questions = ArrayList<Question>()
    val rejected = ArrayList<RejectedRow>()
    for (index in 0 until rows.length()) {
        val item = rows.optJSONObject(index)
        if (item == null) {
            rejected.add(RejectedRow(index + 1, "这一项不是对象"))
            continue
        }
        val record = jsonRecord(item)
        val rowNumber = item.optInt("source_row", index + 1)
        val (question, reason) = questionFromRecord(record, rowNumber)
        if (question == null) rejected.add(RejectedRow(rowNumber, reason ?: "无法导入"))
        else questions.add(question)
    }
    return ImportReport(filename.substringAfterLast('/'), questions, rejected)
}

private fun jsonRecord(item: JSONObject): LinkedHashMap<String, String?> {
    val record = LinkedHashMap<String, String?>()
    val keys = item.keys()
    while (keys.hasNext()) {
        val key = keys.next()
        val name = key.trim()
        val field = HEADER_ALIASES[name] ?: ENGLISH_FIELDS[name]
        if (field != null && item.opt(key) !is JSONObject && item.opt(key) !is JSONArray) {
            record[field] = jsonScalar(item.opt(key))
        }
    }
    val options = item.optJSONObject("options")
    if (options != null) {
        val optionKeys = options.keys()
        while (optionKeys.hasNext()) {
            val key = optionKeys.next()
            val letter = toHalfwidth(key).trim().uppercase()
            if (letter.length == 1 && letter[0] in 'A'..'F') record[letter] = jsonScalar(options.opt(key))
        }
    }
    return record
}

private fun jsonScalar(value: Any?): String? {
    if (value == null || value == JSONObject.NULL) return null
    return value.toString()
}

fun questionFromRecord(record: Map<String, String?>, rowNumber: Int): Pair<Question?, String?> {
    val qtype = canonicalType(record["题型"]) ?: return null to "题型无法识别"
    val stem = cellToStr(record["题目"]).trim()
    if (stemFingerprint(stem).isEmpty()) return null to "题目为空"
    val (options, optionError) = collectOptions(record)
    if (optionError != null) return null to optionError
    val count = options.size
    if (qtype == "judgment") {
        if (count != 2) return null to "判断题需要 2 个选项"
    } else if (count < 3 || count > 6) {
        return null to "单选题和多选题需要 3 到 6 个选项，且中间不能空着"
    }
    val answer = try {
        normalizeAnswer(record["答案"], options, qtype)
    } catch (exc: IllegalArgumentException) {
        return null to (exc.message ?: "答案无法对应到选项")
    }
    return Question(
        qtype = qtype,
        typeLabel = TYPE_LABEL.getValue(qtype),
        stem = stem,
        options = options,
        answer = answer,
        difficulty = cellToStr(record["难度"]).trim(),
        basis = cellToStr(record["试题依据"]).trim(),
        analysis = cleanAnalysis(record["试题解析"]),
        tag = cellToStr(record["保命题"]).trim(),
        sourceRow = rowNumber,
        fingerprint = stemFingerprint(stem),
    ) to null
}

private fun collectOptions(record: Map<String, String?>): Pair<LinkedHashMap<String, String>, String?> {
    val pairs = ArrayList<Pair<String, String>>()
    for (letter in "ABCDEF") {
        val text = stripOptionPrefix(cellToStr(record[letter.toString()]).trim())
        pairs.add(letter.toString() to text)
    }
    while (pairs.isNotEmpty() && pairs.last().second.isEmpty()) pairs.removeAt(pairs.lastIndex)
    if (pairs.any { it.second.isEmpty() }) return LinkedHashMap<String, String>() to "存在空选项"
    return LinkedHashMap<String, String>().apply { for ((letter, text) in pairs) put(letter, text) } to null
}

private fun normalizeAnswer(raw: String?, options: Map<String, String>, qtype: String): String {
    val text = toHalfwidth(cellToStr(raw)).trim()
    if (text.isEmpty()) throw IllegalArgumentException("答案为空")
    val found = text.uppercase().filter { it in 'A'..'F' }.toSet()
    var letters = "ABCDEF".filter { it in found }
    if (letters.isEmpty() && qtype == "judgment") {
        val word = normalizeMatchText(text)
        letters = when (word) {
            in setOf("正确", "对", "是", "true", "t") -> letterFor(options, setOf("正确", "对")) ?: ""
            in setOf("错误", "错", "否", "false", "f") -> letterFor(options, setOf("错误", "错")) ?: ""
            else -> ""
        }
    }
    if (letters.isEmpty()) throw IllegalArgumentException("答案无法对应到选项")
    if (letters.any { it.toString() !in options }) throw IllegalArgumentException("答案里的字母超出了已有选项")
    if (qtype == "single" && letters.length != 1) throw IllegalArgumentException("单选题答案只能有一个字母")
    if (qtype == "judgment" && letters.length != 1) throw IllegalArgumentException("判断题答案只能有一个字母")
    if (qtype == "multi" && letters.length < 2) throw IllegalArgumentException("多选题答案至少需要两个字母")
    return letters
}

private fun letterFor(options: Map<String, String>, words: Set<String>): String? {
    val hits = options.filter { (_, text) -> normalizeMatchText(text) in words }.keys.toList()
    return if (hits.size == 1) hits[0] else null
}

private fun bankToJson(bank: QuestionBank): JSONObject {
    val questions = JSONArray()
    for (question in bank.questions) {
        val options = JSONObject()
        for ((letter, text) in question.options) options.put(letter, text)
        questions.put(
            JSONObject()
                .put("qtype", question.qtype)
                .put("type_label", question.typeLabel)
                .put("stem", question.stem)
                .put("options", options)
                .put("answer", question.answer)
                .put("difficulty", question.difficulty)
                .put("basis", question.basis)
                .put("analysis", question.analysis)
                .put("tag", question.tag)
                .put("source_row", question.sourceRow)
                .put("fingerprint", question.fingerprint)
                .put("bank_name", question.bankName),
        )
    }
    return JSONObject()
        .put("version", 1)
        .put("source_name", bank.sourceName)
        .put("questions", questions)
}

private fun bankFromJson(text: String, fallbackName: String): QuestionBank {
    val payload = JSONObject(text)
    val rows = payload.optJSONArray("questions") ?: JSONArray()
    val questions = ArrayList<Question>()
    for (index in 0 until rows.length()) {
        val item = rows.optJSONObject(index) ?: continue
        try {
            questions.add(questionFromCache(item))
        } catch (_: Exception) {
            continue
        }
    }
    val name = payload.optString("source_name").ifEmpty { fallbackName }
    return QuestionBank(questions, name)
}

private fun questionFromCache(item: JSONObject): Question {
    val optionsJson = item.getJSONObject("options")
    val options = LinkedHashMap<String, String>()
    val keys = optionsJson.keys()
    val ordered = ArrayList<String>()
    while (keys.hasNext()) ordered.add(keys.next())
    for (letter in "ABCDEF") {
        if (letter.toString() in ordered) {
            val value = optionsJson.optString(letter.toString()).trim()
            if (value.isNotEmpty()) options[letter.toString()] = value
        }
    }
    val qtype = item.getString("qtype")
    if (qtype !in TYPE_LABEL) throw IllegalArgumentException(qtype)
    val stem = item.getString("stem")
    return Question(
        qtype = qtype,
        typeLabel = item.optString("type_label").ifEmpty { TYPE_LABEL.getValue(qtype) },
        stem = stem,
        options = options,
        answer = item.getString("answer"),
        difficulty = item.optString("difficulty"),
        basis = item.optString("basis"),
        analysis = cleanAnalysis(item.optString("analysis")),
        tag = item.optString("tag"),
        sourceRow = item.optInt("source_row"),
        fingerprint = stemFingerprint(stem),
        bankName = item.optString("bank_name"),
    )
}
