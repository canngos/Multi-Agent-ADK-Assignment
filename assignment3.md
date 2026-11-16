## Overview

You will build a multi-agent system using Google's Agent Development Kit (**ADK**): [https://google.github.io/adk-docs/.](https://google.github.io/adk-docs/.) In this system, two agents collaborate iteratively to produce a digital drawing. A Painter agent draws on a digital canvas, and a Critic agent evaluates the resulting drawing visually and provides actionable feedback to the Painter agent. The agents take turns in rounds: each round consists of the Painter drawing (or refining) the canvas, followed by the Critic reviewing it and suggesting improvements. The Critic decides when to stop.

### Technical Setup

Install Google **ADK** (pinned version)

**ADK** is updated frequently, and newer versions may change its **API**. Use exactly the versions below. **ADK** requires Python 3.11 or newer.

```bash python3 --version                      # must be 3.11 or newer python3 -m venv .venv source .venv/bin/activate              # Windows: .venv\Scripts\activate pip install *google-adk==2.14.1* *litellm==1.**109**.1* python -c *import google.adk; print(google.adk.__version__)*   # should print 2.14.1 ```

Include a `requirements.txt` with these pinned versions in your submission.

Note: online tutorials and AI assistants often show code for older **ADK** versions (1.x). If an example does not work, check it against the **ADK** documentation.

Model access (Lehmus AI) Use the following model for both agents:

