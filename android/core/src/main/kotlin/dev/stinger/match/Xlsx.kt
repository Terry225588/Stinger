package dev.stinger.match

import org.w3c.dom.Element
import java.io.ByteArrayInputStream
import java.util.zip.ZipInputStream
import javax.xml.parsers.DocumentBuilderFactory

class BankFormatException(message: String) : IllegalArgumentException(message)

fun readXlsxRows(bytes: ByteArray): List<List<List<String?>>> {
    val entries = HashMap<String, ByteArray>()
    ZipInputStream(ByteArrayInputStream(bytes)).use { zip ->
        var entry = zip.nextEntry
        while (entry != null) {
            if (!entry.isDirectory) {
                entries[entry.name.removePrefix("/")] = zip.readBytes()
            }
            zip.closeEntry()
            entry = zip.nextEntry
        }
    }
    if (entries.isEmpty()) throw BankFormatException("Excel 无法读取。")
    val workbook = entries["xl/workbook.xml"] ?: throw BankFormatException("Excel 缺少工作表。")
    val rels = entries["xl/_rels/workbook.xml.rels"] ?: throw BankFormatException("Excel 缺少工作表。")
    val relationTargets = relationTargets(rels)
    val sheetPaths = sheetPaths(workbook, relationTargets)
    if (sheetPaths.isEmpty()) throw BankFormatException("Excel 缺少工作表。")
    val shared = entries["xl/sharedStrings.xml"]?.let { sharedStrings(it) } ?: emptyList()
    return sheetPaths.map { path ->
        val sheet = entries[path] ?: throw BankFormatException("Excel 缺少工作表。")
        sheetRows(sheet, shared)
    }
}

private fun relationTargets(xml: ByteArray): Map<String, String> {
    val document = parseXml(xml)
    val map = LinkedHashMap<String, String>()
    for (node in elements(document.documentElement, "Relationship")) {
        val id = node.getAttribute("Id")
        val target = node.getAttribute("Target").removePrefix("/")
        if (id.isNotEmpty() && target.isNotEmpty()) {
            val path = if (target.startsWith("xl/")) target else "xl/$target"
            map[id] = path
        }
    }
    return map
}

private fun sheetPaths(xml: ByteArray, relations: Map<String, String>): List<String> {
    val document = parseXml(xml)
    val paths = ArrayList<String>()
    for (node in descendants(document.documentElement, "sheet")) {
        val id = node.getAttribute("r:id").ifEmpty {
            node.attributes.let { attrs ->
                var found = ""
                for (i in 0 until attrs.length) {
                    val item = attrs.item(i)
                    if (item.localName == "id") found = item.nodeValue
                }
                found
            }
        }
        val path = relations[id]
        if (path != null) paths.add(path)
    }
    return paths
}

private fun sharedStrings(xml: ByteArray): List<String> {
    val document = parseXml(xml)
    val values = ArrayList<String>()
    for (node in descendants(document.documentElement, "si")) {
        values.add(descendantText(node, "t"))
    }
    return values
}

private fun sheetRows(xml: ByteArray, shared: List<String>): List<List<String?>> {
    val document = parseXml(xml)
    val sheetData = descendants(document.documentElement, "sheetData").firstOrNull()
        ?: document.documentElement
    val byIndex = java.util.TreeMap<Int, List<String?>>()
    for (row in elements(sheetData, "row")) {
        var width = 0
        val cells = ArrayList<Pair<Int, String?>>()
        for (cell in elements(row, "c")) {
            val ref = cell.getAttribute("r")
            val column = if (ref.isNotEmpty()) columnIndex(ref) else width
            if (column >= 0) cells.add(column to cellText(cell, shared))
            width = maxOf(width, column + 1)
        }
        val values = MutableList<String?>(width.coerceAtLeast(0)) { null }
        for ((column, text) in cells) {
            if (column in values.indices) values[column] = text
        }
        val rowIndex = row.getAttribute("r").toIntOrNull()?.minus(1) ?: byIndex.size
        if (rowIndex >= 0) byIndex[rowIndex] = values
    }
    if (byIndex.isEmpty()) return emptyList()
    val last = byIndex.lastKey()
    return (0..last).map { byIndex[it] ?: emptyList() }
}

private fun cellText(cell: Element, shared: List<String>): String? {
    val type = cell.getAttribute("t")
    if (type == "inlineStr") return descendantText(cell, "t")
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
    factory.setFeature("http://apache.org/xml/features/disallow-doctype-decl", true)
    factory.setFeature("http://xml.org/sax/features/external-general-entities", false)
    factory.setFeature("http://xml.org/sax/features/external-parameter-entities", false)
    return factory.newDocumentBuilder().parse(ByteArrayInputStream(xml))
}

private fun elements(parent: Element, local: String): List<Element> {
    val nodes = parent.getElementsByTagNameNS("*", local)
    val list = ArrayList<Element>(nodes.length)
    for (i in 0 until nodes.length) {
        val node = nodes.item(i)
        if (node is Element && node.parentNode == parent) list.add(node)
    }
    return list
}

private fun descendants(parent: Element, local: String): List<Element> {
    val nodes = parent.getElementsByTagNameNS("*", local)
    val list = ArrayList<Element>(nodes.length)
    for (i in 0 until nodes.length) {
        val node = nodes.item(i)
        if (node is Element) list.add(node)
    }
    return list
}

private fun descendantText(parent: Element, local: String): String {
    return descendants(parent, local).joinToString("") { it.textContent ?: "" }
}
