package dev.stinger.match

import java.io.ByteArrayInputStream
import java.net.URLDecoder
import java.util.zip.ZipInputStream

private const val MAX_IMPORT_BYTES = 32 * 1024 * 1024

fun normalizeImportName(raw: String?): String {
    val source = raw?.trim().orEmpty()
    if (source.isEmpty()) return "题库.xlsx"
    val decoded = try {
        URLDecoder.decode(source, "UTF-8")
    } catch (_: Exception) {
        source
    }
    val base = decoded.substringAfterLast('/').substringAfterLast('\\').substringAfterLast(':').trim()
    return base.ifEmpty { "题库.xlsx" }
}

fun isXlsxName(name: String): Boolean = normalizeImportName(name).lowercase().endsWith(".xlsx")

fun isLegacyXlsName(name: String): Boolean {
    val lower = normalizeImportName(name).lowercase()
    return lower.endsWith(".xls") && !lower.endsWith(".xlsx")
}

fun sniffXlsx(bytes: ByteArray): Boolean {
    if (bytes.size < 4 || bytes[0] != 'P'.code.toByte() || bytes[1] != 'K'.code.toByte()) return false
    return try {
        ZipInputStream(ByteArrayInputStream(bytes)).use { zip ->
            var entry = zip.nextEntry
            while (entry != null) {
                val name = entry.name.replace('\\', '/').lowercase()
                if (name == "xl/workbook.xml" || name.endsWith("/xl/workbook.xml")) return true
                entry = zip.nextEntry
            }
            false
        }
    } catch (_: Exception) {
        false
    }
}

/** 返回 null 表示可以交给表格解析。文件名和内容只要有一边能证明是 xlsx 就继续。 */
fun precheckImport(name: String, bytes: ByteArray): String? {
    if (bytes.isEmpty()) return "文件是空的。"
    if (bytes.size > MAX_IMPORT_BYTES) return "文件太大。"
    if (isLegacyXlsName(name)) return "不能读取旧版 .xls。请在表格软件里另存为 .xlsx 后再选。"
    val namedXlsx = isXlsxName(name)
    val zipped = sniffXlsx(bytes)
    if (!namedXlsx && !zipped) return "这不是 Excel 文件。请选择 .xlsx，官方模板也是这种文件。"
    if (!zipped) return "文件打不开，内容不是有效的 xlsx。"
    return null
}

fun importNameFor(raw: String?): String {
    val name = normalizeImportName(raw)
    return if (isXlsxName(name)) name else if (name.endsWith(".xlsx", true)) name else "$name.xlsx"
}
