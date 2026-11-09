#!/usr/bin/env python3
"""
Voice_based-_Tic-Tac-Toe Application Validator

Validates application dependencies and syntax without executing GUI, audio, or gameplay.

4 Sequential Validation Steps (stops on first failure):
1. Import speech_recognition module (no microphone init)
2. Import pyaudio module (no audio operations)
3. Compile Tic-Tac-Toe.py (syntax check)
4. Compile example.py, ga.py, kas.py (syntax checks)

All imports use -c flag to prevent module initialization side effects.
All syntax checks use python -m py_compile (no execution).

Exit Code:
  0 = All checks passed
  1 = Any check failed (validation stops at first failure)
"""

import logging
import subprocess
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def run_check(step_num, description, command):
    """Execute a single validation step and return success status."""
    logger.info(f"Step {step_num}: {description}")
    logger.debug(f"  Command: {command}")
    
    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=30,
        )
        
        if result.returncode == 0:
            logger.info(f"  ✓ PASS")
            if result.stdout:
                logger.debug(f"  Output: {result.stdout.strip()}")
            return True
        else:
            logger.error(f"  ✗ FAIL (exit code {result.returncode})")
            if result.stdout:
                logger.error(f"  stdout: {result.stdout.strip()}")
            if result.stderr:
                logger.error(f"  stderr: {result.stderr.strip()}")
            return False
    
    except subprocess.TimeoutExpired:
        logger.error(f"  ✗ FAIL (timeout after 30s)")
        return False
    except Exception as e:
        logger.error(f"  ✗ FAIL (exception: {e})")
        return False


def main():
    """Execute all validation steps sequentially."""
    logger.info("=" * 60)
    logger.info("Voice_based-_Tic-Tac-Toe Application Validator")
    logger.info("=" * 60)
    
    # Define validation steps (4 steps - tkinter removed)
    steps = [
        (
            1,
            "Validate speech_recognition import",
            'python -c "import speech_recognition; print(\'✓ speech_recognition available\')"',
        ),
        (
            2,
            "Validate pyaudio import",
            'python -c "import pyaudio; print(\'✓ pyaudio available\')"',
        ),
        (
            3,
            "Validate Tic-Tac-Toe.py syntax",
            "python -m py_compile Tic-Tac-Toe.py",
        ),
        (
            4,
            "Validate application syntax (example.py, ga.py, kas.py)",
            "python -m py_compile example.py ga.py kas.py",
        ),
    ]
    
    # Execute steps sequentially; stop on first failure
    for step_num, description, command in steps:
        if not run_check(step_num, description, command):
            logger.error("")
            logger.error("=" * 60)
            logger.error(f"VALIDATION FAILED at Step {step_num}")
            logger.error("=" * 60)
            return 1
    
    logger.info("")
    logger.info("=" * 60)
    logger.info("✓ ALL VALIDATION CHECKS PASSED")
    logger.info("=" * 60)
    return 0


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
