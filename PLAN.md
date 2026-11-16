# PLAN — Assignment 3: Painter & Critic (Google ADK)

Working plan for implementing `assignment3.md` phase by phase. Tick a phase off only when its **Check** passes.

## The task in short

Build a multi-agent system with Google ADK where two agents make a drawing together:

- **Painter** — draws on a 200x200 canvas by calling drawing tools (at least 3). It sees the current canvas and the Critic's last feedback, and improves the drawing each round.
- **Critic** — receives the actual image (not a description), gives structured feedback (what works, what to change, concrete next steps), and decides when to stop.

One **round** = Painter draws, then Critic reviews. The system runs until the Critic stops it or 30 rounds are reached. Every round saves an image (`round_001.png`, `round_002.png`, …).

Hard rules:

- `google-adk==2.14.1`, `litellm==1.109.1`, Python 3.11+.
- Both agents use the Lehmus model (Gemma4 26B) through ADK's `LiteLlm`. The API only works on the University network or VPN.
- Rounds are orchestrated by ADK itself (`LoopAgent` / `Workflow`). No manual `for` loop calling the agents or the runner, no raw API calls, no other agent framework.
- API key comes from `.env` and is never committed.

Deliverables: runnable source + `requirements.txt`, all round images, the full Painter/Critic conversation log, and a `README.md` (how to run, subject prompt, design decisions, observations on the output).

## Design

These are proposals; change any of them before the phase that builds it.

| Topic | Decision | Why |
|---|---|---|
| Pattern | Generator–critic loop: `LoopAgent(sub_agents=[painter, critic], max_iterations=30)` | One loop iteration is exactly one round; the cap of 30 comes for free. |
| Starting the run | One single `runner.run_async(...)` call | The loop lives inside ADK, so nothing is orchestrated by hand. |
| Stopping | Critic has ADK's built-in `exit_loop` tool | The hint in the assignment; the Critic decides, ADK ends the loop. |
| Canvas | One Pillow `Image` (200x200 RGB) in `canvas.py` | Simple, produces real PNG files. |
| Painter tools | `fill_background`, `draw_rectangle`, `draw_ellipse`, `draw_line`, `draw_polygon`, `draw_dots` | Six tools (minimum is three); each draws many pixels per call, so progress is visible. `draw_dots` draws a square dot (1–10 px) at each point, so even "pixel" details stay visible. |
| Vision | `before_model_callback` adds the current canvas as an image part (`types.Part` with `inline_data`) to every model request of both agents | Both agents really see the canvas. |
| Coordinate grid | The image sent to the model is upscaled and has a labelled grid; saved round images stay clean | Helps the Painter place shapes instead of guessing coordinates. |
| Feedback hand-off | Critic `output_key="critic_feedback"`; Painter instruction reads `{critic_feedback?}` from session state | ADK-native way to pass data between agents. |
| Feedback format | Fixed sections: *Works well / Needs change / Next steps* | "Structured, actionable feedback" is a grading point. |
| Round images | `before_agent_callback` on the Painter bumps the round counter; `after_agent_callback` saves `output/run_<timestamp>/round_NNN.png` | One image per round, guaranteed, without relying on the model. |
| Critic's view | Two images: the saved `round_NNN.png` (upscaled, clean) for judging, plus the grid view for naming positions | It judges the real output file, but can still give coordinates. |
| Instructions | Instruction *functions* (ADK instruction providers) that read round, subject, feedback and history from state | No brace-escaping issues; prompts adapt per round. |
| Fixing mistakes | Painter sees its **drawing history** (commands since the last `fill_background`, frozen at round start). To move/remove/reorder it redraws: `fill_background` + corrected replay. Small additions go on top. | Found in testing: patching over shapes with "background color" left artifacts and made drawings worse each round. |
| Robustness guards | Off-canvas coordinates are clamped to the edge; at most 30 tool calls and one `fill_background` per round; explicit `max_llm_calls` | Found in testing: off-by-one errors (x=200) and a restart loop (repeated `fill_background`) wasted whole rounds. |
| Context size | Earlier rounds are kept out of the request (`include_contents='none'`) | 30 rounds of images and tool calls would overflow the context; the agents only need the instruction, latest feedback and current image. |
| Log | `transcript.py` turns the runner's events into `output/run_<timestamp>/conversation_log.md` (+ console) | Required deliverable; Markdown with embedded round images reads like the story of the drawing. |
| Reliable stop | Critic `after_model_callback`: a written "Decision: STOP" without a tool call gets the `exit_loop` call added | Found in testing: Gemma sometimes writes STOP but forgets the tool call. The decision stays the Critic's. |
| Subject | "A small red house with a brown roof on a green hill, a yellow sun in a blue sky, and one tree." | Simple shapes fit the tools and make improvement easy to see. One constant in `config.py`. |

