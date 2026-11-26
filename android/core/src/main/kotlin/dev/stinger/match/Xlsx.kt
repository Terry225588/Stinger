package dev.stinger.match

import org.w3c.dom.Element
import java.io.ByteArrayInputStream
import java.util.zip.ZipInputStream
import javax.xml.parsers.DocumentBuilderFactory

class BankFormatException(message: String) : IllegalArgumentException(message)

fun readXlsxRows(bytes: ByteArray): List<List<List<String?>>> {
    if (bytes.isEmpty()) throw BankFormatException("文件是空的。")
    val entries = HashMap<String, ByteArray>()
    try {
        ZipInputStream(ByteArrayInputStream(bytes)).use { zip ->
            var entry = zip.nextEntry
            while (entry != null) {
                if (!entry.isDirectory) {
                    val name = entry.name.replace('\\', '/').removePrefix("/").lowercase()
                    entries[name] = zip.readBytes()
                }
                zip.closeEntry()
                entry = zip.nextEntry
            }
        }
    } catch (_: Exception) {
        throw BankFormatException("文件打不开，内容不是有效的 xlsx。")
    }
    if (entries.isEmpty()) throw BankFormatException("文件打不开，内容不是有效的 xlsx。")
    fun get(path: String): ByteArray? = entries[path.replace('\\', '/').removePrefix("/").lowercase()]
    val workbook = get("xl/workbook.xml") ?: throw BankFormatException("Excel 缺少工作表。")
    val rels = get("xl/_rels/workbook.xml.rels")
    val relationTargets = if (rels != null) relationTargets(rels) else emptyMap()
    var sheetPaths = if (rels != null) sheetPaths(workbook, relationTargets) else emptyList()
    if (sheetPaths.isEmpty()) {
        sheetPaths = entries.keys.filter { it.startsWith("xl/worksheets/") && it.endsWith(".xml") }.sorted()
    }
    if (sheetPaths.isEmpty()) throw BankFormatException("Excel 缺少工作表。")
    val shared = get("xl/sharedStrings.xml")?.let { sharedStrings(it) } ?: emptyList()
    return sheetPaths.map { path ->
        val sheet = get(path) ?: throw BankFormatException("Excel 缺少工作表。")
        sheetRows(sheet, shared)
    }
}

private fun relationTargets(xml: ByteArray): Map<String, String> {
    val document = parseXml(xml)
    val map = LinkedHashMap<String, String>()
    for (node in childElements(document.documentElement, "Relationship")) {
        val id = attr(node, "Id")
        val target = attr(node, "Target")
        if (id.isNotEmpty() && target.isNotEmpty()) map[id] = resolveTarget(target)
    }
    return map
}

private fun resolveTarget(target: String): String {
    val cleaned = target.trim().replace('\\', '/')
    val relative = if (cleaned.startsWith("/")) cleaned.removePrefix("/") else "xl/$cleaned"
    val parts = ArrayList<String>()
    for (part in relative.split('/')) {
        when (part) {
            "", "." -> Unit
            ".." -> if (parts.isNotEmpty()) parts.removeAt(parts.lastIndex)
            else -> parts.add(part)
        }
    }
    return parts.joinToString("/")
}

private fun sheetPaths(xml: ByteArray, relations: Map<String, String>): List<String> {
    val document = parseXml(xml)
    val paths = ArrayList<String>()
    for (node in descendants(document.documentElement, "sheet")) {
        val id = attr(node, "id")
        val path = relations[id]
        if (path != null) paths.add(path)
    }
    return paths
}

private fun sharedStrings(xml: ByteArray): List<String> {
    val document = parseXml(xml)
    val values = ArrayList<String>()
    for (node in descendants(document.documentElement, "si")) {
        values.add(textExcludingPhonetic(node))
    }
    return values
}

private fun sheetRows(xml: ByteArray, shared: List<String>): List<List<String?>> {
    val document = parseXml(xml)
    val sheetData = descendants(document.documentElement, "sheetData").firstOrNull()
        ?: document.documentElement
    val byIndex = java.util.TreeMap<Int, List<String?>>()
    for (row in childElements(sheetData, "row")) {
        var width = 0
        val cells = ArrayList<Pair<Int, String?>>()
        for (cell in childElements(row, "c")) {
            val ref = attr(cell, "r")
            val column = if (ref.isNotEmpty()) columnIndex(ref) else width
            if (column >= 0) cells.add(column to cellText(cell, shared))
            width = maxOf(width, column + 1)
        }
        val values = MutableList<String?>(width.coerceAtLeast(0)) { null }
        for ((column, text) in cells) {
            if (column in values.indices) values[column] = text
        }
        val rowIndex = attr(row, "r").toIntOrNull()?.minus(1) ?: byIndex.size
        if (rowIndex >= 0) byIndex[rowIndex] = values
    }
    if (byIndex.isEmpty()) return emptyList()
    val last = byIndex.lastKey()
    return (0..last).map { byIndex[it] ?: emptyList() }
}

