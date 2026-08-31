import json
from pathlib import Path
from ocr_solution import OCR
import Levenshtein

ocr_tests = Path("./testing/ocr_test_files")

ocr = OCR(Path("./testing"),False)
ocr.initiate_model_v3()

def precision_recall_test(actual: str, predicted: str) -> dict:
    actual_words = set(actual.lower().split())
    predicted_words = set(predicted.lower().split())

    true_positives = actual_words & predicted_words   # words in both
    false_negatives = actual_words - predicted_words  # words in ref but not OCR (missed)
    false_positives = predicted_words - actual_words  # words in OCR but not ref (hallucinated)

    precision = len(true_positives) / len(predicted_words) if predicted_words else 0
    recall    = len(true_positives) / len(actual_words) if actual_words else 0
    f1        = (2 * precision * recall) / (precision + recall) if (precision + recall) else 0

    return {
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "missed_words": false_negatives,
        "extra_words": false_positives
    }

def character_error_rate(actual: str, predicted: str):
    ref, hyp = list(actual), list(predicted)
    n, m = len(ref), len(hyp)

    dp = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(n + 1):
        dp[i][0] = i
    for j in range(m + 1):
        dp[0][j] = j

    for i in range(1, n + 1):
        for j in range(1, m + 1):
            if ref[i - 1] == hyp[j - 1]:
                dp[i][j] = dp[i - 1][j - 1]
            else:
                dp[i][j] = 1 + min(
                    dp[i - 1][j],     # deletion
                    dp[i][j - 1],     # insertion
                    dp[i - 1][j - 1]  # substitution
                )

    edit_distance = dp[n][m]
    return edit_distance / n if n > 0 else 0.0

for file in ocr_tests.iterdir():
    if file.is_file() and file.suffix == '.json':
        with open(file, encoding='utf-8-sig') as f:
            data = json.load(f)

        # Get the PNG with the same name
        image_path = Path(file.with_suffix('.png'))
        if not image_path.exists():
            print(f"No image found for {file.name}, skipping...")
            continue

        words = []
        for field in data['form']:
            for word in field['words']:
                if word['text'].strip():
                    words.append(word['text'])

        full_text = " ".join(field['text'] for field in data['form'] if field['text'].strip())

        ocr_prediction = ocr.ocr_test(image_path,0.50)

        print(ocr_prediction)
        print(full_text)

        results = precision_recall_test(full_text, ocr_prediction)

        print(f"File: {file.name}")
        print(f"Precision: {results['precision']:.2%}  (of what OCR returned, how much was correct)")
        print(f"Recall: {results['recall']:.2%}  (of ground truth, how much OCR found)")
        print(f"F1 Score: {results['f1']:.2%}  (balance of both)")
        print(f"Missed words: {results['missed_words']}")
        print(f"Extra words: {results['extra_words']}")
        print("-" * 40)

        cer = character_error_rate(full_text, ocr_prediction)

        print(f"Character Error Rate: {cer}")




    

