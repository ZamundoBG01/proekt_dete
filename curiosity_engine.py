import uuid
from typing import List, Dict, Any
from core_universe import BaseObject, GraphLink

# ==========================================
# AP-080: Gap Detection & Proactive Curiosity
# ==========================================
class CuriosityEngine:
    """Модул за откриване на празнини в знанията и генериране на въпроси."""
    def __init__(self, workspace_id: str):
        self.workspace_id = workspace_id
        self.gap_queue: List[Dict[str, Any]] = []

    def scan_for_orphans(self, objects: List[BaseObject], links: List[GraphLink]) -> List[Dict[str, Any]]:
        """Открива 'изолирани' обекти (Orphans), които нямат връзки с нищо друго."""
        connected_ids = set()
        for link in links:
            connected_ids.add(link.source_id)
            connected_ids.add(link.target_id)

        orphans = []
        for obj in objects:
            if obj.id not in connected_ids:
                gap = {
                    "gap_id": str(uuid.uuid4()),
                    "object_id": obj.id,
                    "object_name": obj.name,
                    "type": "ORPHAN_NODE",
                    "suggestion": f"Обектът '{obj.name}' няма свързани факти или релации. Искате ли да добавим връзка?"
                }
                orphans.append(gap)
                self.gap_queue.append(gap)

        return orphans

    def get_proactive_proposals(self) -> List[Dict[str, Any]]:
        """Връща списък с въпроси/предложения за потребителя."""
        return self.gap_queue
