# PaddleOCR 三模式本地演示

一个独立的 FastAPI 单体应用，为本机 `/home/lyc/PaddleOCR` 提供三种 GPU 推理演示：

- PP-OCRv6 Medium：文字检测、识别、置信度和可视化。
- PP-StructureV3：版面、表格、公式、Markdown、JSON 和 DOCX。
- PaddleOCR-VL 1.6：本地原生视觉语言模型文档解析。

## 安装与启动

```bash
cd /home/lyc/paddleocr_web_demo
./setup.sh
./preload_models.sh
./run_local.sh
```

浏览器打开 <http://127.0.0.1:8000>。


首次完整预热会下载多套模型，占用较多时间与磁盘。也可以先只预热一种模式：

```bash
./preload_models.sh ocr
./preload_models.sh structure
./preload_models.sh vl
```

## 临时公网演示

```bash
./run_public.sh
```

脚本会下载 `cloudflared` 并显示随机的 `trycloudflare.com` 地址。该地址没有登录保护，请只在演示期间保持终端运行。

## 运行约束

- 服务只监听 `127.0.0.1`，公网访问经 Cloudflare Quick Tunnel 转发。
- 单次只运行一个 GPU 任务，最多保留 3 个等待任务。
- 每个来源 IP 每 10 分钟最多提交 5 次。
- 文件最大 15MB，图片最大 2500 万像素。
- OCR/Structure PDF 最多 10 页，VL PDF 最多 3 页。
- 结果在完成或失败 30 分钟后自动清理。
- 三个模式不会同时常驻 GPU；切换模式时工作进程会重启以释放显存。

## 测试

```bash
source .venv/bin/activate
pytest
```

