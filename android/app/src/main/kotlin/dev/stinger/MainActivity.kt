package dev.stinger

import android.Manifest
import android.app.Activity
import android.content.ActivityNotFoundException
import android.content.Intent
import android.content.pm.PackageManager
import android.graphics.Bitmap
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.provider.OpenableColumns
import android.provider.Settings
import android.view.View
import android.widget.AdapterView
import android.widget.ArrayAdapter
import android.widget.Toast
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AppCompatActivity
import androidx.camera.core.CameraSelector
import androidx.camera.core.ImageAnalysis
import androidx.camera.core.ImageProxy
import androidx.camera.core.Preview
import androidx.camera.core.UseCaseGroup
import androidx.camera.lifecycle.ProcessCameraProvider
import androidx.core.content.ContextCompat
import com.google.mlkit.vision.common.InputImage
import com.google.mlkit.vision.text.Text
import com.google.mlkit.vision.text.TextRecognition
import com.google.mlkit.vision.text.TextRecognizer
import com.google.mlkit.vision.text.chinese.ChineseTextRecognizerOptions
import dev.stinger.databinding.ActivityMainBinding
import dev.stinger.match.BankCatalog
import dev.stinger.match.CameraReadout
import dev.stinger.match.FrameGate
import dev.stinger.match.LookupSession
import dev.stinger.match.formatBatchLine
import dev.stinger.match.importNameFor
import dev.stinger.match.normalizeImportName
import dev.stinger.match.precheckImport
import java.io.ByteArrayOutputStream
import java.io.File
import java.util.concurrent.ExecutorService
import java.util.concurrent.Executors
import java.util.concurrent.atomic.AtomicBoolean

class MainActivity : AppCompatActivity() {
    private lateinit var binding: ActivityMainBinding
    private lateinit var catalog: BankCatalog
    private lateinit var session: LookupSession
    private val gate = FrameGate()
    private val analysisExecutor: ExecutorService = Executors.newSingleThreadExecutor()
    private val workExecutor: ExecutorService = Executors.newSingleThreadExecutor()
    private var cameraProvider: ProcessCameraProvider? = null
    private var recognizer: TextRecognizer? = null
    private var cameraBound = false
    private var askedPermission = false
    private var updatingSpinner = false
    private val closed = AtomicBoolean(false)
    private var stickyStatus: CameraReadout? = null
    private var pendingUris: List<Uri>? = null

    private val permissionLauncher = registerForActivityResult(
        ActivityResultContracts.RequestPermission(),
    ) { granted ->
        askedPermission = true
        if (granted) openCamera() else showPermissionDenied()
    }

    private val storagePermissionLauncher = registerForActivityResult(
        ActivityResultContracts.RequestPermission(),
    ) { granted ->
        val uris = pendingUris
        pendingUris = null
        if (!granted || uris.isNullOrEmpty()) {
            showImport(
                CameraReadout(
                    null,
                    "导入失败",
                    "没有存储权限，读不到这个文件。请允许存储权限，或从文件管理器重新选择 .xlsx。",
                ),
            )
        } else {
            acceptUris(uris)
        }
    }

