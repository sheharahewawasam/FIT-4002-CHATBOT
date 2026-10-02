from ocr_solution import OCR
from pathlib import Path
import time

OUTPUT = Path("./testing/vlm_test_output/")

def test_vlm_page(pdf: Path):
    try:
        print("Running Single Page Test..")
        start = time.perf_counter()

        ocr = OCR()
        res = ocr.predictVLM(pdf)

        filepath = OUTPUT / pdf.with_suffix(".md").name
        OUTPUT.mkdir(parents=True, exist_ok=True)

        with open(filepath, "w", encoding="utf-8") as file:
            file.write(res)

        end = time.perf_counter()
        print(f"  Single Page Test ran for: {end-start} seconds")
    except Exception as e:
        print(f"Error: {e}")

def test_multiple_vlm(pdfs: list[Path]):
    print("Running Multi Page Test..")

    ocr = OCR()
    start = time.perf_counter()

    for pdf in pdfs:
        startpdf = time.perf_counter()
        res = ocr.predictVLM(pdf)

        filepath = OUTPUT / pdf.with_suffix(".md").name
        OUTPUT.mkdir(parents=True, exist_ok=True)

        with open(filepath, "w", encoding="utf-8") as file:
            file.write(res)

        endpdf = time.perf_counter()
        print(f"    Single Page Test ran for: {endpdf-startpdf} seconds")

    end = time.perf_counter()

    print(f"  Multiple PDF Test ran for: {end-start} seconds")


def run_vlm_tests():
    pdf1 = Path("../pdfs/atoform.pdf")
    pdf2 = Path("../pdfs/deed.pdf")
    pdf3 = Path("../pdfs/image-based-pdf-sample_rotated.pdf")
    pdf4 = Path("../pdfs/scansmpl.pdf")

    # test_vlm_page
    test_vlm_page(pdf2)

    # pdfs = [pdf2,pdf3,pdf4]

    # test_multiple_vlm(pdfs)

if __name__ == "__main__":
    run_vlm_tests()