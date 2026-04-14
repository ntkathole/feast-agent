"""Tools for inspecting and managing Feast RBAC permissions."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from langchain_core.tools import tool

from feast import FeatureStore


def get_auth_tools(store: FeatureStore) -> list:
    """Return all auth/RBAC tools bound to *store*."""

    @tool
    def get_auth_status() -> Dict[str, Any]:
        """Show the current authentication and authorization configuration:
        auth type, whether RBAC permissions are registered, and connectivity mode
        (local vs remote registry)."""
        config = store.config

        auth_info: Dict[str, Any] = {
            "auth_type": getattr(config, "auth", {}).get("type", "no_auth")
            if isinstance(getattr(config, "auth", None), dict)
            else str(getattr(getattr(config, "auth_config", None), "type", "no_auth")),
            "project": config.project,
            "provider": config.provider,
        }

        reg = config.registry
        if isinstance(reg, str):
            auth_info["registry_type"] = "file"
            auth_info["registry_path"] = reg
        elif hasattr(reg, "registry_type"):
            auth_info["registry_type"] = reg.registry_type
            if hasattr(reg, "path"):
                auth_info["registry_path"] = reg.path

        try:
            permissions = store.list_permissions()
            auth_info["permissions_count"] = len(permissions)
            auth_info["permissions"] = [p.name for p in permissions]
            auth_info["rbac_active"] = len(permissions) > 0
        except Exception:
            auth_info["permissions_count"] = 0
            auth_info["rbac_active"] = False
            auth_info["note"] = "Could not list permissions (may not be supported by this registry)."

        return auth_info

    @tool
    def list_permissions() -> Dict[str, Any]:
        """List all RBAC permissions registered in the Feast feature store.
        Each permission defines which actions are allowed on which resource
        types, controlled by a policy (role, group, or namespace-based)."""
        try:
            permissions = store.list_permissions()
        except Exception as e:
            return {"error": f"Failed to list permissions: {e}"}

        if not permissions:
            return {
                "count": 0,
                "message": "No permissions registered. When RBAC is active, "
                "this means all access is DENIED by default.",
            }

        result = []
        for perm in permissions:
            entry: Dict[str, Any] = {
                "name": perm.name,
                "types": [t.__name__ for t in perm.types] if hasattr(perm, "types") else [],
                "actions": [a.value for a in perm.actions] if hasattr(perm, "actions") else [],
                "tags": dict(getattr(perm, "tags", {})),
            }

            if hasattr(perm, "name_patterns") and perm.name_patterns:
                entry["name_patterns"] = list(perm.name_patterns)

            if hasattr(perm, "policy"):
                policy = perm.policy
                policy_info: Dict[str, Any] = {"type": type(policy).__name__}
                if hasattr(policy, "roles"):
                    policy_info["roles"] = list(policy.roles)
                if hasattr(policy, "groups"):
                    policy_info["groups"] = list(policy.groups)
                if hasattr(policy, "namespaces"):
                    policy_info["namespaces"] = list(policy.namespaces)
                entry["policy"] = policy_info

            result.append(entry)

        return {"count": len(result), "permissions": result}

    @tool
    def describe_permission(name: str) -> Dict[str, Any]:
        """Describe a specific RBAC permission in detail.

        Args:
            name: Name of the permission to describe.
        """
        try:
            perm = store.get_permission(name)
        except Exception as e:
            return {"error": f"Permission '{name}' not found: {e}"}

        info: Dict[str, Any] = {
            "name": perm.name,
            "types": [t.__name__ for t in perm.types] if hasattr(perm, "types") else [],
            "actions": [a.value for a in perm.actions] if hasattr(perm, "actions") else [],
            "tags": dict(getattr(perm, "tags", {})),
        }

        if hasattr(perm, "name_patterns") and perm.name_patterns:
            info["name_patterns"] = list(perm.name_patterns)
        if hasattr(perm, "required_tags") and perm.required_tags:
            info["required_tags"] = dict(perm.required_tags)

        if hasattr(perm, "policy"):
            policy = perm.policy
            policy_info: Dict[str, Any] = {"type": type(policy).__name__}
            if hasattr(policy, "roles"):
                policy_info["roles"] = list(policy.roles)
            if hasattr(policy, "groups"):
                policy_info["groups"] = list(policy.groups)
            if hasattr(policy, "namespaces"):
                policy_info["namespaces"] = list(policy.namespaces)
            info["policy"] = policy_info

        return info

    @tool
    def create_permission(
        name: str,
        actions: List[str],
        resource_types: Optional[List[str]] = None,
        name_patterns: Optional[List[str]] = None,
        roles: Optional[List[str]] = None,
        groups: Optional[List[str]] = None,
        namespaces: Optional[List[str]] = None,
        tags: Optional[Dict[str, str]] = None,
    ) -> str:
        """Create and register an RBAC permission.

        Args:
            name: Unique name for the permission.
            actions: List of allowed actions. Valid values: CREATE, DESCRIBE,
                UPDATE, DELETE, READ_ONLINE, READ_OFFLINE, WRITE_ONLINE,
                WRITE_OFFLINE.
            resource_types: Optional list of Feast object types this applies to.
                Valid: FeatureView, OnDemandFeatureView, StreamFeatureView,
                BatchFeatureView, Entity, DataSource, FeatureService.
                If omitted, applies to all types.
            name_patterns: Optional regex patterns — resource name must match
                at least one.
            roles: Roles that satisfy this permission (RoleBasedPolicy).
            groups: Groups that satisfy this permission (GroupBasedPolicy).
            namespaces: Namespaces that satisfy this permission.
            tags: Optional metadata tags on the permission itself.
        """
        from feast.permissions.action import AuthzedAction
        from feast.permissions.permission import Permission
        from feast.permissions.policy import AllowAll, RoleBasedPolicy

        action_map = {a.name.lower(): a for a in AuthzedAction}
        resolved_actions = []
        for a in actions:
            key = a.strip().lower()
            if key not in action_map:
                return f"Error: Unknown action '{a}'. Valid: {sorted(action_map.keys())}"
            resolved_actions.append(action_map[key])

        resolved_types = None
        if resource_types:
            import feast
            type_map = {
                "featureview": feast.FeatureView,
                "ondemandfeatureview": feast.OnDemandFeatureView,
                "streamfeatureview": feast.StreamFeatureView,
                "batchfeatureview": feast.BatchFeatureView,
                "entity": feast.Entity,
                "featureservice": feast.FeatureService,
            }
            resolved_types = []
            for rt in resource_types:
                key = rt.strip().lower().replace("_", "")
                if key not in type_map:
                    return f"Error: Unknown resource type '{rt}'. Valid: {sorted(type_map.keys())}"
                resolved_types.append(type_map[key])

        if roles:
            policy = RoleBasedPolicy(roles=roles)
        elif groups:
            from feast.permissions.policy import GroupBasedPolicy
            policy = GroupBasedPolicy(groups=groups)
        elif namespaces:
            from feast.permissions.policy import NamespaceBasedPolicy
            policy = NamespaceBasedPolicy(namespaces=namespaces)
        else:
            policy = AllowAll()

        kwargs: dict = {
            "name": name,
            "actions": resolved_actions,
            "policy": policy,
            "tags": tags or {},
        }
        if resolved_types:
            kwargs["types"] = resolved_types
        if name_patterns:
            kwargs["name_patterns"] = name_patterns

        perm = Permission(**kwargs)
        store.apply([perm])

        policy_desc = type(policy).__name__
        if hasattr(policy, "roles"):
            policy_desc += f" (roles={list(policy.roles)})"
        elif hasattr(policy, "groups"):
            policy_desc += f" (groups={list(policy.groups)})"

        return (
            f"Created Permission '{name}': actions={[a.name for a in resolved_actions]}, "
            f"policy={policy_desc}."
        )

    @tool
    def check_connectivity() -> Dict[str, Any]:
        """Verify that the agent can connect to the Feast registry and report
        connection details. Useful for diagnosing remote connectivity issues."""
        config = store.config

        result: Dict[str, Any] = {
            "project": config.project,
            "provider": config.provider,
        }

        reg = config.registry
        if isinstance(reg, str):
            result["registry_type"] = "file"
            result["registry_path"] = reg
        elif hasattr(reg, "registry_type"):
            result["registry_type"] = reg.registry_type
            if hasattr(reg, "path"):
                result["registry_url"] = reg.path
            if hasattr(reg, "is_tls"):
                result["tls"] = reg.is_tls

        try:
            sources = store.list_data_sources()
            result["connected"] = True
            result["data_sources_found"] = len(sources)
        except Exception as e:
            result["connected"] = False
            result["error"] = str(e)

        auth_type = "no_auth"
        try:
            auth_config = config.auth_config
            auth_type = str(getattr(auth_config, "type", "no_auth"))
        except Exception:
            pass
        result["auth_type"] = auth_type

        return result

    return [
        get_auth_status,
        list_permissions,
        describe_permission,
        create_permission,
        check_connectivity,
    ]
