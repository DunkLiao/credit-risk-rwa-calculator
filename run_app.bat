@echo off
title 信用風險標準法計算器 - 啟動服務
echo ===================================================
echo   正在啟動信用風險標準法適用風險權重計算器...
echo ===================================================
cd /d "D:\VIbeCoding\risk_analysis"
streamlit run app.py
pause
