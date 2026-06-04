# from pathlib import Path
# from paddleocr import PPStructureV3
from langchain.text_splitter import MarkdownTextSplitter
import difflib

with open('./ocr_output/Test_Scan_0.5.md', 'r', encoding='utf-8') as file:
    content1 = file.read()
with open('./ocr_output/Test_Scan_0.3.md', 'r', encoding='utf-8') as file:
    content2 = file.read()
with open('./ocr_output/Test_Scan_0.7.md', 'r', encoding='utf-8') as file:
    content3 = file.read()

# print(content)

splitter = MarkdownTextSplitter(chunk_size = 1000, chunk_overlap = 0)

doc = splitter.create_documents([content1])
doc1 = splitter.create_documents([content2])
doc2 = splitter.create_documents([content3])

print(len(doc),len(doc1),len(doc2))

print(doc1[0])

# directory = Path("./pdfs")
# output_path = Path("./ocr_output")

# pipelineV3 = PPStructureV3(
#             text_recognition_model_name="en_PP-OCRv4_mobile_rec",
#             # use_region_detection=True,
#             # use_doc_unwarping=True, 
#             # use_doc_orientation_classify=True, 
#             # use_textline_orientation=True, 
#             # use_seal_recognition=True,
#             # use_formula_recognition=True,
#             # use_table_recognition=True,
#             # layout_threshold=1,
#             # layout_nms=True,

#         )

# for pdf in directory.iterdir():
#     if not pdf.is_file():
#         continue

#     input_file = pdf    
#     outputV3 = pipelineV3.predict(input=str(input_file))

#     markdown_list = []
#     markdown_images = []

#     for res in outputV3:
#         md_info = res.markdown
#         markdown_list.append(md_info)
#         markdown_images.append(md_info.get("markdown_images", {}))

#     markdown_texts = pipelineV3.concatenate_markdown_pages(markdown_list)

#     mkd_file_path = output_path / f"{Path(input_file).stem}.md"
#     mkd_file_path.parent.mkdir(parents=True, exist_ok=True)

#     with open(mkd_file_path, "w", encoding="utf-8") as f:
#         f.write(markdown_texts.get("markdown_texts"))

#     for item in markdown_images:
#         if item:
#             for path, image in item.items():
#                 file_path = output_path / path
#                 file_path.parent.mkdir(parents=True, exist_ok=True)
#                 image.save(file_path)

