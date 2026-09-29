import pytest


def pytest_addoption(parser):
    parser.addoption("--run-docker", action="store_true", help="Run the real Docker and Forge proofs.")
    parser.addoption("--run-live-exa", action="store_true", help="Check the keyless hosted Exa tool snapshot.")


def pytest_configure(config):
    config.addinivalue_line("markers", "docker: requires the local runner image and Docker")
    config.addinivalue_line("markers", "live_exa: calls the keyless hosted Exa service")


def pytest_collection_modifyitems(config, items):
    for item in items:
        if "live_exa" in item.keywords and not config.getoption("--run-live-exa"):
            item.add_marker(pytest.mark.skip(reason="Use --run-live-exa for hosted parity."))
    if not config.getoption("--run-docker"):
        for item in items:
            if "docker" in item.keywords:
                item.add_marker(pytest.mark.skip(reason="Use --run-docker to run Docker proofs."))
