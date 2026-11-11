FROM ghcr.io/buidlguidl/ethevals-chain:inputs-8761a2534c168efd
USER root
COPY setup/ /setup/
ENTRYPOINT ["python3", "/opt/start_chain.py"]
