# Wiring Guide: Raspberry Pi to Pico Controllers

## Overview
This system uses **1 Raspberry Pi 5** to control **4 Raspberry Pi Picos**, with each Pico controlling 9 motors (36 motors total).

---

## Raspberry Pi 5 GPIO Pinout Reference

```
       3.3V  1 ●  ● 2   5V
  GPIO  2  3 ●  ● 4   5V
  GPIO  3  5 ●  ● 6   GND
  GPIO  4  7 ●  ● 8   GPIO 14 (UART TX)
        GND  9 ●  ● 10  GPIO 15 (UART RX)
  GPIO 17 11 ●  ● 12  GPIO 18
  GPIO 27 13 ●  ● 14  GND
  GPIO 22 15 ●  ● 16  GPIO 23
       3.3V 17 ●  ● 18  GPIO 24
  GPIO 10 19 ●  ● 20  GND          <-- MOSI (SPI0)
  GPIO  9 21 ●  ● 22  GPIO 25
  GPIO 11 23 ●  ● 24  GPIO  8      <-- SCLK & CE0 (SPI0)
        GND 25 ●  ● 26  GPIO  7      <-- CE1 (SPI0)
```

---

## SPI Protocol Details

### Packet Format (sent to each Pico):
```
[0xAA] [PWM0_H] [PWM0_L] [PWM1_H] [PWM1_L] ... [PWM8_H] [PWM8_L] [0x55]
```

- **Start Byte**: `0xAA` (sync marker)
- **PWM Data**: 9 motors × 2 bytes each (16-bit big-endian, range 1000-2000)
- **End Byte**: `0x55` (packet terminator)
- **Total packet size**: 21 bytes (1 + 18 + 1)

### Example for Motor PWM = 1500:
```
High byte: 0x05 (1500 >> 8 = 5)
Low byte:  0xDC (1500 & 0xFF = 220)
```

---

## Wiring: Raspberry Pi → Picos

### **Pico 0 (Top-Left Quadrant) - Motors 0-8**

| Raspberry Pi | Pin# | Wire Color | Pico 0 Pin | Purpose |
|--------------|------|------------|------------|---------|
| **GPIO 10** (MOSI) | 19 | 🟦 Blue | GP16 (SPI0 RX) | SPI Data |
| **GPIO 11** (SCLK) | 23 | 🟨 Yellow | GP18 (SPI0 SCK) | SPI Clock |
| **GPIO 8** (CE0) | 24 | 🟩 Green | GP17 (SPI0 CSn) | Chip Select |
| **GPIO 17** | 11 | 🟧 Orange | GP15 | Sync Signal |
| **GND** | 9 or 25 | ⬛ Black | GND | Ground |
| **5V** | 2 or 4 | 🔴 Red | VSYS | Power (optional) |

**Pico 0 Motor Outputs:**
- GP0 → Motor 0 (ESC signal wire)
- GP1 → Motor 1
- GP2 → Motor 2
- GP3 → Motor 3
- GP4 → Motor 4
- GP5 → Motor 5
- GP6 → Motor 6
- GP7 → Motor 7
- GP8 → Motor 8

---

### **Pico 1 (Top-Right Quadrant) - Motors 9-17**

| Raspberry Pi | Pin# | Wire Color | Pico 1 Pin | Purpose |
|--------------|------|------------|------------|---------|
| **GPIO 10** (MOSI) | 19 | 🟦 Blue | GP16 (SPI0 RX) | SPI Data |
| **GPIO 11** (SCLK) | 23 | 🟨 Yellow | GP18 (SPI0 SCK) | SPI Clock |
| **GPIO 7** (CE1) | 26 | 🟪 Purple | GP17 (SPI0 CSn) | Chip Select |
| **GPIO 17** | 11 | 🟧 Orange | GP15 | Sync Signal |
| **GND** | 9 or 25 | ⬛ Black | GND | Ground |
| **5V** | 2 or 4 | 🔴 Red | VSYS | Power (optional) |

