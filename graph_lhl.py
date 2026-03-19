import json
from typing import Optional
from langgraph.graph import StateGraph, END
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field

# 导入咱们前两步写好的 State、数据结构和底层 Tools
from schema import AgentState, JobInfo
from tools import search_jobs_api, scrape_job_detail_api

# 1. 初始化大模型 (请替换为你自己的 API_KEY 和 模型名称)
llm = ChatOpenAI(
    model="qwen3.5-35b-a3b", 
    temperature=0.2, # 规划和判断任务，温度设低一点，保证严谨
    api_key="sk-9fdd123439314a459d37a7e0ae6cf7da", 
    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1"
)

# ==========================================
# 专门为 LLM 设计的两个“结构化思维模型”
# ==========================================
class SearchStrategy(BaseModel):
    """用于 Planner 节点：让 LLM 输出下一步的搜索策略"""
    platform: str = Field(description="选择的招聘平台，必须从 '牛客网' 或 '实习僧' 中选择")
    query: str = Field(description="搜索关键词，如 'AI Engineer 校招', '大模型算法实习'")

class JobEvaluation(BaseModel):
    """用于 Executor 节点：让 LLM 进行语义判断（面试核心加分项）"""
    is_match: bool = Field(description="该岗位是否为AI/机器学习方向，且面向校招/应届/实习？")
    reason: str = Field(description="给出判断理由，为什么匹配或不匹配？")
    job_info: Optional[JobInfo] = Field(None, description="如果 is_match 为 true，则提取结构化岗位信息；如果为 false，则传 null")


# ==========================================
# 节点 1：规划节点 (Planner Node)
# 职责：根据当前进度和历史经验，决定下一步动作
# ==========================================
def planner_node(state: AgentState):
    print("\n🧠 [Planner Node] 大脑正在规划搜索策略...")
    history = state.get("search_history", [])
    current_count = len(state.get("jobs", []))
    # 动态读取用户的要求和目标数量
    user_req = state.get("user_requirement", "AI Engineer 实习生")
    target_count = state.get("target_count", 3)

    # 巧妙的 Prompt 设计：赋予角色、告知现状、避免重复
    prompt = ChatPromptTemplate.from_messages([
        ("system", "你是顶级的 AI 招聘猎头。用户的求职要求是：\n【{user_req}】\n"
                   "你的目标是寻找 {target_count} 个完全符合上述要求的岗位。\n"
                   "目前你已成功收集：{current_count} 个岗位。\n"
                   "你之前尝试过的 [平台-关键词] 组合记录如下：{history}\n"
                   "请结合历史经验，决定下一步的搜索平台和关键词。务必避开已经失败或毫无收获的组合！\n"
                   "注意：你制定的关键词必须紧扣用户的求职要求！"),
        ("user", "请以 JSON 格式输出下一步策略。必须直接输出包含 'platform' 和 'query' 的扁平 JSON 对象，绝对不要在外面嵌套 'SearchStrategy' 这个键名！")
    ])
    
    chain = prompt | llm.with_structured_output(SearchStrategy)
    # 把动态变量传给大模型
    strategy = chain.invoke({
        "user_req": user_req, 
        "target_count": target_count,
        "current_count": current_count, 
        "history": history
    })
    
    print(f"   🎯 制定策略 => 准备前往 [{strategy.platform}] 搜索关键词 [{strategy.query}]")
    
    # 将新的策略更新到状态中
    return {
        "current_platform": strategy.platform,
        "current_query": strategy.query,
        "search_history": [{strategy.platform: strategy.query}] # 存入历史防止死循环
    }

