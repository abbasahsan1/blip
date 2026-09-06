import os
import json
import asyncio
import logging
from pathlib import Path
from typing import Dict, Any, Tuple

logger = logging.getLogger("transcode-worker.transcoder")


async def probe_media(input_path: str) -> Dict[str, Any]:
    """
    Uses ffprobe to inspect media format, streams, and duration.
    """
    cmd = [
        "ffprobe",
        "-v", "error",
        "-print_format", "json",
        "-show_format",
        "-show_streams",
        input_path,
    ]
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    if proc.returncode != 0:
        raise RuntimeError(f"ffprobe failed: {stderr.decode()}")

    return json.loads(stdout.decode())


async def transcode_variants(input_path: str, output_dir: str) -> Tuple[Dict[str, str], float, str]:
    """
    Transcodes input media into 3 audio tiers (low, standard, high) in output_dir.
    Returns:
      (variants_dict, duration_seconds, source_type)
      where variants_dict is {"low": "/path/to/low.m4a", "standard": "...", "high": "..."}
      and source_type is "video_conversion" or "direct_upload".
    """
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # 1. Probe input
    probe_data = await probe_media(input_path)
    streams = probe_data.get("streams", [])
    has_video = any(s.get("codec_type") == "video" for s in streams)
    source_type = "video_conversion" if has_video else "direct_upload"

    format_info = probe_data.get("format", {})
    duration = float(format_info.get("duration", 0.0))

    # Output file paths
    low_path = str(out_dir / "low.m4a")
    standard_path = str(out_dir / "standard.m4a")
    high_path = str(out_dir / "high.m4a")

    # 2. Encode tiers using ffmpeg
    # Low: 32k stereo AAC
    cmd_low = [
        "ffmpeg", "-y", "-i", input_path,
        "-vn", "-c:a", "aac", "-b:a", "32k", "-ac", "2",
        low_path,
    ]
    # Standard: 96k stereo AAC
    cmd_standard = [
        "ffmpeg", "-y", "-i", input_path,
        "-vn", "-c:a", "aac", "-b:a", "96k", "-ac", "2",
        standard_path,
    ]
    # High: 192k stereo AAC
    cmd_high = [
        "ffmpeg", "-y", "-i", input_path,
        "-vn", "-c:a", "aac", "-b:a", "192k", "-ac", "2",
        high_path,
    ]

    for name, cmd in [("low", cmd_low), ("standard", cmd_standard), ("high", cmd_high)]:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()
        if proc.returncode != 0:
            raise RuntimeError(f"FFmpeg encoding for {name} failed: {stderr.decode()}")

    # Measure exact duration on high variant
    try:
        high_probe = await probe_media(high_path)
        high_dur = float(high_probe.get("format", {}).get("duration", duration))
        if high_dur > 0:
            duration = high_dur
    except Exception as e:
        logger.warning(f"Could not re-probe high variant duration: {e}")

    variants = {
        "low": low_path,
        "standard": standard_path,
        "high": high_path,
    }

    return variants, duration, source_type
