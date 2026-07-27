"""
test_validate_patch.py: Regression tests for BuildMiscellaneous._validate_patch

Phase 3 goal: _validate_patch must RAISE PatchValidationError on invalid
patches instead of calling sys.exit(3), so the guardrail is unit-testable
(a failing patch no longer kills the whole interpreter).

Runnable two ways:
    python3 tests/test_validate_patch.py      # standalone, no dependencies
    pytest tests/test_validate_patch.py       # if pytest is installed
"""
import sys
import binascii
from pathlib import Path

# Allow running from the repo root without installing the package.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from opencore_legacy_patcher.efi_builder.misc import BuildMiscellaneous, PatchValidationError


def _validator():
    # _validate_patch does not touch instance state, so bypass __init__
    # (which would try to build a whole OpenCore config).
    return BuildMiscellaneous.__new__(BuildMiscellaneous)


def _patch(find_hex, replace_hex, comment="test"):
    return {
        "Comment": comment,
        "Identifier": "com.apple.test",
        "Base": "",
        "Find": binascii.unhexlify(find_hex),
        "Replace": binascii.unhexlify(replace_hex),
    }


def test_valid_patch_returns_true():
    obj = _validator()
    patch = _patch("554889E5", "31C0C390")  # 4 bytes == 4 bytes
    assert obj._validate_patch(patch) is True


def test_length_mismatch_raises():
    obj = _validator()
    patch = _patch("554889E5", "31C0C3")  # 4 bytes != 3 bytes
    try:
        obj._validate_patch(patch)
    except PatchValidationError:
        return  # expected
    raise AssertionError("Expected PatchValidationError for length mismatch")


def test_missing_field_raises():
    obj = _validator()
    patch = {"Comment": "broken", "Find": None, "Replace": b"\x00"}
    try:
        obj._validate_patch(patch)
    except PatchValidationError:
        return  # expected
    raise AssertionError("Expected PatchValidationError for missing/None field")


def test_validation_error_is_not_systemexit():
    # A test must be able to catch the failure; sys.exit() raises SystemExit
    # (BaseException) which would not be caught by `except Exception`.
    obj = _validator()
    patch = _patch("55", "5566")
    try:
        obj._validate_patch(patch)
    except Exception:
        return  # PatchValidationError is a plain Exception subclass -> good
    raise AssertionError("Expected a catchable Exception, not SystemExit")


def _run_standalone():
    tests = [
        test_valid_patch_returns_true,
        test_length_mismatch_raises,
        test_missing_field_raises,
        test_validation_error_is_not_systemexit,
    ]
    failures = 0
    for t in tests:
        try:
            t()
            print(f"PASS: {t.__name__}")
        except AssertionError as e:
            failures += 1
            print(f"FAIL: {t.__name__} -> {e}")
    if failures:
        print(f"\n{failures} test(s) failed")
        return 1
    print(f"\nAll {len(tests)} tests passed")
    return 0


if __name__ == "__main__":
    sys.exit(_run_standalone())
