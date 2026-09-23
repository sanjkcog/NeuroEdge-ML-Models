# Reading the KIT CNC milling data — a beginner's guide

What this data is, where each number comes from, how to open every file, and how it becomes the
windows a model is trained on. Everything below was checked against the files on disk in this
folder, not copied from a dataset description or a textbook. What could not be checked is marked
**unconfirmed** where it is said, and collected in §17.

**Part 1 (§1–§10) is the raw data.** Start here if you want to know what the numbers are.
**Part 2 (§11–§17) is the dataset the model reads.** Which trials are used, how 500 Hz becomes
10 Hz windows, the splits, the synthetic data, and what is still unconfirmed.
**Training and the result** are in [`model.md`](model.md): epochs, folds, and how to read the
number.

Source: **"A Multimodal Dataset for Process Monitoring and Anomaly Detection in Industrial CNC
Milling"**, Ströbel et al. 2025, KIT. DOI `10.35097/hvvwn1kfwf7qt48z`, **CC BY 4.0** — free to
use commercially, attribution required.

---

## 1. The physical setup — what actually happened

A **milling machine** cuts metal or plastic by spinning a cutting tool and pushing it through a
solid block. The block is the *workpiece*; the spinning cutter is the *tool*; the motors that
move the tool around are the *axes*.

KIT ran ~6 hours of real milling and recorded everything. One **experiment** (they call it a
trial) = one workpiece machined start to finish, 4–20 minutes.

### The machine

**DMC 60 H** (Deckel Maho) — a 3-axis *horizontal* machining centre, retrofitted. Three axes
plus a spindle:

| Axis index in the data | Motor | What it does |
|---|---|---|
| `1` | **X** | moves left–right |
| `2` | **Y** | moves up–down |
| `3` | **Z** | moves in–out |
| `6` | **Spindle** | *spins the cutter* — this is the one doing the cutting work |

> Indices 4 and 5 exist in the signal template but are never populated — the machine has no
> 4th/5th axis. The 1/2/3/6 → X/Y/Z/spindle mapping is the standard convention for this
> machine class and is consistent with the data; it is **not** written down in the dataset, so
> confirm it against an NC program before betting a model on it (see §6).

### The three parts being made

The same machine made three different things, so the dataset isn't specific to one shape or
material. This is the single most confusing thing about the folder layout: **these are
products, not sensors.** Every experiment records all the same signals.

| Folder | What it is | Material | Why it's different |
|---|---|---|---|
| **Impeller** | a fan/pump wheel with curved blades | POM-C (a tough plastic) | small Ø5 mm cutter at **8000 rpm**; delicate 3D shapes |
| **Injection mold** | a steel mould tool used to injection-mould plastic parts | S235JR (structural steel) | Ø10 mm cutter, 3200–4450 rpm; hard material, heavy cuts |
| **Thermoforming mold** | an aluminium mould for shaping plastic sheet | Al 2007 T4 (aluminium) | Ø20 mm cutter, ~1900 rpm; large, fast material removal |

All start from a 150 × 75 × 50 mm blank.

### The sensors — and the crucial split

Data comes from **two completely separate systems** that were later lined up in time. This
split explains the whole folder structure:

| | **The machine's own view** | **Independent sensors bolted on** |
|---|---|---|
| Source | Siemens SINUMERIK 840D controller, read by the "Analyze MyWorkpiece/Capture" Edge app | Kistler 9255C force platform under the workpiece + PCB 356A33 accelerometer on the spindle |
| Rate | **500 Hz** (500 readings/second) | **10 kHz** (10,000/second) |
| Measures | what the motors are commanded to do and what they report back — position, current, torque, load | actual physical force and vibration |
| Lands in | `processed_data/*.csv` (and `.json`) | `raw_data/*.mat` |

**Why two?** The controller knows what it *told* the motors and what the encoders report — but
it cannot feel vibration or chatter. The accelerometer can. The controller's view is free
(already inside the machine); the sensors had to be installed. A real factory usually has only
the first, which is why a model that works on controller signals alone is valuable.

---

## 2. The folder layout

```
data/raw/
  README.txt                          KIT's own description
  Dataset/
    Impeller/           IMP-BASE, IMP-01 … IMP-12, IMP-01-A01 … A04
    Injection mold/     IM-01R, IM-01F, IM-01R-A01 … A05, IM-01F-A01, IM-02F-A01
    Thermoforming mold/ TF-01 … TF-03, TF-01-A01, TF-02-A01, TF-03-A01, TF-03-A02
      <TRIAL>/
        processed_data/
          <TRIAL>_hfdata.csv        <- THE MAIN FILE: 500 Hz controller signals
          <TRIAL>_hfblockevent.csv  <- which line of the G-code program was running
          <TRIAL>_header.csv        <- the signal dictionary for this recording
        raw_data/
          <TRIAL>.mat               <- 10 kHz force + vibration (MATLAB)
  Descriptive/
    DoE/DoE.xlsx                    every trial and what was deliberately done to it
    Part description/<type>/nc_data/*.nc    the G-code programs
    Part description/<type>/*.stp           3D CAD models
    Tools/                          cutting tool specs
```

**Trial naming:** a plain id (`IMP-01`) is a **normal** run. An `-A0n` suffix is an **anomaly**
run — something was deliberately made wrong. `DoE.xlsx`'s `Comment` column says what.

