#!/usr/bin/env python3
"""
Automated Pico Firmware Builder

Builds firmware for all 4 Pico boards from a single template file.
Only edit firmware_template.c, then run this script to generate all .uf2 files.

Works on Windows, macOS, and Linux. Tools are discovered automatically in this order:
  1. System PATH  (e.g. installed via apt, brew, or manual install)
  2. ~/.pico-sdk/ (installed by the VS Code Raspberry Pi Pico extension)

Usage:
    python build_all_firmware.py

Output:
    pico/firmware_pico0.uf2
    pico/firmware_pico1.uf2
    pico/firmware_pico2.uf2
    pico/firmware_pico3.uf2
"""

import os
import sys
import shutil
import subprocess
from pathlib import Path


# ==========================================
# CONFIGURATION
# ==========================================

SCRIPT_DIR    = Path(__file__).parent.absolute()
PICO_DIR      = SCRIPT_DIR
TEMPLATE_FILE = PICO_DIR / "firmware_template.c"
NUM_BOARDS    = 4

IS_WINDOWS = sys.platform == "win32"
EXE        = ".exe" if IS_WINDOWS else ""


# ==========================================
# CROSS-PLATFORM TOOL DISCOVERY
# ==========================================

def _find_in_pico_sdk(subdir: str, binary: str) -> Path | None:
    """
    Search ~/.pico-sdk/<subdir>/ for a binary.
    The extension installs versioned subdirectories, e.g.:
        ~/.pico-sdk/cmake/v3.31.5/bin/cmake(.exe)
        ~/.pico-sdk/ninja/v1.12.1/ninja(.exe)
        ~/.pico-sdk/toolchain/14_2_Rel1/bin/arm-none-eabi-gcc(.exe)
    Picks the highest version if multiple are present.
    """
    sdk_root = Path.home() / ".pico-sdk" / subdir
    if not sdk_root.exists():
        return None

    # Sort versions descending so the newest is tried first
    version_dirs = sorted(
        [d for d in sdk_root.iterdir() if d.is_dir()],
        reverse=True,
    )
    for ver_dir in version_dirs:
        candidates = [
            ver_dir / "bin" / binary,   # cmake layout
            ver_dir / binary,           # ninja layout
        ]
        for candidate in candidates:
            if candidate.exists():
                return candidate
    return None


def find_tool(name: str, pico_sdk_subdir: str) -> str:
    """
    Return the path to a build tool binary.
    Checks system PATH first, then ~/.pico-sdk/.
    Exits with a clear error message if the tool cannot be found.
    """
    binary = name + EXE

    # 1. System PATH
    if shutil.which(name):
        return name   # Let the shell resolve it

    # 2. VS Code Pico SDK extension install
    sdk_path = _find_in_pico_sdk(pico_sdk_subdir, binary)
    if sdk_path:
        return str(sdk_path)

    # Not found
    print(f"\n  ERROR: '{name}' not found on this system.")
    print(f"  Install options:")
    if sys.platform == "darwin":
        print(f"    brew install {name}")
    elif sys.platform.startswith("linux"):
        pkg = {"cmake": "cmake", "ninja": "ninja-build"}.get(name, name)
        print(f"    sudo apt install {pkg}")
    print(f"  Or install the VS Code Raspberry Pi Pico extension — it bundles all tools.")
    sys.exit(1)


def _pico_sdk_bin_dir(subdir: str, binary: str) -> Path | None:
    """Return the parent directory of a tool found in ~/.pico-sdk/."""
    sdk_root = Path.home() / ".pico-sdk" / subdir
    if not sdk_root.exists():
        return None
    for ver_dir in sorted([d for d in sdk_root.iterdir() if d.is_dir()], reverse=True):
        for candidate in [ver_dir / "bin" / binary, ver_dir / binary]:
            if candidate.exists():
                return candidate.parent
    return None


