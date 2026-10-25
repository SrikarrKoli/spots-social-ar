# Feature Spec: Sustained Camera and Application Performance

Status: Approved for implementation
Last updated: 2026-10-25

## Context

The live camera feed and the rest of the application become slower during a
session. The current implementation reads a frame, recognizes it against every
loaded reference, JPEG-encodes it, and only then reads the next frame. Automatic
view banking adds references and performs feature extraction plus file/database
writes in that same processing path.

The current local data contains 71 persisted fingerprints, including 59
auto-banked views. Loading them produces 111 in-memory scale variants and about
39,600 keypoints. A local benchmark of the current code measured a 1280x720
recognition pass at roughly 61 ms with three in-memory references and 209–215
ms with all 111 references. OpenCV currently uses all 10 logical CPU cores, and
the configured local Faster Whisper `medium` model can contend for the same CPU
during transcription.

The frontend polling loops are serial and the MJPEG service retains only the
latest encoded frame, so the evidence does not point to an unbounded browser
request queue. The primary failure is growing and unbounded work per frame,
combined with capture, recognition, banking, persistence, and encoding being
too tightly coupled.

## Objectives and Success Criteria

- Camera capture must always favor the newest frame; slow recognition must not
  create an application-level backlog of stale frames.
- With the current five-object database, active recognition references are
  bounded to at most four persisted views per identity and a documented,
  bounded number of scale variants.
- Automatic banking must not grow persisted or in-memory recognition work
  beyond its configured limits, including after track expiry or app restart.
- On the demo laptop, sustain at least 15 displayed camera FPS and at least 8
  recognition updates per second for 20 minutes, with p95 capture-to-display
  age below 250 ms when local transcription is idle.
- During one local transcription, camera display should remain at least 10 FPS
  with p95 frame age below 500 ms; typed UI interactions must remain usable.
- After warm-up, a 20-minute fixture soak must show no monotonic reference-count
  growth and less than 100 MB RSS growth, excluding initial Whisper model load.
- `GET /api/recognition` should have p95 server latency below 50 ms with five
  detected identities and must not load complete conversation threads on every
  poll.
- Recognition correctness tests and the existing post, enrolment, voice, and
  transcription behavior must continue to pass.

## Scope

### Included

- A latest-frame capture architecture with independent capture, recognition,
  and shared JPEG encoding cadences.
- Configurable and validated limits for recognition cadence, stream cadence,
  analysis resolution, OpenCV worker threads, JPEG quality, and active views.
- A bounded active-reference policy at startup and runtime.
- Bounded automatic banking with near-duplicate rejection and no reset of its
  lifetime limit when a visible track expires.
- A dry-run-first maintenance command for identifying and optionally pruning
  surplus auto-banked files and database rows; no automatic deletion.
- Moving feature extraction and persistence off the capture critical path and
  serializing recognizer reads/mutations safely.
- Lightweight recognition enrichment that avoids repeated full-thread queries.
- Removal of duplicate frontend fetches and isolation of high-frequency camera
  state updates from the thread/composer subtree where practical.
- Lower-contention defaults for OpenCV and documented local-transcription
  options.
- Repeatable performance benchmarks, soak checks, metrics, tests, and docs.

### Excluded

- WebRTC, native glasses video transport, GPU-specific deployment, distributed
  processing, or a replacement of the application stack.
- Replacing SIFT/ORB with embeddings or a learned recognition model in this
  pass. Matcher/index work is a gated follow-up only if bounded references and
  pipeline separation miss the targets.
- Automatically deleting existing user enrolments, posts, fingerprints, or
  files during startup or migration.
- Changing recognition confidence thresholds merely to improve benchmark
  numbers; any threshold change requires a separate accuracy evaluation.
- Visual redesign or unrelated refactoring.

## Proposed Design and File Changes

### 1. Baseline instrumentation and regression harness

