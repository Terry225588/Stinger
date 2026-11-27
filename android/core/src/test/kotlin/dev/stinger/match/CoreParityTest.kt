package dev.stinger.match

import java.io.ByteArrayOutputStream
import java.util.zip.ZipEntry
import java.util.zip.ZipOutputStream
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertFalse
import kotlin.test.assertNotNull
import kotlin.test.assertNull
import kotlin.test.assertSame
import kotlin.test.assertTrue

class CoreParityTest {
    @Test
    fun sequenceMatcherMatchesPythonRatios() {
        assertRatio("传输层提供端到端可靠传输与差错控制功能说明", "传输层提供端到端可靠传输与差错控剖功能说明", 0.9523809523809523)
        assertRatio("工作人员不得在带电设备上作业并应立即报告负责人", "工作人员可以在带电设备上作业并应立即报告负责人", 0.9130434782608695)
        assertRatio("距离不小于100米时应停止作业并报告现场负责人", "距离不小于10米时应停止作业并报告现场负责人", 0.9777777777777777)
        assertRatio("下列说法正确的是关于接地线装设顺序的要求说明", "下列说法错误的是关于接地线装设顺序的要求说明", 0.9090909090909091)
        assertRatio("作业人员不在带电设备上停留并应报告负责人处理", "作业人员在带电设备上停留并应报告负责人处理", 0.9767441860465116)
    }

    @Test
    fun normalizeIgnoresBracketsPunctuationAndDecimalForm() {
        val bare = "下列说法正确的是"
        val expected = stemFingerprint(bare)
        assertTrue(expected.isNotEmpty())
        for (variant in listOf("下列说法正确的是（）", "下列说法正确的是()", "下列说法正确的是（ ）", "下列说法正确的是【】", "  下列说法正确的是 ？ ", "下列说法正确的是[]")) {
            assertEquals(expected, stemFingerprint(variant))
        }
        assertEquals(normalizeMatchText("100"), normalizeMatchText("100.0"))
        assertEquals("100", normalizeMatchText("100.00"))
        assertEquals("100", normalizeMatchText("１００．０"))
        assertEquals(normalizeMatchText("100.50"), normalizeMatchText("100.5"))
        assertTrue(normalizeMatchText("100.0") != normalizeMatchText("1000"))
        assertEquals(stemFingerprint("传输层负责端到端传输"), stemFingerprint("12. 传输层负责端到端传输"))
        assertEquals(stemFingerprint("传输层负责端到端传输"), stemFingerprint("【单选题】传输层负责端到端传输"))
        assertEquals(stemFingerprint("传输层负责端到端传输"), stemFingerprint("单选题 传输层负责端到端传输"))
        assertTrue(stemFingerprint("单选题库如何建设才能保证题目质量") != stemFingerprint("库如何建设才能保证题目质量"))
        assertEquals(stemFingerprint("传输层负责端到端传输"), stemFingerprint("（3）传输层负责端到端传输"))
        assertEquals(stemFingerprint("100是一个合法数值"), stemFingerprint("100.0是一个合法数值"))
        assertEquals(stemFingerprint("说法是正确"), stemFingerprint("说法是（正确）"))
        assertEquals("", cleanAnalysis("无"))
        assertEquals("", cleanAnalysis("【无】"))
        assertEquals("", cleanAnalysis(null))
        assertEquals("见教材第 3 章", cleanAnalysis("见教材第 3 章"))
    }