    private val importLauncher = registerForActivityResult(
        ActivityResultContracts.StartActivityForResult(),
    ) { result ->
        if (result.resultCode != Activity.RESULT_OK) return@registerForActivityResult
        val data = result.data
        if (data == null) {
            showImport(CameraReadout(null, "导入失败", "没有选到文件。"))
            return@registerForActivityResult
        }
        val uris = ArrayList<Uri>()
        val clip = data.clipData
        if (clip != null) {
            for (index in 0 until clip.itemCount) {
                clip.getItemAt(index)?.uri?.let { uris.add(it) }
            }
        }
        if (uris.isEmpty()) data.data?.let { uris.add(it) }
        if (uris.isEmpty()) {
            showImport(CameraReadout(null, "导入失败", "没有选到文件。"))
            return@registerForActivityResult
        }
        val flags = data.flags and (
            Intent.FLAG_GRANT_READ_URI_PERMISSION or Intent.FLAG_GRANT_WRITE_URI_PERMISSION
            )
        if (flags != 0) {
            for (uri in uris) {
                try {
                    contentResolver.takePersistableUriPermission(uri, flags)
                } catch (_: Exception) {
                    // GET_CONTENT 的授权往往不能长期保存。下面会立刻把内容拷进应用目录。
                }
            }
        }
        acceptUris(uris)
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityMainBinding.inflate(layoutInflater)
        setContentView(binding.root)
        catalog = BankCatalog.load(catalogDir())
        session = LookupSession { catalog.active() }
        binding.importBank.setOnClickListener { openImporter() }
        binding.allowCamera.setOnClickListener { requestCamera() }
        binding.banks.onItemSelectedListener = object : AdapterView.OnItemSelectedListener {
            override fun onItemSelected(parent: AdapterView<*>?, view: View?, position: Int, id: Long) {
                if (updatingSpinner) return
                val label = parent?.getItemAtPosition(position)?.toString() ?: return
                catalog.use(if (label == getString(R.string.all_banks)) dev.stinger.match.ALL_BANKS else label)
                catalog.save(catalogDir())
                session.invalidate()
                render(CameraReadout(null, getString(R.string.aim), ""))
            }

            override fun onNothingSelected(parent: AdapterView<*>?) = Unit
        }
        refreshBanks()
        render(initialReadout())
        if (hasCameraPermission()) openCamera() else permissionLauncher.launch(Manifest.permission.CAMERA)
    }

    override fun onResume() {
        super.onResume()
        if (hasCameraPermission()) {
            hidePermissionDenied()
            if (!cameraBound) openCamera()
        } else if (askedPermission) {
            showPermissionDenied()
        }
    }

    override fun onDestroy() {
        closed.set(true)
        cameraProvider?.unbindAll()
        cameraBound = false
        recognizer?.close()
        recognizer = null
        analysisExecutor.shutdown()
        workExecutor.shutdown()
        super.onDestroy()
    }

    private fun initialReadout(): CameraReadout {
        return if (catalog.isEmpty()) {
            CameraReadout(null, "请先导入题库", getString(R.string.import_local))
        } else {
            CameraReadout(null, getString(R.string.aim), "")
        }
    }

    private fun openImporter() {
        val open = pickIntent(Intent.ACTION_OPEN_DOCUMENT)
        val getContent = pickIntent(Intent.ACTION_GET_CONTENT)
        try {
            val chooser = Intent.createChooser(open, getString(R.string.pick_excel)).apply {
                putExtra(Intent.EXTRA_INITIAL_INTENTS, arrayOf(getContent))
                addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
            }
            importLauncher.launch(chooser)
        } catch (_: ActivityNotFoundException) {
            try {
                importLauncher.launch(getContent)
            } catch (_: ActivityNotFoundException) {
                showImport(
                    CameraReadout(
                        null,
                        "导入失败",
                        "这台手机没有可以打开文件的程序。请安装文件管理器后，再选择 .xlsx。",
                    ),
                )
            }
        }
    }

    private fun pickIntent(action: String): Intent {
        return Intent(action).apply {
            addCategory(Intent.CATEGORY_OPENABLE)
            type = "*/*"
            putExtra(
                Intent.EXTRA_MIME_TYPES,
                arrayOf(
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    "application/vnd.ms-excel",
                    "application/octet-stream",
                    "application/zip",
                    "application/x-zip-compressed",
                    "*/*",
                ),
            )
            putExtra(Intent.EXTRA_ALLOW_MULTIPLE, true)
            putExtra(Intent.EXTRA_LOCAL_ONLY, true)
            addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
            if (action == Intent.ACTION_OPEN_DOCUMENT) {
                addFlags(Intent.FLAG_GRANT_PERSISTABLE_URI_PERMISSION)
            }
        }
    }

