WITH
categories(category) AS (
  VALUES ('SAFETY'), ('QUALITY'), ('EQUIPMENT_ANOMALY'), ('WORK_HOLD'),
         ('REWORK'), ('HANDOVER'), ('LATEST_PUBLISHED_DOCUMENT'), ('CONFLICTING_RECORDS')
),
scenarios(scenario_type) AS (VALUES ('NORMAL'), ('EXCLUSION'), ('CONFLICT')),
expected_matrix AS (
  SELECT category, scenario_type, 2 AS required FROM categories CROSS JOIN scenarios
),
selected_dataset AS (
  SELECT d.*
  FROM ai_ground_truth_dataset_versions d, _field_readiness_verify_scope s
  WHERE d.dataset_version_id = s.dataset_version_id
),
dataset AS (
  SELECT c.*, p.data_classification, p.readiness_track AS provenance_track,
         p.approval_status, p.first_approved_by AS case_first_approved_by,
         p.second_approved_by AS case_second_approved_by,
         p.source_snapshot_hash, p.contains_sensitive_data,
         dc.snapshot_hash AS member_snapshot_hash
  FROM selected_dataset d
  JOIN ai_ground_truth_dataset_cases dc USING (dataset_version_id)
  JOIN ai_search_ground_truth_cases c USING (ground_truth_case_id)
  JOIN ai_search_ground_truth_provenance p USING (ground_truth_case_id)
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
         json_extract(reference, '$.traceId') AS trace_id,
         json_extract(reference, '$.contentHash') AS content_hash,
         json_extract(reference, '$.rationale') AS rationale,
         json_extract(reference, '$.exclusionReason') AS exclusion_reason,
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
  (SELECT count(*) FROM selected_dataset) AS dataset_count,
  (SELECT count(*) FROM dataset) AS case_count,
  (SELECT count(*) FROM selected_dataset d, _field_readiness_verify_scope s
   WHERE d.status <> 'APPROVED' OR d.readiness_track <> 'FIELD_READINESS'
      OR d.customer_scope <> s.customer_scope OR d.site_scope <> s.site_scope
      OR d.database_scope <> s.database_scope
      OR coalesce(d.line_scope, '') <> coalesce(s.line_scope, '')) AS dataset_scope_violation_count,
  (SELECT count(*) FROM selected_dataset
   WHERE author_id IS NULL OR reviewer_id IS NULL OR first_approved_by IS NULL OR second_approved_by IS NULL
      OR author_id IN (reviewer_id, first_approved_by, second_approved_by)
      OR reviewer_id IN (first_approved_by, second_approved_by)
      OR first_approved_by = second_approved_by) AS dataset_actor_separation_violation_count,
  (SELECT count(*) FROM expected_matrix m LEFT JOIN coverage c USING (category, scenario_type)
   WHERE coalesce(c.actual, 0) <> m.required) AS matrix_gap_count,
  (SELECT count(*) FROM (SELECT case_key FROM dataset GROUP BY case_key HAVING count(*) <> 1)) AS duplicate_case_key_count,
  (SELECT count(*) FROM dataset
   WHERE approval_status <> 'APPROVED' OR case_first_approved_by = case_second_approved_by
      OR case_second_approved_by IS NULL) AS case_approval_violation_count,
  (SELECT count(*) FROM dataset
   WHERE data_classification NOT IN ('ANONYMOUS_FIELD', 'PILOT')
      OR provenance_track <> 'FIELD_READINESS' OR contains_sensitive_data <> 0) AS provenance_violation_count,
  (SELECT count(*) FROM dataset
   WHERE length(source_snapshot_hash) <> 64 OR length(member_snapshot_hash) <> 64) AS snapshot_hash_violation_count,
  (SELECT count(*) FROM reference_checks WHERE source_exists = 0) AS orphan_reference_count,
  (SELECT count(*) FROM reference_checks WHERE length(content_hash) <> 64) AS reference_hash_violation_count,
  (SELECT count(*) FROM reference_checks WHERE trim(coalesce(rationale, '')) = '') AS missing_rationale_count,
  (SELECT count(*) FROM reference_checks
   WHERE disposition = 'EXCLUDED' AND trim(coalesce(exclusion_reason, '')) = '') AS missing_exclusion_reason_count,
  (SELECT count(*) FROM (
     SELECT source_type FROM reference_checks
     WHERE disposition = 'EXPECTED' GROUP BY source_type
   )) AS expected_source_type_count;