Target layout:

```
painter_critic/
  __init__.py
  agent.py        # root_agent = LoopAgent(painter, critic)
  canvas.py       # the 200x200 canvas, PNG export, grid view for the model
  tools.py        # drawing tools
  callbacks.py    # image injection, round saving
  prompts.py      # Painter / Critic instructions
  config.py       # subject, sizes, max rounds, model settings
main.py           # loads .env, runs the loop once, writes the log
tests/
requirements.txt
.env.example
README.md
output/           # round_001.png …, conversation_log.md
```

## Phases

### Phase 0 — Setup ✅
- [x] `.gitignore` (ignores `.env`, `.venv/`, `.idea/`), `.env.example`
- [x] This plan

### Phase 1 — Environment ✅
- [x] Create `.venv` (Python 3.13.15) and activate it
- [x] `requirements.txt` with `google-adk==2.14.1`, `litellm==1.109.1`, `pillow==13.0.0`, `python-dotenv==1.2.4`, `pytest==9.2.0`
- [x] Install (`pip check`: no broken requirements; `LiteLlm`, `LlmAgent`, `LoopAgent`, `exit_loop` import fine)

**Check:** `python -c "import google.adk; print(google.adk.__version__)"` prints `2.14.1`.

### Phase 2 — Model smoke test (needs University network / VPN) ✅
Script: `scripts/smoke_test.py` (re-run any time to check VPN/model access).
- [x] Tiny `LlmAgent` on `LiteLlm` answers a text question
- [x] Same agent describes a test image sent as an image part
- [x] Same agent calls a dummy tool
- [x] Extra: image injected by a `before_model_callback` with `include_contents='none'` is seen by the model (the exact mechanism Phase 4 uses)
- [x] Read the installed ADK 2.14.1 source. Confirmed:
  - `exit_loop(tool_context)` sets `actions.escalate = True`; `LoopAgent` stops on escalate or at `max_iterations`.
  - `before_model_callback(callback_context, llm_request)` → return `None` to continue; `after_agent_callback(callback_context)` → return `None`.
  - `include_contents='none'` still keeps the current turn's tool calls/results and the latest message from the other agent; only older rounds are dropped.
  - `output_key` writes the agent's final text into session state.
  - LiteLlm converts `inline_data` image parts to OpenAI `image_url` (base64 data URI).

**Check:** all three calls succeed. If vision or tool calling fails here, the design is adjusted before any more code is written.

### Phase 3 — Canvas and tools ✅
- [x] `config.py`: canvas size, grid settings, tool limits
- [x] `canvas.py`: create/reset canvas, export PNG bytes, grid view for the model (3x upscale, grid every 20 px, labels every 40 px on all sides), save to file
- [x] `tools.py`: the six drawing tools with input validation (bad coordinates or colors return `{"status": "error", "message": ...}`, never crash); coordinates 0–199, colors as names or hex
- [x] Unit tests (`pytest`, 37 passing): draw, then assert pixel colors; invalid input returns an error and leaves the canvas untouched; ADK builds a valid JSON schema for every tool (ADK 2.x uses `parameters_json_schema`)
- [x] Visual check: the house scene drawn by hand with the tools looks right, and grid labels match the drawn positions

**Check:** tests pass and a hand-drawn test PNG looks right.

### Phase 4 — Agents and loop ✅
- [x] `prompts.py`: Painter and Critic instructions with clearly separate roles
- [x] `callbacks.py`: image injection, round counter, tool-call guards, round saving
- [x] `agent.py`: Painter, Critic, `LoopAgent`
- [x] `main.py`: create session and runner, run once; `--max-rounds`, `--subject`, `--output-dir`

