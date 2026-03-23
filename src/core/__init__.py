"""
Shared memory management for inter-process communication.
Provides safe access to motor control state and telemetry data.
"""

import numpy as np
from multiprocessing import shared_memory
from typing import Tuple, Optional
from config import NUM_MOTORS, SHARED_MEM_NAME


class MotorStateBuffer:
    """
    Manages a shared memory buffer for motor PWM commands.

    Layout:
    - Bytes 0 – 287 : PWM values  [36 × float64]  (1000–2000 µs)
    """

    _PWM_OFFSET = 0

    def __init__(self, create: bool = True):
        """
        Initialize the shared memory buffer.

        Args:
            create: If True, create new buffer; if False, attach to existing
        """
        self.name = SHARED_MEM_NAME
        self.shape = (NUM_MOTORS,)
        self.dtype = np.float64

        try:
            if create:
                # Try to unlink any existing buffer first
                try:
                    existing = shared_memory.SharedMemory(name=self.name)
                    existing.close()
                    existing.unlink()
                except (FileNotFoundError, ValueError):
                    pass

                # Create new shared memory block (PWM array only)
                self.shm = shared_memory.SharedMemory(
                    name=self.name,
                    create=True,
                    size=NUM_MOTORS * 8  # 288 bytes
                )
                self.array = np.ndarray(self.shape, dtype=self.dtype,
                                        buffer=self.shm.buf, offset=self._PWM_OFFSET)
                self.array[:] = 0.0
                print(f"[SharedMem] Created new buffer: {self.name}")
            else:
                # Attach to existing shared memory
                self.shm = shared_memory.SharedMemory(name=self.name)
                self.array = np.ndarray(self.shape, dtype=self.dtype,
                                        buffer=self.shm.buf, offset=self._PWM_OFFSET)
                print(f"[SharedMem] Attached to existing buffer: {self.name}")

        except Exception as e:
            print(f"[SharedMem] ERROR: Failed to initialize buffer: {e}")
            raise

    def set_pwm(self, pwm_values: np.ndarray) -> None:
        """Update PWM values in shared memory."""
        self.array[:] = pwm_values

    def get_pwm(self) -> np.ndarray:
        """Read PWM values from shared memory."""
        return self.array.copy()

    def close(self) -> None:
        """Close the shared memory buffer (does not unlink)."""
        if self.shm:
            self.shm.close()
            print(f"[SharedMem] Closed buffer: {self.name}")

    def unlink(self) -> None:
        """Unlink the shared memory buffer (cleanup)."""
        if self.shm:
            try:
                self.shm.unlink()
                print(f"[SharedMem] Unlinked buffer: {self.name}")
            except Exception as e:
                print(f"[SharedMem] Warning: Could not unlink buffer: {e}")
