FROM ghcr.io/buidlguidl/ethevals-chain:inputs-d0ef1955a98ec678
USER root
COPY setup/ /setup/
ENTRYPOINT ["python3", "/opt/start_chain.py"]
