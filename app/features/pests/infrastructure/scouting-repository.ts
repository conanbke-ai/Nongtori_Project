import type { AlertDecision, FieldEvidenceCode, ScoutingState } from '../domain/scouting-policy';

export type ScoutingLocationStateRow = {
  id: string;
  farm_id: string;
  house_id: string;
  bed_id: string;
  zone_id: string;
  location_key: string;
  house_code: string;
  bed_code: string;
  zone_code: string;
  current_state: ScoutingState;
  active_case_id: string | null;
  last_observed_at: string | null;
  last_field_check_at: string | null;
  last_action_at: string | null;
  last_alert_at: string | null;
  last_alert_reason: string | null;
  recent_pattern_fingerprint: string | null;
  state_version: number;
};

export type ScoutingCaseRow = {
  id: string;
  farm_id: string;
  location_state_id: string;
  issue_family: 'PEST' | 'DISEASE' | 'PHYSIOLOGICAL_ENVIRONMENTAL' | 'UNKNOWN';
  primary_issue_code: string | null;
  status: 'OPEN' | 'MONITORING' | 'POST_TREATMENT' | 'RESOLVED';
  opened_at: string;
  closed_at?: string | null;
  close_reason?: string | null;
};

export type ScoutingPolicyProfile = {
  policy_version: string;
  freshness_mode: 'CALIBRATION_PENDING' | 'FIXED_WINDOW';
  field_check_freshness_minutes: number | null;
};

export type ObservationInput = {
  id: string;
  farmId: string;
  locationStateId: string;
  caseId: string | null;
  captureSessionId?: string | null;
  frameId?: string | null;
  sourceAssetId?: string | null;
  observedAt: string;
  sourceType: 'THERMAL' | 'RGB_REFERENCE' | 'SENSOR' | 'MANUAL' | 'FUSION';
  leafTemp?: number | null;
  ambientTemp?: number | null;
  referenceTemp?: number | null;
  humidity?: number | null;
  lightLevel?: number | null;
  thermalFeaturesJson?: string;
  rgbReferenceJson?: string;
  modelName?: string | null;
  modelVersion?: string | null;
  riskSignal?: number | null;
  noveltySignal?: number | null;
  trendSignal?: number | null;
  spatialSignal?: number | null;
  patternFingerprint?: string | null;
  policyInputJson: string;
};

export class ScoutingRepository {
  constructor(private db: D1Database) {}

  async resolveLocation(farmId: string, houseId: string, bedId: string, zoneId: string, now: string) {
    const location = await this.db.prepare(`SELECT h.id AS house_id, h.code AS house_code,
        b.id AS bed_id, b.code AS bed_code, z.id AS zone_id, z.code AS zone_code
      FROM houses h JOIN beds b ON b.house_id = h.id JOIN zones z ON z.bed_id = b.id
      WHERE h.farm_id = ? AND h.id = ? AND b.id = ? AND z.id = ?
        AND h.status = 'ACTIVE' AND b.status = 'ACTIVE' AND z.status = 'ACTIVE'
      LIMIT 1`).bind(farmId, houseId, bedId, zoneId).first<{
        house_id: string; house_code: string; bed_id: string; bed_code: string; zone_id: string; zone_code: string;
      }>();
    if (!location) throw new Error('선택한 동·베드·구역이 이 농장에 속하지 않습니다.');

    const locationKey = `${location.house_code}:${location.bed_code}:${location.zone_code}`;
    const existing = await this.db.prepare(`SELECT * FROM scouting_location_states
      WHERE farm_id = ? AND location_key = ? LIMIT 1`).bind(farmId, locationKey).first<ScoutingLocationStateRow>();
    if (existing) return existing;

    const id = crypto.randomUUID();
    await this.db.prepare(`INSERT INTO scouting_location_states(
      id, farm_id, house_id, bed_id, zone_id, location_key, house_code, bed_code, zone_code,
      current_state, state_version, created_at, updated_at
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'BASELINE', 1, ?, ?)`)
      .bind(id, farmId, houseId, bedId, zoneId, locationKey,
        location.house_code, location.bed_code, location.zone_code, now, now).run();
    return this.db.prepare('SELECT * FROM scouting_location_states WHERE id = ?')
      .bind(id).first<ScoutingLocationStateRow>() as Promise<ScoutingLocationStateRow>;
  }

