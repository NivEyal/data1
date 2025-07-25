"""
אפליקציית מומחה כלכלת המשפחה - גרסה משופרת
"""
import streamlit as st
import pandas as pd
import logging
from config import PAGE_TITLE, PAGE_ICON, SUPPORTED_BANKS, DEFAULT_MONTHLY_INCOME
from parsers.hapoalim_parser import HapoalimParser
from parsers.leumi_parser import LeumiParser
from parsers.discount_parser import DiscountParser
from parsers.credit_parser import CreditReportParser
from financial_analyzer import FinancialAnalyzer
from ui_components import UIComponents
from chatbot import FinancialChatbot

# הגדרת לוגינג
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# הגדרת עמוד
st.set_page_config(layout="wide", page_title=PAGE_TITLE, page_icon=PAGE_ICON)

# אתחול משתני session state
def initialize_session_state():
    """אתחול משתני session state"""
    defaults = {
        'df_bank': pd.DataFrame(),
        'df_credit': pd.DataFrame(),
        'total_debts': 0,
        'annual_income': 0,
        'debt_to_income_ratio': 0,
        'classification': None,
        'classification_stage': 0,
        'collection_proceedings': None,
        'can_raise_funds': None,
        'analysis_done': False,
        'messages': []
    }
    
    for key, default_value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = default_value

def get_parser_for_bank(bank_type):
    """קבלת פרסר מתאים לסוג הבנק"""
    parsers = {
        "הפועלים": HapoalimParser(),
        "לאומי": LeumiParser(),
        "דיסקונט": DiscountParser()
    }
    return parsers.get(bank_type)

def process_uploaded_files(bank_type, bank_file, credit_file, monthly_income):
    """עיבוד קבצים שהועלו"""
    results = {
        'df_bank': pd.DataFrame(),
        'df_credit': pd.DataFrame(),
        'success_messages': [],
        'error_messages': []
    }
    
    # עיבוד קובץ בנק
    if bank_file and bank_type != "ללא דוח בנק":
        parser = get_parser_for_bank(bank_type)
        if parser:
            try:
                bank_file_bytes = bank_file.getvalue()
                results['df_bank'] = parser.parse_pdf(bank_file_bytes, bank_file.name)
                
                if not results['df_bank'].empty:
                    results['success_messages'].append(f"✅ דוח בנק ({bank_type}) עובד בהצלחה!")
                else:
                    results['error_messages'].append(f"⚠️ לא הצלחנו לחלץ נתונים מדוח הבנק ({bank_type})")
            except Exception as e:
                results['error_messages'].append(f"❌ שגיאה בעיבוד דוח הבנק: {e}")
    
    # עיבוד קובץ אשראי
    if credit_file:
        try:
            credit_parser = CreditReportParser()
            credit_file_bytes = credit_file.getvalue()
            results['df_credit'] = credit_parser.parse_pdf(credit_file_bytes, credit_file.name)
            
            if not results['df_credit'].empty:
                results['success_messages'].append("✅ דוח נתוני אשראי עובד בהצלחה!")
            else:
                results['error_messages'].append("⚠️ לא הצלחנו לחלץ נתונים מדוח האשראי")
        except Exception as e:
            results['error_messages'].append(f"❌ שגיאה בעיבוד דוח האשראי: {e}")
    else:
        results['error_messages'].append("❌ נא להעלות דוח נתוני אשראי")
    
    return results

def handle_classification_questions(analyzer):
    """טיפול בשאלות הסיווג"""
    ratio = st.session_state.debt_to_income_ratio
    
    # שלב 1: חישוב יחס ראשוני
    if st.session_state.classification_stage == 1:
        classification = analyzer.classify_financial_status(ratio)
        if classification:
            st.session_state.classification = classification
            st.session_state.classification_stage = 4  # סיום
        elif analyzer.needs_collection_question(ratio):
            st.session_state.classification_stage = 2  # שאלה ראשונה
        st.rerun()
    
    # שלב 2: שאלת הליכי גבייה
    elif st.session_state.classification_stage == 2:
        st.subheader("🔍 שאלת הבהרה לסיווג")
        
        q1_answer = st.radio(
            "האם נפתחו נגדך הליכי גבייה?",
            ("כן", "לא"),
            index=None,
            key="q1_collection"
        )
        
        if q1_answer == "כן":
            st.session_state.collection_proceedings = True
            st.session_state.classification = "אדום"
            st.session_state.classification_stage = 4
            st.rerun()
        elif q1_answer == "לא":
            st.session_state.collection_proceedings = False
            st.session_state.classification_stage = 3
            st.rerun()
    
    # שלב 3: שאלת יכולת גיוס כספים
    elif st.session_state.classification_stage == 3:
        st.subheader("🔍 שאלת הבהרה נוספת")
        
        fund_amount = analyzer.calculate_fund_raising_amount(st.session_state.total_debts)
        q2_answer = st.radio(
            f"האם אתה מסוגל לגייס {fund_amount:,.0f} ₪ (50% מהחוב) תוך זמן סביר?",
            ("כן", "לא"),
            index=None,
            key="q2_raise_funds"
        )
        
        if q2_answer == "כן":
            st.session_state.can_raise_funds = True
            st.session_state.classification = "צהוב"
            st.session_state.classification_stage = 4
            st.rerun()
        elif q2_answer == "לא":
            st.session_state.can_raise_funds = False
            st.session_state.classification = "אדום"
            st.session_state.classification_stage = 4
            st.rerun()

