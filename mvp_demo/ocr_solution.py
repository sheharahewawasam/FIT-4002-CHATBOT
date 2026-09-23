from pathlib import Path
from paddleocr import PPStructureV3
import pymupdf as pymu
from chonkie import SemanticChunker
from ollama import generate, chat
import os
import io
import time
import json

# from langchain_text_splitters import MarkdownTextSplitter

class OCR():
    CONF_SCORE = 0.85
    LOW_CONF_RATIO = 0.15
    LAYOUT_CONF_SCORE = 0.85
    LAYOUT_CONF_THRESHOLD = 0.40

    REASONING_PROMPT = (
        "Respond only with the full text of the chosen chunk, exactly as it appears. "
        "Given 3 different chunks of text in the order of 1, 2, 3, determine the "
        "chunk that contains the least amount of errors. The chunks of text should be all similar in meaning, "
        "but if they aren't, choose the chunk from the majority of chunks with the same meaning. "
        "i.e if 2 out of the 3 chunks are similar, choose out of the 2 similar chunks, "
        "with the exception if the chunks are empty. "
        "If none of the chunks are similar to each other, return the 2nd chunk. "
        "If the chunks contain any images then prioritise that chunk less. "
        "Do NOT return a number or explanation — return the full text of the chosen chunk only. "
        "The chunks are split by '||'. The chunks to analyse are: "
    )


    CLEANING_PROMPT = """
        You are cleaning up OCR output. The text below may contain scanning artifacts: misrecognized characters, broken words, stray line breaks, extra whitespace, or garbled punctuation.

        Your task:

        Fix obvious OCR errors (e.g., "rn" misread as "m", "0" for "O", "1" for "l", merged or split words).
        Normalize spacing and line breaks so the text reads naturally.
        Preserve all original content, meaning, numbers, names, and structure exactly — do not summarize, paraphrase, omit, or add anything.
        If a word or phrase is too garbled to confidently reconstruct, leave it as-is rather than guessing.

        Return only the cleaned text, with no commentary.

        Text:
    """


    VLM_PROMPT = """
        Extract all content from this document image and format it strictly as JSON.
        Preserve reading order top to bottom. Transcribe exactly what is visible, no need for any calculations;

        Output ONLY: { "blocks": [...] }
        No explanation, no markdown, no commentary.
    """


    def __init__(self, output: Path = Path("./ocr_output"), gpu: bool = False):
        """
        Constructor for OCR pipeline

        :param output: Path object for output of OCR results
        :param gpu: If to use GPU for processing (must have support NVIDIA GPU)
        """
        self.output = output
        self.gpu = gpu


    def initiate_model_v3(self):
        """
        Creates the PPStructureV3 model
        """
        self.pipelineV3 = PPStructureV3(
            text_recognition_model_name="en_PP-OCRv4_mobile_rec",
            device = "gpu" if self.gpu else "cpu",
        )


    def calc_ocr_confidence(self, res) -> bool:
        data = res.json.get("res", res.json)

        ocr_res = data.get("overall_ocr_res", {})
        texts = ocr_res.get("rec_texts", [])
        scores = ocr_res.get("rec_scores", [])

        if not scores:
            return True

        weights = [max(len(t), 1) for t in texts]
        weighted_avg = sum(s * w for s, w in zip(scores, weights)) / sum(weights)
        low_conf_ratio = sum(1 for s in scores if s < 0.80) / len(scores)

        if weighted_avg < self.CONF_SCORE:
            return True

        if low_conf_ratio < self.LOW_CONF_RATIO:
            return True
        
        layout_res = data.get("layout_det_res", {}).get("boxes", [])
        layout_scores = [box.get("score", 0) for box in layout_res]

        if not layout_scores:
            return True
        
        avg_layout_score = sum(layout_scores) / len(layout_scores)

        if avg_layout_score < self.LAYOUT_CONF_SCORE:
            return True

        if min(layout_scores) < self.LAYOUT_CONF_THRESHOLD:
            return True

        return False
        

    def output_document(self, pdf_path: Path, cleanup: bool) -> str:
        """
        Output document with OCR results
        Uses semi-ensemble learning to produce the most accurate result

        :param pdf_path: Path object of PDF to process
        :param cleanup: Enable or disable LLM cleanup to reduce the time processing
        :return: text processed from the PDF
        """
        start = time.perf_counter()

        if not os.path.exists(pdf_path):
            raise FileNotFoundError("Could not find file at: {pdf_path}")

        res = ""

        self.initiate_model_v3()

        thresh_med = self.predictV3(pdf_path, 0.50)

        chunker = SemanticChunker(
            threshold=0.8,
            chunk_size=4096,
            similarity_window=5
        )

        med_chunks = chunker.chunk(thresh_med)

        chunk2 = self.safe_pop(med_chunks)

        while chunk2:
            if cleanup:
                response = self.clean_text(chunk2)
            else:
                response = chunk2
            res += response

            chunk2 = self.safe_pop(med_chunks)

        mkd_file_path = self.output / f"{pdf_path.stem}.md"
        mkd_file_path.parent.mkdir(parents=True, exist_ok=True)

        with open(mkd_file_path, "w", encoding="utf-8") as f:
            f.write(res)

        end = time.perf_counter()
        self.print_format(f"Execution time: {end-start} secs")

        return res


    def predictVLM(self, pdf_path: Path) -> str:
        """
        Uses a VLM to extract text from an entire PDF

        :param pdf_path: Path object to PDF        
        """
        doc = pymu.open(pdf_path)
        results = []

        for page_num in range(len(doc)):
            page = doc[page_num]
            page_text = self.predictVLMPage(page)
            results.append(page_text)

        doc.close()

        return "".join(results)


    def predictVLMPage(self, page: pymu.Page) -> str:
        img = page.get_pixmap(dpi=200)
        image_bytes = img.tobytes("png")

        response = chat(
            model='qwen3-vl',
            messages=[
                {
                    'role': 'user',
                    'content': self.VLM_PROMPT,
                    'images': [image_bytes]
                }
            ],
            format='json',
            options={
                'num_ctx': 16384,
                'num_predict': -1,
            }
        )

        return response['message']['content']


    def predictImage(self, image) -> str:
        """
        Uses a VLM to predict the text in a single image.

        :param image: Image to extract text from.        
        """
        img_bytes = io.BytesIO()

        image.save(img_bytes, format="PNG")
        img_bytes = img_bytes.getvalue()

        response = chat(
            model='qwen3-vl',
            messages=[
                {
                    'role': 'user',
                    'content': self.VLM_PROMPT,
                    'images': [img_bytes]
                }
            ],
            format='json',
            options={
                'num_ctx': 16384,
                'num_predict': -1,
            }
        )

        return response['message']['content']


    def predictV3(self, pdf_path: Path, threshold: int) -> str:
        """
        OCR solution for processing document with PPStructureV3
        Currently seal recognition does not work

        :param pdf_path: Path object of PDF to process
        :param threshold: strictness level when detecting layout regions\n
            higher value = stricter detection, could result in regions missing
        :return: string with prediction result
        """
        if not pdf_path.is_file():
            return

        if not 0 <= threshold <= 1:
            return

        self.print_format(f"Currently analysing {pdf_path.name}")

        input_file = str(pdf_path)

        output = self.pipelineV3.predict(
            input=str(input_file),
            layout_threshold=threshold,
            layout_nms=True,
            # use_seal_recognition=True, currently bugged
            use_table_recognition=True,
            use_formula_recognition=True,
            use_doc_orientation_classify=True,
            use_doc_unwarping=True,
            use_region_detection=True
        )

        doc = pymu.open(pdf_path)
        markdown_list = []

        mkd_file_path = self.output / f"{Path(input_file).stem}_{str(threshold)}.md"
        mkd_file_path.parent.mkdir(parents=True, exist_ok=True)

        for page_num, res in enumerate(output):
            page_json_path = self.output / f"{Path(input_file).stem}_{threshold}_page{page_num}.json"
            res.save_to_json(str(page_json_path))

            low_conf = self.calc_ocr_confidence(res)
            self.print_format(f"Page {page_num} low_confidence={low_conf}")

            vlm_success = False

            if low_conf:
                page = doc[page_num]
                vlm_res = self.predictVLMPage(page)

                try:
                    vlm_data = json.loads(vlm_res)
                    blocks = vlm_data.get("blocks", [])
                except (json.JSONDecodeError, TypeError):
                    self.print_format(f"Failed to parse VLM JSON on page {page_num}, falling back to raw text")
                    blocks = [vlm_res] if vlm_res else []

                page_text = "\n\n".join(blocks)

                if page_text:
                    markdown_list.append({
                        "markdown_texts": page_text,
                        "markdown_images": {},
                        "page_continuation_flags": (True, True),
                    })

                vlm_success = True

            if not vlm_success:
                md_info = res.markdown
                markdown_images = md_info.get("markdown_images", {})

                if markdown_images:
                    image_text = ""
                    for item in markdown_images:
                        if item:
                            for path, image in item.items():
                                file_path = self.output / path
                                file_path.parent.mkdir(parents=True, exist_ok=True)
                                image.save(file_path)
            
                                image_text += self.predictImage(image)
            
                            md_info["markdown_texts"] = md_info.get("markdown_texts", "") + image_text

                markdown_list.append(md_info)

        doc.close()

        markdown_texts = self.pipelineV3.concatenate_markdown_pages(markdown_list).get("markdown_texts")

        with open(mkd_file_path, "w", encoding="utf-8") as f:
            f.write(markdown_texts)

        return markdown_texts


    def align_text(self, prompt: str) -> str:
        """
        Query an LLM model with separate chunks to determine which chunk is best

        :param prompt: prompt containing the chunks to analyse
        :return: chunk chosen by LLM with the best meaning
        """
        response = generate(
            model="qwen3",
            prompt=self.REASONING_PROMPT + prompt,
            think=False,
            stream=False
        )

        return response.response


    def clean_text(self, prompt: str) -> str:
        """
        Query an LLM model with a prompt that cleans the returned chunk

        :param prompt: prompt containing the OCR text to clean
        :return: cleaned OCR output
        """
        response = generate(
            model="qwen3.8",
            prompt=self.CLEANING_PROMPT + prompt,
            think=False,
            stream=False
        )

        return response.response


    def safe_pop(self, lst: list) -> str:
        """
        Safely pops the first item from a chunk list or returns an empty string if none

        :param lst: list of chunks generated by Chonkie
        :return: text of first chunk or empty string
        """
        try:
            return lst.pop(0).text
        except IndexError:
            return ""


    def ocr_test(
        self,
        pdf_path: Path,
        threshold: float,
        layout_nms: bool = True,
        table_rec: bool = True,
        formula_rec: bool = True,
        doc_orientation_classify: bool = True,
        doc_unwarping: bool = True,
        region_detection: bool = True,
        textline_orientation: bool = False,
        layout_unclip_ratio: float = 1.0,
        layout_merge_bboxes_mode: str | float | None = None,
    ) -> str:
        """
        OCR testing function.

        :param pdf_path: Path object of PDF to process
        :param threshold: layout detection score threshold (0-1). Higher = stricter,
            may drop valid regions
        :param layout_nms: apply Non-Maximum Suppression to layout detection
        :param table_rec: enable table structure recognition
        :param formula_rec: enable formula/LaTeX recognition
        :param doc_orientation_classify: detect and correct whole-page rotation
        :param doc_unwarping: correct perspective/curvature distortion
        :param region_detection: enable macro region grouping pass
        :param textline_orientation: detect rotated individual text lines
        :param layout_unclip_ratio: expand/shrink detected layout boxes (>0, default 1.0)
        :param layout_merge_bboxes_mode: overlapping-box merge strategy for layout detection
        :return: string with prediction result
        """
        ocr_model = PPStructureV3(
            text_recognition_model_name="en_PP-OCRv4_mobile_rec",
            device = "gpu" if self.gpu else "cpu",
        )

        if not pdf_path.is_file():
            return

        if not 0 <= threshold <= 1:
            return

        input_file = str(pdf_path)

        output = ocr_model.predict(
            input=str(input_file),
            layout_threshold=threshold,
            layout_nms=layout_nms,
            layout_unclip_ratio=layout_unclip_ratio,
            layout_merge_bboxes_mode=layout_merge_bboxes_mode,
            use_table_recognition=table_rec,
            use_formula_recognition=formula_rec,
            use_doc_orientation_classify=doc_orientation_classify,
            use_doc_unwarping=doc_unwarping,
            use_region_detection=region_detection,
            use_textline_orientation=textline_orientation,
        )

        markdown_list = []

        for res in output:
            markdown_list.append(res.markdown)

        markdown_texts = self.pipelineV3.concatenate_markdown_pages(markdown_list).get("markdown_texts")

        return markdown_texts


    def print_format(self, text: str):
        print("------------------------------------------------------")
        print(text)
        print("------------------------------------------------------")


if __name__ == "__main__":
    ocr = OCR(Path("./ocr_output"), False)

    # input_file = Path("./pdfs/Proposal Document.pdf")

    # input_file = Path("./pdfs/scansmpl.pdf")

    # input_file = Path("./pdfs/image-based-pdf-sample_rotated.pdf")

    input_file = Path("./pdfs/atoform.pdf")

    # input_file = Path("./pdfs/Investment Strategy.pdf")

    # input_file = Path("./pdfs/Signed_2023_Annual_Return_NOT_AUDITED[1]_unlocked.pdf")


    ocr.output_document(input_file, False)
    # ocr.predictVLM(input_file)