  async activeCase(locationStateId: string) {
    return this.db.prepare(`SELECT * FROM scouting_cases
      WHERE location_state_id = ? AND status IN ('OPEN', 'MONITORING', 'POST_TREATMENT')
      ORDER BY opened_at DESC LIMIT 1`).bind(locationStateId).first<ScoutingCaseRow>();
  }

  async latestResolvedCase(locationStateId: string) {
    return this.db.prepare(`SELECT * FROM scouting_cases WHERE location_state_id = ? AND status = 'RESOLVED'
      ORDER BY closed_at DESC, opened_at DESC LIMIT 1`).bind(locationStateId).first<ScoutingCaseRow>();
  }

  async activePolicyProfile() {
    return this.db.prepare(`SELECT policy_version, freshness_mode, field_check_freshness_minutes
      FROM scouting_policy_profiles WHERE status = 'ACTIVE' ORDER BY created_at DESC LIMIT 1`)
      .first<ScoutingPolicyProfile>();
  }

  async openCase(input: {
    farmId: string; locationStateId: string; issueFamily: ScoutingCaseRow['issue_family'];
    issueCode?: string | null; openedReason: string; now: string; previousCaseId?: string | null;
  }) {
    const id = crypto.randomUUID();
    const statements = [this.db.prepare(`INSERT INTO scouting_cases(
      id, farm_id, location_state_id, issue_family, primary_issue_code, status,
      opened_at, opened_reason, created_at, updated_at
    ) VALUES (?, ?, ?, ?, ?, 'OPEN', ?, ?, ?, ?)`)
      .bind(id, input.farmId, input.locationStateId, input.issueFamily, input.issueCode ?? null,
        input.now, input.openedReason, input.now, input.now)];
    if (input.previousCaseId) {
      statements.push(this.db.prepare(`INSERT INTO scouting_case_links(case_id, previous_case_id, link_type, created_at)
        VALUES (?, ?, 'RECURRENCE', ?)`).bind(id, input.previousCaseId, input.now));
    }
    statements.push(this.db.prepare(`INSERT INTO scouting_case_events(
      id, farm_id, location_state_id, case_id, event_type, reason_code, actor_member_id, detail_json, created_at
    ) VALUES (?, ?, ?, ?, ?, ?, NULL, ?, ?)`)
      .bind(crypto.randomUUID(), input.farmId, input.locationStateId, id,
        input.previousCaseId ? 'RECURRENCE_OPENED' : 'OPENED', input.openedReason,
        JSON.stringify({ previousCaseId: input.previousCaseId ?? null }), input.now));
    await this.db.batch(statements);
    return id;
  }

