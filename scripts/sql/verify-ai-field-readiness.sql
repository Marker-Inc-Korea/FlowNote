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
),
dataset_reviews AS (
  SELECT r.*, d.snapshot_hash AS approved_snapshot_hash,
         b.dataset_snapshot_hash AS bound_snapshot_hash,
         e.status AS evaluation_status,
         e.candidate_identity_stable,
         e.ranking_stable,
         CASE WHEN json_extract(e.metrics_json, '$.case_count') = 48
                   AND json_extract(e.metrics_json, '$.passed_count') = 48
                   AND json_extract(e.metrics_json, '$.source_coverage_complete') = 1
                   AND json_extract(e.metrics_json, '$.top_k_inclusion_rate') = 1.0
                   AND json_extract(e.metrics_json, '$.citation_trace_success_rate') = 1.0
                   AND json_extract(e.metrics_json, '$.citation_semantic_match_rate') = 1.0
                   AND json_extract(e.metrics_json, '$.conflict_disclosure_rate') = 1.0
                   AND json_extract(e.metrics_json, '$.excluded_source_violation') = 0
                   AND json_extract(e.metrics_json, '$.permission_leak_violation') = 0
                   AND json_extract(e.metrics_json, '$.nonexistent_citation_violation') = 0
                   AND json_extract(e.metrics_json, '$.readiness_track') = 'FIELD_READINESS'
                   AND json_extract(e.metrics_json, '$.dataset_version_id') = d.dataset_version_id
                   AND json_extract(e.metrics_json, '$.dataset_snapshot_hash') = d.snapshot_hash
              THEN 1 ELSE 0 END AS evaluation_quality_ready
  FROM selected_dataset d
  JOIN ai_field_readiness_sample_reviews r USING (dataset_version_id)
  LEFT JOIN ai_evaluation_dataset_bindings b
    ON b.run_id = r.evaluation_run_id
   AND b.dataset_version_id = r.dataset_version_id
  LEFT JOIN ai_search_evaluation_runs e ON e.run_id = r.evaluation_run_id
),
stable_review_runs AS (
  SELECT DISTINCT reviewed.evaluation_run_id
  FROM dataset_reviews reviewed
  WHERE reviewed.evaluation_quality_ready = 1
    AND EXISTS (
      SELECT 1
      FROM ai_evaluation_dataset_bindings other_binding
      JOIN ai_search_evaluation_runs other_run
        ON other_run.run_id = other_binding.run_id
      WHERE other_binding.dataset_version_id = reviewed.dataset_version_id
        AND other_binding.dataset_snapshot_hash = reviewed.dataset_snapshot_hash
        AND other_binding.run_id <> reviewed.evaluation_run_id
        AND other_run.status = 'PASSED'
        AND other_run.candidate_identity_stable = 1
        AND other_run.ranking_stable = 1
        AND json_extract(other_run.metrics_json, '$.case_count') = 48
        AND json_extract(other_run.metrics_json, '$.passed_count') = 48
        AND json_extract(other_run.metrics_json, '$.source_coverage_complete') = 1
        AND json_extract(other_run.metrics_json, '$.top_k_inclusion_rate') = 1.0
        AND json_extract(other_run.metrics_json, '$.citation_trace_success_rate') = 1.0
        AND json_extract(other_run.metrics_json, '$.citation_semantic_match_rate') = 1.0
        AND json_extract(other_run.metrics_json, '$.conflict_disclosure_rate') = 1.0
        AND json_extract(other_run.metrics_json, '$.excluded_source_violation') = 0
        AND json_extract(other_run.metrics_json, '$.permission_leak_violation') = 0
        AND json_extract(other_run.metrics_json, '$.nonexistent_citation_violation') = 0
        AND (SELECT count(*) FROM ai_search_evaluation_cases current_case
             WHERE current_case.run_id = reviewed.evaluation_run_id) = 48
        AND NOT EXISTS (
          SELECT 1
          FROM ai_search_evaluation_cases current_case
          LEFT JOIN ai_search_evaluation_cases other_case
            ON other_case.run_id = other_binding.run_id
           AND other_case.case_key = current_case.case_key
          WHERE current_case.run_id = reviewed.evaluation_run_id
            AND (
              other_case.id IS NULL
              OR other_case.actual_evidence_json <> current_case.actual_evidence_json
              OR other_case.ranking_hash <> current_case.ranking_hash
              OR other_case.passed <> current_case.passed
            )
        )
    )
),
review_sample_coverage AS (
  SELECT r.review_id, count(j.value) AS sample_count,
         count(DISTINCT c.category || ':' || c.scenario_type) AS matrix_cell_count
  FROM dataset_reviews r
  JOIN json_each(r.sample_case_keys_json) j
  LEFT JOIN ai_ground_truth_dataset_cases sample_member
    ON sample_member.dataset_version_id = r.dataset_version_id
   AND sample_member.case_key = j.value
  LEFT JOIN ai_search_ground_truth_cases c
    ON c.ground_truth_case_id = sample_member.ground_truth_case_id
  WHERE r.review_role = 'INDEPENDENT'
  GROUP BY r.review_id
),
review_pairs AS (
  SELECT first_review.review_id AS first_review_id,
         second_review.review_id AS second_review_id,
         first_review.evaluation_run_id,
         first_review.sample_hash,
         first_review.decision_hash AS first_decision_hash,
         second_review.decision_hash AS second_decision_hash
  FROM dataset_reviews first_review
  JOIN dataset_reviews second_review
    ON second_review.evaluation_run_id = first_review.evaluation_run_id
   AND second_review.sample_hash = first_review.sample_hash
   AND second_review.id > first_review.id
  JOIN review_sample_coverage first_coverage
    ON first_coverage.review_id = first_review.review_id
  JOIN review_sample_coverage second_coverage
    ON second_coverage.review_id = second_review.review_id
  JOIN stable_review_runs stable_run
    ON stable_run.evaluation_run_id = first_review.evaluation_run_id
  WHERE first_review.review_role = 'INDEPENDENT'
    AND second_review.review_role = 'INDEPENDENT'
    AND first_review.reviewer_id <> second_review.reviewer_id
    AND first_coverage.sample_count = 24
    AND first_coverage.matrix_cell_count = 24
    AND second_coverage.sample_count = 24
    AND second_coverage.matrix_cell_count = 24
    AND first_review.dataset_snapshot_hash = first_review.approved_snapshot_hash
    AND second_review.dataset_snapshot_hash = second_review.approved_snapshot_hash
    AND first_review.bound_snapshot_hash = first_review.approved_snapshot_hash
    AND second_review.bound_snapshot_hash = second_review.approved_snapshot_hash
    AND first_review.evaluation_status = 'PASSED'
    AND second_review.evaluation_status = 'PASSED'
    AND first_review.candidate_identity_stable = 1
    AND second_review.candidate_identity_stable = 1
    AND first_review.ranking_stable = 1
    AND second_review.ranking_stable = 1
    AND first_review.evaluation_quality_ready = 1
    AND second_review.evaluation_quality_ready = 1
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
   WHERE data_classification <> 'ANONYMOUS_FIELD'
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
   )) AS expected_source_type_count,
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
   ) = 4 THEN 0 ELSE 1 END AS expected_source_balance_violation_count,
  (SELECT count(*) FROM dataset_reviews
   WHERE length(dataset_snapshot_hash) <> 64
      OR dataset_snapshot_hash <> approved_snapshot_hash
      OR bound_snapshot_hash <> approved_snapshot_hash
      OR evaluation_status <> 'PASSED'
      OR candidate_identity_stable <> 1
      OR ranking_stable <> 1
      OR evaluation_quality_ready <> 1
      OR NOT EXISTS (
        SELECT 1 FROM stable_review_runs stable_run
        WHERE stable_run.evaluation_run_id = dataset_reviews.evaluation_run_id
      )
      OR trim(coalesce(sampling_plan_reference, '')) = ''
      OR length(sample_hash) <> 64
      OR length(decision_hash) <> 64) AS sample_review_scope_violation_count,
  (SELECT count(*) FROM dataset_reviews consensus
   WHERE consensus.review_role = 'CONSENSUS'
     AND (
       consensus.review_pair_hash IS NULL
       OR consensus.resolved_review_ids_json IS NULL
       OR (SELECT count(DISTINCT value)
           FROM json_each(consensus.resolved_review_ids_json)) <> 2
       OR EXISTS (
         SELECT 1 FROM dataset_reviews independent
         WHERE independent.evaluation_run_id = consensus.evaluation_run_id
           AND independent.review_role = 'INDEPENDENT'
           AND independent.reviewer_id = consensus.reviewer_id
       )
     )) AS sample_review_actor_violation_count,
  (SELECT count(*) FROM review_pairs pair
   WHERE pair.first_decision_hash = pair.second_decision_hash
      OR EXISTS (
        SELECT 1 FROM dataset_reviews consensus
        WHERE consensus.evaluation_run_id = pair.evaluation_run_id
          AND consensus.review_role = 'CONSENSUS'
          AND consensus.sample_hash = pair.sample_hash
          AND consensus.review_pair_hash IS NOT NULL
          AND (SELECT count(*) FROM json_each(consensus.resolved_review_ids_json) ids
               WHERE ids.value IN (pair.first_review_id, pair.second_review_id)) = 2
      )) AS sample_review_complete_count,
  (SELECT count(*) FROM review_pairs pair
   WHERE pair.first_decision_hash <> pair.second_decision_hash
     AND NOT EXISTS (
       SELECT 1 FROM dataset_reviews consensus
       WHERE consensus.evaluation_run_id = pair.evaluation_run_id
         AND consensus.review_role = 'CONSENSUS'
         AND consensus.sample_hash = pair.sample_hash
         AND consensus.review_pair_hash IS NOT NULL
         AND (SELECT count(*) FROM json_each(consensus.resolved_review_ids_json) ids
              WHERE ids.value IN (pair.first_review_id, pair.second_review_id)) = 2
     )) AS sample_review_pending_disagreement_count;
