CREATE SCHEMA public;
COMMENT ON SCHEMA public IS 'standard public schema';
CREATE TABLE public.alert_history (
    knowledge_base_id text NOT NULL,
    alert_id text NOT NULL,
    entity_id text NOT NULL,
    entity_type text NOT NULL,
    severity text NOT NULL,
    status text NOT NULL,
    title text NOT NULL,
    reasoning text NOT NULL,
    metric_name text NOT NULL,
    evidence_pack_id text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    entity_label text DEFAULT ''::text NOT NULL,
    confidence double precision DEFAULT 0 NOT NULL,
    tags jsonb DEFAULT '[]'::jsonb NOT NULL,
    assignee text,
    triage_history jsonb DEFAULT '[]'::jsonb NOT NULL,
    generation_metadata jsonb DEFAULT '{}'::jsonb NOT NULL
);
CREATE TABLE public.audit_log (
    event_id text NOT NULL,
    occurred_at timestamp with time zone NOT NULL,
    tenant_id text NOT NULL,
    knowledge_base_id text,
    actor_user_id text NOT NULL,
    actor_email text,
    actor_roles jsonb DEFAULT '[]'::jsonb NOT NULL,
    action text NOT NULL,
    resource_type text NOT NULL,
    resource_id text NOT NULL,
    before jsonb,
    after jsonb,
    correlation_id text NOT NULL,
    client_ip text,
    user_agent text,
    outcome text NOT NULL,
    failure_reason text,
    metadata jsonb DEFAULT '{}'::jsonb NOT NULL,
    CONSTRAINT ck_audit_log_outcome CHECK ((outcome = ANY (ARRAY['success'::text, 'failure'::text])))
);
CREATE TABLE public.cases (
    knowledge_base_id text NOT NULL,
    case_id text NOT NULL,
    title text NOT NULL,
    status text NOT NULL,
    priority text NOT NULL,
    assignee text,
    originating_alert_id text,
    evidence_pack_id text,
    alert_ids jsonb DEFAULT '[]'::jsonb NOT NULL,
    timeline jsonb DEFAULT '[]'::jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    feedback_history jsonb DEFAULT '[]'::jsonb NOT NULL,
    playbook_ref jsonb
);
CREATE TABLE public.connector_quarantine_records (
    quarantine_id text NOT NULL,
    run_id text NOT NULL,
    connector_id text NOT NULL,
    knowledge_base_id text NOT NULL,
    source_record_id text NOT NULL,
    reason text NOT NULL,
    raw_ref text,
    created_at timestamp with time zone NOT NULL
);
CREATE TABLE public.connector_sync_runs (
    run_id text NOT NULL,
    connector_id text NOT NULL,
    knowledge_base_id text NOT NULL,
    requested_by text NOT NULL,
    status text NOT NULL,
    counters jsonb DEFAULT '{}'::jsonb NOT NULL,
    idempotency_key text,
    ingest_correlation_id text,
    source_cursor text,
    error_message text,
    started_at timestamp with time zone NOT NULL,
    completed_at timestamp with time zone,
    updated_at timestamp with time zone NOT NULL,
    CONSTRAINT ck_connector_sync_runs_status CHECK ((status = ANY (ARRAY['queued'::text, 'running'::text, 'completed'::text, 'failed'::text, 'canceled'::text])))
);
CREATE TABLE public.connectors (
    connector_id text NOT NULL,
    knowledge_base_id text NOT NULL,
    name text NOT NULL,
    source_type text NOT NULL,
    domain_name text,
    status text NOT NULL,
    schedule_mode text NOT NULL,
    schedule_expression text,
    credentials_ref text,
    config jsonb DEFAULT '{}'::jsonb NOT NULL,
    mapping jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_at timestamp with time zone NOT NULL,
    updated_at timestamp with time zone NOT NULL,
    CONSTRAINT ck_connectors_schedule_mode CHECK ((schedule_mode = ANY (ARRAY['manual'::text, 'interval'::text, 'cron'::text]))),
    CONSTRAINT ck_connectors_source_type CHECK ((source_type = ANY (ARRAY['filesystem'::text, 'object_store'::text, 'http'::text]))),
    CONSTRAINT ck_connectors_status CHECK ((status = ANY (ARRAY['active'::text, 'disabled'::text])))
);
CREATE TABLE public.conversations (
    conversation_id text NOT NULL,
    title text NOT NULL,
    knowledge_base_id text NOT NULL,
    messages jsonb DEFAULT '[]'::jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);
