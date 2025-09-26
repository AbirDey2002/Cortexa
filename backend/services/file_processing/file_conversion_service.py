import os
import subprocess
from datetime import datetime


def docx_to_pdf(docx_file_path):
    """
    Convert a DOCX file to PDF using LibreOffice.
    
    Args:
        docx_file_path (str): Path to the DOCX file
        
    Returns:
        str: Path to the generated PDF file
        
    Raises:
        FileNotFoundError: If the DOCX file or generated PDF is not found
        subprocess.CalledProcessError: If LibreOffice conversion fails
    """
    if not os.path.isfile(docx_file_path):
        raise FileNotFoundError(f"File not found: {docx_file_path}")
    
    directory, filename = os.path.split(docx_file_path)
    base_name, _ = os.path.splitext(filename)
    
    # Use LibreOffice to convert DOCX to PDF
    convert_command = [
        "soffice",
        "--headless",
        "--convert-to", "pdf",
        docx_file_path,
        "--outdir", directory
    ]
    
    subprocess.run(convert_command, check=True)
    
    # Check if the PDF was generated
    generated_pdf_path = os.path.join(directory, f"{base_name}.pdf")
    if not os.path.exists(generated_pdf_path):
        raise FileNotFoundError(f"Converted PDF not found: {generated_pdf_path}")
    
    # Add timestamp to the filename to avoid conflicts
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    new_pdf_filename = f"{base_name}_{timestamp}.pdf"
    new_pdf_path = os.path.join(directory, new_pdf_filename)
    os.rename(generated_pdf_path, new_pdf_path)
    
    return new_pdf_path
