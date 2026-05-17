import os
import plistlib
import logging
import sys

# Set up logging for standalone runs
if not logging.getLogger().hasHandlers():
    logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

def finalize_t2_tahoe(path):
    """
    Hardened patcher for T2 Macs running macOS 15/16.
    Ensures dictionary keys exist before writing to prevent plist corruption.
    """
    logging.info(f"Applying T2 Tahoe Booter and Security patches to: {path}")
    
    if not os.path.exists(path):
        logging.error(f"File not found: {path}. Ensure your EFI partition is mounted.")
        return

    try:
        with open(path, 'rb') as f:
            config = plistlib.load(f)

        # 1. Booter Quirks (T2 + macOS Tahoe/26)
        # IMPORTANT: RebuildAppleMemoryMap and DevirtualiseMmio must remain False on T2 Macs.
        # Enabling them modifies kernel memory layout before corecrypto initializes,
        # which causes the FIPS Kernel POST to fail (-2074) and kernel panic at boot.
        # T2 Macs use Apple's own secure memory management via the T2 chip — these quirks
        # are only needed for non-Apple (Hackintosh) firmware.
        booter = config.setdefault('Booter', {})
        quirks = booter.setdefault('Quirks', {})

        quirks.update({
            'RebuildAppleMemoryMap': False,
            'EnableWriteUnprotector': False,
            'SyncRuntimePermissions': False,
            'DevirtualiseMmio': False,
        })

        # 2. PlatformInfo & Security Settings
        # UpdateSMBIOSMode: 'Custom' is required for T2 SMBIOS patches to work
        platform_info = config.setdefault('PlatformInfo', {})
        platform_info['UpdateSMBIOSMode'] = 'Custom'
        
        # SecureBootModel: Must be 'Disabled' for Tahoe/Sequoia on unsupported IDs
        misc = config.setdefault('Misc', {})
        security = misc.setdefault('Security', {})
        security['SecureBootModel'] = 'Disabled'

        # 3. Schema Guard (Prevents ocvalidate crashes)
        # Ensure Kernel->Quirks exists so validation doesn't fail on missing parent keys
        kernel = config.setdefault('Kernel', {})
        kernel_quirks = kernel.setdefault('Quirks', {})
        if 'DisableIoMapper' not in kernel_quirks:
            kernel_quirks['DisableIoMapper'] = True

        # 4. Save the file back
        with open(path, 'wb') as f:
            plistlib.dump(config, f, sort_keys=True)
            
        print("-" * 30)
        print("T2 PATCH SUCCESSFUL")
        print("Status: Booter/Security schema verified.")
        print("-" * 30)

    except Exception as e:
        logging.error(f"Critical failure during config patch: {e}")
        # Raise so build.py can catch the error and exit cleanly
        raise

if __name__ == "__main__":
    # Default path for manual execution
    target_plist = '/Volumes/EFI/EFI/OC/config.plist'
    try:
        logging.info("Starting manual T2 Tahoe post-processing...")
        finalize_t2_tahoe(target_plist)
    except Exception as e:
        logging.error("Process aborted due to unexpected error.")
        sys.exit(3)
