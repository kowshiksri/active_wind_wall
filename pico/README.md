# Pico Firmware Build System

This directory contains firmware for the 4 Raspberry Pi Pico boards that control 36 motors (9 motors per board).

## Quick Start

**To make firmware changes:**

1. Edit **`firmware_template.c`** (the master firmware file)
2. Run the build script:
   ```bash
   cd pico
   python build_all_firmware.py
   ```
3. Flash the generated `.uf2` files to your Pico boards

That's it! The script automatically:
- Generates 4 versions of the firmware (one for each board)
- Builds all 4 versions
- Outputs clean `.uf2` files ready to flash
- Cleans up build artifacts

## File Structure

```
pico/
├── firmware_template.c        ← EDIT THIS (master firmware)
├── build_all_firmware.py      ← RUN THIS (build script)
├── firmware_pico0.uf2         ← Flash to Pico #0
├── firmware_pico1.uf2         ← Flash to Pico #1  
├── firmware_pico2.uf2         ← Flash to Pico #2
├── firmware_pico3.uf2         ← Flash to Pico #3
└── pico_sdk_import.cmake      (SDK configuration)
``` 

## Flashing Firmware to Pico Boards

For each Pico board:

1. **Enter BOOTSEL mode:**
   - Disconnect USB from Pico
   - Hold the BOOTSEL button on the Pico
   - Connect USB while holding BOOTSEL
   - Release BOOTSEL (Pico appears as USB drive)

2. **Flash firmware:**
   - Copy the corresponding `.uf2` file to the Pico drive
   - Example: Copy `firmware_pico0.uf2` to Pico #0
   - The board will automatically reboot with new firmware