CREATE TABLE public.entity_derived_signals (
    knowledge_base_id text NOT NULL,
    entity_id text NOT NULL,
    entity_type text NOT NULL,
    metric_name text NOT NULL,
    interval_start timestamp with time zone NOT NULL,
    peer_group_key text NOT NULL,
    aggregate_value double precision NOT NULL,
    peer_mean double precision NOT NULL,
    peer_std double precision NOT NULL,
    z_score double precision NOT NULL,
    signal_value double precision NOT NULL,
    weight double precision NOT NULL,
    rationale text NOT NULL,
    correlation_id text NOT NULL,
    computed_at timestamp with time zone DEFAULT now() NOT NULL
);
CREATE TABLE public.entity_metric_history (
    knowledge_base_id text NOT NULL,
    entity_id text NOT NULL,
    metric_name text NOT NULL,
    value double precision NOT NULL,
    observed_at timestamp with time zone NOT NULL,
    correlation_id text NOT NULL
);
CREATE TABLE public.entity_metrics_current (
    knowledge_base_id text NOT NULL,
    entity_id text NOT NULL,
    metric_name text NOT NULL,
    value double precision NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);
CREATE TABLE public.event_dlq (
    dlq_id text NOT NULL,
    event_type text NOT NULL,
    correlation_id text NOT NULL,
    payload jsonb NOT NULL,
    error_message text NOT NULL,
    error_traceback text NOT NULL,
    retry_count integer NOT NULL,
    failed_at timestamp with time zone NOT NULL,
    status text DEFAULT 'pending'::text NOT NULL,
    replayed_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);
