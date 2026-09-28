# TEL-C2-023 — Telecom Field Engineer Work Log Summarization & Completion Validation Agent

> **Category**: Cat 2 (orchestrates multiple steps to accomplish a specific job-to-be-done)
> **Industry**: TEL

## Overview

Field engineers write up what they did in free-form notes. Turning those notes into something a
service-management system can use means reading each log, working out which of the required steps
for that job type were actually performed, spotting what was left open, and writing a summary — for
every visit, in whatever style the engineer happened to write in.

This agent does that pass. It validates and parses the log into structured actions and
measurements with a confidence score, checks those actions against the completion criteria for the
work type, collects the failed and uncertain items with an urgency label and a recommended next
step, and generates a summary suitable for a service-management ticket.

**It reports what the log says, not what happened on site.** A log it marks complete means the
notes cover the required steps — not that the work was done correctly, and not that anything was
independently verified. Where its parse is uncertain, that is carried through as an item to check
rather than resolved silently. The completion criteria live in configuration and are yours to
match to your own procedures. Personal details of engineers, customer addresses, and equipment
identifiers are checked for and kept out of the generated summary.

This is an agent template built with the **AGENTIC STAR** development platform and the
**AgentCore Framework**. It is intended to be taken as a starting point: fork it, adapt it to
your own data and policies, and run it inside your own AGENTIC STAR deployment.

## Requirements

**This template does not run standalone.** It requires:

| Requirement | Notes |
|---|---|
| **AGENTIC STAR platform** | The agent connects to the platform at start-up. Without it, start-up fails immediately (see *Behaviour without the platform* below). Deployment guides and API documentation: [AGENTIC STAR Developers](https://developers.fd.agenticstar.tm.softbank.jp/) |
| **AgentCore Framework** (`agenticstar-agentcore`) | Installed from PyPI as a dependency. |
| Python | >=3.11 |

```bash
pip install -e .
```

### Behaviour without the platform

The framework is designed to run **only** on AGENTIC STAR. There is no fallback or degraded
mode. If the platform is unreachable or the SDK version does not match, the agent raises
`PlatformRequired` during graph compile / start-up preflight rather than starting in a partially
working state. This is intentional — a half-running agent is worse than one that refuses to start.

## Quick Start

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
python -m pytest tests/ -v
```

Tests run without a platform connection. Running the agent itself does not.

## Project Structure

```
src/          agent implementation (nodes, services, schemas)
tests/        unit, integration and boundary tests
config/       agent configuration
docs/         design and test documentation
```

See `docs/02_design.md` for the design and `docs/03_test_spec.md` for the test specification.

## Customising

1. Adjust `config/` for your own environment and policies.
2. Replace the knowledge sources and sample data with your own.
3. Review the node implementations under `src/nodes/` for domain-specific logic.
4. Re-run the test suite.

## License

MIT — see [LICENSE](LICENSE).

## Status of this repository

This template is published **as is**, by its individual author, under the MIT license. It carries
**no warranty and no support commitment**, and no organisation stands behind its behaviour or
fitness for any purpose. Issues and pull requests may or may not receive a response; that is at
the sole discretion of the repository owner.
