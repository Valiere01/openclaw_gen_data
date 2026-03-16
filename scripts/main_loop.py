#!/usr/bin/env python3

import argparse
import json
import sys
import os
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'src'))

from loop_manager import LoopManager
import config

# ── 2条测试intent（用于并发测试）──────────────────────────────────────────── #
DEFAULT_TEST_INTENTS = [
    "请帮我查看当前工作目录下有哪些文件，并告诉我其中有几个Python文件",
    "帮我创建一个名为hello.txt的文件，内容是'Hello, World!'，然后读取并确认内容",
]


# ── 单任务执行 ─────────────────────────────────────────────── #

def fetch_shared_tools_schema(tools_file: str = None) -> Dict:
    """批量运行开始前fetch一次工具schema，供所有intent共享

    Args:
        tools_file: 保存路径，None则不持久化

    Returns:
        Dict: {tool_name: tool_object}

    Raises:
        RuntimeError: 获取工具列表失败（不允许继续）
    """
    import subprocess
    import json
    
    print("🔧 获取工具列表（共享）...")
    dump_script = "/Users/luosiyuan/openclaw_proj/openclaw_gen_data/tools/fetch_tools/dump_tools.mjs"
    
    try:
        result = subprocess.run(
            ["node", dump_script],
            capture_output=True,
            text=True,
            timeout=10
        )
        if result.returncode != 0:
            raise RuntimeError(f"dump_tools.mjs 失败: {result.stderr}")
        
        tools_list = json.loads(result.stdout)
        if not isinstance(tools_list, list) or len(tools_list) == 0:
            raise RuntimeError("dump_tools.mjs 返回空列表")
        
        # 转换为 {name: tool_object} 字典
        tools_schema = {}
        for t in tools_list:
            name = t.get("function", ).get("name") if "function" in t else t.get("name")
            if name:
                tools_schema[name] = t
        
        n = len(tools_schema)
        print(f"   ✅ 获取到 {n} 个工具")
        
        # 持久化
        if tools_file:
            os.makedirs(os.path.dirname(tools_file), exist_ok=True)
            with open(tools_file, 'w', encoding='utf-8') as f:
                json.dump(tools_list, f, ensure_ascii=False, indent=2)
            print(f"   💾 已保存: {tools_file}")
        print()
        return tools_schema
        
    except Exception as e:
        raise RuntimeError(f"❌ 获取工具列表失败，终止运行: {e}") from e


def run_single_intent(intent: str, max_iterations: int = None, run_dirs: Dict = None,
                      tools_schema: Dict = None) -> Dict:
    """运行单个intent的对话循环"""
    manager = LoopManager(
        max_iterations=max_iterations,
        run_dir=run_dirs["sessions"] if run_dirs else None,
        logs_dir=run_dirs["logs"] if run_dirs else None,
        tools_schema=tools_schema
    )
    result = manager.run_conversation_loop(intent)
    if result["success"]:
        manager.save_result(result)
    return result


def run_batch_intents(
    intents: List[str],
    concurrent: int = 1,
    max_iterations: int = None,
    run_dirs: Dict = None
) -> List[Dict]:
    """批量运行 intents，支持并发"""
    results = []
    run_dir = run_dirs["sessions"] if run_dirs else config.SESSIONS_BACKUP_ROOT
    tools_file = run_dirs["tools_file"] if run_dirs else None

    # 批量运行开始前 fetch 一次工具schema，所有任务共享
    tools_schema = fetch_shared_tools_schema(tools_file=tools_file)

    if concurrent <= 1:
        for i, intent in enumerate(intents, 1):
            print(f"\n{'═' * 70}")
            print(f"[{i}/{len(intents)}] {intent[:60]}")
            print(f"{'═' * 70}")
            result = run_single_intent(intent, max_iterations, run_dirs, tools_schema)
            results.append(result)
    else:
        print(f"\n{'═' * 70}")
        print(f"并发模式: {len(intents)} 个任务，并发数 {concurrent}")
        print(f"{'═' * 70}\n")

        with ThreadPoolExecutor(max_workers=concurrent) as executor:
            future_map = {
                executor.submit(run_single_intent, intent, max_iterations, run_dirs, tools_schema): (i, intent)
                for i, intent in enumerate(intents, 1)
            }
            for future in as_completed(future_map):
                i, intent = future_map[future]
                try:
                    result = future.result()
                    results.append(result)
                    status = "✅" if result["success"] else "❌"
                    done = "完成" if result.get("completed") else "未完成"
                    print(f"[{i}/{len(intents)}] {status} {done} | 轮次:{result.get('total_turns',0)} | {intent[:40]}...")
                except Exception as e:
                    print(f"[{i}/{len(intents)}] ❌ 异常: {e}")
                    results.append({
                        "success": False,
                        "intent": intent,
                        "reason": f"异常: {str(e)}",
                        "total_turns": 0,
                        "completed": False
                    })
    return results


# ── 批量汇总 ───────────────────────────────────────────────── #

