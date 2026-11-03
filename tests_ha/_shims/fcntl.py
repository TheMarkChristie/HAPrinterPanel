"""A stand-in for fcntl on Windows, where Home Assistant's test harness almost runs: nothing here locks anything. Put on
the path by tests_ha/conftest.py only when sys.platform is win32."""


def fcntl(*args, **kwargs):
    return 0


def ioctl(*args, **kwargs):
    return 0


def flock(*args, **kwargs):
    return None


LOCK_EX = LOCK_NB = LOCK_UN = LOCK_SH = F_GETFL = F_SETFL = 0
