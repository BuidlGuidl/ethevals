FROM ghcr.io/buidlguidl/ethevals-chain:inputs-d0ef1955a98ec678
WORKDIR /workspace
RUN ln -s /chain/chain_context.json /workspace/chain_context.json && \
    ln -s /chain/payouts.csv /workspace/payouts.csv && \
    ln -s /chain/payout-bot.log /workspace/payout-bot.log
ENTRYPOINT []
CMD ["sleep", "infinity"]
