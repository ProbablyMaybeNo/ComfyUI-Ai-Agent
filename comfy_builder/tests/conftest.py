"""Shared fixtures for comfy_builder tests."""

import json
import pytest
from pathlib import Path
from unittest.mock import patch


# Minimal schema for testing — just the nodes used by planners
MOCK_SCHEMA = {
    "CheckpointLoaderSimple": {
        "input": {
            "required": {"ckpt_name": ["STRING", {}]},
        },
        "output": ["MODEL", "CLIP", "VAE"],
        "output_name": ["MODEL", "CLIP", "VAE"],
        "name": "CheckpointLoaderSimple",
        "display_name": "Load Checkpoint",
        "category": "loaders",
        "description": "Loads a checkpoint.",
    },
    "CLIPTextEncode": {
        "input": {
            "required": {
                "text": ["STRING", {"multiline": True}],
                "clip": ["CLIP", {}],
            },
        },
        "output": ["CONDITIONING"],
        "output_name": ["CONDITIONING"],
        "name": "CLIPTextEncode",
        "display_name": "CLIP Text Encode",
        "category": "conditioning",
        "description": "Encodes text.",
    },
    "EmptyLatentImage": {
        "input": {
            "required": {
                "width": ["INT", {}],
                "height": ["INT", {}],
                "batch_size": ["INT", {}],
            },
        },
        "output": ["LATENT"],
        "output_name": ["LATENT"],
        "name": "EmptyLatentImage",
        "display_name": "Empty Latent Image",
        "category": "latent",
        "description": "Creates empty latent.",
    },
    "KSampler": {
        "input": {
            "required": {
                "model": ["MODEL", {}],
                "positive": ["CONDITIONING", {}],
                "negative": ["CONDITIONING", {}],
                "latent_image": ["LATENT", {}],
                "seed": ["INT", {}],
                "steps": ["INT", {}],
                "cfg": ["FLOAT", {}],
                "sampler_name": ["STRING", {}],
                "scheduler": ["STRING", {}],
                "denoise": ["FLOAT", {}],
            },
        },
        "output": ["LATENT"],
        "output_name": ["LATENT"],
        "name": "KSampler",
        "display_name": "KSampler",
        "category": "sampling",
        "description": "Samples latent.",
    },
    "VAEDecode": {
        "input": {
            "required": {
                "samples": ["LATENT", {}],
                "vae": ["VAE", {}],
            },
        },
        "output": ["IMAGE"],
        "output_name": ["IMAGE"],
        "name": "VAEDecode",
        "display_name": "VAE Decode",
        "category": "latent",
        "description": "Decodes latent to image.",
    },
    "SaveImage": {
        "input": {
            "required": {
                "images": ["IMAGE", {}],
                "filename_prefix": ["STRING", {}],
            },
        },
        "output": [],
        "output_name": [],
        "name": "SaveImage",
        "display_name": "Save Image",
        "category": "image",
        "description": "Saves images.",
    },
    "LoraLoader": {
        "input": {
            "required": {
                "model": ["MODEL", {}],
                "clip": ["CLIP", {}],
                "lora_name": ["STRING", {}],
                "strength_model": ["FLOAT", {}],
                "strength_clip": ["FLOAT", {}],
            },
        },
        "output": ["MODEL", "CLIP"],
        "output_name": ["MODEL", "CLIP"],
        "name": "LoraLoader",
        "display_name": "Load LoRA",
        "category": "loaders",
        "description": "Loads LoRA.",
    },
    "ADE_AnimateDiffLoaderWithContext": {
        "input": {
            "required": {
                "model": ["MODEL", {}],
                "model_name": ["STRING", {}],
                "beta_schedule": ["STRING", {}],
            },
        },
        "output": ["MODEL"],
        "output_name": ["MODEL"],
        "name": "ADE_AnimateDiffLoaderWithContext",
        "display_name": "AnimateDiff Loader",
        "category": "Animate Diff",
        "description": "AnimateDiff loader.",
    },
    "CreateVideo": {
        "input": {
            "required": {
                "images": ["IMAGE", {}],
                "fps": ["FLOAT", {"default": 30.0}],
            },
        },
        "output": ["VIDEO"],
        "output_name": ["VIDEO"],
        "name": "CreateVideo",
        "display_name": "Create Video",
        "category": "image/video",
        "description": "Creates video from images.",
    },
    "SaveVideo": {
        "input": {
            "required": {
                "video": ["VIDEO", {}],
                "filename_prefix": ["STRING", {}],
                "format": ["COMBO", {}],
                "codec": ["COMBO", {}],
            },
        },
        "output": [],
        "output_name": [],
        "name": "SaveVideo",
        "display_name": "Save Video",
        "category": "image/video",
        "description": "Saves video.",
    },
}


@pytest.fixture
def mock_schema():
    """Patch schema.load() to return mock schema without disk access."""
    import comfy_builder.schema as schema_mod
    with patch("comfy_builder.schema.load", return_value=MOCK_SCHEMA):
        # Also set cache directly so node_exists/get_node work via load()
        old_cache = schema_mod._schema_cache
        schema_mod._schema_cache = MOCK_SCHEMA
        yield MOCK_SCHEMA
        schema_mod._schema_cache = old_cache


@pytest.fixture
def sample_text2img_workflow():
    """A minimal text2img workflow for testing."""
    return {
        "1": {
            "class_type": "CheckpointLoaderSimple",
            "inputs": {"ckpt_name": "test.safetensors"},
        },
        "2": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": "a cat", "clip": ["1", 1]},
        },
        "3": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": "blurry", "clip": ["1", 1]},
        },
        "4": {
            "class_type": "EmptyLatentImage",
            "inputs": {"width": 1024, "height": 1024, "batch_size": 1},
        },
        "5": {
            "class_type": "KSampler",
            "inputs": {
                "seed": 42, "steps": 20, "cfg": 7.0,
                "sampler_name": "euler", "scheduler": "normal", "denoise": 1.0,
                "model": ["1", 0], "positive": ["2", 0],
                "negative": ["3", 0], "latent_image": ["4", 0],
            },
        },
        "6": {
            "class_type": "VAEDecode",
            "inputs": {"vae": ["1", 2], "samples": ["5", 0]},
        },
        "7": {
            "class_type": "SaveImage",
            "inputs": {"filename_prefix": "test", "images": ["6", 0]},
        },
    }
