DefinitionBlock ("", "SSDT", 2, "GUTY", "T2FAKE", 0x00000000)
{
    /*
     * 1. External References
     * These paths are based on standard MacBook Pro 15,1 (2018) ACPI tables.
     * Ensure these match your specific hardware's DSDT paths.
     */
    External (_SB.PCI0.LPCB.EC.TBAR, DeviceObj) // Touch Bar Controller
    External (_SB.ALS0, DeviceObj)              // Ambient Light Sensor (Path 1)
    External (_SB.PCI0.LPCB.ALS0, DeviceObj)    // Ambient Light Sensor (Path 2)
    External (_SB.PCI0.I2C0.ISP0, DeviceObj)    // Image Signal Processor (FaceTime Camera)

    /*
     * 2. Device Disabling Logic (Method _STA)
     * We return 0x00 to inform macOS that the device is not present.
     * This prevents the Kernel from waiting for a response from these 
     * peripherals, thus avoiding T2 Bridge communication timeouts.
     */

    // Disable Touch Bar to reduce bridgeOS I/O overhead during boot
    Scope (_SB.PCI0.LPCB.EC.TBAR)
    {
        Method (_STA, 0, NotSerialized)
        {
            If (_OSI ("Darwin")) // Target macOS only
            {
                Return (0x00) // 0x00 = Disabled / Not Present
            }
            Else
            {
                Return (0x0F) // 0x0F = Enabled (Normal operation for Windows/Linux)
            }
        }
    }

    // Disable Ambient Light Sensor to prevent I2C bus hangs during boot transition
    Scope (_SB.ALS0)
    {
        Method (_STA, 0, NotSerialized)
        {
            If (_OSI ("Darwin"))
            {
                Return (0x00)
            }
            Else
            {
                Return (0x0F)
            }
        }
    }

    // Disable Camera/ISP to mitigate T2 'bridge unresponsive' panics
    Scope (_SB.PCI0.I2C0.ISP0)
    {
        Method (_STA, 0, NotSerialized)
        {
            If (_OSI ("Darwin"))
            {
                Return (0x00)
            }
            Else
            {
                Return (0x0F)
            }
        }
    }
}