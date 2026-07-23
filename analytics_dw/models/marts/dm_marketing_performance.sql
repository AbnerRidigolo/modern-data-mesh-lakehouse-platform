{#
    Performance de marketing no grão mês x categoria. Consolida investimento de
    mídia (spend), alcance (impressions), engajamento (clicks) por campanha e
    cruza com a receita comercial atribuída àquela categoria/mês para derivar as
    métricas de eficiência que uma liderança de Growth acompanha:

      - CTR  = clicks / impressions            (qualidade do criativo/segmentação)
      - CPC  = spend / clicks                   (custo de tráfego)
      - CPM  = spend / impressions * 1000       (custo de alcance)
      - ROAS = receita atribuída / spend        (retorno sobre investimento)
      - CAC  = spend / novos clientes           (custo de aquisição)

    A atribuição é do tipo "last-touch por categoria" simplificada: toda a receita
    concluída da categoria no mês é creditada ao investimento daquela categoria no
    mesmo mês. Alimenta a página de Marketing do BI.
#}

WITH marketing AS (
    SELECT
        DATE_TRUNC('month', event_date) AS activity_month,
        category,
        SUM(spend) AS spend,
        SUM(impressions) AS impressions,
        SUM(clicks) AS clicks
    FROM {{ ref('stg_marketing') }}
    GROUP BY 1, 2
),

sales_by_category AS (
    SELECT
        DATE_TRUNC('month', s.sale_date) AS activity_month,
        COALESCE(p.category, 'Sem Categoria') AS category,
        SUM(s.amount) AS attributed_revenue,
        COUNT(DISTINCT s.sale_id) AS orders,
        COUNT(DISTINCT s.customer_id) AS buyers
    FROM {{ ref('fct_sales') }} AS s
    LEFT JOIN {{ ref('dim_products') }} AS p
        ON s.product_name = p.product_name
    WHERE s.status = 'COMPLETED'
    GROUP BY 1, 2
),

joined AS (
    SELECT
        m.activity_month,
        m.category,
        m.spend,
        m.impressions,
        m.clicks,
        COALESCE(s.attributed_revenue, 0) AS attributed_revenue,
        COALESCE(s.orders, 0) AS orders,
        COALESCE(s.buyers, 0) AS buyers
    FROM marketing AS m
    LEFT JOIN sales_by_category AS s
        ON m.activity_month = s.activity_month
        AND m.category = s.category
)

SELECT
    activity_month,
    category,
    ROUND(spend, 2) AS spend,
    impressions,
    clicks,
    orders,
    buyers,
    ROUND(attributed_revenue, 2) AS attributed_revenue,
    ROUND(100.0 * clicks / NULLIF(impressions, 0), 2) AS ctr_pct,
    ROUND(spend / NULLIF(clicks, 0), 2) AS cpc,
    ROUND(1000.0 * spend / NULLIF(impressions, 0), 2) AS cpm,
    ROUND(attributed_revenue / NULLIF(spend, 0), 2) AS roas,
    ROUND(spend / NULLIF(buyers, 0), 2) AS cac,
    ROUND(100.0 * orders / NULLIF(clicks, 0), 2) AS click_to_order_pct
FROM joined
ORDER BY activity_month DESC, spend DESC
