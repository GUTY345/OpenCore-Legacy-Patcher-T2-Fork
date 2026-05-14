import os
import re
class t2smbiossettings:

    # Update this path if you are running it on a USB or different mount point
    config_path = '/Volumes/EFI/EFI/OC/config.plist'
    
    def finalize_t2_tahoe(path):
        logging.info("Adding Booter Quirks patches for T2 Macs")
        if not os.path.exists(path):
            print(f"Error: {path} not found. Ensure EFI is mounted.")
            return
        
        with open(path, 'r') as f:
            content = f.read()
        
        # 2. Booter Quirks (Crucial for T2 Memory Protection)
        replacements = {
            '<key>RebuildAppleMemoryMap</key>\n\t\t\t<false/>': '<key>RebuildAppleMemoryMap</key>\n\t\t\t<true/>',
            '<key>EnableWriteUnprotector</key>\n\t\t\t<true/>': '<key>EnableWriteUnprotector</key>\n\t\t\t<false/>',
            '<key>SyncRuntimePermissions</key>\n\t\t\t<false/>': '<key>SyncRuntimePermissions</key>\n\t\t\t<true/>', # Added for Tahoe stability
            '<key>DevirtualiseMmio</key>\n\t\t\t<false/>': '<key>DevirtualiseMmio</key>\n\t\t\t<true/>'          # Added to help EXITBS:START
        }
    
        for old, new in replacements.items():
            content = content.replace(old, new)
    
        # 3. Security and SMBIOS
        content = re.sub(r'(<key>UpdateSMBIOSMode</key>\s*<string>).*?(</string>)', r'\1Custom\2', content)
        content = re.sub(r'(<key>SecureBootModel</key>\s*<string>).*?(</string>)', r'\1Disabled\2', content)
    
        with open(path, 'w') as f:
            f.write(content)
        
        print("-" * 30)
        print("DONE.")
        print("Action Required: Reset NVRAM before booting!")
        print("-" * 30)
    
    if __name__ == "__main__":
        finalize_t2_tahoe(config_path)
