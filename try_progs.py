import sqlite3
import pandas as pd
import plotly.express as px
import streamlit as st

# ==========================================
# 1. Database Manager (إدارة قاعدة البيانات)
# ==========================================
class DatabaseManager:
    def __init__(self, db_name: str = "zain_competitors.db"):
        self.db_name = db_name
        self.init_db()

    def get_connection(self):
        return sqlite3.connect(self.db_name)

    def init_db(self):
        """إنشاء الجداول تلقائياً عند تشغيل التطبيق إذا لم تكن موجودة"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS competitor_offers (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    Competitor_Name TEXT NOT NULL,
                    Plan_Type TEXT,
                    Price_IQD REAL,
                    Data_GB REAL,
                    Validity_Days REAL,
                    Cost_Per_GB REAL,
                    Cost_Per_Day REAL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            conn.commit()

    def save_data(self, df: pd.DataFrame) -> tuple[bool, str]:
        """حفظ البيانات المعالجة داخل قاعدة البيانات"""
        try:
            with self.get_connection() as conn:
                df.to_sql('competitor_offers', conn, if_exists='append', index=False)
            return True, "تم حفظ البيانات في قاعدة البيانات بنجاح!"
        except Exception as e:
            return False, f"خطأ أثناء الحفظ بقاعدة البيانات: {str(e)}"

    def fetch_all_data(self) -> pd.DataFrame:
        """قراءة كامل البيانات المخزنة من قاعدة البيانات"""
        with self.get_connection() as conn:
            return pd.read_sql_query("SELECT * FROM competitor_offers ORDER BY created_at DESC", conn)

    def clear_database(self):
        """حذف جميع البيانات المكسورة أو القديمة"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM competitor_offers")
            conn.commit()

# ==========================================
# 2. File Processor & Data Cleaner
# ==========================================
class FileProcessor:
    def __init__(self, required_columns: list):
        self.required_columns = required_columns

    def load_file(self, uploaded_file):
        if uploaded_file is None:
            return None, "لم يتم رفع أي ملف."
        try:
            filename = uploaded_file.name
            if filename.endswith('.csv'):
                df = pd.read_csv(uploaded_file)
            elif filename.endswith(('.xls', '.xlsx')):
                df = pd.read_excel(uploaded_file)
            else:
                return None, "صيغة الملف غير مدعومة. يرجى رفع ملف CSV أو Excel."
            return df, None
        except Exception as e:
            return None, f"حدث خطأ أثناء قراءة الملف: {str(e)}"

    def validate_schema(self, df: pd.DataFrame):
        if df is None or df.empty:
            return False, "الجدول المرفوع فارغ."
        missing_cols = [col for col in self.required_columns if col not in df.columns]
        if missing_cols:
            return False, f"الملف لا يطابق السكيمة المطلوب! الأعمدة المفقودة: {', '.join(missing_cols)}"
        return True, "السكيمة متطابقة وصحيحة."

class DataCleaner:
    def remove_duplicates(self, df: pd.DataFrame) -> pd.DataFrame:
        return df.drop_duplicates().reset_index(drop=True)

    def clean_text_columns(self, df: pd.DataFrame, text_columns: list) -> pd.DataFrame:
        for col in text_columns:
            if col in df.columns:
                df[col] = df[col].astype(str).str.strip().str.title()
        return df

    def clean_numeric_columns(self, df: pd.DataFrame, numeric_defaults: dict) -> pd.DataFrame:
        for col, default_val in numeric_defaults.items():
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce').fillna(default_val)
        return df

    def execute_cleaning_pipeline(self, df: pd.DataFrame) -> pd.DataFrame:
        cleaned_df = self.remove_duplicates(df)
        cleaned_df = self.clean_text_columns(cleaned_df, ['Competitor_Name', 'Plan_Type'])
        defaults = {'Price_IQD': 0.0, 'Data_GB': 0.0, 'Validity_Days': 1.0}
        cleaned_df = self.clean_numeric_columns(cleaned_df, defaults)
        return cleaned_df

