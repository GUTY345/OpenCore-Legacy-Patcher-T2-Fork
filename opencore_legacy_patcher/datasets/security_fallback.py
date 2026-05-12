"""
security_fallback.py: External fallback values for T2 Mac security overrides.

This file contains security configuration settings that are used only for T2 Macs.
Keeping these values in a separate module avoids hard-coded SIP policy values inside
`security.py` and makes T2 fallback behavior easier to extend.
"""

DEFAULT_T2_SECURITY_SETTINGS = {
    "csr-active-config": "03080000",
    "boot-args": [
        "ipc_control_port_options=0",
        "-v",
        "amfi=0x80",
        "amfi_get_out_of_my_way=1",
    ],
    "Misc.Security.SecureBootModel": "Disabled",
    "Misc.Security.ApECID": 0,
    "Misc.Security.DmgLoading": "Any",
}

MODEL_SPECIFIC_T2_SECURITY_SETTINGS = {
    # Add per-model overrides here when needed.
    # Example:
    # "MacBookPro15,4": {
    #     "boot-args": ["ipc_control_port_options=0", "-v", "amfi=0x80"],
    # },
}


def get_security_fallback(model: str) -> dict:
    """Return fallback security settings for a given model."""
    settings = DEFAULT_T2_SECURITY_SETTINGS.copy()
    settings.update(MODEL_SPECIFIC_T2_SECURITY_SETTINGS.get(model, {}))
    return settings
