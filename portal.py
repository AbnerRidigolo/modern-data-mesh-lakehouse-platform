import os
import json
import requests
import pandas as pd
import numpy as np
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

def load_dbt_lineage():
    manifest_path = os.path.join(base_dir, "analytics_dw", "target", "manifest.json")
    if not os.path.exists(manifest_path):
        return None
        
    try:
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)
            
        nodes = manifest.get("nodes", {})
        
        # We want to trace models in our project (package name is 'analytics_dw')
        dag_nodes = {}
        
        # Parse standard models
        for node_id, node_info in nodes.items():
            if node_info.get("resource_type") == "model" and node_info.get("package_name") == "analytics_dw":
                name = node_info.get("name")
                depends_on = node_info.get("depends_on", {}).get("nodes", [])
                parents = []
                for p_id in depends_on:
                    if p_id.startswith("model.analytics_dw."):
                        parents.append(p_id.split(".")[-1])
                    elif p_id.startswith("source.analytics_dw."):
                        parts = p_id.split(".")
                        parents.append(f"{parts[-2]}.{parts[-1]}")
                dag_nodes[name] = parents
                
        return dag_nodes
    except Exception as e:
        st.error(f"Erro ao carregar linhagem dbt: {e}")
        return None

def render_lineage_graph(dag_nodes):
    if not dag_nodes:
        st.warning("Nenhum nó de linhagem encontrado.")
        return
        
    # DOT language graph representation
    dot = "digraph Lineage {\n"
    dot += '    graph [rankdir=LR, bgcolor="#1e293b", margin=0];\n'
    dot += '    node [fontname="Outfit", fontsize=11, shape=box, style="filled,rounded", color="#3b82f6", fillcolor="#0f172a", fontcolor="#f8fafc"];\n'
    dot += '    edge [color="#64748b", arrowhead=vee, arrowsize=0.7];\n'
    
    for name, parents in dag_nodes.items():
        if name.startswith("stg_"):
            color = "#10b981"  # green for staging
        elif name.startswith("dim_"):
            color = "#8b5cf6"  # purple for dimension
        elif name.startswith("fct_"):
            color = "#f59e0b"  # amber for fact
        elif name.startswith("ml_"):
            color = "#ec4899"  # pink for ml/feature
        else:
            color = "#3b82f6"  # blue default
            
        dot += f'    "{name}" [color="{color}", fillcolor="#0f172a", penwidth=2];\n'
        for p in parents:
            dot += f'    "{p}" -> "{name}";\n'
            
    dot += "}"
    st.graphviz_chart(dot)

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
tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "📊 BI Dashboard & Performance Cache",
    "🕰️ Delta Lake Time Travel & Auditoria",
    "🕸️ Catálogo Data Mesh & Contratos",
    "📈 MLOps: Precificação Dinâmica",
    "🔍 Busca Semântica Vetorial"
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

    st.markdown("---")
    st.subheader("📊 Linhagem de Dados Analíticos (dbt Lineage Graph)")
    st.markdown("""
    Abaixo está a linhagem de dados gerada automaticamente a partir do compilador do **dbt Core**.
    Ela ilustra o fluxo de dados desde as tabelas de staging (Delta Lake) até os marts analíticos e features de ML (DuckDB).
    """)
    
    dag_nodes = load_dbt_lineage()
    if dag_nodes is None:
        st.info("💡 Execute a pipeline no Airflow para gerar a linhagem dbt docs (`manifest.json`).")
    else:
        render_lineage_graph(dag_nodes)

