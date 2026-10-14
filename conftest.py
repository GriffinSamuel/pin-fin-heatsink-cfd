import pytest


def pytest_addoption(parser):
    parser.addoption("--slow", action="store_true", default=False, help="run tests that call the OpenFOAM v1912 mesher (minutes)")


def pytest_configure(config):
    config.addinivalue_line("markers", "slow: needs the cloud OpenFOAM (ESI) mesher; run with --slow")


def pytest_collection_modifyitems(config, items):
    if config.getoption("--slow"):
        return
    skip = pytest.mark.skip(reason="slow mesher test; use --slow")
    for it in items:
        if "slow" in it.keywords:
            it.add_marker(skip)
