"""
Step 3: automatically feed Narsese lines into ONA and read back the answer.

IMPORTANT: set ONA_PATH below to the actual path to your ONA folder,
e.g. "/Users/yourname/Downloads/OpenNARS-for-Applications"

Run standalone to sanity-check it against the robin/animal example:
    python3 run_ona.py
"""

import subprocess
import re
import os

# vvv CHANGE THIS to your actual ONA folder path vvv
ONA_PATH = os.path.expanduser("~/Downloads/OpenNARS-for-Applications")

INFERENCE_CYCLES = 20  # matches the paper's fixed cycle count before querying


def run_narsese(lines):
    """
    Feed a list of Narsese lines (statements ending in '.' and one query
    ending in '?') into ONA, run inference, and return the parsed result:
    {"frequency": float or None, "confidence": float or None, "raw_output": str}
    frequency=None means ONA gave no answer at all (maps to Uncertain).
    """
    nar_binary = os.path.join(ONA_PATH, "NAR")
    if not os.path.exists(nar_binary):
        raise FileNotFoundError(
            f"Couldn't find the ONA binary at {nar_binary}. "
            f"Update ONA_PATH at the top of this file."
        )

    # Build the full input: statements, then run some cycles, then the query
    script_lines = list(lines)
    input_text = "\n".join(script_lines) + "\n"

    result = subprocess.run(
        [nar_binary, "shell"],
        input=input_text,
        capture_output=True,
        text=True,
        timeout=30,
    )
    output = result.stdout

    # Look for the LAST "Answer:" line -- that's the response to our query
    answer_lines = [l for l in output.splitlines() if l.strip().startswith("Answer:")]
    if not answer_lines:
        return {"frequency": None, "confidence": None, "raw_output": output}

    last_answer = answer_lines[-1]
    match = re.search(
        r"frequency=([\d.]+),\s*confidence=([\d.]+)", last_answer
    )
    if not match:
        return {"frequency": None, "confidence": None, "raw_output": output}

    freq, conf = float(match.group(1)), float(match.group(2))
    return {"frequency": freq, "confidence": conf, "raw_output": output}


def frequency_to_label(frequency):
    """Apply the paper's exact thresholds."""
    if frequency is None:
        return "Uncertain"  # no answer at all
    if frequency >= 0.50:
        return "True"
    if frequency <= 0.05:
        return "False"
    return "Uncertain"


if __name__ == "__main__":
    # sanity check with the robin/animal example
    test_lines = [
        "<bird --> animal>.",
        "<robin --> bird>.",
        "<robin --> animal>?",
    ]
    result = run_narsese(test_lines)
    print("Frequency:", result["frequency"])
    print("Confidence:", result["confidence"])
    print("Label:", frequency_to_label(result["frequency"]))
