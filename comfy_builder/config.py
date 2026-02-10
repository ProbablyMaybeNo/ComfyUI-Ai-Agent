"""ComfyUI AI Builder — Configuration."""

import os
from pathlib import Path

# Project root (parent of comfy_builder) — for .env
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Load .env from project root if python-dotenv is available
try:
    from dotenv import load_dotenv
    load_dotenv(PROJECT_ROOT / ".env")
except ImportError:
    pass

# Builder root
BUILDER_DIR = Path(__file__).parent.resolve()

# ComfyUI
COMFYUI_URL = os.environ.get("COMFYUI_URL", "http://127.0.0.1:8000")
COMFYUI_PATH = Path(os.environ.get(
    "COMFYUI_PATH",
    r"C:\Users\Admin\Documents\ComfyUI"
))

# ComfyUI sub-paths (input = where LoadImage looks for files)
COMFYUI_INPUT_DIR = COMFYUI_PATH / "input"
CUSTOM_NODES_DIR = COMFYUI_PATH / "custom_nodes"
MODELS_DIR = COMFYUI_PATH / "models"
CHECKPOINTS_DIR = MODELS_DIR / "checkpoints"
LORAS_DIR = MODELS_DIR / "loras"
VAE_DIR = MODELS_DIR / "vae"
CONTROLNET_DIR = MODELS_DIR / "controlnet"
IPADAPTER_DIR = MODELS_DIR / "ipadapter"
CLIP_VISION_DIR = MODELS_DIR / "clip_vision"
ANIMATEDIFF_DIR = MODELS_DIR / "animatediff_models"

# Builder sub-paths
WORKFLOWS_DIR = BUILDER_DIR / "workflows"
TEMPLATES_DIR = WORKFLOWS_DIR / "templates"
DRAFTS_DIR = WORKFLOWS_DIR / "drafts"
CURRENT_WORKFLOW = WORKFLOWS_DIR / "current.json"

SCHEMA_DIR = BUILDER_DIR / "schema"
SCHEMA_FILE = SCHEMA_DIR / "node_schema.json"
SCHEMA_META = SCHEMA_DIR / "schema_meta.json"

INSTALLS_DIR = BUILDER_DIR / "installs"
ALLOWLIST_FILE = INSTALLS_DIR / "allowlist.json"
NODE_PACKS_FILE = INSTALLS_DIR / "node_packs.json"
INSTALL_LOG = INSTALLS_DIR / "install.log"

LOGS_DIR = BUILDER_DIR / "logs"
RUNS_DIR = LOGS_DIR / "runs"

OUT_DIR = BUILDER_DIR / "out"
IMAGES_DIR = OUT_DIR / "images"
VIDEO_DIR = OUT_DIR / "video"
METADATA_FILE = OUT_DIR / "metadata.jsonl"

# Defaults
DEFAULT_CHECKPOINT = "realvisxlV50_v50LightningBakedvae.safetensors"
DEFAULT_STEPS = 20
DEFAULT_CFG = 7.0
DEFAULT_SAMPLER = "euler"
DEFAULT_SCHEDULER = "normal"
DEFAULT_WIDTH = 1024
DEFAULT_HEIGHT = 1024
DEFAULT_NEGATIVE = "blurry, deformed, ugly, watermark, text, low quality"

# Chat UI
CHAT_PORT = int(os.environ.get("CHAT_PORT", "8085"))
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen2.5:7b")

# Limits
MAX_BATCH_SIZE = 100
MAX_RETRIES = 3
RUN_TIMEOUT_S = 900  # 15 min — AnimateDiff SDXL can take 8+ min on 8GB VRAM
MAX_QUEUE_DEPTH = 5