    private fun acceptUris(uris: List<Uri>) {
        if (uris.any { needsLegacyStorage(it) }) {
            pendingUris = uris
            showImport(CameraReadout(null, "需要存储权限", getString(R.string.storage_rationale)))
            storagePermissionLauncher.launch(Manifest.permission.READ_EXTERNAL_STORAGE)
            return
        }
        val copied = ArrayList<Pair<String, ByteArray>>()
        val early = ArrayList<String>()
        for (uri in uris) {
            val name = displayName(uri)
            try {
                copied.add(name to copyIntoAppStorage(uri, name))
            } catch (exc: Exception) {
                early.add("${normalizeImportName(name)}：失败。${exc.message ?: "无法读取"}")
            }
        }
        workExecutor.execute {
            val lines = ArrayList<String>()
            lines.addAll(early)
            for ((name, bytes) in copied) {
                val storedName = importNameFor(name)
                val reason = precheckImport(name, bytes)
                if (reason != null) {
                    lines.add("$storedName：失败。$reason")
                    continue
                }
                try {
                    val report = catalog.addBytes(storedName, bytes)
                    lines.add(formatBatchLine(storedName, report, ""))
                    report.rejected.take(3).forEach { row ->
                        lines.add("  第 ${row.row} 行：${row.reason}")
                    }
                } catch (exc: Exception) {
                    lines.add("$storedName：失败。${exc.message ?: "无法导入"}")
                }
            }
            val anySuccess = lines.any { "：成功" in it }
            if (anySuccess) {
                catalog.save(catalogDir())
                session.invalidate()
            }
            val badge = if (anySuccess) "已导入" else "导入失败"
            val detail = if (lines.isEmpty()) "没有选到文件。" else lines.joinToString("\n")
            runOnUiThread {
                if (closed.get()) return@runOnUiThread
                refreshBanks()
                showImport(CameraReadout(null, badge, detail))
            }
        }
    }

    private fun needsLegacyStorage(uri: Uri): Boolean {
        if (!"file".equals(uri.scheme, ignoreCase = true)) return false
        if (Build.VERSION.SDK_INT >= 33) return false
        return ContextCompat.checkSelfPermission(
            this,
            Manifest.permission.READ_EXTERNAL_STORAGE,
        ) != PackageManager.PERMISSION_GRANTED
    }

    private fun copyIntoAppStorage(uri: Uri, name: String): ByteArray {
        val bytes = if ("file".equals(uri.scheme, ignoreCase = true)) {
            val path = uri.path ?: throw IllegalArgumentException("找不到文件")
            val file = File(path)
            if (!file.isFile) throw IllegalArgumentException("找不到文件")
            if (file.length() > MAX_IMPORT_BYTES) throw IllegalArgumentException("文件太大。")
            file.readBytes()
        } else {
            val input = try {
                contentResolver.openInputStream(uri)
            } catch (_: SecurityException) {
                throw IllegalArgumentException("没有读到文件的权限。请重新选择一次。")
            } ?: throw IllegalArgumentException("无法读取文件")
            input.use { stream ->
                val output = ByteArrayOutputStream()
                val buffer = ByteArray(8192)
                var total = 0
                while (true) {
                    val count = stream.read(buffer)
                    if (count < 0) break
                    total += count
                    if (total > MAX_IMPORT_BYTES) throw IllegalArgumentException("文件太大。")
                    output.write(buffer, 0, count)
                }
                output.toByteArray()
            }
        }
        val folder = File(filesDir, "imports").apply { mkdirs() }
        val safe = importNameFor(name).replace(Regex("""[^\w\u4e00-\u9fff.\-]+"""), "_")
        File(folder, "${System.currentTimeMillis()}-$safe").writeBytes(bytes)
        return bytes
    }

