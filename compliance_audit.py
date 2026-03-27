#!/usr/bin/env python3
"""
Nursing Roster Compliance Audit Script
Validates shift data against labor safety standards:
- 12-hour maximum shift duration
- 10-hour minimum rest between shifts
"""

from datetime import datetime, timedelta
from typing import List, Dict, Tuple
import json

# Compliance Criteria
MAX_SHIFT_DURATION_HOURS = 12
MIN_REST_BETWEEN_SHIFTS_HOURS = 10

# Shift Data Structure
# Each shift: (nurse_id, start_datetime, end_datetime)
SHIFT_DATA = [
    # Nurse N001 - Two 12-hour overnight shifts
    ("N001", datetime(2025, 10, 1, 19, 0), datetime(2025, 10, 2, 7, 0)),   # Oct 1-2, 12 hours
    ("N001", datetime(2025, 10, 3, 19, 0), datetime(2025, 10, 4, 7, 0)),   # Oct 3-4, 12 hours
    
    # Nurse N002 - Back-to-back shifts with rest violation
    ("N002", datetime(2025, 10, 2, 22, 0), datetime(2025, 10, 3, 8, 0)),   # Ends Oct 3 at 08:00
    ("N002", datetime(2025, 10, 3, 10, 0), datetime(2025, 10, 3, 20, 0)),  # Starts Oct 3 at 10:00 (only 2hr rest)
    
    # Nurse N003 - Two day shifts (compliant)
    ("N003", datetime(2025, 10, 1, 7, 0), datetime(2025, 10, 1, 19, 0)),   # 12 hours, compliant
    ("N003", datetime(2025, 10, 2, 7, 0), datetime(2025, 10, 2, 19, 0)),   # 12 hours, compliant
]


def calculate_shift_duration(start: datetime, end: datetime) -> float:
    """Calculate shift duration in hours."""
    duration = end - start
    return duration.total_seconds() / 3600


def calculate_rest_period(shift1_end: datetime, shift2_start: datetime) -> float:
    """Calculate rest period between shifts in hours."""
    rest = shift2_start - shift1_end
    return rest.total_seconds() / 3600


def check_shift_duration_violations(shifts: List[Tuple]) -> List[Dict]:
    """Check for shifts exceeding maximum duration."""
    violations = []
    for nurse_id, start, end in shifts:
        duration = calculate_shift_duration(start, end)
        if duration > MAX_SHIFT_DURATION_HOURS:
            violations.append({
                "nurse_id": nurse_id,
                "violation_type": "SHIFT_DURATION_EXCEEDED",
                "shift_start": start.strftime("%Y-%m-%d %H:%M"),
                "shift_end": end.strftime("%Y-%m-%d %H:%M"),
                "duration_hours": duration,
                "limit_hours": MAX_SHIFT_DURATION_HOURS,
                "excess_hours": round(duration - MAX_SHIFT_DURATION_HOURS, 2)
            })
    return violations


def check_rest_period_violations(shifts: List[Tuple]) -> List[Dict]:
    """Check for insufficient rest between consecutive shifts per nurse."""
    violations = []
    
    # Group shifts by nurse
    nurse_shifts: Dict[str, List[Tuple]] = {}
    for nurse_id, start, end in shifts:
        if nurse_id not in nurse_shifts:
            nurse_shifts[nurse_id] = []
        nurse_shifts[nurse_id].append((start, end))
    
    # Sort each nurse's shifts by start time and check rest periods
    for nurse_id, shifts_list in nurse_shifts.items():
        shifts_list.sort(key=lambda x: x[0])
        
        for i in range(len(shifts_list) - 1):
            shift1_end = shifts_list[i][1]
            shift2_start = shifts_list[i + 1][0]
            rest_hours = calculate_rest_period(shift1_end, shift2_start)
            
            if rest_hours < MIN_REST_BETWEEN_SHIFTS_HOURS:
                violations.append({
                    "nurse_id": nurse_id,
                    "violation_type": "INSUFFICIENT_REST_PERIOD",
                    "previous_shift_end": shift1_end.strftime("%Y-%m-%d %H:%M"),
                    "next_shift_start": shift2_start.strftime("%Y-%m-%d %H:%M"),
                    "rest_hours": round(rest_hours, 2),
                    "required_hours": MIN_REST_BETWEEN_SHIFTS_HOURS,
                    "deficit_hours": round(MIN_REST_BETWEEN_SHIFTS_HOURS - rest_hours, 2)
                })
    
    return violations


