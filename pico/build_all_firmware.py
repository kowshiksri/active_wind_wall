#!/usr/bin/env python3
"""
Automated Pico Firmware Builder

Builds firmware for all Pico boards from a single template file.
All hardware constants (PWM limits, motor count, pin mapping) are pulled
from config/__init__.py at build time — no hardcoded values here.

Only edit firmware_template.c or config/__init__.py, then run this script
to regenerate all .uf2 files.

Usage:
    python build_all_firmware.py

Output:
    pico/firmware_pico0.uf2  ...  pico/firmware_pico{N-1}.uf2
"""

import os
import stat
import sys
import shutil
import subprocess
from pathlib import Path


def _rm_readonly(func, path, _exc):
    """onerror callback for shutil.rmtree — clears read-only bit then retries.
    Required on Windows where .git objects are marked read-only."""
    os.chmod(path, stat.S_IWRITE)
    func(path)


def rmtree(path):
    """shutil.rmtree that handles Windows read-only files (e.g. .git objects)."""
    shutil.rmtree(path, onerror=_rm_readonly)


# ─────────────────────────────────────────────
# MSVC environment helper (Windows only)
# ─────────────────────────────────────────────
_VCVARSALL = (
    r"C:\Program Files (x86)\Microsoft Visual Studio\18\BuildTools"
    r"\VC\Auxiliary\Build\vcvarsall.bat"
)

def _get_msvc_env():
    """
    Activate the MSVC x64 environment and return the resulting os.environ dict.

    Runs vcvarsall.bat x64, captures the output environment via 'set', and
    merges it with the current process environment so the ARM toolchain PATH
    entries are preserved.

    Returns None if vcvarsall.bat is not found (non-Windows or no VS install).
    """
    if not os.path.isfile(_VCVARSALL):
        return None
    try:
        result = subprocess.run(
            f'cmd.exe /c ""{_VCVARSALL}" x64 > nul 2>&1 && set"',
            shell=True,
            capture_output=True,
            text=True,
        )
        env = dict(os.environ)  # start with current (has ARM toolchain on PATH)
        for line in result.stdout.splitlines():
            if '=' in line:
                k, _, v = line.partition('=')
                # Merge PATH: keep our additions (ARM toolchain etc.) in front
                if k.upper() == 'PATH':
                    env['PATH'] = env.get('PATH', '') + os.pathsep + v
                else:
                    env[k] = v
        return env
    except Exception as e:
        print(f"    WARNING: Could not activate MSVC environment: {e}")
        return None


# Compute once at module load — reused for every cmake subprocess call
_BUILD_ENV = _get_msvc_env() or dict(os.environ)


# Allow imports from the project root (for config/__init__.py)
SCRIPT_DIR = Path(__file__).parent.absolute()
PROJECT_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(PROJECT_ROOT))

from config import (
    NUM_PICOS,
    NUM_MOTORS,
    MOTORS_PER_PICO,
    PWM_MIN,
    PWM_MIN_RUNNING,
    PWM_MAX,
)

# ─────────────────────────────────────────────
# Derived constants (not in config — firmware-only concepts)
# ─────────────────────────────────────────────
PWM_RANGE   = PWM_MAX - PWM_MIN_RUNNING   # Must match interface.py _range
NUM_BOARDS  = NUM_PICOS                    # Single source of truth

# Template substitution table — order matters: longer keys first to avoid
# partial replacement (e.g. {{PWM_MIN_RUNNING}} before {{PWM_MIN}}).
# {{PICO_ID}} and {{MOTOR_PINS}} are substituted per-board inside the loop.
GLOBAL_SUBSTITUTIONS = {
    '{{MOTORS_PER_PICO}}':  str(MOTORS_PER_PICO),
    '{{NUM_MOTORS}}':       str(NUM_MOTORS),
    '{{NUM_PICOS}}':        str(NUM_PICOS),
    '{{PWM_MIN_RUNNING}}':  str(PWM_MIN_RUNNING),
    '{{PWM_MIN}}':          str(PWM_MIN),
    '{{PWM_MAX}}':          str(PWM_MAX),
    '{{PWM_RANGE}}':        str(PWM_RANGE),
}

# ─────────────────────────────────────────────
# Paths
# ─────────────────────────────────────────────
PICO_DIR      = SCRIPT_DIR
TEMPLATE_FILE = PICO_DIR / "firmware_template.c"


def select_cmake_generator():
    """Select a CMake generator that exists on this machine."""
    if shutil.which("ninja"):
        return "Ninja"
    if shutil.which("make"):
        return "Unix Makefiles"
    return None


def print_header(message):
    print(f"\n{'=' * 70}")
    print(f"  {message}")
    print(f"{'=' * 70}\n")


def print_step(step_num, total_steps, message):
    print(f"[{step_num}/{total_steps}] {message}")