    private fun requestCamera() {
        val permanent = askedPermission &&
            !shouldShowRequestPermissionRationale(Manifest.permission.CAMERA)
        if (permanent) {
            startActivity(
                Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS).apply {
                    data = Uri.fromParts("package", packageName, null)
                },
            )
        } else {
            permissionLauncher.launch(Manifest.permission.CAMERA)
        }
    }

    private fun openCamera() {
        hidePermissionDenied()
        binding.preview.post {
            if (closed.get() || !hasCameraPermission()) return@post
            val future = ProcessCameraProvider.getInstance(this)
            future.addListener(
                {
                    if (closed.get()) return@addListener
                    val provider = try {
                        future.get()
                    } catch (exc: Exception) {
                        render(CameraReadout(null, getString(R.string.no_camera), exc.message ?: ""))
                        return@addListener
                    }
                    cameraProvider = provider
                    val preview = Preview.Builder().build().also {
                        it.surfaceProvider = binding.preview.surfaceProvider
                    }
                    val analysis = ImageAnalysis.Builder()
                        .setBackpressureStrategy(ImageAnalysis.STRATEGY_KEEP_ONLY_LATEST)
                        .setOutputImageFormat(ImageAnalysis.OUTPUT_IMAGE_FORMAT_YUV_420_888)
                        .build()
                    analysis.setAnalyzer(analysisExecutor) { image -> analyze(image) }
                    val selector = when {
                        provider.hasCamera(CameraSelector.DEFAULT_BACK_CAMERA) -> CameraSelector.DEFAULT_BACK_CAMERA
                        provider.hasCamera(CameraSelector.DEFAULT_FRONT_CAMERA) -> CameraSelector.DEFAULT_FRONT_CAMERA
                        else -> {
                            render(CameraReadout(null, getString(R.string.no_camera), ""))
                            return@addListener
                        }
                    }
                    try {
                        provider.unbindAll()
                        val viewPort = binding.preview.viewPort
                        if (viewPort != null) {
                            val group = UseCaseGroup.Builder()
                                .setViewPort(viewPort)
                                .addUseCase(preview)
                                .addUseCase(analysis)
                                .build()
                            provider.bindToLifecycle(this, selector, group)
                        } else {
                            provider.bindToLifecycle(this, selector, preview, analysis)
                        }
                        cameraBound = true
                    } catch (exc: Exception) {
                        cameraBound = false
                        render(CameraReadout(null, getString(R.string.no_camera), exc.message ?: ""))
                    }
                },
                ContextCompat.getMainExecutor(this),
            )
        }
    }

    private fun analyze(image: ImageProxy) {
        if (closed.get() || !gate.tryAcquire()) {
            image.close()
            return
        }
        if (catalog.isEmpty()) {
            image.close()
            gate.release()
            runOnUiThread {
                if (!closed.get()) {
                    render(CameraReadout(null, "请先导入题库", getString(R.string.import_local)))
                }
            }
            return
        }
        val cropped = try {
            val full = image.toBitmap()
            val part = cropToTarget(full)
            if (part !== full) full.recycle()
            part
        } catch (_: Exception) {
            image.close()
            gate.release()
            return
        }
        image.close()
        val client = textRecognizer()
        if (client == null || closed.get()) {
            cropped.recycle()
            gate.release()
            return
        }
        client.process(InputImage.fromBitmap(cropped, 0))
            .addOnSuccessListener { vision -> deliver(readLines(vision)) }
            .addOnFailureListener { deliver("") }
            .addOnCompleteListener {
                cropped.recycle()
                gate.release()
            }
    }

    private fun deliver(raw: String) {
        if (closed.get()) return
        if (catalog.isEmpty()) {
            runOnUiThread {
                if (!closed.get()) render(CameraReadout(null, "请先导入题库", getString(R.string.import_local)))
            }
            return
        }
        val token = session.begin(raw) ?: return
        runOnUiThread {
            if (session.isCurrent(token)) render(CameraReadout(null, getString(R.string.aim), ""))
        }
        workExecutor.execute {
            val readout = session.readout(raw)
            runOnUiThread {
                if (!closed.get() && session.isCurrent(token)) render(readout)
            }
        }
    }

    private fun textRecognizer(): TextRecognizer? {
        recognizer?.let { return it }
        return try {
            TextRecognition.getClient(ChineseTextRecognizerOptions.Builder().build()).also { recognizer = it }
        } catch (_: Throwable) {
            runOnUiThread {
                render(CameraReadout(null, getString(R.string.ocr_unavailable), ""))
            }
            null
        }
    }

    private fun showImport(readout: CameraReadout) {
        stickyStatus = readout
        val summary = readout.context.lineSequence().firstOrNull { it.isNotBlank() } ?: readout.badge
        Toast.makeText(this, summary, Toast.LENGTH_LONG).show()
        render(readout)
    }

    private fun render(readout: CameraReadout) {
        val keepSticky = stickyStatus != null && readout.answer == null &&
            (readout.badge == "请先导入题库" || (readout.badge == getString(R.string.aim) && readout.context.isEmpty()))
        val shown = if (keepSticky) stickyStatus!! else readout
        if (!keepSticky && shown !== stickyStatus) stickyStatus = null
        val answer = shown.answer
        if (answer.isNullOrEmpty()) {
            binding.answer.text = ""
            binding.answer.setTextColor(0xFFC62828.toInt())
            binding.badge.text = shown.badge
            binding.badge.setTextColor(if (shown.badge == "导入失败") 0xFFFFB74D.toInt() else 0xFFECEFF1.toInt())
        } else {
            binding.answer.text = answer
            binding.answer.setTextColor(0xFFC62828.toInt())
            binding.badge.text = shown.badge
            binding.badge.setTextColor(if (shown.badge == "待确认") 0xFFFFB74D.toInt() else 0xFFECEFF1.toInt())
        }
        binding.context.text = shown.context
    }

    private fun refreshBanks() {
        val labels = ArrayList<String>()
        labels.add(getString(R.string.all_banks))
        labels.addAll(catalog.names())
        updatingSpinner = true
        binding.banks.adapter = ArrayAdapter(this, android.R.layout.simple_spinner_dropdown_item, labels)
        val selected = if (catalog.mode == dev.stinger.match.ALL_BANKS) 0 else labels.indexOf(catalog.mode).coerceAtLeast(0)
        binding.banks.setSelection(selected)
        updatingSpinner = false
    }

    private fun showPermissionDenied() {
        cameraProvider?.unbindAll()
        cameraBound = false
        binding.permission.visibility = View.VISIBLE
        val permanent = askedPermission && !shouldShowRequestPermissionRationale(Manifest.permission.CAMERA)
        binding.allowCamera.setText(if (permanent) R.string.open_settings else R.string.allow_camera)
    }

    private fun hidePermissionDenied() {
        binding.permission.visibility = View.GONE
    }

    private fun hasCameraPermission(): Boolean {
        return ContextCompat.checkSelfPermission(this, Manifest.permission.CAMERA) == PackageManager.PERMISSION_GRANTED
    }

    private fun catalogDir(): File = File(filesDir, "catalog").apply { mkdirs() }

    private fun displayName(uri: Uri): String {
        try {
            contentResolver.query(uri, arrayOf(OpenableColumns.DISPLAY_NAME), null, null, null)?.use { cursor ->
                if (cursor.moveToFirst()) {
                    val index = cursor.getColumnIndex(OpenableColumns.DISPLAY_NAME)
                    if (index >= 0) {
                        val value = cursor.getString(index)
                        if (!value.isNullOrBlank()) return normalizeImportName(value)
                    }
                }
            }
        } catch (_: Exception) {
            // 部分文件管理器不允许查询文件名。下面改用地址里的名字。
        }
        return normalizeImportName(uri.lastPathSegment ?: "题库.xlsx")
    }

    private fun cropToTarget(source: Bitmap): Bitmap {
        val x = (source.width * TargetOverlay.LEFT).toInt().coerceIn(0, source.width - 1)
        val y = (source.height * TargetOverlay.TOP).toInt().coerceIn(0, source.height - 1)
        val right = (source.width * TargetOverlay.RIGHT).toInt().coerceIn(x + 1, source.width)
        val bottom = (source.height * TargetOverlay.BOTTOM).toInt().coerceIn(y + 1, source.height)
        return Bitmap.createBitmap(source, x, y, right - x, bottom - y)
    }

    private fun readLines(text: Text): String {
        val lines = text.textBlocks
            .flatMap { it.lines }
            .sortedWith(compareBy({ it.boundingBox?.top ?: 0 }, { it.boundingBox?.left ?: 0 }))
            .map { it.text.trim() }
            .filter { it.isNotEmpty() }
        if (lines.isNotEmpty()) return lines.joinToString("\n")
        return text.text
    }

    companion object {
        private const val MAX_IMPORT_BYTES = 32 * 1024 * 1024
    }
}