CREATE TABLE public.explanation_reviews (
    id text NOT NULL,
    knowledge_base_id text NOT NULL,
    evidence_pack_id text NOT NULL,
    target_type text NOT NULL,
    target_id text NOT NULL,
    state text NOT NULL,
    reasons jsonb DEFAULT '[]'::jsonb NOT NULL,
    comment text,
    actor_user_id text NOT NULL,
    actor_email text,
    created_at timestamp with time zone NOT NULL,
    updated_at timestamp with time zone NOT NULL,
    update_count integer DEFAULT 0 NOT NULL,
    CONSTRAINT ck_explanation_reviews_state CHECK ((state = ANY (ARRAY['useful'::text, 'incomplete'::text, 'misleading'::text, 'unsupported'::text, 'approved'::text, 'rejected'::text, 'regeneration_requested'::text]))),
    CONSTRAINT ck_explanation_reviews_target_type CHECK ((target_type = ANY (ARRAY['narrative'::text, 'narrative_section'::text, 'feature_attribution'::text, 'evidence_item'::text, 'provenance_reference'::text]))),
    CONSTRAINT ck_explanation_reviews_update_count CHECK ((update_count >= 0))
);
CREATE TABLE public.fraud_playbook_snapshots (
    domain_name text NOT NULL,
    playbook_id text NOT NULL,
    version text NOT NULL,
    status text NOT NULL,
    definition jsonb NOT NULL,
    source text NOT NULL,
    published_by text NOT NULL,
    published_at timestamp with time zone NOT NULL,
    created_at timestamp with time zone NOT NULL,
    updated_at timestamp with time zone NOT NULL,
    knowledge_base_id text NOT NULL,
    CONSTRAINT ck_fraud_playbook_snapshots_source CHECK ((source = ANY (ARRAY['domain_config'::text, 'api_import'::text, 'api_publish'::text]))),
    CONSTRAINT ck_fraud_playbook_snapshots_status CHECK ((status = ANY (ARRAY['draft'::text, 'published'::text, 'retired'::text])))
);
CREATE TABLE public.governance_eval_runs (
    run_id text NOT NULL,
    knowledge_base_id text NOT NULL,
    artifact_kind text NOT NULL,
    artifact_id text NOT NULL,
    artifact_version text NOT NULL,
    baseline_version text NOT NULL,
    dataset_id text NOT NULL,
    status text NOT NULL,
    metrics jsonb NOT NULL,
    drift_summary jsonb NOT NULL,
    dataset_source_refs jsonb NOT NULL,
    affected_alert_ids jsonb NOT NULL,
    affected_case_ids jsonb NOT NULL,
    created_by text NOT NULL,
    created_at timestamp with time zone NOT NULL,
    approval jsonb,
    CONSTRAINT ck_governance_eval_runs_artifact_kind CHECK ((artifact_kind = ANY (ARRAY['connector'::text, 'model'::text, 'playbook'::text, 'prompt'::text, 'scoring'::text, 'workflow_definition'::text]))),
    CONSTRAINT ck_governance_eval_runs_status CHECK ((status = ANY (ARRAY['candidate'::text, 'approved'::text, 'rejected'::text])))
);
CREATE TABLE public.identity_links (
    id text NOT NULL,
    knowledge_base_id text NOT NULL,
    canonical_entity_id text NOT NULL,
    source_entity_id text NOT NULL,
    relationship_type text NOT NULL,
    confidence text NOT NULL,
    score double precision NOT NULL,
    review_state text NOT NULL,
    decision_source text NOT NULL,
    source_refs jsonb DEFAULT '[]'::jsonb NOT NULL,
    match_reasons jsonb DEFAULT '[]'::jsonb NOT NULL,
    decision_history jsonb DEFAULT '[]'::jsonb NOT NULL,
    created_at timestamp with time zone NOT NULL,
    updated_at timestamp with time zone NOT NULL,
    CONSTRAINT ck_identity_links_confidence CHECK ((confidence = ANY (ARRAY['high'::text, 'medium'::text, 'low'::text]))),
    CONSTRAINT ck_identity_links_decision_history_type CHECK ((jsonb_typeof(decision_history) = 'array'::text)),
    CONSTRAINT ck_identity_links_decision_history_values CHECK (((decision_history = '[]'::jsonb) OR ((jsonb_array_length(jsonb_path_query_array(decision_history, '$[*]."decision"'::jsonpath)) = jsonb_array_length(decision_history)) AND (jsonb_path_query_array(decision_history, '$[*]."decision"'::jsonpath) <@ '["approve_merge", "reject_merge", "split_identity"]'::jsonb)))),
    CONSTRAINT ck_identity_links_review_state CHECK ((review_state = ANY (ARRAY['auto_linkable'::text, 'steward_review'::text, 'needs_review'::text, 'merged'::text, 'rejected'::text, 'split'::text]))),
    CONSTRAINT ck_identity_links_score CHECK (((score >= (0)::double precision) AND (score <= (1)::double precision)))
);
CREATE TABLE public.observations (
    knowledge_base_id text NOT NULL,
    entity_id text NOT NULL,
    entity_type text NOT NULL,
    metric_name text NOT NULL,
    score double precision NOT NULL,
    observed_at timestamp with time zone NOT NULL,
    rationale text NOT NULL,
    evidence_pack_id text,
    batch_id text NOT NULL,
    correlation_id text NOT NULL
);
CREATE TABLE public.policy_items (
    knowledge_base_id text NOT NULL,
    rule_id text NOT NULL,
    target_ref text NOT NULL,
    item_id text NOT NULL,
    rule_pack_id text NOT NULL,
    target_kind text NOT NULL,
    title text NOT NULL,
    severity text NOT NULL,
    matched_fields jsonb DEFAULT '{}'::jsonb NOT NULL,
    citations jsonb DEFAULT '[]'::jsonb NOT NULL,
    status text NOT NULL,
    disposition jsonb,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);
CREATE TABLE public.raw_records (
    knowledge_base_id text NOT NULL,
    record_type text NOT NULL,
    record_id text NOT NULL,
    payload jsonb NOT NULL,
    source_type text NOT NULL,
    source_ref text,
    correlation_id text NOT NULL,
    content_hash text NOT NULL,
    ingested_at timestamp with time zone DEFAULT now() NOT NULL
);
CREATE TABLE public.record_submissions (
    knowledge_base_id text NOT NULL,
    submission_hash text NOT NULL,
    correlation_id text NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);
