from agent import app

print("====== Agentic AI 求职助手启动 ======")
print("请告诉我您想找什么样的工作？")
user_req = input(" 您的详细要求 ：\n> ")

target_str = input("请输入希望收集的岗位数量 ：\n> ")
try:
    target_count = int(target_str)
except ValueError:
    target_count = 2 # 默认值

# 初始化动态状态
initial_state = {
    "user_requirements": user_req,
    "target_count": target_count,
    "jobs": [],
    "visited_urls": set(),
    "search_history": [],
    "error_count": 0
}

print("\n⚙️ 收到需求！Agent 正在为您规划并执行搜索任务...")

# 启动图的执行流
final_state = app.invoke(initial_state)



print("\n\n====== 📊 最终输出成果 ======")


# 获取最终收集到的岗位
final_jobs = final_state.get("jobs", [])
target = final_state.get("target_count", 2)

if not final_jobs:
    print("\n 非常抱歉！Agent 经过多轮全网检索与大模型的深度筛选，")
    print("未能发掘到完全符合您偏门或严苛要求（如特定冷门地点、特殊技术栈）的岗位。")

else:
    for i, job in enumerate(final_jobs):
        print(f"\n岗位 {i+1}: {job.title} | {job.company} | 地点: {job.location}")
        print(f"技术标签: {job.tech_tags}")
        print(f"详情: {job.requirements}")
        print(f"链接: {job.job_url}")
        
    # 如果找到了，但是没找够目标数量
    if len(final_jobs) < target:
        print(f"\n提示：受限于当前数据库存量及您的严格要求，系统已尽最大努力，")
        print(f"为您挖掘到 {len(final_jobs)} 个完美匹配的岗位（您的目标是 {target} 个）。")
        print("您可以尝试放宽搜索条件以获取更多结果！")
