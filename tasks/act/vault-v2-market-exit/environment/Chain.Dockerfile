FROM ghcr.io/buidlguidl/ethevals-chain:inputs-8761a2534c168efd
USER root
COPY setup/ /setup/
RUN mkdir -p setup && cp /setup/*.sol setup/ && \
    cp /opt/setup-foundry.toml foundry.toml && \
    forge build && rm -rf setup
ENTRYPOINT ["python3", "/opt/start_chain.py"]