    @Test
    fun parserSplitsOptionsAndJudgment() {
        val parsed = parseOcrText("3. 下列说法正确的是（）\nA. 100\nB. 200\nC. 300\nD. 400\n上一题\n")
        assertTrue("下列说法正确的是" in parsed.stem)
        assertEquals(listOf("A", "B", "C", "D"), parsed.options.keys.toList())
        assertEquals("100", parsed.options["A"])
        assertFalse("（）" in parsed.fingerprint)
        assertFalse("上一题" in parsed.stem)
        val inline = parseOcrText("分组交换有哪些特点 A、存储转发 B、独占电路 C、统计复用 D、逐段链路")
        assertEquals(listOf("A", "B", "C", "D"), inline.options.keys.toList())
        assertEquals("存储转发", inline.options["A"])
        val wide = parseOcrText("题干写在前面\nＡ．甲\nＢ．乙\nＣ．丙\n")
        assertEquals("甲", wide.options["A"])
        val joined = parseOcrText("题干在同一行 A. 甲 B. 乙 C. 丙 D. 丁")
        assertEquals("甲", joined.options["A"])
        assertEquals("丁", joined.options["D"])
        val judged = parseOcrText("操作系统是否属于系统软件\n错误\n正确\n")
        assertEquals("错误", judged.options["A"])
        assertEquals("正确", judged.options["B"])
        val numeric = parseOcrText("满分是多少\nA. 100.0\nB. 60\nC. 0\n")
        assertEquals("100.0", numeric.options["A"])
    }

    @Test
    fun singleChoiceRemapsShuffledOptions() {
        val stored = question(
            stem = "传输层的主要职责是提供端到端的可靠传输",
            options = linked("A" to "端到端可靠传输", "B" to "路由选择", "C" to "调制解调", "D" to "域名解析"),
            answer = "A",
            sourceRow = 12,
            basis = "教材第 4 章",
            tag = "否",
        )
        val outcome = matchText(
            bank(stored),
            "12. 传输层的主要职责是提供端到端的可靠传输（）\nA. 路由选择\nB. 调制解调\nC. 端到端可靠传输\nD. 域名解析\n",
        )
        assertEquals("high", outcome.status)
        assertTrue(outcome.confident)
        assertSame(stored, outcome.chosen)
        assertEquals("C", outcome.remapped)
        val text = formatOutcome(outcome, "ocr")
        assertTrue("端到端可靠传输" in text)
        assertTrue("题库记录的字母：A" in text)
        assertTrue("按当前画面选项对应的字母：C" in text)
        assertTrue("题库未提供解析" in text)
        assertTrue("教材第 4 章" in text)
        val readout = cameraReadout(outcome)
        assertEquals("端到端可靠传输（画面 C）", readout.answer)
        assertEquals("", readout.badge)
    }

    @Test
    fun multiRemapAndJudgmentFace() {
        val stored = question(
            qtype = "multi",
            stem = "下列哪些属于传输层能够提供的能力",
            options = linked(
                "A" to "可靠传输",
                "B" to "差错控制",
                "C" to "流量控制",
                "D" to "域名解析",
                "E" to "调制解调",
                "F" to "拥塞控制",
            ),
            answer = "ABF",
            sourceRow = 20,
        )
        val outcome = matchText(
            bank(stored),
            "下列哪些属于传输层能够提供的能力\nA. 域名解析\nB. 可靠传输\nC. 差错控制\nD. 调制解调\nE. 拥塞控制\nF. 流量控制\n",
        )
        assertEquals("ABF", outcome.chosen?.answer)
        assertEquals("BCE", outcome.remapped)
        val text = formatOutcome(outcome)
        assertTrue("可靠传输    （画面上的 B）" in text)
        val judged = question(
            qtype = "judgment",
            stem = "操作系统属于系统软件这一说法是否成立",
            options = linked("A" to "正确", "B" to "错误"),
            answer = "A",
            sourceRow = 30,
        )
        val swapped = matchText(bank(judged), "操作系统属于系统软件这一说法是否成立\nA. 错误\nB. 正确\n")
        assertEquals("B", swapped.remapped)
        assertEquals("对", cameraReadout(swapped).answer)
        val plain = matchText(bank(judged), "操作系统属于系统软件这一说法是否成立\n错误\n正确\n")
        assertEquals("B", plain.remapped)
        assertEquals("对", judgmentFace(judged))
    }