# ==========================================
# 3. Analytics & Business Logic
# ==========================================
class CompetitorAnalyzer:
    def __init__(self, df: pd.DataFrame):
        self.df = df.copy()

    def apply_business_logic(self) -> pd.DataFrame:
        safe_data_gb = self.df['Data_GB'].replace(0, 0.001)
        safe_validity = self.df['Validity_Days'].replace(0, 1)

        self.df['Cost_Per_GB'] = self.df['Price_IQD'] / safe_data_gb
        self.df['Cost_Per_Day'] = self.df['Price_IQD'] / safe_validity
        return self.df

    def compute_summary_kpis(self) -> dict:
        if self.df.empty:
            return {}
        avg_gb_prices = self.df.groupby('Competitor_Name')['Cost_Per_GB'].mean().to_dict()
        cheapest_comp = min(avg_gb_prices, key=avg_gb_prices.get) if avg_gb_prices else "N/A"
        most_common_plan = self.df['Plan_Type'].mode()[0] if not self.df['Plan_Type'].empty else "N/A"

        return {
            'total_records': len(self.df),
            'avg_gb_prices': avg_gb_prices,
            'cheapest_competitor': cheapest_comp,
            'most_common_plan': most_common_plan
        }

class RecommendationEngine:
    def __init__(self, zain_baseline_gb_price: float = 1500.0):
        self.zain_baseline_gb_price = zain_baseline_gb_price

    def generate_recommendations(self, df: pd.DataFrame, kpis: dict) -> list:
        recommendations = []
        if not kpis or df.empty:
            return ["لا توجد بيانات كافية لتوليد التوصيات."]

        cheapest_comp = kpis.get('cheapest_competitor')
        cheapest_price = kpis.get('avg_gb_prices', {}).get(cheapest_comp, 0)

        if cheapest_price > 0 and cheapest_price < self.zain_baseline_gb_price:
            diff_pct = round(((self.zain_baseline_gb_price - cheapest_price) / self.zain_baseline_gb_price) * 100, 1)
            recommendations.append(
                f"⚠️ **تنبيه سعر المنافسة:** المنافس (**{cheapest_comp}**) يقدم متوسط سعر للجيجابايت أرخص من زين بنسبة **{diff_pct}%**. يُوصى بإطلاق باقة داتا ترويجية."
            )

        long_plans = df[df['Validity_Days'] >= 30]
        if len(df) > 0 and (len(long_plans) / len(df)) >= 0.4:
            recommendations.append(
                "📅 **اتجاه العروض:** المنافسون يركزون بشكل مكثف على الباقات ذات الصلاحية الممتدة (30 يوم أو أكثر). يُنصح بتعزيز خطط الصلاحيات الشهرية."
            )
        available_types = [t.lower() for t in df['Plan_Type'].dropna().unique()]
        if 'student' not in available_types:
            recommendations.append(
                "🎓 **فرصة استراتيجية:** لا توجد عروض موجهة لشريحة 'الطلاب' بين المنافسين في البيانات. فرصة لشركة زين للاستحواذ على هذه الفئة."
            )

        return recommendations

# ==========================================
# 4. Streamlit Front-End (الواجهة الأمامية)
# ==========================================
st.set_page_config(page_title="نظام تحليل منافسي زين", layout="wide", page_icon="📊")

# تهيئة الكائنات
db_manager = DatabaseManager()
file_processor = FileProcessor(required_columns=['Competitor_Name', 'Plan_Type', 'Price_IQD', 'Data_GB', 'Validity_Days'])
cleaner = DataCleaner()

# القائمة الجانبية (Sidebar)
st.sidebar.title("⚙️ لوحة التحكم")
zain_baseline = st.sidebar.number_input("سعر الجيجابايت المرجعي لزين (IQD)", value=1500.0, step=100.0)
rec_engine = RecommendationEngine(zain_baseline_gb_price=zain_baseline)

