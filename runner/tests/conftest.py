import pytest


def pytest_addoption(parser):
    parser.addoption("--run-docker", action="store_true", help="Run the real Docker and Forge proofs.")
    parser.addoption("--shard", help="Run only shard I of N of the Docker proofs, written I/N.")


def pytest_configure(config):
    config.addinivalue_line("markers", "docker: requires the local runner image and Docker")


def pytest_collection_modifyitems(config, items):
    if not config.getoption("--run-docker"):
        for item in items:
            if "docker" in item.keywords:
                item.add_marker(pytest.mark.skip(reason="Use --run-docker to run Docker proofs."))
    if shard := config.getoption("--shard"):
        index, count = map(int, shard.split("/"))
        if not 1 <= index <= count:
            raise pytest.UsageError("--shard must be I/N with 1 <= I <= N")
        docker = [item for item in items if "docker" in item.keywords]
        dropped = {item for position, item in enumerate(docker) if position % count != index - 1}
        config.hook.pytest_deselected(items=list(dropped))
        items[:] = [item for item in items if item not in dropped]
