from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.operators.bash import BashOperator
from datetime import datetime, timedelta

default_args = {
    'owner': 'Analytics_Team',
    'depends_on_past': False,
    'start_date': datetime(2026, 1, 1),
    'email_on_failure': False,
    'email_on_retry': False,
    'retries': 0,
    'retry_delay': timedelta(minutes=1),
}

dag = DAG(
    'enterprise_data_mesh_pipeline',
    default_args=default_args,
    description='Pipeline orquestradora unificada (Data Mesh): Ingestão paralela CRM/E-Commerce e modelagem dbt no Data Warehouse',
    schedule_interval=None,  # Manual trigger
    catchup=False,
)

def trigger_crm():
    from domains.crm.ingest import run_ingestion
    run_ingestion()

def trigger_ecommerce():
    from domains.ecommerce.ingest import run_ingestion
    run_ingestion()

# 1. CRM Ingestion Task
crm_task = PythonOperator(
    task_id='crm_customers_ingestion',
    python_callable=trigger_crm,
    dag=dag,
)

# 2. E-Commerce Ingestion Task
ecommerce_task = PythonOperator(
    task_id='ecommerce_sales_ingestion',
    python_callable=trigger_ecommerce,
    dag=dag,
)

# 3. dbt Analytical Data Warehouse Task (Staging & Marts)
# Runs dbt build and generates documentation docs
dbt_task = BashOperator(
    task_id='dbt_warehouse_build',
    bash_command='cd /opt/airflow/analytics_dw && dbt build --profiles-dir . && dbt docs generate --profiles-dir .',
    dag=dag,
)

# 4. ML Price Elasticity & Recommender Training Task
def trigger_ml_training():
    from domains.ml_pricing.train import train_model
    train_model()

ml_task = PythonOperator(
    task_id='ml_pricing_training',
    python_callable=trigger_ml_training,
    dag=dag,
)

# 5. ML Data Drift Monitoring Task
def trigger_drift_monitoring():
    from domains.ml_pricing.drift_monitor import check_drift
    check_drift()

drift_task = PythonOperator(
    task_id='ml_pricing_drift_check',
    python_callable=trigger_drift_monitoring,
    dag=dag,
)

# Lineage & Dependency Flow
[crm_task, ecommerce_task] >> dbt_task >> [ml_task, drift_task]
