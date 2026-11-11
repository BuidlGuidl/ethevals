FROM ghcr.io/buidlguidl/ethevals-chain:inputs-d0ef1955a98ec678 AS contracts
USER root
WORKDIR /opt/governance
COPY contracts/ ./
RUN git clone --depth 1 --branch v5.7.0 https://github.com/OpenZeppelin/openzeppelin-contracts.git lib/openzeppelin-contracts && \
    test "$(git -C lib/openzeppelin-contracts rev-parse HEAD)" = cab19933c33c2ad1d4c7a84864a3601dddfd16f3 && \
    ln -s /opt/solidity/lib/forge-std lib/forge-std && \
    forge build && python3 export.py
COPY setup/ /setup/
RUN chmod +x /setup/bin/anvil
WORKDIR /tmp
ENTRYPOINT ["python3", "/setup/start.py"]
