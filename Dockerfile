FROM apache/airflow:2.9.2-python3.11

USER root
# Install Java JDK (required by PySpark)
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       openjdk-17-jre-headless \
    && apt-get autoremove -yqq --purge \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Set JAVA_HOME
ENV JAVA_HOME=/usr/lib/jvm/java-17-openjdk-amd64
ENV PATH="${JAVA_HOME}/bin:${PATH}"

USER airflow
# Install required libraries inside Airflow
RUN pip install --no-cache-dir \
    deltalake==0.23.0 \
    duckdb==1.1.3 \
    dbt-duckdb==1.8.3 \
    polars==1.17.1 \
    pydantic==2.10.4 \
    pyspark==3.5.3 \
    delta-spark==3.2.1 \
    redis==5.2.1 \
    scikit-learn==1.6.0 \
    joblib==1.4.2 \
    mlflow \
    scipy==1.11.4 \
    pytest==7.4.4 \
    email-validator==2.3.0 \
    qdrant-client==1.7.3 \
    fastembed==0.2.2

# Bake the pipeline code into the image so it is self-contained on Kubernetes
# (Airflow has no bind mounts there). In docker-compose the same paths are
# bind-mounted, which shadows these copies for live local development.
COPY --chown=airflow:root dags/ /opt/airflow/dags/
COPY --chown=airflow:root domains/ /opt/airflow/domains/
COPY --chown=airflow:root analytics_dw/ /opt/airflow/analytics_dw/