CREATE TABLE public.risk_projections (
    knowledge_base_id text NOT NULL,
    entity_id text NOT NULL,
    entity_type text NOT NULL,
    overall_score double precision NOT NULL,
    risk_level text NOT NULL,
    top_typology_ids jsonb DEFAULT '[]'::jsonb NOT NULL,
    alert_ids jsonb DEFAULT '[]'::jsonb NOT NULL,
    case_ids jsonb DEFAULT '[]'::jsonb NOT NULL,
    evidence_pack_ids jsonb DEFAULT '[]'::jsonb NOT NULL,
    score_run_id text,
    model_version text NOT NULL,
    catalog_version text NOT NULL,
    scored_at timestamp with time zone NOT NULL,
    updated_at timestamp with time zone NOT NULL,
    status text NOT NULL
);
CREATE TABLE public.risk_score_history (
    knowledge_base_id text NOT NULL,
    entity_id text NOT NULL,
    request_id text NOT NULL,
    overall_score double precision NOT NULL,
    risk_level text NOT NULL,
    factors jsonb NOT NULL,
    assessed_at timestamp with time zone DEFAULT now() NOT NULL
);
CREATE TABLE public.score_batches (
    id text NOT NULL,
    run_id text NOT NULL,
    knowledge_base_id text NOT NULL,
    batch_number integer NOT NULL,
    status text NOT NULL,
    entity_ids jsonb DEFAULT '[]'::jsonb NOT NULL,
    scored_entities integer DEFAULT 0 NOT NULL,
    failed_entities integer DEFAULT 0 NOT NULL,
    attempts integer DEFAULT 0 NOT NULL,
    error_summary text,
    created_at timestamp with time zone NOT NULL,
    updated_at timestamp with time zone NOT NULL,
    started_at timestamp with time zone,
    finished_at timestamp with time zone,
    CONSTRAINT ck_score_batches_status CHECK ((status = ANY (ARRAY['queued'::text, 'running'::text, 'completed'::text, 'failed'::text, 'canceled'::text, 'replayed'::text])))
);
CREATE TABLE public.score_runs (
    id text NOT NULL,
    knowledge_base_id text NOT NULL,
    status text NOT NULL,
    requested_by text,
    idempotency_key text,
    model_version text NOT NULL,
    catalog_version text NOT NULL,
    replay_of_run_id text,
    entity_cursor text,
    total_entities integer DEFAULT 0 NOT NULL,
    scored_entities integer DEFAULT 0 NOT NULL,
    failed_entities integer DEFAULT 0 NOT NULL,
    error_summary text,
    created_at timestamp with time zone NOT NULL,
    updated_at timestamp with time zone NOT NULL,
    started_at timestamp with time zone,
    finished_at timestamp with time zone,
    CONSTRAINT ck_score_runs_status CHECK ((status = ANY (ARRAY['queued'::text, 'running'::text, 'completed'::text, 'failed'::text, 'canceled'::text, 'replayed'::text])))
);
CREATE TABLE public.scorecard_runs (
    knowledge_base_id text NOT NULL,
    run_id text NOT NULL,
    template_id text NOT NULL,
    template_name text NOT NULL,
    scope_type text NOT NULL,
    scope_id text NOT NULL,
    period_start date NOT NULL,
    period_end date NOT NULL,
    source_snapshot_hash text NOT NULL,
    status text NOT NULL,
    overall_health text NOT NULL,
    sections jsonb NOT NULL,
    export_payloads jsonb NOT NULL,
    created_at timestamp with time zone NOT NULL,
    updated_at timestamp with time zone NOT NULL
);
CREATE TABLE public.source_document_status (
    knowledge_base_id text NOT NULL,
    source_document_id text NOT NULL,
    current_status text NOT NULL,
    status_rank integer NOT NULL,
    last_error text,
    dropped_entity_count integer DEFAULT 0 NOT NULL,
    dropped_relationship_count integer DEFAULT 0 NOT NULL,
    sample_reasons jsonb DEFAULT '[]'::jsonb NOT NULL,
    first_event_at timestamp with time zone NOT NULL,
    updated_at timestamp with time zone NOT NULL
);
CREATE TABLE public.timeseries_anomalies (
    knowledge_base_id text NOT NULL,
    entity_id text NOT NULL,
    metric_name text NOT NULL,
    observed_at timestamp with time zone NOT NULL,
    observed_value double precision NOT NULL,
    expected_value double precision NOT NULL,
    z_score double precision NOT NULL,
    severity double precision NOT NULL,
    detection_strategy text NOT NULL,
    correlation_id text NOT NULL,
    detected_at timestamp with time zone DEFAULT now() NOT NULL
);
CREATE TABLE public.workflow_definition_snapshots (
    snapshot_id text NOT NULL,
    knowledge_base_id text NOT NULL,
    domain_name text,
    definition_id text NOT NULL,
    version text NOT NULL,
    status text NOT NULL,
    name text NOT NULL,
    description text,
    allowed_capability_refs jsonb NOT NULL,
    steps jsonb NOT NULL,
    created_by text NOT NULL,
    approved_by text,
    created_at timestamp with time zone NOT NULL,
    updated_at timestamp with time zone NOT NULL,
    approved_at timestamp with time zone,
    retired_at timestamp with time zone,
    CONSTRAINT ck_workflow_definition_snapshots_status CHECK ((status = ANY (ARRAY['draft'::text, 'approved'::text, 'retired'::text])))
);
ALTER TABLE ONLY public.alert_history
    ADD CONSTRAINT alert_history_pkey PRIMARY KEY (knowledge_base_id, alert_id);