    @Test
    fun duplicateStemNeedsOptionsBeforeChoosing() {
        val stem = "重复题干用于区分单选和多选时不能只看题目本身"
        val single = question(stem = stem, options = linked("A" to "苹果", "B" to "香蕉", "C" to "梨"), answer = "A", sourceRow = 77)
        val multi = question(
            qtype = "multi",
            stem = stem,
            options = linked("A" to "红", "B" to "绿", "C" to "蓝", "D" to "黄"),
            answer = "ABC",
            sourceRow = 545,
        )
        val unclear = matchText(bank(single, multi), stem + "（）")
        assertEquals("ambiguous", unclear.status)
        assertNull(unclear.chosen)
        assertEquals(setOf(77, 545), unclear.candidates.map { it.question.sourceRow }.toSet())
        assertNull(cameraReadout(unclear).answer)
        assertEquals("待确认", cameraReadout(unclear).badge)
        val picked = matchText(bank(single, multi), stem + "\nA. 黄\nB. 红\nC. 绿\nD. 蓝\n")
        assertSame(multi, picked.chosen)
        assertEquals("BCD", picked.remapped)
        val onlySingle = matchText(bank(single, multi), stem + "\nA. 梨\nB. 苹果\nC. 香蕉\n")
        assertSame(single, onlySingle.chosen)
        assertEquals("B", onlySingle.remapped)
    }

    @Test
    fun numericOptionsAndUnmappedLetters() {
        val stored = question(
            stem = "下列数值哪一个等于满分",
            options = linked("A" to "100.0", "B" to "60.0", "C" to "0.0"),
            answer = "A",
        )
        val outcome = matchText(bank(stored), "下列数值哪一个等于满分\nA. 60\nB. 0\nC. 100\n")
        assertTrue(outcome.confident)
        assertEquals("C", outcome.remapped)
        val single = question(
            stem = "传输层的主要职责是提供端到端的可靠传输",
            options = linked("A" to "端到端可靠传输", "B" to "路由选择", "C" to "调制解调", "D" to "域名解析"),
            answer = "A",
        )
        val unmatched = matchText(bank(single), "传输层的主要职责是提供端到端的可靠传输\nA. 猫\nB. 狗\nC. 鸟\nD. 鱼\n")
        assertTrue(unmatched.confident)
        assertNull(unmatched.remapped)
        assertTrue("未能对应到画面字母" in formatOutcome(unmatched))
        assertEquals("端到端可靠传输", cameraReadout(unmatched).answer)
    }

    @Test
    fun partialShortAndNegationStayUncertain() {
        val longStem = "在分组交换网络里传输层提供端到端可靠传输和差错控制"
        val partialHighStem = "在分组交换网络里传输层提供端到端可靠传输以及差错控制与流量控制能力"
        val partialHigh = partialHighStem.take(24)
        val partialMedium = longStem.take(16)
        val stored = question(stem = partialHighStem, options = linked("A" to "甲", "B" to "乙", "C" to "丙"), answer = "B")
        val high = matchText(bank(stored), partialHigh)
        assertEquals("partial", high.status)
        assertFalse(high.confident)
        assertNull(cameraReadout(high).answer)
        assertEquals("待确认", cameraReadout(high).badge)
        val mediumQuestion = question(stem = longStem, options = linked("A" to "甲", "B" to "乙", "C" to "丙"), answer = "A")
        val medium = matchText(bank(mediumQuestion), partialMedium)
        assertEquals("medium", medium.status)
        val low = matchText(bank(mediumQuestion), longStem.take(9))
        assertEquals("low", low.status)
        assertNull(low.chosen)
        val stem = "工作人员不得在带电设备上作业并应立即报告负责人"
        val negated = question(stem = stem, options = linked("A" to "甲", "B" to "乙", "C" to "丙"), answer = "A")
        val flipped = matchText(bank(negated), stem.replace("不得", "可以"))
        assertFalse(flipped.confident)
        assertTrue(flipped.reasons.joinToString("").contains("否定"))
        assertNull(cameraReadout(flipped).answer)
        val numbered = question(
            stem = "距离不小于100米时应停止作业并报告现场负责人",
            options = linked("A" to "甲", "B" to "乙", "C" to "丙"),
            answer = "C",
        )
        val changed = matchText(bank(numbered), "距离不小于10米时应停止作业并报告现场负责人")
        assertTrue(changed.reasons.joinToString("").contains("数字"))
        val swapped = question(
            stem = "下列说法正确的是关于接地线装设顺序的要求说明",
            options = linked("A" to "甲", "B" to "乙", "C" to "丙"),
            answer = "A",
        )
        val wrongWord = matchText(bank(swapped), "下列说法错误的是关于接地线装设顺序的要求说明")
        assertFalse(wrongWord.confident)
    }

