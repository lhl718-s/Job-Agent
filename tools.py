from langchain_core.tools import tool
import json
import os

# ==========================================
# 动态加载外部 Mock 数据库
# ==========================================
def load_mock_database():
    """从外部 json 文件加载数据库，模拟真实的后端数据源"""
    db_path = os.path.join(os.path.dirname(__file__), "mock_jobs.json")
    try:
        with open(db_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"⚠️ 警告：未找到 {db_path}，请确保已创建该数据文件！")
        return []

MOCK_JD_DATABASE = load_mock_database()

# ==========================================
# 工具 1：智能搜索引擎 (支持模糊匹配与降级策略)
# ==========================================
@tool
def search_jobs_api(query: str, platform: str) -> str:
    """
    在指定的招聘网站上搜索岗位信息。
    参数:
    - query: 搜索关键词 (例如: "大模型", "CV", "NLP", "推荐算法")
    - platform: 招聘平台名称 (目前仅支持 "牛客网" 或 "实习僧")
    返回: 包含职位基础信息和详情链接(job_url)的 JSON 字符串。
    """
    print(f"\n[Tool 运行中] 🔍 正在 '{platform}' 的海量数据库中检索关键词: '{query}'...")
    
    results = []
    query_lower = query.lower()
    
    # 模拟真实搜索引擎的检索逻辑
    for job in MOCK_JD_DATABASE:
        if job["platform"] == platform:
            search_text = (job["title"] + " " + job["req"]).lower()
            
            is_match = False
            # 基础匹配：用户的查询词是否直接包含在岗位文本中
            # 扩展匹配：一些 AI 领域的常见同义词
            for kw in ["大模型", "llm", "视觉", "cv", "nlp", "自然语言", "推荐", "aigc", "java", "前端", "数据", "ai", "人工智能", "算法", "实习", "校招"]:
                if kw in query_lower and kw in search_text:
                    is_match = True
                    break
            
            # 如果大模型用的词比较泛，保底匹配
            if "engineer" in query_lower or "实习生" in query_lower:
                is_match = True

            if is_match:
                results.append({
                    "title": job["title"],
                    "company": job["company"],
                    "job_url": f"https://mock.com/{job['id']}"
                })
                
    # 💡 保底机制：如果大模型的关键词太离谱，随便吐一条数据回去，逼着大模型自己去清洗并换词！
    if not results:
        print("   ⚠️ 检索无精准命中，触发通用召回策略...")
        for job in MOCK_JD_DATABASE:
            if job["platform"] == platform:
                results.append({"title": job["title"], "company": job["company"], "job_url": f"https://mock.com/{job['id']}"})
                break

    return json.dumps(results, ensure_ascii=False)

# ==========================================
# 工具 2：详情页解析器
#============================================
@tool
def scrape_job_detail_api(job_url: str) -> str:
    """根据岗位链接(job_url)抓取岗位的详细 JD (职位描述)。"""
    print(f"[Tool 运行中] 🕷️ 正在深度解析网页结构: {job_url}...")
    job_id = job_url.split("/")[-1]
    
    for job in MOCK_JD_DATABASE:
        if job["id"] == job_id:
            jd_text = (
                f"职位名称：{job['title']}\n公司：{job['company']}\n工作地点：{job['location']}\n"
                f"薪酬范围：{job['salary']}\n职位要求/职责：\n{job['req']}\n来源平台：{job['platform']}"
            )
            return jd_text
            
    return "404 Error: 该职位详情已失效或无权限访问。"

agent_tools = [search_jobs_api, scrape_job_detail_api]
