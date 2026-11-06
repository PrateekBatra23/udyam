"""Gemini adapter for the advisor's tool-calling loop (google-genai SDK).

This is the ONLY provider-specific module. It turns the neutral tool schemas in
advisor/tools.py into Gemini function declarations, runs the call/response loop and
returns the model's final text. Safety does not depend on the model: the profile is
bound server-side by `run_tool`, the catalogue it can see is already restricted to
eligible products, and agent.py re-validates whatever comes back.
"""
import json

import config

MAX_TOOL_ROUNDS = 8


def make_client():
    from google import genai
    return genai.Client(api_key=config.LLM_API_KEY)


def _declarations(tool_schemas: list[dict]):
    from google.genai import types
    decls = []
    for t in tool_schemas:
        params = t.get("input_schema") or {}
        kw = {"parameters": params} if params.get("properties") else {}   # Gemini rejects empty objects
        decls.append(types.FunctionDeclaration(name=t["name"], description=t["description"], **kw))
    return types.Tool(function_declarations=decls)


def run_chat(client, system: str, brief: dict, tool_schemas: list[dict], run_tool) -> str:
    """Run the tool loop. `run_tool(name, args) -> JSON-serialisable result`.
    Returns the final text answer."""
    from google.genai import types

    gen_config = types.GenerateContentConfig(
        system_instruction=system,
        tools=[_declarations(tool_schemas)],
        # we execute tools ourselves so the server stays in control of every call
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        temperature=0.2,
    )
    # last round: tools switched off so the model must commit to a final answer
    final_config = types.GenerateContentConfig(
        system_instruction=system, tools=[_declarations(tool_schemas)], temperature=0.2,
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        tool_config=types.ToolConfig(
            function_calling_config=types.FunctionCallingConfig(mode="NONE")))
    contents = [types.Content(role="user", parts=[types.Part(text=json.dumps(brief))])]

    for i in range(MAX_TOOL_ROUNDS):
        last = i == MAX_TOOL_ROUNDS - 1
        resp = client.models.generate_content(model=config.LLM_MODEL, contents=contents,
                                              config=final_config if last else gen_config)
        cand = resp.candidates[0]
        parts = list(cand.content.parts or [])
        calls = [p.function_call for p in parts if getattr(p, "function_call", None)]
        if not calls:
            return "".join(p.text for p in parts
                           if getattr(p, "text", None) and not getattr(p, "thought", False))
        contents.append(cand.content)            # keep the model turn as-is (incl. any signatures)
        responses = []
        for fc in calls:
            result = run_tool(fc.name, dict(fc.args or {}))
            responses.append(types.Part.from_function_response(
                name=fc.name, response={"result": json.loads(json.dumps(result, default=str))}))
        contents.append(types.Content(role="user", parts=responses))
    raise RuntimeError("tool loop did not finish within the round limit")
