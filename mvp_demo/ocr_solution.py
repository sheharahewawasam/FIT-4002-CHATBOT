from pathlib import Path
from paddleocr import PPStructureV3

class OCR():
    def __init__(self, output: Path):
        self.pipelineV3 = PPStructureV3(
            text_recognition_model_name="PP-OCRv5_server_rec",
            use_doc_unwarping=True, 
            use_doc_orientation_classify=True, 
            use_textline_orientation=True, 
            use_seal_recognition=True,
        )

        self.output = output
    
    def predictV3(self, pdf_path: Path):
        if not pdf_path.is_file():
            return
        
        input_file = str(pdf_path)

        output = self.pipelineV3.predict(input=str(input_file))

        markdown_list = []
        markdown_images = []

        for res in output:
            md_info = res.markdown
            markdown_list.append(md_info)
            markdown_images.append(md_info.get("markdown_images", {}))


        markdown_texts = self.pipelineV3.concatenate_markdown_pages(markdown_list)

        mkd_file_path = self.output / f"{Path(input_file).stem}.md"
        mkd_file_path.parent.mkdir(parents=True, exist_ok=True)

        with open(mkd_file_path, "w", encoding="utf-8") as f:
            f.write(markdown_texts.get("markdown_texts"))

        for item in markdown_images:
            if item:
                for path, image in item.items():
                    file_path = self.output / path
                    file_path.parent.mkdir(parents=True, exist_ok=True)
                    image.save(file_path)

if __name__ == "__main__":
    ocr = OCR(Path("./ocr_output"))
    input_file = Path("./pdfs/Project_26.pdf")
    input_file2 = Path("./pdfs/Test_Scan.pdf")

    ocr.predictV3(input_file)
    ocr.predictV3(input_file2)
