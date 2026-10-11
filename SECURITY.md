# Security

Sequela runs an AI agent through tools and checks its answers against what the tools really do. The bugs that matter most are a tool call that escapes its sandbox, an API key that ends up in a result file or a log, and a way to make the checker agree with a false answer. Please report those. A weak score is a normal issue.

## How to report

Open a new issue titled **Security report**. Say only that you have found something, and leave out the details, so nothing is made public before it is fixed. I will reply and we can move the details somewhere private.

## What to expect

This is a one-person project, so there is no formal response time. A report that comes with steps to reproduce it gets read promptly.

## Supported versions

Only the latest commit on `main` is supported.
