# Stinger

基于 OCR 的离线搜题软件。在 Windows 10 x64 上框选一块题目区域，用本机中文 OCR 读字，再在你自己导入的 Excel 题库里查找。不调用云端模型，不需要 API 密钥。

本仓库不包含任何私人题库。随程序提供的 `assets/stinger-question-template.xlsx` 只有三行标了【示例】的填法说明。

## 能做什么

- 框选一次后，松开鼠标就识别。文字稳定变化后再查；去掉空白和标点后没有实质变化则不重复查询。
- 大约十个汉字就可以先查。前缀对上多道且答案不同时不猜，继续识别。
- 选择题给出答案原文；选项文字对得上时才换算画面字母。判断题只显示「对」或「错」。
- 浮动面板显示题干匹配度、约十二个字的题干和红色答案。低置信或答案冲突标「待确认」，不当成确定答案。
- 「导入题库」可选一个或多个 xlsx。选一个导入这一份；选多个按文件名分别入库，并逐个报告成功、跳过和失败。
- 「导出模板」保存官方表。表头是：题型、题目、A–F、答案、难度、试题依据、试题解析、保命题。
- 可在「全部题库」和某一份题库之间切换，并记住上次的选择。
- 快捷键默认是框选 `Ctrl+Alt+F`、开始或暂停 `Ctrl+Alt+P`，可以改。Windows 上向系统登记热键，不安装键盘钩子。

界面是灰阶、细黑边和浅浮雕按钮。窗口图标用的是 `assets/stinger-app-icon.jpg`，以及由它缩小得到的 `assets/stinger.ico`。这不是 Apple 官方界面。

## 它不做的事

- 不使用云端 AI，也不把题目发到网上。
- 不自动点击选项，不向网页发送鼠标或键盘。
- 不隐藏窗口，不做穿透点击，不伪造焦点，也不声称截图或遮罩能避开页面的焦点检测。
- 第一次框选会打开可见遮罩，按系统规则拿走焦点。之后自动查题尽量不把本程序变成前台，但你点击设置窗或拖动边框时，网页仍可能失去焦点。程序不会把焦点送回网页。
- 不编造解析。题库里没有解析，就写「题库未提供解析」。

## 在源码里运行

需要 64 位 Python 3.12。识别库钉在 `rapidocr-onnxruntime` 1.4.4，它只声明支持到 3.12；当前的 numpy 也没有更旧的 Windows 轮子。

```bash
python3.12 -m venv .venv
.venv/bin/pip install -r requirements.txt
PYTHONPATH=src .venv/bin/python -m screenmatch
```

Windows 可以双击 `启动Stinger.bat`。它会查找 `SCREENMATCH_PYTHON`、上一级的 `Python312\python.exe`、本机用户目录里的 Python 3.12，然后才是 `py -3.12` 和 `python`。模型和依赖需要先能下载安装包；装好之后 OCR 读取 wheel 里自带的 ONNX 文件，不再联网识别。

```powershell
.\.venv\Scripts\python -m screenmatch
```

测试：

```bash
PYTHONPATH=src .venv/bin/python -m pytest -q
```

## Windows 打包

当前环境没有生成过可分发的 exe。在 Windows 10 x64 上可以试：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\build_windows.ps1
```

脚本只接受 64 位 Python 3.12。成功后请保留整个 `dist\Stinger` 文件夹（`Stinger.exe`、`_internal` 和 `assets`）。运行这份目录不再需要 Python。打包脚本还没有在本仓库的编写环境里执行过。

## Android

手机版是相机实时搜题：预览一直开着，把题目放进取景框后自动识别并在本机题库里查找。不拍照，也不需要再点一次确认。

题库只从手机里已有的 Excel 选择。请先用数据线或普通的文件分享把 xlsx 拷到手机（下载、微信或 QQ 接收、USB），再点「导入题库」，在文件管理器里选这个 .xlsx。选择器会按扩展名和常见文件类型一起列出，选中后先复制到应用自己的目录再读取。成功或失败都会在画面上写出原因。可以同时保留多份题库，并在「全部题库」和某一份之间切换。表头与 `assets/stinger-question-template.xlsx` 相同。程序不提供局域网、Wi-Fi、二维码、附近分享或 HTTP 传题库。

识别使用随安装包带上的中文 OCR 模型，不在第一次打开时下载。清单里去掉了网络权限。匹配规则从桌面版移植，包括小数、否定和数字、判断题只显示「对」或「错」，以及只有选项原文对得上才换算画面字母。确定答案用红色 `#c62828`。没有匹配、题目变了，或几道题答案冲突时，不把上一题的答案继续当成当前答案；冲突和不确定标「待确认」。

已核对的构建范围：

- `minSdk` 24（Android 7.0）。目标是 Android 7 的华为 Mate 8 和 Android 9 的 Xperia 这一档，以及更新的 arm 手机。
- 调试 APK 只包含 `armeabi-v7a` 和 `arm64-v8a`。x86 模拟器装不上这份包。
- 桌面版仍是 Windows 上的 Python，界面和行为没有改。手机 OCR 用的是 ML Kit 中文模型，不是桌面的 RapidOCR，同一张画面的文字可能不完全一样。
- 这台构建环境没有手机相机。取景、权限弹窗、实机识别速度和各机型对焦都还没有在真机上试过。

在装好 Android SDK 后：

```bash
cd android
# local.properties 里写 sdk.dir=/你的/Android/Sdk
./gradlew :core:test :app:lintDebug :app:assembleDebug
```

调试包在 `android/app/build/outputs/apk/debug/app-debug.apk`。

## 许可

Apache License 2.0。独立实现，不是 ibosOCR 的改版。说明见 `NOTICE`。