# ==========================================
# TAB 4: MLOps: Precificação Dinâmica
# ==========================================
with tab4:
    st.header("📈 Otimização de Elasticidade e Precificação Dinâmica")
    st.markdown("""
    Esta tela utiliza o modelo de Machine Learning (**Random Forest Regressor**) treinado e registrado no Lakehouse para simular a resposta de demanda de cada produto e calcular o preço ideal de maximização de faturamento.
    """)
    
    metadata_path = os.path.join(base_dir, "storage", "model_registry", "pricing_metadata.json")
    model_path = os.path.join(base_dir, "storage", "model_registry", "pricing_model.joblib")
    
    if not os.path.exists(metadata_path) or not os.path.exists(model_path):
        st.warning("⚠️ O modelo de ML e os metadados de otimização ainda não foram gerados. Por favor, execute a DAG do Airflow com sucesso.")
    else:
        # Load metadata and model
        with open(metadata_path, "r", encoding="utf-8") as mf:
            metadata = json.load(mf)
            
        import joblib
        model = joblib.load(model_path)

        # Check drift status
        drift_path = os.path.join(base_dir, "storage", "model_registry", "drift_status.json")
        if os.path.exists(drift_path):
            with open(drift_path, "r", encoding="utf-8") as rf:
                drift_data = json.load(rf)
                
            if drift_data.get("overall_drift_detected", False):
                st.error("🚨 **Alerta de Drift**: Desvio estatístico significativo detectado nos preços de venda recentes! O modelo pode estar operando fora das condições ideais de treino. Recomenda-se retreinar o pipeline.")
            else:
                st.success("✅ **Drift Monitor**: Distribuições de preços recentes estão estáveis e em conformidade com os dados de treino.")
        else:
            st.info("ℹ️ Nenhum dado de monitoramento de drift gerado ainda.")

        st.markdown("---")
        
        # Display Model Metrics in premium cards
        metrics = metadata.get("model_metrics", {})
        col_t1, col_t2, col_t3 = st.columns(3)
        with col_t1:
            st.metric("Acurácia do Modelo (Test R²)", f"{metrics.get('r2_score', 0)*100:.2f}%")
        with col_t2:
            st.metric("Erro Médio Absoluto (MAE)", f"{metrics.get('mae', 0):.2f} unidades")
        with col_t3:
            trained_at = datetime.fromisoformat(metadata.get("last_trained")).strftime("%d/%m/%Y %H:%M:%S")
            st.metric("Último Retreino do Modelo", trained_at)
            
        st.markdown("---")
        
        # Product Selection
        optimal_prices = metadata.get("optimal_prices", {})
        products_list = list(optimal_prices.keys())
        selected_prod = st.selectbox("Escolha um produto para simulação e otimização:", products_list)
        
        if selected_prod:
            prod_details = optimal_prices[selected_prod]
            
            # Show optimal price details
            st.subheader(f"🎯 Recomendação de Preço Ótimo: {selected_prod}")
            col_d1, col_d2, col_d3, col_d4 = st.columns(4)
            with col_d1:
                st.metric("Preço Praticado Atual", f"R$ {prod_details['base_price']:,.2f}")
            with col_d2:
                # Calculate delta for styling
                price_delta = prod_details['optimal_price'] - prod_details['base_price']
                st.metric(
                    "Preço Ótimo Sugerido (P*)", 
                    f"R$ {prod_details['optimal_price']:,.2f}",
                    delta=f"R$ {price_delta:,.2f}" if price_delta != 0 else None
                )
            with col_d3:
                st.metric("Preço Médio Concorrente", f"R$ {prod_details['competitor_price']:,.2f}")
            with col_d4:
                st.metric(
                    "Lift Estimado de Faturamento", 
                    f"+{prod_details['revenue_lift_pct']:.2f}%",
                    delta=f"R$ {prod_details['projected_daily_revenue'] - prod_details['current_daily_revenue']:,.2f} / dia"
                )
                
            st.markdown("---")
            
            # Interactive Simulator
            st.subheader("🎮 Simulador de Preço e Demanda Interativo")
            st.markdown("Ajuste o controle deslizante abaixo para ver a demanda projetada e o faturamento simulado em tempo real.")
            
            base_price = prod_details['base_price']
            min_slider = float(max(10.0, base_price * 0.4))
            max_slider = float(base_price * 1.6)
            
            sim_price = st.slider(
                "Defina o Preço Simulado (R$):", 
                min_value=min_slider, 
                max_value=max_slider, 
                value=float(base_price), 
                step=5.0
            )
            
            is_weekend_sim = st.checkbox("Simular Vendas no Fim de Semana?")
            
            # Reconstruct the feature list and make prediction
            feature_cols = metadata["feature_columns"]
            product_cols = metadata["product_one_hot_columns"]
            
            # Prepare row for prediction
            row = {
                "price": sim_price,
                "competitor_price": prod_details['competitor_price'],
                "day_of_week": 6 if is_weekend_sim else 3,
                "is_weekend": 1 if is_weekend_sim else 0
            }
            for col in product_cols:
                row[col] = 1 if col == f"prod_{selected_prod}" else 0
                
            sim_df = pd.DataFrame([row])[feature_cols]
            sim_demand = float(model.predict(sim_df)[0])
            sim_revenue = sim_price * sim_demand
            
            # Display simulated results in columns
            col_s1, col_s2, col_s3 = st.columns(3)
            with col_s1:
                st.metric("Demanda Diária Projetada", f"{sim_demand:.2f} unidades")
            with col_s2:
                st.metric("Faturamento Diário Projetado", f"R$ {sim_revenue:,.2f}")
            with col_s3:
                current_rev = prod_details['current_daily_revenue']
                sim_lift = ((sim_revenue - current_rev) / current_rev) * 100 if current_rev > 0 else 0.0
                st.metric(
                    "Lift Comparado ao Baseline", 
                    f"{sim_lift:+.2f}%", 
                    delta=f"R$ {sim_revenue - current_rev:,.2f} / dia"
                )
                
            st.markdown("---")
            
            # Curvas de Demanda e Faturamento
            st.subheader("📊 Curvas de Elasticidade de Preço")
            
            # Generate a dense range of prices for the charts
            chart_prices = np.linspace(min_slider, max_slider, 50)
            chart_data = []
            
            for p in chart_prices:
                r_chart = {
                    "price": p,
                    "competitor_price": prod_details['competitor_price'],
                    "day_of_week": 6 if is_weekend_sim else 3,
                    "is_weekend": 1 if is_weekend_sim else 0
                }
                for col in product_cols:
                    r_chart[col] = 1 if col == f"prod_{selected_prod}" else 0
                chart_data.append(r_chart)
                
            chart_df = pd.DataFrame(chart_data)[feature_cols]
            pred_demands = model.predict(chart_df)
            pred_revenues = chart_prices * pred_demands
            
            # Combine into a dataframe for graphing
            curves_df = pd.DataFrame({
                "Preço (R$)": chart_prices,
                "Demanda Projetada (Q)": pred_demands,
                "Faturamento Projetado (R$)": pred_revenues
            }).set_index("Preço (R$)")
            
            col_g1, col_g2 = st.columns(2)
            with col_g1:
                st.markdown("**📉 Curva de Demanda (Preço vs. Quantidade Vendida)**")
                st.line_chart(curves_df["Demanda Projetada (Q)"], color="#ef4444")
            with col_g2:
                st.markdown("**💰 Curva de Receita (Preço vs. Faturamento Esperado)**")
                st.line_chart(curves_df["Faturamento Projetado (R$)"], color="#10b981")

