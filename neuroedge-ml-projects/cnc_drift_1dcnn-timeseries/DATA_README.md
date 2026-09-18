# Reading the KIT CNC milling data — a beginner's guide

What this data is, where each number comes from, and how to open every file. Everything below
was checked against the files actually on disk in `data/raw/`, not copied from the dataset's
description.

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

**What's inside:** the 10 kHz signals from the force platform (cutting force in X, Y, Z) and
the spindle accelerometer (vibration). This is where `vibration_rms` has to come from — it is
**not** in the CSV.

### Why MATLAB at all?

MATLAB is the standard tool in mechanical-engineering labs, and its **timetable** type stores
a signal with its timestamps attached as one object. KIT saved them the way they worked with
them. It is a convenience for the authors, not a format choice aimed at Python users.

### The catch — verified on these files

These are **MATLAB object files (MCOS timetables)**, not plain arrays. `scipy` cannot decode
them:

```python
import scipy.io
m = scipy.io.loadmat("IMP-01.mat")
# -> {'None': MatlabOpaque(...)}     class 'timetable', variable 'tmp_new'
```

You get an opaque handle, not data. Options, in order of least effort:

1. **`pymatreader`** (`pip install pymatreader`) — handles MCOS objects.
2. **Octave** (free) or MATLAB — load and re-export to CSV/Parquet once:
   `load('IMP-01.mat'); writetimetable(tmp_new, 'IMP-01.csv')`
3. **Read the JSON Edge export instead** — only if you need controller signals, which are
   already in the CSV anyway.

Convert once, work in Parquet thereafter.

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
| `vibration_rms` | accelerometer in `raw_data/*.mat`, RMS per window | not in the CSV at all — needs the conversion in §5 |

Two open questions this data does **not** settle, both recorded in `data/profile.json`:

- **The channel list was never specified.** The use case (`intent.yaml`) says "vibration,
  temperature, dimensional accuracy, spindle load, etc." — `x_axis_error` is a stand-in for
  "dimensional accuracy", and **this dataset has no temperature channel at all**.
- **Only 5 of the 15 anomaly trials are genuine tool wear.** Six are commanded parameter
  changes (the "anomaly" is also an input column — a model would learn to read the commanded
  feedrate and detect nothing on a real line), and four are workpiece defects belonging to a
  different use case.

## 10. Quick start — verified, runs as written

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

## Attribution

Using this data requires crediting the authors (CC BY 4.0):

> Ströbel, R. et al. (2025). *A Multimodal Dataset for Process Monitoring and Anomaly Detection
> in Industrial CNC Milling.* Karlsruhe Institute of Technology.
> DOI: 10.35097/hvvwn1kfwf7qt48z. Licensed under CC BY 4.0.

This must reach the model card and the product NOTICE, not just this file.