  async validateObservationScope(input: {
    farmId: string; location: ScoutingLocationStateRow; captureSessionId?: string | null; frameId?: string | null;
  }) {
    let sessionId = input.captureSessionId ?? null;
    if (input.captureSessionId) {
      const session = await this.db.prepare(`SELECT id, farm_id, house_id, bed_id, zone_id FROM capture_sessions WHERE id = ? LIMIT 1`)
        .bind(input.captureSessionId).first<{ id: string; farm_id: string; house_id: string | null; bed_id: string | null; zone_id: string | null }>();
      if (!session || session.farm_id !== input.farmId) throw new Error('관측 세션이 선택한 농장과 일치하지 않습니다.');
      if ((session.house_id && session.house_id !== input.location.house_id)
        || (session.bed_id && session.bed_id !== input.location.bed_id)
        || (session.zone_id && session.zone_id !== input.location.zone_id)) {
        throw new Error('관측 세션 위치가 선택한 동·베드·구역과 일치하지 않습니다.');
      }
    }

    if (input.frameId) {
      const frame = await this.db.prepare(`SELECT fr.id, fr.capture_session_id, cs.farm_id,
          cs.house_id AS session_house_id, cs.bed_id AS session_bed_id, cs.zone_id AS session_zone_id,
          fla.house_id AS frame_house_id, fla.bed_id AS frame_bed_id, fla.zone_id AS frame_zone_id
        FROM frames fr JOIN capture_sessions cs ON cs.id = fr.capture_session_id
        LEFT JOIN frame_location_assignments fla ON fla.frame_id = fr.id
        WHERE fr.id = ? LIMIT 1`).bind(input.frameId).first<{
          id: string; capture_session_id: string; farm_id: string;
          session_house_id: string | null; session_bed_id: string | null; session_zone_id: string | null;
          frame_house_id: string | null; frame_bed_id: string | null; frame_zone_id: string | null;
        }>();
      if (!frame || frame.farm_id !== input.farmId) throw new Error('관측 프레임이 선택한 농장과 일치하지 않습니다.');
      if (sessionId && frame.capture_session_id !== sessionId) throw new Error('관측 프레임과 capture session이 서로 일치하지 않습니다.');
      sessionId = frame.capture_session_id;
      const houseId = frame.frame_house_id ?? frame.session_house_id;
      const bedId = frame.frame_bed_id ?? frame.session_bed_id;
      const zoneId = frame.frame_zone_id ?? frame.session_zone_id;
      if ((houseId && houseId !== input.location.house_id)
        || (bedId && bedId !== input.location.bed_id)
        || (zoneId && zoneId !== input.location.zone_id)) {
        throw new Error('관측 프레임 위치가 선택한 동·베드·구역과 일치하지 않습니다.');
      }
    }
    return sessionId;
  }

  async appendObservation(input: ObservationInput) {
    await this.db.prepare(`INSERT INTO scouting_observations(
      id, farm_id, location_state_id, case_id, capture_session_id, frame_id, source_asset_id,
      observed_at, source_type, leaf_temp, ambient_temp, reference_temp, humidity, light_level,
      thermal_features_json, rgb_reference_json, model_name, model_version,
      risk_signal, novelty_signal, trend_signal, spatial_signal, pattern_fingerprint,
      policy_input_json, created_at
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`)
      .bind(input.id, input.farmId, input.locationStateId, input.caseId,
        input.captureSessionId ?? null, input.frameId ?? null, input.sourceAssetId ?? null,
        input.observedAt, input.sourceType, input.leafTemp ?? null, input.ambientTemp ?? null,
        input.referenceTemp ?? null, input.humidity ?? null, input.lightLevel ?? null,
        input.thermalFeaturesJson ?? '{}', input.rgbReferenceJson ?? '{}',
        input.modelName ?? null, input.modelVersion ?? null,
        input.riskSignal ?? null, input.noveltySignal ?? null, input.trendSignal ?? null,
        input.spatialSignal ?? null, input.patternFingerprint ?? null, input.policyInputJson, input.observedAt).run();
  }

  async appendAlert(input: {
    id: string; farmId: string; locationStateId: string; caseId: string | null; observationId: string;
    decision: AlertDecision; reason: string; suppressionReason: string | null; policyVersion: string; now: string;
  }) {
    await this.db.prepare(`INSERT INTO scouting_alert_events(
      id, farm_id, location_state_id, case_id, observation_id, created_at,
      alert_decision, alert_reason, suppression_reason, policy_version
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`)
      .bind(input.id, input.farmId, input.locationStateId, input.caseId, input.observationId,
        input.now, input.decision, input.reason, input.suppressionReason, input.policyVersion).run();
  }

  async updateLocation(input: {
    locationStateId: string; nextState: ScoutingState; activeCaseId: string | null;
    observedAt: string; fingerprint?: string | null; alertAt?: string | null; alertReason?: string | null;
  }) {
    await this.db.prepare(`UPDATE scouting_location_states SET
      current_state = ?, active_case_id = ?, last_observed_at = ?,
      recent_pattern_fingerprint = COALESCE(?, recent_pattern_fingerprint),
      last_alert_at = COALESCE(?, last_alert_at),
      last_alert_reason = COALESCE(?, last_alert_reason),
      state_version = state_version + 1, updated_at = ?
      WHERE id = ?`)
      .bind(input.nextState, input.activeCaseId, input.observedAt, input.fingerprint ?? null,
        input.alertAt ?? null, input.alertReason ?? null, input.observedAt, input.locationStateId).run();
  }

