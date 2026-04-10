# Active Wind Wall — Debugging Handoff

Context dump for a fresh chat instance. The recipient has access to the same repository. Focus is on the firmware comparison at the end — the earlier sections provide background.

---

## 1. System Overview

- **Raspberry Pi 5** → **4× Raspberry Pi Pico 2 (RP2350, 150 MHz)** → **36 brushless motors** via ESCs.
- Pi sends 36 SPI bytes (one per motor, 0–255) then fires a GPIO SYNC pulse on pin 22.
- Each Pico reads its 9 bytes from the stream and latches all values atomically on SYNC, then outputs 50 Hz PWM to 9 ESCs.
- PWM mapping: byte `0` → 1000 µs (armed idle), bytes `1–255` → 1200–2000 µs (active range). There is an intentional gap from 1000→1200.
- GUI: Arm/Disarm button starts/stops a 20 Hz heartbeat sending 1000 µs. Start/Stop launches experiments through `flight_loop` at 400 Hz.

Key files:
- `pico/firmware_template.c` — Pico firmware (templated, builds 4 UF2s via `{{PICO_ID}}` substitution)
- `src/hardware/interface.py` — Pi-side SPI/GPIO driver
- `src/core/flight_loop.py` — 400 Hz control loop
- `gui_interface.py` — PyQt6 GUI with arm/disarm and experiment launch
- `config/__init__.py` — constants (PWM_MIN=1000, PWM_MIN_RUNNING=1200, PWM_MAX=2000)

---

## 2. Symptoms We Have Been Chasing

1. **Motors stop beeping when the Pico powers on**, before any software on the Pi runs. ESCs appear to arm themselves.
2. **Arm/disarm from the GUI produces no observable change** in motor behavior.
3. **At a constant commanded value (~0.3 normalized ≈ 1440 µs), motors cannot sustain rotation** — they stutter at roughly 2–4 Hz in a repeating spin-up/stall pattern.
4. **Most recently: motors activate randomly even when disarmed**, with no signal being sent from the Pi at all. This got worse after changing the watchdog to hold 1000 µs instead of 0.

The software logic has been audited and appears correct on paper. The problem manifests only with real motors connected.

---

## 3. Firmware Changes Made During This Session

### Fix 1 — Clock divider (addresses stutter symptom)

**Before:** `pwm_set_clkdiv(slices[i], 125.0f)` — correct for RP2040 but WRONG for RP2350 at 150 MHz. This made every pulse 83.3% of intended width. Commanded 1000 µs → actual 833 µs. Commanded 1440 µs → actual ~1200 µs, which is right at the ESC minimum threshold — explaining the 2–4 Hz stall/restart cycle.

**After:** `pwm_set_clkdiv(slices[i], 150.0f)` with `pwm_set_wrap(slices[i], 20000)` and the assumption that 1 tick = 1 µs.

### Fix 2 — Watchdog attempt (made things worse, then removed)

The original watchdog called `set_motor_pwm_us(i, 0)` (no pulse) after 200 ms without SYNC. We changed it to `set_motor_pwm_us(i, 1000)` with the intent of keeping ESCs armed-idle on comm loss.

**This broke the system badly.** On Pico boot there is no SYNC, so after 200 ms the watchdog starts hammering 1000 µs on every loop iteration — arming the ESCs without the Pi's permission. Any SPI noise then corrupts `motor_values[]` which gets latched on the next real SYNC, producing random motor activation.

**Decision: removed the watchdog entirely.** The Pico is now pure pass-through — receive SPI bytes, latch on SYNC, set PWM, nothing else. The Pi is the sole authority. Physical kill switch is the safety backstop. The rationale: signals are pre-computed, the GUI arm button can be a pure software gate, and we don't need the Pico to make autonomous decisions.

### Current state of `pico/firmware_template.c`
- `clkdiv = 150.0f` (hardcoded, assumes RP2350 at 150 MHz)
- `wrap = 20000` (50 Hz carrier assuming 1 tick = 1 µs)
- Boot state: `pwm_set_chan_level(..., 0)` → pin driven low, no pulse
- `set_motor_pwm_us(pulse_us)` has a special case for `pulse_us == 0` that outputs level=0
- No watchdog. Main loop is Step A (SPI read) + Step B (SYNC latch + PWM update) only.
- LED blinks via SYNC counter inside Step B (moved out of the IRQ handler)

---

## 4. Key Observation That Points Away From Firmware Logic

- **Scope test (probe on PWM pin, no ESC connected):** pulses look clean and correct.
- **With ESC + motor connected:** erratic behavior, random activation, cannot sustain rotation.
- **Old firmware (pulses 20% short):** motor barely spins → low EMI → at least semi-controllable.
- **New firmware (correct pulses):** motor spins harder → more EMI → more corruption → random activation.

This pattern suggests the problem may not be firmware logic at all, but **electrical/EMI coupling from the motor switching currents into the SPI lines, SYNC pin, or Pico power rail**. The noise source (the motor) is only present in real operation, which is why scope-only tests pass.

Things we have NOT yet checked:
- Whether SPI (GPIO 16–18) and SYNC (GPIO 22) are routed near motor power wires
- Whether the Pico shares ground path with the ESC power supply (ground loop)
- Whether there are hardware pull-downs on SYNC and CS (firmware has only weak software pull-down)
- Whether a single motor on a completely isolated power supply behaves correctly
- Comparison with a known-working ESP32 version the user built previously

---

## 5. The Important Part — Comparison With a Forked Variant

Someone forked this project for a headless (no GUI) variant and modified the firmware. They appear to understand the hardware well. We compared their `firmware_template.c` against our current one. Their variant uses 8 motors per Pico × 8 Picos = 64 motors; ours is 9 × 4 = 36. Ignoring the scaling differences, **three substantive differences matter.**