    @Test
    fun nearDuplicateJudgmentIsNotMerged() {
        val stem = "依据某规定工作负责人应组织执行工作票所列安全措施"
        val plain = question(
            qtype = "judgment",
            stem = stem,
            options = linked("A" to "正确", "B" to "错误"),
            answer = "A",
            sourceRow = 1061,
        )
        val reserved = question(
            qtype = "judgment",
            stem = stem + "（ ）",
            options = linked("A" to "正确", "B" to "错误"),
            answer = "A",
            sourceRow = 1081,
            tag = "是",
        )
        assertEquals(plain.fingerprint, reserved.fingerprint)
        val outcome = matchText(bank(plain, reserved), stem + "\nA. 正确\nB. 错误\n")
        assertNull(outcome.chosen)
        assertEquals(setOf(1061, 1081), outcome.candidates.map { it.question.sourceRow }.toSet())
        val text = formatOutcome(outcome, stem)
        assertTrue("不能合并成一条" in text)
        assertTrue("保命题：是" in text)
        assertEquals("待确认", cameraReadout(outcome).badge)
        assertNull(cameraReadout(outcome).answer)
    }

    @Test
    fun excelImportValidatesRowsAndTemplate() {
        val bytes = xlsx(
            listOf(
                listOf("题型", "题目", "A", "B", "C", "D", "E", "F", "答案", "难度", "试题依据", "试题解析", "保命题"),
                listOf("单选题", "传输层负责什么", "端到端", "路由", "调制", "编码", "", "", "A", "易", "教材", "", "否"),
                listOf("多选题", "下面哪些属于传输层", "可靠传输", "差错控制", "流量控制", "域名解析", "调制解调", "", "A,C,E", "", "", "无", ""),
                listOf("判断题", "操作系统是系统软件", "正确", "错误", "", "", "", "", "A", "", "", "", ""),
                listOf("判断", "防火墙只能是硬件", "正确", "错误", "", "", "", "", "错误", "", "", "暂无", "是"),
                listOf("单选", "存在空选项的题", "甲", "乙", "", "丁", "", "", "A", "", "", "", ""),
                listOf("单选题", "缺少答案的题", "甲", "乙", "丙", "", "", "", "", "", "", "", ""),
                listOf("填空", "这不是支持的题型", "甲", "乙", "丙", "", "", "", "A", "", "", "", ""),
                listOf("单选题", "只有两个选项", "甲", "乙", "", "", "", "", "A", "", "", "", ""),
                listOf("多选题", "多选却只有一个答案", "甲", "乙", "丙", "丁", "", "", "B", "", "", "", ""),
                listOf("多选题", "六个选项都入选", "一", "二", "三", "四", "五", "六", "ABDF", "", "", "", ""),
                listOf("单选题", "数值选项题", "100.0", "200", "三百", "", "", "", "A", "", "", "", ""),
            ),
        )
        val (imported, report) = loadBankBytes(bytes, "bank.xlsx")
        assertEquals(6, report.validCount)
        assertEquals(mapOf("single" to 2, "multi" to 2, "judgment" to 2), report.counts())
        assertEquals(imported.counts(), report.counts())
        val reasons = report.rejected.map { it.reason }.toSet()
        assertTrue("存在空选项" in reasons)
        assertTrue("答案为空" in reasons)
        assertTrue("题型无法识别" in reasons)
        assertTrue("单选题和多选题需要 3 到 6 个选项，且中间不能空着" in reasons)
        assertTrue("多选题答案至少需要两个字母" in reasons)
        val judgment = imported.questions.first { it.stem.startsWith("防火墙") }
        assertEquals("judgment", judgment.qtype)
        assertEquals("B", judgment.answer)
        assertEquals("", judgment.analysis)
        assertEquals("是", judgment.tag)
        val numeric = imported.questions.first { it.stem == "数值选项题" }
        assertEquals("100.0", numeric.options["A"])
        val multi = imported.questions.first { "六个选项" in it.stem }
        assertEquals(listOf("A", "B", "C", "D", "E", "F"), multi.options.keys.toList())
        assertEquals("ABDF", multi.answer)
        val template = javaClass.classLoader.getResourceAsStream("stinger-question-template.xlsx")!!.readBytes()
        val (sample, sampleReport) = loadBankBytes(template, "stinger-question-template.xlsx")
        assertEquals(emptyList(), sampleReport.rejected)
        assertEquals(3, sampleReport.validCount)
        assertEquals(listOf("single", "multi", "judgment"), sample.questions.map { it.qtype })
        assertEquals("A", sample.questions[0].answer)
        assertEquals("ABC", sample.questions[1].answer)
        assertEquals("B", sample.questions[2].answer)
        assertTrue(sample.questions.all { "示例" in it.stem })
        assertTrue(sample.questions.size != 1080)
        val error = assertFailsWith<BankFormatException> { loadBankBytes("不是题库".toByteArray(), "notes.txt") }
        assertTrue("xlsx" in error.message.orEmpty())
    }

