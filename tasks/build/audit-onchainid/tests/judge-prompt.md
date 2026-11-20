You are judging a security audit that an AI agent wrote.

The agent was given a smart contract project and asked to act as its security auditor. It was told to review the contracts and write up its findings, at most 10, the most severe first. Its report is the file submission/findings.md.

Professional auditors reviewed the same code before. Their findings are listed below. Your job is to say, for each one, whether the agent's report found it.

How to decide:
- Only the first 10 findings in the report count.
- A finding is found when the report describes the same flaw, in the same code, with the same consequence. Different wording, severity or proof of concept does not matter.
- It is not found when the report describes a different flaw in the same function or file, makes a generic remark such as "validate inputs", or lists areas to review.
- One finding in the report can count for two of the auditors' findings only when it gives the root cause of both.
- The last item in the list, 'guard', is not one of the auditors' findings. Answer it from the whole report.

The auditors' findings:

{criteria}
