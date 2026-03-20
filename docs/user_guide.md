# JMV-DAS User Guide

This document explains the main functions of the JMV-DAS application, the meaning of each user-facing parameter, and the logic used for fibre break detection and automatic switching.

## 1. Application Purpose

JMV-DAS is a desktop application for:

- receiving live `amp` and `phase` data from two acquisition channels,
- visualizing the data as a waterfall image and time series,
- controlling a two-channel optical switch over RS485,
- detecting fibre break conditions from `amp` data,
- automatically switching to a backup fibre when configured to do so,
- exposing a compatibility REST API for machine ID and fibre status.

## 2. Main Layout

The application window is divided into two areas:

- Left panel: configuration, switch control, fibre break settings, and document buttons.
- Right panel: time-series chart, waterfall display, distance axis, and hover information.

## 3. Acquisition Parameters

These parameters define how the device is started.

### Scan Rate

Available options:

- `1k`
- `2k`
- `4k`
- `10k`

Meaning:

- This value is passed directly to the acquisition backend as the scan-rate setting.
- Higher scan rate generally means faster data updates.
- The selected scan rate is part of the device start configuration but does not directly change the fibre break threshold logic.

### Mode

Available options:

- `Coherent Suppression`
- `Polarization Suppression`
- `Coherent + Polarization`

Meaning:

- This selects the demodulation mode used by the acquisition backend.
- It affects the type of processed signal produced by the hardware/backend.
- Fibre break detection still uses `amp` data only, regardless of the display mode or selected waterfall stream.

### Pulse Width

Meaning:

- This value is sent directly to the acquisition backend during startup.
- It influences the measurement configuration of the device.
- It does not directly change the automatic switching rules in software.

### Scale Down

Meaning:

- This value is sent to the acquisition backend.
- It also affects distance conversion inside fibre break detection.
- The estimated fibre length is calculated from the detected position multiplied by the base spacing and by `Scale Down`.

Relationship:

- If `Scale Down` increases, the same detected position corresponds to a larger physical distance.
- Therefore, `Scale Down` influences the reported fibre length and the break decision.

## 4. Optical Switch Controls

The optical switch section controls the RS485 switch hardware.

### Optical Switch Port

Meaning:

- Serial port used for the RS485 connection.
- Example on Linux: `/dev/ttyUSB0`

### Refresh Ports

Meaning:

- Reloads the list of available serial ports from the operating system.

### Connect Switch

Meaning:

- Opens the selected serial port and prepares the switch controller.
- The software then assumes the switch follows the current UI selection for each channel.

### Disconnect Switch

Meaning:

- Closes the serial port connection to the switch.

### Optical Switch CH1 Fibre / CH2 Fibre

Available options:

- `Main`
- `Standby`

Meaning:

- These represent the current target fibre for channel 1 and channel 2.
- In this application:
  - `Main` corresponds to relay OFF
  - `Standby` corresponds to relay ON

### Apply Fibre Selection

Meaning:

- Sends the selected CH1 and CH2 fibre states to the switch.
- Updates the application's internal assumed active fibre state.

Important note:

- The software tracks the switch state based on commands sent from this application.
- If the hardware state is changed externally, the software does not automatically read it back.

## 5. Waterfall and Display Parameters

### Waterfall Channel

Available options:

- `1`
- `2`

Meaning:

- Selects which acquisition channel is shown in the waterfall and time-series display.

### Waterfall Kind

Available options:

- `phase`
- `amp`

Meaning:

- Selects which stream is displayed.
- This affects visualization only.
- Fibre break detection always uses `amp`, even if the waterfall currently shows `phase`.

### Time Series Column

Meaning:

- Selects the spatial column extracted from the current waterfall stream for the top time-series chart.
- The chart title and distance axis update based on this column.

### Energy Window

Meaning:

- Number of lines used in the waterfall transform window.
- Larger values produce more temporal averaging in the rendered waterfall.

### dB vmin / dB vmax

Meaning:

- Lower and upper bounds for display normalization in the waterfall transform.
- These values affect rendering contrast only.

Relationship:

- If the range is too wide, image contrast becomes weak.
- If the range is too narrow, the waterfall may saturate.

### Gamma

Meaning:

- Nonlinear display adjustment for the rendered waterfall.
- This affects only visual appearance.

### Invert

Meaning:

- Inverts the rendered brightness mapping.
- This affects only the display, not detection.

## 6. Fibre Break Detection

Fibre break detection operates on `amp` data only.

### Core Method

For each incoming `amp` block:

1. The application selects the current active fibre for the channel.
2. The 2D `amp` block is averaged over time to produce a 1D spatial profile.
3. A spatial EWMA is applied to smooth the profile.
4. The software scans from the end of the fibre backward and finds the last position above threshold.
5. That position is converted to distance in meters.
6. If the estimated distance is below the configured minimum length, the fibre is considered broken.

### Fibre Break Monitor Channel

Available options:

- `1`
- `2`

Meaning:

- This selects which channel is used for the full monitoring workflow:
  - UI status display,
  - auto-switch logic,
  - peek-other-fibre workflow.

Important note:

- The application still keeps break-status results for both channels.
- However, the active auto-switch and peek workflow only runs on the selected monitor channel.

### Fibre Break EWMA Alpha

Meaning:

- Smoothing factor for the spatial EWMA.

Relationship:

