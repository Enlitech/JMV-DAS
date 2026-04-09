# JMV-DAS Recording Format

This document describes the on-disk format used by JMV-DAS for waterfall recording sessions and snapshots.

It is intended for:

- customers who want to understand what is stored,
- engineers who want to parse the saved files,
- future tools that may replay or convert recorded data.

## 1. Overview

JMV-DAS stores recorded data as a session directory containing:

- session-level metadata,
- one raw waterfall data file per recorded callback block,
- one JSON metadata file per raw block,
- an append-only JSON Lines index,
- optional snapshots saved during the session,
- a session summary written when recording stops.

The format is intentionally simple:

- numeric waterfall arrays are stored as NumPy `.npy`,
- metadata is stored as UTF-8 JSON text,
- each callback block is stored independently.

## 2. Default Location

By default, recordings are written under:

```text
<project-root>/recordings/
```

The actual output root can be changed in the application UI through `Recording Output Folder`.

## 3. Session Directory Layout

Each recording session creates a directory named with local start time:

```text
YYYY-MM-DD_HH-MM-SS
```

Example:

```text
recordings/
  2026-04-09_14-32-18/
    session.json
    summary.json
    chunks/
      index.jsonl
      ch1_amp_000001.npy
      ch1_amp_000001.json
      ch1_amp_000002.npy
      ch1_amp_000002.json
    snapshots/
      snapshot_2026-04-09_14-33-02.png
      snapshot_2026-04-09_14-33-02_values.npy
      snapshot_2026-04-09_14-33-02_row_times.npy
      snapshot_2026-04-09_14-33-02_meta.json
```

Notes:

- `summary.json` is written only after recording is stopped normally.
- `snapshots/` may remain empty if no snapshot is saved during the session.
- If a snapshot is saved while no recording session is active, it is written under:

```text
<recording-output-root>/snapshots_only/snapshots/
```

## 4. Recording Modes and Scope

The saved content depends on two UI settings.

### Recording Mode

Available values:

- `selected`
- `all`

Meaning:

- `selected`: record only the currently selected `channel/kind`.
- `all`: record every incoming stream delivered to the application.

### Recording Scope

Available values:

- `full`
- `filtered`

Meaning:

- `full`: store the full spatial block width received from acquisition.
- `filtered`: store only the currently configured waterfall distance range.

When `filtered` is used, the chunk metadata includes a `range_filter` object describing the cropped interval.

## 5. Session Metadata: `session.json`

Path:

```text
<session-dir>/session.json
```

Purpose:

- describes how the session started,
- stores static settings that are needed to interpret the session.

Example:

```json
{
  "kind": "waterfall_recording_session",
  "started_at_epoch_s": 1775716338.418259,
  "started_at_local": "2026-04-09 14:32:18",
  "started_at_utc": "2026-04-09 06:32:18 UTC",
  "recording_mode": "selected",
  "metadata": {
    "machine_id": "JMV-XXXXXXXXXXXX",
    "selected_stream": {
      "channel": 1,
      "kind": "amp"
    },
    "acquisition": {
      "scan_rate": "10k",
      "mode": "Coherent Suppression",
      "pulse_width": 100,
      "scale_down": 10
    },
    "transform": {
      "mode": "Energy (MSE dB)",
      "energy_win": 32,
      "vmin": -30.0,
      "vmax": 30.0,
      "gamma": 1.0,
      "eps": 1e-06,
      "invert": false
    },
    "waterfall": {
      "history_seconds_target": 10.0,
      "history_seconds_effective": 10.8,
      "history_lines_per_row": 3,
      "history_rows": 600,
      "range_filter_enabled": true,
      "range_start_m": 100.0,
      "range_end_m": 200.0,
      "range_start_col": 24,
      "range_end_col": 50,
      "source_point_count": 1000,
      "filtered_point_count": 26
    },
    "recording_scope": "filtered"
  }
}
```

### Session Metadata Fields

| Field | Type | Meaning |
| --- | --- | --- |
| `kind` | string | Always `waterfall_recording_session` |
| `started_at_epoch_s` | number | Unix epoch seconds |
| `started_at_local` | string | Human-readable local wall-clock time |
| `started_at_utc` | string | Human-readable UTC time |
| `recording_mode` | string | `selected` or `all` |
| `metadata` | object | Session configuration snapshot from the UI |

### `metadata.selected_stream`

Only meaningful when `recording_mode` is `selected`.