- `scripts/benchmark_performance.py` — add a read-only benchmark that loads the
  configured references and reports physical reference files, in-memory
  variants, keypoints, load time, per-frame recognition latency, and estimated
  throughput as machine-readable JSON plus a concise human summary.
- `backend/app/camera.py` — track rolling capture FPS, recognition FPS, stream
  FPS, recognition duration, captured frame sequence, source capture time, last
  published frame age, active stream clients, and active reference counts.
- `backend/app/models.py`, `backend/app/main.py` — expose diagnostics through a
  development/status endpoint or structured periodic log, not in the normal
  250 ms recognition payload.
- Record capture time immediately after `read()`, rather than assigning the
  timestamp after recognition, so latency measurements cannot hide processing
  delay.

### 2. Bound reference work before changing concurrency

- `backend/app/config.py`, `.env.example` — add validated settings with initial
  demo defaults:
  - `APP_MAX_REFERENCE_FILES_PER_IDENTITY=4`
  - `APP_MAX_AUTO_BANKED_FILES_PER_IDENTITY=2`
  - `APP_RECOGNITION_MAX_WIDTH=960`
  - `APP_RECOGNITION_FPS=8`
  - `APP_STREAM_FPS=15`
  - `APP_STREAM_JPEG_QUALITY=75`
  - `APP_OPENCV_THREADS=3`
- `backend/app/repositories.py` — return reference metadata grouped by identity
  and distinguish primary/manual/live views from auto-banked paths. Selection
  retains the primary view, prefers deliberate live/manual views, and fills any
  remaining slots with diverse auto-banked views in stable order.
- `backend/app/recognition.py` — make reference loading accept an explicit
  bounded selection. Do not generate a redundant half-scale variant for crops
  already near the live analysis size. Enforce a second hard cap on total
  in-memory variants so scale expansion cannot bypass the physical-file cap.
- `backend/app/camera.py` — make banking limits lifetime-per-identity for the
  process, derived from recognizer/repository state rather than `_bank_state`
  attached to a temporary visible track. Reject near-duplicate crops using the
  existing small grayscale thumbnail comparison before feature extraction and
  persistence.
- Existing surplus references remain on disk and in SQLite but are inactive;
  this provides an immediate performance recovery without destructive startup
  behavior.
- `scripts/prune_reference_views.py` — report active/retained/surplus views and
  estimated reclaimed space by default. Require an explicit `--apply`, create a
  database backup first, delete only surplus `-banked-` artifacts, and leave
  primary/manual/live views untouched. This command is not run automatically.

### 3. Separate capture, recognition, encoding, and banking

- `backend/app/camera.py` — replace the serialized `read -> detect -> encode`
  loop with three bounded latest-value loops:
  1. A capture owner continuously reads the camera and atomically overwrites a
     one-frame raw slot with frame sequence and capture timestamp.
  2. A recognition worker samples only the newest unprocessed frame at the
     configured recognition cadence. It analyzes a downscaled copy and maps
     corners back into source-frame coordinates.
  3. A shared encoder samples the newest raw frame at the configured stream
     cadence and publishes one JPEG for all clients. It pauses when there are
     no stream clients.
- Set `CAP_PROP_BUFFERSIZE=1` when the backend supports it, while keeping the
  latest-frame overwrite as the correctness mechanism because buffer controls
  are backend-dependent.
- Use conditions/events rather than busy loops. Shutdown must wake and join all
  workers, release `VideoCapture` exactly once, and preserve fixture mode.
- Protect recognizer detection and reference mutation with a narrow lock or a
  single recognition-worker command queue. Live enrolment, confirmation,
  add-view, and removal operations must not mutate `_references` while detection
  iterates it.
- Move PNG encoding, file writes, and fingerprint insertion to a bounded
  persistence worker. A full queue drops/rejects an optional bank operation
  rather than delaying capture; explicit enrolment remains synchronous and
  reports failure.

### 4. Reduce backend and frontend steady-state work

