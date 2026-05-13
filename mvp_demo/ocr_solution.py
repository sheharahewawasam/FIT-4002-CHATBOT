from pathlib import Path
from paddleocr import PPStructureV3
import pymupdf as pymu
from chonkie import FastChunker
from ollama import generate

class OCR():
    TEXT_MIN = 50

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

    def __init__(self, output: Path, gpu: bool):
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

    def output_document(self, pdf_path):
        res = ""

        self.initiate_model_v3()

        thresh_low = self.predictV3(pdf_path, 0.30)
        thresh_med = self.predictV3(pdf_path, 0.50)
        thresh_hi = self.predictV3(pdf_path, 0.70)

        chunker = FastChunker(
            chunk_size=4096,
            delimiters="\n"
        )

        low_chunks = chunker.chunk(thresh_low)
        med_chunks = chunker.chunk(thresh_med)
        hi_chunks = chunker.chunk(thresh_hi)
        
        chunk1 = self.safe_pop(low_chunks)
        chunk2 = self.safe_pop(med_chunks)
        chunk3 = self.safe_pop(hi_chunks)

        while chunk1 or chunk2 or chunk3:
            # print(chunk1)
            # print("=========================================================================================")
            # print(chunk2)
            # print("=========================================================================================")
            # print(chunk3)
            prompt = chunk1+"||"+chunk2+"||"+chunk3

            response = self.align_text(prompt)
            # print(response)

            res += response

            chunk1 = self.safe_pop(low_chunks)
            chunk2 = self.safe_pop(med_chunks)
            chunk3 = self.safe_pop(hi_chunks)
        
        return res
            
    def predictV3(self, pdf_path: Path, threshold: int):
        """
        OCR solution for predicting output of 
        """
        if not pdf_path.is_file():
            return
        
        if not 0 <= threshold <= 1:
            return
        
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

        markdown_list = []
        markdown_images = []

        for res in output:
            md_info = res.markdown
            markdown_list.append(md_info)
            markdown_images.append(md_info.get("markdown_images", {}))


        markdown_texts = self.pipelineV3.concatenate_markdown_pages(markdown_list).get("markdown_texts")

        # mkd_file_path = self.output / f"{Path(input_file).stem}.md"
        # mkd_file_path.parent.mkdir(parents=True, exist_ok=True)

        # with open(mkd_file_path, "w", encoding="utf-8") as f:
        #     f.write(markdown_texts)

        for item in markdown_images:
            if item:
                for path, image in item.items():
                    file_path = self.output / path
                    file_path.parent.mkdir(parents=True, exist_ok=True)
                    image.save(file_path)
        
        return markdown_texts
    
    def align_text(self, prompt: str) -> str:
        response = generate(
            model="qwen3",
            prompt=self.REASONING_PROMPT + prompt,
            think=False,
            stream=False
        )

        return response.response

    def determine_if_OCR(self, pdf_path: Path):
        pdf = pymu.open(pdf_path)

        total_pages = len(pdf)

        count = 0
        for page in pdf:
            text = page.get_text("text", delimiters = "\n\r")
            text = " ".join(text.split())
            if len(text) < self.TEXT_MIN:
                count += 1
        
        if count < total_pages/10:
            return False

        return True

    def safe_pop(self, lst: list):
        try:
            return lst.pop(0).text
        except IndexError:
            return ""

if __name__ == "__main__":
    ocr = OCR(Path("./ocr_output"), False)

    input_file = Path("./pdfs/Project_26.pdf")
    # print(ocr.determine_if_OCR(input_file))

    # input_file2 = Path("./pdfs/Test_Scan.pdf")
    # print(ocr.determine_if_OCR(input_file2))

    # input_file3 = Path("./pdfs/deed.pdf")
    # ocr.predictV3(input_file3)

    # prompt = (
    #     "The EU AI Act was passed in 2024 and regulates artificial intelligence systems across Europe."
    #     "||"
    #     "The EU Al Act was pased in 2024 and reguletes artifical intelligance systems acros Europ."
    #     "||"
    #     "The EU AI Act was passed in 2024 and regulates artificial intelligence systems across Europe."
    # )

    # print(ocr.align_text(prompt))

    print(ocr.output_document(input_file))