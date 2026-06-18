import os
import json
import requests
import pandas as pd
import streamlit as st
import time
from deltalake import DeltaTable
from datetime import datetime

# Set page configuration
st.set_page_config(
    page_title="Enterprise Data Mesh & Lakehouse Portal",
    page_icon="🕸️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# App Title & Subtitle with premium styling
st.markdown("""
<div style="background-color:#1e293b;padding:20px;border-radius:10px;margin-bottom:25px">
    <h1 style="color:#f8fafc;margin:0;font-family:'Outfit', sans-serif;">🕸️ Enterprise Data Mesh & Lakehouse</h1>
    <p style="color:#94a3b8;font-size:16px;margin:5px 0 0 0;">Portal de Governança, Observabilidade, Time Travel e Data-as-a-Service (DaaS)</p>
</div>
""", unsafe_allow_html=True)

# API endpoint URL
API_URL = os.environ.get("API_URL", "http://localhost:8000")

# Local Delta Paths
base_dir = os.path.abspath(os.path.dirname(__file__))
DELTA_PATHS = {
    "CRM Customers": os.path.join(base_dir, "storage", "lakehouse", "crm", "customers"),
    "E-Commerce Sales": os.path.join(base_dir, "storage", "lakehouse", "ecommerce", "sales")
}

# Sidebar Info
st.sidebar.markdown("### 🛠️ Status da Infraestrutura")
try:
    resp = requests.get(API_URL, timeout=2)
    if resp.status_code == 200:
        api_status = resp.json()
        st.sidebar.success("🟢 API Gateway: Ativo")
        st.sidebar.info(f"💾 DB Path: `{api_status.get('database_path')}`")
        st.sidebar.info(f"⚡ Cache: `{api_status.get('cache_type')}`")
    else:
        st.sidebar.error("🔴 API Gateway: Erro de Conexão")
except Exception:
    st.sidebar.error("🔴 API Gateway: Offline")

st.sidebar.markdown("---")
st.sidebar.markdown("""
**Arquitetura Implementada:**
- **Orquestração:** Apache Airflow
- **Processamento:** PySpark (Sales) & Polars (Customers)
- **Armazenamento:** Delta Lake (Lakehouse)
- **Modelagem:** dbt Core & DuckDB
- **Servimento:** FastAPI & Redis Cache
""")

# Create Tabs
tab1, tab2, tab3 = st.tabs([
    "📊 BI Dashboard & Performance Cache",
    "🕰️ Delta Lake Time Travel & Auditoria",
    "🕸️ Catálogo Data Mesh & Contratos"
])

# ==========================================
# TAB 1: BI Dashboard & Performance Cache
# ==========================================
with tab1:
    st.header("Dashboard de Performance & KPIs Financeiros")
    
    # Cache performance simulator
    st.subheader("⚡ Simulação de Latência & Caching")
    col_c1, col_c2 = st.columns(2)
    
    with col_c1:
        if st.button("Consultar API (Sem Caching / Forçar DB)"):
            # Clear cache first
            try:
                requests.post(f"{API_URL}/api/v1/cache/clear")
            except Exception:
                pass
                
            start = time.time()
            try:
                r = requests.get(f"{API_URL}/api/v1/kpis").json()
                lat = time.time() - start
                st.metric("Tempo de Resposta (DB)", f"{lat:.4f}s", delta="Cache Miss", delta_color="inverse")
                st.json(r)
            except Exception as e:
                st.error(f"Erro ao chamar a API: {e}. Certifique-se de que o FastAPI está rodando na porta 8000 e a pipeline foi executada.")

    with col_c2:
        if st.button("Consultar API (Com Caching / Redis)"):
            start = time.time()
            try:
                r = requests.get(f"{API_URL}/api/v1/kpis").json()
                lat = time.time() - start
                st.metric("Tempo de Resposta (Redis)", f"{lat:.4f}s", delta="Cache Hit", delta_color="normal")
                st.json(r)
            except Exception as e:
                st.error(f"Erro ao chamar a API: {e}")

    st.markdown("---")
    
    # Renders the actual dashboard if DB is ready
    st.subheader("📈 KPIs Consolidados por Mês")
    try:
        kpi_resp = requests.get(f"{API_URL}/api/v1/kpis").json()
        kpi_data = kpi_resp.get("data", [])
        
        if not kpi_data:
            st.warning("Nenhum dado KPI disponível. Execute o pipeline no Airflow primeiro.")
        else:
            df_kpis = pd.DataFrame(kpi_data)
            
            # Show Metrics Row
            latest = df_kpis.iloc[0]
            col_m1, col_m2, col_m3, col_m4 = st.columns(4)
            col_m1.metric("Mês", latest["sales_month"])
            col_m2.metric("Faturamento Líquido", f"R$ {latest['net_revenue']:,.2f}")
            col_m3.metric("Pedidos Concluídos", latest["completed_orders_count"])
            col_m4.metric("Ticket Médio", f"R$ {latest['average_ticket']:,.2f}")
            
            # Render Chart
            st.bar_chart(data=df_kpis, x="sales_month", y="net_revenue", color="#3b82f6")
            
            st.dataframe(df_kpis, use_container_width=True)
            
    except Exception:
        st.info("FastAPI Gateway Offline. Não é possível renderizar os gráficos dinâmicos.")

# ==========================================
# TAB 2: Delta Lake Time Travel & Auditoria
# ==========================================
with tab2:
    st.header("Delta Lake Time Travel Engine")
    st.markdown("""
    O Delta Lake mantém um log transacional completo (`_delta_log/`) para cada tabela.
    Abaixo, você pode **auditar o histórico de versões**, **visualizar dados no passado** e realizar um **rollback** do estado físico da tabela.
    """)
    
    selected_table = st.selectbox("Selecione o Data Product para Auditar:", list(DELTA_PATHS.keys()))
    table_path = DELTA_PATHS[selected_table]
    
    if not os.path.exists(table_path):
        st.warning(f"A tabela Delta '{selected_table}' ainda não foi criada. Execute a pipeline no Airflow.")
    else:
        # Load Delta Table
        dt = DeltaTable(table_path)
        
        # 1. Show Version History
        st.subheader("📜 Histórico de Commits (Audit Log)")
        history = dt.history()
        history_df = pd.DataFrame(history)
        
        # Select key columns to display neatly
        cols_to_show = ["version", "timestamp", "operation", "userName", "operationParameters"]
        cols_to_show = [c for c in cols_to_show if c in history_df.columns]
        
        # Format timestamps
        if "timestamp" in history_df.columns:
            history_df["timestamp"] = pd.to_datetime(history_df["timestamp"], unit='ms')
            
        st.dataframe(history_df[cols_to_show], use_container_width=True)
        
        # 2. Select Version for Time Travel
        st.subheader("🕰️ Viagem no Tempo (Time Travel Query)")
        latest_version = max([h["version"] for h in history])
        
        if latest_version > 0:
            selected_version = st.slider("Arraste para selecionar a Versão da Tabela:", 0, latest_version, latest_version)
        else:
            st.info("Apenas a versão 0 (inicial) está disponível no momento.")
            selected_version = 0
        
        st.info(f"Exibindo dados do {selected_table} na **Versão {selected_version}**:")
        
        # Load and display that specific version
        try:
            dt_version = DeltaTable(table_path, version=selected_version)
            df_version = dt_version.to_pandas()
            st.dataframe(df_version, use_container_width=True)
        except Exception as e:
            st.error(f"Erro ao ler versão: {e}")
            
        # 3. Rollback Action
        st.subheader("🚨 Ação de Recuperação (Restore / Rollback)")
        st.warning(f"Esta ação irá reverter a tabela física '{selected_table}' ao estado exato da **Versão {selected_version}**.")
        
        if st.button(f"Executar Restore para Versão {selected_version}"):
            if selected_version == latest_version:
                st.info("A tabela já está na versão selecionada.")
            else:
                with st.spinner("Realizando rollback transacional no Delta Lake..."):
                    try:
                        # Delta restore command reverts the table
                        dt.restore(selected_version)
                        st.success(f"Tabela '{selected_table}' restaurada com sucesso para a Versão {selected_version}!")
                        time.sleep(2)
                        st.rerun()
                    except Exception as e:
                        st.error(f"Erro ao executar restore: {e}")

# ==========================================
# TAB 3: Catálogo Data Mesh & Contratos
# ==========================================
with tab3:
    st.header("🕸️ Catálogo de Governança Data Mesh")
    st.markdown("""
    Em uma arquitetura Data Mesh, os domínios definem e expõem seus dados de forma documentada.
    Veja abaixo as definições dos **Data Products** ativos e o monitoramento de **Contratos de Dados (Data Quality Gates)**.
    """)
    
    col_d1, col_d2 = st.columns(2)
    
    with col_d1:
        st.markdown("""
        ### 👤 Domínio: CRM (Cadastro Clientes)
        * **Proprietário:** Equipe de Relacionamento (CRM Team)
        * **Interface:** Delta Lake Table (`storage/lakehouse/crm/customers`)
        * **Stack de Escrita:** Polars DataFrames (Rust-based)
        * **Data Contract (Pydantic Schema):**
          - `id` (int, Required, Primary Key)
          - `name` (str, Required, Min length: 2)
          - `email` (EmailStr, Required, Regex Validated)
          - `created_at` (datetime, Required)
          - `status` (str, Required, Allowed: `['active', 'inactive']`)
        """)
        
    with col_d2:
        st.markdown("""
        ### 🛒 Domínio: E-Commerce (Vendas)
        * **Proprietário:** Equipe Comercial (E-Commerce Team)
        * **Interface:** Delta Lake Table (`storage/lakehouse/ecommerce/sales`)
        * **Stack de Escrita:** Apache Spark (PySpark DataFrame API)
        * **Particionamento:** Por coluna `status` (Otimização colunar de leitura)
        * **Data Contract (Pydantic Schema):**
          - `sale_id` (int, Required, Primary Key)
          - `customer_id` (int, Required, Foreign Key)
          - `product` (str, Required, Min length: 2)
          - `amount` (float, Required, > 0.0)
          - `status` (str, Required, Allowed: `['COMPLETED', 'PENDING', 'CANCELLED']`)
          - `sale_date` (datetime, Required)
        """)

    st.markdown("---")
    st.subheader("🚨 Observabilidade de Contratos & Quarentena")
    st.markdown("""
    Quando um registro viola o contrato de dados de um domínio, ele é rejeitado em tempo de execução e enviado para a **Quarentena** para análise técnica, evitando poluir o Data Lakehouse.
    """)
    
    q_crm_path = os.path.join(base_dir, "storage", "raw", "quarantine", "crm")
    q_eco_path = os.path.join(base_dir, "storage", "raw", "quarantine", "ecommerce")
    
    col_q1, col_q2 = st.columns(2)
    
    with col_q1:
        st.markdown("#### Quarentena CRM")
        if not os.path.exists(q_crm_path) or not os.listdir(q_crm_path):
            st.success("✅ Nenhum registro em quarentena para o domínio CRM.")
        else:
            files = os.listdir(q_crm_path)
            st.error(f"⚠️ {len(files)} violações de contrato detectadas!")
            selected_err_file = st.selectbox("Selecione o erro CRM para inspecionar:", files)
            with open(os.path.join(q_crm_path, selected_err_file), "r", encoding="utf-8") as ef:
                try:
                    err_content = json.load(ef)
                    st.json(err_content)
                except Exception as e:
                    st.warning("Falha ao decodificar JSON do arquivo de erro. Exibindo conteúdo bruto:")
                    ef.seek(0)
                    st.text(ef.read())
                
    with col_q2:
        st.markdown("#### Quarentena E-Commerce")
        if not os.path.exists(q_eco_path) or not os.listdir(q_eco_path):
            st.success("✅ Nenhum registro em quarentena para o domínio E-Commerce.")
        else:
            files = os.listdir(q_eco_path)
            st.error(f"⚠️ {len(files)} violações de contrato detectadas!")
            selected_err_file = st.selectbox("Selecione o erro E-Commerce para inspecionar:", files)
            with open(os.path.join(q_eco_path, selected_err_file), "r", encoding="utf-8") as ef:
                try:
                    err_content = json.load(ef)
                    st.json(err_content)
                except Exception as e:
                    st.warning("Falha ao decodificar JSON do arquivo de erro. Exibindo conteúdo bruto:")
                    ef.seek(0)
                    st.text(ef.read())
