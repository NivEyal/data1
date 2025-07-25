"""
רכיבי ממשק משתמש
"""
import streamlit as st
import plotly.express as px
import pandas as pd


class UIComponents:
    """מחלקה לרכיבי ממשק המשתמש"""
    
    @staticmethod
    def show_financial_summary(total_debts, annual_income, debt_ratio):
        """הצגת סיכום פיננסי"""
        st.header("📊 סיכום פיננסי")
        
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("💰 סך חובות", f"{total_debts:,.0f} ₪")
        with col2:
            st.metric("📈 הכנסה שנתית", f"{annual_income:,.0f} ₪")
        with col3:
            st.metric("⚖️ יחס חוב להכנסה", f"{debt_ratio:.1%}")
    
    @staticmethod
    def show_classification_result(classification, analyzer):
        """הצגת תוצאת הסיווג"""
        if not classification:
            return
        
        status_type, message = analyzer.get_classification_color_and_message(classification)
        
        if status_type == "success":
            st.success(message)
        elif status_type == "warning":
            st.warning(message)
        elif status_type == "error":
            st.error(message)
        else:
            st.info(message)
    
    @staticmethod
    def show_debt_breakdown_chart(df_credit):
        """תרשים פירוק חובות"""
        if df_credit.empty or 'סוג עסקה' not in df_credit.columns:
            return
        
        st.subheader("📊 פירוק חובות לפי סוג")
        
        debt_summary = df_credit.groupby("סוג עסקה")["יתרת חוב"].sum().reset_index()
        debt_summary = debt_summary[debt_summary['יתרת חוב'] > 0]
        
        if not debt_summary.empty:
            fig = px.pie(
                debt_summary, 
                values='יתרת חוב', 
                names='סוג עסקה',
                title='פירוט יתרות חוב לפי סוג עסקה',
                color_discrete_sequence=px.colors.qualitative.Set3
            )
            fig.update_traces(textposition='inside', textinfo='percent+label')
            fig.update_layout(font=dict(size=14))
            st.plotly_chart(fig, use_container_width=True)
    
    @staticmethod
    def show_debt_vs_income_chart(total_debts, annual_income):
        """תרשים השוואת חובות להכנסה"""
        if total_debts <= 0 or annual_income <= 0:
            return
        
        st.subheader("📊 השוואת חובות להכנסה")
        
        comparison_data = pd.DataFrame({
            'קטגוריה': ['סך חובות', 'הכנסה שנתית'],
            'סכום בש"ח': [total_debts, annual_income]
        })
        
        fig = px.bar(
            comparison_data, 
            x='קטגוריה', 
            y='סכום בש"ח',
            title='השוואת סך חובות להכנסה שנתית',
            color='קטגוריה',
            text_auto=True
        )
        fig.update_layout(showlegend=False, font=dict(size=14))
        st.plotly_chart(fig, use_container_width=True)
    
    @staticmethod
    def show_balance_trend_chart(df_bank, bank_name):
        """תרשים מגמת יתרות"""
        if df_bank.empty or 'Date' not in df_bank.columns:
            return
        
        st.subheader(f"📈 מגמת יתרת חשבון - {bank_name}")
        
        df_plot = df_bank.dropna(subset=['Date', 'Balance'])
        if not df_plot.empty:
            fig = px.line(
                df_plot, 
                x='Date', 
                y='Balance',
                title=f'מגמת יתרת חשבון ({bank_name})',
                markers=True
            )
            fig.update_layout(
                xaxis_title='תאריך',
                yaxis_title='יתרה בש"ח',
                font=dict(size=14)
            )
            st.plotly_chart(fig, use_container_width=True)
    
    @staticmethod
    def show_data_tables(df_credit, df_bank, bank_name):
        """הצגת טבלאות נתונים"""
        # טבלת נתוני אשראי
        with st.expander("📋 טבלת נתוני אשראי מפורטת"):
            if not df_credit.empty:
                # עיצוב הטבלה
                styled_df = df_credit.style.format({
                    "גובה מסגרת": '{:,.0f}',
                    "סכום מקורי": '{:,.0f}',
                    "יתרת חוב": '{:,.0f}',
                    "יתרה שלא שולמה": '{:,.0f}'
                })
                st.dataframe(styled_df, use_container_width=True)
            else:
                st.info("לא נטענו נתוני אשראי")
        
        # טבלת יתרות בנק
        if bank_name != "ללא דוח בנק":
            with st.expander(f"🏦 טבלת יתרות בנק ({bank_name})"):
                if not df_bank.empty:
                    styled_df = df_bank.style.format({"Balance": '{:,.2f}'})
                    st.dataframe(styled_df, use_container_width=True)
                else:
                    st.info("לא נטענו נתוני בנק")