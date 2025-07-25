"""
פרסר עבור דוחות בנק דיסקונט
"""
import re
import io
import pdfplumber
from .base_parser import BaseBankParser
from utils.text_processing import clean_number, parse_date


class DiscountParser(BaseBankParser):
    """פרסר עבור בנק דיסקונט"""
    
    def __init__(self):
        super().__init__("דיסקונט")
        self.date_pattern = re.compile(r"(\d{1,2}/\d{1,2}/\d{2,4})\s+(\d{1,2}/\d{1,2}/\d{2,4})$")
        self.balance_amount_pattern = re.compile(r"^([₪\-,\d]+\.\d{2})\s+([₪\-,\d]+\.\d{2})")
    
    def parse_pdf(self, pdf_content_bytes, filename="discount_pdf"):
        """פרסור PDF של בנק דיסקונט"""
        transactions = []
        
        try:
            with pdfplumber.open(io.BytesIO(pdf_content_bytes)) as pdf:
                for page in pdf.pages:
                    text = page.extract_text(x_tolerance=2, y_tolerance=2)
                    if not text:
                        continue
                    
                    lines = text.splitlines()
                    for line_text in lines:
                        transaction = self._parse_line(line_text)
                        if transaction:
                            transactions.append(transaction)
                            
        except Exception as e:
            self.logger.error(f"Failed to process PDF {filename}: {e}")
            return self.create_dataframe([])
        
        self.log_parsing_result(len(transactions), filename)
        return self.create_dataframe(transactions)
    
    def _parse_line(self, line_text):
        """פרסור שורה בודדת"""
        line = line_text.strip()
        if not line:
            return None
        
        # חיפוש תאריכים
        date_match = self.date_pattern.search(line)
        if not date_match:
            return None
        
        date_str = date_match.group(1)  # תאריך עסקה
        parsed_date = parse_date(date_str)
        if not parsed_date:
            return None
        
        # חיפוש יתרה וסכום
        line_before_dates = line[:date_match.start()].strip()
        balance_amount_match = self.balance_amount_pattern.search(line_before_dates)
        if not balance_amount_match:
            return None
        
        balance_str = balance_amount_match.group(1)
        balance = clean_number(balance_str)
        
        if balance is None:
            return None
        
        return {
            'Date': parsed_date,
            'Balance': balance
        }