def save_batch_summary(results: List[Dict], output_path: str = None, run_dirs: Dict = None) -> str:
    """保存批量运行汇总"""
    if output_path is None:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        logs_dir = run_dirs["logs"] if run_dirs else config.LOGS_ROOT
        run_name = os.path.basename(run_dirs["sessions"]) if run_dirs else ""
        name = f"batch_summary_{run_name}_{ts}" if run_name else f"batch_summary_{ts}"
        output_path = os.path.join(logs_dir, f"{name}.json")

    total = len(results)
    success = sum(1 for r in results if r.get("success"))
    completed = sum(1 for r in results if r.get("completed"))
    avg_turns = (
        sum(r.get("total_turns", 0) for r in results) / total
        if total > 0 else 0
    )

    # session文件列表（供Part 2使用）
    session_files = [
        {
            "session_id":    r.get("session_id", ""),
            "session_file":  r.get("backup_file_path") or r.get("session_file_path", ""),
            "intent":        r.get("intent", ""),
            "completed":     r.get("completed", False),
            "total_turns":   r.get("total_turns", 0)
        }
        for r in results if r.get("session_id")
    ]

    summary = {
        "timestamp": datetime.now().isoformat(),
        "total": total,
        "success": success,
        "completed": completed,
        "failed": total - success,
        "average_turns": round(avg_turns, 2),
        "session_files": session_files,
        "results": results
    }

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    print(f"\n{'═' * 70}")
    print(f"批量运行汇总")
    print(f"  总数: {total} | 成功: {success} | 完成: {completed} | 失败: {total - success}")
    print(f"  平均轮次: {avg_turns:.1f}")
    print(f"  汇总文件: {output_path}")
    print(f"{'═' * 70}\n")

    return output_path


# ── 主程序 ─────────────────────────────────────────────────── #

def main():
    parser = argparse.ArgumentParser(
        description="Part 1: Agent-UserModel 循环系统 —— 生成Session文件"
    )

    group = parser.add_mutually_exclusive_group()
    group.add_argument("--intent", type=str, help="单个用户意图")
    group.add_argument("--intents-file", type=str, help="批量intent文件（每行一个）")
    group.add_argument(
        "--test",
        action="store_true",
        help=f"使用内置的 {len(DEFAULT_TEST_INTENTS)} 条测试intent"
    )

    parser.add_argument(
        "--max-iterations",
        type=int,
        default=config.MAX_ITERATIONS,
        help=f"最大交互轮次 (默认: {config.MAX_ITERATIONS})"
    )
    parser.add_argument(
        "--concurrent",
        type=int,
        default=1,
        help="并发数 (仅批量模式，默认: 1)"
    )
    parser.add_argument("--output", type=str, help="输出文件路径（可选）")

    args = parser.parse_args()

    # 如果没有指定任何模式，默认使用 --test
    if not args.intent and not args.intents_file and not args.test:
        args.test = True

    # 配置检查
    is_valid, error_msg = config.validate_config()
    if not is_valid:
        print(f"❌ 配置错误: {error_msg}")
        sys.exit(1)
    config.ensure_dirs()

    # 确定本次运行编号（以sessions目录为准，其余目录同步）
    run_name = os.path.basename(config.get_next_run_dir(config.SESSIONS_BACKUP_ROOT))

    # ── 单个intent ──
    if args.intent:
        run_dirs = config.ensure_run_dirs(run_name)
        print(f"模式: 单个Intent | 运行目录: {run_name}\nIntent: {args.intent}\n")
        result = run_single_intent(args.intent, args.max_iterations,
                                   run_dirs=run_dirs)
        if result["success"]:
            print(f"\n✅ 完成！Session: {result['session_id']}")
        else:
            print(f"\n❌ 失败: {result['reason']}")
            sys.exit(1)

    # ── 批量文件 ──
    elif args.intents_file:
        try:
            with open(args.intents_file, 'r', encoding='utf-8') as f:
                intents = [l.strip() for l in f if l.strip()]
        except FileNotFoundError:
            print(f"❌ 文件不存在: {args.intents_file}")
            sys.exit(1)
        if not intents:
            print("❌ 文件中没有有效intent")
            sys.exit(1)

        run_dirs = config.ensure_run_dirs(run_name)
        print(f"模式: 批量 ({len(intents)} 个intent, 并发:{args.concurrent}) | 运行目录: {run_name}\n")
        results = run_batch_intents(intents, min(args.concurrent, config.MAX_CONCURRENT),
                                    args.max_iterations, run_dirs)
        save_batch_summary(results, args.output, run_dirs=run_dirs)

    # ── 测试模式 ──
    elif args.test:
        run_dirs = config.ensure_run_dirs(run_name)
        print(f"模式: 测试 ({len(DEFAULT_TEST_INTENTS)} 条内置intent) | 运行目录: {run_name}\n")
        for i, intent in enumerate(DEFAULT_TEST_INTENTS, 1):
            print(f"  [{i}] {intent}")
        print()
        results = run_batch_intents(DEFAULT_TEST_INTENTS,
                                    min(args.concurrent, config.MAX_CONCURRENT),
                                    args.max_iterations, run_dirs)
        save_batch_summary(results, args.output, run_dirs=run_dirs)


if __name__ == "__main__":
    main()
