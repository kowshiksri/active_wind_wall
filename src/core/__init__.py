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
    Manages a shared memory buffer for motor PWM commands and enable mask.

    Layout (two contiguous float64 arrays):
    - Bytes   0 – 287 : PWM values  [36 × float64]  (1000–2000 µs)
    - Bytes 288 – 575 : Enable mask  [36 × float64]  (1.0 = on, 0.0 = muted)
    """

    _PWM_OFFSET  = 0
    _MASK_OFFSET = NUM_MOTORS * 8  # 288 bytes in

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

                # Create new shared memory block (PWM array + mask array)
                self.shm = shared_memory.SharedMemory(
                    name=self.name,
                    create=True,
                    size=NUM_MOTORS * 8 * 2  # 576 bytes total
                )
                self.array = np.ndarray(self.shape, dtype=self.dtype,
                                        buffer=self.shm.buf, offset=self._PWM_OFFSET)
                self.mask  = np.ndarray(self.shape, dtype=self.dtype,
                                        buffer=self.shm.buf, offset=self._MASK_OFFSET)
                self.array[:] = 0.0
                self.mask[:]  = 1.0  # All motors enabled by default
                print(f"[SharedMem] Created new buffer: {self.name}")
            else:
                # Attach to existing shared memory
                self.shm = shared_memory.SharedMemory(name=self.name)
                self.array = np.ndarray(self.shape, dtype=self.dtype,
                                        buffer=self.shm.buf, offset=self._PWM_OFFSET)
                self.mask  = np.ndarray(self.shape, dtype=self.dtype,
                                        buffer=self.shm.buf, offset=self._MASK_OFFSET)
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

    def set_mask(self, mask: np.ndarray) -> None:
        """Write enable mask (1.0 = on, 0.0 = muted) into shared memory."""
        self.mask[:] = mask

    def get_mask(self) -> np.ndarray:
        """Read enable mask from shared memory."""
        return self.mask.copy()
    
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