    @Test
    fun catalogKeepsBanksSeparateAndPersistsMode() {
        val root = kotlin.io.path.createTempDirectory("stinger-banks").toFile()
        val catalog = BankCatalog()
        val first = xlsx(
            listOf(
                HEADERS,
                listOf("单选题", "第一份题库里的唯一题目内容", "甲", "乙", "丙", "", "", "", "A", "", "", "", ""),
            ),
        )
        val second = xlsx(
            listOf(
                HEADERS,
                listOf("判断题", "第二份题库的判断题内容完全不同", "正确", "错误", "", "", "", "", "A", "", "", "", ""),
            ),
        )
        catalog.addBytes("甲库.xlsx", first)
        catalog.addBytes("乙库.xlsx", second)
        assertEquals(listOf("乙库", "甲库"), catalog.names())
        catalog.use("甲库")
        assertEquals(1, catalog.active().questions.size)
        assertTrue(catalog.active().questions.all { "第一份" in it.stem })
        catalog.use(ALL_BANKS)
        assertEquals(2, catalog.active().questions.size)
        catalog.save(root)
        val loaded = BankCatalog.load(root)
        assertEquals(2, loaded.active().questions.size)
        loaded.use("乙库")
        loaded.save(root)
        val again = BankCatalog.load(root)
        assertEquals("乙库", again.mode)
        assertEquals("judgment", again.active().questions.single().qtype)
    }

    @Test
    fun lookupClearsStaleAnswerAndFrameGateDropsBacklog() {
        val stored = question(
            stem = "传输层的主要职责是提供端到端的可靠传输",
            options = linked("A" to "端到端可靠传输", "B" to "路由选择", "C" to "调制解调", "D" to "域名解析"),
            answer = "A",
        )
        val session = LookupSession { bank(stored) }
        val raw = "传输层的主要职责是提供端到端的可靠传输\nA. 端到端可靠传输\nB. 路由选择\nC. 调制解调\nD. 域名解析"
        val first = session.begin(raw)
        assertNotNull(first)
        val shown = session.readout(raw)
        assertEquals("端到端可靠传输", shown.answer)
        assertNull(session.begin("  $raw（） "))
        val changed = session.begin("完全无关的园林绿化施工组织设计题目")
        assertNotNull(changed)
        val cleared = session.readout("完全无关的园林绿化施工组织设计题目")
        assertNull(cleared.answer)
        assertEquals("没有匹配", cleared.badge)
        assertFalse(session.isCurrent(first))
        assertTrue(session.isCurrent(changed))

        var now = 0L
        val gate = FrameGate(minIntervalMs = 450) { now }
        assertTrue(gate.tryAcquire())
        assertFalse(gate.tryAcquire())
        gate.release()
        now = 100
        assertFalse(gate.tryAcquire())
        now = 450
        assertTrue(gate.tryAcquire())
        assertFalse(gate.tryAcquire())
    }