> Not downloaded: `processed_data/*_synchronized.mat` — 39 GB across the dataset, and
> **derivable**. It is the CSV and the `.mat` merged, with the 500 Hz signals stretched to
> 10 kHz by interpolation. Interpolation invents no information, and upsampling a slow channel
> is the opposite of what an edge device wants, so it was excluded deliberately.

---

## 3. `hfdata.csv` — the file you will actually use

**61 columns, 500 rows per second.** Column names look like `SIGNAL|axis`:

```
LOAD|6      = Load on axis 6 (the spindle)
ENC_POS|1   = Encoder position of axis 1 (X)
```

### The signal dictionary

`header.csv` is the machine's own name-to-code map. Read it first for any recording:

```
SignalName,Type,Axis,Address
ActualAxisPosition,DOUBLE,,ENC_POS|1
Load,DOUBLE,,LOAD|1
ControlDiff,DOUBLE,,CTRL_DIFF|1
```

### What each column means

| Column | Real name | Plain English |
|---|---|---|
| `CYCLE` | Cycle | a counter ticking once per sample. **Not** a timestamp — it starts at an arbitrary number and increments by 1 at 500 Hz |
| `DES_POS\|n` | CommandedAxisPosition | where the controller **told** the axis to be (mm) |
| `ENC_POS\|n` | ActualAxisPosition | where the encoder says it **actually** is (mm) |
| `CTRL_DIFF\|n` | ControlDiff | **commanded − actual**, i.e. the *following error* — the machine's own measure of how far behind the axis is lagging |
| `CTRL_DIFF2\|n` | ControlDiff2 | a second variant of the same idea |
| `CONT_DEV\|n` | ContourDeviation | how far off the intended path the tool is |
| `LOAD\|n` | Load | motor load as a **percentage** of rating. `LOAD\|6` = how hard the spindle is working |
| `TORQUE\|n` | Torque | twisting force the motor is producing |
| `CURRENT\|n` | Current | electrical current the motor is drawing |
| `POWER\|n` | Power | electrical power (watts) |
| `CMD_SPEED\|n` | CommandedSpeed | commanded speed |
| `VEL_FFW\|n`, `TORQUE_FFW\|n` | feed-forward terms | controller internals — predictive corrections |
| `CTRL_POS\|n` | ControlPos | the controller's internal position setpoint |
| `ENC1_POS\|n`, `ENC2_POS\|n` | Encoder 1 / 2 | motor-side and load-side encoders (a ballscrew can twist between them) |

### Reading a real row — idle vs cutting

Both rows are from `Impeller/IMP-01`:

```
                    AT REST (row 1)        CUTTING HARD (row 4604)
CYCLE               4814008                4818612
LOAD|6   spindle    0.0 %                  99.98 %        <- flat out
POWER|6             0                      20,233 W       <- 20 kW into the cut
TORQUE|6            0.0                    -37.48
CURRENT|6           0.0                    -36.01
DES_POS|1  X told   -3.530037 mm           -2.530047 mm
ENC_POS|1  X actual -3.530037 mm           -2.529100 mm
CTRL_DIFF|1         0.000000               -0.000947 mm   <- lagging ~1 micron
```

**This is the physics the whole project rests on.** At rest the X axis sits exactly where it
was told. Under a 20 kW cut it lags by about a micron, because the cutting force pushes back
against the servo. As a tool goes blunt, it pushes back *harder for the same commanded
motion* — so following error grows. That growth, on an unchanged program, **is** mechanical
drift.

And note:

```
DES_POS|1 − ENC_POS|1 = -0.000947   ==   CTRL_DIFF|1
```

The controller already computes the subtraction for you. Two independent routes to the same
number, which is a good position to be in — they cross-check each other.

### Scale of one file

| Trial | Part | Rows | Duration | CSV size |
|---|---|---|---|---|
| `IMP-01` | Impeller | 172,052 | 5.7 min | 95.8 MB |
| `IM-01R` | Injection mold | 610,343 | 20.3 min | 338.7 MB |
| `TF-01` | Thermoforming | 130,772 | 4.4 min | 71.3 MB |

### Opening it

```python
import pandas as pd
df = pd.read_csv("data/raw/Dataset/Impeller/IMP-01/processed_data/IMP-01_hfdata.csv")
df["time_s"] = (df["CYCLE"] - df["CYCLE"].iloc[0]) / 500.0     # CYCLE is a counter, not time
df["x_following_error"] = df["DES_POS|1"] - df["ENC_POS|1"]    # == df["CTRL_DIFF|1"]
```

A 339 MB CSV is slow to load repeatedly — convert once to Parquet
(`df.to_parquet(...)`) and reads become near-instant.

---

## 4. `hfblockevent.csv` — what the program was doing

A G-code program is a list of instructions. This file records which one was executing:

```
HFProbeCounter,Channel,SeekOffset,SelectedTool,ActiveTool,GCode,IpoGC,ipoReadError,laBuf
4817081,1,13,0,0,STOPRE,G1,,0
```

`HFProbeCounter` shares the 500 Hz clock family with `hfdata.csv`'s `CYCLE`, so the two can be
aligned. `GCode` is the actual command running at that instant.

**Why it matters:** it lets you say *"this vibration happened while cutting the third blade
pocket"* rather than just *"at second 143"*. That's how you locate a defect tied to a specific
place on the part.

---

## 5. `raw_data/*.mat` — force and vibration

**What's inside:** the 10 kHz signals from the force platform and the spindle accelerometer:
seven columns, `Sync_Signal`, `xForce`, `yForce`, `zForce`, `xAcceleration`, `yAcceleration`,
`zAcceleration`. This is the **only** place `vibration_rms` can come from; the CSV has no
vibration channel.

