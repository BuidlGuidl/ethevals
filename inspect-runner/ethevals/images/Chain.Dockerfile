FROM ghcr.io/foundry-rs/foundry:v1.5.1@sha256:3a70bfa9bd2c732a767bb60d12c8770b40e8f9b6cca28efc4b12b1be81c7f28e AS foundry
FROM python:3.13.7-slim-bookworm@sha256:adafcc17694d715c905b4c7bebd96907a1fd5cf183395f0ebc4d3428bd22d92d
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates git && rm -rf /var/lib/apt/lists/*
COPY --from=foundry /usr/local/bin/anvil /usr/local/bin/cast /usr/local/bin/forge /usr/local/bin/
RUN mkdir -p /opt/solidity/lib && \
    git init /opt/solidity/lib/forge-std && \
    git -C /opt/solidity/lib/forge-std fetch --depth 1 https://github.com/foundry-rs/forge-std.git 77041d2ce690e692d6e03cc812b57d1ddaa4d505 && \
    git -C /opt/solidity/lib/forge-std checkout FETCH_HEAD && \
    rm -rf /opt/solidity/lib/forge-std/.git && chmod -R a-w /opt/solidity
COPY ChainSetup.sol /opt/solidity/lib/ChainSetup.sol
COPY rpc_filter.py /opt/rpc_filter.py
COPY rpc_methods.json /opt/rpc_methods.json
RUN ln -s /usr/local/bin/python3 /usr/bin/python3 && \
    useradd --create-home agent && mkdir /eval /workspace && chown agent:agent /eval /workspace
USER agent
WORKDIR /eval
ENTRYPOINT ["python3", "/opt/rpc_filter.py"]