    @Test
    fun phoneImportAcceptsChineseNamesSharedStringsAndRejectsTheWrongFile() {
        assertEquals("题库（一）.xlsx", normalizeImportName("%E9%A2%98%E5%BA%93%EF%BC%88%E4%B8%80%EF%BC%89.xlsx"))
        assertEquals("题库.xlsx", importNameFor("primary:Download/题库.xlsx"))
        assertEquals("微信文件.xlsx", importNameFor("微信文件"))
        assertTrue(isXlsxName("下载/安全生产.xlsx"))
        assertEquals("不能读取旧版 .xls。请在表格软件里另存为 .xlsx 后再选。", precheckImport("旧表.xls", byteArrayOf(1, 2, 3, 4)))
        assertEquals("文件是空的。", precheckImport("题库.xlsx", byteArrayOf()))
        assertEquals("这不是 Excel 文件。请选择 .xlsx，官方模板也是这种文件。", precheckImport("照片.jpg", "hello".toByteArray()))
        val template = javaClass.classLoader.getResourceAsStream("stinger-question-template.xlsx")!!.readBytes()
        assertEquals(null, precheckImport("无扩展名", template))
        assertEquals("无扩展名.xlsx", importNameFor("无扩展名"))
        val shared = sharedStringXlsx()
        assertEquals(null, precheckImport("octet-stream.bin", shared))
        val (bank, report) = loadBankBytes(shared, "微信接收的题库.xlsx")
        assertEquals(1, report.validCount)
        assertEquals("传输层负责什么", bank.questions.single().stem)
        assertEquals("A", bank.questions.single().answer)
        val missingHeader = xlsx(listOf(listOf("姓名", "备注"), listOf("甲", "乙")))
        val error = assertFailsWith<BankFormatException> { loadBankBytes(missingHeader, "没有表头.xlsx") }
        assertTrue(error.message.orEmpty().contains("表头"))
    }
}

private val HEADERS = listOf("题型", "题目", "A", "B", "C", "D", "E", "F", "答案", "难度", "试题依据", "试题解析", "保命题")

private fun assertRatio(left: String, right: String, expected: Double) {
    val actual = SequenceMatcher(left, right).ratio()
    assertTrue(kotlin.math.abs(actual - expected) < 1e-12, "ratio $actual != $expected")
}

private fun linked(vararg pairs: Pair<String, String>): LinkedHashMap<String, String> = LinkedHashMap<String, String>().apply {
    for ((key, value) in pairs) put(key, value)
}

private fun question(
    stem: String,
    options: LinkedHashMap<String, String>,
    answer: String,
    qtype: String = "single",
    sourceRow: Int = 2,
    basis: String = "",
    tag: String = "",
    analysis: String = "",
): Question {
    val labels = mapOf("single" to "单选题", "multi" to "多选题", "judgment" to "判断题")
    return Question(
        qtype = qtype,
        typeLabel = labels.getValue(qtype),
        stem = stem,
        options = options,
        answer = answer,
        difficulty = "",
        basis = basis,
        analysis = analysis,
        tag = tag,
        sourceRow = sourceRow,
        fingerprint = stemFingerprint(stem),
    )
}

private fun bank(vararg questions: Question) = QuestionBank(questions.toList(), "fixture")

