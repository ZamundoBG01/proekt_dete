import re
from typing import List, Dict, Any
from core_universe import BaseObject, KnowledgeStatus

# ==========================================
# AP-020: Memory Budget Manager
# ==========================================
class MemoryBudgetManager:
    """Управлява размера на контекста, изпращан към модела."""
    def __init__(self, max_tokens_budget: int = 4000):
        self.max_budget = max_tokens_budget

    def estimate_tokens(self, text: str) -> int:
        """Бърза приблизителна оценка за броя токени/думи."""
        return len(text.split())

    def trim_context_to_budget(self, items: List[str], current_prompt: str) -> str:
        """Сглобява контекста, гарантирайки че не надвишаваме бюджета."""
        budget_left = self.max_budget - self.estimate_tokens(current_prompt)
        selected_context = []

        for item in items:
            item_tokens = self.estimate_tokens(item)
            if budget_left - item_tokens >= 0:
                selected_context.append(item)
                budget_left -= item_tokens
            else:
                break  # Спираме, когато достигнем лимита

        return "\n---\n".join(selected_context)


# ==========================================
# AP-021: Verification & Anti-Hallucination Engine
# ==========================================
class VerificationEngine:
    """Проверява достоверността на данните и спира халюцинациите."""
    def __init__(self):
        pass

    def classify_statement(self, text: str) -> KnowledgeStatus:
        """Автоматично определя дали твърдението е факт, правило или хипотеза."""
        text_lower = text.lower()
        if any(word in text_lower for word in ["задължително", "винаги", "закон", "правило", "не може"]):
            return KnowledgeStatus.RULE
        elif any(word in text_lower for word in ["може би", "вероятно", "предполагам", "хипотеза", "ако"]):
            return KnowledgeStatus.HYPOTHESIS
        else:
            return KnowledgeStatus.FACT

    def verify_against_rules(self, generated_text: str, active_rules: List[str]) -> Dict[str, Any]:
        """Проверява дали генерираният отговор нарушава някое от установените правила."""
        violations = []
        for rule in active_rules:
            # Базова проверка за пряко противоречие (ще се надгражда с агент)
            if "не " + rule.lower() in generated_text.lower():
                violations.append(rule)

        return {
            "is_valid": len(violations) == 0,
            "violations": violations
        }
