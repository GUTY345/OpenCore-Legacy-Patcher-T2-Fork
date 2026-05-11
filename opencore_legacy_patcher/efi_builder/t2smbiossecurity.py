import os
import re

# Update this path if you are running it on a USB or different mount point
config_path = '/Volumes/EFI/EFI/OC/config.plist'

def finalize_t2_tahoe(path):
    if not os.path.exists(path):
        print(f"Error: {path} not found. Ensure EFI is mounted.")
        return
    
    with open(path, 'r') as f:
        content = f.read()

    # 1. Clean and Inject Boot-Args
    # We define the flags we want. 
    target_flags = ["-v", "rddelay=5", "amfi=0x80", "igfxfw=2", "igfxonln=1", "-disable_ext_panics", "-no_compat_check"]
    
    # Extract current args to prevent duplicates
    match = re.search(r'<key>boot-args</key>\s*<string>(.*?)</string>', content)
    if match:
        current_args = match.group(1).split()
        for flag in target_flags:
            if flag not in current_args:
                current_args.append(flag)
        new_args_str = " ".join(current_args)
        content = re.sub(r'(<key>boot-args</key>\s*<string>).*?(</string>)', 
                         fr'\1{new_args_str}\2', content)

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
    print("DONE: Macmini8,1 Tahoe Polish Applied.")
    print("Action Required: Reset NVRAM before booting!")
    print("-" * 30)

if __name__ == "__main__":
    finalize_t2_tahoe(config_path)
