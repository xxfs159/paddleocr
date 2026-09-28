# PaddleOCR Local Demo

A GPU-backed web demo for running three PaddleOCR document pipelines locally:

- **PP-OCRv6 Medium** for text detection, recognition, confidence scores, and annotated images.
- **PP-StructureV3** for document layout, tables, formulas, Markdown, JSON, and DOCX output.
- **PaddleOCR-VL 1.6** for visual document parsing.

This repository contains the demo application. The upstream PaddleOCR source is tracked as the `PaddleOCR` Git submodule.

## Repository layout

```text
.
├── PaddleOCR/                 # PaddlePaddle/PaddleOCR source submodule
├── paddleocr_web_demo/
│   ├── app/                    # FastAPI routes, inference, job queue, validation
│   ├── scripts/                # Model preparation helpers
│   ├── static/                 # Browser UI
│   ├── tests/                  # Application tests
│   ├── setup.sh                # Create the virtual environment and install dependencies
│   ├── preload_models.sh       # Download and warm the selected models
│   └── run_local.sh            # Start the local web server
└── README.md
```

## Requirements

- Linux x86_64 with Python 3.12.
- NVIDIA GPU and a CUDA 12.9 compatible driver for the supplied PaddlePaddle GPU wheel.
- `git`, `bash`, and network access for installing dependencies and downloading models.

The setup script currently pins PaddlePaddle GPU 3.2.1 for CUDA 12.9. Review `paddleocr_web_demo/setup.sh` before using a different Python, CUDA, or GPU configuration.

## Clone and start

Clone the project and its PaddleOCR source together:

```bash
git clone --recurse-submodules https://github.com/xxfs159/paddleocr.git
cd paddleocr/paddleocr_web_demo
./setup.sh
./preload_models.sh
./run_local.sh
```

If the repository was cloned without submodules, initialize the source before setup:

```bash
git submodule update --init --recursive
```

Open <http://127.0.0.1:8000> after the server starts. The first full model preload downloads several large models. To warm one mode only, run `./preload_models.sh ocr`, `./preload_models.sh structure`, or `./preload_models.sh vl`.

The PaddleOCR source path defaults to the checked-out `PaddleOCR` submodule. Set `PADDLEOCR_DIR` if you keep that source elsewhere. Other useful settings include `PADDLE_DEMO_DATA_DIR`, `HOST`, and `PORT`.

## Temporary public demo

`./run_public.sh` starts the local server and opens a temporary Cloudflare Quick Tunnel. Anyone with the generated URL can submit jobs while it is running; the demo does not provide user authentication. Keep the script running only for the duration of a demonstration.

## Runtime limits

- One GPU job runs at a time, with up to three queued jobs.
- Each client IP can submit five jobs per ten minutes.
- Uploads are limited to 15 MB and images to 25 million pixels.
- OCR and Structure PDF input is limited to 10 pages; VL PDF input is limited to 3 pages.
- Job results are removed 30 minutes after completion or failure.
- Only one inference mode stays loaded at a time; switching modes restarts the worker to release GPU memory.

## Development

From `paddleocr_web_demo/`, install the development dependencies in the project virtual environment and run the tests:

```bash
source .venv/bin/activate
pytest
```

See [the demo README](paddleocr_web_demo/README.md) for setup details and operational notes.

## License

The demo code in this repository is distributed under the included Apache-2.0 license. The PaddleOCR submodule is maintained by PaddlePaddle; see its repository for license and attribution details.