- `backend/app/repositories.py`, `backend/app/main.py` — replace per-detection
  `object_by_identity` plus full `thread()` reconstruction with one bounded
  query/cache that returns object summary and only the latest root/reply preview.
  Invalidate/update the cache after post and enrolment writes.
- `backend/app/database.py` — configure WAL and persistent database pragmas at
  initialization rather than attempting `PRAGMA journal_mode=WAL` on every
  short-lived read connection. Keep foreign-key and busy-timeout settings per
  connection.
- `frontend/src/components/ThreadPanel.tsx` — remove the duplicate request caused
  by the object-change effect and the polling hook both fetching immediately.
- `frontend/src/App.tsx`, `frontend/src/components/CameraStage.tsx` — keep rapid
  recognition state local to/memoized around the camera subtree so coordinate
  updates do not unnecessarily reconcile the thread, composer, voice controls,
  and enrolment UI.
- `frontend/src/hooks/usePolling.ts` — retain serialized non-overlapping polls,
  pause recognition polling while the document is hidden, and resume with one
  immediate refresh. Keep the 1.5-second cross-session thread freshness goal.
- Only remove `backdrop-filter` or other paint-heavy styles if browser profiling
  shows material main-thread/GPU cost; do not pre-emptively degrade the design.

### 5. Control CPU contention and transcription impact

- Apply `cv2.setNumThreads(APP_OPENCV_THREADS)` once during backend startup and
  document the tradeoff. The default leaves CPU capacity for the browser and
  Faster Whisper.
- Keep the current transcription API, but document `small`/`base`, cloud, and
  disabled options for constrained laptops. Add a configurable policy to reduce
  recognition cadence during local inference rather than stopping capture or
  streaming.
- Do not unload/reload the Whisper model per request. Measure RSS after its
  one-time load separately from steady-state growth.

### 6. Gated matcher optimization

- After phases 1–5, rerun the same corpus and hardware acceptance checks.
- Only if recognition still misses its 8 Hz target, benchmark FLANN or a shared
  descriptor index against the current `BFMatcher` per-reference loop.
- Adopt a matcher change only if it materially improves p95 latency while
  preserving known-object, swapped-position, partial-frame, and unknown-scene
  outcomes. Otherwise keep the simpler bounded brute-force matcher.

### Expected Files

- `backend/app/camera.py` — latest-frame workers, safe banking, metrics.
- `backend/app/recognition.py` — bounded references, scale/dedup policy, optional
  gated matcher work.
- `backend/app/config.py` — validated performance settings.
- `backend/app/database.py`, `backend/app/repositories.py` — lower-overhead
  connections, bounded reference metadata, lightweight previews.
- `backend/app/main.py`, `backend/app/models.py` — startup settings, diagnostics,
  recognition enrichment and cache invalidation.
- `backend/app/transcription.py` — inference activity signal for adaptive
  recognition throttling, without changing transcription behavior.
- `backend/tests/` — concurrency, bounded-growth, mapping, API, and soak-oriented
  regression tests.
- `frontend/src/App.tsx`, `frontend/src/components/CameraStage.tsx`,
  `frontend/src/components/ThreadPanel.tsx`, `frontend/src/hooks/usePolling.ts`
  — render and polling reductions.
- `scripts/benchmark_performance.py`, `scripts/prune_reference_views.py` —
  repeatable measurement and explicit maintenance.
- `backend/tests/performance/`, `frontend/src/performance.test.tsx` — opt-in
  timing/soak coverage and CI-safe structural performance regressions.
- `.env.example`, `README.md`, `TODO.md`, `HANDOFF.md` — configuration,
  operation, remaining physical checks, and verified results.

## Performance Test Design

Performance coverage is split into three tiers so normal CI catches structural
regressions without relying on brittle wall-clock thresholds, while repeatable
machine-specific tests still prove the end-to-end targets.

### Tier 1: CI-safe performance invariants