def main():
    """פונקציה ראשית"""
    initialize_session_state()
    
    # כותרת ראשית
    st.title("💰 מומחה כלכלת המשפחה")
    st.markdown("**העלה את דוחות הבנק ודוח נתוני האשראי, ספק הכנסה חודשית, וקבל ניתוח פיננסי מקצועי**")
    
    # סרגל צד - קלטים
    with st.sidebar:
        st.header("📁 העלאת נתונים")
        
        # בחירת סוג בנק
        bank_options = ["ללא דוח בנק"] + list(SUPPORTED_BANKS.keys())
        selected_bank = st.selectbox("בחר סוג דוח בנק:", bank_options)
        
        # העלאת קובץ בנק
        bank_file = None
        if selected_bank != "ללא דוח בנק":
            bank_file = st.file_uploader(
                f"העלה דוח בנק ({selected_bank})",
                type="pdf",
                help="העלה את דוח התנועות החודשי מהבנק"
            )
        
        # העלאת קובץ אשראי
        credit_file = st.file_uploader(
            "העלה דוח נתוני אשראי",
            type="pdf",
            help="דוח זה ניתן להוריד מאתר בנק ישראל"
        )
        
        # הכנסה חודשית
        monthly_income = st.number_input(
            "הכנסה חודשית כוללת (₪):",
            min_value=0,
            value=DEFAULT_MONTHLY_INCOME,
            step=500,
            help="הכנסה חודשית נטו של כל משק הבית"
        )
        
        # כפתור ניתוח
        if st.button("🔍 נתח נתונים", type="primary", use_container_width=True):
            if not credit_file:
                st.error("נא להעלות דוח נתוני אשראי")
            else:
                # איפוס נתונים קודמים
                for key in ['analysis_done', 'classification', 'classification_stage', 
                           'collection_proceedings', 'can_raise_funds']:
                    st.session_state[key] = None if 'classification' in key or 'proceedings' in key or 'funds' in key else (0 if 'stage' in key else False)
                
                with st.spinner("מעבד נתונים... אנא המתן"):
                    # עיבוד קבצים
                    results = process_uploaded_files(selected_bank, bank_file, credit_file, monthly_income)
                    
                    # עדכון session state
                    st.session_state.df_bank = results['df_bank']
                    st.session_state.df_credit = results['df_credit']
                    
                    # הצגת הודעות
                    for msg in results['success_messages']:
                        st.success(msg)
                    for msg in results['error_messages']:
                        st.error(msg)
                    
                    # חישובים פיננסיים
                    if not results['df_credit'].empty:
                        st.session_state.total_debts = results['df_credit']['יתרת חוב'].sum()
                        st.session_state.annual_income = monthly_income * 12
                        
                        analyzer = FinancialAnalyzer()
                        st.session_state.debt_to_income_ratio = analyzer.calculate_debt_to_income_ratio(
                            st.session_state.total_debts, st.session_state.annual_income
                        )
                        
                        st.session_state.analysis_done = True
                        st.session_state.classification_stage = 1
                        st.rerun()
    
    # תוכן ראשי
    if st.session_state.analysis_done:
        analyzer = FinancialAnalyzer()
        ui = UIComponents()
        
        # סיכום פיננסי
        ui.show_financial_summary(
            st.session_state.total_debts,
            st.session_state.annual_income,
            st.session_state.debt_to_income_ratio
        )
        
        # טיפול בשאלות סיווג
        handle_classification_questions(analyzer)
        
        # הצגת תוצאת הסיווג
        if st.session_state.classification_stage == 4:
            ui.show_classification_result(st.session_state.classification, analyzer)
        
        # ויזואליזציות
        st.header("📊 ויזואליזציות")
        
        col1, col2 = st.columns(2)
        with col1:
            ui.show_debt_breakdown_chart(st.session_state.df_credit)
        with col2:
            ui.show_debt_vs_income_chart(st.session_state.total_debts, st.session_state.annual_income)
        
        # גרף מגמת יתרות
        if not st.session_state.df_bank.empty:
            ui.show_balance_trend_chart(st.session_state.df_bank, selected_bank)
        
        # טבלאות נתונים
        ui.show_data_tables(st.session_state.df_credit, st.session_state.df_bank, selected_bank)
    
    # צ'אטבוט
    chatbot = FinancialChatbot()
    analysis_data = {
        'analysis_done': st.session_state.analysis_done,
        'total_debts': st.session_state.total_debts,
        'annual_income': st.session_state.annual_income,
        'debt_to_income_ratio': st.session_state.debt_to_income_ratio,
        'classification': st.session_state.classification,
        'collection_proceedings': st.session_state.collection_proceedings,
        'can_raise_funds': st.session_state.can_raise_funds
    }
    chatbot.display_chat_interface(analysis_data)
    
    # כותרת תחתונה
    st.sidebar.markdown("---")
    st.sidebar.info("💡 **הערה חשובה:** המידע כאן אינו מהווה ייעוץ פיננסי מקצועי. יש להתייעץ עם יועץ כלכלי מוסמך.")

if __name__ == "__main__":
    main()