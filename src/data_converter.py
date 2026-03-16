import json
import os
from typing import Dict, List, Tuple, Optional

from session_parser import SessionParser


class DataConverter:
    """OpenClaw session → mid_format 转换器"""

    def __init__(self, runtime_tools: Dict = None):
        """
        Args:
            runtime_tools: 从 OpenClawController.tools_schema 传入的运行时工具定义
                           格式: {tool_name: OpenAI_tool_object}
                           来源：create_new_session(fetch_tools=True) 时agent直接输出的完整schema
                           fallback：静态缓存文件（若存在）
        """
        self.parser = SessionParser()
        # 运行时schema优先（从agent交互获取，含完整description），静态文件兜底
        if runtime_tools:
            self.tools_definitions: Dict = runtime_tools
        else:
            self.tools_definitions: Dict = self._load_tools_cache()

    # ------------------------------------------------------------------ #
    #  主转换入口                                                           #
    # ------------------------------------------------------------------ #

    def convert_session_to_mid_format(
        self,
        session_file_path: str,
        intent: str,
        system_prompt: str = None,
        status: str = None
    ) -> Dict:
        """将session文件转换为mid_format格式

        Args:
            session_file_path: session JSONL文件路径
            intent: 用户意图
            system_prompt: 系统提示词（None则从session中提取）
            status: 强制指定状态，None则自动判断

        Returns:
            Dict: 符合 mid_format_schema 的数据
        """
        # 1. 解析原始消息
        messages_raw = self.parser.parse_jsonl_file(session_file_path)

        # 2. 提取session_id（从文件名）
        session_id = os.path.basename(session_file_path).replace(".jsonl", "")

        # 3. 转换消息 + 提取工具定义
        messages_openai, tools = self._convert_messages(messages_raw)

        # 4. system prompt
        if system_prompt is None:
            system_prompt = self._extract_system_prompt(messages_raw)
        if system_prompt:
            messages_openai.insert(0, {"role": "system", "content": system_prompt})

        # 5. 最终输出
        final_output = self._extract_final_output(messages_raw)

        # 6. 状态
        if status is None:
            status = self._determine_status(messages_raw, final_output)

        # 7. 统计轮次
        total_steps = self.parser.count_turns(messages_raw)

        # 8. 是否启用thinking
        enable_thinking = self._check_enable_thinking(messages_raw)

        # 9. init/final state（从session metadata提取，无则空dict）
        init_state, final_state = self._extract_states(messages_raw)

        return {
            "status": status,
            "session_id": session_id,
            "intent": intent,
            "total_steps": total_steps,
            "final_output": final_output,
            "enable_thinking": enable_thinking,
            "messages": messages_openai,
            "tools": tools,
            "init_state": init_state,
            "final_state": final_state
        }

    # ------------------------------------------------------------------ #
    #  消息格式转换                                                         #
    # ------------------------------------------------------------------ #

    def _convert_messages(
        self, messages_raw: List[Dict]
    ) -> Tuple[List[Dict], List[Dict]]:
        """将OpenClaw格式消息转为OpenAI格式，同时提取tools定义

        Returns:
            (messages_openai, tools_list)
        """
        messages_openai: List[Dict] = []
        # tool_name -> set of argument key sets（用于推断schema）
        tools_seen: Dict[str, List[Dict]] = {}

        for msg_obj in messages_raw:
            msg = msg_obj.get("message", {})
            role = msg.get("role")

            if role == "user":
                text = self.parser.extract_text_from_content(msg.get("content", []))
                if text:
                    messages_openai.append({"role": "user", "content": text})

            elif role == "assistant":
                content_list = msg.get("content", [])
                text = self.parser.extract_text_from_content(content_list)
                tool_calls_raw = self.parser.extract_tool_calls(content_list)

                openai_msg: Dict = {
                    "role": "assistant",
                    "content": text,
                }

                # reasoning_content（thinking）
                if msg.get("reasoning_content"):
                    openai_msg["reasoning_content"] = msg["reasoning_content"]

                # tool_calls
                if tool_calls_raw:
                    openai_msg["tool_calls"] = []
                    for i, tc in enumerate(tool_calls_raw):
                        openai_msg["tool_calls"].append({
                            "index": i,
                            "id": tc["id"],
                            "type": "function",
                            "function": {
                                "name": tc["name"],
                                "arguments": json.dumps(
                                    tc["arguments"], ensure_ascii=False
                                )
                            }
                        })
                        # 记录工具使用情况
                        if tc["name"] not in tools_seen:
                            tools_seen[tc["name"]] = []
                        tools_seen[tc["name"]].append(tc["arguments"])

                messages_openai.append(openai_msg)

            elif role == "toolResult":
                tr = self.parser.extract_tool_result(msg_obj)
                messages_openai.append({
                    "role": "tool",
                    "name": tr["name"],
                    "tool_call_id": tr["tool_call_id"],
                    "content": tr["content"],
                    "success": tr["success"]
                })

        # 生成 tools schema
        tools = self._build_tools_schema(tools_seen)

        return messages_openai, tools

    # ------------------------------------------------------------------ #
    #  工具Schema构建                                                       #
    # ------------------------------------------------------------------ #

    def _build_tools_schema(self, tools_seen: Dict[str, List[Dict]]) -> List[Dict]:
        """构建tools定义列表

        优先使用缓存的完整定义（OpenAI格式），fallback到从调用示例推断。
        """
        result = []
        for tool_name, examples in tools_seen.items():
            if tool_name in self.tools_definitions:
                cached = self.tools_definitions[tool_name]
                # 已经是OpenAI格式 {"type":"function","function":{...}}
                if "function" in cached:
                    result.append(cached)
                else:
                    # Anthropic格式，转换
                    result.append({
                        "type": "function",
                        "function": {
                            "name": cached.get("name", tool_name),
                            "description": cached.get("description", f"Tool: {tool_name}"),
                            "parameters": cached.get("input_schema", cached.get("parameters", {
                                "type": "object", "properties": {}, "required": []
                            }))
                        }
                    })
            else:
                # 从调用示例推断（fallback）
                parameters = self._infer_parameters(examples)
                result.append({
                    "type": "function",
                    "function": {
                        "name": tool_name,
                        "description": f"Tool: {tool_name}",
                        "parameters": parameters
                    }
                })
        return result

    def _infer_parameters(self, examples: List[Dict]) -> Dict:
        """从参数调用示例推断JSON schema"""
        if not examples:
            return {"type": "object", "properties": {}, "required": []}

        properties = {}
        for ex in examples:
            for k, v in ex.items():
                if k not in properties:
                    properties[k] = {
                        "type": self._infer_type(v),
                        "description": f"Parameter: {k}"
                    }

        return {
            "type": "object",
            "properties": properties,
            "required": []
        }

    @staticmethod
    def _infer_type(value) -> str:
        if isinstance(value, bool):
            return "boolean"
        if isinstance(value, int):
            return "integer"
        if isinstance(value, float):
            return "number"
        if isinstance(value, list):
            return "array"
        if isinstance(value, dict):
            return "object"
        return "string"

    # ------------------------------------------------------------------ #
    #  辅助提取方法                                                         #
    # ------------------------------------------------------------------ #

    def _extract_system_prompt(self, messages_raw: List[Dict]) -> str:
        for msg_obj in messages_raw:
            msg = msg_obj.get("message", {})
            if msg.get("role") == "system":
                return self.parser.extract_text_from_content(msg.get("content", []))
        return ""

    def _extract_final_output(self, messages_raw: List[Dict]) -> str:
        resp = self.parser.extract_agent_response(messages_raw)
        return resp["agent_text"] if resp else ""

    def _determine_status(self, messages_raw: List[Dict], final_output: str = "") -> str:
        text = final_output.lower()
        complete_kw = ["success", "completed", "成功", "完成", "done", "✅"]
        error_kw = ["error", "failed", "失败", "错误"]

        for kw in complete_kw:
            if kw in text:
                return "completed"
        for kw in error_kw:
            if kw in text:
                return "failed"

        # 有最终回复但无关键词 → completed（对话自然结束）
        if final_output:
            return "completed"
        return "in_progress"

    def _check_enable_thinking(self, messages_raw: List[Dict]) -> bool:
        for msg_obj in messages_raw:
            msg = msg_obj.get("message", {})
            if msg.get("reasoning_content"):
                return True
        return False

    def _extract_states(
        self, messages_raw: List[Dict]
    ) -> Tuple[Dict, Dict]:
        """提取 init_state 和 final_state

        OpenClaw session 文件通常不含业务状态，返回空dict。
        如需自定义，可在子类中重写此方法。
        """
        return {}, {}

    # ------------------------------------------------------------------ #
    #  工具定义缓存                                                         #
    # ------------------------------------------------------------------ #

    def _load_tools_cache(self) -> Dict:
        """加载已缓存的OpenClaw工具定义

        Returns:
            Dict: tool_name -> tool_definition
        """
        cache_file = os.path.join(
            "/Users/luosiyuan/openclaw_proj/openclaw_gen_data/output",
            "openclaw_all_tools.json"
        )
        if not os.path.exists(cache_file):
            return {}
        try:
            with open(cache_file, 'r', encoding='utf-8') as f:
                tools_list = json.load(f)
            # 支持两种格式：
            # 1. OpenAI格式: {"type":"function","function":{"name":...}}
            # 2. Anthropic格式: {"name":..., "description":..., "input_schema":...}
            result = {}
            for t in tools_list:
                if "function" in t and "name" in t["function"]:
                    # OpenAI格式：直接存整个tool object，按name索引
                    result[t["function"]["name"]] = t
                elif "name" in t:
                    result[t["name"]] = t
            return result
        except Exception:
            return {}


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        session_file = sys.argv[1]
        intent = sys.argv[2] if len(sys.argv) > 2 else "测试任务"
    else:
        # 使用test_loop agent的最新session
        session_dir = "/Users/luosiyuan/.openclaw/agents/test_loop/sessions/"
        jsonl_files = [
            f for f in os.listdir(session_dir) if f.endswith(".jsonl")
        ]
        if not jsonl_files:
            print("❌ 没有找到session文件")
            sys.exit(1)
        session_file = os.path.join(session_dir, jsonl_files[0])
        intent = "测试转换"

    print(f"=== DataConverter 测试 ===")
    print(f"Session: {session_file}")
    print(f"Intent: {intent}\n")

    converter = DataConverter()
    data = converter.convert_session_to_mid_format(session_file, intent)

    print(f"status: {data['status']}")
    print(f"session_id: {data['session_id']}")
    print(f"total_steps: {data['total_steps']}")
    print(f"messages: {len(data['messages'])}")
    print(f"tools: {len(data['tools'])}")
    print(f"enable_thinking: {data['enable_thinking']}")
    print(f"final_output: {data['final_output'][:150]}")

    out = "/tmp/test_mid_format.json"
    with open(out, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"\n✅ 已保存到 {out}")
