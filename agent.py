### 引入多线程并发 + 限制审核 Tokens
import json
import concurrent.futures
from typing import Optional
from langgraph.graph import StateGraph, END
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field

# 导入咱们前两步写好的 State、数据结构和底层 Tools
from schema import AgentState, JobInfo
from tools import search_jobs_api, scrape_job_detail_api

# 1. 初始化大模型
llm = ChatOpenAI(
    model="qwen3.5-flash", 
    temperature=0.2, 
    api_key="  ",   #这个是我的密钥
    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1"
)

# ==========================================
# 专门为 LLM 设计的两个“结构化思维模型”
# ==========================================
class SearchStrategy(BaseModel):
    """用于 Planner 节点：让 LLM 输出下一步的搜索策略"""
    platform: str = Field(description="选择的招聘平台，必须从 '牛客网' 或 '实习僧' 中选择，绝对不能自己编造其他平台！")
    # 👇 删除了 AI 相关的误导例子，强调提取核心要素
    query: str = Field(description="必须从用户的原话中提取核心搜索关键词（包含地点、行业、岗位名），例如用户要北京前端，就输出 '北京 前端'")

class JobEvaluation(BaseModel):
    """用于 Executor 节点：让 LLM 进行语义判断"""
    is_match: bool = Field(description="该岗位是否满足用户的全部要求？")
    reason: str = Field(description="给出判断理由")
    # 👇 将嵌套对象全部拉平，化繁为简，专治各种大模型解析报错
    title: str = Field(default="", description="如果匹配，提取职位名称，否则留空")
    company: str = Field(default="", description="如果匹配，提取公司名称，否则留空")
    location: str = Field(default="", description="提取工作地点")
    salary: str = Field(default="", description="提取薪资范围")
    tech_tags: list[str] = Field(default_factory=list, description="提取2-4个技术标签")
    requirements: str = Field(default="", description="提取核心要求摘要")
    source: str = Field(default="", description="提取来源平台")
    job_url: str = Field(default="", description="提取岗位链接")