  async appendFieldCheck(input: {
    id: string; farmId: string; locationStateId: string; caseId: string | null; observationId?: string | null;
    checkedAt: string; checkerMemberId: string; evidenceCode: FieldEvidenceCode;
    secondaryEvidenceJson?: string; note?: string | null;
  }) {
    await this.db.prepare(`INSERT INTO scouting_field_checks(
      id, farm_id, location_state_id, case_id, observation_id, checked_at, checker_member_id,
      primary_evidence_code, secondary_evidence_json, note, created_at
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`)
      .bind(input.id, input.farmId, input.locationStateId, input.caseId, input.observationId ?? null,
        input.checkedAt, input.checkerMemberId, input.evidenceCode, input.secondaryEvidenceJson ?? '{}',
        input.note ?? null, input.checkedAt).run();
  }

  async fieldCheckForCorrection(farmId: string, fieldCheckId: string) {
    return this.db.prepare(`SELECT id, farm_id, location_state_id, case_id, primary_evidence_code, checked_at
      FROM scouting_field_checks WHERE id = ? AND farm_id = ? LIMIT 1`).bind(fieldCheckId, farmId).first<{
      id: string; farm_id: string; location_state_id: string; case_id: string | null;
      primary_evidence_code: FieldEvidenceCode; checked_at: string;
    }>();
  }

  async applyFieldCheckState(input: {
    locationStateId: string; caseId: string | null; nextState: ScoutingState;
    evidenceCode: FieldEvidenceCode; issueFamily?: ScoutingCaseRow['issue_family']; issueCode?: string | null; now: string;
  }) {
    const statements = [
      this.db.prepare(`UPDATE scouting_location_states SET current_state = ?, last_field_check_at = ?,
        state_version = state_version + 1, updated_at = ? WHERE id = ?`)
        .bind(input.nextState, input.now, input.now, input.locationStateId),
    ];
    if (input.caseId && input.issueFamily && input.issueCode) {
      statements.push(this.db.prepare(`UPDATE scouting_cases SET issue_family = ?, primary_issue_code = ?,
        status = ?, updated_at = ? WHERE id = ? AND status != 'RESOLVED'`)
        .bind(input.issueFamily, input.issueCode,
          input.evidenceCode === 'DIRECT_MITE_OR_EGG_CONFIRMED' ? 'OPEN' : 'MONITORING', input.now, input.caseId));
    } else if (input.caseId) {
      statements.push(this.db.prepare(`UPDATE scouting_cases SET status = 'MONITORING', updated_at = ?
        WHERE id = ? AND status != 'RESOLVED'`).bind(input.now, input.caseId));
    }
    await this.db.batch(statements);
  }