| Field | Type | Meaning |
| --- | --- | --- |
| `channel` | integer | Acquisition channel number |
| `kind` | string | `amp` or `phase` |

### `metadata.acquisition`

| Field | Type | Meaning |
| --- | --- | --- |
| `scan_rate` | string | UI scan rate label such as `10k` |
| `mode` | string | Acquisition mode label |
| `pulse_width` | integer | Configured pulse width |
| `scale_down` | integer | Spatial scale-down factor |

### `metadata.transform`

| Field | Type | Meaning |
| --- | --- | --- |
| `mode` | string | Current waterfall transform mode |
| `energy_win` | integer | Rolling energy window |
| `vmin` | number | Lower display normalization bound |
| `vmax` | number | Upper display normalization bound |
| `gamma` | number | Display gamma |
| `eps` | number | Numerical epsilon for transform |
| `invert` | boolean | Invert display mapping |

### `metadata.waterfall`

| Field | Type | Meaning |
| --- | --- | --- |
| `history_seconds_target` | number | Requested waterfall history duration |
| `history_seconds_effective` | number | Effective history after scan-rate-dependent compression |
| `history_lines_per_row` | integer | Number of raw time lines merged into one display row |
| `history_rows` | integer | Fixed display buffer height |
| `range_filter_enabled` | boolean | Whether distance filtering is enabled |
| `range_start_m` | number | Filter start distance in meters |
| `range_end_m` | number | Filter end distance in meters |
| `range_start_col` | integer | Absolute source start column |
| `range_end_col` | integer | Absolute source end column, exclusive |
| `source_point_count` | integer | Original block width before optional cropping |
| `filtered_point_count` | integer | Saved/displayed block width after cropping |

### `metadata.recording_scope`

| Value | Meaning |
| --- | --- |
| `full` | Save full incoming block width |
| `filtered` | Save only the configured range-filter interval |

## 6. Raw Chunk Files

Each recorded callback block produces:

- one `.npy` file containing raw numeric data,
- one `.json` file containing metadata for that block.

### File Name Pattern

```text
ch<channel>_<kind>_<seq:06d>.npy
ch<channel>_<kind>_<seq:06d>.json
```

Examples:

```text
ch1_amp_000001.npy
ch1_amp_000001.json
ch2_phase_000123.npy
ch2_phase_000123.json
```

### Sequence Number

- `seq` is monotonically increasing within the session.
- It is assigned when the payload is accepted for recording.
- It is not reset per stream.

## 7. Chunk Array File: `.npy`

Purpose:

- stores the raw waterfall callback block as a 2D numeric array.

Array type:

- `float32`

Array shape:

```text
(cb_lines, point_count)
```

Meaning:

- axis 0: time lines within the callback block,
- axis 1: spatial columns within the stored spatial interval.

Important note:

- If `recording_scope = full`, `point_count` is the full received block width.
- If `recording_scope = filtered`, `point_count` is the cropped width only.

Python example:

```python
import numpy as np

block = np.load("ch1_amp_000001.npy")
print(block.dtype)   # float32
print(block.shape)   # (cb_lines, point_count)
```

## 8. Chunk Metadata File: `.json`

Path example:

```text
chunks/ch1_amp_000001.json
```

Example:

```json
{
  "seq": 1,
  "channel": 1,
  "kind": "amp",
  "ts": 1775716339.103944,
  "ts_local": "2026-04-09 14:32:19",
  "ts_utc": "2026-04-09 06:32:19 UTC",
  "cfg_scan_rate": "10k",
  "cfg_mode": "Coherent Suppression",
  "cfg_pulse_width": 100,
  "cfg_scale_down": 10,
  "cb_lines": 64,
  "point_count": 26,
  "shape": [64, 26],
  "range_filter": {
    "enabled": true,
    "start_m": 100.0,
    "end_m": 200.0,
    "start_col": 24,
    "end_col": 50,
    "source_point_count": 1000,
    "filtered_point_count": 26
  }
}
```

### Chunk Metadata Fields

| Field | Type | Meaning |
| --- | --- | --- |
| `seq` | integer | Session-global sequence number |
| `channel` | integer | Acquisition channel number |
| `kind` | string | `amp` or `phase` |
| `ts` | number | Block end time in Unix epoch seconds |
| `ts_local` | string | Local wall-clock rendering of `ts` |
| `ts_utc` | string | UTC rendering of `ts` |
| `cfg_scan_rate` | string | Acquisition scan-rate label |
| `cfg_mode` | string | Acquisition mode label |
| `cfg_pulse_width` | integer | Acquisition pulse width |
| `cfg_scale_down` | integer | Scale-down used by acquisition and distance mapping |
| `cb_lines` | integer | Number of lines in the callback block |
| `point_count` | integer | Stored block width in columns |
| `shape` | integer[] | Same information as the `.npy` array shape |

