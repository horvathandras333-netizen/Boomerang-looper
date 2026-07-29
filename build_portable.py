"""
Build Portable Release for Boomerang Looper
Automatically bundles Python script + FFmpeg binaries into a single-file executable
and creates a portable .zip release.
"""

import os
import sys
import shutil
import zipfile
import subprocess
from pathlib import Path

def build_portable():
    print("=== Building Boomerang Looper Portable Release ===")
    
    # 1. Locate FFmpeg & FFprobe
    ffmpeg = shutil.which("ffmpeg.exe") or shutil.which("ffmpeg")
    ffprobe = shutil.which("ffprobe.exe") or shutil.which("ffprobe")
    
    if not ffmpeg or not ffprobe:
        print("Error: FFmpeg or FFprobe binaries not found on PATH.")
        sys.exit(1)
        
    print(f"Found FFmpeg: {ffmpeg}")
    print(f"Found FFprobe: {ffprobe}")
    
    project_dir = Path(__file__).parent.resolve()
    dist_dir = project_dir / "dist"
    
    # 2. Construct PyInstaller command
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconsole",
        "--onefile",
        "--name", "BoomerangLooper",
        "--add-binary", f"{ffmpeg}{os.pathsep}.",
        "--add-binary", f"{ffprobe}{os.pathsep}.",
        str(project_dir / "Boomerang_Looper.py")
    ]
    
    print("\nRunning PyInstaller...")
    print(" ".join(cmd))
    res = subprocess.run(cmd, cwd=str(project_dir))
    if res.returncode != 0:
        print("PyInstaller build failed!")
        sys.exit(res.returncode)
        
    exe_path = dist_dir / ("BoomerangLooper.exe" if os.name == "nt" else "BoomerangLooper")
    if not exe_path.exists():
        print(f"Error: Executable not found at {exe_path}")
        sys.exit(1)
        
    print(f"\n[OK] Standalone executable created: {exe_path}")
    
    # 3. Create portable .zip package
    zip_path = dist_dir / "BoomerangLooper_Portable.zip"
    print(f"Creating portable zip archive: {zip_path}")
    
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        z.write(exe_path, arcname=exe_path.name)
        readme = project_dir / "README.md"
        if readme.exists():
            z.write(readme, arcname="README.md")
            
    print(f"\n[OK] Portable release build complete!")
    print(f"Executable: {exe_path}")
    print(f"Portable Zip: {zip_path}")

if __name__ == "__main__":
    build_portable()
