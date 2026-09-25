# Evaluate agents for doing, bare models for knowing

ETH Evals scores two different things in two tables.

The agent evals table scores agents, a harness plus a model, in the `internet` and `skills` modes. People use agents day to day, and "can I trust my agent with Ethereum" is the question this table answers. Anything that needs an agent loop is tested only here, because nobody uses a bare model that way.

The knowledge table scores bare models in the `vanilla` mode. It asks straight questions with fixed answers, with no harness and no tools, and grades them deterministically. It shows what a model knows and whether a newer model knows more.

The cost: every harness brings its own system prompt and tools, so the agent evals table never shows pure model knowledge. The knowledge table covers that.
