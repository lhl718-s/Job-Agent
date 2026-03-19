#####  定义 数据结构 和状态机 
from typing import List, Set, Dict, Annotated
from typing_extensions import TypedDict
from pydantic import BaseModel, Field
import operator

# ==========================================
# 第一部分：Pydantic 结构化输出模型
# ==========================================
class JobInfo(BaseModel):
    """单条岗位信息的标准数据结构"""
    title: str = Field(..., description="职位名称")
    company: str = Field(..., description="公司名称")
    location: str = Field(..., description="工作地点")
    salary: str = Field(..., description="薪资范围")
    # 技术栈作为列表存储，完美契合“LLM 技术栈识别”加分项
    tech_tags: List[str] = Field(default_factory=list, description="技术关键词(如LLM/CV/NLP/推荐系统)")
    requirements: str = Field(..., description="岗位核心技能摘要")
    source: str = Field(..., description="招聘网站")
    job_url: str = Field(..., description="岗位链接")

# ==========================================
# 第二部分：LangGraph Agent 状态机记忆层
# ==========================================
class AgentState(TypedDict):
    """
    Agent 在运行过程中的全局状态。
    使用 Annotated 和 operator 意味着这些字段在图的流转中是“追加(Append)”而不是“覆盖(Overwrite)”。
    """
    user_requirements: str 

    target_count :int
    # 1. 核心目标数据：收集到的有效岗位列表
    jobs: Annotated[List[JobInfo], operator.add]
    
    # 2. 去重与防死循环核心：记录已经爬取过的岗位链接
    visited_urls: Annotated[Set[str], operator.or_]
    
    # 3. 策略状态：当前正在使用的搜索关键词 (如 "AI Engineer 校招")
    current_query: str
    
    # 4. 策略状态：当前正在搜索的招聘平台 (如 "牛客网", "实习僧")
    current_platform: str
    
    # 5. 记忆轨迹：记录已经尝试过的 [平台+关键词] 组合，防止 Agent 在同一个地方反复横跳
    search_history: Annotated[List[Dict[str, str]], operator.add]
    
    # 6. Fallback 触发器：记录连续失败（如搜不到新岗位或解析出错）的次数
    error_count: int