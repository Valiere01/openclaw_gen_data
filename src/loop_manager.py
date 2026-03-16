import time
import json
import shutil
import os
from datetime import datetime
from typing import Dict, Optional, List

from openclaw_controller import OpenClawController
from usermodel_client import UserModelClient
import config


class LoopManager:
    """对话循环管理器"""

    def __init__(
        self,
        max_iterations: int = None,
        run_dir: str = None,
        tools_schema: Dict = None,
        logs_dir: str = None
    ):
        """初始化循环管理器

        Args:
            max_iterations: 最大对话轮次
            run_dir: session备份目录（如 output/sessions/test1/）
            tools_schema: 预先获取的工具schema（批量模式下只fetch一次，各任务共享）
            logs_dir: loop日志目录（如 logs/test1/）
        """
        self.max_iterations = max_iterations or config.MAX_ITERATIONS
        self.usermodel = UserModelClient()
        self.run_dir  = run_dir  or config.SESSIONS_BACKUP_ROOT
        self.logs_dir = logs_dir or config.LOGS_ROOT
        self.tools_schema = tools_schema

    def run_conversation_loop(self, intent: str) -> Dict:
        """运行完整的对话循环

        流程：
          1. 生成唯一 session_id 创建独立 session（支持并发）
          2. UserModel 生成第一条用户消息
          3. 发送到 Agent，收到回复
          4. UserModel 判断是否完成，未完成则生成下一条消息
          5. 循环直到完成或达到上限

        Args:
            intent: 用户意图（自然语言描述）

        Returns:
            Dict: {
                "success": bool,
                "session_id": str,
                "session_file_path": str,
                "intent": str,
                "total_turns": int,
                "completed": bool,
                "reason": str,
                "final_agent_response": str,
                "conversation_history": List[Dict]  # OpenAI格式
            }
        """
        sep = "=" * 60
        print(f"\n{sep}")
        print(f"Intent: {intent[:80]}")
        print(f"最大轮次: {self.max_iterations}")
        print(f"{sep}\n")

        # 每个任务独立的 controller
        openclaw = OpenClawController()
        conversation_history: List[Dict] = []
        session_info: Dict = {}

        try:
            # ── Step 1: 创建新session ──
            # fetch_tools 只在没有预共享schema时才执行
            if self.tools_schema:
                print("[1] 创建新session（复用共享工具schema）...")
                session_info = openclaw.create_new_session(fetch_tools=False)
                openclaw.tools_schema = self.tools_schema  # 注入共享schema
                print(f"    ✅ session_id: {session_info['session_id']}")
                print(f"    🔧 工具数量: {len(self.tools_schema)} (共享)\n")
            else:
                print("[1] 创建新session（含工具列表查询）...")
                session_info = openclaw.create_new_session(fetch_tools=True)
                print(f"    ✅ session_id: {session_info['session_id']}")
                print(f"    🔧 工具数量: {session_info['tools_count']}\n")

            # ── Step 2: 生成第一条用户消息 ──
            print("[2] UserModel 生成第一条消息...")
            first_message = self.usermodel.generate_first_message(intent)
            print(f"    📝 {first_message[:100]}\n")

            conversation_history.append({
                "role": "user",
                "content": first_message
            })

            # ── Step 3: 对话循环 ──
            turn = 0
            completed = False
            reason = ""
            final_agent_response = ""

            for turn in range(1, self.max_iterations + 1):
                print(f"{'─' * 50}")
                print(f"轮次 {turn}/{self.max_iterations}")
                print(f"{'─' * 50}")

                # 发送用户消息
                current_user_msg = conversation_history[-1]["content"]
                print(f"📤 用户: {current_user_msg[:100]}")

                send_result = openclaw.send_message(current_user_msg)

                if not send_result["success"]:
                    reason = f"发送消息失败 (轮次{turn}): {send_result.get('error','')}"
                    print(f"❌ {reason}")
                    break

                agent_reply = send_result["reply"]
                final_agent_response = agent_reply
                print(f"🤖 Agent: {agent_reply[:150]}{'...' if len(agent_reply) > 150 else ''}\n")

                # 更新对话历史
                conversation_history.append({
                    "role": "assistant",
                    "content": agent_reply
                })

                # 快速关键词检查
                if self.usermodel.check_completion_by_keywords(agent_reply):
                    completed = True
                    reason = f"Agent回复包含完成关键词 (轮次{turn})"
                    print(f"🎯 {reason}")
                    break

                # UserModel 判断 + 生成下一条消息
                print("🤔 UserModel 判断...")
                next_step = self.usermodel.generate_next_message(
                    intent,
                    conversation_history,
                    agent_reply
                )

                if next_step["completed"]:
                    completed = True
                    reason = f"UserModel判断完成: {next_step.get('reason','')} (轮次{turn})"
                    print(f"✅ {reason}")
                    break

                # 未完成，继续
                next_msg = next_step["message"]
                print(f"➡️  下一轮: {next_msg[:80]}")
                print(f"   意图: {next_step.get('reason','')[:60]}\n")

                conversation_history.append({
                    "role": "user",
                    "content": next_msg
                })

                time.sleep(0.5)  # 轻微节流

            # 达到上限
            if not completed and turn >= self.max_iterations:
                reason = f"达到最大轮次 ({self.max_iterations})"
                print(f"⚠️  {reason}")

            # ── Step 4: 备份session文件 ──
            backup_path = self._backup_session_file(
                openclaw.session_file_path
            )

            result = {
                "success": True,
                "session_id": openclaw.session_id,
                "session_file_path": openclaw.session_file_path,
                "backup_file_path": backup_path,
                "intent": intent,
                "total_turns": turn,
                "completed": completed,
                "reason": reason,
                "final_agent_response": final_agent_response,
                "conversation_history": conversation_history,
                # 运行时工具schema，供data_converter使用
                "runtime_tools": openclaw.tools_schema
            }

            print(f"\n{sep}")
            print(f"循环结束 | 轮次:{turn} | {'✅完成' if completed else '⚠️未完成'}")
            print(f"原因: {reason}")
            print(f"{sep}\n")

            return result

        except Exception as e:
            import traceback
            traceback.print_exc()
            return {
                "success": False,
                "session_id": session_info.get("session_id", ""),
                "session_file_path": session_info.get("session_file_path", ""),
                "intent": intent,
                "total_turns": 0,
                "completed": False,
                "reason": f"异常: {str(e)}",
                "final_agent_response": "",
                "conversation_history": conversation_history
            }

    # ------------------------------------------------------------------ #
    #  工具方法                                                             #
    # ------------------------------------------------------------------ #

    def _backup_session_file(self, session_file_path: str) -> Optional[str]:
        """备份session文件到output/sessions/"""
        if not session_file_path or not os.path.exists(session_file_path):
            return None
        try:
            os.makedirs(self.run_dir, exist_ok=True)
            backup_path = os.path.join(
                self.run_dir,
                os.path.basename(session_file_path)
            )
            shutil.copy2(session_file_path, backup_path)
            print(f"    💾 session已备份: {backup_path}")
            return backup_path
        except Exception as e:
            print(f"    ⚠️ 备份失败: {e}")
            return None

    def save_result(self, result: Dict, output_path: str = None) -> str:
        """保存循环结果到JSON文件"""
        if output_path is None:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            sid = result.get("session_id", "unknown")[:8]
            os.makedirs(self.logs_dir, exist_ok=True)
            output_path = os.path.join(self.logs_dir, f"loop_{sid}_{ts}.json")

        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)

        print(f"    📄 结果已保存: {output_path}")
        return output_path


if __name__ == "__main__":
    print("=== LoopManager 测试 ===\n")
    manager = LoopManager(max_iterations=3)
    result = manager.run_conversation_loop("请帮我查看当前目录下有哪些文件")
    if result["success"]:
        manager.save_result(result)
        print(f"\n✅ 完成，共{result['total_turns']}轮，session: {result['session_id']}")
    else:
        print(f"\n❌ 失败: {result['reason']}")