def build_environment() -> dict:
    """
    Return an env dict with all tool bin directories prepended to PATH.
    This ensures arm-none-eabi-gcc (and ninja) are visible to cmake even
    when they were found via ~/.pico-sdk/ rather than the system PATH.
    """
    extra_dirs = []
    for subdir, binary in [
        ("cmake",     "cmake"    + EXE),
        ("ninja",     "ninja"    + EXE),
        ("toolchain", "arm-none-eabi-gcc" + EXE),
    ]:
        d = _pico_sdk_bin_dir(subdir, binary)
        if d:
            extra_dirs.append(str(d))

    new_path = os.pathsep.join(extra_dirs + [os.environ.get("PATH", "")])
    return {**os.environ, "PATH": new_path}


# Resolve tools and environment once at startup
CMAKE_EXE = find_tool("cmake", "cmake")
NINJA_EXE = find_tool("ninja", "ninja")
BUILD_ENV  = build_environment()


# ==========================================
# HELPERS
# ==========================================

def print_header(message: str) -> None:
    print(f"\n{'=' * 70}")
    print(f"  {message}")
    print(f"{'=' * 70}\n")


def print_step(step_num: int, total_steps: int, message: str) -> None:
    print(f"[{step_num}/{total_steps}] {message}")


# ==========================================
# FIRMWARE GENERATION
# ==========================================

def generate_firmware_source(pico_id: int) -> Path:
    """Expand firmware_template.c for a specific Pico ID."""
    output_file = PICO_DIR / f"firmware_pico{pico_id}.c"
    with open(TEMPLATE_FILE, "r") as f:
        content = f.read().replace("{{PICO_ID}}", str(pico_id))
    with open(output_file, "w") as f:
        f.write(content)
    print(f"    ✓ Generated: {output_file.name}")
    return output_file


def generate_cmake_file(pico_id: int) -> None:
    """Generate CMakeLists.txt for a specific Pico ID."""
    project_name = f"firmware_pico{pico_id}"
    source_file  = f"firmware_pico{pico_id}.c"

    cmake_content = f"""# Generated CMake file for Pico {pico_id}
# Auto-generated by build_all_firmware.py — do not edit manually.

cmake_minimum_required(VERSION 3.13)

set(CMAKE_C_STANDARD 11)
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_EXPORT_COMPILE_COMMANDS ON)

# Locate the VS Code Pico SDK extension cmake helper (works on Win/Mac/Linux)
if(WIN32)
    set(USERHOME $ENV{{USERPROFILE}})
else()
    set(USERHOME $ENV{{HOME}})
endif()
set(sdkVersion 2.2.0)
set(toolchainVersion 14_2_Rel1)
set(picotoolVersion 2.2.0-a4)
set(picoVscode ${{USERHOME}}/.pico-sdk/cmake/pico-vscode.cmake)
if(EXISTS ${{picoVscode}})
    include(${{picoVscode}})
endif()

set(PICO_BOARD pico2 CACHE STRING "Board type")

include(pico_sdk_import.cmake)

project({project_name} C CXX ASM)

pico_sdk_init()

add_executable({project_name} {source_file})

pico_set_program_name({project_name} "{project_name}")
pico_set_program_version({project_name} "1.0")

# No USB/UART stdio needed — motors are controlled via SPI
pico_enable_stdio_uart({project_name} 0)
pico_enable_stdio_usb({project_name} 0)

target_link_libraries({project_name}
        pico_stdlib
        hardware_spi
        hardware_pwm
        hardware_dma)

target_include_directories({project_name} PRIVATE
        ${{CMAKE_CURRENT_LIST_DIR}})

pico_add_extra_outputs({project_name})
"""
    output_file = PICO_DIR / "CMakeLists.txt"
    with open(output_file, "w") as f:
        f.write(cmake_content)
    print(f"    ✓ Generated: CMakeLists.txt for Pico {pico_id}")


# ==========================================
# BUILD
# ==========================================

