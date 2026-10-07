"""High-level retriever interface for expense compliance policies."""

from pathlib import Path
from expense_auditor.config import settings
from expense_auditor.models.expense import ExpenseCategory, ExpenseReport
from expense_auditor.models.policy import PolicyCitation, PolicySection
from expense_auditor.rag.policy_store import PolicyStore


class PolicyRetriever:
    """Retrieves relevant policy clauses for a given expense report or query."""

    def __init__(self, policy_path: Path | None = None):
        path = policy_path or settings.policy_document_path
        self.store = PolicyStore(path)

    def retrieve_for_report(self, report: ExpenseReport) -> list[PolicySection]:
        """Gathers all policy sections applicable to the expense report."""
        categories = set(r.category for r in report.receipts)
        # Check if any receipt contains alcohol items
        for r in report.receipts:
            if any(item.is_alcohol for item in r.line_items):
                categories.add(ExpenseCategory.ALCOHOL)

        # Also inspect notes for keywords
        notes_lower = report.justification_notes.lower()
        if "uber" in notes_lower or "lyft" in notes_lower or "taxi" in notes_lower or "transit" in notes_lower:
            categories.add(ExpenseCategory.GROUND_TRANSIT)
        if "client" in notes_lower or "dinner" in notes_lower or len(report.attendees) > 0:
            categories.add(ExpenseCategory.CLIENT_ENTERTAINMENT)

        matched_sections: dict[str, PolicySection] = {}

        # 1. Category matches
        for sec in self.store.get_all_sections():
            if sec.category in categories:
                matched_sections[sec.section_id] = sec

        # 2. Query search using justification notes & trip purpose
        query_text = f"{report.trip_purpose} {report.justification_notes}"
        searched = self.store.search(query_text, top_k=4)
        for sec in searched:
            matched_sections[sec.section_id] = sec

        # Always include anti-fraud and receipt documentation rules as standard baseline
        base_rules = ["SEC-1.1", "SEC-1.3", "SEC-5.1"]
        for rule_id in base_rules:
            sec = self.store.get_section_by_id(rule_id)
            if sec:
                matched_sections[sec.section_id] = sec

        return sorted(matched_sections.values(), key=lambda s: s.section_id)

    def format_policies_for_prompt(self, sections: list[PolicySection]) -> str:
        """Formats policy sections into clean markdown for injection into LLM prompts."""
        blocks = []
        for s in sections:
            blocks.append(f"### [{s.section_id}] {s.title}\n{s.content}")
        return "\n\n".join(blocks)

    def create_citation(self, section_id: str, explanation: str | None = None) -> PolicyCitation:
        sec = self.store.get_section_by_id(section_id)
        if sec:
            return PolicyCitation(
                section_id=sec.section_id,
                title=sec.title,
                relevant_clause=sec.content[:200] + "...",
                explanation=explanation,
            )
        return PolicyCitation(
            section_id=section_id,
            title=f"Policy {section_id}",
            relevant_clause="Referenced policy clause",
            explanation=explanation,
        )
