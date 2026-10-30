FROM ghcr.io/buidlguidl/ethevals-chain:inputs-d0ef1955a98ec678
WORKDIR /workspace
COPY --chown=agent:agent foundry.toml /workspace/foundry.toml
COPY --chown=agent:agent README.md /workspace/README.md
COPY --chown=agent:agent src /workspace/src
COPY --chown=agent:agent test /workspace/test
ENTRYPOINT []
CMD ["sleep", "infinity"]
