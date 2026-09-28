FROM ghcr.io/foundry-rs/foundry:v1.5.1@sha256:3a70bfa9bd2c732a767bb60d12c8770b40e8f9b6cca28efc4b12b1be81c7f28e AS foundry
FROM python:3.13.7-slim-bookworm@sha256:adafcc17694d715c905b4c7bebd96907a1fd5cf183395f0ebc4d3428bd22d92d
ARG TARGETARCH
COPY --from=foundry /usr/local/bin/anvil /usr/local/bin/cast /usr/local/bin/forge /usr/local/bin/
RUN python3 -c 'import hashlib, os, pathlib, urllib.request; \
    sources = {"amd64": ("https://raw.githubusercontent.com/ethereum/solc-bin/gh-pages/linux-amd64/solc-linux-amd64-v0.8.30+commit.73712a01", "f3e987dc6ecebd4bd350c48edcbc320b46cf9e3109bd3fc3d88f1acaf4c428f7"), \
    "arm64": ("https://raw.githubusercontent.com/nikitastupin/solc/main/linux/aarch64/solc-v0.8.30", "54f48274e5ec8a58b378f07c226fa1e25801526b6b0d16129f3a14a18efe72cd")}; \
    url, expected = sources[os.environ["TARGETARCH"]]; data = urllib.request.urlopen(url, timeout=120).read(); \
    assert hashlib.sha256(data).hexdigest() == expected, "solc checksum mismatch"; \
    path = pathlib.Path("/opt/solc"); path.write_bytes(data); path.chmod(0o755)'
COPY rpc_filter.py /opt/rpc_filter.py
RUN ln -s /usr/local/bin/python3 /usr/bin/python3 && \
    useradd --create-home foundry && mkdir /eval && chown foundry:foundry /eval
USER foundry
WORKDIR /eval
ENTRYPOINT ["python3", "/opt/rpc_filter.py"]
