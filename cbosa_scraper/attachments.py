# cbosa_scraper/attachments.py
import os
import logging
from typing import List, Dict, Tuple, Optional

from .docx_newsletter import DocxNewsletterGenerator
from file_helpers import build_judgments_zip  # już masz

Attachment = Tuple[str, bytes, str]  # (filename, content, mime)

class EmailAttachmentBuilder:
    def __init__(self, output_dir: str = "./out"):
        self.output_dir = output_dir
        os.makedirs(self.output_dir, exist_ok=True)
        self.docx_gen = DocxNewsletterGenerator(output_dir=output_dir)
        self._temp_files = []
        self.logger = logging.getLogger(__name__)

    def _read_bytes(self, path: str) -> bytes:
        with open(path, "rb") as f:
            return f.read()

    def build_docx(self, analyses: List[Dict], search_params: Dict, stats: Dict) -> Attachment:
        docx_path = self.docx_gen.create(analyses=analyses, search_params=search_params, stats=stats)
        self.track_file(docx_path)
        return (os.path.basename(docx_path), self._read_bytes(docx_path),
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document")

    def build_stats_txt(self, stats: Dict) -> Attachment:
        # prosty, „płaski” raport .txt
        lines = [
            "CBOSA – statystyki analizy",
            f"Przeanalizowano: {stats.get('successful_analyses', 0)} z {stats.get('total_analyses', 0)}",
            f"Współczynnik sukcesu: {stats.get('success_rate', 0):.1f}%",
            f"Tokeny użyte: {stats.get('total_tokens_used', 0)}",
            f"Szacowany koszt (USD): {stats.get('estimated_cost_usd', 0):.4f}",
            f"Szacowany koszt (PLN): {stats.get('estimated_cost_pln', 0):.2f}",
            f"Liczba orzeczeń bez uzasadnienia: {stats.get('no_uzasadnienie_count', 0)}",
            ""
        ]
        content = ("\n".join(lines)).encode("utf-8")
        return ("CBOSA_AI_Stats.txt", content, "text/plain; charset=utf-8")

    def build_zip(self, successful_downloads: List[Dict]) -> Optional[Attachment]:
        zip_bytes, zip_name = build_judgments_zip(successful_downloads)
        self.track_file(zip_name)
        if not zip_bytes:
            return None
        return (zip_name, zip_bytes, "application/zip")

    def build_all(self, analyses: List[Dict], search_params: Dict, stats: Dict, successful_downloads: List[Dict]) -> List[Attachment]:
        attachments: List[Attachment] = []
        # DOCX
        attachments.append(self.build_docx(analyses, search_params, stats))
        # TXT
        attachments.append(self.build_stats_txt(stats))
        # ZIP (opcjonalnie)
        zip_att = self.build_zip(successful_downloads)
        if zip_att:
            attachments.append(zip_att)
        return attachments
    
    def track_file(self, path: str):
        """Dodaj ścieżkę do listy do późniejszego usunięcia"""
        self._temp_files.append(path)

    def cleanup(self):
        """Usuń wszystkie tymczasowe pliki"""
        for path in self._temp_files:
            try:
                if os.path.exists(path):
                    os.remove(path)
                    self.logger.info(f"🧹 Usunięto plik tymczasowy: {path}")
            except Exception as e:
                self.logger.warning(f"⚠️ Nie udało się usunąć {path}: {e}")
        self._temp_files = []
