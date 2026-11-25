FROM ghcr.io/buidlguidl/ethevals-chain:inputs-d0ef1955a98ec678
USER root
COPY setup/ /setup/
RUN chmod +x /setup/bin/anvil && \
    mkdir -p setup && cp /setup/*.sol setup/ && \
    cp /opt/setup-foundry.toml foundry.toml && \
    forge build && rm -rf setup
WORKDIR /tmp
ENTRYPOINT ["python3", "/setup/start.py"]