### Why MATLAB at all?

MATLAB is the standard tool in mechanical-engineering labs, and its **timetable** type stores
a signal with its timestamps attached as one object. KIT saved the files the way they worked
with them. That was convenient for the authors, not a choice made for Python users.

### Reading them — tested on these files

These are **MATLAB object files (MCOS timetables)** in MAT v5 format, not plain arrays. Most
readers fail **silently**:

| Reader | What you actually get |
|---|---|
| `scipy.io.loadmat` | `{'None': MatlabOpaque(...)}`: an opaque handle, no data |
| `pymatreader` | `tmp_new = {'_TypeSystem', '_Class', '_ObjectMetadata'}`: object metadata, **no signal arrays**, no error |
| `mat73` / `h5py` | these are for v7.3 (HDF5) files; the KIT files are v5 |
| Octave | has no `timetable` class (not tested: Octave isn't installed here) |
| **`mat-io`** (`import matio`) | **works**: a pandas DataFrame, 1,035,000 × 7 for `TF-03-A02` |

```python
import matio                                   # pip install mat-io  (needs numpy>=2.2)
df = matio.load_from_mat(path)["tmp_new"]      # DataFrame, 10 kHz
t_s = np.arange(len(df)) / 10_000              # the index is truncated to WHOLE seconds
```

The decoded index is `timedelta64[s]`, so `TF-03-A02` has 1,035,000 rows but only 104
distinct index values. Rebuild time from the sample number, never from the index.

### The real problem: the two recorders are not in step

The `.mat` and `hfdata.csv` start at different moments (**offsets from −9.3 s to +6.4 s** across
trials) and run at different lengths (`TF-03-A02`: 103.5 s against 114.1 s). "Row 0 = row 0" is
wrong by seconds. Cross-correlating vibration against spindle power does **not** find the
offset (r = −0.2 to 0.25, no clear peak).

What does work is the **sync pulse** KIT wired in on purpose. Every NC program starts with:

```
TAKTGEBER          ; "clock generator": drives Sync_Signal, a 0/5 V square wave, 16 ms per phase
R60=0
G04 F2             ; 2-second dwell: the square wave stops
R60=1              ; ...and starts again
S3050 M3           ; spindle on
```

- **Anchor.** The dwell is the **only** long gap in `Sync_Signal`: exactly one per trial,
  2.016–2.044 s long against the logged 2.002 s. `hfblockevent.csv` logs the `G04 F2` block and
  the block after it on the same counter as `hfdata.csv`'s `CYCLE`. So the first edge after the
  gap and the counter of the block after the dwell are the same instant.
- **Rate.** Each phase of the square wave is 8 controller ticks (16 ms). Fitting edge position
  against edge number measures the DAQ clock directly: it runs **75–81 ppm fast on every
  trial**, which adds up to **98 ms** over `IM-01R`'s 20 minutes. A fixed offset leaves that
  error in; the fit removes it.
- **Program end.** The clock generator stretches one phase at `M5`/`M30`, in the last 2–14 s, so
  the fit stops there and the fitted rate covers the tail.

**Accuracy:** 33/33 trials aligned. The anchor is good to about one sync phase: vibration
leaves baseline a median **8 ms before** spindle current does (range −14 to +8 ms), because the
generator restarts on its own phase grid. That's negligible for RMS over windows of 0.2 s or
more. It's too coarse for timing events shorter than ~20 ms.

### Getting `vibration_rms` — one command

This is packaged as AgentForge's `sensor_align` module (shipped into this repo at
`agentforge/src/sensor_align/`; see the "Joining a second recorder" section of
`agentic-assets/docs/guides/how_to_build_ml_models_v2.md`). From the repo root:

```bash
D=neuroedge-ml-projects/cnc_drift_1dcnn-timeseries
uv run --no-project --with-requirements agentforge/src/requirements-sensor.txt \
  python -m agentforge.src.sensor_align.align --root $D/data/raw/Dataset \
    --mat-glob "*/*/raw_data/*.mat" \
    --events-template "{mat_dir}/../processed_data/{trial}_hfblockevent.csv" \
    --out-template "$D/data/interim/{trial}_sensor.parquet" \
    --diagnostics "$D/data/interim/alignment.json"
```

It runs in a throwaway environment because `mat-io` needs `numpy>=2.2`, and this project's
`agentforge` group holds `numpy<2` for the voice stack. The run takes a few minutes and writes:

- `data/interim/<trial>_sensor.parquet`: **one row per controller tick**, where `tick`
  equals `hfdata.csv`'s `CYCLE`. Columns: `n_samples` (20 per tick), per-axis `*_rms`, and the
  magnitudes `vibration_rms` = RMS of the 3-axis acceleration vector and `force_rms` likewise.
  Each channel's whole-run mean is removed first, so sensor DC offset and platform preload
  don't count. Gitignored and regenerable, 590 MB in total.
- `data/interim/alignment.json`: per trial, the anchor, the measured gap against the logged
  dwell, drift in ppm, fit residual and trailing seconds. This file is tracked, and it is the
  evidence that the join is right.

```python
h = pd.read_csv(f"{trial_dir}/processed_data/{trial}_hfdata.csv", usecols=["CYCLE", "TORQUE|6", "CTRL_DIFF|1"])
s = pd.read_parquet(f"data/interim/{trial}_sensor.parquet", columns=["tick", "vibration_rms"])
df = h.merge(s, left_on="CYCLE", right_on="tick", how="inner")   # >= 89% of CSV rows matched, median 96%
```

