import json
from pathlib import Path
from ocr_solution import OCR
import difflib

# def ocr_test(
#     self,
#     pdf_path: Path,
#     threshold: float,
#     layout_nms: bool = True,
#     table_rec: bool = True,
#     formula_rec: bool = True,
#     doc_orientation_classify: bool = True,
#     doc_unwarping: bool = True,
#     region_detection: bool = True,
#     textline_orientation: bool = False,
#     layout_unclip_ratio: float = 1.0,
#     layout_merge_bboxes_mode: str | float | None = None,
# ) -> str:
#     """
#     OCR testing function.

#     :param pdf_path: Path object of PDF to process
#     :param threshold: layout detection score threshold (0-1). Higher = stricter,
#         may drop valid regions
#     :param layout_nms: apply Non-Maximum Suppression to layout detection
#     :param table_rec: enable table structure recognition
#     :param formula_rec: enable formula/LaTeX recognition
#     :param doc_orientation_classify: detect and correct whole-page rotation
#     :param doc_unwarping: correct perspective/curvature distortion
#     :param region_detection: enable macro region grouping pass
#     :param textline_orientation: detect rotated individual text lines
#     :param layout_unclip_ratio: expand/shrink detected layout boxes (>0, default 1.0)
#     :param layout_merge_bboxes_mode: overlapping-box merge strategy for layout detection
#     :return: string with prediction result
#     """
#     ocr_model = PPStructureV3(
#         text_recognition_model_name="en_PP-OCRv4_mobile_rec",
#         device = "gpu" if self.gpu else "cpu",
#     )

#     if not pdf_path.is_file():
#         return

#     if not 0 <= threshold <= 1:
#         return

#     input_file = str(pdf_path)

#     output = ocr_model.predict(
#         input=str(input_file),
#         layout_threshold=threshold,
#         layout_nms=layout_nms,
#         layout_unclip_ratio=layout_unclip_ratio,
#         layout_merge_bboxes_mode=layout_merge_bboxes_mode,
#         use_table_recognition=table_rec,
#         use_formula_recognition=formula_rec,
#         use_doc_orientation_classify=doc_orientation_classify,
#         use_doc_unwarping=doc_unwarping,
#         use_region_detection=region_detection,
#         use_textline_orientation=textline_orientation,
#     )

#     markdown_list = []

#     for res in output:
#         markdown_list.append(res.markdown)

#     markdown_texts = self.pipelineV3.concatenate_markdown_pages(markdown_list).get("markdown_texts")

#     return markdown_texts


def precision_recall_test(actual: str, predicted: str) -> dict:
    """
    Performs a precision and recall test for an OCR prediction

    :param actual: The actual test in the image
    :param predicted: The text the OCR model predicted
    :return dict: dictionary containing precision, recall, F1 value and amount of missed and extra words
    """
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

def character_error_rate(actual: str, predicted: str) -> int:
    """
    Performs a character error rate evaluation of an OCR output using dynamically programmed edit distance calculations

    :param actual: The actual test in the image
    :param predicted: The text the OCR model predicted
    :return cer: Character error rate between the predicted and actual texts
    """
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

def run_ocr_test():
    ocr_tests = Path("./testing/ocr_test_files")

    ocr = OCR(Path("./testing"),False)
    ocr.initiate_model_v3()

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

            ocr_prediction = ocr.output_document(image_path)

            results = precision_recall_test(full_text, ocr_prediction)

            cer = character_error_rate(full_text, ocr_prediction)

            if cer > 0.1:
                print(f"File: {file.name}")
                print(f"Precision: {results['precision']:.2%}  (of what OCR returned, how much was correct)")
                print(f"Recall: {results['recall']:.2%}  (of ground truth, how much OCR found)")
                print(f"F1 Score: {results['f1']:.2%}  (balance of both)")
                print(f"Missed words: {results['missed_words']}")
                print(f"Extra words: {results['extra_words']}")
                print("-" * 40)

                print(f"Character Error Rate: {cer}")


def test_combine_text():
    """
    Tests the function combining texts from OCR and PDF Parsing

    OCR text has an extra leading sentence the PDF text is missing, and the
    PDF text has clauses inserted/appended that the OCR text is missing.
    combine_text should keep OCR-only content (delete) and pull in
    PDF-only content (insert/replace), producing the fuller combined text.
    """
    ocr_string = (
        "By this Deed, the Trustee establishes an indefinitely continuing\n\n"
        "superannuation fund to be known as THE DARTO SUPER FUND for the purpose of providing superannuation benefits to any\n\n"
        "person."
    )

    pdf_string = (
        "superannuation fund to be known as THE DARTO SUPER FUND (the\n\n"
        "'Fund') for the purpose of providing superannuation benefits to any\n\n"
        "person who is a Member of the Fund."
    )

    expected = (
        "By this Deed, the Trustee establishes an indefinitely continuing\n\n"
        "superannuation fund to be known as THE DARTO SUPER FUND (the\n\n"
        "'Fund') for the purpose of providing superannuation benefits to any\n\n"
        "person who is a Member of the Fund."
    )

    result = combine_text(ocr_string, pdf_string)

    print(result == expected)

def combine_text(ocr_string, pdf_string) -> str:
    """
    Combines two different strings into one string, removing duplicate words
    """
    s = difflib.SequenceMatcher(None, ocr_string, pdf_string)
    merged_chunks = []

    for tag, i1, i2, j1, j2 in s.get_opcodes():
        if tag == 'equal':
            merged_chunks.append(ocr_string[i1:i2])
        elif tag == 'delete':
            merged_chunks.append(ocr_string[i1:i2])
        elif tag in ('insert', 'replace'):
            merged_chunks.append(pdf_string[j1:j2])

    result = "".join(merged_chunks)

    return result


if __name__ == "__main__":
    test_combine_text()


    