# ==========================================
# 节点 2：执行与评估节点 (Executor Node)
# 职责：调用工具搜索 -> 抓取网页 -> 语义判别 -> 数据清洗
# ==========================================
def executor_node(state: AgentState):
    print("\n⚙️ [Executor Node] 正在执行抓取与审核动作...")
    platform = state.get("current_platform")
    query = state.get("current_query")
    visited = state.get("visited_urls", set())
    
    # 【核心修复 1：全局去重集合】获取所有已存在于最终名单中的 URL
    existing_job_urls = {job.job_url for job in state.get("jobs", [])}
    
    search_result_str = search_jobs_api.invoke({"query": query, "platform": platform})
    try:
        search_results = json.loads(search_result_str)
    except:
        search_results = []
        
    if isinstance(search_results, dict) and "error" in search_results:
        print(f"   ❌ 工具报错: {search_results['error']}")
        return {"error_count": state.get("error_count", 0) + 1} 
        
    new_jobs = []
    newly_visited = set()
    user_req = state.get("user_requirement", "AI/算法相关实习")
    
    eval_prompt = ChatPromptTemplate.from_messages([
        ("system", "你是一个极其严格的招聘数据清洗专家。请评估职位描述(JD)是否符合用户要求：\n"
                   "【求职者要求】：{user_req}\n\n"
                   "【数据清洗与强制规范】:\n"
                   "1. 必须以 JSON 格式直接扁平输出 'is_match', 'reason', 'job_info'。\n"
                   "2. 'job_info' 内部键名必须为原生英文(title, company, location, salary, tech_tags, requirements, source, job_url)，绝不翻译。\n"
                   "3. 如果含有非AI/社招等不符合要求的元素，直接判定为不匹配！"),
        ("user", "岗位链接：{url}\n\n职位描述：\n{jd_text}")
    ])
    eval_chain = eval_prompt | llm.with_structured_output(JobEvaluation)
    
    for item in search_results:
        url = item.get("job_url")
        
        # 【核心修复 2：步骤 6 全局去重拦截】
        # 如果爬过，或者已经存在于最终岗位库中，坚决跳过！
        if not url or url in visited or url in newly_visited or url in existing_job_urls:
            print(f"   ⏭️ [去重机制] {url} 已处理过，跳过。")
            continue
            
        newly_visited.add(url)
        print(f"   🕷️ 正在深度抓取: {item.get('title')} ({url})")
        jd_text = scrape_job_detail_api.invoke({"job_url": url})
        
        print(f"   ⚖️ 正在进行语义审查与技术栈提取...⏳")
        try:
            eval_res = eval_chain.invoke({"user_req": user_req, "url": url, "jd_text": jd_text})
            if eval_res.is_match and eval_res.job_info:
                print(f"   ✅ [审核通过] {eval_res.reason}")
                new_jobs.append(eval_res.job_info)
            else:
                print(f"   🛑 [审核拦截] {eval_res.reason}")
        except Exception as e:
            print(f"   ⚠️ [审核异常] 解析失败: {e}")
            continue 

    if not new_jobs:
        print("   ⚠️ 本轮颗粒无收，将触发换词或换平台机制。")
        return {"visited_urls": newly_visited, "error_count": state.get("error_count", 0) + 1}
    else:
        print(f"   🎉 本轮斩获 {len(new_jobs)} 个有效岗位！")
        return {"jobs": new_jobs, "visited_urls": newly_visited, "error_count": 0}

# ==========================================
# 边缘路由：反思循环控制器 (Conditional Edge)
# 职责：判断是该结束，还是打回重新规划
# ==========================================
def route_condition(state: AgentState):
    current_count = len(state.get("jobs", []))
    errors = state.get("error_count", 0)
    
    # 👇 从状态机里动态读取用户想要收集的数量
    TARGET = state.get("target_count", 3) 
    
    if current_count >= TARGET:
        print(f"\n🏁 [系统判断] 目标达成！已收集 {current_count} 个岗位，任务圆满结束。")
        return "end"
        
    if errors >= 3:
        # 解决面试官追问 4：连续报错怎么办？触发熔断！
        print(f"\n💀 [系统判断] 连续失败 {errors} 次，触发防死循环熔断保护。强制结束。")
        return "end"
        
    print(f"\n🔄 [系统判断] 当前 {current_count}/{TARGET}，进度不足，重定向至 Planner 进行新一轮规划...")
    return "continue"

# ==========================================
# 组装超级图 (Build LangGraph)
# ==========================================
workflow = StateGraph(AgentState)

# 1. 添加节点
workflow.add_node("planner", planner_node)
workflow.add_node("executor", executor_node)

# 2. 定义起点
workflow.set_entry_point("planner")

# 3. 规划完毕后，必定走向执行
workflow.add_edge("planner", "executor")

# 4. 执行完毕后，进行条件判断 (循环的核心)
workflow.add_conditional_edges(
    "executor",
    route_condition,
    {
        "end": END,          # 如果达成目标或报错超限，走向结束
        "continue": "planner" # 如果没搜够，滚回 Planner 重新思考
    }
)

# 5. 编译成可执行的 Application
app = workflow.compile()