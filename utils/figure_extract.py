# utils/figure_extract.py
import fitz  # PyMuPDF
import os

def extract_images_from_pdf(pdf_path, output_folder):
    doc = fitz.open(pdf_path)
    
    if not os.path.exists(output_folder):
        os.makedirs(output_folder)

    image_count = 0
    saved_files = []

    for page_index in range(len(doc)):
        page = doc[page_index]
        images = page.get_images(full=True)
        
        for img_index, img in enumerate(images, start=1):
            xref = img[0]
            base_image = doc.extract_image(xref)
            image_bytes = base_image["image"]
            image_ext = base_image["ext"]

            image_filename = f"page{page_index+1}_img{img_index}.{image_ext}"
            image_path = os.path.join(output_folder, image_filename)
            with open(image_path, "wb") as f:
                f.write(image_bytes)

            saved_files.append(image_path)
            image_count += 1

    print(f"Extracted {image_count} images to '{output_folder}'")
    return saved_files 