**Check:** a short run (`python main.py --max-rounds 6`) produces `round_001.png…`, and the Critic's reply clearly refers to what is in the image. ✅ Final test run: scores 7 → 9 → 10, Critic called `exit_loop` in round 3, every review matched the image.

Testing log (5 test runs, problems found → fixes):
1. Painter "moved" shapes by drawing new ones; old ones stayed (no eraser). Critic too lenient (STOP while listing problems) and wrote "STOP" without calling `exit_loop`. → stricter stop rules; "STOP alone does nothing, call exit_loop".
2. Painting over shapes with the background color left artifacts; drawings got worse. → drawing history + redraw strategy.
3. Off-by-one coordinate (x=200) triggered a restart loop of `fill_background`. → clamp coordinates; one `fill_background` per round.
4. Loop persisted: the live history shown in the prompt was cleared by the redraw itself. → history frozen at round start + reminder next to the canvas image.
5. Clean run, no errors.

### Phase 5 — Logging and stop behaviour ✅
- [x] `painter_critic/transcript.py`: every Painter/Critic message, tool call and tool result goes to the console and to `output/run_<timestamp>/conversation_log.md` (Markdown: one section per round, full tool arguments, each round's image embedded, Critic's full review, final "Result" section with the stop reason). Written line by line, so a crash still leaves a partial log plus the error.
- [x] Confirm `exit_loop` ends the run when the Critic is satisfied (`output/phase5_stop3`: Critic stopped in round 8)
- [x] Confirm the run ends at the cap when it is not (`output/phase5_cap`: `--max-rounds 2`, Critic said CONTINUE, loop ended at 2)
- [x] Unit tests for the transcript (offline, hand-built ADK events) and the Critic callback: 51 tests passing

**Check:** the log shows both agents in every round; both ways of stopping work. ✅

Problems found → fixes:
1. Painter pasted the Python-style history (`draw_ellipse(center_x=30, …)`) into JSON args as a key → history now uses the model's own format: `draw_ellipse {"center_x": 30, …}`.
2. Critic wrote "Decision: STOP" in rounds 3–5 without calling `exit_loop`, so the loop continued against its own decision → `critic_after_model` callback adds the `exit_loop` call to such a response; ADK then runs the built-in tool. Marked in the log when it happens. Verified live with a forced-STOP agent: loop ended after 1 of 3 iterations.

