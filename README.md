# Enterprise Expense Policy Compliance Auditor

An intelligent compliance auditor for corporate travel and entertainment (T&E) expense reports, built with Google Gemini, LangChain, and LangSmith.

## The Problem

Employees submit corporate expense reports with receipts, but compliance policies are nuanced:
- **Daily Per Diem**: $75 per day cap on individual meals.
- **Alcohol Limits**: Capped at 20% of meal subtotal; strictly prohibited for solo breakfast/lunch.
- **Ground Transportation**: Rideshares (Uber/Lyft) disallowed if public transit is under 15 minutes, with exceptions for late-night travel (10 PM–6 AM) or safety/equipment concerns.
- **Client Entertainment**: Requires itemized receipts, full attendee names and affiliations, and explicit business justification ($150 per person limit).
- **Documentation**: Itemized receipts mandatory for expenses > $25; split-receipt evasion prohibited.

This application inspects receipts, metadata, and justification notes against company policy to detect violations, compute eligible reimbursement amounts, and provide actionable feedback to employees.

## Development Approach: Build → Evaluate → Learn → Improve

In accordance with enterprise trust standards:
1. **Build**: Develop an expense auditor with policy retrieval (RAG) and verification capabilities.
2. **Evaluate**: Test across curated real-world scenarios (clean reports, clear violations, edge cases).
3. **Learn**: Inspect traces in LangSmith and analyze where the auditor struggles.
4. **Improve**: Iteratively refine the system to fix observed failure modes.

## Quickstart

### Prerequisites
- Python 3.12+
- [uv](https://docs.astral.sh/uv/) package manager

### Installation

```bash
git clone <repo-url>
cd enterprise-expense-auditor
make install
```

### Configuration

Copy `.env.example` to `.env` and set your API keys:

```bash
cp .env.example .env
```

Ensure `GOOGLE_API_KEY` (or `GEMINI_API_KEY`) is set. Optional: set `LANGCHAIN_API_KEY` to enable LangSmith tracing.

### Running Tests

```bash
make test
```
