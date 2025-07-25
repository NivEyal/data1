"""
רכיבי ממשק משתמש
"""
import streamlit as st
import plotly.express as px
import pandas as pd
from utils.helpers import format_currency, format_percentage


class UIComponents:
    """רכיבי ממשק משתמש"""
    
    @staticmethod
    def show_header():
        """הצגת כותרת האפליקציה"""
        st.title("💰 יועץ פיננסי חכם")
        st.markdown("**קבל ניתוח מקצועי של מצבך הפיננסי בקלות ובמהירות**")
        st.markdown("---")
    
    @staticmethod
    def show_file_upload_section():
        """סעיף העלאת קבצים"""
        st.header("📁 העלאת דוחות")
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("דוח בנק")
            bank_type = st.selectbox(
                "בחר סוג בנק:",
                ["ללא דוח", "הפועלים", "לאומי", "דיסקונט"],
                key="bank_type"
            )
            
            bank_file = None
            if bank_type != "ללא דוח":
                bank_file = st.file_uploader(
                    f"העלה דוח {bank_type}",
                    type="pdf",
                    key="bank_file",
                    help="דוח תנועות חודשי מהבנק"
                )
        
        with col2:
            st.subheader("דוח נתוני אשראי")
            credit_file = st.file_uploader(
                "העלה דוח נתוני אשראי",
                type="pdf",
                key="credit_file",
                help="דוח מבנק ישראל - מומלץ מאוד"
            )
        
        return bank_type, bank_file, credit_file
    
    @staticmethod
    def show_questionnaire():
        """הצגת שאלון פיננסי"""
        st.header("📋 שאלון פיננסי")
        
        with st.form("financial_questionnaire"):
            col1, col2 = st.columns(2)
            
            with col1:
                st.subheader("הכנסות חודשיות (נטו)")
                income_main = st.number_input("הכנסתך:", min_value=0, value=0, step=500)
                income_partner = st.number_input("הכנסת בן/בת זוג:", min_value=0, value=0, step=500)
                income_other = st.number_input("הכנסות נוספות:", min_value=0, value=0, step=500)
                
                st.subheader("חובות")
                total_debts = st.number_input("סך כל החובות (ללא משכנתא):", min_value=0, value=0, step=1000)
            
            with col2:
                st.subheader("הוצאות קבועות חודשיות")
                expense_housing = st.number_input("דיור (שכירות/משכנתא):", min_value=0, value=0, step=500)
                expense_loans = st.number_input("החזרי הלוואות:", min_value=0, value=0, step=500)
                expense_other = st.number_input("הוצאות קבועות אחרות:", min_value=0, value=0, step=500)
                
                st.subheader("שאלות נוספות")
                has_collection = st.radio("האם יש הליכי גבייה נגדך?", ["לא", "כן"])
                can_raise_funds = st.radio("האם תוכל לגייס 50% מהחוב?", ["לא", "כן"])
            
            submitted = st.form_submit_button("🔍 נתח מצב פיננסי", type="primary")
            
            if submitted:
                return {
                    'total_income': income_main + income_partner + income_other,
                    'total_expenses': expense_housing + expense_loans + expense_other,
                    'total_debts': total_debts,
                    'has_collection': has_collection == "כן",
                    'can_raise_funds': can_raise_funds == "כן"
                }
        
        return None
    
    @staticmethod
    def show_financial_summary(data):
        """הצגת סיכום פיננסי"""
        st.header("📊 סיכום פיננסי")
        
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric("💰 הכנסה חודשית", format_currency(data['total_income']))
        
        with col2:
            st.metric("💸 הוצאות קבועות", format_currency(data['total_expenses']))
        
        with col3:
            st.metric("🏦 סך חובות", format_currency(data['total_debts']))
        
        with col4:
            annual_income = data['total_income'] * 12
            ratio = data['total_debts'] / annual_income if annual_income > 0 else float('inf')
            st.metric("⚖️ יחס חוב להכנסה", format_percentage(ratio))
        
        # יתרה חודשית
        monthly_balance = data['total_income'] - data['total_expenses']
        if monthly_balance >= 0:
            st.success(f"✅ יתרה חודשית: {format_currency(monthly_balance)}")
        else:
            st.error(f"❌ גירעון חודשי: {format_currency(abs(monthly_balance))}")
    
    @staticmethod
    def show_classification_result(classification):
        """הצגת תוצאת הסיווג"""
        if not classification:
            st.warning("⏳ נדרש מידע נוסף לסיווג המצב")
            return
        
        # הצגת הסיווג
        if classification['color'] == 'success':
            st.success(classification['message'])
        elif classification['color'] == 'warning':
            st.warning(classification['message'])
        elif classification['color'] == 'error':
            st.error(classification['message'])
        
        # הצגת המלצות
        st.subheader("💡 המלצות לפעולה")
        for i, rec in enumerate(classification['recommendations'], 1):
            st.write(f"{i}. {rec}")
    
    @staticmethod
    def show_charts(data, df_credit=None, df_bank=None):
        """הצגת תרשימים"""
        st.header("📈 ויזואליזציות")
        
        col1, col2 = st.columns(2)
        
        with col1:
            # תרשים הכנסות vs הוצאות vs חובות
            comparison_data = pd.DataFrame({
                'קטגוריה': ['הכנסה שנתית', 'הוצאות שנתיות', 'סך חובות'],
                'סכום': [
                    data['total_income'] * 12,
                    data['total_expenses'] * 12,
                    data['total_debts']
                ]
            })
            
            fig = px.bar(
                comparison_data,
                x='קטגוריה',
                y='סכום',
                title='השוואה פיננסית שנתית',
                color='קטגוריה'
            )
            st.plotly_chart(fig, use_container_width=True)
        
        with col2:
            # תרשים פירוק חובות (אם יש דוח אשראי)
            if df_credit is not None and not df_credit.empty:
                debt_by_type = df_credit.groupby('סוג עסקה')['יתרת חוב'].sum().reset_index()
                debt_by_type = debt_by_type[debt_by_type['יתרת חוב'] > 0]
                
                if not debt_by_type.empty:
                    fig = px.pie(
                        debt_by_type,
                        values='יתרת חוב',
                        names='סוג עסקה',
                        title='פירוק חובות לפי סוג'
                    )
                    st.plotly_chart(fig, use_container_width=True)
                else:
                    st.info("אין נתוני חובות להצגה")
            else:
                st.info("העלה דוח נתוני אשראי לפירוק מפורט של החובות")
        
        # תרשים מגמת יתרות (אם יש דוח בנק)
        if df_bank is not None and not df_bank.empty:
            st.subheader("מגמת יתרות בחשבון")
            fig = px.line(
                df_bank,
                x='Date',
                y='Balance',
                title='מגמת יתרת החשבון',
                markers=True
            )
            st.plotly_chart(fig, use_container_width=True)
    
    @staticmethod
    def show_data_tables(df_credit=None, df_bank=None):
        """הצגת טבלאות נתונים"""
        with st.expander("📋 נתונים מפורטים"):
            if df_credit is not None and not df_credit.empty:
                st.subheader("נתוני אשראי")
                st.dataframe(df_credit, use_container_width=True)
            
            if df_bank is not None and not df_bank.empty:
                st.subheader("נתוני בנק")
                st.dataframe(df_bank, use_container_width=True)