ALTER TABLE ONLY public.audit_log
    ADD CONSTRAINT audit_log_pkey PRIMARY KEY (event_id);
ALTER TABLE ONLY public.cases
    ADD CONSTRAINT cases_pkey PRIMARY KEY (knowledge_base_id, case_id);
ALTER TABLE ONLY public.connector_quarantine_records
    ADD CONSTRAINT connector_quarantine_records_pkey PRIMARY KEY (quarantine_id);
ALTER TABLE ONLY public.connector_sync_runs
    ADD CONSTRAINT connector_sync_runs_pkey PRIMARY KEY (run_id);
ALTER TABLE ONLY public.connectors
    ADD CONSTRAINT connectors_pkey PRIMARY KEY (connector_id);
ALTER TABLE ONLY public.conversations
    ADD CONSTRAINT conversations_pkey PRIMARY KEY (conversation_id);
ALTER TABLE ONLY public.entity_derived_signals
    ADD CONSTRAINT entity_derived_signals_pkey PRIMARY KEY (knowledge_base_id, entity_id, metric_name, interval_start);
ALTER TABLE ONLY public.entity_metric_history
    ADD CONSTRAINT entity_metric_history_pkey PRIMARY KEY (knowledge_base_id, entity_id, metric_name, observed_at);
ALTER TABLE ONLY public.entity_metrics_current
    ADD CONSTRAINT entity_metrics_current_pkey PRIMARY KEY (knowledge_base_id, entity_id, metric_name);
ALTER TABLE ONLY public.event_dlq
    ADD CONSTRAINT event_dlq_pkey PRIMARY KEY (dlq_id);
ALTER TABLE ONLY public.explanation_reviews
    ADD CONSTRAINT explanation_reviews_pkey PRIMARY KEY (id);
ALTER TABLE ONLY public.governance_eval_runs
    ADD CONSTRAINT governance_eval_runs_pkey PRIMARY KEY (run_id);
ALTER TABLE ONLY public.observations
    ADD CONSTRAINT observations_pkey PRIMARY KEY (knowledge_base_id, entity_id, metric_name, observed_at);
ALTER TABLE ONLY public.fraud_playbook_snapshots
    ADD CONSTRAINT pk_fraud_playbook_snapshots PRIMARY KEY (knowledge_base_id, domain_name, playbook_id, version);
ALTER TABLE ONLY public.identity_links
    ADD CONSTRAINT pk_identity_links PRIMARY KEY (knowledge_base_id, id);
ALTER TABLE ONLY public.policy_items
    ADD CONSTRAINT policy_items_pkey PRIMARY KEY (knowledge_base_id, rule_id, target_ref);
ALTER TABLE ONLY public.raw_records
    ADD CONSTRAINT raw_records_pkey PRIMARY KEY (knowledge_base_id, record_type, record_id);
ALTER TABLE ONLY public.record_submissions
    ADD CONSTRAINT record_submissions_pkey PRIMARY KEY (knowledge_base_id, submission_hash);
