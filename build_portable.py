"""
Build Portable Release for Boomerang Looper
Creates a 1-file standalone executable (BoomerangLooper.exe) containing
Python runtime, Tkinter GUI, and embedded FFmpeg binaries into 1 single file.
"""

import os
import sys
import shutil
import zipfile
import subprocess
from pathlib import Path

def build_portable():
    print("=== Building Boomerang Looper 1-File Portable Executable ===")
    
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
    
    # 2. PyInstaller 1-file standalone build using --add-data (avoids zlib decompression lock)
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconsole",
        "--onefile",
        "--name", "BoomerangLooper",
        "--clean",
        "--add-data", f"{ffmpeg}{os.pathsep}.",
        "--add-data", f"{ffprobe}{os.pathsep}.",
        str(project_dir / "Boomerang_Looper.py")
    ]
    
    print("\nRunning PyInstaller (Building 1-file executable)...")
    print(" ".join(cmd))
    res = subprocess.run(cmd, cwd=str(project_dir))
    if res.returncode != 0:
        print("PyInstaller build failed!")
        sys.exit(res.returncode)
        
    exe_path = dist_dir / ("BoomerangLooper.exe" if os.name == "nt" else "BoomerangLooper")
    if not exe_path.exists():
        print(f"Error: Executable not found at {exe_path}")
        sys.exit(1)
        
    print(f"\n[OK] Single 1-file standalone executable built at: {exe_path}")
    
    # 3. Create portable .zip package containing the single executable and README
    zip_path = dist_dir / "BoomerangLooper_Portable.zip"
    print(f"Creating portable zip archive: {zip_path}")
    
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        z.write(exe_path, arcname=exe_path.name)
        readme = project_dir / "README.md"
        if readme.exists():
            z.write(readme, arcname="README.md")
                
    print(f"\n[OK] Portable release build complete!")
    print(f"Single Executable: {exe_path}")
    print(f"Portable Zip:       {zip_path}")

if __name__ == "__main__":
    build_portable()
