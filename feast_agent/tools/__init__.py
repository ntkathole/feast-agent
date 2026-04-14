"""Feast Agent tools — LangChain tool wrappers around the Feast SDK."""

from feast_agent.tools.auth import get_auth_tools
from feast_agent.tools.inspect import get_inspect_tools
from feast_agent.tools.registry import get_registry_tools
from feast_agent.tools.feature_views import get_feature_view_tools
from feast_agent.tools.transformations import get_transformation_tools
from feast_agent.tools.materialize import get_materialize_tools
from feast_agent.tools.validate import get_validate_tools
from feast_agent.tools.optimize import get_optimize_tools


def get_all_tools(store):
    """Return every tool, bound to the given FeatureStore instance."""
    return [
        *get_auth_tools(store),
        *get_inspect_tools(store),
        *get_registry_tools(store),
        *get_feature_view_tools(store),
        *get_transformation_tools(store),
        *get_materialize_tools(store),
        *get_validate_tools(store),
        *get_optimize_tools(store),
    ]


__all__ = ["get_all_tools"]