ALTER TABLE ONLY public.risk_projections
    ADD CONSTRAINT risk_projections_pkey PRIMARY KEY (knowledge_base_id, entity_id);
ALTER TABLE ONLY public.risk_score_history
    ADD CONSTRAINT risk_score_history_pkey PRIMARY KEY (request_id);
ALTER TABLE ONLY public.score_batches
    ADD CONSTRAINT score_batches_pkey PRIMARY KEY (id);
ALTER TABLE ONLY public.score_batches
    ADD CONSTRAINT score_batches_run_id_batch_number_key UNIQUE (run_id, batch_number);
ALTER TABLE ONLY public.score_runs
    ADD CONSTRAINT score_runs_pkey PRIMARY KEY (id);
ALTER TABLE ONLY public.scorecard_runs
    ADD CONSTRAINT scorecard_runs_knowledge_base_id_template_id_scope_type_sco_key UNIQUE (knowledge_base_id, template_id, scope_type, scope_id, period_start, period_end, source_snapshot_hash);
ALTER TABLE ONLY public.scorecard_runs
    ADD CONSTRAINT scorecard_runs_pkey PRIMARY KEY (knowledge_base_id, run_id);
ALTER TABLE ONLY public.source_document_status
    ADD CONSTRAINT source_document_status_pkey PRIMARY KEY (knowledge_base_id, source_document_id);
ALTER TABLE ONLY public.timeseries_anomalies
    ADD CONSTRAINT timeseries_anomalies_pkey PRIMARY KEY (knowledge_base_id, entity_id, metric_name, observed_at);
ALTER TABLE ONLY public.explanation_reviews
    ADD CONSTRAINT uq_explanation_reviews_target UNIQUE (knowledge_base_id, evidence_pack_id, target_type, target_id);
ALTER TABLE ONLY public.workflow_definition_snapshots
    ADD CONSTRAINT uq_workflow_definition_snapshots_natural_key UNIQUE (knowledge_base_id, definition_id, version);
ALTER TABLE ONLY public.workflow_definition_snapshots
    ADD CONSTRAINT workflow_definition_snapshots_pkey PRIMARY KEY (snapshot_id);
