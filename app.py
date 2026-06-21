import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
import io

# -----------------------------------------------------------------------------
# 1. 頁面基本設定與主題 CSS 注入
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="信用風險標準法計量與風險權重計算器",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 注入高級感設計的自訂 CSS (包含暗色調與玻璃微光效果)
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;600;700&family=Noto+Sans+TC:wght@300;400;500;700&display=swap');
    
    /* 全域字體與背景微調 */
    html, body, [class*="css"] {
        font-family: 'Outfit', 'Noto Sans TC', sans-serif;
    }
    
    /* 頂部標題漸層效果 */
    .title-gradient {
        background: linear-gradient(135deg, #1e3c72 0%, #2a5298 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        font-weight: 700;
        font-size: 2.5rem;
        margin-bottom: 0.5rem;
    }
    .subtitle {
        color: #666;
        font-size: 1.1rem;
        margin-bottom: 2rem;
    }
    
    /* 玻璃擬態卡片容器 */
    .premium-card {
        background: rgba(255, 255, 255, 0.9);
        border: 1px solid rgba(226, 232, 240, 0.8);
        border-radius: 16px;
        padding: 24px;
        box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.05), 0 4px 6px -2px rgba(0, 0, 0, 0.02);
        margin-bottom: 20px;
        transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
    }
    .premium-card:hover {
        transform: translateY(-2px);
        box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.1), 0 10px 10px -5px rgba(0, 0, 0, 0.04);
        border-color: #2a5298;
    }
    
    /* 核心指標展示 */
    .metric-title {
        font-size: 0.9rem;
        color: #718096;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        margin-bottom: 4px;
        font-weight: 600;
    }
    .metric-value {
        font-size: 2.2rem;
        font-weight: 700;
        color: #1a202c;
        line-height: 1.2;
    }
    .metric-sub {
        font-size: 0.85rem;
        color: #4a5568;
        margin-top: 6px;
    }
    
    /* 漸層標籤 */
    .badge-primary {
        background: linear-gradient(135deg, #2b6cb0 0%, #1a365d 100%);
        color: white;
        padding: 4px 10px;
        border-radius: 8px;
        font-size: 0.8rem;
        font-weight: bold;
    }
    .badge-success {
        background: linear-gradient(135deg, #48bb78 0%, #22543d 100%);
        color: white;
        padding: 4px 10px;
        border-radius: 8px;
        font-size: 0.8rem;
        font-weight: bold;
    }
    
    /* 分隔線 */
    .divider {
        height: 1px;
        background: linear-gradient(to right, #2a5298, transparent);
        margin: 25px 0;
    }
    
    /* 調整 sidebar 樣式 */
    .css-1d391tw {
        background-color: #f7fafc;
    }
</style>
""", unsafe_allow_html=True)

# -----------------------------------------------------------------------------
# 2. 常數與法規對照表定義
# -----------------------------------------------------------------------------
# 外部信用評等對照表 (S&P/Fitch vs Moody's vs 中華信評)
RATING_MAP = {
    "S&P / Fitch": ["AAA ~ AA-", "A+ ~ A-", "BBB+ ~ BBB-", "BB+ ~ B-", "Below B-", "Unrated (未評等)"],
    "Moody's": ["Aaa ~ Aa3", "A1 ~ A3", "Baa1 ~ Baa3", "Ba1 ~ B3", "Below B3", "Unrated (未評等)"],
    "Taiwan Ratings (中華信評)": ["twAAA ~ twAA-", "twA+ ~ twA-", "twBBB+ ~ twBBB-", "twBB+ ~ twB-", "Below twB-", "Unrated (未評等)"]
}

# 1. 主權國家與中央銀行風險權數
SOVEREIGN_RULES = {
    0: 0.0,   # 等級 1
    1: 0.20,  # 等級 2
    2: 0.50,  # 等級 3
    3: 1.00,  # 等級 4 (BB+ ~ BB-)
    4: 1.00,  # 等級 5 (B+ ~ B-)
    5: 1.50,  # 等級 6
    6: 1.00   # 未評等
}

# 2. 銀行與證券商風險權數 (標準評等法 - 依銀行本身評等)
# 分為長期與短期(3個月以下)
BANK_RULES = {
    0: {"long": 0.20, "short": 0.20},  # 等級 1
    1: {"long": 0.50, "short": 0.20},  # 等級 2
    2: {"long": 0.50, "short": 0.20},  # 等級 3
    3: {"long": 1.00, "short": 0.50},  # 等級 4
    4: {"long": 1.00, "short": 0.50},  # 等級 5
    5: {"long": 1.50, "short": 1.50},  # 等級 6
    6: {"long": 0.50, "short": 0.20}   # 未評等
}

# 3. 一般企業風險權數
CORPORATE_RULES = {
    0: 0.20,  # 等級 1
    1: 0.50,  # 等級 2
    2: 1.00,  # 等級 3 & 4 (BBB+ ~ BB-)
    3: 1.00,  # 等級 3 & 4 (BBB+ ~ BB-)
    4: 1.50,  # 等級 5 & 6
    5: 1.00,  # 未評等
    "SME": 0.85 # 未評等合格中小企業適用優惠權數 (Basel III 核心改革)
}

# 表外項目之信用轉換係數 (CCF)
CCF_RULES = {
    "直接授信等值工具 (如一般保證、承兌、信用衍生商品)": 1.00,
    "特定交易相關之或有債務 (如履約保證金、投標保證金)": 0.50,
    "短期且具自行清償性質之貿易相關信用狀 (如以出運單據為抵押之信用狀)": 0.20,
    "可無條件隨時撤銷之承諾 (UCC)": 0.10,
    "其他承諾 (原始期限不限，非屬無條件撤銷者)": 0.40,
    "未承諾或可隨時撤銷之額度": 0.10,
    "無表外項目 (直接表內曝險)": 0.00
}

# 合格擔保品及其折扣率 (Haircut) - 適用信用風險抵減綜合法
CRM_HAIRCUTS = {
    "現金 (與曝險幣別相同)": 0.00,
    "現金 (與曝險幣別不同 - 有匯率風險)": 0.08,
    "主權債券 (評等 AAA~AA-，年限 <= 1年)": 0.005,
    "主權債券 (評等 AAA~AA-，年限 > 1年且 <= 5年)": 0.02,
    "主權債券 (評等 AAA~AA-，年限 > 5年)": 0.04,
    "主權債券 (評等 A+~BBB-，年限 <= 1年)": 0.01,
    "主權債券 (評等 A+~BBB-，年限 > 1年且 <= 5年)": 0.03,
    "主權債券 (評等 A+~BBB-，年限 > 5年)": 0.06,
    "企業/銀行債券 (評等 AAA~AA-，年限 <= 1年)": 0.01,
    "企業/銀行債券 (評等 AAA~AA-，年限 > 1年且 <= 5年)": 0.04,
    "企業/銀行債券 (評等 AAA~AA-，年限 > 5年)": 0.08,
    "企業/銀行債券 (評等 A+~BBB-，年限 <= 1年)": 0.02,
    "企業/銀行債券 (評等 A+~BBB-，年限 > 1年且 <= 5年)": 0.06,
    "企業/銀行債券 (評等 A+~BBB-，年限 > 5年)": 0.12,
    "主要指數股票 (Main Index Equities)": 0.15,
    "黃金": 0.15,
    "無擔保品": 0.00
}

# -----------------------------------------------------------------------------
# 3. 計算邏輯函數
# -----------------------------------------------------------------------------
def calculate_risk_weight(category, rating_idx, rating_agency, details={}):
    """計算信用風險權重"""
    if category == "主權國家與中央銀行":
        return SOVEREIGN_RULES.get(rating_idx, 1.0)
        
    elif category == "銀行與證券商":
        is_short_term = details.get("is_short_term", False)
        rule = BANK_RULES.get(rating_idx, {"long": 0.50, "short": 0.20})
        return rule["short"] if is_short_term else rule["long"]
        
    elif category == "一般企業":
        is_sme = details.get("is_sme", False)
        # 對應等級索引
        # AAA~AA- (0), A+~A- (1), BBB+~BBB- (2), BB+~B- (3), Below B- (4), Unrated (5)
        if rating_idx == 5: # Unrated
            return CORPORATE_RULES["SME"] if is_sme else CORPORATE_RULES[5]
        elif rating_idx in [2, 3]: # BBB+ ~ B-
            return CORPORATE_RULES[2] # 100%
        else:
            return CORPORATE_RULES.get(rating_idx, 1.0)
            
    elif category == "零售債權":
        retail_type = details.get("retail_type", "合格零售債權")
        if "合格零售" in retail_type:
            return 0.75
        else:
            return 1.00
            
    elif category == "住宅用不動產 (RRE)":
        ltv = details.get("ltv", 80.0)
        dependent_on_cash_flow = details.get("dependent_on_cash_flow", False)
        
        if dependent_on_cash_flow:
            if ltv <= 50: return 0.30
            elif ltv <= 60: return 0.35
            elif ltv <= 80: return 0.45
            elif ltv <= 90: return 0.60
            elif ltv <= 100: return 0.75
            else: return 1.05
        else:
            if ltv <= 50: return 0.20
            elif ltv <= 60: return 0.25
            elif ltv <= 80: return 0.30
            elif ltv <= 90: return 0.40
            elif ltv <= 100: return 0.50
            else: return 0.70
            
    elif category == "商用不動產 (CRE)":
        ltv = details.get("ltv", 80.0)
        dependent_on_cash_flow = details.get("dependent_on_cash_flow", False)
        if dependent_on_cash_flow:
            if ltv <= 60: return 0.65
            elif ltv <= 80: return 0.75
            else: return 1.10
        else:
            if ltv <= 60: return 0.50
            else: return 1.00
            
    elif category == "權益證券 (股權)":
        equity_type = details.get("equity_type", "一般上市股權")
        if "非上市" in equity_type or "投機" in equity_type:
            return 4.00
        elif "上市" in equity_type:
            return 2.50
        else:
            return 1.00
            
    elif category == "其他資產":
        asset_type = details.get("other_asset_type", "一般資產")
        if "現金" in asset_type or "黃金" in asset_type:
            return 0.00
        elif "託收中" in asset_type:
            return 0.20
        else:
            return 1.00
            
    elif category == "土地收購、開發及建築 (ADC 曝險)":
        adc_type = details.get("adc_type", "一般土地收購/開發/建築放款 - 未滿足審慎條件")
        if "商業區購地" in adc_type or "工業區閒置土地" in adc_type:
            return 2.00
        elif "滿足審慎條件" in adc_type:
            return 1.00
        else: # 住宅區購地, 建築業餘屋, 一般未滿足條件
            return 1.50
            
    return 1.00

def get_rating_label(category, rating_idx, rating_agency):
    """取得對應信用評等的標籤文字"""
    if category in ["主權國家與中央銀行", "銀行與證券商", "一般企業"]:
        return RATING_MAP[rating_agency][rating_idx]
    return "不適用 (依資產類別或 LTV 計算)"

# -----------------------------------------------------------------------------
# 4. 側邊欄設定
# -----------------------------------------------------------------------------
st.sidebar.markdown("""
<div style="text-align: center; margin-bottom: 20px;">
    <h2 style="color: #2a5298; font-weight: 700; margin-bottom: 5px;">⚙️ 設定面板</h2>
    <p style="color: #718096; font-size: 0.85rem;">信用風險標準法設定</p>
</div>
""", unsafe_allow_html=True)

regulatory_framework = st.sidebar.selectbox(
    "適用監理規範版本",
    ["台灣金管會最新版本 (與巴塞爾協定III改革同步)", "國際巴塞爾協定III (Basel III)"],
    help="金管會針對台灣銀行業之自有資本計提標準，已於民國 114 年起全面導入最新版信用風險標準法。"
)

rating_agency = st.sidebar.selectbox(
    "外部信用評等機構 (ECAI) 基準",
    list(RATING_MAP.keys()),
    help="計算器會根據您選擇的評等機構，自動將其評等對應至法規規範之信用等級(1~6級)。"
)

st.sidebar.markdown("---")
st.sidebar.markdown("""
### 💡 信用風險標準法核心公式
$$\\text{RWA} = \\text{EAD} \\times \\text{RW}$$
* **EAD (表內外曝險總額)** = 表內金額 + (表外金額 × CCF)
* **RW (風險權重)** = 依資產類別及評等
* **最低資本要求** = $\\text{RWA} \\times 8\\%$
""")

# -----------------------------------------------------------------------------
# 5. 主頁面頂部
# -----------------------------------------------------------------------------
st.markdown('<div class="title-gradient">信用風險標準法適用風險權重計算器</div>', unsafe_allow_html=True)
st.markdown('<div class="subtitle">依據巴塞爾協定 III 與台灣金管會最新規範，提供單筆曝險分析、信用風險抵減（CRM）計算及批次組合評估。</div>', unsafe_allow_html=True)

# 建立功能頁籤
tabs = st.tabs(["📊 單筆曝險計量與場景分析", "📂 批次大量試算與組合分析", "📜 法規標準與評等對照表"])

# -----------------------------------------------------------------------------
# Tab 1: 單筆曝險計量與場景分析
# -----------------------------------------------------------------------------
with tabs[0]:
    st.markdown("### 🔍 曝險部位基本資料輸入")
    
    # 版面分配：左側輸入，右側即時展示結果
    col1, col2 = st.columns([3, 2])
    
    with col1:
        # 使用卡片式容器
        st.markdown('<div class="premium-card">', unsafe_allow_html=True)
        
        c1, c2 = st.columns(2)
        with c1:
            exposure_name = st.text_input("曝險項目名稱", "甲企業一般中期放款")
            exposure_category = st.selectbox(
                "曝險類別",
                ["主權國家與中央銀行", "銀行與證券商", "一般企業", "零售債權", "住宅用不動產 (RRE)", "商用不動產 (CRE)", "土地收購、開發及建築 (ADC 曝險)", "權益證券 (股權)", "其他資產"]
            )
        with c2:
            balance_sheet_type = st.radio("曝險類型", ["表內項目 (On-Balance Sheet)", "表外項目 (Off-Balance Sheet)"], horizontal=True)
            
            # 金額輸入
            exposure_amount = st.number_input(
                "表內曝光金額 (元)", 
                min_value=0.0, 
                value=10000000.0, 
                step=100000.0, 
                format="%.2f",
                help="請輸入表內放款或投資金額。"
            )
            
        # 表外細項
        ccf_val = 0.0
        off_balance_amount = 0.0
        if balance_sheet_type == "表外項目 (Off-Balance Sheet)":
            st.markdown("##### 表外項目額外參數")
            co1, co2 = st.columns(2)
            with co1:
                off_balance_amount = st.number_input("表外名目金額 (元)", min_value=0.0, value=5000000.0, step=100000.0, format="%.2f")
            with co2:
                ccf_desc = st.selectbox("信用轉換係數 (CCF)", list(CCF_RULES.keys()))
                ccf_val = CCF_RULES[ccf_desc]
                st.info(f"適用 CCF: **{ccf_val * 100:.0f}%**")
                
        st.markdown('</div>', unsafe_allow_html=True)
        
        # 根據不同的曝險類別，動態載入對應的特有參數
        st.markdown(f"### ⚙️ {exposure_category} 特有計算參數")
        st.markdown('<div class="premium-card">', unsafe_allow_html=True)
        
        details = {}
        rating_idx = 5 # 預設 Unrated
        
        if exposure_category in ["主權國家與中央銀行", "銀行與證券商", "一般企業"]:
            ce1, ce2 = st.columns(2)
            with ce1:
                rating_options = RATING_MAP[rating_agency]
                rating_selected = st.selectbox("外部信用評等", rating_options, index=5)
                rating_idx = rating_options.index(rating_selected)
                
            with ce2:
                if exposure_category == "銀行與證券商":
                    details["is_short_term"] = st.checkbox("屬短期債權 (原始期限 3 個月以下)", value=False)
                elif exposure_category == "一般企業":
                    details["is_sme"] = st.checkbox("屬合格中小企業 (SME)", value=False, help="未評等之中小企業符合特定年營收條件者，可適用較低之風險權重 (85%)")
                    
        elif exposure_category == "零售債權":
            details["retail_type"] = st.selectbox(
                "零售債權分類",
                ["合格零售債權 (適用 75% 權重)", "其他零售債權 (適用 100% 權重)"],
                help="符合分散性、金額限制（如台幣3000萬以內）及個人/小微企業性質者，為合格零售債權。"
            )
            
        elif exposure_category in ["住宅用不動產 (RRE)", "商用不動產 (CRE)"]:
            cr1, cr2 = st.columns(2)
            with cr1:
                ltv = st.slider("貸放比率 (LTV, %)", min_value=0.0, max_value=150.0, value=75.0, step=1.0, help="貸款金額 / 不動產鑑估價值")
                details["ltv"] = ltv
            with cr2:
                details["dependent_on_cash_flow"] = st.checkbox(
                    "還款來源實質依賴該不動產產生的收益 (如出租、Buy-to-Let)", 
                    value=False,
                    help="若還款來源高度依賴不動產產生的租金或處分收益，風險敏感度較高，適用較高之風險權數級距。"
                )
                
        elif exposure_category == "權益證券 (股權)":
            details["equity_type"] = st.selectbox(
                "權益證券類型",
                ["一般上市公司股權 (適用 250%)", "非上市公司股權 (適用 400%)", "投機性股權部位 (適用 400%)", "其他股權 (適用 100%)"]
            )
            
        elif exposure_category == "土地收購、開發及建築 (ADC 曝險)":
            details["adc_type"] = st.selectbox(
                "土地收購、開發及建築放款 (ADC) 細項與土地類別",
                [
                    "住宅區購地貸款 (適用 150% 風險權重)",
                    "商業區購地貸款 (適用 200% 風險權重)",
                    "建築業餘屋貸款 (適用 150% 風險權重)",
                    "工業區閒置土地抵押貸款 (適用 200% 風險權重)",
                    "一般土地收購/開發/建築放款 - 未滿足審慎條件 (適用 150% 風險權重)",
                    "一般土地收購/開發/建築放款 - 滿足審慎條件 (預售成數達標或自有權益資金達15%以上) (適用 100% 風險權重)"
                ],
                help="依據金管會與巴塞爾協定III最新規範，土地收購、開發及建築 (ADC) 曝險一般適用 150% 或 200% 較高風險權數。若能證明專案已取得高比例預售/預租，或借款人投入實質股權（達完成後估值 15% 以上），得適用 100% 優惠權數。"
            )

        elif exposure_category == "其他資產":
            details["other_asset_type"] = st.selectbox(
                "其他資產細項",
                ["一般資產 (適用 100% 權重)", "庫存現金 (適用 0% 權重)", "黃金 (適用 0% 權重)", "託收中應收現金款項 (適用 20% 權重)"]
            )
            
        # 是否逾期放款放寬
        is_past_due = st.checkbox("此筆債權已逾期 (逾期 90 天以上未清償)", value=False)
        if is_past_due:
            st.markdown("##### 逾期放款專用參數")
            cp1, cp2 = st.columns(2)
            with cp1:
                provision_ratio = st.slider("備抵呆帳提列比率 (%)", min_value=0.0, max_value=100.0, value=15.0, step=1.0, help="針對該筆逾期放款所提列的專提備抵呆帳比率")
            with cp2:
                st.info("💡 逾期放款風險權重規則：\n* 備抵呆帳 < 20%：風險權重為 150%\n* 備抵呆帳 >= 20%：風險權重為 100%")
        
        st.markdown('</div>', unsafe_allow_html=True)
        
        # 信用風險抵減 (CRM)
        st.markdown("### 🛡️ 信用風險抵減 (CRM) 設定")
        st.markdown('<div class="premium-card">', unsafe_allow_html=True)
        
        use_crm = st.checkbox("啟用信用風險抵減 (CRM)", value=False, help="透過合格擔保品或保證人降低信用風險曝險金額或轉換權重。")
        crm_method = "無"
        crm_details = {}
        
        if use_crm:
            crm_method = st.selectbox("抵減方法", ["綜合法 (Comprehensive Approach) - 折扣率法", "簡單法 (Simple Approach) - 權重替代法"])
            
            if crm_method == "綜合法 (Comprehensive Approach) - 折扣率法":
                cc1, cc2 = st.columns(2)
                with cc1:
                    collateral_type = st.selectbox("合格金融擔保品種類", list(CRM_HAIRCUTS.keys()))
                    collateral_haircut = CRM_HAIRCUTS[collateral_type]
                    st.info(f"標準折扣率 (Haircut): **{collateral_haircut * 100:.2f}%**")
                with cc2:
                    collateral_value = st.number_input("擔保品市價 (元)", min_value=0.0, value=5000000.0, step=100000.0, format="%.2f")
                    fx_mismatch = st.checkbox("曝險與擔保品存在貨幣錯配 (Currency Mismatch)", value=False, help="若兩者幣別不同，需額外加計 8% 匯率風險折扣率。")
                    
                crm_details = {
                    "collateral_value": collateral_value,
                    "collateral_haircut": collateral_haircut,
                    "fx_mismatch": fx_mismatch
                }
            else:
                cs1, cs2 = st.columns(2)
                with cs1:
                    guarantor_rw = st.number_input("保證人/擔保品適用風險權重 (%)", min_value=0.0, max_value=150.0, value=20.0, step=5.0) / 100.0
                with cs2:
                    guarantor_amount = st.number_input("受保證/足額擔保之金額 (元)", min_value=0.0, value=4000000.0, step=100000.0)
                crm_details = {
                    "guarantor_rw": guarantor_rw,
                    "guarantor_amount": guarantor_amount
                }
                
        st.markdown('</div>', unsafe_allow_html=True)

    # 右側：即時計算與動態視覺化儀表板
    with col2:
        st.markdown("### 📈 計量結果儀表板")
        
        # --- 計算邏輯核心實作 ---
        # 1. 計算 EAD (表內外合計曝光額)
        on_balance_ead = exposure_amount
        off_balance_ead = off_balance_amount * ccf_val
        total_ead = on_balance_ead + off_balance_ead
        
        # 2. 計算原始基礎風險權重
        base_rw = calculate_risk_weight(exposure_category, rating_idx, rating_agency, details)
        
        # 3. 處理逾期放款調整
        if is_past_due:
            if provision_ratio < 20.0:
                base_rw = 1.50
            else:
                base_rw = 1.00
                
        # 4. 處理 CRM 抵減
        net_ead = total_ead
        applied_rw = base_rw
        rwa = 0.0
        crm_effect_desc = ""
        
        if use_crm:
            if crm_method == "綜合法 (Comprehensive Approach) - 折扣率法":
                c_val = crm_details["collateral_value"]
                h_c = crm_details["collateral_haircut"]
                h_fx = 0.08 if crm_details["fx_mismatch"] else 0.00
                
                # 公式: E* = max(0, E * (1 + He) - C * (1 - Hc - Hfx))
                # 假設 He (曝險折扣率) 為 0 (非證券借貸交易標準情況)
                adjusted_ead = max(0.0, total_ead - c_val * (1.0 - h_c - h_fx))
                net_ead = adjusted_ead
                rwa = adjusted_ead * base_rw
                crm_effect_desc = f"使用綜合法：擔保品價值折價後為 {c_val * (1 - h_c - h_fx):,.2f} 元，調整後淨曝險額 (E*) 為 {adjusted_ead:,.2f} 元。"
                
            elif crm_method == "簡單法 (Simple Approach) - 權重替代法":
                g_amount = crm_details["guarantor_amount"]
                g_rw = crm_details["guarantor_rw"]
                
                secured_portion = min(total_ead, g_amount)
                unsecured_portion = max(0.0, total_ead - g_amount)
                
                rwa = (unsecured_portion * base_rw) + (secured_portion * g_rw)
                net_ead = total_ead
                crm_effect_desc = f"使用簡單法：保證/擔保覆蓋部分 ({secured_portion:,.2f} 元) 適用替代權重 {g_rw*100:.1f}%，剩餘部分適用原權重 {base_rw*100:.1f}%。"
        else:
            rwa = total_ead * base_rw
            
        capital_requirement = rwa * 0.08
        effective_rw = (rwa / total_ead) if total_ead > 0 else 0.0
        
        # --- 渲染結果卡片 ---
        html_card = f"""<div class="premium-card" style="background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%); color: white; border: none; padding: 24px; border-radius: 16px;">
<div class="metric-title" style="color: #94a3b8; font-size: 0.9rem; font-weight: 600; text-transform: uppercase; margin-bottom: 4px;">信用相當曝險額 (EAD)</div>
<div class="metric-value" style="color: #38bdf8; font-size: 2.2rem; font-weight: 700; line-height: 1.2;">${total_ead:,.2f}</div>
<div class="metric-sub" style="color: #cbd5e1; font-size: 0.85rem; margin-top: 6px;">表內: ${on_balance_ead:,.2f} | 表外折算: ${off_balance_ead:,.2f}</div>
<div class="divider" style="height: 1px; background: linear-gradient(to right, #38bdf8, transparent); margin: 20px 0;"></div>
<div class="metric-title" style="color: #94a3b8; font-size: 0.9rem; font-weight: 600; text-transform: uppercase; margin-bottom: 4px;">實質/平均風險權重 (Effective RW)</div>
<div class="metric-value" style="color: #f59e0b; font-size: 2.2rem; font-weight: 700; line-height: 1.2;">{effective_rw * 100:.2f}%</div>
<div class="metric-sub" style="color: #cbd5e1; font-size: 0.85rem; margin-top: 6px;">原始基礎權重: {base_rw * 100:.1f}%</div>
<div class="divider" style="height: 1px; background: linear-gradient(to right, #f59e0b, transparent); margin: 20px 0;"></div>
<div class="metric-title" style="color: #94a3b8; font-size: 0.9rem; font-weight: 600; text-transform: uppercase; margin-bottom: 4px;">風險加權資產 (RWA)</div>
<div class="metric-value" style="color: #10b981; font-size: 2.2rem; font-weight: 700; line-height: 1.2;">${rwa:,.2f}</div>
<div class="metric-sub" style="color: #cbd5e1; font-size: 0.85rem; margin-top: 6px;">最低計提資本要求 (8%): <span style="color: #34d399; font-weight: 600;">${capital_requirement:,.2f}</span></div>
</div>"""
        st.markdown(html_card, unsafe_allow_html=True)
        
        # 顯示抵減效果說明
        if use_crm:
            st.success(crm_effect_desc)
            
        # 視覺化圖表：風險權重儀表盤 / 計量對比
        st.markdown("##### 📊 資本計提敏感度分析")
        
        # 模擬場景：外部評等變動對 RWA 的影響 (若該資產與評等相關)
        if exposure_category in ["主權國家與中央銀行", "銀行與證券商", "一般企業"]:
            scenario_ratings = RATING_MAP[rating_agency]
            scenario_rwas = []
            scenario_labels = []
            
            for idx, r_label in enumerate(scenario_ratings):
                temp_rw = calculate_risk_weight(exposure_category, idx, rating_agency, details)
                if use_crm and crm_method == "綜合法 (Comprehensive Approach) - 折扣率法":
                    temp_rwa = net_ead * temp_rw
                elif use_crm and crm_method == "簡單法 (Simple Approach) - 權重替代法":
                    g_amount = crm_details["guarantor_amount"]
                    g_rw = crm_details["guarantor_rw"]
                    secured_portion = min(total_ead, g_amount)
                    unsecured_portion = max(0.0, total_ead - g_amount)
                    temp_rwa = (unsecured_portion * temp_rw) + (secured_portion * g_rw)
                else:
                    temp_rwa = total_ead * temp_rw
                scenario_rwas.append(temp_rwa)
                scenario_labels.append(r_label)
                
            fig = go.Figure()
            fig.add_trace(go.Bar(
                x=scenario_labels,
                y=scenario_rwas,
                name="RWA (元)",
                marker_color=['#3b82f6' if lbl != rating_selected else '#ef4444' for lbl in scenario_labels]
            ))
            fig.update_layout(
                title=f"評等變動對 RWA 影響分析 (紅色為當前選擇)",
                xaxis_title="信用評等",
                yaxis_title="RWA (元)",
                template="plotly_white",
                height=300,
                margin=dict(l=20, r=20, t=40, b=20)
            )
            st.plotly_chart(fig, use_container_width=True)
            
        elif exposure_category in ["住宅用不動產 (RRE)", "商用不動產 (CRE)"]:
            # 不動產：模擬 LTV 在不同比率下的風險權重變化
            ltvs = list(range(40, 121, 10))
            rws = []
            for l in ltvs:
                temp_details = details.copy()
                temp_details["ltv"] = l
                rws.append(calculate_risk_weight(exposure_category, 0, rating_agency, temp_details) * 100)
                
            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=ltvs, y=rws, 
                mode='lines+markers', 
                line=dict(color='#2563eb', width=3),
                marker=dict(size=8, color='#1d4ed8')
            ))
            # 標出目前位置
            fig.add_trace(go.Scatter(
                x=[ltv], y=[effective_rw * 100],
                mode='markers',
                marker=dict(size=12, color='#ef4444'),
                name="當前 LTV"
            ))
            fig.update_layout(
                title="LTV 比率 vs. 風險權重 (%) 曲線圖",
                xaxis_title="貸放成數 (LTV %)",
                yaxis_title="風險權重 (%)",
                template="plotly_white",
                height=300,
                margin=dict(l=20, r=20, t=40, b=20)
            )
            st.plotly_chart(fig, use_container_width=True)

# -----------------------------------------------------------------------------
# Tab 2: 批次大量試算與組合分析
# -----------------------------------------------------------------------------
with tabs[1]:
    st.markdown("### 📂 批次資產組合信用風險計算")
    st.markdown("""
    請下載範例範本填寫您的資產組合資料，並將其上傳。系統將會自動對每筆債權進行分類、套用最新風險權數，並分析整體資產組合的 RWA 及資本要求。
    """)
    
    # 建立一個模擬的範本資料
    sample_df = pd.DataFrame({
        "曝險名稱": ["A公司擔保放款", "B主權國家國庫券", "C銀行同業短期拆借", "D個人自用住宅貸款", "E新創事業無擔保融資", "F上市公司股權投資", "G市地重劃營建貸款", "H商業區土地購地貸款"],
        "曝險類別": ["一般企業", "主權國家與中央銀行", "銀行與證券商", "住宅用不動產 (RRE)", "一般企業", "權益證券 (股權)", "土地收購、開發及建築 (ADC 曝險)", "土地收購、開發及建築 (ADC 曝險)"],
        "表內金額": [50000000.0, 100000000.0, 30000000.0, 15000000.0, 10000000.0, 5000000.0, 60000000.0, 40000000.0],
        "表外金額": [0.0, 0.0, 0.0, 0.0, 2000000.0, 0.0, 10000000.0, 0.0],
        "CCF類型": ["無表外項目 (直接表內曝險)", "無表外項目 (直接表內曝險)", "無表外項目 (直接表內曝險)", "無表外項目 (直接表內曝險)", "其他承諾 (原始期限不限，非屬無條件撤銷者)", "無表外項目 (直接表內曝險)", "特定交易相關之或有債務 (如履約保證金、投標保證金)", "無表外項目 (直接表內曝險)"],
        "評等機構選擇": ["S&P / Fitch", "S&P / Fitch", "S&P / Fitch", "不適用", "S&P / Fitch", "不適用", "不適用", "不適用"],
        "外部評等": ["A+ ~ A-", "AAA ~ AA-", "A+ ~ A-", "Unrated (未評等)", "Unrated (未評等)", "Unrated (未評等)", "Unrated (未評等)", "Unrated (未評等)"],
        "短期債權(銀行專用)": [False, False, True, False, False, False, False, False],
        "合格中小企業(企業專用)": [False, False, False, False, True, False, False, False],
        "LTV成數(不動產專用)": [0.0, 0.0, 0.0, 75.0, 0.0, 0.0, 0.0, 0.0],
        "不動產收益依賴(不動產專用)": [False, False, False, False, False, False, False, False],
        "股權類型(股權專用)": ["不適用", "不適用", "不適用", "不適用", "不適用", "一般上市公司股權 (適用 250%)", "不適用", "不適用"],
        "ADC類型(ADC專用)": ["不適用", "不適用", "不適用", "不適用", "不適用", "不適用", "一般土地收購/開發/建築放款 - 未滿足審慎條件 (適用 150% 風險權重)", "商業區購地貸款 (適用 200% 風險權重)"],
        "是否逾期": [False, False, False, False, False, False, False, False],
        "逾期備抵呆帳率": [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
    })
    
    # 下載範本按鈕
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
        sample_df.to_excel(writer, sheet_name='Sheet1', index=False)
    
    st.download_button(
        label="📥 下載批次匯入範本 (Excel)",
        data=buffer.getvalue(),
        file_name="credit_risk_batch_template.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    
    st.markdown("---")
    
    # 上傳檔案
    uploaded_file = st.file_uploader("上傳填妥的資產組合試算表 (.xlsx)", type=["xlsx"])
    
    # 決定使用哪份資料（如果沒有上傳，則使用預設模擬的範本展示）
    if uploaded_file is not None:
        try:
            df = pd.read_excel(uploaded_file)
            st.success("🎉 檔案上傳成功！已讀取資產部位。")
        except Exception as e:
            st.error(f"檔案讀取失敗，請確認格式是否正確。錯誤訊息：{e}")
            df = sample_df.copy()
    else:
        st.info("💡 尚未上傳檔案，下方展示預設模擬資產組合的分析結果：")
        df = sample_df.copy()
        
    # 計算批次資料的 RWA
    results = []
    
    for idx, row in df.iterrows():
        try:
            # 解析參數
            category = row["曝險類別"]
            val_on = float(row["表內金額"])
            val_off = float(row["表外金額"])
            ccf_type = row["CCF類型"]
            agency = row["評等機構選擇"]
            rating_str = row["外部評等"]
            
            # CCF
            ccf_val = CCF_RULES.get(ccf_type, 0.0)
            ead = val_on + (val_off * ccf_val)
            
            # 評等 Index 尋找
            rating_idx = 5 # 預設 Unrated
            if agency in RATING_MAP and rating_str in RATING_MAP[agency]:
                rating_idx = RATING_MAP[agency].index(rating_str)
                
            # 細項
            details = {
                "is_short_term": bool(row.get("短期債權(銀行專用)", False)),
                "is_sme": bool(row.get("合格中小企業(企業專用)", False)),
                "ltv": float(row.get("LTV成數(不動產專用)", 0.0)),
                "dependent_on_cash_flow": bool(row.get("不動產收益依賴(不動產專用)", False)),
                "equity_type": str(row.get("股權類型(股權專用)", "一般上市公司股權 (適用 250%)")),
                "adc_type": str(row.get("ADC類型(ADC專用)", "一般土地收購/開發/建築放款 - 未滿足審慎條件 (適用 150% 風險權重)"))
            }
            
            # 基礎風險權重
            rw = calculate_risk_weight(category, rating_idx, agency, details)
            
            # 逾期處理
            is_past_due = bool(row.get("是否逾期", False))
            if is_past_due:
                prov = float(row.get("逾期備抵呆帳率", 0.0))
                rw = 1.50 if prov < 20.0 else 1.00
                
            rwa = ead * rw
            capital = rwa * 0.08
            
            results.append({
                "項次": idx + 1,
                "曝險名稱": row["曝險名稱"],
                "曝險類別": category,
                "信用評等": rating_str if category in ["主權國家與中央銀行", "銀行與證券商", "一般企業"] else "N/A",
                "EAD (元)": ead,
                "風險權重": f"{rw * 100:.1f}%",
                "RWA (元)": rwa,
                "最低計提資本要求 (元)": capital
            })
        except Exception as err:
            st.warning(f"第 {idx+1} 筆資料解析時發生不影響整體之錯誤：{err}")
            
    res_df = pd.DataFrame(results)
    
    # 組合分析儀表板指標
    total_portfolio_ead = res_df["EAD (元)"].sum()
    total_portfolio_rwa = res_df["RWA (元)"].sum()
    total_portfolio_capital = res_df["最低計提資本要求 (元)"].sum()
    weighted_rw = (total_portfolio_rwa / total_portfolio_ead) if total_portfolio_ead > 0 else 0.0
    
    m1, m2, m3, m4 = st.columns(4)
    with m1:
        st.markdown(f"""<div class="premium-card">
<div class="metric-title">組合總曝險 (EAD)</div>
<div class="metric-value">${total_portfolio_ead:,.2f}</div>
</div>""", unsafe_allow_html=True)
    with m2:
        st.markdown(f"""<div class="premium-card">
<div class="metric-title">組合總風險資產 (RWA)</div>
<div class="metric-value" style="color: #2b6cb0;">${total_portfolio_rwa:,.2f}</div>
</div>""", unsafe_allow_html=True)
    with m3:
        st.markdown(f"""<div class="premium-card">
<div class="metric-title">整體加權風險權重</div>
<div class="metric-value" style="color: #d69e2e;">{weighted_rw * 100:.2f}%</div>
</div>""", unsafe_allow_html=True)
    with m4:
        st.markdown(f"""<div class="premium-card">
<div class="metric-title">最低計提資本要求</div>
<div class="metric-value" style="color: #38a169;">${total_portfolio_capital:,.2f}</div>
</div>""", unsafe_allow_html=True)
        
    st.markdown("#### 📊 資產組合視覺化分析")
    g1, g2 = st.columns(2)
    
    with g1:
        # 圖1：各曝險類別之 RWA 分布
        cat_rwa = res_df.groupby("曝險類別")["RWA (元)"].sum().reset_index()
        fig_rwa = px.pie(
            cat_rwa, values="RWA (元)", names="曝險類別", 
            title="各類別風險加權資產 (RWA) 佔比",
            color_discrete_sequence=px.colors.qualitative.Pastel
        )
        st.plotly_chart(fig_rwa, use_container_width=True)
        
    with g2:
        # 圖2：曝險金額與 RWA 的對比
        fig_compare = go.Figure()
        fig_compare.add_trace(go.Bar(
            x=res_df["曝險名稱"], y=res_df["EAD (元)"],
            name="曝險金額 (EAD)", marker_color='#93c5fd'
        ))
        fig_compare.add_trace(go.Bar(
            x=res_df["曝險名稱"], y=res_df["RWA (元)"],
            name="風險加權資產 (RWA)", marker_color='#1d4ed8'
        ))
        fig_compare.update_layout(
            barmode='group',
            title="各單筆資產：曝險額 vs. RWA 對比",
            xaxis_title="曝險項目",
            yaxis_title="金額 (元)",
            template="plotly_white"
        )
        st.plotly_chart(fig_compare, use_container_width=True)
        
    st.markdown("#### 📋 詳細試算清單")
    st.dataframe(res_df.style.format({
        "EAD (元)": "{:,.2f}",
        "RWA (元)": "{:,.2f}",
        "最低計提資本要求 (元)": "{:,.2f}"
    }), use_container_width=True)
    
    # 匯出結果按鈕
    res_buffer = io.BytesIO()
    with pd.ExcelWriter(res_buffer, engine='openpyxl') as writer:
        res_df.to_excel(writer, sheet_name='RWA_Calculated', index=False)
        
    st.download_button(
        label="📤 匯出 RWA 計算結果 (Excel)",
        data=res_buffer.getvalue(),
        file_name="credit_risk_calculated_results.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

# -----------------------------------------------------------------------------
# Tab 3: 法規標準與評等對照表
# -----------------------------------------------------------------------------
with tabs[2]:
    st.markdown("### 📜 信用風險標準法監理參考規範")
    st.markdown("""
    本對照表係根據金管會《銀行自有資本與風險性資產之計算方法說明及表格》之第二部分「信用風險標準法」整理。
    """)
    
    st.markdown("#### 1. 外部信用評等與信用等級對照表")
    ref_rating_df = pd.DataFrame({
        "信用等級": ["第1級", "第2級", "第3級", "第4級", "第5級", "第6級"],
        "S&P / Fitch": ["AAA ~ AA-", "A+ ~ A-", "BBB+ ~ BBB-", "BB+ ~ BB-", "B+ ~ B-", "Below B-"],
        "Moody's": ["Aaa ~ Aa3", "A1 ~ A3", "Baa1 ~ Baa3", "Ba1 ~ Ba3", "B1 ~ B3", "Below B3"],
        "中華信評": ["twAAA ~ twAA-", "twA+ ~ twA-", "twBBB+ ~ twBBB-", "twBB+ ~ twBB-", "twB+ ~ twB-", "Below twB-"]
    })
    st.table(ref_rating_df)
    
    st.markdown("#### 2. 主要曝險類別風險權數對照")
    
    c_ref1, c_ref2 = st.columns(2)
    
    with c_ref1:
        st.markdown("**主權國家與中央銀行**")
        sovereign_ref = pd.DataFrame({
            "信用等級": ["第1級", "第2級", "第3級", "第4、5級", "第6級", "未評等"],
            "風險權數": ["0%", "20%", "50%", "100%", "150%", "100%"]
        })
        st.table(sovereign_ref)
        
        st.markdown("**一般企業**")
        corporate_ref = pd.DataFrame({
            "信用等級/分類": ["第1級", "第2級", "第3、4級", "第5、6級", "未評等", "合格中小企業(SME)"],
            "風險權數": ["20%", "50%", "100%", "150%", "100%", "85%"]
        })
        st.table(corporate_ref)
        
    with c_ref2:
        st.markdown("**銀行與證券商 (標準評等法)**")
        bank_ref = pd.DataFrame({
            "信用等級": ["第1級", "第2級", "第3級", "第4級", "第5級", "第6級", "未評等"],
            "一般債權權數": ["20%", "50%", "50%", "100%", "100%", "150%", "50%"],
            "短期債權權數 (<=3個月)": ["20%", "20%", "20%", "50%", "50%", "150%", "20%"]
        })
        st.table(bank_ref)
        
        st.markdown("**零售債權與其他**")
        retail_ref = pd.DataFrame({
            "分類項目": ["合格零售債權", "其他零售債權", "庫存現金/黃金", "一般股權(上市公司)", "非上市股權"],
            "風險權數": ["75%", "100%", "0%", "250%", "400%"]
        })
        st.table(retail_ref)
        
    st.markdown("#### 3. 住宅用不動產 (RRE) LTV 風險權數對照表 (Basel III 最新)")
    st.markdown("""
    依據巴塞爾協定III最新定案版本，住宅用不動產之風險權數改採**貸放成數 (LTV)** 為基準之細緻化風險敏感權數：
    """)
    
    rre_ref = pd.DataFrame({
        "貸放成數 (LTV) 級距": ["LTV <= 50%", "50% < LTV <= 60%", "60% < LTV <= 80%", "80% < LTV <= 90%", "90% < LTV <= 100%", "LTV > 100%"],
        "一般型 RRE (不賴不動產收益)": ["20%", "25%", "30%", "40%", "50%", "70%"],
        "收益型 RRE (實質依賴不動產收益)": ["30%", "35%", "45%", "60%", "75%", "105%"]
    })
    st.table(rre_ref)
    
    st.markdown("#### 4. 土地收購、開發及建築放款 (ADC 曝險) 風險權數對照表")
    st.markdown("""
    ADC (Acquisition, Development, and Construction) 曝險屬不動產放款中風險最高之類別。根據金管會與巴塞爾協定III最新規範，其風險權數計提標準如下：
    """)
    
    adc_ref = pd.DataFrame({
        "ADC 曝險細分與土地類型": [
            "住宅區購地貸款", 
            "商業區購地貸款", 
            "建築業餘屋貸款 (屬開發後未售部位)", 
            "工業區閒置土地抵押貸款",
            "一般開發與營建放款 (未滿足審慎條件)",
            "一般開發與營建放款 (滿足審慎條件 - 預售達標或自有權益資金 >= 15%)"
        ],
        "適用風險權數 (金管會/Basel III)": ["150%", "200%", "150%", "200%", "150%", "100%"]
    })
    st.table(adc_ref)
    
    st.markdown("""
    > ⚠️ **聲明與說明**：
    > 1. 本計算器為教學與試算輔助工具，實際信用加權風險資產申報金額應以銀行報經主管機關核定之系統與官方表格為準。
    > 2. 合格零售債權、合格中小企業等定義需符合金管會規範之分散性、金額限額（如對單一客戶暴險限額）等前置審查條件。
    """)
