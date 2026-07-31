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
all_smoke_dataset AS (
  SELECT c.*, p.data_classification, p.readiness_track, p.approval_status,
         p.first_approved_by, p.second_approved_by, p.source_snapshot_hash,
         p.contains_sensitive_data
  FROM ai_search_ground_truth_cases c
  JOIN ai_search_ground_truth_provenance p USING (ground_truth_case_id)
  WHERE p.readiness_track = 'SMOKE_REGRESSION'
    AND p.approval_status = 'APPROVED'
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
),
all_smoke_references AS (
  SELECT d.ground_truth_case_id, 'EXPECTED' AS disposition, e.value AS reference
  FROM all_smoke_dataset d, json_each(d.expected_evidence_json) e
  UNION ALL
  SELECT d.ground_truth_case_id, 'EXCLUDED', e.value
  FROM all_smoke_dataset d, json_each(d.excluded_evidence_json) e
),
all_smoke_reference_checks AS (
  SELECT r.*,
         json_extract(reference, '$.sourceType') AS source_type,
         json_extract(reference, '$.sourceId') AS source_id,
         json_extract(reference, '$.sourceVersionId') AS source_version_id,
         json_extract(reference, '$.contentHash') AS content_hash,
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
  FROM all_smoke_references r
),
matrix_comments AS (
  SELECT * FROM field_comments
  WHERE comment_id LIKE 'comment-smoke48-v1-%'
    AND comment_id NOT LIKE 'comment-smoke48-v1-negative-%'
),
matrix_reports AS (
  SELECT * FROM reports WHERE report_id LIKE 'report-smoke48-v1-%'
),
matrix_documents AS (
  SELECT * FROM documents WHERE document_id LIKE 'doc-smoke48-v1-%'
    AND document_id NOT LIKE 'doc-smoke48-v1-negative-%'
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
  (SELECT count(*) FROM (
     SELECT customer_scope, site_scope, database_scope, coalesce(line_scope, '') AS line_scope,
            case_key, count(*) AS actual
     FROM all_smoke_dataset
     GROUP BY customer_scope, site_scope, database_scope, coalesce(line_scope, ''), case_key
     HAVING actual <> 1
   )) AS smoke_duplicate_case_key_count,
  (SELECT count(*) FROM all_smoke_dataset
   WHERE first_approved_by = second_approved_by OR second_approved_by IS NULL)
     AS smoke_approval_violation_count,
  (SELECT count(*) FROM all_smoke_dataset
   WHERE data_classification NOT IN ('SYNTHETIC', 'TEST') OR contains_sensitive_data <> 0)
     AS smoke_provenance_violation_count,
  (SELECT count(*) FROM all_smoke_dataset WHERE length(source_snapshot_hash) <> 64)
     AS smoke_snapshot_hash_violation_count,
  (SELECT count(*) FROM all_smoke_reference_checks WHERE source_exists = 0)
     AS smoke_orphan_reference_count,
  (SELECT count(*) FROM all_smoke_reference_checks WHERE length(content_hash) <> 64)
     AS smoke_reference_hash_violation_count,
  (SELECT count(*) FROM (
     SELECT f.idempotency_key, count(DISTINCT f.comment_id) AS actual
     FROM all_smoke_reference_checks r
     JOIN field_comments f ON r.source_type = 'FIELD_COMMENT' AND f.comment_id = r.source_id
     WHERE f.idempotency_key IS NOT NULL
     GROUP BY f.idempotency_key
     HAVING actual <> 1
   )) AS smoke_field_comment_idempotency_duplicate_count,
  (SELECT count(*) FROM reference_checks WHERE source_exists = 0) AS orphan_reference_count,
  (SELECT count(*) FROM reference_checks WHERE length(content_hash) <> 64) AS reference_hash_violation_count,
  (SELECT count(*) FROM reference_checks WHERE trim(coalesce(rationale, '')) = '') AS missing_rationale_count,
  (SELECT count(*) FROM (
     SELECT source_type, count(*) AS actual
     FROM reference_checks
     WHERE disposition = 'EXPECTED'
     GROUP BY source_type
     HAVING actual <> 12
   )) + CASE WHEN (
     SELECT count(DISTINCT source_type)
     FROM reference_checks
     WHERE disposition = 'EXPECTED'
   ) = 4 THEN 0 ELSE 1 END AS expected_source_balance_violation,
  abs((SELECT count(*) FROM matrix_comments) - 48) AS matrix_field_comment_count_violation,
  (SELECT count(*) FROM (
     SELECT status, count(*) AS actual FROM matrix_comments GROUP BY status
     HAVING status NOT IN ('ANALYZED', 'REVIEWED', 'SELECTED', 'EXCLUDED') OR actual < 8 OR actual > 16
   )) + CASE WHEN (SELECT count(DISTINCT status) FROM matrix_comments) = 4 THEN 0 ELSE 1 END
     AS field_comment_status_distribution_violation,
  (SELECT count(*) FROM matrix_comments
   WHERE assigned_to IS NULL OR review_due_at IS NULL OR trim(coalesce(last_transition_reason, '')) = '')
     AS field_comment_assignment_violation,
  (SELECT count(*) FROM matrix_comments f
   WHERE NOT EXISTS (
     SELECT 1 FROM activity_history a
     WHERE a.target_type = 'field_comment' AND a.target_id = f.comment_id
       AND a.event_type = 'field_comment.review_changed'
       AND length(json_extract(a.before_value, '$.source_hash_sha256')) = 64
       AND json_extract(a.before_value, '$.source_hash_sha256') = json_extract(a.after_value, '$.source_hash_sha256')
       AND trim(coalesce(a.change_reason, '')) <> ''
   )) AS field_comment_audit_hash_violation,
  (SELECT count(*) FROM matrix_comments f
   WHERE NOT EXISTS (
     SELECT 1 FROM activity_history a
     WHERE a.target_type = 'field_comment' AND a.target_id = f.comment_id
       AND a.history_id GLOB 'hist-smoke48-v1-*-[1-3]'
       AND json_extract(a.before_value, '$.review_revision') IS NOT NULL
       AND json_extract(a.after_value, '$.status') = f.status
   )) + (SELECT count(*) FROM activity_history a
     WHERE a.history_id GLOB 'hist-smoke48-v1-*-[1-3]'
       AND json_extract(a.before_value, '$.review_revision') IS NOT NULL
       AND (json_extract(a.before_value, '$.status'), json_extract(a.after_value, '$.status')) NOT IN (
         VALUES ('NEW','ANALYZED'), ('ANALYZED','REVIEWED'), ('REVIEWED','SELECTED'), ('NEW','EXCLUDED')
       )) AS field_comment_transition_path_violation,
  (SELECT count(*) FROM (
     SELECT idempotency_key FROM matrix_comments GROUP BY idempotency_key HAVING count(*) <> 1
   )) + (SELECT count(*) FROM matrix_comments WHERE idempotency_key IS NULL)
     AS field_comment_idempotency_violation,
  abs((SELECT count(*) FROM matrix_reports) - 16) AS report_count_violation,
  (SELECT count(*) FROM matrix_reports r
   WHERE (SELECT count(DISTINCT rs.source_type) FROM report_sources rs WHERE rs.report_id = r.report_id) < 2)
     AS report_source_type_violation,
  (SELECT count(*) FROM report_sources rs JOIN matrix_reports r USING (report_id)
   WHERE rs.source_version_id IS NULL OR length(rs.source_hash_sha256) <> 64 OR trim(rs.trace_id) = '')
     AS report_frozen_source_violation,
  (SELECT count(*) FROM matrix_documents d
   WHERE (SELECT count(DISTINCT td.tag_type)
          FROM document_tags dt JOIN tag_definitions td USING (tag_id)
          WHERE dt.document_id = d.document_id
            AND td.tag_type IN ('equipment', 'item', 'process', 'error_type')) < 2)
     AS domain_tag_axis_violation,
  abs((SELECT count(*) FROM ai_search_ground_truth_cases
       WHERE case_key LIKE 'sensitive-policy-regression-v1-%') - 5)
     AS policy_regression_case_count_gap,
  (SELECT count(*)
   FROM ai_search_ground_truth_cases c
   JOIN ai_search_ground_truth_provenance p USING (ground_truth_case_id)
   WHERE c.case_key LIKE 'sensitive-policy-regression-v1-%'
     AND (p.readiness_track <> 'SMOKE_REGRESSION'
          OR p.data_classification <> 'TEST'
          OR p.contains_sensitive_data <> 0))
     AS policy_regression_track_violation,
  (SELECT count(*)
   FROM ai_search_ground_truth_cases c,
        json_each(c.excluded_evidence_json) reference
   WHERE c.case_key LIKE 'sensitive-policy-regression-v1-%'
     AND (trim(coalesce(json_extract(reference.value, '$.sourceId'), '')) = ''
          OR trim(coalesce(json_extract(reference.value, '$.sourceVersionId'), '')) = ''
          OR trim(coalesce(json_extract(reference.value, '$.traceId'), '')) = ''
          OR trim(coalesce(json_extract(reference.value, '$.traceVersionId'), '')) = ''
          OR length(json_extract(reference.value, '$.contentHash')) <> 64))
     AS policy_regression_frozen_reference_violation;