# ==========================================
# 节点 1：规划节点 (Planner Node)
# 职责：根据当前进度和历史经验，决定下一步动作
# ==========================================
def planner_node(state: AgentState):
    print("\n [Planner Node] 大脑正在规划搜索策略...")
    history = state.get("search_history", [])
    current_count = len(state.get("jobs", []))
    # 动态读取用户的要求和目标数量
    user_req = state.get("user_requirements", "AI Engineer 实习生")
    target_count = state.get("target_count", 3)


    # 巧妙的 Prompt 设计：赋予角色、告知现状、避免重复
    prompt = ChatPromptTemplate.from_messages([
        # 👇 1. 去掉“AI”，变成通用的“招聘搜索专家”
        ("system", "你是顶级的招聘搜索专家。用户的详细求职要求是：\n【{user_req}】\n"
                   "你的目标是寻找 {target_count} 个完全符合上述要求的岗位。\n"
                   "目前你已成功收集：{current_count} 个岗位。\n"
                   "你之前尝试过的 [平台-关键词] 组合记录如下：{history}\n"
                   "请结合历史经验，决定下一步的搜索平台和关键词。\n"
                   "【最高警告】：\n"
                   "1. 你的平台必须且只能从 '牛客网', '实习僧' 中选择！严禁使用 LinkedIn, Indeed 等！\n"
                   # 👇 2. 增加针对地域和特定行业的死命令
                   "2. 生成的 query 必须【绝对忠于用户的输入】！如果用户指定了冷门城市（如内蒙古）或特定行业（如芯片设计），必须把这些词完整放入 query 中，绝不能擅自篡改成其他通用岗位！\n"
                   "3. 如果历史记录中某个组合失败了，必须换一个不同的关键词继续搜索！"),
        ("user", "请以 JSON 格式输出下一步策略。必须直接输出包含 'platform' 和 'query' 的扁平 JSON 对象。")
    ])
    
    chain = prompt | llm.with_structured_output(SearchStrategy)
    # 把动态变量传给大模型
    strategy = chain.invoke({
        "user_req": user_req, 
        "target_count": target_count,
        "current_count": current_count, 
        "history": history
    })
    
    print(f"    制定策略 => 准备前往 [{strategy.platform}] 搜索关键词 [{strategy.query}]")
    
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
    print("\n⚙️ [Executor Node] 正在执行抓取与审核动作 ...")
    platform = state.get("current_platform")
    query = state.get("current_query")
    visited = state.get("visited_urls", set())
    
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
    user_req = state.get("user_requirements", "AI/算法相关实习")
    
    eval_prompt = ChatPromptTemplate.from_messages([
        ("system", "你是一个极其严格的招聘数据清洗专家。请评估职位描述(JD)是否符合用户要求：\n"
                   "【求职者要求】：{user_req}\n\n"
                   "【数据清洗与强制规范】:\n"
                   "1. 必须以 JSON 格式直接输出，且必须是完全扁平的结构！包含：'is_match', 'reason', 'title', 'company', 'location', 'salary', 'tech_tags', 'requirements', 'source', 'job_url'。\n"
                   "2. 绝对不要嵌套！所有字段全都在最外层！如果不匹配，is_match填false；如果匹配，必须提取完整！"),
        ("user", "岗位链接：{url}\n\n职位描述：\n{jd_text}")
    ])

    # 👇 核心修复 1：给审核节点也加上 max_tokens，强行斩断 5 万 Tokens 的发癫行为！
    limited_eval_llm = llm.bind(max_tokens=1024)
    eval_chain = eval_prompt | limited_eval_llm.with_structured_output(JobEvaluation)
    
    # 定义单个岗位的处理函数，方便多线程调用
    def process_single_job(item):
        url = item.get("job_url")
        # 去重拦截
        if not url or url in visited or url in newly_visited or url in existing_job_urls:
            return None, url
            
        print(f"   🕷️ 正在深度抓取: {item.get('title')} ({url})")
        jd_text = scrape_job_detail_api.invoke({"job_url": url})
        
        try:
            eval_res = eval_chain.invoke({"user_req": user_req, "url": url, "jd_text": jd_text})
            if eval_res.is_match:
                print(f"   ✅ [审核通过] {item.get('title')} - {eval_res.reason}")
                extracted_job = JobInfo(
                    title=eval_res.title, company=eval_res.company, location=eval_res.location,
                    salary=eval_res.salary, tech_tags=eval_res.tech_tags, requirements=eval_res.requirements,
                    source=eval_res.source, job_url=eval_res.job_url
                )
                return extracted_job, url
            else:
                print(f"   🛑 [审核拦截] {item.get('title')} - {eval_res.reason}")
                return None, url
        except Exception as e:
            print(f"   ⚠️ [审核异常] {item.get('title')} - 解析失败，已跳过。")
            return None, url


    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        # 将所有搜索结果提交给线程池
        future_to_job = {executor.submit(process_single_job, item): item for item in search_results}
        
        # 收集结果
        for future in concurrent.futures.as_completed(future_to_job):
            job_result, url = future.result()
            if url:
                newly_visited.add(url)
            if job_result:
                new_jobs.append(job_result)

    if not new_jobs:
        print("   ⚠️ 本轮颗粒无收，将触发换词或换平台机制。")
        return {"visited_urls": newly_visited, "error_count": state.get("error_count", 0) + 1}
    else:
        print(f"   🎉 本轮斩获 {len(new_jobs)} 个有效岗位！")
        return {"jobs": new_jobs, "visited_urls": newly_visited, "error_count": 0}



def route_condition(state: AgentState):
    
    current_count = len(state.get("jobs", []))
    errors = state.get("error_count", 0)
    

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
        "end": END,          
        "continue": "planner"
    }
)

# 5. 编译成可执行的 Application
app = workflow.compile()