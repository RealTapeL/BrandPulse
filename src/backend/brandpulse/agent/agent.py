"""
BrandPulse 招商品牌情报 Agent（Pydantic AI）

LLM 走 OpenAI 兼容接口（OpenAIChatModel + OpenAIProvider），
base_url / api_key / model 从 Config 读取（.env 中的 LLM_* 配置）。

Agent 惰性初始化：未配置 LLM_API_KEY 时 import 本模块不报错，
只有真正运行对话时才抛出清晰错误。
"""
from typing import List, Optional, Tuple

from brandpulse.agent import tools
from brandpulse.config.config import Config
from brandpulse.logger.logger import get_logger

logger = get_logger(__name__)

SYSTEM_PROMPT = """你是 BrandPulse 招商品牌情报数据分析助手，服务招商团队的品牌选址与竞品分析。

你可以使用以下工具：
- list_tables：查看数据库主要业务表结构（写 SQL 前先调用）
- query_db：对 PostgreSQL 执行只读 SQL（表：dp_shop_metrics 点评门店、xhs_notes 小红书笔记、brand_heat_daily 热度日聚合、brand_indicators_daily 指标日表）
- run_indicators：刷新口碑/热度/SOV/趋势指标
- crawl：驱动浏览器采集指定商场×品类的点评/小红书数据（约 40 秒）
- external_research：在 Agent-Reach 已启用时读取或搜索公开网页；结果仅作外部研究，不进入指标表

硬性规则：
1. 所有数字必须来自工具返回结果，严禁编造；工具没查到的数据就说"暂无数据"。
2. 回答必须注明数据来源（哪张表 / 哪个工具）。
3. 指标（口碑、热度、SOV、趋势）的含义与口径以 indicators 模块计算结果为准，不要自行发明口径。
4. 用中文回答，结论先行，数据支撑随后。"""
SYSTEM_PROMPT += """
5. external_research 返回的是外部公开资料，不等同于 BrandPulse 内部指标；引用时必须给出 URL 或外部来源。
6. 不要要求用户把 Cookie、Token、密码放进对话；外部平台登录态由用户在本机按 Agent-Reach 文档单独配置。
"""


def build_agent():
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
    return Agent(
        model,
        system_prompt=SYSTEM_PROMPT,
        tools=[
            tools.query_db,
            tools.run_indicators,
            tools.crawl,
            tools.list_tables,
            tools.external_research,
        ],
    )


def ask(question: str, message_history: Optional[List] = None) -> Tuple[str, List]:
    """
    单轮问答。

    Args:
        question: 用户问题
        message_history: 历史消息（多轮对话时传入），None 表示新会话

    Returns:
        (回答文本, 更新后的消息历史)
    """
    agent = build_agent()
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
