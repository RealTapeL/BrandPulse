"""
BrandPulse 招商品牌情报 Agent（Pydantic AI）

LLM 走 OpenAI 兼容接口（OpenAIChatModel + OpenAIProvider），
base_url / api_key / model 从 Config 读取（.env 中的 LLM_* 配置）。

Agent 惰性初始化：未配置 LLM_API_KEY 时 import 本模块不报错，
只有真正运行对话时才抛出清晰错误。
"""
from typing import Iterable, List, Optional, Tuple

from brandpulse.agent import tools
from brandpulse.config.config import Config
from brandpulse.logger.logger import get_logger

logger = get_logger(__name__)

SYSTEM_PROMPT = """你是 BrandPulse 招商品牌情报数据分析助手，服务招商团队的品牌选址与竞品分析。

默认只能调用受控的语义化证据工具：监测范围、可信快照、已确认品牌观测、机会信号、数据质量和业务事项。
普通问答不得自行构造 SQL，也不得把旧 dataset key 当作真实品牌。管理员高级诊断模式才可能提供只读 SQL 工具。

硬性规则：
1. 所有数字必须来自工具返回结果，严禁编造；工具没查到的数据就说"暂无数据"。
2. 每次回答都按以下小节组织：数据事实、系统推断、待人工确认、证据与数据质量。
3. 证据与数据质量必须写明范围（城市×商场×品类）、快照 ID、数据截止时间、来源覆盖/缺失来源、质量等级和指标版本；未调用快照工具时明确写"未取得可信快照"。
4. 公开数据仅可说明公开口碑、公开声量、门店分布和竞争线索，绝不能等同销售、坪效、租户健康度、经营风险或自动招商结论。
5. 趋势只有工具明确提供且满足可比性时才能描述；不要将累计评价/点赞存量说成近期热度。
6. 用中文回答，结论先行。采集、重算、创建告警、生成报告和创建事项都是有副作用动作：不得执行；应说明需要用户在对应页面显式确认。"""
SYSTEM_PROMPT += """
5. external_research 返回的是外部公开资料，不等同于 BrandPulse 内部指标；引用时必须给出 URL 或外部来源。
6. 不要要求用户把 Cookie、Token、密码放进对话；外部平台登录态由用户在本机按 Agent-Reach 文档单独配置。
"""


_AGENT_FUNCTIONS = {
    "list_monitoring_scopes": tools.list_monitoring_scopes,
    "get_scope_snapshot_evidence": tools.get_scope_snapshot_evidence,
    "get_brand_evidence": tools.get_brand_evidence,
    "list_opportunity_evidence": tools.list_opportunity_evidence,
    "list_data_quality_evidence": tools.list_data_quality_evidence,
    "list_business_case_evidence": tools.list_business_case_evidence,
    "query_db": tools.query_db,
    "list_tables": tools.list_tables,
    "external_research": tools.external_research,
}


def build_agent(allowed_tools: Optional[Iterable[str]] = None):
    """
    构建 Pydantic AI Agent（惰性初始化）。

    Raises:
        RuntimeError: 未配置 LLM_API_KEY / LLM_MODEL 时给出清晰提示
    """
    if not Config.LLM_API_KEY:
        raise RuntimeError(
            "未配置 LLM_API_KEY，请在项目根目录 .env 中配置 "
            "LLM_BASE_URL / LLM_API_KEY / LLM_MODEL（参考 .env.example）"
        )
    if not Config.LLM_MODEL:
        raise RuntimeError("未配置 LLM_MODEL，请在 .env 中指定模型名")

    from pydantic_ai import Agent
    from pydantic_ai.models.openai import OpenAIChatModel
    from pydantic_ai.providers.openai import OpenAIProvider

    provider = OpenAIProvider(
        base_url=Config.LLM_BASE_URL or None,
        api_key=Config.LLM_API_KEY,
    )
    model = OpenAIChatModel(Config.LLM_MODEL, provider=provider)
    allowed = set(allowed_tools) if allowed_tools is not None else set(_AGENT_FUNCTIONS)
    selected_tools = [_AGENT_FUNCTIONS[name] for name in _AGENT_FUNCTIONS if name in allowed]
    if not selected_tools:
        raise RuntimeError("当前账号没有可用的 Agent 工具")
    prompt = SYSTEM_PROMPT
    if "query_db" in allowed:
        prompt += "\n当前为管理员高级诊断模式：SQL 仅用于排障，任何业务回答仍应优先使用可信快照语义工具并附上证据。"
    return Agent(
        model,
        system_prompt=prompt,
        tools=selected_tools,
    )


def ask(
    question: str,
    message_history: Optional[List] = None,
    *,
    allowed_tools: Optional[Iterable[str]] = None,
) -> Tuple[str, List]:
    """
    单轮问答。

    Args:
        question: 用户问题
        message_history: 历史消息（多轮对话时传入），None 表示新会话

    Returns:
        (回答文本, 更新后的消息历史)
    """
    agent = build_agent(allowed_tools=allowed_tools)
    result = agent.run_sync(question, message_history=message_history)
    return result.output, result.all_messages()


def chat_interactive() -> None:
    """交互式多轮对话（保持对话历史，输入 exit/quit 退出）"""
    try:
        build_agent()
    except RuntimeError as e:
        print(f"Agent 启动失败: {e}")
        return

    print("BrandPulse 品牌情报助手（输入 exit 或 quit 退出）")
    history: Optional[List] = None
    while True:
        try:
            question = input("\n你: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n再见")
            break
        if not question:
            continue
        if question.lower() in ("exit", "quit"):
            print("再见")
            break
        try:
            answer, history = ask(question, message_history=history)
        except Exception as e:
            logger.error(f"Agent 运行失败: {e}")
            print(f"出错了: {e}")
            continue
        print(f"\n助手: {answer}")