st.title("📊 نظام تحليل بيانات عروض منافسي شركة زين")

# إنشاء التبويبات (Tabs)
tab_upload, tab_database = st.tabs(["📁 رفع وتحليل ملف جديد", "🗄️ قاعدة البيانات المخزنة"])

# --- التبويب الأول: رفع وحفظ الملفات ---
with tab_upload:
    st.subheader("رفع ملف البيانات جديد (CSV / Excel)")
    uploaded_file = st.file_uploader("اختر ملفاً لرفعه", type=['csv', 'xlsx'], key="file_uploader")

    if uploaded_file:
        df_raw, err = file_processor.load_file(uploaded_file)
        if err:
            st.error(err)
        else:
            is_valid, val_msg = file_processor.validate_schema(df_raw)
            if not is_valid:
                st.error(val_msg)
            else:
                cleaned_df = cleaner.execute_cleaning_pipeline(df_raw)
                analyzer = CompetitorAnalyzer(cleaned_df)
                processed_df = analyzer.apply_business_logic()
                
                st.success("تم فحص وتنظيف البيانات بنجاح!")

                # زر حفظ البيانات في DB
                if st.button("💾 حفظ البيانات في قاعدة البيانات", type="primary"):
                    saved, db_msg = db_manager.save_data(processed_df)
                    if saved:
                        st.success(db_msg)
                    else:
                        st.error(db_msg)

                # عرض KPIs والتشغيل البصري
                kpis = analyzer.compute_summary_kpis()
                c1, c2, c3 = st.columns(3)
                c1.metric("أرخص منافس للبيانات", kpis.get('cheapest_competitor', 'N/A'))
                c2.metric("نوع العرض الأكثر انتشاراً", kpis.get('most_common_plan', 'N/A'))
                c3.metric("عدد العروض المحللة", kpis.get('total_records', 0))

                st.divider()

                chart_col1, chart_col2 = st.columns(2)
                with chart_col1:
                    fig_bar = px.bar(
                        processed_df, 
                        x='Competitor_Name', 
                        y='Cost_Per_GB', 
                        color='Competitor_Name',
                        title="مقارنة متوسط سعر الجيجابايت (IQD)"
                    )
                    st.plotly_chart(fig_bar, use_container_width=True)

                with chart_col2:
                    fig_pie = px.pie(
                        processed_df, 
                        names='Plan_Type', 
                        title="توزيع أنواع العروض في السوق"
                    )
                    st.plotly_chart(fig_pie, use_container_width=True)

                st.subheader("💡 التوصيات الاستراتيجية")
                for rec in rec_engine.generate_recommendations(processed_df, kpis):
                    st.info(rec)

# --- التبويب الثاني: استعراض قاعدة البيانات ---
with tab_database:
    st.subheader("🗄️ السجلات المخزنة في قاعدة البيانات")
    
    db_df = db_manager.fetch_all_data()
    
    if db_df.empty:
        st.warning("لا توجد بيانات مخزنة في قاعدة البيانات حالياً.")
    else:
        st.dataframe(db_df, use_container_width=True)
        
        # تحليلات على البيانات التاريخية المخزنة
        st.divider()
        st.subheader("📊 تحليل إجمالي السجلات التاريخية")
        
        history_analyzer = CompetitorAnalyzer(db_df)
        history_kpis = history_analyzer.compute_summary_kpis()
        
        col_a, col_b = st.columns(2)
        col_a.metric("إجمالي العروض في قاعدة البيانات", len(db_df))
        col_b.metric("أرخص منافس (تاريخياً)", history_kpis.get('cheapest_competitor', 'N/A'))
        
        if st.button("🗑️ مسح جميع البيانات من قاعدة البيانات", type="secondary"):
            db_manager.clear_database()
            st.warning("تم مسح جميع البيانات المخزنة بنجاح.")
            st.rerun()