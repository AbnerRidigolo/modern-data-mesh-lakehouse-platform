from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.python import PythonOperator

# Define the DAG
default_args = {
    'owner': 'CRM_Team',
    'depends_on_past': False,
    'start_date': datetime(2026, 1, 1),
    'email_on_failure': False,
    'email_on_retry': False,
    'retries': 1,
    'retry_delay': timedelta(minutes=1),
}

dag = DAG(
    'crm_customers_ingestion',
    default_args=default_args,
    description='Ingere dados de clientes (CRM) aplicando contratos Pydantic e salvando em Delta Lake usando Polars',
    schedule_interval=None,  # Manual trigger for demo
    catchup=False,
)

def trigger_crm_ingestion():
    # Import the function from our domains folder (which is on PYTHONPATH)
    from domains.crm.ingest import run_ingestion
    run_ingestion()

run_task = PythonOperator(
    task_id='run_crm_ingestion_with_contracts',
    python_callable=trigger_crm_ingestion,
    dag=dag,
)
