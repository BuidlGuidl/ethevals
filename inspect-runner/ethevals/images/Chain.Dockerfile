FROM ghcr.io/foundry-rs/foundry:v1.5.1@sha256:3a70bfa9bd2c732a767bb60d12c8770b40e8f9b6cca28efc4b12b1be81c7f28e AS foundry
FROM python:3.13.7-slim-bookworm@sha256:adafcc17694d715c905b4c7bebd96907a1fd5cf183395f0ebc4d3428bd22d92d
ARG TARGETARCH
RUN apt-get update && apt-get install -y --no-install-recommends jq ca-certificates && rm -rf /var/lib/apt/lists/*
COPY --from=foundry /usr/local/bin/anvil /usr/local/bin/cast /usr/local/bin/forge /usr/local/bin/
COPY solc.json /tmp/solc.json
RUN python3 -c 'import hashlib, json, os, pathlib, urllib.request; \
    source = json.loads(pathlib.Path("/tmp/solc.json").read_text())["sources"][os.environ["TARGETARCH"]]; \
    data = urllib.request.urlopen(source["url"], timeout=120).read(); \
    assert hashlib.sha256(data).hexdigest() == source["sha256"], "solc checksum mismatch"; \
    path = pathlib.Path("/opt/solc"); path.write_bytes(data); path.chmod(0o755)'
COPY rpc_filter.py /opt/rpc_filter.py
RUN ln -s /usr/local/bin/python3 /usr/bin/python3 && \
    useradd --create-home foundry && mkdir /eval && chown foundry:foundry /eval
USER foundry
WORKDIR /eval
ENTRYPOINT ["python3", "/opt/rpc_filter.py"]
