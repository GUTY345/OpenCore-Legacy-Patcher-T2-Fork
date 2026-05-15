import os
import plistlib
import logging
import sys

# Set up logging for standalone runs
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

config_path = '/Volumes/EFI/EFI/OC/config.plist'

def finalize_t2_tahoe(path):
    logging.info("Applying T2 Tahoe Booter and Security patches...")
    
    if not os.path.exists(path):
        logging.error(f"File not found: {path}. Ensure your EFI partition is mounted.")
        return

    try:
        with open(path, 'rb') as f:
            config = plistlib.load(f)

        # 1. Booter Quirks (Stability for T2 + macOS 26)
        if 'Booter' not in config: config['Booter'] = {'Quirks': {}}
        if 'Quirks' not in config['Booter']: config['Booter']['Quirks'] = {}
        
        config['Booter']['Quirks']['RebuildAppleMemoryMap'] = True
        config['Booter']['Quirks']['EnableWriteUnprotector'] = False
        config['Booter']['Quirks']['SyncRuntimePermissions'] = True
        config['Booter']['Quirks']['DevirtualiseMmio'] = True

        # 2. Kernel/Security Settings
        # UpdateSMBIOSMode: 'Custom' is required for many T2 patches to stick
        config.get('PlatformInfo', {})['UpdateSMBIOSMode'] = 'Custom'
        
        # SecureBootModel: 'Disabled' is often necessary for macOS 26 Tahoe and macOS 15 Sequoia to work on unsupported Macs
        config.get('Misc', {}).get('Security', {})['SecureBootModel'] = 'Disabled'

        # 3. Save the file back
        with open(path, 'wb') as f:
            plist_data = plistlib.dump(config, f, sort_keys=True)
            
        print("-" * 30)
        print("PATCH COMPLETE")
        print("Status: Booter Quirks and Security levels updated.")
        print("Action Required: Reset NVRAM to apply changes.")
        print("-" * 30)

    except Exception as e:
        logging.error(f"Failed to patch config: {e}")

if __name__ == "__main__":
    config_path = '/Volumes/EFI/EFI/OC/config.plist'
    try:
        logging.info("Starting T2 Tahoe post-processing...")
        # Note: We pass config_path here
        finalize_t2_tahoe(config_path)
    except Exception as e:
        logging.error("We couldn't call finalize_t2_tahoe function due to the following error:")
        logging.exception("Stack Trace:") 
        logging.info("Aborting...")
        sys.exit(3)