### Optional `range_filter`

This object is present when the payload carries range-filter information.

This happens in two cases:

- recording scope is `filtered`,
- or the UI range filter is enabled and the application intentionally preserves the active filter metadata even if the filtered width equals the full width.

Fields:

| Field | Type | Meaning |
| --- | --- | --- |
| `enabled` | boolean | Whether range filtering was enabled |
| `start_m` | number | Filter start distance |
| `end_m` | number | Filter end distance |
| `start_col` | integer | Absolute source start column |
| `end_col` | integer | Absolute source end column, exclusive |
| `source_point_count` | integer | Full original block width |
| `filtered_point_count` | integer | Stored cropped width |

## 9. Chunk Index File: `index.jsonl`

Path:

```text
<session-dir>/chunks/index.jsonl
```

Purpose:

- append-only flat index of chunk metadata,
- useful for sequential parsing without opening every `.json` file separately.

Format:

- UTF-8 text,
- one compact JSON object per line,
- each line contains the same metadata content as the corresponding chunk `.json`.

Example:

```json
{"seq":1,"channel":1,"kind":"amp","ts":1775716339.103944,"ts_local":"2026-04-09 14:32:19","ts_utc":"2026-04-09 06:32:19 UTC","cfg_scan_rate":"10k","cfg_mode":"Coherent Suppression","cfg_pulse_width":100,"cfg_scale_down":10,"cb_lines":64,"point_count":26,"shape":[64,26],"range_filter":{"enabled":true,"start_m":100.0,"end_m":200.0,"start_col":24,"end_col":50,"source_point_count":1000,"filtered_point_count":26}}
```

## 10. Session Summary: `summary.json`

Path:

```text
<session-dir>/summary.json
```

Purpose:

- records final counters and stop time after recording ends.

Example:

```json
{
  "recording_mode": "selected",
  "session_dir": "/path/to/recordings/2026-04-09_14-32-18",
  "written_blocks": 153,
  "written_bytes": 9685320,
  "dropped_blocks": 0,
  "last_error": "",
  "last_snapshot": "/path/to/recordings/2026-04-09_14-32-18/snapshots/snapshot_2026-04-09_14-33-02.png",
  "stopped_at_epoch_s": 1775716402.019844,
  "stopped_at_local": "2026-04-09 14:33:22",
  "stopped_at_utc": "2026-04-09 06:33:22 UTC"
}
```

### Summary Fields

| Field | Type | Meaning |
| --- | --- | --- |
| `recording_mode` | string | `selected` or `all` |
| `session_dir` | string | Absolute session path |
| `written_blocks` | integer | Number of chunk files successfully written |
| `written_bytes` | integer | Approximate total size of `.npy` + `.json` chunk files |
| `dropped_blocks` | integer | Number of blocks dropped due to queue pressure |
| `last_error` | string | Last writer-thread error, if any |
| `last_snapshot` | string | Last snapshot PNG path, if any |
| `stopped_at_epoch_s` | number | Stop time in Unix epoch seconds |
| `stopped_at_local` | string | Stop time in local time |
| `stopped_at_utc` | string | Stop time in UTC |

## 11. Snapshot Files

Snapshots are optional and can be saved during or outside a recording session.

For each snapshot, the application may create:

- one rendered PNG image,
- one raw values `.npy`,
- one row-times `.npy`,
- one metadata `.json`.

### Snapshot File Set

```text
snapshot_<local-time>.png
snapshot_<local-time>_values.npy
snapshot_<local-time>_row_times.npy
snapshot_<local-time>_meta.json
```

Example:

```text
snapshot_2026-04-09_14-33-02.png
snapshot_2026-04-09_14-33-02_values.npy
snapshot_2026-04-09_14-33-02_row_times.npy
snapshot_2026-04-09_14-33-02_meta.json
```

### Snapshot PNG

Purpose:

- stores the rendered waterfall image exactly as saved from the UI.

### Snapshot Values Array

Type:

- `float32`

Shape:

```text
(history_rows, filtered_point_count)
```

Meaning:

- raw numeric values aligned with the current waterfall display buffer.
- may contain `NaN` entries for rows that are not yet populated.