### Phase 6 — Full run and tuning
Diagnosis of the Phase 5 runs: (1) the simple subject was nearly finished in round 1, so later rounds changed little; (2) scores were noisy (the Critic misjudged colors); (3) the Critic named tools that don't exist (`draw_circle`, `draw_rect`).
Tuning applied:
- [x] Richer version of the same scene (chimney + smoke, window frames, path, apples, fence, flowers, clouds, sun rays) so improvement is visible over more rounds; per-round tool cap 30 → 40
- [x] Critic gets the Painter's exact tool list, a scoring guide (1–3 / 4–5 / 6–7 / 8 / 9–10), and the previous round's image (Image 3) for comparison
- [x] Painter: copy unchanged commands exactly when redrawing; one `draw_dots` call for many small things; contrast between touching objects
- [x] `scripts/make_contact_sheet.py`: all rounds of a run in one labelled `progression.png` (with the Critic's scores)
- [x] Full run 1 (`output/full_run_1`): 20 rounds, Critic stopped itself. Rounds 1→6 improved steadily (6→9/10), but rounds 7 and 13 collapsed to a nearly blank canvas (1/10).
  - Cause: Gemma sent a tool call as plain text (`<|tool_call>call:draw_polygon {...}<tool_call|>`) in the middle of a redraw; ADK took it as the final answer and ended the turn. 2 occurrences, exactly the 2 collapsed rounds.
  - Fix: `after_model_callback` on both agents turns leaked text tool calls into real function calls (marked in the log). Also: colors with extra quotes (`'"yellow"'`) are accepted.
- [x] Full run 2 (`output/full_run_2`): no more collapses (4 leaked calls recovered). Peaked at 9/10 in rounds 12–14, then from round 15 every round hit the 40-call cap and the scores slid to 2/10 by round 30 (hit the 30-round cap).
  - Cause: each redraw replayed ~19 single `draw_line` calls (fence slats, sun rays); the fence came last and was cut off by the cap. The Critic also asked to "REDRAW" for mere additions ("complete the fence"). Separately, the model kept dropping `center_y` from `draw_ellipse` calls.
  - Fix: `draw_line` → `draw_lines` (many segments in one call, like `draw_dots`); `draw_ellipse(center_x, center_y, …)` → `draw_ellipse(x, y, …)`; both agents told: additions go ADD ON TOP, REDRAW only to move/remove/resize/reorder.
- [x] Full run 3 (`output/full_run_3`): 8 rounds, Critic stopped at 9/10 (written STOP → safety net). Clear progression (fence: lines → dashes → zigzag → picket fence; flowers, apples, smoke added). ~20 calls per redraw round, 2–4 per add-on-top round; no cap hits, no collapses.
- [x] Full run 4 (`output/full_run_4`): 10 rounds, scores 6→7→8→8→9→8→9→9→9→10, Critic stopped (written STOP → safety net). Max 31 calls in a round. Round 5 added noisy specks; the Critic flagged them and round 6 removed them with a redraw. Confirms run 3's behaviour is repeatable.
- [x] Tune prompts if the drawing stalls, or the Critic stops too early or never (runs 1–3 above)
- [x] Best run chosen: **`output/full_run_4`** (backup: `full_run_3`). Copy it to the submission folder in Phase 7.

**Check:** the drawing visibly improves across rounds. ✅

Known remaining quirks (for the README's observations): `draw_lines` sometimes gets [x, y] pairs instead of [x1, y1, x2, y2] (error → corrected next call); the Critic usually writes STOP without calling `exit_loop` (handled by the callback); the Critic's scores still wobble by ±1 between rounds.

Full-run summary:

| Run | Rounds | Ended by | Scores | Main problem → fix |
|---|---|---|---|---|
| 1 | 20 | Critic | 6→9, collapses to 1 in rounds 7 and 13 | tool calls leaked as text → recovery callback |
| 2 | 30 | cap | peak 9 (r12–14), then slid to 2 | 40-call cap hit by line-by-line redraws → `draw_lines`, add-vs-redraw rule, `x`/`y` ellipse params |
| 3 | 8 | Critic | 6→9 | — |
| 4 | 10 | Critic | 6→10 | — (submission run) |

### Phase 7 — README and submission
- [x] `README.md`: how to run, subject prompt, design pattern and why, tools and why, observations (what went well, what went wrong); observations checked against the enlarged round images
- [x] Submitted run copied to `results/` (from `output/full_run_4`); `output/` (test runs) added to `.gitignore`
- [x] Fixes for running on another PC: empty `LEHMUS_API_BASE=` / `LEHMUS_MODEL_ID=` lines fall back to the defaults; clear message when `LEHMUS_API_KEY` is missing; `smoke_test.py` uses the same config
- [x] Fresh-copy test, offline part: only git-included files copied → fresh venv → `pip install -r requirements.txt` → ADK 2.14.1, 61 tests pass, missing key gives clear message
- [x] Fresh-copy test, live part: `.env` made from `.env.example` with only the key filled in → `python main.py --max-rounds 3` → 3 round images + `conversation_log.md`, exit code 0 (blank API base / model ID fell back to the defaults). Observation: in round 3 the Painter made 19 one-line `draw_lines` calls, hit the 40-call cap and left a redraw unfinished (7 → 5) → added to the README's observations.
- [x] Make sure `.env` is not in the repo or the zip (ignored by git; no key in any included file)

**Check:** someone else can run it from the README alone.

## Grading criteria and where they are covered

| Criterion | Phase |
|---|---|
| Agent architecture (clear instructions, distinct roles, suitable pattern) | 4 |
| Multimodal critic; Painter sees the canvas | 2, 4 |
| Iterative improvement; Painter receives feedback | 4, 6 |
| Valid image file each round | 4 |
| At least three drawing tools | 3 |
| ADK-native orchestration | 4, 5 |
| Documentation and reproducibility | 7 |
