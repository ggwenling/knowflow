"""Render and recognize one page inside the isolated parser."""
import os
import subprocess

from .parsing import ParseFailure


def recognize_page(data: bytes, page: int) -> str:
    number = str(page)
    try:
        image = subprocess.run(
            ["pdftoppm", "-f", number, "-l", number, "-singlefile",
             "-scale-to", "2000", "-gray", "-"],
            input=data, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            check=True, timeout=5,
        ).stdout
        if not image or len(image) > 4_000_128:
            raise ParseFailure("PDF_OCR_FAILED")
        text = subprocess.run(
            ["tesseract", "stdin", "stdout", "-l", "chi_sim+chi_tra+eng"],
            input=image, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            env={**os.environ, "OMP_THREAD_LIMIT": "1"}, check=True, timeout=8,
        ).stdout
        return text.decode("utf-8")
    except FileNotFoundError:
        raise ParseFailure("PDF_OCR_UNAVAILABLE") from None
    except (subprocess.SubprocessError, UnicodeError, OSError):
        raise ParseFailure("PDF_OCR_FAILED") from None
