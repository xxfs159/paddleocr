# PaddleOCR 本地演示站

独立的 FastAPI 应用，为本地 PaddleOCR 源码提供三个 GPU 推理入口：

- **PP-OCRv6 Medium**：文本检测与识别、置信度和可视化结果。
- **PP-StructureV3**：版面、表格、公式，以及 Markdown、JSON、DOCX 结果。
- **PaddleOCR-VL 1.6**：视觉语言模型文档解析。

## 目录

```text
app/          FastAPI 路由、推理、任务管理、输入校验
scripts/      模型预热脚本
static/       浏览器界面
tests/        应用测试
data/         运行时任务与结果（自动生成，不提交到 Git）
.tools/       临时工具，例如 cloudflared（自动生成，不提交到 Git）
```

## 环境要求

- Linux x86_64、Python 3.12、Bash。
- NVIDIA GPU 和兼容 CUDA 12.9 的驱动。
- 安装及首次运行模型需要联网。

`setup.sh` 当前安装 PaddlePaddle GPU 3.2.1 的 CUDA 12.9 wheel，并通过 `PaddleOCR` 子模块安装项目依赖。若使用其他 CUDA、Python 或硬件环境，请先检查并调整该脚本。

## 安装与本地运行

从仓库根目录克隆时建议包含子模块：

```bash
git clone --recurse-submodules https://github.com/xxfs159/paddleocr.git
cd paddleocr/paddleocr_web_demo
./setup.sh
./preload_models.sh
./run_local.sh
```

如果克隆时未包含子模块，请先回到仓库根目录执行：

```bash
git submodule update --init --recursive
```

服务默认监听 `127.0.0.1:8000`。访问 <http://127.0.0.1:8000>。

首次预热会下载多套模型，时间和磁盘占用较大。可只预热所需模式：

```bash
./preload_models.sh ocr
./preload_models.sh structure
./preload_models.sh vl
```

## 配置

| 环境变量 | 默认值 | 说明 |
| --- | --- | --- |
| `PADDLEOCR_DIR` | 仓库根目录下的 `PaddleOCR/` | PaddleOCR 源码位置 |
| `PADDLE_DEMO_DATA_DIR` | `data/` | 上传文件、任务状态和结果的运行时目录 |
| `PADDLE_DEMO_MODEL_TIMEOUT` | `1800` | 启动模型工作进程的超时时间（秒） |
| `PADDLE_DEMO_JOB_TIMEOUT` | `1800` | 单个任务的超时时间（秒） |
| `HOST` | `127.0.0.1` | 本地服务器监听地址 |
| `PORT` | `8000` | 本地服务器端口 |

例如，`PADDLEOCR_DIR=/opt/PaddleOCR ./run_local.sh` 可以指定单独安装的源码目录。设置 `HOST=0.0.0.0` 会让服务监听所有网络接口，请只在可信网络和受控环境中使用。

## 临时公网演示

```bash
./run_public.sh
```

脚本会下载 `cloudflared`（如本地尚未安装）并创建临时 Cloudflare Quick Tunnel。公网链接没有登录保护，持有链接的人都可以提交任务。演示期间保持终端运行，结束后按 `Ctrl+C` 关闭服务和隧道。

## 运行限制

- 服务一次处理一个 GPU 任务，最多排队 3 个任务。
- 每个来源 IP 每 10 分钟最多提交 5 次。
- 上传文件最大 15 MB；图片最大 2500 万像素。
- OCR 和 Structure 模式的 PDF 最多 10 页；VL 模式最多 3 页。
- 任务完成或失败 30 分钟后清理结果。
- 任一时刻只加载一种推理模式；切换时重启工作进程以释放显存。

## 开发与测试

```bash
source .venv/bin/activate
pytest
```

应用入口为 `app.main:app`。本地启动脚本使用单个 Uvicorn worker，因为 GPU 队列和模型工作进程由应用统一管理。


## Security boundaries

Markdown permits only explicit `http` and `https` schemes. Relative URLs,
fragments, and protocol-relative URLs remain supported; local `markdown_assets/`
images are rewritten to the job artifact endpoint. The page CSP independently
restricts image loading to same-origin, data, and blob sources.

Sample paths are resolved against the real `PADDLEOCR_DIR` and must name a file
strictly below it. In-root absolute paths and symlinks are supported; escaping
paths, missing files, and resolution errors return 404. Keep the sample tree and
its parent directories unwritable by untrusted users/processes: resolving a path
before `FileResponse` opens it does not prevent concurrent filesystem replacement.