def motor_pins_for_pico(pico_id):
    """
    Return the C array initialiser string for MOTOR_PINS on this board.

    Pin assignment: motors are numbered 0..MOTORS_PER_PICO-1 on each Pico.
    GPIO pins follow the same 0-based offset unless FULL_PICO_MOTOR_MAP
    specifies a pin_offset (currently 0 for all boards).
    This produces e.g. '{0, 1, 2, 3, 4, 5, 6, 7, 8}' for 9 motors.
    """
    try:
        from config import FULL_PICO_MOTOR_MAP
        for _, cfg in FULL_PICO_MOTOR_MAP.items():
            if cfg['pico_id'] == pico_id:
                offset = cfg.get('pin_offset', 0)
                pins = [offset + i for i in range(len(cfg['motors']))]
                return '{' + ', '.join(str(p) for p in pins) + '}'
    except ImportError:
        pass
    # Fallback: 0-based sequential pins
    return '{' + ', '.join(str(i) for i in range(MOTORS_PER_PICO)) + '}'


def generate_firmware_source(pico_id):
    """Instantiate the template for a specific Pico, return the output Path."""
    output_file = PICO_DIR / f"firmware_pico{pico_id}.c"

    with open(TEMPLATE_FILE, 'r') as f:
        content = f.read()

    # Apply global substitutions
    for placeholder, value in GLOBAL_SUBSTITUTIONS.items():
        content = content.replace(placeholder, value)

    # Apply per-board substitutions
    content = content.replace('{{PICO_ID}}',    str(pico_id))
    content = content.replace('{{MOTOR_PINS}}', motor_pins_for_pico(pico_id))

    # Warn if any unreplaced placeholders remain
    import re
    remaining = re.findall(r'\{\{[^}]+\}\}', content)
    if remaining:
        print(f"    WARNING: unreplaced placeholders in Pico {pico_id} firmware: {remaining}")

    with open(output_file, 'w') as f:
        f.write(content)

    print(f"    Generated: {output_file.name}")
    return output_file


def generate_cmake_file(pico_id):
    """Write CMakeLists.txt for a specific Pico ID."""
    project_name = f"firmware_pico{pico_id}"
    source_file  = f"firmware_pico{pico_id}.c"

    cmake_content = f"""# Generated CMake file for Pico {pico_id}
# Auto-generated by build_all_firmware.py — do not edit by hand

cmake_minimum_required(VERSION 3.13)

set(CMAKE_C_STANDARD 11)
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_EXPORT_COMPILE_COMMANDS ON)

# Initialise pico_sdk from installed location
if(WIN32)
    set(USERHOME $ENV{{USERPROFILE}})
else()
    set(USERHOME $ENV{{HOME}})
endif()
set(sdkVersion 2.2.0)
set(toolchainVersion 14_2_Rel1)
set(picotoolVersion 2.2.0-a4)
set(picoVscode ${{USERHOME}}/.pico-sdk/cmake/pico-vscode.cmake)
if (EXISTS ${{picoVscode}})
    include(${{picoVscode}})
endif()

set(PICO_BOARD pico2 CACHE STRING "Board type")

# Pull in Raspberry Pi Pico SDK (must be before project)
include(pico_sdk_import.cmake)

project({project_name} C CXX ASM)

# Initialise the Raspberry Pi Pico SDK
pico_sdk_init()

# Add executable
add_executable({project_name} {source_file})

pico_set_program_name({project_name} "{project_name}")
pico_set_program_version({project_name} "1.0")

# Disable stdio (no USB/UART output needed in production)
pico_enable_stdio_uart({project_name} 0)
pico_enable_stdio_usb({project_name} 0)

# Link libraries
target_link_libraries({project_name}
        pico_stdlib
        hardware_spi
        hardware_pwm
        hardware_dma)

# Include directories
target_include_directories({project_name} PRIVATE
        ${{CMAKE_CURRENT_LIST_DIR}})

pico_add_extra_outputs({project_name})
"""

    output_file = PICO_DIR / "CMakeLists.txt"
    with open(output_file, 'w') as f:
        f.write(cmake_content)

    print(f"    Generated: CMakeLists.txt for Pico {pico_id}")


