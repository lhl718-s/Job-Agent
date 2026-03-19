from langchain_core.tools import tool
import json

# ==========================================
# 模拟数据库 (Mock Database)
# ==========================================
# 故意混入非 AI 岗位、非校招岗位，测试 Agent 的“火眼金睛”
MOCK_JD_DATABASE = {
    "job_001": {
        "title": "大模型算法实习生", "company": "字节跳动", "location": "北京", "salary": "400-500/天", 
        "req": "面向2025届毕业生。熟悉Transformer架构，熟练使用PyTorch。有大模型(LLM)微调、RAG开发经验者优先。", 
        "source": "牛客网"
    },
    "job_002": {
        "title": "计算机视觉校招 (CV方向)", "company": "商汤科技", "location": "上海", "salary": "30k-40k/月", 
        "req": "2024/2025届校招。精通目标检测、图像分割等前沿算法，曾在CVPR/ICCV发表论文者优先。", 
        "source": "牛客网"
    },
    "job_003": { # 🛑 陷阱 1：这是一个非 AI 岗位
        "title": "Java后端开发实习生", "company": "美团", "location": "北京", "salary": "300/天", 
        "req": "熟悉Spring Boot框架，掌握MySQL、Redis等数据库操作。主要负责外卖业务后台研发。", 
        "source": "牛客网"
    },
    "job_004": {
        "title": "NLP自然语言处理实习生", "company": "百度", "location": "北京", "salary": "350/天", 
        "req": "熟悉HuggingFace生态，了解大语言模型原理，能使用Python进行数据清洗和模型评测。实习期不少于3个月。", 
        "source": "实习僧"
    },
    "job_005": { # 🛑 陷阱 2：这是一个 AI 岗位，但要求 3 年经验（非校招/实习）
        "title": "资深自动驾驶算法工程师", "company": "小马智行", "location": "广州", "salary": "50k-80k/月", 
        "req": "本科及以上学历，3年以上自动驾驶感知/规划算法落地经验。精通C++和CUDA优化。", 
        "source": "实习僧"
    }
}

# ==========================================
# 工具 1：职位搜索 API
# 对标面试题要求：“能调用搜索工具”
# ==========================================
@tool
def search_jobs_api(query: str, platform: str) -> str:
    """
    在指定的招聘网站上搜索岗位信息。
    参数:
    - query: 搜索关键词 (例如: "AI Engineer", "大模型实习生")
    - platform: 招聘平台名称 (目前仅支持 "牛客网" 或 "实习僧")
    返回: 包含职位基础信息和详情链接(job_url)的 JSON 字符串。
    """
    print(f"\n[Tool 运行中] 🔍 正在 '{platform}' 搜索关键词: '{query}'...")
    
    results = []
    # 简单的模拟搜索逻辑
    if platform == "牛客网":
        results = [
            {"title": "大模型算法实习生", "company": "字节跳动", "job_url": "https://mock.com/job_001"},
            {"title": "计算机视觉校招 (CV方向)", "company": "商汤科技", "job_url": "https://mock.com/job_002"},
            {"title": "Java后端开发实习生", "company": "美团", "job_url": "https://mock.com/job_003"} # 混入陷阱
        ]
    elif platform == "实习僧":
        results = [
            {"title": "NLP自然语言处理实习生", "company": "百度", "job_url": "https://mock.com/job_004"},
            {"title": "资深自动驾驶算法工程师", "company": "小马智行", "job_url": "https://mock.com/job_005"} # 混入陷阱
        ]
    else:
        return json.dumps({"error": f"暂不支持平台: {platform}。请尝试 牛客网 或 实习僧。"}, ensure_ascii=False)
        
    return json.dumps(results, ensure_ascii=False)

# ==========================================
# 工具 2：详情页抓取与解析 API
# 对标面试题要求：“网页抓取工具”
# ==========================================
@tool
def scrape_job_detail_api(job_url: str) -> str:
    """
    根据岗位链接(job_url)抓取岗位的详细 JD (职位描述)。
    参数:
    - job_url: 岗位详情页的完整URL
    返回: 该岗位的完整文本描述，包含薪资、地点、技能要求等。
    """
    print(f"[Tool 运行中] 🕷️ 正在抓取网页详情: {job_url}...")
    
    # 从 url 中提取 mock ID
    job_id = job_url.split("/")[-1]
    
    if job_id in MOCK_JD_DATABASE:
        data = MOCK_JD_DATABASE[job_id]
        # 将结构化数据拼装成一段仿真的网页纯文本
        jd_text = (
            f"职位名称：{data['title']}\n"
            f"公司：{data['company']}\n"
            f"工作地点：{data['location']}\n"
            f"薪酬范围：{data['salary']}\n"
            f"职位要求/职责：\n{data['req']}\n"
            f"来源平台：{data['source']}"
        )
        return jd_text
    else:
        return "404 Error: 无法获取该网页内容，该职位可能已下线。"

# 导出工具列表供大模型使用
# OpenAl Function Calling / Tool Use 会直接读取这些工具 
agent_tools = [search_jobs_api, scrape_job_detail_api]