- Higher `Alpha`:
  - reacts faster to local changes,
  - less smoothing.
- Lower `Alpha`:
  - more smoothing,
  - slower response to sharp changes.

### Fibre Break Amp Threshold

Meaning:

- Threshold used when searching from the fibre end backward.
- The software finds the last spatial position where the smoothed `amp` profile is above this value.

Relationship:

- Higher threshold usually shortens the detected fibre length.
- Lower threshold usually extends the detected fibre length.

### Fibre Break Min Length (m)

Meaning:

- Minimum acceptable healthy fibre length in meters.

Decision rule:

- If detected length `>= Min Length`, the fibre is treated as healthy.
- If detected length `< Min Length`, the fibre is treated as broken and marked as abnormal.

Relationship:

- This value should be chosen together with `Scale Down` and `Amp Threshold`.
- If `Min Length` is set too high, false alarms become more likely.
- If `Min Length` is set too low, short broken fibres may still be treated as healthy.

### Enable Fibre Alarm

Meaning:

- Enables visual alarm emphasis in the UI status text when the monitored current fibre is abnormal.

Important note:

- This does not control the actual detection calculation.
- It controls alarm presentation in the interface.

## 7. Automatic Switching Logic

Automatic switching uses the configured switch state and the latest health result for the current and other fibre.

### Default Fibre

Available options:

- `Main`
- `Standby`

Meaning:

- Preferred normal operating fibre for the monitored channel.

### Auto Switch On Break

Meaning:

- Enables automatic switching when the monitored current fibre becomes unhealthy.

### Auto-switch Decision Logic

When auto-switch is enabled, the logic is:

1. Read the current active fibre.
2. Read the cached health of:
   - current fibre,
   - other fibre,
   - default fibre.
3. If the current fibre is broken:
   - switch to `Default Fibre` if it is healthy,
   - otherwise switch to the other fibre if it is healthy.
4. If the current fibre is healthy but is not the `Default Fibre`:
   - switch back to `Default Fibre` if the default fibre is healthy.
5. If the target fibre is the same as the current fibre:
   - do nothing.

Important note:

- Auto-switch applies only to the selected monitor channel.
- Channel 1 and channel 2 still have their own current fibre status, but only the monitor channel participates in switch actions.

## 8. Peek Other Fibre Logic

The application can temporarily switch to the non-active fibre to update its health estimate.

### Peek Other Fibre

Meaning:

- Enables periodic sampling of the non-active fibre on the monitor channel.

### Peek Every N Amp Blocks

Meaning:

- Number of `amp` callback blocks between peek attempts.

Relationship:

- Smaller value:
  - peeks more often,
  - updates backup-fibre health more frequently,
  - causes more switching activity.
- Larger value:
  - peeks less often,
  - reduces switching activity,
  - other-fibre health may become older.

### Peek Settle Delay (ms)

Meaning:

- Delay after switching fibres before sampling the other fibre.
- The same delay is also used while returning to the original fibre.

Relationship:

- If this value is too short, the sampled data may still be unstable after switching.
- If it is too long, the peek cycle becomes slower.

### Peek Workflow

When peek is enabled and the interval condition is met:

1. The application switches the monitor channel to the other fibre.
2. It waits for the configured settle delay.
3. It processes one `amp` block for the other fibre.
4. It stores the other fibre health result.
5. It switches back to the original fibre.
6. It waits again for the settle delay to allow recovery.
7. Normal monitoring resumes.

Important note:

- The other-fibre health reported in the UI and API may be based on the last peek result, not on a simultaneous live measurement.

## 9. Relationship Between Key Parameters

The most important tuning relationship is:

- `Scale Down`
- `Fibre Break Amp Threshold`
- `Fibre Break Min Length (m)`
- `Fibre Break EWMA Alpha`

Practical interpretation:

- `Scale Down` changes distance conversion.
- `Amp Threshold` changes where the fibre end is detected.
- `Min Length` decides whether that detected end is acceptable.
- `EWMA Alpha` changes how sensitive the profile is to local variation.

If false alarms occur:

- lower `Min Length`,
- lower `Amp Threshold`,
- or reduce `Alpha` for stronger smoothing.

If real breaks are missed:

- raise `Min Length`,
- raise `Amp Threshold`,
- or increase `Alpha` to react more strongly to sharp changes.

## 10. Machine ID and Documentation

### Machine ID

The application generates a stable machine ID from system identity information and displays it:

- in the window title,
- in the left control panel,
- through the compatibility API.

### API Docs

Opens the compatibility API Markdown document rendered inside the application.

### User Guide

Opens this user guide rendered inside the application.

## 11. Recommended Operating Sequence

1. Connect the acquisition device and optical switch hardware.
2. Select the correct serial port and connect the switch.
3. Set CH1 and CH2 to the expected normal fibre state.
4. Configure acquisition parameters.
5. Set the monitor channel and fibre break parameters.
6. Set the default fibre.
7. Enable auto-switch and peek only after thresholds are validated.
8. Start acquisition and observe the waterfall and status text.
9. Confirm that measured fibre length and switch behavior match the real installation.

## 12. Current Implementation Notes

- Fibre break detection is based on `amp` only.
- The waterfall can display either `amp` or `phase`.
- Both channels expose status through the compatibility API.
- Only the selected monitor channel performs automatic switching and peek operations.
- The switch state is command-tracked inside the application and is not read back from the hardware.
