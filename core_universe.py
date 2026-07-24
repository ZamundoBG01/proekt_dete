import uuid
from enum import Enum
from typing import Dict, Any, List, Optional

# ==========================================
# AP-010: Workspace Isolation & Multi-Tenancy
# ==========================================
class WorkspaceContext:
    """Управлява изолацията между различните проекти."""
    def __init__(self, workspace_id: str):
        self.workspace_id = workspace_id

    def apply_workspace_filter(self, query_dict: dict) -> dict:
        """Гарантира, че всяка заявка търси само в текущия проект."""
        query_dict["workspace_id"] = self.workspace_id
        return query_dict


# ==========================================
# AP-011: Universal Base Object Schema
# ==========================================
class KnowledgeStatus(Enum):
    FACT = "fact"          # Потвърден факт
    HYPOTHESIS = "hypothesis"  # Хипотеза/Проучва се
    RULE = "rule"          # Задължително правило на света


class BaseObject:
    """Универсален базов клас за всеки обект в системата."""
    def __init__(
        self, 
        name: str, 
        obj_type: str, 
        workspace_id: str, 
        data: Optional[Dict[str, Any]] = None,
        status: KnowledgeStatus = KnowledgeStatus.FACT,
        object_id: Optional[str] = None
    ):
        self.id = object_id if object_id else str(uuid.uuid4())
        self.name = name
        self.type = obj_type
        self.workspace_id = workspace_id
        self.status = status
        self.data = data if data is not None else {}

    def to_dict(self) -> dict:
        """Преобразува обекта в речник за лесно запазване/изпращане."""
        return {
            "id": self.id,
            "name": self.name,
            "type": self.type,
            "workspace_id": self.workspace_id,
            "status": self.status.value,
            "data": self.data
        }


# ==========================================
# AP-012: Graph Link Protocol
# ==========================================
class GraphLink:
    """Дефинира връзка между два обекта в графа."""
    def __init__(
        self, 
        source_id: str, 
        target_id: str, 
        relation_type: str, 
        weight: float = 1.0,
        workspace_id: str = "default"
    ):
        self.link_id = str(uuid.uuid4())
        self.source_id = source_id
        self.target_id = target_id
        self.relation_type = relation_type  # напр. "OWNS", "LOCATED_IN", "FRIEND_WITH"
        self.weight = weight
        self.workspace_id = workspace_id

    def to_dict(self) -> dict:
        return {
            "link_id": self.link_id,
            "source_id": self.source_id,
            "target_id": self.target_id,
            "relation_type": self.relation_type,
            "weight": self.weight,
            "workspace_id": self.workspace_id
        }


# ==========================================
# AP-013: Timeline & Versioning Engine
# ==========================================
class TimelineManager:
    """Управлява алтернативни времеви линии и 'Какво ако?' сценарии."""
    def __init__(self, workspace_id: str, main_timeline_name: str = "Main"):
        self.workspace_id = workspace_id
        self.active_timeline = main_timeline_name
        self.timelines: Dict[str, List[dict]] = {main_timeline_name: []}

    def create_branch(self, parent_timeline: str, new_timeline_name: str):
        """Създава разклонение (алтернативна сюжетна линия/сценарий)."""
        if parent_timeline in self.timelines:
            # Копираме състоянието от бащината линия в новата
            self.timelines[new_timeline_name] = list(self.timelines[parent_timeline])
            print(f" Timeline '{new_timeline_name}' created from '{parent_timeline}'")
        else:
            raise ValueError(f"Timeline '{parent_timeline}' does not exist.")

    def switch_timeline(self, timeline_name: str):
        """Превключва активната линия."""
        if timeline_name in self.timelines:
            self.active_timeline = timeline_name
        else:
            raise ValueError(f"Timeline '{timeline_name}' does not exist.")