private fun cellText(cell: Element, shared: List<String>): String? {
    val type = attr(cell, "t")
    if (type == "inlineStr") return textExcludingPhonetic(cell)
    val raw = descendants(cell, "v").firstOrNull()?.textContent ?: return null
    return when (type) {
        "s" -> shared.getOrNull(raw.toIntOrNull() ?: -1)
        "b" -> if (raw == "1" || raw.equals("true", true)) "是" else "否"
        "str" -> raw
        else -> numberOrRaw(raw)
    }
}

private fun numberOrRaw(raw: String): String {
    val trimmed = raw.trim()
    if (trimmed.isEmpty()) return ""
    if (!trimmed.any { it == '.' || it == 'e' || it == 'E' }) return trimmed
    val value = trimmed.toDoubleOrNull() ?: return trimmed
    return pythonNumber(value)
}

private fun columnIndex(ref: String): Int {
    var n = 0
    for (ch in ref) {
        if (!ch.isLetter()) break
        n = n * 26 + (ch.uppercaseChar() - 'A' + 1)
    }
    return n - 1
}

private fun parseXml(xml: ByteArray): org.w3c.dom.Document {
    val factory = DocumentBuilderFactory.newInstance()
    factory.isNamespaceAware = true
    factory.isExpandEntityReferences = false
    // Android 自带的解析器没有 Xerces 这些开关。设不上就继续解析，不能因此让整份题库失败。
    trySetFeature(factory, "http://apache.org/xml/features/disallow-doctype-decl", true)
    trySetFeature(factory, "http://xml.org/sax/features/external-general-entities", false)
    trySetFeature(factory, "http://xml.org/sax/features/external-parameter-entities", false)
    return try {
        factory.newDocumentBuilder().parse(ByteArrayInputStream(xml))
    } catch (exc: BankFormatException) {
        throw exc
    } catch (_: Exception) {
        throw BankFormatException("Excel 内容无法解析。")
    }
}

private fun trySetFeature(factory: DocumentBuilderFactory, name: String, value: Boolean) {
    try {
        factory.setFeature(name, value)
    } catch (_: Exception) {
        // 手机上的解析器不认识这项时，跳过即可。
    }
}

private fun childElements(parent: org.w3c.dom.Node, local: String): List<Element> {
    val list = ArrayList<Element>()
    val children = parent.childNodes ?: return list
    for (index in 0 until children.length) {
        val child = children.item(index)
        if (child is Element && localNameOf(child) == local) list.add(child)
    }
    return list
}

private fun descendants(parent: org.w3c.dom.Node, local: String): List<Element> {
    val list = ArrayList<Element>()
    fun walk(node: org.w3c.dom.Node) {
        val children = node.childNodes ?: return
        for (index in 0 until children.length) {
            val child = children.item(index)
            if (child is Element) {
                if (localNameOf(child) == local) list.add(child)
                walk(child)
            }
        }
    }
    walk(parent)
    return list
}

private fun textExcludingPhonetic(parent: Element): String {
    val text = StringBuilder()
    fun walk(node: org.w3c.dom.Node, phonetic: Boolean) {
        val children = node.childNodes ?: return
        for (index in 0 until children.length) {
            val child = children.item(index)
            if (child !is Element) continue
            val name = localNameOf(child)
            val nextPhonetic = phonetic || name == "rPh"
            if (name == "t" && !nextPhonetic) text.append(child.textContent ?: "")
            else walk(child, nextPhonetic)
        }
    }
    walk(parent, false)
    return text.toString()
}

private fun localNameOf(node: org.w3c.dom.Node): String {
    val local = node.localName
    if (!local.isNullOrEmpty()) return local
    val name = node.nodeName ?: return ""
    val colon = name.indexOf(':')
    return if (colon >= 0) name.substring(colon + 1) else name
}

private fun attr(element: Element, local: String): String {
    val direct = element.getAttribute(local)
    if (direct.isNotEmpty()) return direct
    val namespaced = element.getAttributeNS(
        "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
        local,
    )
    if (!namespaced.isNullOrEmpty()) return namespaced
    val attributes = element.attributes ?: return ""
    for (index in 0 until attributes.length) {
        val item = attributes.item(index) ?: continue
        val name = item.nodeName ?: continue
        if (item.localName == local || name == local || name.endsWith(":$local")) {
            return item.nodeValue ?: ""
        }
    }
    return ""
}
