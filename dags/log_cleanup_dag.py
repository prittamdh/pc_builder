from datetime import datetime, timedelta, timezone

MAX_LOG_AGE_IN_DAYS = 7
BASE_LOG_FOLDER = "/opt/airflow/logs"
MAX_PROCESSOR_MANAGER_LOG_BYTES = 10 * 1024 * 1024

CLEANUP_COMMAND = (
    f"find {BASE_LOG_FOLDER} -type f -mtime +{MAX_LOG_AGE_IN_DAYS} -delete && "
    f"find {BASE_LOG_FOLDER} -type d -empty -delete && "
    f"find {BASE_LOG_FOLDER}/dag_processor_manager -name 'dag_processor_manager.log' "
    f"-size +{MAX_PROCESSOR_MANAGER_LOG_BYTES}c -exec truncate -s 0 {{}} \\;"
)

try:
    from airflow import DAG
    from airflow.operators.bash import BashOperator

    default_args = {
        "owner": "pc_builder",
        "depends_on_past": False,
        "email_on_failure": False,
        "email_on_retry": False,
        "retries": 1,
        "retry_delay": timedelta(minutes=5),
    }

    dag = DAG(
        "airflow_log_cleanup",
        default_args=default_args,
        description=f"Deletes Airflow task/scheduler logs older than {MAX_LOG_AGE_IN_DAYS} days",
        schedule="@daily",
        start_date=datetime(2026, 1, 1, tzinfo=timezone.utc),
        catchup=False,
        tags=["maintenance"],
    )

    delete_old_logs_task = BashOperator(
        task_id="delete_old_logs",
        bash_command=CLEANUP_COMMAND,
        dag=dag,
    )
except ImportError:
    pass
