"""
פרסר עבור דוחות בנק לאומי
"""
import re
import io
import pdfplumber
from .base_parser import BaseBankParser
from utils.text_processing import clean_number, parse_date, normalize_text


class LeumiParser(BaseBankParser):
    """פרסר עבור בנק לאומי"""
    
    def __init__(self):
        super().__init__("לאומי")
        self.transaction_pattern = re.compile(
            r"^([\-\u200b\d,\.]+)\s+"           # יתרה
            r"(\d{1,3}(?:,\d{3})*\.\d{2})?\s*" # סכום (אופציונלי)
            r"(\S+)\s+"                        # אסמכתא
            r"(.*?)\s+"                        # תיאור
            r"(\d{1,2}/\d{1,2}/\d{2,4})\s+"     # תאריך
            r"(\d{1,2}/\d{1,2}/\d{2,4})$"       # תאריך ערך
        )
    
    def parse_pdf(self, pdf_content_bytes, filename="leumi_pdf"):
        """פרסור PDF של בנק לאומי"""
        transactions = []
        
        try:
            with pdfplumber.open(io.BytesIO(pdf_content_bytes)) as pdf:
                previous_balance = None
                
                for page in pdf.pages:
                    text = page.extract_text(x_tolerance=2, y_tolerance=2, layout=True)
                    if not text:
                        continue
                    
                    lines = text.splitlines()
                    for line_text in lines:
                        transaction = self._parse_line(line_text.strip(), previous_balance)
                        if transaction:
                            transactions.append(transaction)
                            previous_balance = transaction['Balance']
                            
        except Exception as e:
            self.logger.error(f"Failed to process PDF {filename}: {e}")
            return self.create_dataframe([])
        
        self.log_parsing_result(len(transactions), filename)
        return self.create_dataframe(transactions)
    
    def _parse_line(self, line_text, previous_balance):
        """פרסור שורה בודדת"""
        if not line_text:
            return None
        
        match = self.transaction_pattern.match(line_text)
        if not match:
            return None
        
        balance_str, amount_str, reference, description, date_str, value_date_str = match.groups()
        
        # פרסור יתרה ותאריך
        current_balance = clean_number(balance_str)
        parsed_date = parse_date(date_str)
        
        if parsed_date is None or current_balance is None:
            return None
        
        # בדיקה אם זו עסקה אמיתית (יש סכום)
        amount = clean_number(amount_str) if amount_str else None
        if amount is None or amount == 0:
            return None
        
        return {
            'Date': parsed_date,
            'Balance': current_balance,
            'Description': normalize_text(description),
            'Amount': amount
        }