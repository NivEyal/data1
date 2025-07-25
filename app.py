"""
אפליקציית יועץ פיננסי חכם
"""
import streamlit as st
import pandas as pd
import logging
from config import APP_TITLE, APP_ICON
from parsers.bank_parser import BankParser
from parsers.credit_parser import CreditParser
from analyzer.financial_analyzer import FinancialAnalyzer
from ui.components import UIComponents
from chatbot.advisor import FinancialAdvisor

# הגדרת לוגינג
logging.basicConfig(level=logging.INFO)

# הגדרת עמוד
st.set_page_config(
    page_title=APP_TITLE,
    page_icon=APP_ICON,
    layout="wide",
    initial_sidebar_state="expanded"
)

# אתחול משתני session state
def initialize_session_state():
    """אתחול משתני session state"""
    defaults = {
        'financial_data': None,
        'df_bank': pd.DataFrame(),
        'df_credit': pd.DataFrame(),
        'analysis_complete': False,
        'classification': None
    }
    
    for key, default_value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = default_value


def process_files(bank_type, bank_file, credit_file):
    """עיבוד קבצים שהועלו"""
    df_bank = pd.DataFrame()
    df_credit = pd.DataFrame()
    messages = []
    
    # עיבוד דוח בנק
    if bank_file and bank_type != "ללא דוח":
        try:
            parser = BankParser(bank_type)
            df_bank = parser.parse_pdf(bank_file.getvalue(), bank_file.name)
            
            if not df_bank.empty:
                messages.append(f"✅ דוח {bank_type} עובד בהצלחה - {len(df_bank)} רשומות")
            else:
                messages.append(f"⚠️ לא נמצאו נתונים בדוח {bank_type}")
        except Exception as e:
            messages.append(f"❌ שגיאה בעיבוד דוח {bank_type}: {e}")
    
    # עיבוד דוח אשראי
    if credit_file:
        try:
            parser = CreditParser()
            df_credit = parser.parse_pdf(credit_file.getvalue(), credit_file.name)
            
            if not df_credit.empty:
                messages.append(f"✅ דוח נתוני אשראי עובד בהצלחה - {len(df_credit)} רשומות")
            else:
                messages.append("⚠️ לא נמצאו נתונים בדוח האשראי")
        except Exception as e:
            messages.append(f"❌ שגיאה בעיבוד דוח האשראי: {e}")
    
    return df_bank, df_credit, messages


def main():
    """פונקציה ראשית"""
    initialize_session_state()
    ui = UIComponents()
    
    # כותרת
    ui.show_header()
    
    # סרגל צד
    with st.sidebar:
        st.header("🎛️ בקרה")
        
        if st.button("🔄 התחל מחדש", type="secondary"):
            for key in st.session_state.keys():
                del st.session_state[key]
            st.rerun()
        
        st.markdown("---")
        st.info("💡 **טיפ:** העלה דוחות לניתוח מדויק יותר")
    
    # העלאת קבצים
    bank_type, bank_file, credit_file = ui.show_file_upload_section()
    
    # עיבוד קבצים אם הועלו
    if bank_file or credit_file:
        if st.button("📊 עבד קבצים", type="secondary"):
            with st.spinner("מעבד קבצים..."):
                df_bank, df_credit, messages = process_files(bank_type, bank_file, credit_file)
                
                # שמירה ב-session state
                st.session_state.df_bank = df_bank
                st.session_state.df_credit = df_credit
                
                # הצגת הודעות
                for msg in messages:
                    if "✅" in msg:
                        st.success(msg)
                    elif "⚠️" in msg:
                        st.warning(msg)
                    else:
                        st.error(msg)
    
    st.markdown("---")
    
    # שאלון פיננסי
    questionnaire_data = ui.show_questionnaire()
    
    if questionnaire_data:
        # שמירת נתונים
        st.session_state.financial_data = questionnaire_data
        
        # חישוב נתונים נוספים מדוחות
        if not st.session_state.df_credit.empty:
            credit_debt = st.session_state.df_credit['יתרת חוב'].fillna(0).sum()
            if credit_debt > 0:
                st.session_state.financial_data['total_debts'] = max(
                    st.session_state.financial_data['total_debts'], 
                    credit_debt
                )
                st.info(f"עודכן סך החובות לפי דוח האשראי: {credit_debt:,.0f} ₪")
        
        # ניתוח פיננסי
        analyzer = FinancialAnalyzer()
        annual_income = questionnaire_data['total_income'] * 12
        debt_ratio = analyzer.calculate_debt_to_income_ratio(
            questionnaire_data['total_debts'], 
            annual_income
        )
        
        # סיווג
        classification = analyzer.classify_financial_status(
            debt_ratio,
            questionnaire_data['has_collection'],
            questionnaire_data['can_raise_funds']
        )
        
        st.session_state.classification = classification
        st.session_state.analysis_complete = True
        
        st.markdown("---")
        
        # הצגת תוצאות
        ui.show_financial_summary(questionnaire_data)
        
        st.markdown("---")
        
        if classification:
            ui.show_classification_result(classification)
        else:
            # שאלות נוספות אם נדרש
            if analyzer.needs_additional_questions(debt_ratio):
                st.warning("⏳ נדרש מידע נוסף לסיווג מדויק")
                
                with st.form("additional_questions"):
                    st.subheader("שאלות נוספות")
                    
                    fund_amount = analyzer.calculate_fund_raising_amount(questionnaire_data['total_debts'])
                    
                    collection = st.radio(
                        "האם נפתחו נגדך הליכי גבייה?",
                        ["לא", "כן"]
                    )
                    
                    funds = st.radio(
                        f"האם תוכל לגייס {fund_amount:,.0f} ₪ (50% מהחוב)?",
                        ["לא", "כן"]
                    )
                    
                    if st.form_submit_button("סיים ניתוח"):
                        classification = analyzer.classify_financial_status(
                            debt_ratio,
                            collection == "כן",
                            funds == "כן"
                        )
                        st.session_state.classification = classification
                        st.rerun()
        
        st.markdown("---")
        
        # ויזואליזציות
        ui.show_charts(
            questionnaire_data,
            st.session_state.df_credit,
            st.session_state.df_bank
        )
        
        # טבלאות נתונים
        ui.show_data_tables(
            st.session_state.df_credit,
            st.session_state.df_bank
        )
        
        st.markdown("---")
        
        # יועץ וירטואלי
        advisor = FinancialAdvisor()
        advisor.display_chat(st.session_state.financial_data)
    
    # כותרת תחתונה
    st.markdown("---")
    st.markdown(
        "<div style='text-align: center; color: gray;'>"
        "💡 המידע כאן אינו מהווה ייעוץ פיננסי מקצועי. "
        "יש להתייעץ עם יועץ כלכלי מוסמך."
        "</div>",
        unsafe_allow_html=True
    )


if __name__ == "__main__":
    main()