**Pico 1 Motor Outputs:**
- GP0 → Motor 9
- GP1 → Motor 10
- ...
- GP8 → Motor 17

---

### **Pico 2 & 3 - IMPORTANT NOTE**

⚠️ **WARNING**: The Raspberry Pi only has 2 hardware chip select pins (CE0 and CE1).

**For Pico 2 and 3, you have two options:**

#### **Option A: Use I2C or UART Instead**
Switch Pico 2 and 3 to use I2C or UART communication instead of SPI.

#### **Option B: Manual GPIO Chip Select (Advanced)**
Use regular GPIO pins as manual chip selects. This requires:
1. Modifying the Python code to manually toggle GPIO pins
2. Updating Pico firmware to use GPIO instead of hardware CSn

**Current code supports only Pico 0 and 1 via SPI.**

---

## Power Distribution

### **Motor Power (High Current)**
- ESCs require **high current** (depends on motor size)
- **DO NOT** power ESCs from Pi or Pico GPIO
- Use external battery/power supply → ESC power terminals
- ESC ground → Common ground with Pi/Pico

### **Logic Power**
- Pico can be powered from Pi's 5V (low current)
- OR use separate 5V regulator from main battery

---

## Signal Flow Diagram

```
Raspberry Pi 5 (400 Hz loop)
    │
    ├─── SPI0 (MOSI, SCLK) ────────────┬──────────┬──────────┬──────────┐
    │                                   │          │          │          │
    ├─── CE0 (GPIO 8) ──────────────> Pico 0    Pico 1    Pico 2    Pico 3
    ├─── CE1 (GPIO 7) ──────────────>   │          │          │          │
    │                                   │          │          │          │
    └─── SYNC (GPIO 17) ────────────────┴──────────┴──────────┴──────────┘
                                        │          │          │          │
                                        ▼          ▼          ▼          ▼
                                    Motors 0-8  Motors 9-17  ...       ...
```

---

## Testing Steps

### 1. **Test Single Pico (Pico 0 Only)**
```bash
# On Raspberry Pi
cd ~/active_wind_wall
python3 gui_interface_enhanced.py
```
- Assign motors 0-8 to a group
- Start with low amplitude sine wave
- Verify motors respond

### 2. **Check SPI Communication**
```bash
# On Raspberry Pi - verify SPI is enabled
ls /dev/spidev*
# Should show: /dev/spidev0.0 and /dev/spidev0.1
```

### 3. **Oscilloscope Verification (if available)**
- Probe MOSI line: should see data bursts at 400 Hz
- Probe SCLK: should see 1 MHz clock during transfers
- Probe CE0/CE1: should pulse low during each transfer
- Probe SYNC: should toggle after all SPI transfers

---

## Troubleshooting

| Problem | Check |
|---------|-------|
| No motors respond | - SPI enabled? `sudo raspi-config` → Interface Options → SPI<br>- Wiring correct?<br>- Pico firmware running? |
| Some motors jitter | - Common ground connected?<br>- PWM signal quality<br>- ESC calibration |
| Delayed response | - Check `UPDATE_RATE_HZ` in config<br>- CPU load on Pi |
| Only Pico 0 works | - CE1 wiring for Pico 1?<br>- Pico 1 firmware loaded? |

---

## Next Steps

1. ✅ Wire Pico 0 (Top-Left quadrant)
2. ✅ Test with `gui_interface_enhanced.py`
3. ✅ Wire Pico 1 (Top-Right quadrant)
4. ⚠️ Decide on communication method for Pico 2 & 3
5. 🔧 Update code if using I2C/UART for additional Picos

---

**Need help? Check the code comments in:**
- [src/hardware/interface.py](src/hardware/interface.py) - SPI communication
- [config/__init__.py](config/__init__.py) - Motor mapping
