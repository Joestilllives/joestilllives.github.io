-- ============================================================
-- v2: "Held back by technology" finder
-- Expired US patents (filed 1980-2002) that depended on technology
-- that was expensive/primitive then and is cheap now, which newer
-- patents (2012+) keep citing, outside capital-heavy fields.
-- Check the size estimate (top-right) before running.
-- ============================================================
WITH candidates AS (
  SELECT
    p.publication_number, p.family_id, p.filing_date,
    (SELECT t.text FROM UNNEST(p.title_localized) t ORDER BY t.language = 'en' DESC LIMIT 1) AS title,
    (SELECT a.text FROM UNNEST(p.abstract_localized) a ORDER BY a.language = 'en' DESC LIMIT 1) AS abstract,
    (SELECT c.code FROM UNNEST(p.cpc) c WHERE c.first LIMIT 1) AS main_cpc,
    (SELECT a.name FROM UNNEST(p.assignee_harmonized) a LIMIT 1) AS owner
  FROM `patents-public-data.patents.publications` p
  WHERE p.country_code = 'US' AND p.grant_date > 0
    AND p.filing_date BETWEEN 19800101 AND 20021231
),
enabled AS (
  SELECT c.* EXCEPT (txt),
    ARRAY_TO_STRING(ARRAY(
      SELECT e.name FROM UNNEST([
        STRUCT('mobile internet' AS name, r'telephone line|phone line|modem|pager|dial-up|cellular' AS rx),
        ('cheap computing', r'microprocessor|microcontroller|personal computer'),
        ('cameras & vision', r'camera|image sensor|video|image processing'),
        ('voice AI', r'speech recogni|voice recogni|speech synth|voice synth'),
        ('AI', r'neural network|artificial intelligence|expert system|pattern recogni|fuzzy logic'),
        ('GPS', r'\bgps\b|global positioning'),
        ('batteries', r'rechargeable|lithium'),
        ('solar', r'solar|photovoltaic'),
        ('LEDs', r'\bleds?\b|light emitting diode'),
        ('sensors', r'accelerometer|gyroscope|sensor'),
        ('wireless', r'wireless|radio frequency|\brfid\b|bluetooth'),
        ('3D printing', r'stereolithograph|rapid prototyp|three-dimensional print')
      ]) e WHERE REGEXP_CONTAINS(c.txt, e.rx)), ', ') AS enablers
  FROM (
    SELECT *, LOWER(CONCAT(IFNULL(title, ''), ' ', IFNULL(abstract, ''))) AS txt
    FROM candidates
    WHERE main_cpc IS NOT NULL
      -- leave out capital-heavy / heavily regulated fields
      AND NOT REGEXP_CONTAINS(main_cpc,
        r'^(A61K|A61P|A61F2|A61B17|A61B18|A61M|A61N|C07|C08|C12|H01L|G21|B64|B63|B61|F02|F01|C10|C21|C22|E21|B01J)')
  ) c
),
cites AS (
  SELECT e.publication_number, cb.publication_number AS citing
  FROM enabled e
  JOIN `patents-public-data.google_patents_research.publications` r USING (publication_number),
  UNNEST(r.cited_by) cb
  WHERE e.enablers != ''
),
dated AS (
  SELECT c.publication_number,
    COUNT(*) AS total_citations,
    COUNTIF(d.filing_date >= 20120101) AS citations_since_2012
  FROM cites c
  JOIN (SELECT publication_number, filing_date FROM `patents-public-data.patents.publications`) d
    ON d.publication_number = c.citing
  GROUP BY 1
),
one_per_family AS (
  SELECT e.*, d.total_citations, d.citations_since_2012
  FROM enabled e JOIN dated d USING (publication_number)
  WHERE d.total_citations >= 20
  QUALIFY ROW_NUMBER() OVER (PARTITION BY e.family_id ORDER BY d.total_citations DESC) = 1
)
SELECT
  publication_number,
  DIV(filing_date, 10000) AS filing_year,
  main_cpc,
  owner,
  enablers,
  total_citations,
  citations_since_2012,
  ROUND(citations_since_2012 / total_citations, 2) AS revival_ratio,
  title,
  abstract
FROM one_per_family
QUALIFY ROW_NUMBER() OVER (PARTITION BY SUBSTR(main_cpc, 1, 4) ORDER BY citations_since_2012 DESC) <= 8
ORDER BY citations_since_2012 * (citations_since_2012 / total_citations) DESC
LIMIT 400;
