import subprocess
import json
import time
import os
from typing import Dict, Optional, List
import config


class OpenClawController:
    """OpenClaw交互控制器"""

    def __init__(self):
        """初始化控制器"""
        self.session_id: Optional[str] = None
        self.session_file_path: Optional[str] = None
        # 运行时从agent获取的完整工具定义（name -> OpenAI tool object）
        self.tools_schema: Dict[str, Dict] = {}

    # ------------------------------------------------------------------ #
    #  Session管理                                                          #
    # ------------------------------------------------------------------ #

    def create_new_session(self, fetch_tools: bool = False) -> Dict:
        """创建新的独立session（通过 /session <uuid> 命令）

        Args:
            fetch_tools: 已废弃，保留参数兼容性

        Returns:
            Dict: {
                "session_id": str,
                "session_file_path": str,
                "agent_reply": str,
                "tools_count": int   # 固定返回0（工具由外部提供）
            }
        Raises:
            RuntimeError: 创建失败
        """
        import uuid
        session_id = str(uuid.uuid4())
        
        # 发送 /session 命令切换到新 session
        result = self._run_agent_command(f"/session {session_id}")
        
        session_file = os.path.join(config.OPENCLAW_SESSION_DIR, f"{session_id}.jsonl")
        self.session_id = session_id
        self.session_file_path = session_file

        return {
            "session_id": session_id,
            "session_file_path": session_file,
            "agent_reply": result["reply"],
            "tools_count": 0
        }

    def get_tools_for_names(self, tool_names: List[str]) -> List[Dict]:
        """根据工具名列表返回对应的完整schema

        优先使用从agent获取的运行时schema，
        fallback到 output/openclaw_all_tools.json 静态schema。

        Args:
            tool_names: 工具名列表

        Returns:
            List[Dict]: OpenAI格式的工具定义列表
        """
        result = []
        missing = []

        for name in tool_names:
            if name in self.tools_schema:
                result.append(self.tools_schema[name])
            else:
                missing.append(name)

        # fallback：从静态文件补充
        if missing:
            static = self._load_static_tools_cache()
            for name in missing:
                if name in static:
                    result.append(static[name])

        return result

    @staticmethod
    def _load_static_tools_cache() -> Dict:
        """加载静态工具schema缓存（fallback用）"""
        cache_file = os.path.join(
            "/Users/luosiyuan/openclaw_proj/openclaw_gen_data/output",
            "openclaw_all_tools.json"
        )
        if not os.path.exists(cache_file):
            return {}
        try:
            with open(cache_file, 'r', encoding='utf-8') as f:
                tools_list = json.load(f)
            result = {}
            for t in tools_list:
                if "function" in t:
                    result[t["function"]["name"]] = t
                elif "name" in t:
                    result[t["name"]] = t
            return result
        except Exception:
            return {}

    # ------------------------------------------------------------------ #
    #  消息收发                                                             #
    # ------------------------------------------------------------------ #

    def send_message(self, message: str) -> Dict:
        """发送消息并同步等待Agent回复

        Args:
            message: 消息内容

        Returns:
            Dict: {
                "success": bool,
                "reply": str,        # Agent的文本回复
                "session_id": str
            }
        """
        if not self.session_id:
            raise ValueError("请先调用 create_new_session()")

        try:
            result = self._run_agent_command(message)
            return {
                "success": True,
                "reply": result["reply"],
                "session_id": result["session_id"]
            }
        except Exception as e:
            return {
                "success": False,
                "reply": "",
                "session_id": self.session_id,
                "error": str(e)
            }

    # ------------------------------------------------------------------ #
    #  Session文件读取                                                      #
    # ------------------------------------------------------------------ #

    def get_full_session_data(self) -> List[Dict]:
        """读取当前session的完整JSONL数据（用于最终转换mid_format）

        Returns:
            List[Dict]: type=="message" 的条目列表
        """
        if not self.session_file_path:
            raise ValueError("请先创建session")

        # 等待文件稳定（agent写完）
        time.sleep(1)

        messages = []
        try:
            with open(self.session_file_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        obj = json.loads(line)
                        if obj.get("type") == "message":
                            messages.append(obj)
                    except json.JSONDecodeError:
                        continue
        except FileNotFoundError:
            pass

        return messages

    # ------------------------------------------------------------------ #
    #  内部工具                                                             #
    # ------------------------------------------------------------------ #

    def _run_agent_command(self, message: str, timeout: int = 180) -> Dict:
        """执行 openclaw agent 命令并返回结构化结果

        Args:
            message: 发送给agent的消息
            timeout: 超时秒数

        Returns:
            Dict: {
                "session_id": str,
                "reply": str,
                "raw": dict   # 完整JSON响应
            }

        Raises:
            RuntimeError: 命令失败或超时
        """
        # 转义消息中的特殊字符（单引号策略）
        safe_message = message.replace("'", "'\\''")

        # 构建命令
        if self.session_id:
            cmd = (
                f"openclaw agent --agent {config.OPENCLAW_AGENT_NAME} "
                f"--session-id {self.session_id} "
                f"--message '{safe_message}' --json"
            )
        else:
            cmd = (
                f"openclaw agent --agent {config.OPENCLAW_AGENT_NAME} "
                f"--message '{safe_message}' --json"
            )

        try:
            proc = subprocess.run(
                cmd,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout
            )
        except subprocess.TimeoutExpired:
            raise RuntimeError(f"openclaw agent 命令超时（{timeout}s）")

        if proc.returncode != 0:
            raise RuntimeError(f"openclaw agent 命令失败: {proc.stderr.strip()}")

        # 解析JSON
        try:
            data = json.loads(proc.stdout)
        except json.JSONDecodeError as e:
            raise RuntimeError(f"解析响应JSON失败: {e}\n原始输出: {proc.stdout[:500]}")

        if data.get("status") != "ok":
            raise RuntimeError(f"agent返回非ok状态: {data.get('status')}")

        # 提取关键字段
        meta = data.get("result", {}).get("meta", {}).get("agentMeta", {})
        session_id = meta.get("sessionId", self.session_id or "")

        payloads = data.get("result", {}).get("payloads", [])
        reply = payloads[0].get("text", "") if payloads else ""

        # 更新session_id（/reset后会变）
        if session_id:
            self.session_id = session_id
            self.session_file_path = os.path.join(
                config.OPENCLAW_SESSION_DIR, f"{session_id}.jsonl"
            )

        return {
            "session_id": session_id,
            "reply": reply,
            "raw": data
        }


if __name__ == "__main__":
    print("=== OpenClawController 测试 ===\n")
    ctrl = OpenClawController()

    print("1. 创建新session...")
    info = ctrl.create_new_session()
    print(f"   session_id: {info['session_id']}")
    print(f"   reset reply: {info['agent_reply'][:80]}\n")

    print("2. 发送测试消息...")
    res = ctrl.send_message("请列出当前目录的文件，只输出文件名列表。")
    print(f"   success: {res['success']}")
    print(f"   reply: {res['reply'][:200]}\n")

    print("3. 读取session文件...")
    msgs = ctrl.get_full_session_data()
    print(f"   共 {len(msgs)} 条消息")
