WITH source AS (
    SELECT * FROM delta_scan('{{ env_var("LAKEHOUSE_ROOT", "s3://lakehouse") }}/marketing/campaigns')
),

renamed AS (
    SELECT
        CAST(event_id AS INT) AS event_id,
        TRIM(campaign) AS campaign,
        TRIM(channel) AS channel,
        TRIM(category) AS category,
        CAST(spend AS DOUBLE) AS spend,
        CAST(impressions AS BIGINT) AS impressions,
        CAST(clicks AS BIGINT) AS clicks,
        CAST(event_date AS TIMESTAMP) AS event_date,
        -- Deduplicação defensiva por event_id (fonte append-only)
        ROW_NUMBER() OVER (PARTITION BY event_id ORDER BY event_date DESC) AS rn
    FROM source
)

SELECT
    event_id, campaign, channel, category, spend, impressions, clicks, event_date
FROM renamed
WHERE rn = 1
