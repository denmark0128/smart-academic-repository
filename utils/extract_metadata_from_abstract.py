#extract_metadata_from_abstract.py

from bs4 import BeautifulSoup

def extract_metadata_from_abstract(html_path):
    """
    Extract metadata from the abstract page in merged CHM HTML.
    Returns a dictionary with:
    title, authors, program, college, year (int), abstract
    """
    with open(html_path, "r", encoding="utf-8") as f:
        soup = BeautifulSoup(f, "html.parser")

    metadata = {
        "title": None,
        "authors": [],
        "program": None,
        "college": None,
        "year": None,
        "abstract": None
    }

    abstract_div = soup.find("div", class_="cont")
    if not abstract_div:
        return metadata

    text = abstract_div.get_text(separator="\n").split("\n")
    text = [line.strip() for line in text if line.strip()]

    for i, line in enumerate(text):
        if line.startswith("Title"):
            title = []
            j = i + 1
            while j < len(text) and not text[j].startswith(("Researchers", "Year", "Project Description")):
                title_line = text[j].lstrip(":").strip()
                if title_line:
                    title.append(title_line)
                j += 1
            metadata['title'] = " ".join(title)

        elif line.startswith("Researchers"):
            authors = []
            j = i + 1
            while j < len(text) and not text[j].startswith(("Degree", "Year", "Project Description")):
                authors.append(text[j].strip())
                j += 1
            metadata['authors'] = authors

        elif line.startswith("Degree"):
            program_lines = []
            j = i + 1
            while j < len(text) and not text[j].startswith(("Year", "Project Description")):
                program_line = text[j].lstrip(":").strip()
                if program_line:
                    program_lines.append(program_line)
                j += 1
            program_str = " ".join(program_lines)
            metadata['program'] = program_str

            # Set college based on program
            if "Computer Science" in program_str or "Com Sci" in program_str.lower():
                metadata['college'] = "College of Computer Studies"
            else:
                metadata['college'] = None  # fallback

        elif line.startswith("Year"):
            year_lines = []
            j = i + 1
            while j < len(text) and not text[j].startswith("Project Description"):
                year_line = text[j].lstrip(":").strip()
                if year_line:
                    year_lines.append(year_line)
                j += 1
            if year_lines and year_lines[0].isdigit():
                metadata['year'] = int(year_lines[0])

        elif line.startswith("Project Description"):
            p_tag = abstract_div.find_next_sibling("p")
            if p_tag:
                metadata['abstract'] = p_tag.get_text(strip=True)

    return metadata

