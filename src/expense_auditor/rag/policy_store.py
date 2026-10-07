"""Policy document parser and in-memory knowledge store."""

import re
from pathlib import Path
from expense_auditor.models.expense import ExpenseCategory
from expense_auditor.models.policy import PolicySection


class PolicyStore:
    """Loads, indexes, and provides retrieval over corporate policy markdown."""

    def __init__(self, policy_path: Path):
        self.policy_path = policy_path
        self.sections: list[PolicySection] = []
        self._load_and_parse()

    def _load_and_parse(self) -> None:
        if not self.policy_path.exists():
            raise FileNotFoundError(f"Policy document not found at {self.policy_path}")

        text = self.policy_path.read_text(encoding="utf-8")
        # Split on headers of the form: ### SEC-X.Y: Title
        pattern = r"###\s+(SEC-[\d\.]+):\s+([^\n]+)\n(.*?)(?=(?:###\s+SEC-|\Z))"
        matches = re.findall(pattern, text, re.DOTALL)

        category_map = {
            "SEC-1.1": ExpenseCategory.MEALS,
            "SEC-1.2": ExpenseCategory.ALCOHOL,
            "SEC-1.3": ExpenseCategory.MEALS,
            "SEC-2.1": ExpenseCategory.GROUND_TRANSIT,
            "SEC-2.2": ExpenseCategory.GROUND_TRANSIT,
            "SEC-3.1": ExpenseCategory.CLIENT_ENTERTAINMENT,
            "SEC-3.2": ExpenseCategory.CLIENT_ENTERTAINMENT,
            "SEC-4.1": ExpenseCategory.LODGING,
            "SEC-4.2": ExpenseCategory.INCIDENTAL,
            "SEC-5.1": ExpenseCategory.OTHER,
            "SEC-5.2": ExpenseCategory.OTHER,
        }

        for sec_id, title, content in matches:
            content_clean = content.strip()
            # Extract keywords from title and content
            words = set(re.findall(r"\b[a-zA-Z]{4,}\b", (title + " " + content_clean).lower()))
            category = category_map.get(sec_id, ExpenseCategory.OTHER)

            section = PolicySection(
                section_id=sec_id,
                title=title.strip(),
                content=content_clean,
                category=category,
                keywords=list(words),
            )
            self.sections.append(section)

    def get_all_sections(self) -> list[PolicySection]:
        return list(self.sections)

    def get_section_by_id(self, section_id: str) -> PolicySection | None:
        for sec in self.sections:
            if sec.section_id.lower() == section_id.lower():
                return sec
        return None

    def search(self, query: str, top_k: int = 3, category: ExpenseCategory | None = None) -> list[PolicySection]:
        """Keyword and relevance scoring search across policy sections."""
        query_words = set(re.findall(r"\b[a-zA-Z]{3,}\b", query.lower()))
        scored: list[tuple[float, PolicySection]] = []

        for sec in self.sections:
            score = 0.0
            # Category boost
            if category and sec.category == category:
                score += 3.0

            # Title matches
            title_lower = sec.title.lower()
            for q in query_words:
                if q in title_lower:
                    score += 2.0
                if q in sec.keywords:
                    score += 1.0

            # Content exact phrase boost
            if query.lower() in sec.content.lower():
                score += 4.0

            scored.append((score, sec))

        # Sort descending by score
        scored.sort(key=lambda x: x[0], reverse=True)
        return [sec for score, sec in scored[:top_k] if score > 0] or self.sections[:top_k]
