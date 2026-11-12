FROM ghcr.io/buidlguidl/ethevals-chain:inputs-d0ef1955a98ec678
WORKDIR /workspace
COPY --chown=agent:agent foundry.toml /workspace/foundry.toml
COPY --chown=agent:agent src /workspace/src
# OpenZeppelin 5.7.0 for the raffle, and 4.9.6 because Chainlink's VRF mock imports it by that name.
RUN git clone --depth 1 --branch v5.7.0 https://github.com/OpenZeppelin/openzeppelin-contracts.git /workspace/lib/openzeppelin-contracts \
    && git clone --depth 1 --branch v4.9.6 https://github.com/OpenZeppelin/openzeppelin-contracts.git /workspace/lib/openzeppelin-contracts-4.9.6 \
    && rm -rf /workspace/lib/openzeppelin-contracts/.git /workspace/lib/openzeppelin-contracts-4.9.6/.git
# @chainlink/contracts 1.5.0 from npm, pinned by hash, at lib/chainlink so the docs' import paths work.
RUN python3 -c "import hashlib, io, tarfile, urllib.request; data = urllib.request.urlopen('https://registry.npmjs.org/@chainlink/contracts/-/contracts-1.5.0.tgz').read(); assert hashlib.sha256(data).hexdigest() == '24a8d510e947a74763723845d5f55405997104aecb9d45061f969d25fb917a3d', 'unexpected tarball'; tarfile.open(fileobj=io.BytesIO(data)).extractall('/workspace/lib', filter='data')" \
    && mv /workspace/lib/package /workspace/lib/chainlink \
    && chown -R agent:agent /workspace/lib
ENTRYPOINT []
CMD ["sleep", "infinity"]
