package dev.stinger.match

/**
 * Python 3 `difflib.SequenceMatcher`（isjunk 为空、autojunk 打开）的比率和编辑片段。
 * 题干短于 200 时不会把高频字当成垃圾字符。
 */
class SequenceMatcher(a: String, b: String) {
    private val aa = a.toCharArray()
    private val bb = b.toCharArray()
    private val b2j: Map<Char, IntArray>

    init {
        val lists = LinkedHashMap<Char, MutableList<Int>>()
        for (i in bb.indices) {
            lists.getOrPut(bb[i]) { ArrayList() }.add(i)
        }
        if (bb.size >= 200) {
            val ntest = bb.size / 100 + 1
            val iterator = lists.entries.iterator()
            while (iterator.hasNext()) {
                val entry = iterator.next()
                if (entry.value.size > ntest) iterator.remove()
            }
        }
        b2j = lists.mapValues { (_, value) -> value.toIntArray() }
    }

    fun ratio(): Double {
        val matches = matchingBlocks().sumOf { it.size }
        val length = aa.size + bb.size
        return if (length == 0) 1.0 else 2.0 * matches / length
    }

    fun editSize(): Int {
        var total = 0
        for (opcode in opcodes()) {
            if (opcode.tag == "equal") continue
            total += maxOf(opcode.i2 - opcode.i1, opcode.j2 - opcode.j1)
        }
        return total
    }

    data class Block(val i: Int, val j: Int, val size: Int)

    data class Opcode(val tag: String, val i1: Int, val i2: Int, val j1: Int, val j2: Int)

    fun opcodes(): List<Opcode> {
        var i = 0
        var j = 0
        val answer = ArrayList<Opcode>()
        for (block in matchingBlocks()) {
            val tag = when {
                i < block.i && j < block.j -> "replace"
                i < block.i -> "delete"
                j < block.j -> "insert"
                else -> ""
            }
            if (tag.isNotEmpty()) answer.add(Opcode(tag, i, block.i, j, block.j))
            i = block.i + block.size
            j = block.j + block.size
            if (block.size > 0) answer.add(Opcode("equal", block.i, i, block.j, j))
        }
        return answer
    }

    fun matchingBlocks(): List<Block> {
        val queue = ArrayDeque<IntArray>()
        queue.add(intArrayOf(0, aa.size, 0, bb.size))
        val found = ArrayList<Block>()
        while (queue.isNotEmpty()) {
            val item = queue.removeLast()
            val alo = item[0]
            val ahi = item[1]
            val blo = item[2]
            val bhi = item[3]
            val block = findLongest(alo, ahi, blo, bhi)
            if (block.size > 0) {
                found.add(block)
                if (alo < block.i && blo < block.j) {
                    queue.add(intArrayOf(alo, block.i, blo, block.j))
                }
                if (block.i + block.size < ahi && block.j + block.size < bhi) {
                    queue.add(intArrayOf(block.i + block.size, ahi, block.j + block.size, bhi))
                }
            }
        }
        found.sortWith(compareBy<Block> { it.i }.thenBy { it.j }.thenBy { it.size })
        var i1 = 0
        var j1 = 0
        var k1 = 0
        val collapsed = ArrayList<Block>()
        for (block in found) {
            if (i1 + k1 == block.i && j1 + k1 == block.j) {
                k1 += block.size
            } else {
                if (k1 > 0) collapsed.add(Block(i1, j1, k1))
                i1 = block.i
                j1 = block.j
                k1 = block.size
            }
        }
        if (k1 > 0) collapsed.add(Block(i1, j1, k1))
        collapsed.add(Block(aa.size, bb.size, 0))
        return collapsed
    }

    private fun findLongest(alo: Int, ahi: Int, blo: Int, bhi: Int): Block {
        var besti = alo
        var bestj = blo
        var bestsize = 0
        var j2len = HashMap<Int, Int>()
        for (i in alo until ahi) {
            val newj2len = HashMap<Int, Int>()
            val indexes = b2j[aa[i]]
            if (indexes != null) {
                for (j in indexes) {
                    if (j < blo) continue
                    if (j >= bhi) break
                    val k = (j2len[j - 1] ?: 0) + 1
                    newj2len[j] = k
                    if (k > bestsize) {
                        besti = i - k + 1
                        bestj = j - k + 1
                        bestsize = k
                    }
                }
            }
            j2len = newj2len
        }
        while (besti > alo && bestj > blo && aa[besti - 1] == bb[bestj - 1]) {
            besti -= 1
            bestj -= 1
            bestsize += 1
        }
        while (besti + bestsize < ahi && bestj + bestsize < bhi && aa[besti + bestsize] == bb[bestj + bestsize]) {
            bestsize += 1
        }
        return Block(besti, bestj, bestsize)
    }
}
