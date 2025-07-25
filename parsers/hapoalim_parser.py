"""
פרסר עבור דוחות בנק הפועלים
"""
import re
import pymupdf as fitz
from .base_parser import BaseBankParser
from utils.text_processing import clean_number, parse_date, normalize_text


class HapoalimParser(BaseBankParser):
    """פרסר עבור בנק הפועלים"""
    
    def __init__(self):
        super().__init__("הפועלים")
        self.date_pattern = re.compile(r"(\d{1,2}/\d{1,2}/\d{4})\s*$")
        self.balance_pattern = re.compile(r"^\s*(₪?-?[\d,]+\.\d{2})")
    
    def parse_pdf(self, pdf_content_bytes, filename="hapoalim_pdf"):
        """פרסור PDF של בנק הפועלים"""
        transactions = []
        
        try:
            doc = fitz.open(stream=pdf_content_bytes, filetype="pdf")
        except Exception as e:
            self.logger.error(f"Failed to open PDF {filename}: {e}")
            return self.create_dataframe([])
        
        for page in doc:
            lines = page.get_text("text", sort=True).splitlines()
            
            for line_text in lines:
                transaction = self._parse_line(line_text)
                if transaction:
                    transactions.append(transaction)
        
        doc.close()
        self.log_parsing_result(len(transactions), filename)
        return self.create_dataframe(transactions)
    
    def _parse_line(self, line_text):
        """פרסור שורה בודדת"""
        line_normalized = normalize_text(line_text.strip())
        if not line_normalized:
            return None
        
        # חיפוש תאריך
        date_match = self.date_pattern.search(line_text)
        if not date_match:
            return None
        
        date_str = date_match.group(1)
        parsed_date = parse_date(date_str)
        if not parsed_date:
            return None
        
        # חיפוש יתרה
        balance_match = self.balance_pattern.search(line_text)
        if not balance_match:
            return None
        
        balance_str = balance_match.group(1)
        balance = clean_number(balance_str)
        if balance is None:
            return None
        
        return {
            'Date': parsed_date,
            'Balance': balance
        }