# JMV-DAS Compatibility API

This document describes the REST API endpoints exposed by JMV-DAS for compatibility with selected OpticalOS integrations.

## Overview

- Protocol: `HTTP`
- Method: `GET`
- Default bind address: `0.0.0.0`
- Default port: `8009`
- Response format: `application/json`

Base URL example:

```text
http://<device-ip>:8009
```

## Supported Endpoints

The current implementation provides the following compatibility endpoints:

- `GET /info?kind=machine_id`
- `GET /info`
- `GET /fibre_status?kind=health`
- `GET /alert?kind=list`
- `GET /alert?kind=status&alert_name=...`

## 1. Machine ID

Returns the stable machine identifier in OpticalOS-compatible legacy format.

### Request

```text
GET /info?kind=machine_id
```

Example:

```text
http://192.168.1.100:8009/info?kind=machine_id
```

### Success Response

```json
{
  "kind": "machine_id",
  "hash": "JMV-B3ABA4B21167"
}
```

## 2. System Info

Returns a compact compatibility payload including machine ID and channel count.

### Request

```text
GET /info
```

### Success Response

```json
{
  "kind": "all",
  "channel_count": 2,
  "machine_id": {
    "hash": "JMV-B3ABA4B21167"
  }
}
```

## 3. Fibre Status

Returns the current fibre status for both acquisition channels.

Important note:
- Each record represents the status of the channel's current active fibre.
- It does not expand both `main` and `standby` into separate rows for each channel.
- `ch1` and `ch2` are both returned in the same response.

### Request

```text
GET /fibre_status?kind=health
```

Example:

```text
http://192.168.1.100:8009/fibre_status?kind=health
```

### Success Response

```json
{
  "fibre_health": [
    {
      "channel_name": "ch1",
      "is_healthy": true,
      "current_first_high_distance": 5321.4,
      "current_fibre": "main",
      "is_healthy_other": true,
      "other_fibre": "standby",
      "is_peeking_other": false,
      "is_autoswitch_enabled": true,
      "peek_time_interval_ms": 200,
      "peek_other_fibre_interval_multiple": 20,
      "fibre_names": ["main", "standby"]
    },
    {
      "channel_name": "ch2",
      "is_healthy": false,
      "current_first_high_distance": 83.7,
      "current_fibre": "standby",
      "is_healthy_other": true,
      "other_fibre": "main",
      "is_peeking_other": false,
      "is_autoswitch_enabled": true,
      "peek_time_interval_ms": 200,
      "peek_other_fibre_interval_multiple": 20,
      "fibre_names": ["main", "standby"]
    }
  ]
}
```

### Field Description

| Field | Type | Description |
| --- | --- | --- |
| `channel_name` | string | Channel identifier, currently `ch1` or `ch2` |
| `is_healthy` | boolean | Health of the currently active fibre |
| `current_first_high_distance` | number | Estimated fibre break/high-reflection distance in meters |
| `current_fibre` | string | Current active fibre name |
| `is_healthy_other` | boolean | Health of the other fibre based on the latest cached measurement |
| `other_fibre` | string | Name of the non-active fibre |
| `is_peeking_other` | boolean | Whether the system is currently peeking the other fibre |
| `is_autoswitch_enabled` | boolean | Whether auto-switch logic is enabled |
| `peek_time_interval_ms` | number | Peek settle delay in milliseconds |
| `peek_other_fibre_interval_multiple` | number | Peek interval in number of amp blocks |
| `fibre_names` | string[] | Available fibre names |

## 4. Alert List

Lists the fibre break alerts exposed by the device.

### Request

```text
GET /alert?kind=list
```

### Success Response

```json
{
  "alerts": [
    {
      "alert_name": "fibre_break_ch1",
      "type": "fibre_break"
    },
    {
      "alert_name": "fibre_break_ch2",
      "type": "fibre_break"
    }
  ]
}
```

## 5. Alert Status

Returns the detailed status for one fibre break alert.

### Request

```text
GET /alert?kind=status&alert_name=fibre_break_ch1
```

Example:

```text
http://192.168.1.100:8009/alert?kind=status&alert_name=fibre_break_ch1
```

### Success Response

```json
{
  "name": "fibre_break_ch1",
  "type": "fibre_break",
  "channel": "ch1",
  "metric": "amp",
  "ts_wall_ms": 1742280000123,
  "abnormal": false,
  "active_healthy": true,
  "other_healthy": true,
  "threshold": 1000.0,
  "least_len": 100.0,
  "first_high_pos": 284,
  "first_high_distance_m": 5321.4,
  "active_fibre": "main",
  "other_fibre": "standby",
  "is_peeking_other": false,
  "is_autoswitch_enabled": true,
  "peek_time_interval_ms": 200,
  "peek_interval_multiple": 20,
  "default_fibre_name": "main",
  "relay_id": 0,
  "switch_id": 0,
  "fibre_names": ["main", "standby"]
}
```

## Error Handling

Example error responses:

```json
{"error":"missing kind"}
```

```json
{"error":"missing alert_name"}
```

```json
{"error":"alert not found"}
```

```json
{"error":"Invalid argument (no kind)"}
```

## Integration Notes

- CORS is enabled with `Access-Control-Allow-Origin: *`.
- The API is read-only.
- Fibre status is based on the latest available processed data in the running JMV-DAS application.
- If the application is running but no valid data has been received yet, some status values may remain at default values such as `false`, `-1`, or empty cached state.