Rows without a match are outside the DAQ recording, which started later or stopped earlier
than the controller log. Drop them rather than filling them.

### Still open

- **Units** (collected in §17). The dataset doesn't state the acceleration unit. Values (peaks around ±30, 0.1 s
  RMS of 2–5 while cutting) are plausible in *g*, but that's unconfirmed. Settle it before the
  model card quotes a threshold.
- **Deployment.** This accelerometer was bolted on for the experiment, and §1 notes a typical
  plant has only the controller signals. `vibration_rms` is a valid model input **only if the
  edge device will carry an accelerometer**. That's a channel-contract decision for M4.

| Trial | `.mat` size |
|---|---|
| `IMP-01` | 74.6 MB |
| `IM-01R` | 209.7 MB |
| `TF-01` | 45.1 MB |

---

## 6. `Descriptive/` — the context files

**`DoE/DoE.xlsx`** — the experiment plan. One row per trial with cutting parameters and a
`Comment` naming what was deliberately made wrong. An empty `Comment` = a normal run. This is
the only place the labels exist.

**`Part description/<type>/nc_data/*.nc`** — the G-code, and it is readable. From
`Impeller/nc_data/IMP-01.nc`:

```gcode
;(Benchmark zur Evaluierung der Zeitreihenvorhersage von achsspezifischen Stromwerten)
;(IMP-01)
;(Gerade, 3 Schaufel)                  <- "straight, 3 blades"
;(T1 D=5 CR=0 - ZMIN=-8 - Schaftfraser) <- tool 1, Ø5 mm end mill, cuts to -8 mm
;(Used material: POM-C)
;(Rohteilmaße: 150 x 75 x 50 mm X/Y/Z)  <- blank dimensions
G94 G710    ; feed in mm/min, metric
G17         ; work in the XY plane
```

Lines starting `;` are comments. `G1` = cut in a straight line, `G0` = move fast without
cutting, `X… Y… Z…` = go to that coordinate.

**Use this to settle which axis is X:** the G-code names X/Y/Z coordinates explicitly, so
comparing a program's commanded path against `DES_POS|1/2/3` confirms the mapping from the data
rather than from convention.

**`Part description/<type>/*.stp`** — 3D CAD of the finished part, openable in any CAD viewer.

---

## 7. Data quality — check this before you trust a channel

**Two of the 33 trials are missing 12 columns entirely**, and they are not random trials:

| Missing in `IM-01R-A03` and `IM-01R-A04` | |
|---|---|
| `ENC_POS\|1,2,3,6` | the **actual** axis positions |
| `ENC2_POS\|1,2,3,6` | the second encoders |
| `LOAD\|1,2,3,6` | all motor loads |

Both are **tool-wear trials** — 2 of only 5 genuine drift experiments in the whole dataset. So
the obvious channel mapping silently throws away 40% of the training signal, with no error:

| Want | Obvious mapping | Coverage | Robust mapping | Coverage |
|---|---|---|---|---|
| `spindle_load` | `LOAD\|6` | **31/33** ❌ | `TORQUE\|6` or `CURRENT\|6` | **33/33** ✅ |
| `x_axis_error` | `DES_POS\|1 − ENC_POS\|1` | **31/33** ❌ | `CTRL_DIFF\|1` | **33/33** ✅ |

**Use `CTRL_DIFF|1` and `TORQUE|6`.** Earlier in this guide the two routes to following error
look interchangeable — at the level of arithmetic they are, but not at the level of *coverage*.
The controller's own `CTRL_DIFF` survives in trials where the encoder feed does not. That is
not a preference; it is the difference between 5 tool-wear trials and 3.

`LOAD` is a SINUMERIK diagnostic percentage derived from current anyway, so `TORQUE`/`CURRENT`
are also the more fundamental quantities.

### Beware naive thresholds

A first attempt at "is the machine cutting?" used `|TORQUE|6| > 5` and produced nonsense.
Spindle torque sits at **2–3.5 during actual work**; the 85 maximum is a rare spin-up
transient. That filter selected 310 acceleration spikes out of 610,343 rows — 0.6 seconds of a
20-minute file — and every statistic computed from it was meaningless.

Use the X axis actually being driven instead, which is true of ~78% of rows:

```python
moving = df[df["DES_POS|1"].diff().abs() > 1e-6]
```

## 8. What the drift signal actually looks like

Measured over all five tool-wear trials against the normal baseline, on rows where the X axis
is moving:

| Trial | mean \|CTRL_DIFF\| | p99 | mean \|TORQUE\|6\| | |
|---|---|---|---|---|
| `IM-01R` | 5.042 µm | 117.8 | **2.350** | normal |
| `IM-01R-A03` | 5.005 | 117.8 | **2.640** | worn |
| `IM-01R-A04` | 5.113 | 133.5 | **2.709** | worn |
| `IM-01R-A05` | 5.206 | 129.7 | **2.711** | worn |
| `IM-01R-A01` | 5.148 | 134.0 | **2.492** | worn + blowholes |
| `IM-01R-A02` | 5.132 | 134.1 | **2.565** | worn + blowholes |

### How those numbers are calculated

Each row of the table is four operations on one trial's `hfdata.csv`.

**1. Take the raw column.** `CTRL_DIFF|1` is in **millimetres** and is **signed** — the axis can
lag in either direction:

