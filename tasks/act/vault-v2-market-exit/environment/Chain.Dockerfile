FROM ghcr.io/buidlguidl/ethevals-chain:inputs-d0ef1955a98ec678
USER root
COPY setup/ /setup/
RUN mkdir -p setup && cp /setup/*.sol setup/ && \
    cp /opt/setup-foundry.toml foundry.toml && \
    forge build && rm -rf setup
ENTRYPOINT ["python3", "/opt/start_chain.py"]
