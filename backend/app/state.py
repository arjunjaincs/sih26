"""
Shared in-process state store for the demo pipeline.
Using a module-level set keeps state simple without requiring a database for MVP.
"""
from app.models.schemas import AttackScenario

# Mutable set of currently active attack scenarios
active_scenarios: set[AttackScenario] = set()
