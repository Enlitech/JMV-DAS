# JMV-DAS User Guide

This guide describes the current JMV-DAS desktop application, including the meaning of each major parameter, the waterfall display and recording workflow, fibre break detection, and automatic switching behavior.

## 1. Application Purpose

JMV-DAS is a desktop application for:

- receiving live `amp` and `phase` data from two acquisition channels,
- displaying the selected stream as a time series and waterfall image,
- controlling a two-channel optical switch through RS485,
- detecting fibre break conditions from `amp` data,
- switching between `Main` and `Standby` fibres when configured,
- recording waterfall data and snapshots to disk,
- exposing OpticalOS-compatible REST endpoints for machine ID and fibre status.

## 2. Main Window Layout

The main window is divided into two areas.

- Left panel:
  acquisition settings, optical switch controls, fibre break settings, waterfall settings, recording controls, machine ID, current time, and status text.
- Right panel:
  time-series chart, waterfall image, distance axis, and hover inspection text.

The left panel is scrollable, so newer controls such as recording and range filtering do not require a larger main window.

## 3. Acquisition Parameters

These parameters are sent to the acquisition backend when `Start` is pressed.

### Scan Rate

Available options:

- `1k`
- `2k`
- `4k`
- `10k`

Meaning:

- Controls how quickly acquisition lines are produced.
- Higher scan rate gives faster updates.
- It also affects waterfall history compression because history duration is defined in seconds, not only in row count.

### Mode

Available options:

- `Coherent Suppression`
- `Polarization Suppression`
- `Coherent + Polarization`

Meaning:

- Selects the acquisition/demodulation mode used by the backend.
- Changes the produced signal characteristics.
- Does not change the application logic for fibre break detection, which still uses `amp`.

### Pulse Width

Meaning:

- Passed directly to the backend at acquisition start.
- Changes the measurement configuration of the hardware.
- Does not directly change UI rendering or auto-switch policy.

### Scale Down

Meaning:

- Passed to the backend.
- Defines spatial sampling density in the returned data.
- Directly affects distance conversion in the UI, the hover text, range filtering, and fibre break length estimation.

Relationship:

- Larger `Scale Down` means each point represents a larger physical distance.
- If `Scale Down` changes, the same column index corresponds to a different distance in meters.

## 4. Optical Switch Controls

The optical switch section controls the RS485 optical switch hardware.

### Optical Switch Port

Meaning:

- Serial device path used for RS485 communication.
- Example on Linux: `/dev/ttyUSB0`

### Refresh Ports

Meaning:

- Reloads the available serial port list from the operating system.

### Connect Switch

Meaning:

- Opens the selected serial port.
- Enables switch commands from this application.

### Disconnect Switch

Meaning:

- Closes the switch serial port.

### Optical Switch CH1 Fibre / CH2 Fibre

Available options:

- `Main`
- `Standby`

Meaning:

- Defines which fibre each channel should currently use.
- In the present hardware mapping:
  - `Main` corresponds to relay OFF
  - `Standby` corresponds to relay ON

### Apply Fibre Selection

Meaning:

- Sends the selected CH1 and CH2 fibre choices to the RS485 switch.
- Updates the application's assumed current fibre state.

Important note:

- The application tracks switch state from commands sent by this UI.
- If the hardware state is changed outside this application, the software does not automatically read that back.

## 5. Waterfall Display and Navigation

### Waterfall Channel

Available options:

- `1`
- `2`

Meaning:

- Selects which acquisition channel is displayed in the right-side time-series and waterfall panels.

### Waterfall Kind

Available options:

- `phase`
- `amp`

Meaning:

- Selects which stream is displayed.
- This affects visualization only.
- Fibre break detection still uses `amp` even when the waterfall shows `phase`.

### Waterfall History (s)

Meaning:

- Target visible history duration for the waterfall.
- The application does not simply increase widget height.
- Instead, it compresses multiple incoming time lines into one display row so the same UI area can represent a longer time span.

Relationship:

- Larger history means more temporal compression in the waterfall.
- Fine transient detail becomes less visible, but a longer period remains on screen.
- The effective history is recorded in metadata because the exact value depends on scan rate and compression ratio.

### Enable Range Filter

Meaning:

- Restricts the displayed waterfall to a selected distance interval.
- The filter is defined in meters, not only in raw column indices.

Behavior:

- The selected distance range is converted into absolute source columns using the current `Scale Down`.
- The cropped block is then used for waterfall rendering and for the time-series extraction on the selected stream.
- Hover distance and axis labels still report absolute distance, not a re-zeroed local value.

### Range Start Distance (m) / Range End Distance (m)

Meaning:

- Defines the distance interval to display.
- The start and end values are clamped to the actual available data width.