  async appendFieldCheckCorrection(input: {
    id: string; farmId: string; fieldCheckId: string; locationStateId: string; caseId: string | null;
    correctionKind: 'REPLACE' | 'VOID'; replacementEvidenceCode?: FieldEvidenceCode | null;
    reasonCode: 'MISCLICK' | 'WRONG_OBSERVATION' | 'DUPLICATE' | 'OTHER'; note?: string | null;
    actorMemberId: string; now: string; nextState: ScoutingState;
    issueFamily?: ScoutingCaseRow['issue_family']; issueCode?: string | null;
  }) {
    const statements = [this.db.prepare(`INSERT INTO scouting_field_check_corrections(
      id, farm_id, field_check_id, location_state_id, case_id, correction_kind, replacement_evidence_code,
      reason_code, note, actor_member_id, created_at
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`)
      .bind(input.id, input.farmId, input.fieldCheckId, input.locationStateId, input.caseId,
        input.correctionKind, input.replacementEvidenceCode ?? null, input.reasonCode,
        input.note ?? null, input.actorMemberId, input.now),
      this.db.prepare(`UPDATE scouting_location_states SET current_state = ?, last_field_check_at = ?,
        state_version = state_version + 1, updated_at = ? WHERE id = ?`)
        .bind(input.nextState, input.now, input.now, input.locationStateId),
    ];
    if (input.caseId && input.correctionKind === 'REPLACE' && input.issueFamily && input.issueCode) {
      statements.push(this.db.prepare(`UPDATE scouting_cases SET issue_family = ?, primary_issue_code = ?, status = ?, updated_at = ?
        WHERE id = ? AND status != 'RESOLVED'`).bind(input.issueFamily, input.issueCode,
          input.replacementEvidenceCode === 'DIRECT_MITE_OR_EGG_CONFIRMED' ? 'OPEN' : 'MONITORING', input.now, input.caseId));
    } else if (input.caseId && input.correctionKind === 'REPLACE') {
      statements.push(this.db.prepare(`UPDATE scouting_cases SET status = 'MONITORING', updated_at = ?
        WHERE id = ? AND status != 'RESOLVED'`).bind(input.now, input.caseId));
    }
    if (input.caseId) {
      statements.push(this.db.prepare(`INSERT INTO scouting_case_events(
        id, farm_id, location_state_id, case_id, event_type, reason_code, actor_member_id, detail_json, created_at
      ) VALUES (?, ?, ?, ?, 'FIELD_CHECK_CORRECTED', ?, ?, ?, ?)`)
        .bind(crypto.randomUUID(), input.farmId, input.locationStateId, input.caseId, input.reasonCode,
          input.actorMemberId, JSON.stringify({ fieldCheckId: input.fieldCheckId, correctionKind: input.correctionKind,
            replacementEvidenceCode: input.replacementEvidenceCode ?? null }), input.now));
    }
    await this.db.batch(statements);
  }

  async appendAction(input: {
    id: string; farmId: string; locationStateId: string; caseId: string | null;
    actionAt: string; actionCode: string; actorMemberId: string; detailJson?: string; note?: string | null;
    nextState: ScoutingState;
  }) {
    const statements = [
      this.db.prepare(`INSERT INTO scouting_actions(
        id, farm_id, location_state_id, case_id, action_at, action_code, actor_member_id,
        detail_json, note, created_at
      ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`)
        .bind(input.id, input.farmId, input.locationStateId, input.caseId, input.actionAt,
          input.actionCode, input.actorMemberId, input.detailJson ?? '{}', input.note ?? null, input.actionAt),
      this.db.prepare(`UPDATE scouting_location_states SET current_state = ?, last_action_at = ?,
        state_version = state_version + 1, updated_at = ? WHERE id = ?`)
        .bind(input.nextState, input.actionAt, input.actionAt, input.locationStateId),
    ];
    if (input.caseId) {
      const status = input.nextState === 'POST_TREATMENT' ? 'POST_TREATMENT' : 'MONITORING';
      statements.push(this.db.prepare('UPDATE scouting_cases SET status = ?, updated_at = ? WHERE id = ? AND status != \'RESOLVED\'')
        .bind(status, input.actionAt, input.caseId));
    }
    await this.db.batch(statements);
  }

  async resolveCase(input: {
    farmId: string; locationStateId: string; caseId: string; reasonCode: string; actorMemberId: string; now: string;
  }) {
    await this.db.batch([
      this.db.prepare(`UPDATE scouting_cases SET status = 'RESOLVED', closed_at = ?, close_reason = ?, updated_at = ?
        WHERE id = ? AND farm_id = ? AND location_state_id = ? AND status != 'RESOLVED'`)
        .bind(input.now, input.reasonCode, input.now, input.caseId, input.farmId, input.locationStateId),
      this.db.prepare(`UPDATE scouting_location_states SET current_state = 'RESOLVED', active_case_id = NULL,
        state_version = state_version + 1, updated_at = ? WHERE id = ? AND farm_id = ?`)
        .bind(input.now, input.locationStateId, input.farmId),
      this.db.prepare(`INSERT INTO scouting_case_events(
        id, farm_id, location_state_id, case_id, event_type, reason_code, actor_member_id, detail_json, created_at
      ) VALUES (?, ?, ?, ?, 'RESOLVED', ?, ?, '{}', ?)`)
        .bind(crypto.randomUUID(), input.farmId, input.locationStateId, input.caseId,
          input.reasonCode, input.actorMemberId, input.now),
    ]);
  }

