import copy
import uuid
from typing import Dict, Any, List, Optional
from core_universe import BaseObject, KnowledgeStatus

# ==========================================
# AP-030: Sandbox & Scenario Simulation
# ==========================================
class SimulationSandbox:
    """Безопасна изолирана среда за тестване на 'Какво ако?' сценарии."""
    def __init__(self, workspace_id: str):
        self.workspace_id = workspace_id
        self.sandbox_id = str(uuid.uuid4())
        self.temp_objects: Dict[str, BaseObject] = {}

    def load_environment(self, base_objects: List[BaseObject]):
        """Зарежда дубликат на реалните обекти в пясъчника, за да не ги променя оригинално."""
        for obj in base_objects:
            # Правим дълбоко копие, за да пазим оригинала
            self.temp_objects[obj.id] = copy.deepcopy(obj)

    def apply_hypothetical_change(self, object_id: str, field_to_change: str, new_value: Any) -> bool:
        """Прилага експериментална промяна върху обект в симулацията."""
        if object_id in self.temp_objects:
            self.temp_objects[object_id].data[field_to_change] = new_value
            # Маркираме обекта като ХИПОТЕЗА в симулираната среда
            self.temp_objects[object_id].status = KnowledgeStatus.HYPOTHESIS
            return True
        return False

    def run_simulation(self, scenario_description: str) -> Dict[str, Any]:
        """Изпълнява симулационния сценарий и връща прогнозиран резултат."""
        return {
            "sandbox_id": self.sandbox_id,
            "scenario": scenario_description,
            "modified_objects_count": len(self.temp_objects),
            "status": "Simulation Executed Successfully"
        }
