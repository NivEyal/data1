"""
מחלקת בסיס לפרסרים של דוחות בנק
"""
import pandas as pd
import logging
from abc import ABC, abstractmethod


class BaseBankParser(ABC):
    """מחלקת בסיס לפרסרים של בנקים"""
    
    def __init__(self, bank_name):
        self.bank_name = bank_name
        self.logger = logging.getLogger(f"{bank_name}_parser")
    
    @abstractmethod
    def parse_pdf(self, pdf_content_bytes, filename=""):
        """פרסור קובץ PDF - יש לממש במחלקות היורשות"""
        pass
    
    def create_dataframe(self, transactions):
        """יצירת DataFrame מרשימת עסקאות"""
        if not transactions:
            return pd.DataFrame()
        
        df = pd.DataFrame(transactions)
        df['Date'] = pd.to_datetime(df['Date'])
        df['Balance'] = pd.to_numeric(df['Balance'], errors='coerce')
        
        # מיון וניקוי כפילויות
        df = df.sort_values(by='Date')
        df = df.drop_duplicates(subset='Date', keep='last')
        
        return df[['Date', 'Balance']].reset_index(drop=True)
    
    def log_parsing_result(self, transactions_count, filename):
        """רישום תוצאות הפרסור"""
        if transactions_count > 0:
            self.logger.info(f"Successfully parsed {transactions_count} transactions from {filename}")
        else:
            self.logger.warning(f"No transactions found in {filename}")