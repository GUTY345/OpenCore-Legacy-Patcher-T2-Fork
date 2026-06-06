"""
cache.py: Base class for kernel cache management
"""
import sys

class BaseKernelCache:

    def rebuild(self) -> None:
        raise NotImplementedError("To be implemented in subclass")
