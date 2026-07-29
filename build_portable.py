"""
Build Portable Release for Boomerang Looper
Creates a clean, instant-launch portable folder distribution containing
BoomerangLooper.exe + FFmpeg binaries, packaged into BoomerangLooper_Portable.zip.
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
    portable_dir = dist_dir / "BoomerangLooper"
    
    # Clean previous build artifacts
    if dist_dir.exists():
        try:
            shutil.rmtree(dist_dir, ignore_errors=True)
        except Exception:
            pass
            
    # 2. Run PyInstaller in --onedir mode (prevents temp archive decompression locks)
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconsole",
        "--onedir",
        "--name", "BoomerangLooper",
        "--clean",
        str(project_dir / "Boomerang_Looper.py")
    ]
    
    print("\nRunning PyInstaller (--onedir mode for instant startup)...")
    print(" ".join(cmd))
    res = subprocess.run(cmd, cwd=str(project_dir))
    if res.returncode != 0:
        print("PyInstaller build failed!")
        sys.exit(res.returncode)
        
    exe_path = portable_dir / ("BoomerangLooper.exe" if os.name == "nt" else "BoomerangLooper")
    if not exe_path.exists():
        print(f"Error: Executable not found at {exe_path}")
        sys.exit(1)
        
    # 3. Copy FFmpeg & FFprobe directly into the portable directory
    print("\nBundling FFmpeg & FFprobe into portable folder...")
    shutil.copy2(ffmpeg, portable_dir / "ffmpeg.exe")
    shutil.copy2(ffprobe, portable_dir / "ffprobe.exe")
    
    readme = project_dir / "README.md"
    if readme.exists():
        shutil.copy2(readme, portable_dir / "README.md")
        
    print(f"[OK] Portable directory assembled at: {portable_dir}")
    
    # 4. Create portable .zip package containing the BoomerangLooper folder
    zip_path = dist_dir / "BoomerangLooper_Portable.zip"
    print(f"Creating portable zip archive: {zip_path}")
    
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for root, _, files in os.walk(portable_dir):
            for file in files:
                full_p = Path(root) / file
                rel_p = Path("BoomerangLooper") / full_p.relative_to(portable_dir)
                z.write(full_p, arcname=rel_p)
                
    print(f"\n[OK] Portable release build complete!")
    print(f"Portable Folder: {portable_dir}")
    print(f"Portable Zip:    {zip_path}")

if __name__ == "__main__":
    build_portable()
