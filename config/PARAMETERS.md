# Configuration Parameters — Active Wind Wall

This document explains **why** every parameter in `config/__init__.py` has the
value it does. Read this before changing anything — several values are tightly
coupled to firmware constants and to each other.

---

## Hardware Topology

| Parameter | Value | Notes |
|---|---|---|
| `NUM_MOTORS` | 36 | 6×6 physical fan grid |
| `NUM_PICOS` | 4 | One Pico per 3×3 quadrant |
| `MOTORS_PER_PICO` | `NUM_MOTORS // NUM_PICOS` = 9 | Derived — never set manually |

If you change the grid size, update `NUM_MOTORS` and `NUM_PICOS` only.
`MOTORS_PER_PICO` and `SHARED_MEM_SIZE` follow automatically.

---

## Loop Rate Derivation

`UPDATE_RATE_HZ = 125` is not arbitrary. It is derived from the actual SPI
frame delivery time measured on the Pi 5.

### Step 1 — SPI clock speed

The Pi is the SPI **master**. The Pico is the SPI **slave**.  
In slave mode, `spi_init(SPI_INST, 1000000)` in the Pico firmware is **ignored**
— the Pico accepts whatever clock the Pi drives.  
The Pi drives SPI at `SPI_SPEED_HZ = 1 MHz`, set in `interface.py`.

```
1 MHz SPI clock → 1 bit = 1 µs → 1 byte = 8 µs (pure hardware time)
```

### Step 2 — Python per-byte overhead

The current SPI write in `interface.py` sends **one byte at a time**:

```python
for b in data:
    spi.xfer2([int(b) & 0xFF])   # separate syscall per byte
```

Each `xfer2()` call crosses the Python → C extension → `ioctl()` → kernel
boundary. On Pi 5 under normal load this costs **~80–150 µs per call**.

Conservative (worst-case) overhead used for calculations: **150 µs/byte**

```
Per byte total = 8 µs (SPI) + 150 µs (Python/kernel) = 158 µs
```

### Step 3 — Full 36-byte frame delivery time

```
36 bytes × 158 µs/byte = 5,688 µs ≈ 5.7 ms
```

### Step 4 — Inter-frame buffer

After the last byte arrives, the Pi sends a SYNC pulse (~10 µs). The Pico
then latches values and updates PWM. A 200 µs gap is added before the next
frame begins to absorb timing jitter.

```
5,688 µs + 200 µs buffer = 5,888 µs  →  max safe rate ≈ 170 Hz
```

### Step 5 — Safety margin

Running at the theoretical maximum leaves zero margin for OS scheduling
jitter, SPI overhead spikes, or load variation. A 15% margin is applied:

```
5,888 µs × 1.15 = 6,771 µs  →  147 Hz  →  rounded to 125 Hz (8 ms loop)
```

### Step 6 — Sanity check against ESC update rate

ESCs update their own PWM output at **50 Hz** (once per 20 ms).
Sending frames at 125 Hz means the Pico receives **2.5 new commands per ESC
PWM cycle** — more than sufficient resolution.

```
UPDATE_RATE_HZ = 125   (8 ms loop period)
LOOP_TIME_MS   = 8.0   (derived — do not edit)
```

### When can UPDATE_RATE_HZ be raised?

Only if the SPI write is changed to a **single** `xfer2()` call:

```python
# Single call — CS held low for all 36 bytes — 288 µs total at 1 MHz
spi.xfer2([int(b) & 0xFF for b in data])
```

With that change, the frame delivery drops to 288 µs and 400 Hz becomes safe.
Until that change is made, **do not raise UPDATE_RATE_HZ above 150**.

---

## SPI Clock Choice

`SPI_SPEED_HZ = 1_000_000` (1 MHz)

### Why 1 MHz and not faster?

The Pico 2 (RP2350) SPI slave hardware maximum is approximately:
```
sys_clk / 12 = 150 MHz / 12 = 12.5 MHz
```
So the Pico can technically handle up to 12.5 MHz. However:

- Longer cables between Pi and Pico introduce capacitance and signal degradation
- At higher frequencies, crosstalk between SPI lines and the SYNC line
  increases the risk of spurious SYNC triggers
- The per-byte Python overhead (~150 µs) dominates total frame time anyway,
  so raising SPI clock has almost no effect on throughput with the current
  byte-at-a-time approach

1 MHz provides a good noise margin and is well within the Pico's limits.

### Changing SPI speed

If you change `SPI_SPEED_HZ`, recalculate the loop rate:

```
pure_spi_us  = 8_000_000 / SPI_SPEED_HZ      # 8 bits per byte
per_byte_us  = pure_spi_us + 150              # add Python overhead
frame_us     = 36 * per_byte_us + 200         # 36 bytes + buffer
max_rate_hz  = 1_000_000 / frame_us
safe_rate_hz = max_rate_hz / 1.15             # 15% safety margin
```

---

## PWM Signal Range

| Parameter | Value | Meaning |
|---|---|---|
| `PWM_MIN` | 1000 µs | Armed/idle — ESC holds but motor does not spin |
| `PWM_MIN_RUNNING` | 1200 µs | Minimum pulse to actually spin the motor |
| `PWM_MAX` | 2000 µs | Full throttle |
| `PWM_CENTER` | 1500 µs | Midpoint — derived, not tunable |

### Coupling with Pico firmware

`PWM_MIN_RUNNING` and `PWM_MAX` are mirrored in `pico/firmware_template.c`:

```c
// firmware_template.c — must match config/__init__.py
target_pwm = 1200 + ((uint32_t)raw_val * 800) / 255;
//           ^^^^                        ^^^
//     PWM_MIN_RUNNING          PWM_MAX - PWM_MIN_RUNNING
```

And in `src/hardware/interface.py`:

```python
byte_val = 1 + int((clipped - PWM_MIN_RUNNING) * 254 / _range)
```

**If you change `PWM_MIN_RUNNING` or `PWM_MAX` here, you must update both
`firmware_template.c` and `interface.py` to match, then rebuild and reflash
all 4 Pico UF2 files.**

### PWM_MIN_RUNNING is provisional

The 1200 µs value is a starting point. Different motor/ESC combinations have
different minimum spin thresholds. Characterise each motor type and update
this value accordingly. Future versions should make this a per-motor array.

---

## Safety Constraints

### Slew Rate Limit

```
MAX_PWM_SLEW_LIMIT = 25.0  µs/ms
```

This limits how fast any motor's PWM can change, expressed as µs per
millisecond of real time — independent of loop rate.

- Full PWM range = 800 µs (1200 → 2000)
- At 25 µs/ms: time to traverse full range = 800 / 25 = **32 ms**
- Per frame at 125 Hz (8 ms): max delta = 25 × 8 = **200 µs/frame**

Increase this if motors feel sluggish during experiments.
Decrease this if you see mechanical shock at experiment start.

---

## SYNC Pin

```
SYNC_PIN = 22   (GPIO BCM numbering on Pi)
```

The Pi pulses this pin HIGH for `SYNC_PULSE_WIDTH_US` (10 µs) after sending
each SPI frame. All Picos receive the rising edge simultaneously via a shared
wire and latch the SPI data into their PWM hardware.

**This value was previously wrong (set to 17) in earlier versions of this
file. The firmware and interface.py both use GPIO 22. This is now corrected.**

---

## Pico Motor Mapping

`FULL_PICO_MOTOR_MAP` defines which logical motor IDs map to which Pico board
and which pin on that board.

### How to rewire

1. Edit the `motors` list for each quadrant to reflect new motor assignments
2. The `pin_offset` field shifts pin numbering if your Pico uses non-zero
   starting pins (leave at 0 for standard wiring)
3. `MOTOR_TO_PICO_LOOKUP` is rebuilt automatically from the map at import time
4. Also update `PHYSICAL_MOTOR_ORDER` in `src/hardware/interface.py` to match

### Single motor test mode

```python
SINGLE_MOTOR_TEST = True
```

Routes all traffic to Motor 0 on Pico 0 only. Use this to verify a single
ESC/motor before running the full array.

---

## Quick Reference — What to Change for Common Tasks

| Task | Change |
|---|---|
| Different grid size (e.g. 8×8) | `NUM_MOTORS`, `NUM_PICOS`, `FULL_PICO_MOTOR_MAP`, rebuild firmware |
| Slower/safer loop rate | Lower `UPDATE_RATE_HZ` (recalculate from §Loop Rate Derivation) |
| Different SPI speed | `SPI_SPEED_HZ`, recalculate `UPDATE_RATE_HZ` |
| Different ESC PWM range | `PWM_MIN_RUNNING`, `PWM_MAX` — **also update firmware + interface.py** |
| More responsive motors | Raise `MAX_PWM_SLEW_LIMIT` |
| Smoother motor ramp | Lower `MAX_PWM_SLEW_LIMIT` |
| Test one motor | `SINGLE_MOTOR_TEST = True` |
| More Fourier harmonics | `FOURIER_TERMS` (higher = smoother waves, higher CPU cost) |
