import uuid
from enum import Enum
from typing import List, Dict, Any, Optional

# ==========================================
# AP-090: Agent Roles & Profiles
# ==========================================
class AgentRole(Enum):
    PLANNER = "planner"        # Планира стъпките
    RESEARCHER = "researcher"  # Търси факти в Knowledge Core / Graph
    CREATIVE = "creative"      # Генерира текстове, код или съдържание
    RULE_CHECKER = "rule_checker" # Следи за правила и ограничения
    CRITIC = "critic"          # Валидира крайния резултат за грешки


class BaseAgent:
    """Дефиниция на индивидуален агент с конкретна роля."""
    def __init__(self, role: AgentRole, system_instruction: str):
        self.agent_id = str(uuid.uuid4())
        self.role = role
        self.system_instruction = system_instruction

    def process_task(self, task_input: str, context: Optional[Dict[str, Any]] = None) -> str:
        """Подготвя контекста и промпта за конкретния агент."""
        # Тук агента структурира работата си според ролята
        return f"[{self.role.value.upper()}] Обработва задача: {task_input}"


# ==========================================
# AP-091: Task Decomposition & Execution (Planner)
# ==========================================
class TaskStep:
    """Единична стъпка от плана за изпълнение."""
    def __init__(self, step_id: int, description: str, assigned_role: AgentRole):
        self.step_id = step_id
        self.description = description
        self.assigned_role = assigned_role
        self.is_completed = False
        self.result: Optional[str] = None


class ExecutionPlanner:
    """Разбива голяма цел на подзадачи и управлява последователността им."""
    def __init__(self):
        pass

    def create_plan(self, high_level_goal: str) -> List[TaskStep]:
        """Генерира последователни стъпки според целта."""
        # Автоматична базова декомпозиция
        plan = [
            TaskStep(1, f"Извличане на факти и правила за: {high_level_goal}", AgentRole.RESEARCHER),
            TaskStep(2, f"Генериране на решение/съдържание за: {high_level_goal}", AgentRole.CREATIVE),
            TaskStep(3, "Проверка за съвместимост с правилата на проекта", AgentRole.RULE_CHECKER),
            TaskStep(4, "Финален критика и валидация на отговора", AgentRole.CRITIC)
        ]
        return plan


# ==========================================
# AP-092: Conflict Resolution & Internal Review Loop
# ==========================================
class ReviewLoopManager:
    """Управлява автоматичната проверка между Изпълнител и Критик."""
    def __init__(self, max_retries: int = 2):
        self.max_retries = max_retries

    def evaluate_output(self, generated_output: str, critic_feedback: str) -> bool:
        """Оценява дали отговорът е одобрен от Критика."""
        # Ако критикът съдържа думи за одобрение, приемаме отговора
        approval_keywords = ["одобрено", "валидно", "няма грешки", "ok", "approved"]
        is_approved = any(word in critic_feedback.lower() for word in approval_keywords)
        return is_approved