### Difference 1 — Dynamic clock calculation (CRITICAL, applies to our setup)

**Theirs:**
```c
#include "hardware/clocks.h"

#define PWM_DIVIDER 64.0f
#define PWM_FREQ_HZ 50.0f

uint16_t pwm_wrap_value = 0;
float counts_per_us = 0.0f;

int main() {
    const uint32_t sys_hz = clock_get_hz(clk_sys);
    counts_per_us = (float)sys_hz / PWM_DIVIDER / 1000000.0f;
    pwm_wrap_value = (uint16_t)((float)sys_hz / PWM_DIVIDER / PWM_FREQ_HZ) - 1;
    ...
    pwm_set_clkdiv(slices[i], PWM_DIVIDER);
    pwm_set_wrap(slices[i], pwm_wrap_value);
}

void set_motor_pwm_us(uint motor_index, uint16_t pulse_us) {
    if (pulse_us < 1000) pulse_us = 1000;
    if (pulse_us > 2000) pulse_us = 2000;
    uint16_t level = (uint16_t)(pulse_us * counts_per_us);
    if (level > pwm_wrap_value) level = pwm_wrap_value;
    pwm_set_chan_level(slices[motor_index], channels[motor_index], level);
}
```

**Ours:**
```c
pwm_set_clkdiv(slices[i], 150.0f);  // hardcoded, assumes 150 MHz
pwm_set_wrap(slices[i], 20000);     // hardcoded
// ... later ...
uint16_t level = pulse_us;          // assumes 1 tick = 1 µs
```

**Why this matters:** We have been ASSUMING the RP2350 runs at exactly 150 MHz. We have NEVER verified it. The forked version **queries the chip at runtime** with `clock_get_hz(clk_sys)` and computes the divider math from the actual clock. If the Pico 2 SDK boots the chip at a different frequency — or if `pico_sdk_init()` configures it differently based on build flags or board version — our hardcoded 150.0f produces silently wrong pulse widths. The stutter we blamed on clkdiv=125 could still be happening if the actual clock isn't 150 MHz.

**This is not headless-specific. It applies to our setup directly.** It is the single most important difference between the two firmwares.

### Difference 2 — Boot state: 1000 µs vs level=0

**Theirs:** `set_motor_pwm_us(i, 1000)` at init. ESCs receive a valid 1000 µs pulse immediately on Pico power-on. Armed idle from the moment the Pico boots.

**Ours:** `pwm_set_chan_level(..., 0)` at init. The pin is driven low with no pulse edges. ESC behavior in this state is ambiguous — some ESCs interpret a driven-low pin as "valid zero-throttle signal" and arm immediately. This likely explains Symptom 1 (motors stop beeping on Pico boot).

**Applies to our setup?** Partially. Their approach eliminates the ambiguity but means ESCs arm the moment the Pico gets power, before the Pi GUI arm button has been pressed. For a GUI-controlled setup that might or might not be desired. It is a design choice, not a clear bug fix.

### Difference 3 — No level=0 special case in `set_motor_pwm_us`

**Theirs:** `set_motor_pwm_us` clamps to 1000–2000. There is no path that outputs zero. The ESC always sees a valid signal.

**Ours:** Has an explicit `if (pulse_us == 0)` path that sets level=0 (drives the pin low). This path is used at boot.

**Applies to our setup?** Related to Difference 2. If we adopt the dynamic clock approach, we should also update `set_motor_pwm_us` to use the computed `counts_per_us` instead of assuming a 1:1 µs-to-tick ratio. Whether to keep the level=0 branch is a separate decision.

### Differences we ignored

- 8 motors × 8 Picos (64 total) vs our 9 × 4 (36): scaling, not relevant.
- Their firmware keeps the watchdog (sending 1000 µs). This is consistent with their boot-to-1000-µs design. We removed ours for a different reason (it was arming motors without the Pi's permission). These are different design philosophies and not directly comparable.
- Their SYNC IRQ handler still does the LED blink. Ours moved it to the main loop. Cosmetic.

---

## 6. The Recommended Next Step

**Adopt the dynamic clock calculation from the forked version.** Specifically:

1. Add `#include "hardware/clocks.h"`
2. Add `PWM_DIVIDER` and `PWM_FREQ_HZ` defines
3. Add `pwm_wrap_value` and `counts_per_us` globals
4. In `main()`, compute them from `clock_get_hz(clk_sys)` BEFORE the PWM init loop
5. Update `set_motor_pwm_us` to use `pulse_us * counts_per_us` instead of assuming 1 tick = 1 µs
6. Keep everything else: our 9-motor / 36-byte frame layout, no watchdog, two-phase PWM init with `pwm_set_mask_enabled`, boot state, GUI arm gate, etc.

This is the smallest possible change that eliminates the "we assumed the wrong clock frequency" class of bugs. It does not commit us to their boot-state or watchdog choices. If after adopting it the problem persists, the next investigation direction is electrical (EMI, grounding, SPI line routing) rather than firmware.

---

## 7. Open Questions for the Next Instance

1. Is the RP2350 actually running at 150 MHz on these boards? `clock_get_hz(clk_sys)` would tell us. We have never measured this.
2. Is the observed "random motor activation" caused by SPI noise injecting phantom bytes into the RX FIFO when a motor is spinning nearby?
3. Does the Pico share a ground path with the ESC power rail? If yes, ground-loop noise could be corrupting logic levels.
4. Does a single motor on an isolated bench supply (separate from the Pico's power) behave correctly with the current firmware?
5. What does the working ESP32 version do differently at the electrical level (wiring, grounding, shielding)?
