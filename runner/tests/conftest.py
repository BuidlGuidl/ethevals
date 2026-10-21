import pytest


def pytest_addoption(parser):
    parser.addoption("--run-docker", action="store_true", help="Run the real Docker and Forge proofs.")


def pytest_configure(config):
    config.addinivalue_line("markers", "docker: requires the local runner image and Docker")


def pytest_collection_modifyitems(config, items):
    if not config.getoption("--run-docker"):
        for item in items:
            if "docker" in item.keywords:
                item.add_marker(pytest.mark.skip(reason="Use --run-docker to run Docker proofs."))