CREATE INDEX entity_metric_history_observed_at_idx ON public.entity_metric_history USING btree (observed_at DESC);
CREATE INDEX ix_alert_history_entity ON public.alert_history USING btree (knowledge_base_id, entity_id, created_at DESC);
CREATE INDEX ix_alert_history_kb_assignee ON public.alert_history USING btree (knowledge_base_id, assignee, updated_at DESC);
CREATE INDEX ix_audit_log_actor_occurred_at ON public.audit_log USING btree (actor_user_id, occurred_at DESC);
CREATE INDEX ix_audit_log_kb_occurred_at ON public.audit_log USING btree (knowledge_base_id, occurred_at DESC);
CREATE INDEX ix_audit_log_tenant_occurred_at ON public.audit_log USING btree (tenant_id, occurred_at DESC);
CREATE INDEX ix_cases_status ON public.cases USING btree (knowledge_base_id, status, updated_at DESC);
CREATE INDEX ix_connector_quarantine_connector ON public.connector_quarantine_records USING btree (connector_id, created_at DESC);
CREATE INDEX ix_connector_quarantine_run ON public.connector_quarantine_records USING btree (run_id, created_at DESC);
CREATE INDEX ix_connector_sync_runs_connector_status ON public.connector_sync_runs USING btree (connector_id, status, started_at DESC);
CREATE INDEX ix_connectors_kb ON public.connectors USING btree (knowledge_base_id, status, updated_at DESC);
CREATE INDEX ix_conversations_kb ON public.conversations USING btree (knowledge_base_id, updated_at DESC);
CREATE INDEX ix_entity_derived_signals_latest ON public.entity_derived_signals USING btree (knowledge_base_id, entity_id, metric_name, computed_at DESC);
CREATE INDEX ix_entity_metric_history_metric_range ON public.entity_metric_history USING btree (knowledge_base_id, metric_name, observed_at);
CREATE INDEX ix_event_dlq_status_created ON public.event_dlq USING btree (status, created_at DESC);
CREATE INDEX ix_explanation_reviews_kb_pack_updated ON public.explanation_reviews USING btree (knowledge_base_id, evidence_pack_id, updated_at DESC);
CREATE INDEX ix_explanation_reviews_kb_state_updated ON public.explanation_reviews USING btree (knowledge_base_id, state, updated_at DESC);
CREATE INDEX ix_fraud_playbook_snapshots_domain_status ON public.fraud_playbook_snapshots USING btree (knowledge_base_id, domain_name, status, updated_at DESC);
CREATE INDEX ix_governance_eval_runs_artifact ON public.governance_eval_runs USING btree (knowledge_base_id, artifact_kind, artifact_id, artifact_version);
CREATE INDEX ix_governance_eval_runs_kb_status ON public.governance_eval_runs USING btree (knowledge_base_id, status, created_at DESC);
CREATE INDEX ix_identity_links_kb_canonical_updated ON public.identity_links USING btree (knowledge_base_id, canonical_entity_id, updated_at DESC);
CREATE INDEX ix_identity_links_kb_review_state_updated ON public.identity_links USING btree (knowledge_base_id, review_state, updated_at DESC);
CREATE INDEX ix_identity_links_kb_source_updated ON public.identity_links USING btree (knowledge_base_id, source_entity_id, updated_at DESC);
CREATE INDEX ix_observations_batch ON public.observations USING btree (knowledge_base_id, batch_id);
CREATE INDEX ix_policy_items_status ON public.policy_items USING btree (knowledge_base_id, status, updated_at DESC);
CREATE INDEX ix_raw_records_correlation ON public.raw_records USING btree (knowledge_base_id, correlation_id);
CREATE INDEX ix_raw_records_payload ON public.raw_records USING gin (payload);
CREATE INDEX ix_risk_projections_kb_score ON public.risk_projections USING btree (knowledge_base_id, overall_score DESC, scored_at DESC);
CREATE INDEX ix_risk_projections_kb_status ON public.risk_projections USING btree (knowledge_base_id, status, risk_level);
CREATE INDEX ix_risk_score_history_entity ON public.risk_score_history USING btree (knowledge_base_id, entity_id, assessed_at DESC);
CREATE INDEX ix_score_batches_run_status ON public.score_batches USING btree (run_id, status, batch_number);
CREATE INDEX ix_score_runs_kb_status ON public.score_runs USING btree (knowledge_base_id, status, created_at DESC);
CREATE INDEX ix_score_runs_status_updated ON public.score_runs USING btree (status, updated_at);
CREATE INDEX ix_scorecard_runs_kb_template ON public.scorecard_runs USING btree (knowledge_base_id, template_id);
CREATE INDEX ix_source_document_status_kb_status ON public.source_document_status USING btree (knowledge_base_id, current_status);
CREATE INDEX ix_workflow_definition_snapshots_kb_status ON public.workflow_definition_snapshots USING btree (knowledge_base_id, status, updated_at DESC);
CREATE INDEX observations_observed_at_idx ON public.observations USING btree (observed_at DESC);
CREATE UNIQUE INDEX ux_connector_sync_runs_idempotency ON public.connector_sync_runs USING btree (connector_id, idempotency_key) WHERE (idempotency_key IS NOT NULL);
CREATE UNIQUE INDEX ux_policy_items_item_id ON public.policy_items USING btree (knowledge_base_id, item_id);
CREATE UNIQUE INDEX ux_score_runs_kb_idempotency ON public.score_runs USING btree (knowledge_base_id, idempotency_key) WHERE (idempotency_key IS NOT NULL);
ALTER TABLE ONLY public.connector_quarantine_records
    ADD CONSTRAINT connector_quarantine_records_run_id_fkey FOREIGN KEY (run_id) REFERENCES public.connector_sync_runs(run_id) ON DELETE CASCADE;
ALTER TABLE ONLY public.connector_sync_runs
    ADD CONSTRAINT connector_sync_runs_connector_id_fkey FOREIGN KEY (connector_id) REFERENCES public.connectors(connector_id) ON DELETE CASCADE;
ALTER TABLE ONLY public.score_batches
    ADD CONSTRAINT score_batches_run_id_fkey FOREIGN KEY (run_id) REFERENCES public.score_runs(id) ON DELETE CASCADE;
-- timescaledb hypertables (hypertable_name|num_dimensions)
entity_metric_history|1
observations|1