```
0   -0.000008
1    0.000002
2   -0.000008
```

**2. Mask to rows where the X axis is actually being driven.** An experiment includes idle
time, tool changes and pauses; following error is meaningless when nothing is moving.

```python
moving = df[df["DES_POS|1"].diff().abs() > 1e-6]     # 475,510 of 610,343 rows = 77.9%
```

**3. Take the absolute value.** The signed mean is `+0.078 µm` — the positive and negative lags
very nearly cancel, so it measures almost nothing. The absolute mean is `5.042 µm`.

**4. Convert mm → microns (×1000)** and reduce:

| Table column | Operation |
|---|---|
| mean \|CTRL_DIFF\| | `(moving["CTRL_DIFF\|1"].abs() * 1000).mean()` |
| p99 | the 99th percentile of that same series |
| mean \|TORQUE\|6\| | `moving["TORQUE\|6"].abs().mean()` — no unit conversion |

### Why a p99 as well as a mean

The distribution is not remotely bell-shaped:

| | p50 | p75 | p90 | p95 | **p99** | p99.9 | max |
|---|---|---|---|---|---|---|---|
| \|following error\| µm | 0.39 | 0.92 | 2.31 | 3.99 | **117.81** | 664.15 | 738.70 |

A **30× jump between p95 and p99**. The axis tracks its command to under a micron for 95% of
the time, then occasionally lags by more than half a millimetre. The mean of 5.04 µm describes
neither state — it is an average of "almost perfect" and "briefly terrible". The p99 is there
to measure the excursions, because that is where the variation actually is.

### ⚠️ What the excursions are — and why this matters more than the table

The spikes are **not** cutting load. They track axis motion:

| | mean \|velocity\| | mean \|acceleration\| |
|---|---|---|
| rows with error > 100 µm | 135.4 mm/s | 1614.5 mm/s² |
| rows with error < 5 µm | 4.7 mm/s | 3.4 mm/s² |

```
correlation( |following error| , |velocity|     ) = 0.70
correlation( |following error| , |acceleration| ) = 0.83
```

**Following error is dominated by how hard the servo is being accelerated, not by how blunt the
tool is.** The axis lags when asked to change direction quickly — that is ordinary servo
dynamics, present in a perfect machine.

This is a **confound**, and it is the single most important thing on this page. Two trials can
differ in mean following error purely because their motion profiles differ. Any comparison has
to control for it — by normalising against acceleration, by comparing matched toolpath
segments, or by leaning on **spindle torque**, which responds to cutting force directly and has
no equivalent motion artefact.

It also explains the table: mean following error barely separates worn from normal (5.04 vs
5.00–5.21) because servo dynamics swamp the wear signal, while torque separates consistently
(2.35 vs 2.49–2.71) because it is measuring the cut itself.

Read this honestly:

- **Spindle torque separates consistently but modestly** — every worn trial is 6–15% above
  normal. That is the clearest signal in the data.
- **Mean following error barely separates at all** (5.04 vs 5.00–5.21). The p99 tail is a
  little better (118 → 130-134 for four of five), but `A03` is indistinguishable from normal.
- **There is exactly one normal roughing baseline.** With a single normal run you cannot
  estimate how much of that 6–15% is just run-to-run variation. This is the central
  limitation of the dataset for this objective, and no amount of modelling removes it.

This is *why* you would train a model over windows rather than compare averages — but it is
also a warning that the separation is subtle, and that a confident-looking result from 5 worn
trials against 1 normal one deserves scepticism. `/synth-data` at M6 is not optional.

## 9. What this project uses

The edge device is to emit a `drift_score` (0–1, alert above 0.7) from three channels:

| Wanted channel | Use this | Why not the obvious one |
|---|---|---|
| `spindle_load` | `TORQUE\|6` (or `CURRENT\|6`) | `LOAD\|6` is missing in 2 of 5 tool-wear trials |
| `x_axis_error` | `CTRL_DIFF\|1` | the subtraction needs `ENC_POS`, missing in the same 2 |
| `vibration_rms` | `vibration_rms` from `data/interim/<trial>_sensor.parquet`, joined on `CYCLE` (§5) | not in the CSV at all; lives in the `.mat`, on a different clock |

Two open questions this data does **not** settle, both recorded in `data/profile.json`:

- **The channel list was never specified.** The original objective (`intent.yaml`, as recorded in
  `data/profile.json` at M2) says "vibration, temperature, dimensional accuracy, spindle load,
  etc." — `x_axis_error` is a stand-in for "dimensional accuracy", and **this dataset has no
  temperature channel at all**. The three channels are now fixed in `use_case.lock.json` (§12).
- **Only 5 of the 15 anomaly trials are genuine tool wear.** Six are commanded parameter
  changes (the "anomaly" is also an input column — a model would learn to read the commanded
  feedrate and detect nothing on a real line), and four are workpiece defects belonging to a
  different use case.

## 10. Quick start — verified, runs as written (re-run 2026-09-23, 4.5 s)

```python
import pandas as pd
base = "data/raw/Dataset/Injection mold"
cols = ["DES_POS|1", "CTRL_DIFF|1", "TORQUE|6"]      # all present in 33/33 trials

for trial, label in [("IM-01R", "normal"), ("IM-01R-A03", "worn"), ("IM-01R-A05", "worn")]:
    df = pd.read_csv(f"{base}/{trial}/processed_data/{trial}_hfdata.csv", usecols=cols)
    moving = df[df["DES_POS|1"].diff().abs() > 1e-6]  # NOT a torque threshold — see section 7
    err = moving["CTRL_DIFF|1"].abs() * 1000          # mm -> microns
    print(f"{trial:12} {label:7} torque {moving['TORQUE|6'].abs().mean():5.3f} "
          f"| following error mean {err.mean():5.2f} um  p99 {err.quantile(.99):6.2f} um")
```

