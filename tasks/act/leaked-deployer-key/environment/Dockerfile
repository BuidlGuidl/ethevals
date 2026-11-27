FROM ghcr.io/buidlguidl/ethevals-chain:inputs-d0ef1955a98ec678
WORKDIR /workspace
COPY --chown=agent:agent repo/ /workspace/
RUN git clone --depth 1 --branch v5.7.0 https://github.com/OpenZeppelin/openzeppelin-contracts.git lib/openzeppelin-contracts && \
    test "$(git -C lib/openzeppelin-contracts rev-parse HEAD)" = cab19933c33c2ad1d4c7a84864a3601dddfd16f3 && \
    git clone --depth 1 --branch v5.7.0 https://github.com/OpenZeppelin/openzeppelin-contracts-upgradeable.git lib/openzeppelin-contracts-upgradeable && \
    test "$(git -C lib/openzeppelin-contracts-upgradeable rev-parse HEAD)" = 14f52c54d3a1eefbda3d4071efba24d3c1e07e8a && \
    ln -s /chain/chain_context.json /workspace/chain_context.json
ENTRYPOINT []
CMD ["sleep", "infinity"]
