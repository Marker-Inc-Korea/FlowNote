WITH
categories(category) AS (
  VALUES ('SAFETY'), ('QUALITY'), ('EQUIPMENT_ANOMALY'), ('WORK_HOLD'),
         ('REWORK'), ('HANDOVER'), ('LATEST_PUBLISHED_DOCUMENT'), ('CONFLICTING_RECORDS')
),
scenarios(scenario_type) AS (VALUES ('NORMAL'), ('EXCLUSION'), ('CONFLICT')),
expected_matrix AS (
  SELECT category, scenario_type, 2 AS required FROM categories CROSS JOIN scenarios
),
dataset AS (
  SELECT c.*, p.data_classification, p.readiness_track, p.approval_status,
         p.first_approved_by, p.second_approved_by, p.source_snapshot_hash,
         p.contains_sensitive_data
  FROM ai_search_ground_truth_cases c
  JOIN ai_search_ground_truth_provenance p USING (ground_truth_case_id)
  WHERE c.case_key LIKE 'smoke48-v1-%'
),
coverage AS (
  SELECT category, scenario_type, count(*) AS actual
  FROM dataset GROUP BY category, scenario_type
),
all_references AS (
  SELECT d.ground_truth_case_id, 'EXPECTED' AS disposition, e.value AS reference
  FROM dataset d, json_each(d.expected_evidence_json) e
  UNION ALL
  SELECT d.ground_truth_case_id, 'EXCLUDED', e.value
  FROM dataset d, json_each(d.excluded_evidence_json) e
),
reference_checks AS (
  SELECT r.*,
         json_extract(reference, '$.sourceType') AS source_type,
         json_extract(reference, '$.sourceId') AS source_id,
         json_extract(reference, '$.sourceVersionId') AS source_version_id,
         json_extract(reference, '$.contentHash') AS content_hash,
         json_extract(reference, '$.rationale') AS rationale,
         CASE json_extract(reference, '$.sourceType')
           WHEN 'PUBLISHED_DOCUMENT_VERSION' THEN EXISTS (
             SELECT 1 FROM document_versions v
             WHERE v.document_id = json_extract(reference, '$.sourceId')
               AND v.version_id = json_extract(reference, '$.sourceVersionId')
           )
           WHEN 'FIELD_COMMENT' THEN EXISTS (
             SELECT 1 FROM field_comments f
             WHERE f.comment_id = json_extract(reference, '$.sourceId')
           )
           WHEN 'WORK_SEQUENCE_HISTORY' THEN EXISTS (
             SELECT 1 FROM work_sequence_change_history h
             WHERE h.change_id = json_extract(reference, '$.sourceId')
           )
           WHEN 'REPORT_SOURCE' THEN EXISTS (
             SELECT 1 FROM report_sources rs
             WHERE CAST(rs.id AS TEXT) = json_extract(reference, '$.sourceId')
           )
           ELSE 0
         END AS source_exists
  FROM all_references r
)
SELECT
  (SELECT count(*) FROM dataset) AS case_count,
  (SELECT count(*) FROM expected_matrix m LEFT JOIN coverage c USING (category, scenario_type)
   WHERE coalesce(c.actual, 0) <> m.required) AS matrix_gap_count,
  (SELECT count(*) FROM (SELECT case_key FROM dataset GROUP BY case_key HAVING count(*) <> 1)) AS duplicate_case_key_count,
  (SELECT count(*) FROM dataset WHERE approval_status <> 'APPROVED'
     OR first_approved_by = second_approved_by OR second_approved_by IS NULL) AS approval_violation_count,
  (SELECT count(*) FROM dataset WHERE data_classification NOT IN ('SYNTHETIC', 'TEST')
     OR readiness_track <> 'SMOKE_REGRESSION' OR contains_sensitive_data <> 0) AS provenance_violation_count,
  (SELECT count(*) FROM dataset WHERE length(source_snapshot_hash) <> 64) AS snapshot_hash_violation_count,
  (SELECT count(*) FROM reference_checks WHERE source_exists = 0) AS orphan_reference_count,
  (SELECT count(*) FROM reference_checks WHERE length(content_hash) <> 64) AS reference_hash_violation_count,
  (SELECT count(*) FROM reference_checks WHERE trim(coalesce(rationale, '')) = '') AS missing_rationale_count;