These tests run in the default backend/frontend suites and use fake clocks,
fake capture, counters, and deliberately slow test doubles rather than timing
the host machine.

- `backend/tests/test_camera_performance.py`
  - feed capture faster than recognition and assert only the newest frame is
    processed, with no queue longer than one;
  - block recognition and assert capture sequence continues advancing;
  - block JPEG encoding and assert recognition continues independently;
  - connect two MJPEG consumers and assert each published frame is encoded once,
    not once per consumer;
  - disconnect the last stream consumer and assert encoding becomes idle;
  - advance a fake clock and assert configured capture/recognition/stream
    cadence and true frame-age metrics;
  - fill the bank-persistence queue and assert optional banks are rejected or
    coalesced without blocking capture;
  - start/stop repeatedly and assert no worker thread or camera handle leaks.
- `backend/tests/test_recognition_performance.py`
  - load more than the configured per-identity file/variant limits and assert
    the active counts remain bounded;
  - expire and reacquire a track repeatedly and assert banking capacity does not
    reset or grow references;
  - add perceptually duplicate views and assert they are rejected before SIFT/
    ORB feature extraction;
  - verify analysis downscaling and source-coordinate restoration without an
    extra full-resolution feature pass;
  - use a counting matcher to assert work is proportional to the bounded active
    set, not all historical fingerprint rows.
- `backend/tests/test_api_performance.py`
  - use repository spies/query counters to assert one recognition snapshot does
    not issue N+1 object/full-thread reads;
  - assert a cached preview is invalidated by post/enrolment writes;
  - assert diagnostics collection does not add database work to every normal
    recognition poll.
- `frontend/src/hooks/usePolling.test.ts`
  - assert slow requests never overlap;
  - assert hidden-document polling pauses and focus/visibility resume performs
    exactly one immediate request;
  - assert unmount aborts the in-flight request and leaves no timer.
- `frontend/src/performance.test.tsx`
  - count thread/composer renders while dispatching many synthetic recognition
    updates and assert the non-camera subtree does not rerender per frame;
  - assert selecting an object produces one immediate thread request rather
    than the current duplicate initial requests;
  - assert camera updates preserve draft, recording, and enrolment state.

### Tier 2: opt-in deterministic microbenchmarks

- Add a `performance` pytest marker in `pyproject.toml`. Default tests exclude
  no correctness coverage; timing-sensitive tests run explicitly with
  `.venv/bin/python -m pytest -m performance`.
- `backend/tests/performance/test_recognition_benchmark.py` runs the committed
  fixture corpus at fixed analysis sizes and active-reference counts. It records
  warm-up separately, then reports median, p95, standard deviation, and frames
  per second over at least 30 measured iterations.
- `backend/tests/performance/test_pipeline_benchmark.py` uses a synthetic 30 FPS
  source plus controlled slow recognizer/encoder to measure dropped/stale frame
  behavior, capture-to-publish age, and worker throughput over a short run.
- `scripts/benchmark_performance.py` supports:
  - `--output <json>` for a machine-readable artifact;
  - `--compare <baseline.json>` for before/after deltas;
  - `--max-regression-percent` for an opt-in local gate;
  - reference-count and resolution matrices without mutating the database.
- Machine-independent assertions cover only bounds and relative complexity
  (for example, 100 historical rows still activate at most 20 views for five
  identities). Absolute millisecond/FPS thresholds are evaluated on the demo
  laptop and are not hard-coded into shared CI.
- A matcher experiment must run the same benchmark and accuracy corpus for both
  implementations and emit one comparison artifact. No matcher is selected on
  speed alone.

### Tier 3: system and soak tests

- `scripts/soak_performance.py` samples the diagnostics endpoint at one-second
  intervals and writes JSONL/summary output containing capture, recognition,
  and stream rates; p50/p95/max frame age; p50/p95 recognition time; reference
  counts; queue/drop counters; API latency; process RSS; and active clients.
