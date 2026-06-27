"""
enums.py: Compatibility module for StrEnum backport
"""
import sys

if sys.version_info >= (3, 11):
    from enum import StrEnum
else:
    from enum import Enum

    class StrEnum(str, Enum):
        """
        Backport of StrEnum for Python < 3.11

        StrEnum: Enum where members are also strings
        """
        def __new__(cls, value):
            if not isinstance(value, str):
                raise TypeError(f"Values of {cls.__name__} must be strings")
            return str.__new__(cls, value)

        def __str__(self):
            return str.__str__(self)