`IM-01R` and `IM-01R-A03/A04/A05` were cut with **identical** parameters — same feed, speed,
depth and toolpath. The only difference is that the A-trials ran a worn tool. Any difference in
those numbers is the drift signal, with nothing else to explain it. That is the pair to build
the demo on — while keeping section 8's caveats in view.

---

# Part 2 — from the raw files to what the model reads

Part 1 ended with three channels worth using. Part 2 follows them from the 33 trials KIT recorded to
the windows the model is trained on. Every number here was read from a file in this folder on
**2026-09-23**: `data/profile.json`, `data/contract_sources.json`, `data/contract/`, `data/splits/`,
`data/synthetic/`, `data/synth-review.md` and `use_case.lock.json`. What the model then does with the
windows (epochs, folds, the result) is in [`model.md`](model.md).

---

## 11. Which trials are used — and which ten are not

The labels come from one decision, recorded in `data/profile.json` (`_taxonomy_decision_M4`, decided
by sanjkcog on 2026-09-17). Every trial is either used with a label, or excluded with a reason:

| Group | Trials | Count | What happens to it |
|---|---|---|---|
| **normal** | `IMP-BASE`, `IMP-01` … `IMP-12`, `TF-01` … `TF-03`, `IM-01R`, `IM-01F` | 18 | used, label `normal` |
| **tool_wear** | `IM-01R-A01` … `IM-01R-A05` | 5 | used, label `tool_wear` |
| commanded parameter change | `TF-01-A01`, `TF-02-A01`, `TF-03-A01`, `TF-03-A02`, `IM-01F-A01`, `IM-02F-A01` | 6 | **excluded** — leakage |
| workpiece defect | `IMP-01-A01` … `IMP-01-A04` | 4 | **excluded** — a different use case |

**Why the parameter-change trials are excluded, not labelled.** `DoE.csv` shows what makes them
anomalous: `TF-01-A01` is "Feedrate + 20%", `TF-03-A02` is "Overload: f_z + 60%, v_c + 60%". The
changed setting is also *in the input data*. The feedrate is visible in the `DES_POS` trajectory,
and `CMD_SPEED` is a column. A model trained on them would learn to read the commanded setting,
which means "this program was configured differently". A real line running its normal program
never shows that, so the model would detect nothing there.

**Why the workpiece defects are excluded.** Cavities, cracks and a chipped edge (`IMP-01-A01` …
`A04`) are faults *in the part*, not wear of the machine. They belong to a part-inspection use case.

**The caveat that stays with every number below.** Of the 5 tool-wear trials, `A01` and `A02` are
"Roughing with Toolwear **and Blowholes**" (`DoE.csv`). Only `A03`, `A04` and `A05` are pure wear, and
`config.yaml` records them as `pure_wear_units`. And there is exactly **one** normal run of the same
program, `IM-01R` (§8).

---

## 12. From 500 Hz to 10 Hz — the contract dataset

The controller writes 500 rows a second (§3). The edge device scores 10 readings a second
(`use_case.lock.json`: `sample_rate_hz: 10`). So before anything is trained, every trial is
reduced **once**, in `data/contract/<trial>.parquet`, and every later step reads only that. The
recipe is `data/contract_sources.json`:

| Contract channel | Source | How 50 ticks (100 ms) become one row | Unit |
|---|---|---|---|
| `spindle_load` | `TORQUE\|6` in `hfdata.csv` | mean | Nm (declared, see §17) |
| `x_axis_error` | `CTRL_DIFF\|1` in `hfdata.csv` | mean, × 1000 (mm → µm) | µm |
| `vibration_rms` | `vibration_rms` in `data/interim/<trial>_sensor.parquet` (§5) | exact pooled RMS, weighted by `n_samples` | g (assumed, see §17) |

So one contract row is one 100 ms step: `block_start` (the first `CYCLE` of the 50), `split`,
`label` and the three channels. A 100 ms block with a missing controller tick is **dropped, not
filled**. `IM-01R`'s 610,343 raw rows become 11,865 contract rows. `data/profile.json` records a
spot check: `IM-01R-A04` block 0, recomputed from the raw files, gives identical values.

**Two things that differ from Part 1's numbers, on purpose.**

- **The contract keeps the sign.** §8 averaged `|CTRL_DIFF|` over moving rows, to measure how
  large the lag is. The contract takes the plain 100 ms mean, as the device will. Spindle torque is
  signed too: its mean is −2.4 Nm, from the spindle's direction convention (`data/profile.json`). So
  a real window's `spindle_load` is negative.
- **The contract keeps idle time.** Nothing is masked to "the axis is moving", because the device
  cannot know that in advance. Averages over whole trials therefore differ from §8's.

**Measured on the contract rows, whole trials:**

| Trial | label | mean \|`spindle_load`\| (Nm) | mean `vibration_rms` |
|---|---|---|---|
| `IM-01R` | normal | 2.155 | 5.681 |
| `IM-01R-A03` | worn | 2.414 | 5.417 |
| `IM-01R-A04` | worn | 2.434 | 5.509 |
| `IM-01R-A05` | worn | 2.456 | 5.469 |

