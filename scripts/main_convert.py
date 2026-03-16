#!/usr/bin/env python3

import argparse
import json
import sys
import os
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Optional, Tuple

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from data_converter import DataConverter
import config


# ── 单文件转换 ─────────────────────────────────────────────── #

def convert_one(
    session_file: str,
    intent: str,
    output_path: str = None,
    system_prompt: str = None,
    status: str = None,
    runtime_tools: Dict = None
) -> Dict:
    """转换单个session文件

    Args:
        session_file: JSONL session文件路径
        intent: 用户意图
        output_path: 输出路径，None自动生成
        system_prompt: 系统提示词（可选）
        status: 强制状态（可选）
        runtime_tools: 运行时工具schema（来自LoopManager结果，优先级最高）

    Returns:
        Dict: {
            "success": bool,
            "output_path": str,
            "session_id": str,
            "error": str (if failed)
        }
    """
    converter = DataConverter(runtime_tools=runtime_tools)

    try:
        mid_data = converter.convert_session_to_mid_format(
            session_file, intent,
            system_prompt=system_prompt,
            status=status
        )

        # 输出路径
        if output_path is None:
            session_id = mid_data["session_id"]
            os.makedirs(config.CONVERTED_DIR, exist_ok=True)
            output_path = os.path.join(config.CONVERTED_DIR, f"{session_id}.json")

        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(mid_data, f, ensure_ascii=False, indent=2)

        return {
            "success": True,
            "output_path": output_path,
            "session_id": mid_data["session_id"],
            "status": mid_data["status"],
            "total_steps": mid_data["total_steps"]
        }

    except Exception as e:
        return {
            "success": False,
            "output_path": "",
            "session_id": os.path.basename(session_file).replace(".jsonl", ""),
            "error": str(e)
        }


# ── 批量转换（从 batch_summary）────────────────────────────── #

def convert_from_summary(
    summary_file: str,
    output_dir: str = None,
    concurrent: int = 1
) -> List[Dict]:
    """从 main_loop.py 生成的 batch_summary 批量转换

    Args:
        summary_file: batch_summary.json 路径
        output_dir: 输出目录
        concurrent: 并发数

    Returns:
        List[Dict]: 每个文件的转换结果
    """
    with open(summary_file, 'r', encoding='utf-8') as f:
        summary = json.load(f)

    session_files = summary.get("session_files", [])
    if not session_files:
        print("⚠️ summary 文件中没有 session_files 记录")
        return []

    print(f"从 summary 读取到 {len(session_files)} 个session")

    tasks: List[Tuple[str, str]] = []
    for item in session_files:
        sf = item.get("session_file") or item.get("session_file_path", "")
        intent = item.get("intent", "未知意图")
        if sf and os.path.exists(sf):
            tasks.append((sf, intent))
        else:
            # 尝试从backup目录找
            sid = item.get("session_id", "")
            backup = os.path.join(config.SESSIONS_BACKUP_DIR, f"{sid}.jsonl")
            if sid and os.path.exists(backup):
                tasks.append((backup, intent))
            else:
                print(f"⚠️ session文件不存在，跳过: {sf}")

    return _run_batch(tasks, output_dir or config.CONVERTED_DIR, concurrent)


# ── 批量转换（目录扫描）────────────────────────────────────── #

def convert_from_dir(
    session_dir: str,
    output_dir: str = None,
    intent_mapping: Dict[str, str] = None,
    default_intent: str = "未知意图",
    concurrent: int = 1
) -> List[Dict]:
    """扫描目录批量转换

    Args:
        session_dir: session文件目录
        output_dir: 输出目录
        intent_mapping: {session_id: intent} 映射
        default_intent: 没有映射时使用的默认intent
        concurrent: 并发数

    Returns:
        List[Dict]: 转换结果
    """
    intent_mapping = intent_mapping or {}

    jsonl_files = [
        os.path.join(session_dir, f)
        for f in os.listdir(session_dir)
        if f.endswith(".jsonl") and not f.endswith(".reset.jsonl")
    ]

    if not jsonl_files:
        print(f"⚠️ 目录中没有 .jsonl 文件: {session_dir}")
        return []

    print(f"扫描到 {len(jsonl_files)} 个session文件")

    tasks = []
    for sf in jsonl_files:
        sid = os.path.basename(sf).replace(".jsonl", "")
        intent = intent_mapping.get(sid, default_intent)
        tasks.append((sf, intent))

    return _run_batch(tasks, output_dir or config.CONVERTED_DIR, concurrent)


