"""HomePilot - Privacy-First Edge AI Voice Assistant."""

from setuptools import setup, find_packages

setup(
    name="homepilot",
    version="2.0.0",
    description="Privacy-first Edge AI Voice Assistant for Raspberry Pi",
    author="HomePilot Team",
    python_requires=">=3.11",
    packages=find_packages(),
    install_requires=[
        "pvporcupine>=3.0.0",
        "pvrecorder>=1.2.0",
        "vosk>=0.3.45",
        "piper-tts>=1.2.0",
        "sounddevice>=0.4.6",
        "numpy>=1.24.0",
        "soundfile>=0.12.0",
        "aiohttp>=3.9.0",
        "cryptography>=41.0.0",
        "pyyaml>=6.0.1",
        "apscheduler>=3.10.0",
        "psutil>=5.9.0",
    ],
    entry_points={
        "console_scripts": [
            "homepilot=homepilot.main:main",
        ],
    },
    classifiers=[
        "Programming Language :: Python :: 3.11",
        "License :: OSI Approved :: MIT License",
        "Operating System :: POSIX :: Linux",
        "Topic :: Home Automation",
    ],
)