Model: Gemma4 **26B** MoE (supports text and image input, and tool calling) Model ID: wnofibsjlomanbprgbdp **API** base **URL** (OpenAI-compatible): [https://api.lehmus-ai.oulu.fi/v1](https://api.lehmus-ai.oulu.fi/v1) **API** key: `<LEHMUS_API_KEY — stored in .env>`

The **API** is only available from the University network or via the University's **VPN**.

Example:
```bash
curl --request **POST** --url [https://api.lehmus-ai.oulu.fi/v1/responses](https://api.lehmus-ai.oulu.fi/v1/responses) \
    --header "authorization: Bearer $LEHMUS_API_KEY" \
    --header 'content-type: application/json' \
    --data '{*model*: *wnofibsjlomanbprgbdp*, *input*: [{*role*: *user*, *content*: *What is the capital of France?*}]}'
```

**ADK** uses Google's Gemini models by default. To use the Lehmus model, connect it through **ADK**'s LiteLLM integration. The prefix `openai/` tells LiteLLM to use the OpenAI-compatible chat completions format:

```python import os from google.adk.models.lite_llm import LiteLlm

model = LiteLlm(
    model=*openai/wnofibsjlomanbprgbdp*,
    api_base=*[https://api.lehmus-ai.oulu.fi/v1*,](https://api.lehmus-ai.oulu.fi/v1*,)
    api_key=os.environ[*LEHMUS_API_KEY"],
)
```

Pass this `model` to your agents. Keep the **API** key secret: load it from a `.env` file or an environment variable, and never commit it to GitHub.

Framework rules Use Google **ADK**. Your implementation must use **ADK**'s agent classes (e.g., `LlmAgent`) and its built-in orchestration (e.g., the workflow agents `LoopAgent` / `SequentialAgent`, or a `Workflow`). Do not use raw **API** calls or other agent frameworks. The system must be fully agentic.

Note: in **ADK** 2.14.1, `LoopAgent` prints a `DeprecationWarning` (it will eventually be replaced by `Workflow`). You may still use `LoopAgent` for this assignment: the version is pinned, so it will keep working.

### Task Description

Build a system with the following two agents:

Agent 1: Painter
- The Painter agent produces or modifies a digital drawing on a canvas. It should call tools for drawing pixels on the canvas.
- The Painter creates its drawing based on a given prompt or subject (you choose the subject).
- In subsequent rounds, the Painter receives the Critic's feedback and modifies the drawing accordingly. The Painter must use the feedback to iteratively improve the artwork.
- The drawing must be an actual image file (**PNG** or similar).

Agent 2: Critic
- The Critic agent receives the image produced by the Painter and evaluates it. Since the model is multimodal, the Critic must receive the actual image (not just a textual description) in its input so it can visually assess the drawing.
- The Critic provides structured, actionable feedback: what works well, what should be changed, and specific suggestions for the next iteration.
- The Critic's feedback is passed back to the Painter for the next round.

### Round Structure

One round consists of exactly two steps: (1) the Painter produces/updates the drawing, and (2) the Critic reviews the image and provides either feedback or stops the drawing process. Your system must support running multiple rounds. Each round should produce a saved image file so that the progression of the artwork can be observed.

## Requirements 
- Both agents must be implemented as ADK agent instances (e.g., `LlmAgent`) with appropriate instructions that define their roles. 
- Use a digital canvas of size 200x200. 
- The Painter must have at least three different tools at its disposal for drawing pixels on the digital canvas. It is recommended to always draw multiple pixels on the canvas instead of a single pixel. If you draw a single pixel, there will be hardly any progress visible.
- Choose your own subject to draw and the amount of details in the subject prompt.
- The Painter and Critic must receive the actual rendered image (using the model's multimodal/vision capability). The Critic must base its feedback on the visual output.
- The system runs until the Critic stops the drawing process, or until a maximum number of 30 rounds is reached. One round is a cycle of Painter + Critic. Each round's image must be saved so that iterative progress is visible.
- The rounds must be orchestrated with ADK's built-in mechanisms (e.g., `LoopAgent` or `Workflow`). Do not orchestrate the turns with manual Python loops that bypass the framework (e.g., calling the runner or the agents repeatedly in a `for` loop).
- Include a README.md with instructions on how to run your solution, the drawing subject you chose (subject prompt), and a brief explanation of your design decisions.


## Deliverables
- Your source code must be executable and run without errors.
- Your source code (Python script), either as a link to a public GitHub repo or in a zip file, including a `requirements.txt` with the pinned versions.
- The saved images from all rounds (round_001.png, round_002.png, round_003.png, etc.).
- The full conversation log between the Painter and Critic (copy & paste text output or save to file).
- A **README**.md file explaining your approach, design choices (which design pattern and why? Which tools and why?), and how to run the code. Also include a section on observations on the painter's output images (e.g., what went well? what went wrong?)

### Grading Criteria

| **Criterion**                   | **What we look for**                                                                                                     |
| ------------------------------- | ------------------------------------------------------------------------------------------------------------------------ |
| Agent architecture              | Clear, well-defined agent instructions. Roles are distinct. A suitable design pattern is used.                           |
| Multimodal critic               | The Painter sees the canvas. The Critic receives and analyzes the actual image. Vision capability of the models is used. |
| Iterative improvement            | The drawing visibly improves across rounds. The Painter receives the feedback from the Critic.                           |
| Image generation                 | The Painter produces valid image files each round.                                                                       |
| Image generation                 | The Painter has at least three different tools at its disposal for drawing on the canvas.                                |
| ADK framework usage              | The rounds are orchestrated via ADK-native mechanisms, not manual loops bypassing the framework.                         |
| Documentation & reproducibility  | README.md is clear. Code runs as documented. Design decisions are explained.                                             |

Total: 15 points

### Hints
- The Painter and Critic should `see` the canvas. (Do not make the Painter guess where to put pixels.)
- For working with images, explore how **ADK** passes images to a model. The model accepts images as image parts (in **ADK**: `google.genai.types.Part` with `inline_data`), which LiteLLM converts to the OpenAI vision message format.
- Think carefully how you structure the instructions for each agent. The Painter should know it is drawing and the Critic should know it is evaluating visual output.
- Use **ADK**'s mechanisms to control the number of rounds and to let the Critic stop (e.g., `max_iterations` of `LoopAgent`, and **ADK**'s built-in `exit_loop` tool). Stop only when the Critic issues a stop, or at 30 rounds (whatever occurs first).
- Save intermediate images with round numbers in the filename so you can see the progression.

Good luck! If you encounter issues with model access, reach out well before the deadline!