private fun xlsx(rows: List<List<String>>): ByteArray {
    val sheet = buildString {
        append("""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>""")
        append("""<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>""")
        rows.forEachIndexed { r, row ->
            append("""<row r="${r + 1}">""")
            row.forEachIndexed { c, value ->
                if (value.isNotEmpty()) {
                    append("""<c r="${columnName(c)}${r + 1}" t="inlineStr"><is><t>${escapeXml(value)}</t></is></c>""")
                }
            }
            append("</row>")
        }
        append("</sheetData></worksheet>")
    }
    val files = linkedMapOf(
        "[Content_Types].xml" to """<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/></Types>""",
        "_rels/.rels" to """<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>""",
        "xl/workbook.xml" to """<?xml version="1.0" encoding="UTF-8"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="题库" sheetId="1" r:id="rId1"/></sheets></workbook>""",
        "xl/_rels/workbook.xml.rels" to """<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/></Relationships>""",
        "xl/worksheets/sheet1.xml" to sheet,
    )
    val out = ByteArrayOutputStream()
    ZipOutputStream(out).use { zip ->
        for ((name, body) in files) {
            zip.putNextEntry(ZipEntry(name))
            zip.write(body.toByteArray(Charsets.UTF_8))
            zip.closeEntry()
        }
    }
    return out.toByteArray()
}

private fun sharedStringXlsx(): ByteArray {
    val strings = listOf("题型", "题目", "A", "B", "C", "D", "E", "F", "答案", "单选题", "传输层负责什么", "端到端", "路由", "调制", "编码")
    val shared = buildString {
        append("""<?xml version="1.0" encoding="UTF-8"?><sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">""")
        for (value in strings) append("<si><t>${escapeXml(value)}</t></si>")
        append("</sst>")
    }
    val sheet = """<?xml version="1.0" encoding="UTF-8"?>
        <worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>
        <row r="1"><c r="A1" t="s"><v>0</v></c><c r="B1" t="s"><v>1</v></c><c r="C1" t="s"><v>2</v></c><c r="D1" t="s"><v>3</v></c><c r="E1" t="s"><v>4</v></c><c r="F1" t="s"><v>5</v></c><c r="G1" t="s"><v>6</v></c><c r="H1" t="s"><v>7</v></c><c r="I1" t="s"><v>8</v></c></row>
        <row r="2"><c r="A2" t="s"><v>9</v></c><c r="B2" t="s"><v>10</v></c><c r="C2" t="s"><v>11</v></c><c r="D2" t="s"><v>12</v></c><c r="E2" t="s"><v>13</v></c><c r="F2" t="s"><v>14</v></c><c r="I2" t="inlineStr"><is><t>A</t></is></c></row>
        </sheetData></worksheet>"""
    val files = linkedMapOf(
        "[Content_Types].xml" to """<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="xml" ContentType="application/xml"/></Types>""",
        "xl/workbook.xml" to """<?xml version="1.0" encoding="UTF-8"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="题库" sheetId="1" r:id="rId1"/></sheets></workbook>""",
        "xl/_rels/workbook.xml.rels" to """<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="/xl/worksheets/sheet1.xml"/></Relationships>""",
        "xl/sharedStrings.xml" to shared,
        "xl/worksheets/sheet1.xml" to sheet,
    )
    val out = ByteArrayOutputStream()
    ZipOutputStream(out).use { zip ->
        for ((name, body) in files) {
            zip.putNextEntry(ZipEntry(name))
            zip.write(body.toByteArray(Charsets.UTF_8))
            zip.closeEntry()
        }
    }
    return out.toByteArray()
}

private fun columnName(index: Int): String {
    var n = index + 1
    val chars = StringBuilder()
    while (n > 0) {
        val rem = (n - 1) % 26
        chars.append(('A'.code + rem).toChar())
        n = (n - 1) / 26
    }
    return chars.reverse().toString()
}

private fun escapeXml(value: String): String = value
    .replace("&", "&amp;")
    .replace("<", "&lt;")
    .replace(">", "&gt;")