- Fixture soak: 20 minutes with repeated synthetic track expiry/reacquisition,
  periodic enrolment scans, and two stream clients. It must satisfy the RSS and
  bounded-reference criteria and demonstrate one shared encoder.
- Physical soak: 20 minutes with motion, leave/return cycles, venue-like
  lighting, and the black bottle plus seeded objects. Capture/display and
  recognition targets are evaluated here.
- Contention soak: repeat a five-minute physical segment while transcribing one
  real microphone recording with Faster Whisper and interacting with the
  composer. Record the idle/transcribing/recovery windows separately.
- Browser profile: capture one short Chromium performance trace before and
  after. Inspect scripting, rendering, image decode, long tasks, and memory;
  only make CSS/GPU changes if the trace identifies them as material.
- Run each hardware scenario at least three times after a short warm-up. Compare
  medians and p95 values, retain the raw JSON artifacts outside source control,
  and summarize the chosen run set in `HANDOFF.md`.

### Initial baseline to preserve

The existing ad hoc measurement becomes the first documented baseline:

| Active in-memory refs | Analysis size | Mean recognition | Estimated FPS |
| ---: | ---: | ---: | ---: |
| 111 | 1280x720 | 215 ms | 4.6 |
| 20 | 1280x720 | 106 ms | 9.5 |
| 20 | 640x360 | 72 ms | 13.9 |
| 10 | 640x360 | 57 ms | 17.6 |

These numbers are directional because the initial script used four iterations
and one enrolled image. The formal benchmark must use warm-up plus at least 30
iterations and the full recognition acceptance corpus before claiming final
improvement.

## Implementation Checklist

- [ ] Capture and save the current baseline benchmark without modifying data.
- [ ] Add metrics and tests that distinguish capture FPS, recognition FPS,
      stream FPS, processing duration, and true frame age.
- [ ] Add CI-safe camera, recognition, API-query, polling, and render-count
      performance regression tests.
- [ ] Add opt-in pytest microbenchmarks, baseline comparison artifacts, and a
      diagnostics-driven soak runner.
- [ ] Add validated performance settings and lower-contention defaults.
- [ ] Bound startup reference selection and in-memory scale variants.
- [ ] Make automatic banking lifetime-bounded and reject near-duplicates.
- [ ] Add the dry-run-first surplus-bank maintenance command and tests.
- [ ] Split capture, recognition, shared encoding, and bank persistence into
      bounded latest-value workers with clean lifecycle handling.
- [ ] Add concurrency tests for enrol/add/remove while recognition is active.
- [ ] Downscale only the analysis copy and verify coordinates map to the source.
- [ ] Replace recognition endpoint N+1/full-thread reads with a preview query or
      cache and move WAL setup out of each connection.
- [ ] Remove duplicate thread fetches and isolate camera-frequency React renders.
- [ ] Add hidden-document polling pause/resume behavior.
- [ ] Limit OpenCV threads and add adaptive recognition cadence during local
      transcription.
- [ ] Run automated checks, fixture benchmark/soak, and physical camera soak.
- [ ] Evaluate matcher optimization only if targets remain unmet.
- [ ] Update documentation, checklist status, and `HANDOFF.md` with measured
      before/after results and unresolved hardware uncertainty.

## Edge Cases and Risks

- Downscaled analysis coordinates must be mapped back exactly or overlays and
  perspective crops will drift.
- A slow or failed persistence worker must never stall capture, but explicit
  user enrolment must still return a truthful success/failure result.
- Reference pruning can reduce viewpoint coverage. Runtime selection and the
  cleanup tool need deterministic retention rules and recognition corpus tests.
- Camera backends may ignore `CAP_PROP_BUFFERSIZE`; correctness cannot depend on
  that property.
- Multiple stream clients must share one encoder rather than multiply JPEG work.
- Fixture mode must not spin without pacing after capture/worker separation.
- Locks must never be held during network streaming, disk I/O, SQLite work, or
  long waits. Lock ordering and shutdown behavior need explicit tests.
