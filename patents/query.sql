-- ============================================================
-- "Ahead of its time" finder — free BigQuery sandbox query
-- Finds EXPIRED US patents (public domain) in quality-of-life
-- areas whose ideas kept getting cited 15+ years after filing:
-- a sign the idea was good but the world wasn't ready.
--
-- Before running: look at the top-right of the editor. It shows
-- how much data the query will read. It should be well under
-- 1 TB (your free monthly limit). If it says more, don't run it.
-- ============================================================
WITH tagged AS (
  SELECT
    p.publication_number,
    p.filing_date,
    (SELECT t.text FROM UNNEST(p.title_localized) t ORDER BY t.language = 'en' DESC LIMIT 1) AS title,
    (SELECT a.text FROM UNNEST(p.abstract_localized) a ORDER BY a.language = 'en' DESC LIMIT 1) AS abstract,
    (SELECT STRING_AGG(DISTINCT c.code, ' ') FROM UNNEST(p.cpc) c) AS cpc_codes,
    CASE
      WHEN EXISTS (SELECT 1 FROM UNNEST(p.cpc) c WHERE STARTS_WITH(c.code, 'C02F') OR STARTS_WITH(c.code, 'E03B')) THEN 'Clean water'
      WHEN EXISTS (SELECT 1 FROM UNNEST(p.cpc) c WHERE STARTS_WITH(c.code, 'E03D') OR STARTS_WITH(c.code, 'A47K11')) THEN 'Sanitation'
      WHEN EXISTS (SELECT 1 FROM UNNEST(p.cpc) c WHERE STARTS_WITH(c.code, 'F24B') OR STARTS_WITH(c.code, 'F24C') OR STARTS_WITH(c.code, 'F24S')) THEN 'Cooking & heating'
      WHEN EXISTS (SELECT 1 FROM UNNEST(p.cpc) c WHERE STARTS_WITH(c.code, 'H02S') OR STARTS_WITH(c.code, 'F21L')) THEN 'Off-grid energy & light'
      WHEN EXISTS (SELECT 1 FROM UNNEST(p.cpc) c WHERE STARTS_WITH(c.code, 'F25D') OR STARTS_WITH(c.code, 'A23B')) THEN 'Food preservation'
      WHEN EXISTS (SELECT 1 FROM UNNEST(p.cpc) c WHERE STARTS_WITH(c.code, 'A61B5') OR STARTS_WITH(c.code, 'A61B3') OR STARTS_WITH(c.code, 'H04R25')) THEN 'Low-cost health checks'
      WHEN EXISTS (SELECT 1 FROM UNNEST(p.cpc) c WHERE STARTS_WITH(c.code, 'A61F2') OR STARTS_WITH(c.code, 'A61G5')) THEN 'Mobility & prosthetics'
      WHEN EXISTS (SELECT 1 FROM UNNEST(p.cpc) c WHERE STARTS_WITH(c.code, 'A01G25') OR STARTS_WITH(c.code, 'A01G9') OR STARTS_WITH(c.code, 'A01C')) THEN 'Small-farm agriculture'
      WHEN EXISTS (SELECT 1 FROM UNNEST(p.cpc) c WHERE STARTS_WITH(c.code, 'E04B1') OR STARTS_WITH(c.code, 'E04H9')) THEN 'Low-cost housing'
    END AS topic
  FROM `patents-public-data.patents.publications` p
  WHERE p.country_code = 'US'
    AND p.grant_date > 0                 -- granted patents only
    AND p.filing_date BETWEEN 19750101 AND 20021231   -- filed long enough ago to be expired
),
scored AS (
  SELECT
    t.*,
    IFNULL(ARRAY_LENGTH(r.cited_by), 0) AS total_citations,
    (SELECT COUNT(*) FROM UNNEST(r.cited_by) cb
       WHERE cb.filing_date >= t.filing_date + 150000) AS late_citations   -- cited 15+ years later
  FROM tagged t
  JOIN `patents-public-data.google_patents_research.publications` r
    USING (publication_number)
  WHERE t.topic IS NOT NULL
)
SELECT
  publication_number,
  topic,
  DIV(filing_date, 10000) AS filing_year,
  title,
  abstract,
  total_citations,
  late_citations,
  ROUND(SAFE_DIVIDE(late_citations, total_citations), 2) AS ahead_of_time_ratio,
  cpc_codes
FROM scored
WHERE total_citations > 0
QUALIFY ROW_NUMBER() OVER (PARTITION BY topic ORDER BY late_citations DESC, total_citations DESC) <= 40
ORDER BY topic, late_citations DESC;
