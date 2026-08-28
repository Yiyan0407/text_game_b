"""向后兼容：StateAgent 现为 WorldStateAgent 别名。"""

from chain.world_state_agent import WorldStateAgent

StateAgent = WorldStateAgent

__all__ = ["StateAgent", "WorldStateAgent"]
