"""
Edge AI model management for HomePilot.

Handles model downloading, validation, and path resolution
for all AI components (Vosk STT, Piper TTS, Porcupine).
"""

from __future__ import annotations

import hashlib
import shutil
import subprocess
import zipfile
from pathlib import Path

from homepilot.utils.logger import get_logger

logger = get_logger("homepilot.edge_ai_models")

# Known model metadata
MODELS: dict[str, dict] = {
    "vosk-model-small-en-us-0.15": {
        "url": "https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip",
        "size_mb": 40,
        "type": "stt",
        "description": "Small English STT model — fast, good for RPi",
    },
    "vosk-model-en-us-0.22": {
        "url": "https://alphacephei.com/vosk/models/vosk-model-en-us-0.22.zip",
        "size_mb": 1800,
        "type": "stt",
        "description": "Large English STT model — best accuracy",
    },
}


class ModelManager:
    """
    AI model manager.

    Provides helpers to check, download, and validate
    AI models used by HomePilot.
    """

    def __init__(self, model_dir: str = "models") -> None:
        self._model_dir = Path(model_dir)
        self._model_dir.mkdir(parents=True, exist_ok=True)

    def is_available(self, model_name: str) -> bool:
        """Check if a model is downloaded and available."""
        model_path = self._model_dir / model_name
        return model_path.exists() and any(model_path.iterdir())

    def get_path(self, model_name: str) -> Path:
        """Get the full path to a model directory."""
        return self._model_dir / model_name

    def list_available(self) -> list[str]:
        """List all downloaded models."""
        models = []
        for item in self._model_dir.iterdir():
            if item.is_dir() and not item.name.startswith("."):
                models.append(item.name)
        return models

    def list_downloadable(self) -> list[dict]:
        """List all known models that can be downloaded."""
        result = []
        for name, info in MODELS.items():
            result.append({
                "name": name,
                "available": self.is_available(name),
                **info,
            })
        return result

    def download_model(self, model_name: str) -> bool:
        """
        Download a model by name.

        Args:
            model_name: Name of the model from MODELS registry.

        Returns:
            True if download succeeded.
        """
        if model_name not in MODELS:
            logger.error("Unknown model: %s", model_name)
            return False

        if self.is_available(model_name):
            logger.info("Model already available: %s", model_name)
            return True

        info = MODELS[model_name]
        url = info["url"]
        zip_path = self._model_dir / f"{model_name}.zip"

        logger.info(
            "Downloading %s (~%dMB)...",
            model_name,
            info["size_mb"],
        )

        try:
            # Use wget or Python urllib
            if shutil.which("wget"):
                subprocess.run(
                    ["wget", "-q", "-O", str(zip_path), url],
                    check=True,
                    timeout=600,
                )
            else:
                import urllib.request
                urllib.request.urlretrieve(url, str(zip_path))

            # Extract
            logger.info("Extracting %s...", model_name)
            with zipfile.ZipFile(zip_path, "r") as zf:
                zf.extractall(self._model_dir)

            # Cleanup zip
            zip_path.unlink()

            logger.info("Model %s downloaded and extracted.", model_name)
            return True

        except Exception as e:
            logger.error("Failed to download %s: %s", model_name, e)
            if zip_path.exists():
                zip_path.unlink()
            return False

    def check_model_files(self, model_path: str) -> dict[str, bool]:
        """
        Verify a model directory contains expected files.

        Returns a dict of checks and their status.
        """
        path = Path(model_path)
        checks = {
            "exists": path.exists(),
            "is_directory": path.is_dir() if path.exists() else False,
            "not_empty": bool(list(path.iterdir())) if path.exists() else False,
        }

        # Vosk model checks
        if path.exists() and (path / "conf").exists():
            checks["vosk_conf"] = (path / "conf" / "mfcc.conf").exists()
            checks["vosk_model"] = (path / "am" / "final.mdl").exists() or \
                                    (path / "model").exists()

        # Piper model checks
        if path.exists() and path.suffix == ".onnx":
            checks["piper_onnx"] = path.exists()
            checks["piper_config"] = Path(f"{path}.json").exists()

        return checks
