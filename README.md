# 🚀 Agentic AI 求职助手 (Job-Search Agent)

基于 **LangGraph** 和 **大语言模型 (LLM)** 构建的自动化求职智能体。
本项目模拟了真实的 AI 猎头工作流：能够理解用户的自然语言求职需求，自主规划搜索策略，并发调用工具抓取职位信息，并通过严格的语义判别对数据进行清洗和结构化输出。

## ✨ 核心技术亮点 (面试踩分点)

1. **自主规划与迭代搜索 (Planner-Executor 闭环)**
   - 采用 LangGraph 构建状态机。`Planner` 节点负责提取用户意图并生成检索策略（平台 + 关键词）。
   - 具备 **Self-Correction (自我修正)** 能力：当搜索数量不足时，系统会自动将失败记录存入上下文，并更换关键词触发新一轮的搜索。
2. **多线程并发执行 (High Performance)**
   - 在 `Executor` 节点引入 `ThreadPoolExecutor`，将传统的串行抓取与 LLM 审核优化为 **并发处理**，极大地提升了海量数据下的执行效率。
3. **精准语义清洗 (Semantic Filtering & Structured Output)**
   - 放弃传统的正则匹配，采用 LLM 的 `with_structured_output` 强制输出扁平化 JSON。
   - 严格审查岗位的**地点、技术栈、实习/社招属性**。智能拦截的无效岗位（如：搜算法岗却返回 Java 岗，或搜实习却返回资深专家岗）。
4. **全局去重与熔断保护 (Robustness)**
   - **全局去重**：在 State 中维护 `visited_urls` 和已收集的职位列表，保证同一 URL 绝对不会被重复抓取和消耗 Token。
   - **防死循环熔断**：设置最大错误重试次数（`error_count >= 3`），应对 API 异常或极端偏门需求，保障系统不会陷入无限死循环。
5. **服务降级与人性化交互 (Graceful Degradation)**
   - 当遇到用户提出极度偏门的要求导致“颗粒无收”时，系统能优雅退出，并给出高情商的修改搜索建议。

---

## 📂 项目结构

```text
Job-Agent/
├── main.py            # 主程序入口：负责与用户交互并启动 Agent 图流转
├── agent.py           # 核心逻辑：定义 State、Planner节点、Executor节点及路由条件
├── tools.py           # 工具封装：包含职位搜索 API 和详情页抓取 API
├── schema.py          # 数据模型：定义 AgentState 状态机和 JobInfo 数据结构
├── mock_jobs.json     # 模拟数据库：包含各种岗位及干扰项的海量测试语料
└── README.md          # 项目说明文档

## python main.py
