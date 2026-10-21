FROM ghcr.io/buidlguidl/ethevals-chain:inputs-583c39604a276cd3
USER root
COPY setup/ /setup/
ENTRYPOINT ["python3", "/opt/start_chain.py"]
