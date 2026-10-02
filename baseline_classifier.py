"""
Baseline LLM classifier for ContractNLI.

What this does:
1. Loads your ContractNLI JSON file
2. Picks a handful of contract + hypothesis pairs
3. Sends each pair to an LLM, asking for Entailment / Contradiction / NotMentioned + evidence sentence
4. Compares the LLM's answer against the real answer in the dataset
5. Prints an accuracy summary

Before running:
1. Install the OpenAI package:
   pip install openai --break-system-packages

2. Get an API key from https://platform.openai.com/api-keys
   Then set it as an environment variable so the script can see it:
   export OPENAI_API_KEY="your-key-here"

3. Run the script:
   python3 baseline_classifier.py
"""

import json
import os
from openai import OpenAI

# ---- CONFIG ----
JSON_PATH = "test.json"      # path to your ContractNLI file
NUM_EXAMPLES = 50             # how many contract-hypothesis pairs to test
MODEL = "gpt-4o-mini"        # cheap + fast, good for a first test

client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))


def load_data(path):
    with open(path) as f:
        return json.load(f)


def get_span_text(doc, span_indices):
    """Given a list of span numbers, pull out the actual text for each."""
    texts = []
    for idx in span_indices:
        start, end = doc["spans"][idx]
        texts.append(doc["text"][start:end])
    return " ".join(texts)


def build_examples(data, n):
    """
    Walk through documents and hypotheses, and collect (contract_text, hypothesis,
    correct_label, correct_evidence) tuples until we have n of them.
    """
    hypotheses = data["labels"]  # dict of nda-1, nda-2, ... -> {hypothesis text}
    examples = []

    for doc in data["documents"]:
        annotations = doc["annotation_sets"][0]["annotations"]
        for hyp_id, ann in annotations.items():
            hyp_text = hypotheses[hyp_id]["hypothesis"]
            label = ann["choice"]
            evidence = get_span_text(doc, ann["spans"]) if ann["spans"] else ""

            examples.append({
                "contract_text": doc["text"],
                "hypothesis": hyp_text,
                "correct_label": label,
                "correct_evidence": evidence,
            })

            if len(examples) >= n:
                return examples
    return examples


def build_prompt(contract_text, hypothesis):
    # Full contract text, no truncation, the model can handle much longer documents than this
    return f"""You are reviewing a contract (NDA) to check whether it supports, contradicts, or does not mention a claim.

Contract:
\"\"\"{contract_text}\"\"\"

Claim: "{hypothesis}"

Answer with ONLY a JSON object in this exact format, nothing else:
{{"label": "Entailment" or "Contradiction" or "NotMentioned", "evidence": "the exact sentence from the contract that supports your answer, or empty string if NotMentioned"}}
"""


def call_model(prompt):
    response = client.chat.completions.create(
        model=MODEL,
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"},
    )
    return json.loads(response.choices[0].message.content)


def main():
    data = load_data(JSON_PATH)
    examples = build_examples(data, NUM_EXAMPLES)

    correct = 0
    results = []

    for i, ex in enumerate(examples):
        prompt = build_prompt(ex["contract_text"], ex["hypothesis"])
        model_output = call_model(prompt)

        predicted_label = model_output.get("label", "")
        is_correct = predicted_label == ex["correct_label"]
        correct += is_correct

        results.append({
            "hypothesis": ex["hypothesis"],
            "correct_label": ex["correct_label"],
            "predicted_label": predicted_label,
            "match": is_correct,
            "model_evidence": model_output.get("evidence", ""),
            "correct_evidence": ex["correct_evidence"],
        })

        print(f"[{i+1}/{len(examples)}] Correct: {ex['correct_label']:<13} | Predicted: {predicted_label:<13} | Match: {is_correct}")

    accuracy = correct / len(examples)
    print(f"\nAccuracy: {correct}/{len(examples)} = {accuracy:.0%}")

    # Save full results to a file so you can look at them later
    with open("results.json", "w") as f:
        json.dump(results, f, indent=2)
    print("Full results saved to results.json")


if __name__ == "__main__":
    main()
