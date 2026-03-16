import os

# ============== OpenClaw配置 ==============
# 使用的Agent名称
OPENCLAW_AGENT_NAME = "test_loop"

# OpenClaw session文件存储目录
OPENCLAW_SESSION_DIR = f"/Users/luosiyuan/.openclaw/agents/{OPENCLAW_AGENT_NAME}/sessions/"

# OpenClaw命令前缀
OPENCLAW_AGENT_COMMAND = "openclaw agent"
OPENCLAW_SESSIONS_COMMAND = "openclaw sessions"

# ============== UserModel API配置 ==============
# Azure OpenAI API配置
USERMODEL_CONFIG = {
    "url": "xxx",
    "api_key": "xxx",
    "model": "gpt-4o-2024-11-20",
    "temperature": 0.7,
    "max_tokens": 4000
}

# ============== 循环控制配置 ==============
# 最大交互轮次
MAX_ITERATIONS = 20

# 任务完成关键词（在Agent回复中检测）
COMPLETION_KEYWORDS = [
    "success",
    "completed",
    "成功完成",
    "任务完成",
    "已完成",
    "successfully completed",
    "task completed"
]

# Session文件检查间隔（秒）
SESSION_CHECK_INTERVAL = 2

# 等待Agent响应的超时时间（秒）
SESSION_TIMEOUT = 60

# ============== 输出路径配置 ==============
# 项目根目录
PROJECT_ROOT = "/Users/luosiyuan/openclaw_proj/openclaw_gen_data"

# 输出目录
OUTPUT_DIR = os.path.join(PROJECT_ROOT, "output")

# 各类输出的根目录（每次批量运行会在此下自动创建 test1/test2/... 子目录）
SESSIONS_BACKUP_ROOT = os.path.join(OUTPUT_DIR, "sessions")   # session JSONL备份
CONVERTED_ROOT       = os.path.join(OUTPUT_DIR, "converted")  # mid_format JSON
TOOLS_ROOT           = os.path.join(OUTPUT_DIR, "tools")       # 工具schema
LOGS_ROOT            = os.path.join(PROJECT_ROOT, "logs")      # 日志和summary

# 兼容旧代码
SESSIONS_BACKUP_DIR = SESSIONS_BACKUP_ROOT
CONVERTED_DIR       = CONVERTED_ROOT
LOGS_DIR            = LOGS_ROOT


def get_next_run_dir(base_dir: str, prefix: str = "test") -> str:
    """获取下一个可用的带编号子目录路径（不创建）

    扫描 base_dir 下的 test1, test2, ... 找到最大编号后+1
    注意：各根目录独立编号，调用方需确保用同一个 run_name。
    """
    import re
    os.makedirs(base_dir, exist_ok=True)
    existing = [d for d in os.listdir(base_dir)
                if os.path.isdir(os.path.join(base_dir, d))
                and re.match(rf'^{re.escape(prefix)}\d+$', d)]
    nums = [int(re.search(r'\d+$', d).group()) for d in existing] if existing else [0]
    return os.path.join(base_dir, f"{prefix}{max(nums) + 1}")


def get_run_dirs(run_name: str) -> dict:
    """根据 run_name（如 "test3"）返回该次运行的所有目录路径

    Returns:
        dict: {
            "sessions": str,   # session JSONL备份
            "converted": str,  # mid_format JSON
            "tools": str,      # 工具schema目录
            "logs": str,       # 日志目录
            "tools_file": str  # 工具schema文件路径
        }
    """
    sessions  = os.path.join(SESSIONS_BACKUP_ROOT, run_name)
    converted = os.path.join(CONVERTED_ROOT,       run_name)
    tools_dir = os.path.join(TOOLS_ROOT,           run_name)
    logs_dir  = os.path.join(LOGS_ROOT,            run_name)
    return {
        "sessions":   sessions,
        "converted":  converted,
        "tools":      tools_dir,
        "logs":       logs_dir,
        "tools_file": os.path.join(tools_dir, "openclaw_all_tools.json"),
    }


def ensure_run_dirs(run_name: str) -> dict:
    """创建该次运行的所有目录并返回路径字典"""
    dirs = get_run_dirs(run_name)
    for key in ("sessions", "converted", "tools", "logs"):
        os.makedirs(dirs[key], exist_ok=True)
    return dirs

# 日志目录
LOGS_DIR = os.path.join(PROJECT_ROOT, "logs")

# ============== 日志配置 ==============
# 日志级别
LOG_LEVEL = "INFO"

# 日志格式
LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

# ============== 并发配置 ==============
# 默认并发数
DEFAULT_CONCURRENT = 5

# 最大并发数
MAX_CONCURRENT = 10


def ensure_dirs():
    """确保所有根目录存在"""
    for d in [OUTPUT_DIR, SESSIONS_BACKUP_ROOT, CONVERTED_ROOT, TOOLS_ROOT, LOGS_ROOT]:
        os.makedirs(d, exist_ok=True)


def validate_config():
    """验证配置是否正确

    Returns:
        tuple: (is_valid: bool, error_message: str)
    """
    # 检查API Key
    if not USERMODEL_CONFIG["api_key"]:
        return False, "AZURE_OPENAI_API_KEY环境变量未设置"

    # 检查OpenClaw session目录是否存在
    if not os.path.exists(OPENCLAW_SESSION_DIR):
        return False, f"OpenClaw session目录不存在: {OPENCLAW_SESSION_DIR}"

    return True, ""


if __name__ == "__main__":
    # 测试配置
    print("=== 配置测试 ===")
    print(f"OpenClaw Session目录: {OPENCLAW_SESSION_DIR}")
    print(f"输出目录: {OUTPUT_DIR}")
    print(f"UserModel API URL: {USERMODEL_CONFIG['url']}")
    print(f"API Key已设置: {'是' if USERMODEL_CONFIG['api_key'] else '否'}")

    # 验证配置
    is_valid, error_msg = validate_config()
    if is_valid:
        print("\n✅ 配置验证通过")
        ensure_dirs()
        print("✅ 所有目录已创建")
    else:
        print(f"\n❌ 配置验证失败: {error_msg}")
