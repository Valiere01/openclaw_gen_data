# Spray Validation Summary

**Date:** 2026-03-28  
**Analysis Type:** IoT Irrigation Logic Pipeline Test  
**Project:** Sub-Saharan Pilot Farms - Water Conservation Analysis  

---

## Video Source

| Field | Value |
|-------|-------|
| Source URL | `http://commondatastorage.googleapis.com/gtv-videos-bucket/sample/ForBiggerBlazes.mp4` |
| Original Duration | 15.02 seconds |
| Resolution | 1280x720 (720p) |
| FPS | 23.98 |

---

## Extracted Segment

| Field | Value |
|-------|-------|
| Requested Timestamp Range | 00:30 - 00:45 (15 seconds) |
| Actual Timestamp Range | 00:00.5 - 00:15.0 (14.5 seconds) |
| Reason for Adjustment | Source video duration was only 15.02 seconds; full content extracted |
| Output File | `ForBiggerBlazes_nozzle_segment.mp4` |
| Output Path | `/mnt/afs_toolcall/luosiyuan/.openclaw/workspaces/gendata-worker-47/ForBiggerBlazes_nozzle_segment.mp4` |
| File Size | 2.1 MB |

---

## Analysis Notes

### ⚠️ Source Limitation

**This was a pipeline workflow test.** The video source is a Google sample video bucket, not actual drone surveillance footage from the Sub-Saharan pilot farms. The content does not represent real irrigation nozzle spray patterns.

### Pipeline Validation Status

- [x] Video download from URL
- [x] Video segment extraction (ffmpeg/MoviePy)
- [x] Output file generation
- [ ] Repository integration (smart-farming-core) — **Blocked**: `git.internal.example.com` unreachable (HTTP 500)
- [ ] Actual field footage analysis — **Pending**: Awaiting real drone surveillance data

---

## Next Steps

1. **Obtain correct video source** — Replace with actual drone footage from pilot farms
2. **Resolve repository access** — Verify `smart-farming-core` git URL and credentials
3. **Run full analysis pipeline** — Process real nozzle spray patterns against IoT irrigation logic
4. **Generate conservation metrics** — Compare spray patterns against water usage targets

---

## Files Generated

```
/mnt/afs_toolcall/luosiyuan/.openclaw/workspaces/gendata-worker-47/
├── ForBiggerBlazes_nozzle_segment.mp4  (extracted clip)
└── spray_validation_summary.md         (this document)
```

---

*Document generated as part of irrigation logic validation workflow test.*