Torque is 12–14% higher on every pure-wear trial, the same direction as §8. **`vibration_rms` goes
the other way:** it is *lower* on all three worn trials than on the one normal run. This guide
cannot tell whether that is wear (a blunt tool can cut more smoothly), the accelerometer mounting,
or run-to-run variation, because there is only one normal run to compare against. So do not read a
rise in vibration as a sign of wear in this dataset.

---

## 13. From rows to windows — what the model actually sees

One 100 ms row tells you nothing. Tool wear shows up as a *pattern over several seconds*. So the
contract rows are cut into short overlapping clips called **windows**. Three numbers from
`use_case.lock.json` decide how:

| Setting | Value | In plain terms |
|---|---|---|
| `sample_rate_hz` | 10 | ten rows per second |
| `window_samples` | 64 | each clip is 64 rows = **6.4 seconds** |
| `stride_samples` | 10 | a new clip starts every 10 rows = **every 1 second** |

Picture a 6.4-second ruler laid on the recording. Note what is under it. Slide it forward one
second. Note it again. Keep going to the end of the trial.

```
recording  ────────────────────────────────────────────────────►  time
window 1   [══════ 6.4 s ══════]
window 2      [══════ 6.4 s ══════]        ← starts 1 s later
window 3         [══════ 6.4 s ══════]
                 ↑ 5.4 s of window 2 is also in window 3
```

Because the ruler moves 1 second but is 6.4 seconds wide, **consecutive windows share 5.4 seconds
of identical data**. The overlap is deliberate: it multiplies how many examples six hours of
milling gives you. It is also a trap, and §14 is about the trap.

### One real window, laid out

Each window is a grid of 3 channels × 64 rows, plus one label. This one is real: `IM-01R-A04`, val
split, starting at `block_start` 5410450.

```
               t=0.0s   t=0.1s   t=0.2s   ...   t=6.3s    window mean
spindle_load [ -1.08    -1.08    -1.09    ...    -1.10 ]   -1.625   Nm
x_axis_error [ -1.26    -1.35    -1.52    ...     0.48 ]   -0.228   um
vibration_rms[  5.97     6.32     6.34    ...     5.84 ]    5.690   g
                                                 label: tool_wear
```

A normal window from the same program looks almost the same. `IM-01R`, val, at `block_start`
3623050, has window means of −2.247 Nm, −0.368 µm and 5.97 g. You cannot see wear by eye in one
window, and that is why this is a model and not a threshold.

That 3 × 64 grid is one training example: 192 numbers. The label is not measured from the signal.
It comes from **which trial the window was cut out of** (§11). Every window from `IM-01R-A04` is
`tool_wear`, because that whole trial was cut with a worn tool. Every window from `IMP-03` is
`normal`.

> The model is told "these 192 numbers mean worn". If the real difference between two trials were
> something other than tool wear, such as a different feedrate or a blowhole, the model would learn
> *that* instead, and nobody would know. `IM-01R` against `IM-01R-A03/A04/A05` is the comparison to
> trust: same program, same parameters, only the tool differs (§10). `A01` and `A02` also carry
> blowholes (§11).

A window never straddles a gap. A window that would run past the end of a split segment is not cut.

---

## 14. The three splits — and why they are by trial, not by row

You need data the model has never seen, to check it learned something real and did not just
memorise. The obvious move is to shuffle all the windows and take 20% for testing. That is
**catastrophically wrong here**.

Consecutive windows share 5.4 of their 6.4 seconds. Shuffle randomly, and window 2 lands in train
while window 3 lands in test. They are 84% the same numbers, so the model scores brilliantly on a
test set it has effectively already read. You would ship a model that looks 99% accurate and
detects nothing on a real machine. This mistake is called **leakage**.

The fix is to split by **trial**, never by row. A whole trial goes into one split. The model learns
from `IM-01R-A01`, and it never sees `IM-01R-A04` until it is scored on it.

Read from `data/splits/*.json` (`split_hash` `47871db08ccc…`). The window counts are computed from
`data/contract/` with the lock's window and stride:

| Split | Units | Normal | Worn | Worn unit | Contract rows | Windows (normal / worn) | What it is for |
|---|---|---|---|---|---|---|---|
| **train** | 16 | 13 | 3 | A01, A02, A05 | 81,729 | 4,491 / 3,588 = **8,079** | the model learns from these |
| **val** | 5 | 4 | 1 | A04 | 24,779 | 1,244 / 1,204 = **2,448** | picks the best epoch and sets the alarm threshold |
| **test** | 4 | 3 | 1 | A03 | 19,919 | 775 / 1,193 = **1,968** | **sealed**, opened once at the very end |

Three things to notice:

**`IM-01R` appears in all three splits.** That is a documented deviation, not a bug. It is the only
normal run of the worn-tool program, so it is cut by **time**: the first 714 s train, the next 231 s
validate, and the last 241 s test. A **10-second gap** sits at each boundary, longer than one 6.4 s
window, so no window can span two splits (`data/splits/*.json`, `segment.rule`). The gaps were
widened from 5 s on 2026-09-18, when the window became 6.4 s. The cost: the test segment is the tail
of a run whose head was trained on, which can make the false-alarm rate look better than it is. The
portal's held-out result repeats that caveat.