# ==========================================
# TAB 5: Busca Semântica Vetorial
# ==========================================
with tab5:
    st.header("🔍 Busca Semântica Vetorial de Produtos")
    st.markdown("""
    Explore nosso catálogo utilizando inteligência artificial. Esta busca utiliza embeddings densos gerados pelo modelo **FastEmbed (BGE)** 
    e pesquisa por similaridade de cosseno no banco de dados vetorial **Qdrant**, permitindo encontrar produtos mesmo sem correspondência exata de palavras-chave.
    """)
    
    # ----------------------------------------------------
    # Search Analytics Expander
    # ----------------------------------------------------
    with st.expander("📊 Observabilidade & Search Analytics (Real-Time)"):
        try:
            log_resp = requests.get(f"{API_URL}/api/v1/search/logs")
            if log_resp.status_code == 200:
                logs_data = log_resp.json()
                if not logs_data:
                    st.info("Nenhuma busca registrada nos logs ainda.")
                else:
                    df_logs = pd.DataFrame(logs_data)
                    
                    # 1. Calcular Métricas
                    total_searches = len(df_logs)
                    cache_hits = len(df_logs[df_logs["source"] == "cache"])
                    hit_rate = (cache_hits / total_searches) * 100 if total_searches > 0 else 0.0
                    avg_latency = df_logs["latency_seconds"].mean()
                    
                    # Exibir Métricas em colunas
                    col_l1, col_l2, col_l3 = st.columns(3)
                    with col_l1:
                        st.metric("Total de Buscas", f"{total_searches}", help="Número total de buscas registradas em JSONL.")
                    with col_l2:
                        st.metric("Taxa de Cache Hit (Redis)", f"{hit_rate:.1f}%", delta=f"{cache_hits} acertos")
                    with col_l3:
                        st.metric("Latência Média", f"{avg_latency:.4f}s", help="Tempo médio de resposta do pipeline de busca.")
                    
                    # 2. Identificar Catalog Gaps (queries com score baixo)
                    st.markdown("### ⚠️ Catalog Gaps (Buscas sem correspondência ideal)")
                    gap_threshold = st.slider(
                        "Ajustar Limite de Similaridade Mínima para Gap (%):", 
                        min_value=0.0, 
                        max_value=1.0, 
                        value=0.60, 
                        step=0.01,
                        help="Consultas com pontuação abaixo deste limite serão marcadas como lacunas de catálogo (Catalog Gaps)."
                    )
                    gap_queries = df_logs[df_logs["top_score"] < gap_threshold]
                    if gap_queries.empty:
                        st.success(f"✅ Excelente! Todas as buscas recentes tiveram correspondência acima de {gap_threshold * 100:.1f}%.")
                    else:
                        st.warning(f"Foram detectadas {len(gap_queries)} buscas com similaridade abaixo de {gap_threshold * 100:.1f}%. Isso pode indicar demandas por produtos não mapeados.")
                        st.dataframe(
                            gap_queries[["timestamp", "query", "top_match", "top_score"]],
                            use_container_width=True
                        )
                    
                    # 3. Tabela Completa de Logs
                    st.markdown("### 📜 Histórico Recente de Buscas")
                    st.dataframe(df_logs, use_container_width=True)
            else:
                st.error("Erro ao carregar logs da API.")
        except Exception as e:
            st.error(f"Erro ao carregar search analytics: {e}")
            
    # Exemplo de buscas rápidas
    st.markdown("💡 **Buscas Sugeridas:**")
    col_sug1, col_sug2, col_sug3, col_sug4 = st.columns(4)
    suggested_query = ""
    with col_sug1:
        if st.button("🎧 Fone sem fio cancelamento ruído", use_container_width=True):
            suggested_query = "Fone sem fio cancelamento ruído"
    with col_sug2:
        if st.button("⌨️ Teclado confortável com switch brown", use_container_width=True):
            suggested_query = "Teclado confortável com switch brown"
    with col_sug3:
        if st.button("📚 Aprender modelagem dbt e airflow", use_container_width=True):
            suggested_query = "Aprender modelagem dbt e airflow"
    with col_sug4:
        if st.button("🖥️ Tela ultrawide para programar", use_container_width=True):
            suggested_query = "Tela ultrawide para programar"

    # Input da Busca
    search_query = st.text_input(
        "O que você está procurando hoje?", 
        value=suggested_query if suggested_query else "", 
        placeholder="Ex: dispositivo ergonômico para evitar dores no pulso...",
        key="main_search_input"
    )
    
    if search_query:
        st.markdown(f"### Resultados para: *\"{search_query}\"*")
        
        start_time = time.time()
        try:
            # Fazer a requisição para a nossa API
            response = requests.get(f"{API_URL}/api/v1/products/search", params={"query": search_query})
            latency = time.time() - start_time
            
            if response.status_code == 200:
                res_data = response.json()
                source = res_data.get("source", "database_qdrant")
                query_time_api = res_data.get("query_time_seconds", 0)
                products_found = res_data.get("data", [])
                
                # Exibir métricas de performance da busca
                col_perf1, col_perf2, col_perf3 = st.columns(3)
                with col_perf1:
                    st.metric(
                        "Tempo Total da Requisição", 
                        f"{latency:.4f}s", 
                        delta="Inclui rede"
                    )
                with col_perf2:
                    st.metric(
                        "Origem da Resposta", 
                        "Cache (Redis)" if source == "cache" else "Banco Vetorial (Qdrant)",
                        delta="Hit" if source == "cache" else "Miss",
                        delta_color="normal" if source == "cache" else "inverse"
                    )
                with col_perf3:
                    st.metric(
                        "Latência de Processamento API", 
                        f"{query_time_api:.4f}s"
                    )
                
                st.markdown("---")
                
                if not products_found:
                    st.warning("Nenhum produto correspondente encontrado no banco vetorial. Certifique-se de que a DAG de indexação foi executada no Airflow.")
                else:
                    for prod in products_found:
                        score = prod.get("score", 0.0)
                        score_pct = int(score * 100)
                        
                        # Criar cards estilizados premium para cada produto encontrado
                        pricing_details = prod.get("pricing_details")
                        
                        # Estilização CSS inline para o card
                        st.markdown(f"""
                        <div style="background-color:#1e293b; padding:20px; border-radius:10px; border-left: 5px solid #3b82f6; margin-bottom:20px;">
                            <div style="display:flex; justify-content:space-between; align-items:center;">
                                <h3 style="color:#f8fafc; margin:0; font-family:'Outfit', sans-serif;">{prod.get('name')}</h3>
                                <span style="background-color:#0f172a; color:#3b82f6; padding: 4px 10px; border-radius:15px; font-size:12px; font-weight:bold; border: 1px solid #3b82f6;">
                                    {prod.get('category')}
                                </span>
                            </div>
                            <p style="color:#cbd5e1; font-size:14px; margin:10px 0;">{prod.get('description')}</p>
                            <div style="margin-top:15px;">
                                <div style="display:flex; justify-content:space-between; margin-bottom:5px;">
                                    <span style="color:#94a3b8; font-size:12px;">Score de Similaridade Semântica:</span>
                                    <span style="color:#10b981; font-weight:bold; font-size:12px;">{score_pct}%</span>
                                </div>
                                <div style="background-color:#0f172a; border-radius:5px; height:8px; width:100%;">
                                    <div style="background-color:#10b981; height:8px; border-radius:5px; width:{score_pct}%;"></div>
                                </div>
                            </div>
                        </div>
                        """, unsafe_allow_html=True)
                        
                        # Se existirem informações de precificação, exibe um painel interativo de ML logo abaixo do card
                        if pricing_details:
                            col_p1, col_p2, col_p3 = st.columns(3)
                            with col_p1:
                                st.write(f"💵 **Preço Praticado:** R$ {pricing_details.get('base_price'):,.2f}")
                            with col_p2:
                                st.write(f"🎯 **Preço Ótimo (P*):** R$ {pricing_details.get('optimal_price'):,.2f}")
                            with col_p3:
                                lift = pricing_details.get('revenue_lift_pct', 0)
                                st.write(f"📈 **Lift de Faturamento:** +{lift:.2f}%")
                                
                            # Mini Simulador integrado!
                            with st.expander(f"🎮 Ajustar Preço e Simular Demanda - {prod.get('name')}"):
                                # Carregar modelo
                                metadata_path = os.path.join(base_dir, "storage", "model_registry", "pricing_metadata.json")
                                model_path = os.path.join(base_dir, "storage", "model_registry", "pricing_model.joblib")
                                
                                if os.path.exists(metadata_path) and os.path.exists(model_path):
                                    import joblib
                                    model_ml = joblib.load(model_path)
                                    with open(metadata_path, "r", encoding="utf-8") as mf:
                                        meta_ml = json.load(mf)
                                        
                                    p_base = pricing_details.get('base_price')
                                    p_slider = st.slider(
                                        "Simular Preço (R$):", 
                                        min_value=float(p_base * 0.5), 
                                        max_value=float(p_base * 1.5), 
                                        value=float(p_base), 
                                        step=5.0,
                                        key=f"slider_search_{prod.get('id')}"
                                    )
                                    
                                    feature_cols = meta_ml["feature_columns"]
                                    product_cols = meta_ml["product_one_hot_columns"]
                                    
                                    # Montar features para o modelo
                                    row_sim = {
                                        "price": p_slider,
                                        "competitor_price": pricing_details.get('base_price') * 0.98,
                                        "day_of_week": 3,
                                        "is_weekend": 0
                                    }
                                    for col in product_cols:
                                        row_sim[col] = 1 if col == f"prod_{prod.get('name')}" else 0
                                        
                                    sim_df_search = pd.DataFrame([row_sim])[feature_cols]
                                    sim_dem_search = float(model_ml.predict(sim_df_search)[0])
                                    sim_rev_search = p_slider * sim_dem_search
                                    
                                    st.write(f"📈 **Demanda projetada:** {sim_dem_search:.2f} unidades/dia")
                                    st.write(f"💰 **Faturamento projetado:** R$ {sim_rev_search:,.2f}/dia")
                                else:
                                    st.info("Treine o modelo no Airflow para ativar a simulação de elasticidade.")
                        else:
                            st.info("ℹ️ Dados de elasticidade e otimização de precificação ML indisponíveis para este item.")
                            
                        st.markdown("<br>", unsafe_allow_html=True)
            else:
                st.error(f"Erro na requisição à API: {response.text}")
        except Exception as e:
            st.error(f"Erro ao conectar com API: {e}")
