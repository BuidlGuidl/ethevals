FROM ghcr.io/buidlguidl/ethevals-chain:inputs-d0ef1955a98ec678
USER root
RUN git clone --depth 1 --branch v5.7.0 https://github.com/OpenZeppelin/openzeppelin-contracts.git lib/openzeppelin-contracts && \
    test "$(git -C lib/openzeppelin-contracts rev-parse HEAD)" = cab19933c33c2ad1d4c7a84864a3601dddfd16f3 && \
    git clone --depth 1 --branch v5.7.0 https://github.com/OpenZeppelin/openzeppelin-contracts-upgradeable.git lib/openzeppelin-contracts-upgradeable && \
    test "$(git -C lib/openzeppelin-contracts-upgradeable rev-parse HEAD)" = 14f52c54d3a1eefbda3d4071efba24d3c1e07e8a && \
    git clone --depth 1 --branch v1.4.1 https://github.com/safe-global/safe-smart-account.git lib/safe-smart-account && \
    test "$(git -C lib/safe-smart-account rev-parse HEAD)" = bf943f80fec5ac647159d26161446ac5d716a294
# The Safe singleton only fits the contract size limit with the optimizer on.
ENV FOUNDRY_OPTIMIZER=true FOUNDRY_OPTIMIZER_RUNS=200
COPY chain-remappings.txt remappings.txt
COPY setup/ /setup/
# setup/bin/anvil starts the chain's clock nine days back, so setup can lay out a history.
ENV PATH=/setup/bin:$PATH
COPY repo/src/ /setup/src/
COPY repo/script/ /setup/script/
RUN chmod +x /setup/bin/anvil && cp -R /setup setup && cp /opt/setup-foundry.toml foundry.toml && \
    forge build && rm -rf setup
ENTRYPOINT ["python3", "/opt/start_chain.py"]
