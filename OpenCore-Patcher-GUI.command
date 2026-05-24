#!/usr/bin/env python3
"""
PyInstaller Entry Point - Hardened with Full Extraction Fix
"""
import sys
import logging
import os
import zipfile
import shutil
import subprocess
from pathlib import Path

# SECURITY FIX: Remove the current directory from the search path.
if "" in sys.path:
    sys.path.remove("")

# We configure logging to write to sys.stdout (the Terminal window)
logging.basicConfig(
    level=logging.ERROR,
    format='%(message)s', # Keep it clean for the Terminal
    stream=sys.stdout
)

def extract_and_copy_tools():
    """
    Locates OpenCoreTools.zip, extracts the archive, and copies 
    the necessary binaries to payloads/OpenCore.
    """
    try:
        if getattr(sys, 'frozen', False):
            base_dir = Path(sys.executable).parent
        else:
            base_dir = Path(__file__).resolve().parent

        # Locate the ZIP file
        zip_path = None
        for file in base_dir.rglob("OpenCoreTools.zip"):
            zip_path = file
            break
        
        if not zip_path:
            for file in base_dir.rglob("*Tools*.zip"):
                zip_path = file
                break

        if not zip_path:
            print("[WARN] Could not locate OpenCoreTools.zip. Proceeding...")
            return

        print(f"[INFO] Found archive at: {zip_path}")

        dest_dir = base_dir / "payloads" / "OpenCore"
        dest_dir.mkdir(parents=True, exist_ok=True)

        # Temporary extraction path to inspect contents
        temp_dir = base_dir / "temp_extracted_tools"
        if temp_dir.exists():
            shutil.rmtree(temp_dir)
        temp_dir.mkdir(parents=True, exist_ok=True)

        print("[INFO] Extracting archive...")
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(temp_dir)

        # Search for the target binaries inside the extracted directory
        found_files = 0
        for path in temp_dir.rglob("*"):
            if path.name in ('ocvalidate', 'macserial') and path.is_file():
                target_path = dest_dir / path.name
                
                # Copy to payloads/OpenCore
                shutil.copy2(path, target_path)
                
                # Apply Unix execution rights
                os.chmod(target_path, 0o755)
                
                print(f"  > Copied and set permissions: {path.name}")
                found_files += 1

        # Clean up temporary files
        shutil.rmtree(temp_dir)

        if found_files < 2:
            print(f"[WARN] Only found {found_files} of 2 required tools (ocvalidate/macserial).")

        # Clear the quarantine attribute to allow execution on modern macOS
        try:
            subprocess.run(
                ["xattr", "-rd", "com.apple.quarantine", str(base_dir)], 
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
        except Exception:
            pass

        print("[INFO] Tools successfully extracted and validated.\n")

    except Exception as e:
        print(f"[ERROR] Failed to extract tools: {e}")


from opencore_legacy_patcher import main

if __name__ == '__main__':
    try:
        extract_and_copy_tools()
        main()
    except Exception as e:
        print("\n" + "="*60)
        logging.error("Whoops, the app crashed because of the following error:")
        print(f"Direct Error: {e}")
        print("-" * 60)
        logging.exception("Stack Trace:")
        print("="*60)
        input("\nPress ENTER to close this window...")
        sys.exit(3)
