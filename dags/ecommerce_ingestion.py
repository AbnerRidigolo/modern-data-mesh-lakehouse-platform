from airflow import DAG
from airflow.operators.python import PythonOperator
from datetime import datetime, timedelta

default_args = {
    'owner': 'ECommerce_Team',
    'depends_on_past': False,
    'start_date': datetime(2026, 1, 1),
    'email_on_failure': False,
    'email_on_retry': False,
    'retries': 1,
    'retry_delay': timedelta(minutes=1),
}

dag = DAG(
    'ecommerce_sales_ingestion',
    default_args=default_args,
    description='Ingere dados de transações de vendas aplicando contratos Pydantic e salvando em Delta Lake usando PySpark',
    schedule_interval=None,  # Manual trigger for demo
    catchup=False,
)

def trigger_ecommerce_ingestion():
    from domains.ecommerce.ingest import run_ingestion
    run_ingestion()

run_task = PythonOperator(
    task_id='run_ecommerce_spark_ingestion',
    python_callable=trigger_ecommerce_ingestion,
    dag=dag,
)
