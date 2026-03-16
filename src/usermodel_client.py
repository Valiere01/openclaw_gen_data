import json
import requests
from typing import Dict, List, Optional
import config


class UserModelClient:
    """UserModel API客户端"""

    def __init__(self, api_config: Dict = None):
        """初始化API客户端

        Args:
            api_config: API配置字典，如果为None则使用config中的默认配置
        """
        self.config = api_config or config.USERMODEL_CONFIG
        self.session = requests.Session()
        self.session.headers.update({
            "Content-Type": "application/json",
            "api-key": self.config["api_key"]
        })

    def _call_api(self, messages: List[Dict], max_retries: int = 3) -> str:
        """调用API的底层方法

        Args:
            messages: OpenAI格式的消息列表
            max_retries: 最大重试次数

        Returns:
            str: API响应内容

        Raises:
            RuntimeError: API调用失败
        """
        payload = {
            "model": self.config["model"],
            "messages": messages,
            "temperature": self.config["temperature"],
            "max_tokens": self.config["max_tokens"]
        }

        for attempt in range(max_retries):
            try:
                response = self.session.post(
                    self.config["url"],
                    json=payload,
                    timeout=60
                )

                if response.status_code == 200:
                    data = response.json()
                    return data["choices"][0]["message"]["content"]
                else:
                    error_msg = f"API返回错误: {response.status_code} - {response.text}"
                    if attempt < max_retries - 1:
                        print(f"⚠️ {error_msg}，重试中...")
                        continue
                    else:
                        raise RuntimeError(error_msg)

            except requests.Timeout:
                if attempt < max_retries - 1:
                    print(f"⚠️ API调用超时，重试中...")
                    continue
                else:
                    raise RuntimeError("API调用超时")
            except Exception as e:
                if attempt < max_retries - 1:
                    print(f"⚠️ API调用出错: {e}，重试中...")
                    continue
                else:
                    raise RuntimeError(f"API调用失败: {e}")

    def generate_first_message(self, intent: str) -> str:
        """基于Intent生成第一条用户消息

        Args:
            intent: 用户意图描述

        Returns:
            str: 第一条用户消息

        Raises:
            RuntimeError: API调用失败
        """
        prompt = f"""你是一个需要完成任务的用户。你的任务意图是：

{intent}

请生成你对AI助手说的第一句话，清晰表达你的需求。
只输出这句话，不要包含任何解释或其他内容。"""

        messages = [
            {"role": "user", "content": prompt}
        ]

        return self._call_api(messages)

    def generate_next_message(
        self,
        intent: str,
        conversation_history: List[Dict],
        agent_response: str
    ) -> Dict:
        """根据对话历史和Agent回复，生成下一条用户消息或判断完成

        Args:
            intent: 原始用户意图
            conversation_history: 对话历史（OpenAI格式的消息列表）
            agent_response: Agent的最新回复

        Returns:
            Dict: {
                "completed": bool,  # 是否完成
                "message": str or None,  # 如果未完成，下一条用户消息
                "reason": str  # 完成原因或下一步意图
            }

        Raises:
            RuntimeError: API调用失败
        """
        # 构建对话历史字符串
        history_str = ""
        for msg in conversation_history[-10:]:  # 只保留最近10条
            role = msg["role"]
            content = msg.get("content", "")
            if role == "user":
                history_str += f"用户: {content}\n"
            elif role == "assistant":
                history_str += f"助手: {content}\n"

        prompt = f"""你是一个正在与AI助手对话的用户，你的原始任务意图是：

{intent}

**对话历史**:
{history_str}

**AI助手的最新回复**:
{agent_response}

请判断：
1. 你的任务意图是否已经完成？
2. 如果已完成，回复: {{"completed": true, "reason": "完成原因"}}
3. 如果未完成，生成你的下一句话: {{"completed": false, "message": "你的回复", "reason": "下一步意图"}}

注意：
- 如果助手的回复中包含"success"、"completed"、"成功"、"完成"等词，且任务目标已达成，则应判断为完成
- 如果助手在询问信息，请根据你的意图提供相应信息
- 保持对话自然，像真实用户一样交流

只输出JSON格式，不要包含任何其他内容。"""

        messages = [
            {"role": "user", "content": prompt}
        ]

        response_text = self._call_api(messages)

        # 解析JSON响应
        try:
            # 尝试提取JSON（可能被包裹在```json...```中）
            if "```json" in response_text:
                json_str = response_text.split("```json")[1].split("```")[0].strip()
            elif "```" in response_text:
                json_str = response_text.split("```")[1].split("```")[0].strip()
            else:
                json_str = response_text.strip()

            result = json.loads(json_str)

            # 验证返回格式
            if "completed" not in result:
                raise ValueError("响应缺少completed字段")

            if not result["completed"] and "message" not in result:
                raise ValueError("未完成时必须包含message字段")

            return result

        except (json.JSONDecodeError, ValueError) as e:
            print(f"⚠️ 解析UserModel响应失败: {e}")
            print(f"原始响应: {response_text}")
            # 返回默认的未完成状态，使用原始响应作为消息
            return {
                "completed": False,
                "message": response_text,
                "reason": "解析失败，使用原始响应"
            }

    def check_completion_by_keywords(self, agent_response: str) -> bool:
        """通过关键词检查Agent回复是否表示任务完成

        Args:
            agent_response: Agent的回复文本

        Returns:
            bool: 是否包含完成关键词
        """
        agent_lower = agent_response.lower()
        for keyword in config.COMPLETION_KEYWORDS:
            if keyword.lower() in agent_lower:
                return True
        return False


if __name__ == "__main__":
    # 测试UserModel客户端
    print("=== UserModel客户端测试 ===\n")

    # 检查API Key
    if not config.USERMODEL_CONFIG["api_key"]:
        print("❌ 请设置AZURE_OPENAI_API_KEY环境变量")
        exit(1)

    client = UserModelClient()

    # 测试1: 生成第一条消息
    print("测试1: 生成第一条用户消息...")
    intent = "我想预订从北京到上海的机票，明天出发，经济舱"
    try:
        first_message = client.generate_first_message(intent)
        print(f"✅ 生成成功:")
        print(f"  Intent: {intent}")
        print(f"  消息: {first_message}\n")

        # 测试2: 模拟对话，生成下一条消息
        print("测试2: 生成下一条用户消息...")
        conversation_history = [
            {"role": "user", "content": first_message},
            {"role": "assistant", "content": "好的，我来帮您查询明天北京到上海的经济舱机票。请问您需要单程还是往返？"}
        ]
        agent_response = "好的，我来帮您查询明天北京到上海的经济舱机票。请问您需要单程还是往返？"

        next_step = client.generate_next_message(intent, conversation_history, agent_response)
        print(f"✅ 生成成功:")
        print(f"  完成状态: {next_step['completed']}")
        if not next_step['completed']:
            print(f"  下一条消息: {next_step['message']}")
        print(f"  原因: {next_step['reason']}\n")

        # 测试3: 测试完成判断
        print("测试3: 测试完成判断...")
        completion_responses = [
            "您的机票预订成功！订单号为ABC123",
            "Task completed successfully",
            "已为您完成预订"
        ]
        for response in completion_responses:
            is_completed = client.check_completion_by_keywords(response)
            print(f"  '{response[:30]}...' -> {'完成' if is_completed else '未完成'}")

    except RuntimeError as e:
        print(f"❌ 测试失败: {e}")
    except Exception as e:
        print(f"❌ 测试出错: {e}")
        import traceback
        traceback.print_exc()
