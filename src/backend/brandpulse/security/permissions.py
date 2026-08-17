"""固定三角色的权限定义；后端是唯一授权来源。"""
from __future__ import annotations

from typing import Final, FrozenSet

ROLE_ADMIN: Final = "admin"
ROLE_OPERATOR: Final = "operator"
ROLE_VIEWER: Final = "viewer"
VALID_ROLES: Final = frozenset({ROLE_ADMIN, ROLE_OPERATOR, ROLE_VIEWER})

BUSINESS_READ: Final = "business.read"
ACCOUNT_SELF: Final = "account.self"
AGENT_QUERY: Final = "agent.query"
AGENT_OPERATE: Final = "agent.operate"
CRAWL_EXECUTE: Final = "crawl.execute"
MONITORING_MANAGE: Final = "monitoring.manage"
GOVERNANCE_MANAGE: Final = "governance.manage"
FORMULA_MANAGE: Final = "formula.manage"
ALERT_MANAGE: Final = "alert.manage"
REPORT_GENERATE: Final = "report.generate"
OPPORTUNITY_MANAGE: Final = "opportunity.manage"
CASE_MANAGE: Final = "case.manage"
OPERATIONS_IMPORT: Final = "operations.import"
ML_MANAGE: Final = "ml.manage"
AUDIT_READ: Final = "audit.read"
SYSTEM_MANAGE: Final = "system.manage"
USER_MANAGE: Final = "user.manage"

VIEWER_PERMISSIONS: Final[FrozenSet[str]] = frozenset({
    BUSINESS_READ,
    ACCOUNT_SELF,
    AGENT_QUERY,
})
OPERATOR_PERMISSIONS: Final[FrozenSet[str]] = frozenset({
    *VIEWER_PERMISSIONS,
    AGENT_OPERATE,
    CRAWL_EXECUTE,
    MONITORING_MANAGE,
    GOVERNANCE_MANAGE,
    FORMULA_MANAGE,
    ALERT_MANAGE,
    REPORT_GENERATE,
    OPPORTUNITY_MANAGE,
    CASE_MANAGE,
    OPERATIONS_IMPORT,
    ML_MANAGE,
})
ADMIN_PERMISSIONS: Final[FrozenSet[str]] = frozenset({
    *OPERATOR_PERMISSIONS,
    AUDIT_READ,
    SYSTEM_MANAGE,
    USER_MANAGE,
})

ROLE_PERMISSIONS: Final[dict[str, FrozenSet[str]]] = {
    ROLE_ADMIN: ADMIN_PERMISSIONS,
    ROLE_OPERATOR: OPERATOR_PERMISSIONS,
    ROLE_VIEWER: VIEWER_PERMISSIONS,
}

BUSINESS_AGENT_TOOLS: Final[FrozenSet[str]] = frozenset({
    "list_monitoring_scopes",
    "get_scope_snapshot_evidence",
    "get_brand_evidence",
    "list_opportunity_evidence",
    "list_data_quality_evidence",
    "list_business_case_evidence",
    "external_research",
})
ADMIN_DEBUG_AGENT_TOOLS: Final[FrozenSet[str]] = frozenset({"query_db", "list_tables"})


def permissions_for_role(role: str) -> FrozenSet[str]:
    """未知角色没有任何权限，调用方必须显式拒绝。"""
    return ROLE_PERMISSIONS.get(role, frozenset())


def has_permission(role: str, permission: str) -> bool:
    return permission in permissions_for_role(role)


def agent_tools_for_role(role: str, *, advanced: bool = False) -> FrozenSet[str]:
    """普通业务问答只暴露语义化证据工具；自由 SQL 仅管理员高级诊断可用。"""
    if role in {ROLE_ADMIN, ROLE_OPERATOR, ROLE_VIEWER}:
        return BUSINESS_AGENT_TOOLS | (ADMIN_DEBUG_AGENT_TOOLS if advanced and role == ROLE_ADMIN else frozenset())
    return frozenset()


def permission_for_request(method: str, path: str) -> str | None:
    """受保护路由的唯一白名单。None 表示未登记，调用方必须拒绝。"""
    method = method.upper()
    path = path.rstrip("/") or "/"

    if path in {"/api/dashboard", "/api/v1/dashboard"} or path.startswith("/api/v1/dashboard/"):
        return BUSINESS_READ
    if path.startswith("/api/v1/brands"):
        return CRAWL_EXECUTE if method == "POST" and path.endswith("/crawl") else BUSINESS_READ
    if path.startswith("/api/v1/crawl_jobs"):
        return CRAWL_EXECUTE if method == "POST" else BUSINESS_READ
    if path.startswith("/api/v1/indicators") or path.startswith("/api/v1/tables"):
        return BUSINESS_READ
    if path.startswith("/api/v1/metrics"):
        return BUSINESS_READ if method == "GET" else MONITORING_MANAGE
    if path.startswith("/api/v1/chat"):
        return AGENT_QUERY
    if path.startswith("/api/v1/agent"):
        return AGENT_OPERATE if method == "POST" and path.endswith("/execute") else AGENT_QUERY
    if path.startswith("/api/v1/formulas"):
        return BUSINESS_READ if method == "GET" else FORMULA_MANAGE
    if path.startswith("/api/v1/data-governance"):
        return BUSINESS_READ if method == "GET" else GOVERNANCE_MANAGE
    if path.startswith("/api/v1/monitoring"):
        return BUSINESS_READ if method == "GET" else MONITORING_MANAGE
    if path.startswith("/api/v1/snapshots"):
        return BUSINESS_READ if method == "GET" else MONITORING_MANAGE
    if path.startswith("/api/v1/alerts"):
        return BUSINESS_READ if method == "GET" else ALERT_MANAGE
    if path.startswith("/api/v1/opportunities"):
        return BUSINESS_READ if method == "GET" else OPPORTUNITY_MANAGE
    if path.startswith("/api/v1/cases"):
        return BUSINESS_READ if method == "GET" else CASE_MANAGE
    if path.startswith("/api/v1/reports"):
        return BUSINESS_READ if method == "GET" else REPORT_GENERATE
    if path.startswith("/api/v1/operations"):
        return BUSINESS_READ if method == "GET" else OPERATIONS_IMPORT
    if path.startswith("/api/v1/ml"):
        return BUSINESS_READ if method == "GET" else ML_MANAGE
    if path.startswith("/api/v1/audit"):
        return AUDIT_READ
    if path.startswith("/api/v1/system/configuration"):
        return SYSTEM_MANAGE
    if path == "/api/v1/users/me/permissions":
        return ACCOUNT_SELF
    if path.startswith("/api/v1/users"):
        return USER_MANAGE
    if path in {
        "/api/v1/auth/me",
        "/api/v1/auth/logout",
        "/api/v1/auth/change-password",
    }:
        return ACCOUNT_SELF
    return None
