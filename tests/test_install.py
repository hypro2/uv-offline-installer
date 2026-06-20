import os
import shutil
import sys
import zipfile
import urllib.request
from urllib.error import URLError

# Mock urllib.request.urlopen to always fail, simulating offline network
def mock_urlopen(*args, **kwargs):
    raise URLError("Simulated offline network error")
urllib.request.urlopen = mock_urlopen

# Add workspace directory to python path
workspace_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, workspace_dir)

from src.installer import install_offline

def extract_payload(zip_path, extract_dir):
    if os.path.exists(extract_dir):
        shutil.rmtree(extract_dir)
    os.makedirs(extract_dir)
    with zipfile.ZipFile(zip_path, 'r') as zipf:
        zipf.extractall(extract_dir)

def test_installations():
    print("Starting simulated offline target installation tests...")
    
    zip_all = os.path.join(workspace_dir, "test_output_all", "uv-offline-all.zip")
    zip_new = os.path.join(workspace_dir, "test_output_new", "uv-offline-new.zip")
    
    # 1. Prepare payload directories
    payload_all = os.path.join(workspace_dir, "test_payload_all")
    payload_new = os.path.join(workspace_dir, "test_payload_new")
    
    extract_payload(zip_all, payload_all)
    extract_payload(zip_new, payload_new)
    
    # Target directory for installing uvtool
    install_target = os.path.join(workspace_dir, "test_target_install")
    if os.path.exists(install_target):
        shutil.rmtree(install_target)
    os.makedirs(install_target)
    
    def log(msg):
        print(f"[INSTALL LOG] {msg}")
    def progress(pct):
        pass

    # TEST A: Incremental Pack installation on a CLEAN directory (Must FAIL)
    print("\n--- TEST A: Installing Incremental Pack on a clean directory (Expect Failure) ---")
    try:
        install_offline(
            payload_dir=os.path.join(payload_new, "payload"),
            install_dir=install_target,
            log_callback=log,
            progress_callback=progress,
            register_global_env=False  # Do not mess up user environment variables in tests
        )
        print("FAIL: Installation succeeded when it should have failed (missing uv.exe and no archive)!")
        return False
    except FileNotFoundError as fnf:
        print(f"SUCCESS (Expected Failure): Caught expected exception: {fnf}")
    except Exception as e:
        print(f"FAIL: Caught unexpected exception: {e}")
        return False

    # TEST B: Full Pack installation on a CLEAN directory (Must SUCCESS)
    print("\n--- TEST B: Installing Full Pack on a clean directory (Expect Success) ---")
    try:
        success = install_offline(
            payload_dir=os.path.join(payload_all, "payload"),
            install_dir=install_target,
            log_callback=log,
            progress_callback=progress,
            register_global_env=False
        )
        if success:
            print("SUCCESS: Full installation completed successfully.")
            # Verify uv.exe exists
            if os.path.exists(os.path.join(install_target, "uv.exe")):
                print("SUCCESS: verified uv.exe exists in target directory.")
            else:
                print("FAIL: uv.exe was not created in target directory.")
                return False
        else:
            print("FAIL: Full installation returned False status.")
            return False
    except Exception as e:
        print(f"FAIL: Full installation raised unexpected exception: {e}")
        import traceback
        traceback.print_exc()
        return False

    # TEST C: Incremental Pack installation on the PRE-INSTALLED directory (Must SUCCESS)
    # We will copy a new dummy wheel into the incremental pack payload/wheels to simulate a new update
    print("\n--- TEST C: Installing Incremental Pack on a pre-installed directory (Expect Success) ---")
    
    # Create dummy wheel in payload_new/payload/wheels
    wheels_dir = os.path.join(payload_new, "payload", "wheels")
    os.makedirs(wheels_dir, exist_ok=True)
    dummy_wheel_path = os.path.join(wheels_dir, "dummy_pkg-1.0.0-py3-none-any.whl")
    with open(dummy_wheel_path, "w") as f:
        f.write("dummy")
        
    try:
        success = install_offline(
            payload_dir=os.path.join(payload_new, "payload"),
            install_dir=install_target,
            log_callback=log,
            progress_callback=progress,
            register_global_env=False
        )
        if success:
            print("SUCCESS: Incremental installation completed successfully.")
            # Verify dummy wheel was copied
            target_dummy = os.path.join(install_target, "wheels", "dummy_pkg-1.0.0-py3-none-any.whl")
            if os.path.exists(target_dummy):
                print("SUCCESS: verified dummy wheel was successfully updated/copied.")
            else:
                print("FAIL: dummy wheel was not found in target wheels folder.")
                return False
        else:
            print("FAIL: Incremental installation returned False status.")
            return False
    except Exception as e:
        print(f"FAIL: Incremental installation raised unexpected exception: {e}")
        return False

    print("\nAll installation tests completed successfully!")
    return True

if __name__ == "__main__":
    if test_installations():
        sys.exit(0)
    else:
        sys.exit(1)
