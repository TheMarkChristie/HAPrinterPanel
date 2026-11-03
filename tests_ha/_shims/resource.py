"""A stand-in for resource on Windows, where Home Assistant's test harness almost runs. Put on the path by
tests_ha/conftest.py only when sys.platform is win32."""

RLIMIT_NOFILE = 7


def getrlimit(*args):
    return (1024, 4096)


def setrlimit(*args):
    return None
