FROM ghcr.io/buidlguidl/ethevals-chain:inputs-d0ef1955a98ec678
WORKDIR /workspace
COPY --chown=agent:agent foundry.toml /workspace/foundry.toml
COPY --chown=agent:agent src /workspace/src
RUN git clone --depth 1 --branch v5.7.0 https://github.com/OpenZeppelin/openzeppelin-contracts.git /workspace/lib/openzeppelin-contracts \
    && chown -R agent:agent /workspace/lib
ENTRYPOINT []
CMD ["sleep", "infinity"]