- Auto-bank filenames are currently the only reliable signal for older banked
  rows. The maintenance command must refuse ambiguous paths rather than delete
  them.
- Reducing OpenCV threads may increase isolated recognition latency even while
  improving whole-system responsiveness; acceptance uses end-to-end metrics.
- Local Whisper CPU inference can still cause thermal throttling. Adaptive
  cadence and smaller-model guidance reduce but do not eliminate that hardware
  constraint.
- The working tree already contains substantial uncommitted user changes.
  Implementation must preserve them and avoid broad rewrites.

## Verification Plan

- Backend unit tests:
  - latest raw slot overwrites stale sequences and never queues frames;
  - recognition and stream workers honor configured cadence;
  - capture timestamp survives processing and frame age is accurate;
  - reference file and variant caps hold on startup, bank, expiry, and restart;
  - duplicate views are rejected before feature extraction/persistence;
  - bank persistence queue is bounded and capture remains live when it is full;
  - analysis-scale corners map correctly to source-frame coordinates;
  - stream client connect/disconnect starts/stops shared encoding work;
  - concurrent detection/enrol/remove does not mutate references unsafely;
  - worker failure and shutdown release the camera and terminate all threads.
- Repository/API tests:
  - reference selection is stable and prioritizes primary/manual views;
  - recognition preview query returns the same user-visible content without
    constructing every full thread;
  - post/enrolment writes invalidate cached previews;
  - maintenance command dry-run is non-mutating, backs up before apply, and
    touches only surplus auto-banked records/files.
- Frontend tests:
  - one immediate thread load occurs per selected-object change;
  - polls remain non-overlapping and abort on unmount;
  - hidden documents pause recognition polling and resume immediately;
  - camera updates do not reset composer, recorder, or thread state.
- Automated checks:
  - `.venv/bin/python -m pytest`
  - `.venv/bin/python -m pytest -m performance`
  - `npm test -- --run`
  - `npm run build`
- Performance checks:
  - record before/after benchmark JSON using the same current database and
    image corpus;
  - 20-minute fixture soak with reference/RSS/latency assertions;
  - 20-minute physical camera run with motion and repeated leave/return cycles;
  - repeat the physical run while performing one local transcription;
  - verify at least one and two simultaneous browser clients share the encoder.
- Recognition acceptance corpus:
  - seeded fixture identities;
  - swapped positions;
  - rotated/moved/partial views;
  - the real black bottle under venue-like lighting;
  - unknown and visually similar unenrolled objects.

## Rollout and Rollback

1. Land measurement and reference bounds first; verify the immediate gain.
2. Land capture/recognition/encoding separation behind configuration defaults.
3. Land API/frontend steady-state reductions.
4. Enable adaptive transcription throttling and validate physical hardware.
5. Keep the old matcher unless the gated benchmark justifies a change.

Rollback is configuration-first: lower stream/recognition cadence or disable
automatic banking without deleting data. The new runtime reference selector can
be disabled to load the legacy set for comparison. The maintenance command is
never part of startup and requires explicit apply, so existing surplus data is
preserved unless the operator intentionally prunes it after reviewing a backup.

## Open Questions

- Confirm the success targets on the exact demo webcam and whether its backend
  honors buffer-size configuration; the design remains correct if it does not.
- Decide after the bounded-reference recognition corpus whether four persisted
  views per identity is sufficient or should be raised to six. Four is the
  proposed starting point based on the current benchmark.
- Decide whether the demo should use Faster Whisper `medium`, a smaller local
  model, or cloud transcription after measuring simultaneous camera behavior.
- Physical camera and microphone acceptance remains required; fixture results
  alone cannot validate driver buffering or thermal throttling.

## Approval

- [x] User approved this scope for implementation.
- Approval date/reference: 2026-10-25, “approved”.
