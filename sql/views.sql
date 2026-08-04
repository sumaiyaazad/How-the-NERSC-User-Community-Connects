-- Views loaded by pipeline/load.py. 

CREATE OR REPLACE VIEW v_repo_year_metrics AS
SELECT a.repo, a.year,
       SUM(a.cpu_node_hours_charged) AS total_cpu_hours,
       SUM(a.gpu_node_hours_charged) AS total_gpu_hours,
       SUM(a.gpu_node_hours_charged) /
         NULLIF(SUM(a.cpu_node_hours_charged) + SUM(a.gpu_node_hours_charged), 0)
         AS gpu_share,
       COUNT(DISTINCT a.user_id) AS n_users,
       ANY_VALUE(a.office) AS office,
       ANY_VALUE(a.science_category) AS science_category,
       f.degree, f.weighted_degree, f.betweenness, f.pagerank,
       f.clustering, f.k_core,
       e.hours_requested, e.hours_used,
       e.gpu_requested,   e.gpu_used,
       e.storage_requested, e.storage_used,
       e.n_requests
FROM allocations a
LEFT JOIN alloc_repo_year_features f USING (repo, year)
LEFT JOIN ercap_repo_year_features e USING (repo, year)
GROUP BY a.repo, a.year,
         f.degree, f.weighted_degree, f.betweenness, f.pagerank,
         f.clustering, f.k_core,
         e.hours_requested, e.hours_used, e.gpu_requested, e.gpu_used,
         e.storage_requested, e.storage_used,
         e.n_requests;

CREATE OR REPLACE VIEW v_pi_succession AS
SELECT repo,
       COUNT(*) - 1 AS n_pi_changes,
       MIN(valid_from_year) AS first_year,
       MAX(valid_to_year)   AS last_year
FROM repo_pi_history
GROUP BY repo;

CREATE OR REPLACE VIEW v_user_office_span AS
SELECT user_id, year,
       COUNT(DISTINCT office) AS n_offices_touched,
       COUNT(DISTINCT repo)   AS n_repos
FROM allocations
GROUP BY user_id, year;

CREATE OR REPLACE VIEW v_resource_concentration AS
SELECT office, year,
       SUM(cpu_node_hours_charged) AS office_cpu,
       SUM(gpu_node_hours_charged) AS office_gpu,
       COUNT(DISTINCT repo)        AS n_repos,
       COUNT(DISTINCT user_id)     AS n_users
FROM allocations
GROUP BY office, year;

CREATE OR REPLACE VIEW v_engagement_tier AS
WITH active AS (
  SELECT user_id, year,
         SUM(cpu_node_hours_charged + gpu_node_hours_charged) AS total_hours,
         BOOL_OR(user_id = pi_user_id) AS is_pi
  FROM allocations
  GROUP BY user_id, year
),
quartiles AS (
  SELECT year,
         quantile_cont(total_hours, 0.25) AS p25,
         quantile_cont(total_hours, 0.75) AS p75
  FROM active
  WHERE total_hours > 0
  GROUP BY year
)
SELECT a.user_id, a.year, a.total_hours, a.is_pi,
       CASE
         WHEN a.total_hours = 0 THEN 'peripheral'
         WHEN a.total_hours < q.p25 THEN 'casual'
         WHEN a.total_hours < q.p75 THEN 'active'
         ELSE 'core'
       END AS tier
FROM active a JOIN quartiles q USING (year);

CREATE OR REPLACE VIEW v_active_repos AS
SELECT year, repo, COUNT(DISTINCT user_id) AS n_active_users
FROM allocations
WHERE cpu_node_hours_charged + gpu_node_hours_charged > 0
GROUP BY year, repo;
