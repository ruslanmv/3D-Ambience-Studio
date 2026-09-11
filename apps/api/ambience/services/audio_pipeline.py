from pathlib import Path
import shutil
import subprocess


def optimize_audio(source: Path, output_dir: Path) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg:
        out = output_dir / "ambience.ogg"
        cmd = [ffmpeg, "-y", "-i", str(source), "-vn", "-c:a", "libopus", "-b:a", "96k", str(out)]
        subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        return {"path": out, "codec": "opus", "bytes": out.stat().st_size}
    out = output_dir / f"ambience{source.suffix.lower()}"
    shutil.copy2(source, out)
    return {"path": out, "codec": "source", "bytes": out.stat().st_size, "warning": "ffmpeg not installed; source audio copied without transcoding"}
