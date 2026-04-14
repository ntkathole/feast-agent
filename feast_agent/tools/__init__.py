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
        *get_inspect_tools(store),
        *get_auth_tools(store),
        *get_registry_tools(store),
        *get_feature_view_tools(store),
        *get_transformation_tools(store),
        *get_materialize_tools(store),
        *get_validate_tools(store),
        *get_optimize_tools(store),
    ]


def get_core_tools(store):
    """Return a focused subset of tools suitable for smaller LLMs.

    Keeps the tool count low (~15) to avoid overwhelming models like
    llama3.1:8b that struggle with large tool schemas.
    """
    inspect = get_inspect_tools(store)
    auth = get_auth_tools(store)
    materialize = get_materialize_tools(store)
    validate = get_validate_tools(store)
    optimize = get_optimize_tools(store)

    inspect_map = {t.name: t for t in inspect}
    auth_map = {t.name: t for t in auth}
    mat_map = {t.name: t for t in materialize}
    val_map = {t.name: t for t in validate}
    opt_map = {t.name: t for t in optimize}

    return [
        inspect_map["list_all_objects"],
        inspect_map["describe_feature_view"],
        inspect_map["describe_data_source"],
        inspect_map["describe_entity"],
        auth_map["get_auth_status"],
        auth_map["list_permissions"],
        auth_map["create_permission"],
        auth_map["check_connectivity"],
        mat_map["get_materialization_status"],
        mat_map["materialize_incremental"],
        val_map["validate_feature_view_schema"],
        val_map["validate_data_freshness"],
        opt_map["suggest_optimizations"],
    ]


__all__ = ["get_all_tools", "get_core_tools"]