**val and test do different jobs.** The model is checked against val after every epoch, so val
steers the training: which epoch is kept, and where the alarm threshold sits. That makes val *used*,
and a number measured on it is flattering. It is labelled `eval_split: self_reported_val`. Test is
opened once, after everything is decided, and its number is labelled `held_out_test`.

**Four worn trials outside test, one per split role.** A01, A02 and A05 teach, A04 validates, and A03
is sealed. Four is the number of worn trials that can ever be held out one at a time.
[`model.md`](model.md) is about what that does to how much you can trust a result.

---

## 15. Synthetic data — what was added, and where it is never used

With 3 worn trials to learn from, M6 generated more (`data/synthetic/`, recipe in
`data/synthetic-recipe.md`, seed 20260918). There are 30 `SYN-normal-*` and 30 `SYN-tool_wear-*`
units, all made by **block-bootstrapping real train rows** of the `IM-01R` program. Real stretches of
15–40 s are resampled and stitched, then a wear signature is ramped in. It is not a physics
simulation.

| Class | Real train windows | Synthetic windows made | Synthetic windows used (cap: 50% of real) | Share synthetic |
|---|---|---|---|---|
| normal | 4,491 | 35,867 | 2,245 | 33% |
| tool_wear | 3,588 | 35,719 | 1,794 | 33% |

So training sees at most 4,039 synthetic windows (`data/synth-review.md`). The gate approved it on
2026-09-19 with this reason: "train-only synthetic, capped 50% of real per class; kept only if it
beats real-only on real val at M8".

**Where synthetic data is never used:** val and test. The alarm threshold is set on real data
only. Test measures the real result, including any gap between synthetic and real.

**Its limits, from the review pack, as written:**

- The wear signature comes largely from **one** pure-wear trial (`A05`).
- The spread is slightly below real, at 81–84% of real std on `spindle_load` and 84–91% on
  `vibration_rms`.
- There is no cross-channel physics beyond a linear correlation nudge.
- Blocks are stitched with no crossfade.
- Every synthetic unit is the `IM-01R` program. Synthesis adds variety *within* one program, not
  new programs.

---

## 16. What leaves this folder

Nothing in `data/` is uploaded by hand from here. Each file that goes to the portal is staged in
`../to-neuroedge/` (AgentForge ADR-0031), and `/agentforge-ml handoff` says where each goes.

| File | Holds | Goes to |
|---|---|---|
| `data/portal_test.zip` → `to-neuroedge/02-M9-test-bundle.zip` | the **sealed test split** (A03, IMP-05, TF-02, IM-01R tail) | Step 3 · Train → Held-out evaluation, only |
| `data/portal_upload.zip` | train + val only (never test) | used only on the fine-tune route, which this project is not on |
| `sim/` → `to-neuroedge/05-M12-simulator-data.zip` | the val split as 10 Hz CSVs, `debug_and_parity` | Step 5 · Virtual Run |
| `sim-demo/` → `to-neuroedge/06-M12-demo-simulator-data.zip` | 5 min composed from val: 70% `tool_wear` windows, first at 30 s | Step 5 · Virtual Run, **for a demo only** |

`data/portal_test.zip` **is** the test data, so it stays out of git (the project's `.gitignore`).
So do the staged copies (`to-neuroedge/.gitignore`), `data/raw/`, and the parquet files in
`data/interim/`, `data/contract/` and `data/synthetic/`, all of which rebuild from the raw files and
the lock. Their manifests stay tracked.

> The demo in `sim-demo/` is deliberately weighted toward `tool_wear`. **Every rate measured on it
> (false alarms, precision, recall) is meaningless as a measurement of the model.** Use `sim/` for
> anything you would call evidence.

---

## 17. Still unconfirmed

These are the claims this guide could **not** check against a file. Each is stated where it is
used, and they are collected here so none is lost:

| Claim | Why it is unconfirmed | What settles it |
|---|---|---|
| Axis `1` = X, `6` = spindle (§1) | the dataset never says; it is the convention for this machine class | compare an NC program's X path against `DES_POS\|1` (§6) |
| `vibration_rms` is in *g* (§5, §12) | KIT's README names the sensor (PCB 356A33) but no unit; the values are plausible in g | the sensor's data sheet or KIT |
| `spindle_load` is in Nm (§12) | the lock declares Nm; KIT's README lists "torque" with no unit | SINUMERIK documentation for `TORQUE\|n` in the Analyze MyWorkpiece export |
| The edge device has an accelerometer (§5) | this one was bolted on for the experiment; a typical plant has only controller signals | the target device's sensor list. Without one, `vibration_rms` cannot be an input |
| How much of the 6–15% torque difference is wear (§8, §12) | there is one normal run of the program, so run-to-run variation cannot be measured | more normal runs of `IM-01R` |
| Why vibration is *lower* on worn trials (§12) | same single-baseline problem | as above |

The use case was also never written for this dataset. The original objective named "vibration,
temperature, dimensional accuracy, spindle load, etc." (recorded in `data/profile.json` at M2).
KIT has no temperature channel, and `x_axis_error` stands in for dimensional accuracy. The three
channels in `use_case.lock.json` are what this dataset can honour, not everything the objective
asked for.

## Attribution

Using this data requires crediting the authors (CC BY 4.0):

> Ströbel, R. et al. (2025). *A Multimodal Dataset for Process Monitoring and Anomaly Detection
> in Industrial CNC Milling.* Karlsruhe Institute of Technology.
> DOI: 10.35097/hvvwn1kfwf7qt48z. Licensed under CC BY 4.0.

This must reach the model card and the product NOTICE, not just this file.