def build_firmware(pico_id, step_num, total_steps):
    """Build firmware for a specific Pico ID. Returns True on success."""
    project_name = f"firmware_pico{pico_id}"
    build_dir    = PICO_DIR / "build"
    uf2_source   = build_dir / f"{project_name}.uf2"
    uf2_dest     = PICO_DIR  / f"{project_name}.uf2"

    print_step(step_num, total_steps, f"Building firmware for Pico {pico_id}")
    print(f"    Constants injected from config:")
    print(f"      NUM_MOTORS={NUM_MOTORS}, NUM_PICOS={NUM_PICOS}, MOTORS_PER_PICO={MOTORS_PER_PICO}")
    print(f"      PWM_MIN={PWM_MIN}, PWM_MIN_RUNNING={PWM_MIN_RUNNING}, PWM_MAX={PWM_MAX}, PWM_RANGE={PWM_RANGE}")
    print(f"      MOTOR_PINS={motor_pins_for_pico(pico_id)}")

    # Step 1: Generate source file from template
    print(f"    Generating source code...")
    generate_firmware_source(pico_id)

    # Step 2: Generate CMakeLists.txt
    print(f"    Generating CMakeLists.txt...")
    generate_cmake_file(pico_id)

    # Step 3: Create/clean build directory
    print(f"    Setting up build directory...")
    if build_dir.exists():
        rmtree(build_dir)
    build_dir.mkdir(exist_ok=True)

    # Step 4: Run CMake configuration
    print(f"    Running CMake configuration...")
    generator = select_cmake_generator()
    if generator is None:
        print(f"    ERROR: No supported CMake build tool found (need ninja or make)")
        print("    Install either 'ninja' or 'make' and try again.")
        return False

    cmake_result = subprocess.run(
        ["cmake", "..", "-G", generator],
        cwd=build_dir,
        capture_output=True,
        text=True,
        env=_BUILD_ENV,
    )

    if cmake_result.returncode != 0:
        print(f"    ERROR: CMake failed for Pico {pico_id} (generator: {generator})")
        print(cmake_result.stderr)
        return False

    # Step 5: Compile
    print(f"    Compiling firmware...")
    make_result = subprocess.run(
        ["cmake", "--build", ".", "--parallel", "4"],
        cwd=build_dir,
        capture_output=True,
        text=True,
        env=_BUILD_ENV,
    )

    if make_result.returncode != 0:
        print(f"    ERROR: Build failed for Pico {pico_id}")
        if make_result.stdout:
            print(make_result.stdout[-4000:])   # last 4000 chars of stdout
        if make_result.stderr:
            print(make_result.stderr[-4000:])   # last 4000 chars of stderr
        return False

    # Step 6: Copy .uf2 to pico/ directory
    if not uf2_source.exists():
        print(f"    ERROR: UF2 file not found after build: {uf2_source}")
        return False

    shutil.copy2(uf2_source, uf2_dest)
    print(f"    Success! Created: {uf2_dest.name}")

    # Step 7: Clean up build artefacts
    print(f"    Cleaning up...")
    rmtree(build_dir)
    source_file = PICO_DIR / f"firmware_pico{pico_id}.c"
    if source_file.exists():
        source_file.unlink()

    return True


def main():
    print_header(f"Pico Firmware Builder — Building {NUM_BOARDS} boards")

    if not TEMPLATE_FILE.exists():
        print(f"ERROR: Template not found: {TEMPLATE_FILE}")
        sys.exit(1)

    print(f"Template:   {TEMPLATE_FILE.name}")
    print(f"Output dir: {PICO_DIR}")
    print(f"Boards:     {NUM_BOARDS}  (from config.NUM_PICOS)")
    print(f"Motors:     {NUM_MOTORS} total, {MOTORS_PER_PICO} per Pico")
    print(f"PWM range:  {PWM_MIN}–{PWM_MAX} µs  (running from {PWM_MIN_RUNNING} µs)")

    success_count = 0
    failed_boards = []

    for pico_id in range(NUM_BOARDS):
        ok = build_firmware(pico_id, pico_id + 1, NUM_BOARDS)
        if ok:
            success_count += 1
        else:
            failed_boards.append(pico_id)

    # Clean up auto-generated CMakeLists.txt if it still exists
    cmake_file = PICO_DIR / "CMakeLists.txt"
    if cmake_file.exists():
        cmake_file.unlink()

    print_header("Build Summary")
    print(f"Successfully built: {success_count}/{NUM_BOARDS} boards")

    if failed_boards:
        print(f"Failed:            Pico {', '.join(map(str, failed_boards))}")
        sys.exit(1)

    print(f"\nAll firmware files are ready in: {PICO_DIR}")
    for pico_id in range(NUM_BOARDS):
        uf2_file = PICO_DIR / f"firmware_pico{pico_id}.uf2"
        if uf2_file.exists():
            size_kb = uf2_file.stat().st_size / 1024
            print(f"  firmware_pico{pico_id}.uf2  ({size_kb:.1f} KB)")

    print(f"\n{'=' * 70}")
    print(f"  Next steps:")
    print(f"  1. Connect each Pico while holding BOOTSEL")
    print(f"  2. Copy the matching .uf2 file to the Pico drive")
    print(f"  3. Pico reboots automatically with new firmware")
    print(f"{'=' * 70}\n")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nBuild cancelled by user")
        sys.exit(1)
    except Exception as e:
        print(f"\nUnexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
