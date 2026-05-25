from __future__ import annotations

import torch
from utils.logger import get_logger

logger = get_logger(__name__)


def detect_device(preference: str = "auto") -> torch.device:
    """Resolve the best available compute device.

    Priority: CUDA > MPS (Apple Silicon) > CPU.
    ``preference`` overrides auto-detection when set to 'cpu', 'cuda', or 'mps'.
    """
    if preference != "auto":
        device = torch.device(preference)
        logger.info("device.forced", device=str(device))
        return device

    if torch.cuda.is_available():
        device = torch.device("cuda")
        name = torch.cuda.get_device_name(0)
        mem_gb = torch.cuda.get_device_properties(0).total_memory / 1e9
        logger.info("device.cuda", name=name, vram_gb=round(mem_gb, 1))
    elif torch.backends.mps.is_available():
        device = torch.device("mps")
        logger.info("device.mps", note="Apple Silicon GPU")
    else:
        device = torch.device("cpu")
        logger.info("device.cpu", note="No GPU found, running on CPU")

    return device


def gpu_info() -> dict:
    if not torch.cuda.is_available():
        return {"available": False, "device": "cpu"}

    props = torch.cuda.get_device_properties(0)
    return {
        "available": True,
        "device": "cuda",
        "name": props.name,
        "vram_gb": round(props.total_memory / 1e9, 2),
        "cuda_version": torch.version.cuda,
        "torch_version": torch.__version__,
    }