def _run_batch(
    tasks: List[Tuple[str, str]],
    output_dir: str,
    concurrent: int
) -> List[Dict]:
    """内部批量执行"""
    results = []
    os.makedirs(output_dir, exist_ok=True)

    def do_one(sf, intent):
        sid = os.path.basename(sf).replace(".jsonl", "")
        out = os.path.join(output_dir, f"{sid}.json")
        return convert_one(sf, intent, output_path=out)

    if concurrent <= 1:
        for i, (sf, intent) in enumerate(tasks, 1):
            print(f"[{i}/{len(tasks)}] 转换: {os.path.basename(sf)}")
            r = do_one(sf, intent)
            results.append(r)
            print(f"  {'✅' if r['success'] else '❌'} {r.get('output_path', r.get('error', ''))}")
    else:
        with ThreadPoolExecutor(max_workers=concurrent) as executor:
            future_map = {
                executor.submit(do_one, sf, intent): (i, sf)
                for i, (sf, intent) in enumerate(tasks, 1)
            }
            for future in as_completed(future_map):
                i, sf = future_map[future]
                try:
                    r = future.result()
                    results.append(r)
                    status = "✅" if r["success"] else "❌"
                    print(f"[{i}/{len(tasks)}] {status} {os.path.basename(sf)}")
                except Exception as e:
                    print(f"[{i}/{len(tasks)}] ❌ 异常: {e}")
                    results.append({"success": False, "error": str(e)})

    return results


def save_convert_summary(results: List[Dict], output_path: str = None, run_name: str = None) -> str:
    """保存转换汇总"""
    if output_path is None:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        name = f"convert_summary_{run_name}_{ts}" if run_name else f"convert_summary_{ts}"
        output_path = os.path.join(config.LOGS_DIR, f"{name}.json")

    total = len(results)
    success = sum(1 for r in results if r.get("success"))

    summary = {
        "timestamp": datetime.now().isoformat(),
        "total": total,
        "success": success,
        "failed": total - success,
        "converted_files": [r["output_path"] for r in results if r.get("success")],
        "results": results
    }

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    print(f"\n{'═' * 60}")
    print(f"转换汇总: 成功 {success}/{total}")
    print(f"汇总文件: {output_path}")
    print(f"{'═' * 60}\n")

    return output_path


# ── 主程序 ─────────────────────────────────────────────────── #

def main():
    parser = argparse.ArgumentParser(
        description="Part 2: Session文件转换为mid_format格式"
    )

    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--session", type=str, help="单个session JSONL文件路径")
    group.add_argument("--summary", type=str, help="batch_summary.json 路径（自动转换其中所有session）")
    group.add_argument("--session-dir", type=str, help="session文件目录（批量扫描）")

    parser.add_argument("--intent", type=str, help="用户意图（单文件模式必填）")
    parser.add_argument("--intent-mapping", type=str, help="JSON文件：{session_id: intent}")
    parser.add_argument("--output", type=str, help="输出路径或目录")
    parser.add_argument("--concurrent", type=int, default=1, help="并发数（默认1）")

    args = parser.parse_args()
    config.ensure_dirs()

    # ── 单文件 ──
    if args.session:
        if not args.intent:
            print("❌ 单文件模式需要 --intent 参数")
            sys.exit(1)
        if not os.path.exists(args.session):
            print(f"❌ 文件不存在: {args.session}")
            sys.exit(1)

        # 自动推断输出目录：session在testN下 → converted也用testN
        if args.output:
            out_path = args.output
        else:
            import re
            m = re.search(r'(test\d+)', args.session)
            if m:
                run_name = m.group(1)
                out_dir = os.path.join(config.CONVERTED_ROOT, run_name)
            else:
                out_dir = config.CONVERTED_ROOT
            os.makedirs(out_dir, exist_ok=True)
            sid = os.path.basename(args.session).replace('.jsonl', '')
            out_path = os.path.join(out_dir, f"{sid}.json")

        r = convert_one(args.session, args.intent, output_path=out_path)
        if r["success"]:
            print(f"✅ 转换成功: {r['output_path']}")
        else:
            print(f"❌ 转换失败: {r.get('error')}")
            sys.exit(1)

    # ── 从summary批量 ──
    elif args.summary:
        if not os.path.exists(args.summary):
            print(f"❌ summary文件不存在: {args.summary}")
            sys.exit(1)

        # 从summary文件名提取run_name（如 batch_summary_test1_xxx.json → test1）
        import re
        summary_base = os.path.basename(args.summary)
        run_name_match = re.search(r'batch_summary_(test\d+)_', summary_base)
        if run_name_match:
            run_name = run_name_match.group(1)
            output_dir = args.output or os.path.join(config.CONVERTED_ROOT, run_name)
        else:
            # fallback: 自动生成新的testN目录
            output_dir = args.output or config.get_next_run_dir(config.CONVERTED_ROOT)
            run_name = os.path.basename(output_dir)

        print(f"输出目录: {output_dir}")
        results = convert_from_summary(
            args.summary,
            output_dir=output_dir,
            concurrent=args.concurrent
        )
        save_convert_summary(results, run_name=run_name)

    # ── 目录批量 ──
    elif args.session_dir:
        if not os.path.isdir(args.session_dir):
            print(f"❌ 目录不存在: {args.session_dir}")
            sys.exit(1)

        # 加载intent映射
        intent_mapping = {}
        if args.intent_mapping:
            try:
                with open(args.intent_mapping, 'r', encoding='utf-8') as f:
                    intent_mapping = json.load(f)
            except Exception as e:
                print(f"⚠️ 加载intent映射失败: {e}")

        results = convert_from_dir(
            args.session_dir,
            output_dir=args.output,
            intent_mapping=intent_mapping,
            default_intent=args.intent or "未知意图",
            concurrent=args.concurrent
        )
        save_convert_summary(results)


if __name__ == "__main__":
    main()
