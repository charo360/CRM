"""AI Assistant module — conversational agent with tool-use over CRM actions."""
from .orchestrator import run_turn
from .models import list_available_models, DEFAULT_MODEL

__all__ = ["run_turn", "list_available_models", "DEFAULT_MODEL"]