### Snapshot Row Times Array

Type:

- `float64`

Shape:

```text
(history_rows,)
```

Meaning:

- per-row wall-clock timestamps aligned with the waterfall display rows.
- may contain `NaN` entries for rows that are not yet populated.

### Snapshot Metadata: `_meta.json`

Purpose:

- stores the exact UI and waterfall state at the time of the snapshot.

Example:

```json
{
  "machine_id": "JMV-XXXXXXXXXXXX",
  "selected_stream": {
    "channel": 1,
    "kind": "amp"
  },
  "acquisition": {
    "scan_rate": "10k",
    "mode": "Coherent Suppression",
    "pulse_width": 100,
    "scale_down": 10
  },
  "transform": {
    "mode": "Energy (MSE dB)",
    "energy_win": 32,
    "vmin": -30.0,
    "vmax": 30.0,
    "gamma": 1.0,
    "eps": 1e-06,
    "invert": false
  },
  "recording_scope": "filtered",
  "saved_at_epoch_s": 1775716382.501125,
  "saved_at_local": "2026-04-09 14:33:02.501",
  "saved_at_utc": "2026-04-09 06:33:02.501 UTC",
  "waterfall": {
    "channel": 1,
    "kind": "amp",
    "source_width": 26,
    "source_height": 600,
    "view_start_col": 0,
    "view_col_count": 26,
    "absolute_view_start_col": 24,
    "scale_down": 10,
    "ts_col": 5,
    "absolute_ts_col": 29,
    "history_seconds_target": 10.0,
    "history_seconds_effective": 10.8,
    "history_lines_per_row": 3,
    "history_rows": 600,
    "range_filter_enabled": true,
    "range_start_m": 100.0,
    "range_end_m": 200.0,
    "range_start_col": 24,
    "range_end_col": 50,
    "source_point_count": 1000,
    "filtered_point_count": 26
  }
}
```

### Snapshot Metadata Notes

- `source_width` is the width of the current display buffer after optional range filtering.
- `absolute_view_start_col` and `absolute_ts_col` map the current UI state back to original source coordinates.
- Snapshot metadata preserves enough information to reproduce the visible waterfall region and selected distance position.

## 12. Time Semantics

Several time fields appear in the recording format.

### `ts`

In chunk metadata:

- `ts` is the block end time associated with the received payload,
- stored as Unix epoch seconds,
- represented again as `ts_local` and `ts_utc`.

### `row_times`

In snapshot data:

- one timestamp per waterfall display row,
- derived from the block timestamp and scan rate,
- aligned to the current displayed waterfall buffer,
- useful for correlating the visual image with absolute time.

### Session and Snapshot Times

- `started_at_*` describes when a recording session started.
- `stopped_at_*` describes when it ended.
- `saved_at_*` describes when a snapshot was created.

## 13. Data Integrity and Limitations

### Queue and Dropped Blocks

The recorder uses an internal writer queue and background thread.

Implications:

- if the disk cannot keep up or the queue is overloaded, some blocks may be dropped,
- dropped counts are reported in `summary.json`.

### No Embedded Checksums

The current format does not include:

- file-level checksums,
- content hashes,
- chunk signatures.

If integrity guarantees are required, an external packaging or checksum step should be added later.

### Partial Sessions

If the application exits unexpectedly:

- `session.json` and some chunk files may still exist,
- `summary.json` may be missing,
- `index.jsonl` may contain fewer lines than expected if writing was interrupted.

## 14. Minimal Parsing Example

```python
from pathlib import Path
import json
import numpy as np

session_dir = Path("recordings/2026-04-09_14-32-18")
session_meta = json.loads((session_dir / "session.json").read_text(encoding="utf-8"))

for meta_path in sorted((session_dir / "chunks").glob("*.json")):
    if meta_path.name == "index.jsonl":
        continue
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    npy_path = meta_path.with_suffix(".npy")
    block = np.load(npy_path)

    print(
        meta["seq"],
        meta["channel"],
        meta["kind"],
        meta["ts_utc"],
        block.shape,
    )
```

## 15. Recommended Consumer Rules

When building downstream tools, use these rules:

- treat `.npy` as the source of truth for numeric samples,
- treat the matching `.json` file as the source of truth for block metadata,
- prefer `index.jsonl` for fast sequential scans,
- use `session.json` for session-wide settings,
- use `summary.json` for final counters and health of the recording run,
- use snapshot metadata only for reproducing saved UI images, not for reconstructing the full session.
