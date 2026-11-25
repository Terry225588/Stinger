package dev.stinger

import android.Manifest
import android.content.Intent
import android.content.pm.PackageManager
import android.graphics.Bitmap
import android.net.Uri
import android.os.Bundle
import android.provider.OpenableColumns
import android.provider.Settings
import android.view.View
import android.widget.AdapterView
import android.widget.ArrayAdapter
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

    private val permissionLauncher = registerForActivityResult(
        ActivityResultContracts.RequestPermission(),
    ) { granted ->
        askedPermission = true
        if (granted) openCamera() else showPermissionDenied()
    }

    private val importLauncher = registerForActivityResult(
        ActivityResultContracts.StartActivityForResult(),
    ) { result ->
        val data = result.data ?: return@registerForActivityResult
        val uris = ArrayList<Uri>()
        val clip = data.clipData
        if (clip != null) {
            for (index in 0 until clip.itemCount) uris.add(clip.getItemAt(index).uri)
        } else {
            data.data?.let { uris.add(it) }
        }
        if (uris.isEmpty()) return@registerForActivityResult
        workExecutor.execute {
            val lines = ArrayList<String>()
            for (uri in uris) {
                val name = displayName(uri)
                if (!name.lowercase().endsWith(".xlsx")) {
                    lines.add("$name：失败。只支持 .xlsx。")
                    continue
                }
                try {
                    val bytes = contentResolver.openInputStream(uri)?.use { it.readBytes() }
                        ?: throw IllegalArgumentException("无法读取文件")
                    val report = catalog.addBytes(name, bytes)
                    lines.add(dev.stinger.match.formatBatchLine(name, report, ""))
                    report.rejected.take(3).forEach { row ->
                        lines.add("  第 ${row.row} 行：${row.reason}")
                    }
                } catch (exc: Exception) {
                    lines.add(dev.stinger.match.formatBatchLine(name, null, exc.message ?: "无法导入"))
                }
            }
            catalog.save(catalogDir())
            session.invalidate()
            runOnUiThread {
                refreshBanks()
                render(CameraReadout(null, "对准题目", lines.joinToString("\n")))
            }
        }
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
        val intent = Intent(Intent.ACTION_OPEN_DOCUMENT).apply {
            addCategory(Intent.CATEGORY_OPENABLE)
            type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            putExtra(Intent.EXTRA_ALLOW_MULTIPLE, true)
            addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
        }
        importLauncher.launch(intent)
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

    private fun render(readout: CameraReadout) {
        val answer = readout.answer
        if (answer.isNullOrEmpty()) {
            binding.answer.text = ""
            binding.answer.setTextColor(0xFFC62828.toInt())
            binding.badge.text = readout.badge
            binding.badge.setTextColor(0xFFECEFF1.toInt())
        } else {
            binding.answer.text = answer
            binding.answer.setTextColor(0xFFC62828.toInt())
            binding.badge.text = readout.badge
            binding.badge.setTextColor(if (readout.badge == "待确认") 0xFFFFB74D.toInt() else 0xFFECEFF1.toInt())
        }
        binding.context.text = readout.context
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
        contentResolver.query(uri, arrayOf(OpenableColumns.DISPLAY_NAME), null, null, null)?.use { cursor ->
            if (cursor.moveToFirst()) {
                val index = cursor.getColumnIndex(OpenableColumns.DISPLAY_NAME)
                if (index >= 0) return cursor.getString(index) ?: "题库.xlsx"
            }
        }
        return uri.lastPathSegment?.substringAfterLast('/') ?: "题库.xlsx"
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
}
