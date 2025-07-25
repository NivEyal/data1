"""
פרסר דוחות בנק
"""
import pandas as pd
import pymupdf as fitz
import pdfplumber
import io
import re
import logging
from utils.helpers import clean_number, parse_date, normalize_text


class BankParser:
    """מחלקה לפרסור דוחות בנק"""
    
    def __init__(self, bank_type):
        self.bank_type = bank_type
        self.logger = logging.getLogger(f"{bank_type}_parser")
    
    def parse_pdf(self, pdf_bytes, filename=""):
        """פרסור PDF לפי סוג הבנק"""
        try:
            if self.bank_type == "הפועלים":
                return self._parse_hapoalim(pdf_bytes, filename)
            elif self.bank_type == "לאומי":
                return self._parse_leumi(pdf_bytes, filename)
            elif self.bank_type == "דיסקונט":
                return self._parse_discount(pdf_bytes, filename)
            else:
                self.logger.error(f"Unsupported bank type: {self.bank_type}")
                return pd.DataFrame()
        except Exception as e:
            self.logger.error(f"Error parsing {self.bank_type} PDF: {e}")
            return pd.DataFrame()
    
    def _parse_hapoalim(self, pdf_bytes, filename):
        """פרסור דוח הפועלים"""
        transactions = []
        
        try:
            doc = fitz.open(stream=pdf_bytes, filetype="pdf")
            date_pattern = re.compile(r"(\d{1,2}/\d{1,2}/\d{4})\s*$")
            balance_pattern = re.compile(r"^\s*(₪?-?[\d,]+\.\d{2})")
            
            for page in doc:
                lines = page.get_text("text", sort=True).splitlines()
                
                for line in lines:
                    line_normalized = normalize_text(line)
                    if not line_normalized or len(line_normalized) < 10:
                        continue
                    
                    date_match = date_pattern.search(line)
                    if not date_match:
                        continue
                    
                    date_str = date_match.group(1)
                    parsed_date = parse_date(date_str)
                    if not parsed_date:
                        continue
                    
                    balance_match = balance_pattern.search(line)
                    if not balance_match:
                        continue
                    
                    balance_str = balance_match.group(1)
                    balance = clean_number(balance_str)
                    if balance is None:
                        continue
                    
                    # סינון שורות כותרת/סיכום
                    lower_line = line_normalized.lower()
                    skip_phrases = ["יתרה לסוף יום", "עובר ושב", "תנועות בחשבון", 
                                  "עמוד", "סך הכל", "הודעה זו כוללת"]
                    if any(phrase in lower_line for phrase in skip_phrases):
                        continue
                    
                    transactions.append({
                        'Date': parsed_date,
                        'Balance': balance
                    })
            
            doc.close()
            
        except Exception as e:
            self.logger.error(f"Error processing Hapoalim PDF: {e}")
            return pd.DataFrame()
        
        return self._create_dataframe(transactions, filename)
    
    def _parse_leumi(self, pdf_bytes, filename):
        """פרסור דוח לאומי"""
        transactions = []
        
        try:
            with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
                pattern = re.compile(
                    r"^([\-\u200b\d,\.]+)\s+"           # יתרה
                    r"(\d{1,3}(?:,\d{3})*\.\d{2})?\s*" # סכום
                    r"(\S+)\s+"                        # אסמכתא
                    r"(.*?)\s+"                        # תיאור
                    r"(\d{1,2}/\d{1,2}/\d{2,4})\s+"     # תאריך
                    r"(\d{1,2}/\d{1,2}/\d{2,4})$"       # תאריך ערך
                )
                
                previous_balance = None
                
                for page in pdf.pages:
                    text = page.extract_text(x_tolerance=2, y_tolerance=2, layout=True)
                    if not text:
                        continue
                    
                    lines = text.splitlines()
                    for line in lines:
                        line = normalize_text(line.strip())
                        if not line:
                            continue
                        
                        match = pattern.match(line)
                        if not match:
                            continue
                        
                        balance_str, amount_str, reference, description, date_str, value_date_str = match.groups()
                        
                        current_balance = clean_number(balance_str)
                        parsed_date = parse_date(date_str)
                        
                        if parsed_date is None or current_balance is None:
                            continue
                        
                        # בדיקה שיש סכום עסקה
                        amount = clean_number(amount_str) if amount_str else None
                        if amount is None or amount == 0:
                            continue
                        
                        transactions.append({
                            'Date': parsed_date,
                            'Balance': current_balance
                        })
                        
                        previous_balance = current_balance
                        
        except Exception as e:
            self.logger.error(f"Error processing Leumi PDF: {e}")
            return pd.DataFrame()
        
        return self._create_dataframe(transactions, filename)
    
    def _parse_discount(self, pdf_bytes, filename):
        """פרסור דוח דיסקונט"""
        transactions = []
        
        try:
            with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
                date_pattern = re.compile(r"(\d{1,2}/\d{1,2}/\d{2,4})\s+(\d{1,2}/\d{1,2}/\d{2,4})$")
                balance_pattern = re.compile(r"^([₪\-,\d]+\.\d{2})\s+([₪\-,\d]+\.\d{2})")
                
                for page in pdf.pages:
                    text = page.extract_text(x_tolerance=2, y_tolerance=2)
                    if not text:
                        continue
                    
                    lines = text.splitlines()
                    for line in lines:
                        line = line.strip()
                        if not line:
                            continue
                        
                        # חיפוש תאריכים
                        date_match = date_pattern.search(line)
                        if not date_match:
                            continue
                        
                        date_str = date_match.group(1)
                        parsed_date = parse_date(date_str)
                        if not parsed_date:
                            continue
                        
                        # חיפוש יתרה
                        line_before_dates = line[:date_match.start()].strip()
                        balance_match = balance_pattern.search(line_before_dates)
                        if not balance_match:
                            continue
                        
                        balance_str = balance_match.group(1)
                        balance = clean_number(balance_str)
                        
                        if balance is None:
                            continue
                        
                        transactions.append({
                            'Date': parsed_date,
                            'Balance': balance
                        })
                        
        except Exception as e:
            self.logger.error(f"Error processing Discount PDF: {e}")
            return pd.DataFrame()
        
        return self._create_dataframe(transactions, filename)
    
    def _create_dataframe(self, transactions, filename):
        """יצירת DataFrame מעובד"""
        if not transactions:
            self.logger.warning(f"No transactions found in {filename}")
            return pd.DataFrame()
        
        df = pd.DataFrame(transactions)
        df['Date'] = pd.to_datetime(df['Date'])
        df['Balance'] = pd.to_numeric(df['Balance'], errors='coerce')
        df = df.dropna(subset=['Date', 'Balance'])
        
        # מיון וניקוי כפילויות
        df = df.sort_values(by='Date').groupby('Date')['Balance'].last().reset_index()
        df = df.sort_values(by='Date').reset_index(drop=True)
        
        self.logger.info(f"Successfully parsed {len(df)} transactions from {filename}")
        return df[['Date', 'Balance']]