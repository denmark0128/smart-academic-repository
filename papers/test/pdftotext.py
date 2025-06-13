import fitz

def extract_text_from_pdf(file_path):
    doc = fitz.open(file_path)
    all_text = ""
    for page in doc:
        all_text += page.get_text()

    with open("output.txt", "w", encoding="utf-8") as f:
        f.write(all_text)

    print("✅ Text saved to output.txt")

extract_text_from_pdf(r"F:\python\thesis\paperrepo\media\papers\2025-THESIS-final_12-1-2024_final_pdf.pdf")