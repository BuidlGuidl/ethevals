FROM ethevals-solidity:foundry-1.5.1-solc-0.8.30-std-1.9.7 AS compiler
FROM ghcr.io/foundry-rs/foundry:v1.5.1@sha256:3a70bfa9bd2c732a767bb60d12c8770b40e8f9b6cca28efc4b12b1be81c7f28e
USER root
RUN apt-get update && apt-get install -y --no-install-recommends python3 && rm -rf /var/lib/apt/lists/*
COPY --from=compiler /home/agent/.svm/0.8.30/solc-0.8.30 /opt/solc
COPY rpc_filter.py /opt/rpc_filter.py
RUN mkdir /eval && chown foundry:foundry /eval
USER foundry
WORKDIR /eval
ENTRYPOINT ["python3", "/opt/rpc_filter.py"]