def generate_compliance_report(duration_violations: List[Dict], rest_violations: List[Dict]) -> str:
    """Generate formal compliance summary report."""
    report_lines = []
    report_lines.append("=" * 70)
    report_lines.append("NURSING ROSTER COMPLIANCE AUDIT REPORT")
    report_lines.append("=" * 70)
    report_lines.append("")
    report_lines.append(f"Audit Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    report_lines.append(f"Reporting Period: October 2025")
    report_lines.append("")
    report_lines.append("COMPLIANCE CRITERIA:")
    report_lines.append(f"  - Maximum Shift Duration: {MAX_SHIFT_DURATION_HOURS} hours")
    report_lines.append(f"  - Minimum Rest Between Shifts: {MIN_REST_BETWEEN_SHIFTS_HOURS} hours")
    report_lines.append("")
    report_lines.append("-" * 70)
    report_lines.append("SUMMARY")
    report_lines.append("-" * 70)
    report_lines.append(f"Total Shifts Analyzed: {len(SHIFT_DATA)}")
    report_lines.append(f"Total Violations Found: {len(duration_violations) + len(rest_violations)}")
    report_lines.append(f"  - Shift Duration Violations: {len(duration_violations)}")
    report_lines.append(f"  - Rest Period Violations: {len(rest_violations)}")
    report_lines.append("")
    
    if duration_violations or rest_violations:
        report_lines.append("-" * 70)
        report_lines.append("VIOLATIONS DETAIL")
        report_lines.append("-" * 70)
        
        if duration_violations:
            report_lines.append("")
            report_lines.append("SHIFT DURATION VIOLATIONS:")
            for i, v in enumerate(duration_violations, 1):
                report_lines.append(f"  [{i}] Nurse ID: {v['nurse_id']}")
                report_lines.append(f"      Shift: {v['shift_start']} to {v['shift_end']}")
                report_lines.append(f"      Duration: {v['duration_hours']} hours (exceeds {v['limit_hours']}h limit)")
                report_lines.append(f"      Excess: {v['excess_hours']} hours")
                report_lines.append("")
        
        if rest_violations:
            report_lines.append("REST PERIOD VIOLATIONS:")
            for i, v in enumerate(rest_violations, 1):
                report_lines.append(f"  [{i}] Nurse ID: {v['nurse_id']}")
                report_lines.append(f"      Previous Shift End: {v['previous_shift_end']}")
                report_lines.append(f"      Next Shift Start: {v['next_shift_start']}")
                report_lines.append(f"      Rest Period: {v['rest_hours']} hours (below {v['required_hours']}h requirement)")
                report_lines.append(f"      Deficit: {v['deficit_hours']} hours")
                report_lines.append("")
    else:
        report_lines.append("-" * 70)
        report_lines.append("STATUS: ALL SHIFTS COMPLIANT")
        report_lines.append("-" * 70)
    
    report_lines.append("-" * 70)
    report_lines.append("RECOMMENDATIONS")
    report_lines.append("-" * 70)
    
    if duration_violations:
        report_lines.append("1. Review scheduling practices to prevent shifts exceeding 12-hour limit")
        report_lines.append("2. Implement automated alerts when shift duration approaches maximum")
    
    if rest_violations:
        report_lines.append("3. Enforce mandatory rest periods between consecutive shifts")
        report_lines.append("4. Add scheduling guardrails to prevent back-to-back assignments")
        report_lines.append("   with insufficient rest periods")
    
    if not duration_violations and not rest_violations:
        report_lines.append("No violations detected. Current scheduling practices are compliant.")
    
    report_lines.append("")
    report_lines.append("=" * 70)
    report_lines.append("END OF REPORT")
    report_lines.append("=" * 70)
    
    return "\n".join(report_lines)


def main():
    """Run compliance audit and generate report."""
    print("Running Nursing Roster Compliance Audit...")
    print(f"  - Maximum Shift Duration: {MAX_SHIFT_DURATION_HOURS} hours")
    print(f"  - Minimum Rest Between Shifts: {MIN_REST_BETWEEN_SHIFTS_HOURS} hours")
    print(f"  - Total Shifts to Analyze: {len(SHIFT_DATA)}")
    print()
    
    # Run compliance checks
    duration_violations = check_shift_duration_violations(SHIFT_DATA)
    rest_violations = check_rest_period_violations(SHIFT_DATA)
    
    # Generate report
    report = generate_compliance_report(duration_violations, rest_violations)
    
    # Save report to file
    report_path = "compliance_report.txt"
    with open(report_path, "w") as f:
        f.write(report)
    
    print(f"Report saved to: {report_path}")
    print()
    print(report)
    
    # Also save violations as JSON for programmatic access
    violations_data = {
        "audit_date": datetime.now().isoformat(),
        "criteria": {
            "max_shift_duration_hours": MAX_SHIFT_DURATION_HOURS,
            "min_rest_between_shifts_hours": MIN_REST_BETWEEN_SHIFTS_HOURS
        },
        "summary": {
            "total_shifts": len(SHIFT_DATA),
            "duration_violations": len(duration_violations),
            "rest_violations": len(rest_violations),
            "total_violations": len(duration_violations) + len(rest_violations)
        },
        "violations": {
            "shift_duration": duration_violations,
            "rest_period": rest_violations
        }
    }
    
    json_path = "violations_data.json"
    with open(json_path, "w") as f:
        json.dump(violations_data, f, indent=2)
    
    print(f"\nViolations data saved to: {json_path}")
    
    return violations_data


if __name__ == "__main__":
    main()
