import os
import logging
from typing import Optional

logger = logging.getLogger("Aetheris.Agents.PromptManager")

def clean_xml_prompt(content: str) -> str:
    """
    Strips leading and trailing markdown code block fences (e.g. ```xml and ```)
    to ensure the model receives clean XML.
    """
    content = content.strip()
    if content.startswith("```xml"):
        content = content[6:].strip()
    elif content.startswith("```"):
        content = content[3:].strip()
    if content.endswith("```"):
        content = content[:-3].strip()
    return content.strip()

def load_prompt_file(filepath: str) -> str:
    """
    Loads and cleans an XML prompt file from the filesystem.
    """
    try:
        if os.path.exists(filepath):
            with open(filepath, "r", encoding="utf-8") as f:
                return clean_xml_prompt(f.read())
        else:
            logger.warning(f"Prompt file not found at path: {filepath}")
    except Exception as e:
        logger.error(f"Failed to load prompt file {filepath}: {e}")
    return ""

def assemble_agent_prompt(
    role: str,
    pipeline_stage: str,
    objective: str,
    iteration: int,
    execution_mode: str,
    system_prompt_filename: str,
) -> str:
    """
    Assembles the 5-layer Aetheris prompt layout with dynamic role injection:
    
    1. <ROLE> block
    2. 00_agent_runtime.xml
    3. 01_prompt_loader.xml
    4. 03_context_manager.xml
    5. 02_response_contract.xml
    6. Agent-specific prompt (e.g., 05_logician.xml)
    """
    # 1. Build the <ROLE> block
    role_block = f"""<ROLE>

Current Role

{role}

Current Pipeline Stage

{pipeline_stage}

Current Objective

{objective}

Current Iteration

{iteration}

Execution Mode

{execution_mode}

</ROLE>"""

    # 2. Locate paths
    # Assuming agents/prompt_manager.py is in c:/Users/amand/Downloads/AETHERIS/agents/
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    prompts_dir = os.path.join(base_dir, "prompts")
    
    # 3. Load all runtime XMLs dynamically, sorted by prefix
    runtime_prompts = []
    runtime_dir = os.path.join(prompts_dir, "runtime")
    if os.path.exists(runtime_dir):
        xml_files = sorted([f for f in os.listdir(runtime_dir) if f.endswith(".xml")])
        for filename in xml_files:
            content = load_prompt_file(os.path.join(runtime_dir, filename))
            if content.strip():
                runtime_prompts.append(content)
    
    # 4. Load agent-specific XML prompt
    agent_prompt = load_prompt_file(os.path.join(prompts_dir, "system", system_prompt_filename))
    
    # Fallback to hardcoded persona constants if XML file is missing or empty
    if not agent_prompt:
        logger.warning(f"Could not load XML prompt {system_prompt_filename}, using fallback persona constants.")
        from agents.personas import PERSONA_REGISTRY
        # map name from filename: 05_logician.xml -> logician
        base_name = os.path.basename(system_prompt_filename)
        # remove prefix digits and .xml: e.g. "05_logician.xml" -> "logician"
        parts = base_name.replace(".xml", "").split("_")
        persona_key = parts[-1].lower() if parts else ""
        agent_prompt = PERSONA_REGISTRY.get(persona_key, "")

    # Combine all parts with double newlines
    parts = [role_block] + runtime_prompts + [agent_prompt]
    
    non_empty_parts = [p for p in parts if p.strip()]
    return "\n\n".join(non_empty_parts)