Practical note:

- These values are stored as meters so they remain meaningful and reproducible in later sessions.

### Use Current View

Meaning:

- Converts the currently visible zoomed/panned view into the active range filter.

Typical workflow:

1. Zoom and pan the waterfall to the region of interest.
2. Press `Use Current View`.
3. The application stores that region as the distance filter for both display and, if chosen, filtered recording.

### Reset Full Range

Meaning:

- Disables the active distance filter and returns the display to the full spatial range.

### Time Series Column (pos idx)

Meaning:

- Selects the current displayed column inside the filtered waterfall view.
- The distance shown in the chart title is still reported in absolute physical distance.

Important note:

- If range filtering is enabled, column `0` in the displayed waterfall may correspond to a nonzero absolute fibre distance.

### Mouse Navigation on the Waterfall

Behavior:

- Mouse wheel: zoom horizontally.
- Left-drag: pan horizontally.
- Double-click: reset viewport to the full currently loaded waterfall range.
- Hover: show distance, time, age, and value.

Important distinction:

- The current zoom/pan viewport is not the same as the distance filter.
- The distance filter defines which data are processed.
- The viewport only defines which part of the already filtered data is currently visible.

## 6. Waterfall Transform Parameters

The current application uses the `Energy (MSE dB)` transform for waterfall rendering.

### Energy Window

Meaning:

- Number of lines used in the temporal rolling energy calculation.
- Larger values give more temporal averaging and a smoother waterfall appearance.

### dB vmin / dB vmax

Meaning:

- Fixed display normalization range for the transformed waterfall.
- These values affect display contrast only.

Relationship:

- If the range is too wide, the image may look flat.
- If the range is too narrow, the image may saturate.

### Gamma

Meaning:

- Nonlinear brightness adjustment applied after normalization.
- Display-only parameter.

### Invert

Meaning:

- Reverses the final grayscale mapping.
- Display-only parameter.

## 7. Recording, Snapshots, and Time Reference

The application can save both still snapshots and continuous waterfall recordings.

### Recording Mode

Available options:

- `Selected Stream`
- `All Streams`

Meaning:

- `Selected Stream` records only the currently selected `channel/kind`.
- `All Streams` records all incoming streams that reach the application.

### Recording Scope

Available options:

- `Record Full Block`
- `Record Filtered Range`

Meaning:

- `Record Full Block` stores the original incoming spatial block width.
- `Record Filtered Range` stores only the currently configured waterfall distance range.

Important note:

- `Recording Scope` is independent from `Recording Mode`.
- For example, you may record only the selected stream but only its filtered distance interval.

### Recording Output Folder

Meaning:

- Root directory used for new recording sessions.

### Save Snapshot

Meaning:

- Saves the currently rendered waterfall image and its associated data.

Saved content includes:

- rendered PNG,
- waterfall `values` array,
- `row_times` array,
- metadata JSON.

### Start Recording / Stop Recording

Meaning:

- Starts or stops a continuous recording session.
- Raw waterfall blocks are saved as `.npy` files with matching `.json` metadata.

### Recorded Metadata

The application stores reproducibility metadata for recordings and snapshots, including:

- selected stream,
- acquisition settings,
- transform settings,
- target and effective waterfall history,
- range filter status and distance interval,
- source point count and filtered point count,
- local time,
- UTC time,
- Unix epoch seconds.

### UTC and Local Time

The application now records explicit UTC fields in addition to epoch time:

- session start UTC,
- session stop UTC,
- chunk UTC timestamp,
- snapshot UTC timestamp.

### Live Clock in the Main Window

The lower part of the left panel shows:

- current local time,
- current UTC time.

This is intended to help operators synchronize screen recordings, external cameras, or other measurement systems.

## 8. Fibre Break Detection

Fibre break detection uses `amp` data only.

### Core Method

For each incoming `amp` block:

1. The application determines the currently active fibre.
2. The block is reduced to a 1D spatial profile.
3. A spatial EWMA is applied.
4. The software scans backward from the fibre end.
5. It finds the last position above the configured threshold.
6. That position is converted to a physical length in meters.
7. If the measured length is below the configured minimum, the fibre is treated as broken.

### Fibre Break Monitor Channel

Available options:

- `1`
- `2`

Meaning:

- Selects which channel uses the full monitoring workflow:
  - detailed UI status,
  - auto-switch,
  - peek-other-fibre workflow.

Important note:

- The application still keeps current-fibre status for both channels.
- Only the selected monitor channel drives active switch decisions.

### Fibre Break EWMA Alpha

Meaning:

- Smoothing factor for the spatial EWMA profile.

Relationship:

- Higher `Alpha` gives faster response and less smoothing.
- Lower `Alpha` gives stronger smoothing and slower response.

### Fibre Break Amp Threshold

Meaning:

- Threshold used when searching backward for the effective fibre end.

Relationship:

- Higher threshold usually shortens the detected fibre length.
- Lower threshold usually increases the detected fibre length.

### Fibre Break Min Length (m)

Meaning:

- Minimum acceptable fibre length.

Decision rule:

- If detected length `>= Min Length`, the fibre is treated as healthy.
- If detected length `< Min Length`, the fibre is treated as broken.

### Enable Fibre Alarm

Meaning:

- Controls UI alarm emphasis for the monitored fibre.
- Does not disable the actual detection calculation.

## 9. Automatic Switching Logic

Automatic switching uses the current assumed switch state and the latest cached health of `Main` and `Standby`.

### Default Fibre

Available options:

- `Main`
- `Standby`

Meaning:

- Preferred normal operating fibre for the monitored channel.

### Auto Switch On Break

Meaning:

- Enables automatic switching when the current monitored fibre becomes unhealthy.

### Auto-switch Decision Logic

When auto-switch is enabled:

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
5. If the target fibre is already active:
   - do nothing.

Important note:

- Auto-switch affects only the selected monitor channel.

## 10. Peek Other Fibre Logic

The application can temporarily move the monitored channel to the non-active fibre to refresh its health estimate.

### Peek Other Fibre

Meaning:

- Enables periodic health sampling of the non-active fibre.

### Peek Every N Amp Blocks

Meaning:

- Number of `amp` blocks between peek attempts.

Relationship:

- Smaller value means more frequent peeks and more switch activity.
- Larger value means less switch activity but older backup-fibre health data.

### Peek Settle Delay (ms)

Meaning:

- Delay applied after switching before sampling.
- Also applied while switching back to the original fibre.

### Peek Workflow

When peek is enabled and the interval condition is reached:

1. Switch to the other fibre.
2. Wait for the settle delay.
3. Process one `amp` block there.
4. Store the health result for that fibre.
5. Switch back.
6. Wait again for stabilization.
7. Resume normal monitoring.

Important note:

- The non-active fibre status may be based on the last peek result rather than a simultaneous live measurement.

## 11. Relationship Between Key Parameters

The most important tuning relationship is:

- `Scale Down`
- `Fibre Break Amp Threshold`
- `Fibre Break Min Length (m)`
- `Fibre Break EWMA Alpha`
- `Waterfall History (s)`
- `Range Filter`

Practical interpretation:

- `Scale Down` changes physical distance conversion.
- `Amp Threshold` changes where the fibre end is detected.
- `Min Length` decides whether that detected end is acceptable.
- `EWMA Alpha` changes how sensitive the profile is to local variation.
- `Waterfall History (s)` changes how much temporal compression is applied in the display.
- `Range Filter` changes which spatial region is displayed and, if selected, which region is recorded.

If the waterfall is too compressed:

- reduce `Waterfall History (s)`.

If the displayed region is too wide:

- enable the range filter and limit the distance interval.

If false break alarms occur:

- lower `Min Length`,
- lower `Amp Threshold`,
- or reduce `Alpha`.

If real breaks are missed:

- raise `Min Length`,
- raise `Amp Threshold`,
- or increase `Alpha`.

## 12. Machine ID, API Docs, and User Guide

### Machine ID

The application generates a stable machine ID and displays it:

- in the window title,
- in the left control panel,
- through the compatibility API.

### API Docs

Opens the built-in API compatibility documentation window.

### User Guide

Opens this guide rendered inside the application.

## 13. Recommended Operating Sequence

1. Connect the acquisition hardware and optical switch.
2. Select the correct RS485 serial port and connect the switch.
3. Set the expected CH1 and CH2 normal fibre states.
4. Configure acquisition settings.
5. Select the waterfall stream to inspect.
6. Set waterfall history duration.
7. If needed, define a distance range filter or use `Use Current View`.
8. Configure recording mode and recording scope.
9. Configure fibre break parameters.
10. Enable auto-switch and peek only after thresholds are validated.
11. Start acquisition and observe waterfall, hover values, time labels, and switch status.
12. Start recording or save snapshots when needed.

## 14. Current Implementation Notes

- Fibre break detection uses `amp` only.
- The waterfall may display `amp` or `phase`.
- Distance filtering is applied in software after the acquisition block reaches the application.
- Recording can store either the full raw block width or only the filtered distance interval.
- Both local and UTC time references are available in the UI and recording metadata.
- Both channels expose status through the compatibility API.
- Only the selected monitor channel performs automatic switch and peek actions.
- The switch state is command-tracked inside the application and is not read back from the hardware.
