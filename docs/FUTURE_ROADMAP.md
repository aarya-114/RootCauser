# Future Improvements

RootCauser has reached a complete, resume-ready engineering-project milestone: alert ingestion, SigNoz REST retrieval, deterministic evidence ranking, grounded LLM reasoning, citation validation, GitHub reporting, Slack notification, and regression tests are implemented.

The following are small, concrete improvements rather than commitments to a broader platform:

- Add mocked webhook orchestration tests around the FastAPI background task.
- Persist investigation artifacts outside the running agent container.
- Persist incident state across restarts so same-incident versioning survives process crashes.
- Continue adding SigNoz response fixtures when deployed versions expose a new REST response shape.

These are not required for the current prototype to demonstrate its implemented incident-investigation workflow.