  async createNotifications(input: {
    farmId: string; locationState: ScoutingLocationStateRow; observationId: string;
    decision: Exclude<AlertDecision, 'SUPPRESSED'>; reason: string; now: string;
  }) {
    const recipients = await this.db.prepare(`SELECT id, phone FROM farm_members
      WHERE farm_id = ? AND status = 'ACTIVE' AND notifications_enabled = 1
        AND phone IS NOT NULL AND phone_verified_at IS NOT NULL`)
      .bind(input.farmId).all<{ id: string; phone: string }>();
    const ids: string[] = [];
    for (const recipient of recipients.results) {
      const id = crypto.randomUUID();
      ids.push(id);
      const payload = JSON.stringify({
        scoutingObservationId: input.observationId,
        locationKey: input.locationState.location_key,
        houseCode: input.locationState.house_code,
        bedCode: input.locationState.bed_code,
        zoneCode: input.locationState.zone_code,
        decision: input.decision,
        reason: input.reason,
      });
      await this.db.prepare(`INSERT INTO notification_outbox(
        id, farm_id, frame_prediction_id, recipient_member_id, recipient_phone,
        notification_type, payload_json, status, attempts, last_error, created_at, sent_at
      ) VALUES (?, ?, NULL, ?, ?, 'PEST_SCOUTING_ALERT', ?, 'PENDING', 0, NULL, ?, NULL)`)
        .bind(id, input.farmId, recipient.id, recipient.phone, payload, input.now).run();
    }
    return ids;
  }

  async latestObservation(locationStateId: string) {
    return this.db.prepare(`SELECT * FROM scouting_observations WHERE location_state_id = ?
      ORDER BY observed_at DESC, id DESC LIMIT 1`).bind(locationStateId).first<Record<string, unknown>>();
  }

  async locationHistory(farmId: string, locationStateId: string, limit = 50) {
    const location = await this.db.prepare(`SELECT * FROM scouting_location_states
      WHERE id = ? AND farm_id = ?`).bind(locationStateId, farmId).first<ScoutingLocationStateRow>();
    if (!location) return null;
    const observations = await this.db.prepare(`SELECT * FROM scouting_observations
      WHERE location_state_id = ? ORDER BY observed_at DESC LIMIT ?`).bind(locationStateId, limit).all();
    const fieldChecks = await this.db.prepare(`SELECT * FROM scouting_field_checks
      WHERE location_state_id = ? ORDER BY checked_at DESC LIMIT ?`).bind(locationStateId, limit).all();
    const corrections = await this.db.prepare(`SELECT * FROM scouting_field_check_corrections
      WHERE location_state_id = ? ORDER BY created_at DESC LIMIT ?`).bind(locationStateId, limit).all();
    const actions = await this.db.prepare(`SELECT * FROM scouting_actions
      WHERE location_state_id = ? ORDER BY action_at DESC LIMIT ?`).bind(locationStateId, limit).all();
    const alerts = await this.db.prepare(`SELECT * FROM scouting_alert_events
      WHERE location_state_id = ? ORDER BY created_at DESC LIMIT ?`).bind(locationStateId, limit).all();
    const caseEvents = await this.db.prepare(`SELECT * FROM scouting_case_events
      WHERE location_state_id = ? ORDER BY created_at DESC LIMIT ?`).bind(locationStateId, limit).all();
    return { location, observations: observations.results, fieldChecks: fieldChecks.results,
      corrections: corrections.results, actions: actions.results, alerts: alerts.results, caseEvents: caseEvents.results };
  }
}