def build_firmware(pico_id: int, step_num: int, total_steps: int) -> bool:
    """Build firmware for one Pico board and produce a .uf2 file."""
    project_name = f"firmware_pico{pico_id}"
    build_dir    = PICO_DIR / "build"
    uf2_source   = build_dir / f"{project_name}.uf2"
    uf2_dest     = PICO_DIR  / f"{project_name}.uf2"

    print_step(step_num, total_steps, f"Building firmware for Pico {pico_id}")

    # 1. Source + CMakeLists
    print("    Generating source code...")
    generate_firmware_source(pico_id)
    print("    Generating CMakeLists.txt...")
    generate_cmake_file(pico_id)

    # 2. Build directory
    print("    Setting up build directory...")
    if build_dir.exists():
        shutil.rmtree(build_dir)
    build_dir.mkdir(exist_ok=True)

    # 3. CMake configure
    print("    Running CMake configuration...")
    cmake_result = subprocess.run(
        [CMAKE_EXE, "-G", "Ninja", ".."],
        cwd=build_dir,
        capture_output=True,
        text=True,
        env=BUILD_ENV,
    )
    if cmake_result.returncode != 0:
        print(f"    ✗ CMake failed for Pico {pico_id}")
        print(cmake_result.stdout[-2000:])
        print(cmake_result.stderr[-2000:])
        return False

    # 4. Ninja build
    print("    Compiling firmware (this may take a minute)...")
    ninja_result = subprocess.run(
        [NINJA_EXE],
        cwd=build_dir,
        capture_output=True,
        text=True,
        env=BUILD_ENV,
    )
    if ninja_result.returncode != 0:
        print(f"    ✗ Build failed for Pico {pico_id}")
        print(ninja_result.stdout[-3000:])
        print(ninja_result.stderr[-1000:])
        return False

    # 5. Copy .uf2
    if not uf2_source.exists():
        print(f"    ✗ UF2 file not found: {uf2_source}")
        return False
    shutil.copy2(uf2_source, uf2_dest)
    print(f"    ✓ Success! Created: {uf2_dest.name}")

    # 6. Clean up
    print("    Cleaning up build artefacts...")
    shutil.rmtree(build_dir)
    source_file = PICO_DIR / f"firmware_pico{pico_id}.c"
    if source_file.exists():
        source_file.unlink()

    return True


# ==========================================
# MAIN
# ==========================================

def main() -> None:
    print_header("Pico Firmware Builder — Building All Boards")

    platform_name = {"win32": "Windows", "darwin": "macOS"}.get(sys.platform, "Linux")
    print(f"Platform : {platform_name}")
    print(f"cmake    : {CMAKE_EXE}")
    print(f"ninja    : {NINJA_EXE}")
    print(f"Template : {TEMPLATE_FILE.name}")
    print(f"Output   : {PICO_DIR}")
    print(f"\nBuilding firmware for {NUM_BOARDS} Pico boards...\n")

    if not TEMPLATE_FILE.exists():
        print(f"✗ Error: {TEMPLATE_FILE} not found.")
        sys.exit(1)

    success_count = 0
    failed_boards = []

    for pico_id in range(NUM_BOARDS):
        ok = build_firmware(pico_id, pico_id + 1, NUM_BOARDS)
        if ok:
            success_count += 1
        else:
            failed_boards.append(pico_id)

    # Clean up auto-generated CMakeLists.txt
    cmake_file = PICO_DIR / "CMakeLists.txt"
    if cmake_file.exists():
        cmake_file.unlink()

    print_header("Build Summary")
    print(f"Successfully built: {success_count}/{NUM_BOARDS} boards")

    if failed_boards:
        print(f"Failed: Pico {', '.join(map(str, failed_boards))}")
        sys.exit(1)

    print(f"\nAll firmware files are ready in: {PICO_DIR}\n")
    for pico_id in range(NUM_BOARDS):
        uf2_file = PICO_DIR / f"firmware_pico{pico_id}.uf2"
        if uf2_file.exists():
            print(f"  firmware_pico{pico_id}.uf2  ({uf2_file.stat().st_size / 1024:.1f} KB)")

    print(f"\n{'=' * 70}")
    print(f"  Flash instructions:")
    print(f"  1. Hold BOOTSEL on the Pico, plug in USB, release BOOTSEL")
    print(f"  2. Pico appears as a USB drive (RPI-RP2 or RP2350)")
    print(f"  3. Copy the matching .uf2 file — Pico reboots automatically")
    print(f"{'=' * 70}\n")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nBuild cancelled by user")
        sys.exit(1)
    except Exception as e:
        print(f"\nUnexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
