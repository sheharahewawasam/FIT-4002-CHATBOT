import json
import re

from ingest import extract_text_with_tables


PDF_PATH = "../pdfs/SIS Act -1.pdf"
DATASET_PATH = "chunk_evaluation_dataset.json"


def normalize(text):
    return re.sub(r"\s+", " ", text).strip()


with open(DATASET_PATH, "r", encoding="utf-8") as file:
    dataset = json.load(file)

document_text = normalize(extract_text_with_tables(PDF_PATH))

all_valid = True

for item in dataset:
    for excerpt_number, excerpt in enumerate(
        item["relevant_excerpts"], start=1
    ):
        found = normalize(excerpt) in document_text

        print(
            f"{item['question_id']} excerpt "
            f"{excerpt_number}: {'FOUND' if found else 'NOT FOUND'}"
        )

        if not found:
            all_valid = False

if all_valid:
    print("\nAll excerpts were found.")
else:
    print(
        "\nSome excerpts were not found. Replace them with the "
        "exact extracted text before calculating metrics."
    )