import { sql } from 'drizzle-orm';
import { check, index, integer, real, sqliteTable, text, uniqueIndex } from 'drizzle-orm/sqlite-core';

export const cultivars = sqliteTable('cultivars', {
  code: text('code').primaryKey(),
  displayNameKo: text('display_name_ko').notNull(),
  operationalStatus: text('operational_status').notNull(),
  supportsQuality: integer('supports_quality', { mode: 'boolean' }).notNull(),
  supportsRipeness: integer('supports_ripeness', { mode: 'boolean' }).notNull(),
  supportsMiteWarning: integer('supports_mite_warning', { mode: 'boolean' }).notNull(),
  createdAt: text('created_at').notNull(),
});

export const farms = sqliteTable(
  'farms',
  {
    id: text('id').primaryKey(),
    code: text('code').notNull().unique(),
    name: text('name').notNull(),
    timezone: text('timezone').notNull().default('Asia/Seoul'),
    status: text('status').notNull().default('ACTIVE'),
    createdAt: text('created_at').notNull(),
    updatedAt: text('updated_at').notNull(),
  },
  (table) => [index('idx_farms_status').on(table.status, table.name)],
);

export const farmCultivars = sqliteTable(
  'farm_cultivars',
  {
    id: text('id').primaryKey(),
    farmId: text('farm_id').notNull().references(() => farms.id, { onDelete: 'cascade' }),
    cultivarCode: text('cultivar_code').notNull().references(() => cultivars.code),
    status: text('status').notNull().default('ACTIVE'),
    createdAt: text('created_at').notNull(),
  },
  (table) => [uniqueIndex('uq_farm_cultivars').on(table.farmId, table.cultivarCode)],
);

export const cropTypes = sqliteTable('crop_types', {
  code: text('code').primaryKey(),
  displayNameKo: text('display_name_ko').notNull(),
  createdAt: text('created_at').notNull(),
});

export const cropProfiles = sqliteTable('crop_profiles', {
  cropCode: text('crop_code').primaryKey().references(() => cropTypes.code, { onDelete: 'cascade' }),
  imageUri: text('image_uri'),
  descriptionKo: text('description_ko').notNull().default(''),
  updatedAt: text('updated_at').notNull(),
});

export const cropGuides = sqliteTable(
  'crop_guides',
  {
    id: text('id').primaryKey(),
    cropCode: text('crop_code').notNull().references(() => cropTypes.code, { onDelete: 'cascade' }),
    cultivarCode: text('cultivar_code').references(() => cultivars.code, { onDelete: 'set null' }),
    guideType: text('guide_type').notNull(),
    title: text('title').notNull(),
    symptomSummary: text('symptom_summary').notNull(),
    riskSummary: text('risk_summary').notNull(),
    preventionSummary: text('prevention_summary').notNull(),
    responseSummary: text('response_summary').notNull(),
    sourceTitle: text('source_title').notNull(),
    sourceUrl: text('source_url').notNull(),
    reviewedAt: text('reviewed_at').notNull(),
    displayOrder: integer('display_order').notNull().default(0),
    status: text('status').notNull().default('ACTIVE'),
    createdAt: text('created_at').notNull(),
    updatedAt: text('updated_at').notNull(),
  },
  (table) => [
    index('idx_crop_guides_crop_cultivar').on(table.cropCode, table.cultivarCode, table.status, table.displayOrder),
  ],
);

export const cropStages = sqliteTable('crop_stages', {
  code: text('code').primaryKey(),
  displayNameKo: text('display_name_ko').notNull(),
  displayOrder: integer('display_order').notNull().default(0),
});

export const cropGuideStages = sqliteTable(
  'crop_guide_stages',
  {
    id: text('id').primaryKey(),
    guideId: text('guide_id').notNull().references(() => cropGuides.id, { onDelete: 'cascade' }),
    stageCode: text('stage_code').notNull().references(() => cropStages.code, { onDelete: 'cascade' }),
  },
  (table) => [
    uniqueIndex('uq_crop_guide_stages_guide_stage').on(table.guideId, table.stageCode),
    index('idx_crop_guide_stages_stage').on(table.stageCode, table.guideId),
  ],
);

export const farmItems = sqliteTable(
  'farm_items',
  {
    id: text('id').primaryKey(),
    farmId: text('farm_id').notNull().references(() => farms.id, { onDelete: 'cascade' }),
    cropCode: text('crop_code').notNull().references(() => cropTypes.code),
    cultivarCode: text('cultivar_code').references(() => cultivars.code),
    displayName: text('display_name').notNull(),
    status: text('status').notNull().default('ACTIVE'),
    createdAt: text('created_at').notNull(),
    updatedAt: text('updated_at').notNull(),
  },
  (table) => [
    uniqueIndex('uq_farm_items_crop_cultivar').on(table.farmId, table.cropCode, table.cultivarCode),
    index('idx_farm_items_farm_status').on(table.farmId, table.status),
  ],
);

export const appUsers = sqliteTable(
  'app_users',
  {
    id: text('id').primaryKey(),
    displayName: text('display_name').notNull(),
    phoneE164: text('phone_e164'),
    phoneVerifiedAt: text('phone_verified_at'),
    preferredLanguage: text('preferred_language').notNull().default('ko'),
    status: text('status').notNull().default('ACTIVE'),
    createdAt: text('created_at').notNull(),
    updatedAt: text('updated_at').notNull(),
  },
  (table) => [
    index('idx_app_users_status').on(table.status, table.updatedAt),
    uniqueIndex('uq_app_users_verified_phone').on(table.phoneE164),
  ],
);

export const authIdentities = sqliteTable(
  'auth_identities',
  {
    id: text('id').primaryKey(),
    userId: text('user_id').notNull().references(() => appUsers.id, { onDelete: 'cascade' }),
    provider: text('provider').notNull(),
    providerSubject: text('provider_subject').notNull(),
    email: text('email'),
    emailVerifiedAt: text('email_verified_at'),
    createdAt: text('created_at').notNull(),
    updatedAt: text('updated_at').notNull(),
  },
  (table) => [
    uniqueIndex('uq_auth_identities_provider_subject').on(table.provider, table.providerSubject),
    index('idx_auth_identities_user').on(table.userId, table.provider),
  ],
);

export const passwordCredentials = sqliteTable(
  'password_credentials',
  {
    userId: text('user_id').primaryKey().references(() => appUsers.id, { onDelete: 'cascade' }),
    loginId: text('login_id').notNull().unique(),
    passwordHash: text('password_hash').notNull(),
    passwordAlgorithm: text('password_algorithm').notNull().default('ARGON2ID'),
    failedAttempts: integer('failed_attempts').notNull().default(0),
    lockedUntil: text('locked_until'),
    passwordChangedAt: text('password_changed_at').notNull(),
    createdAt: text('created_at').notNull(),
    updatedAt: text('updated_at').notNull(),
  },
  (table) => [index('idx_password_credentials_locked').on(table.lockedUntil)],
);

export const authSessions = sqliteTable(
  'auth_sessions',
  {
    id: text('id').primaryKey(),
    userId: text('user_id').notNull().references(() => appUsers.id, { onDelete: 'cascade' }),
    tokenHash: text('token_hash').notNull().unique(),
    expiresAt: text('expires_at').notNull(),
    lastSeenAt: text('last_seen_at').notNull(),
    revokedAt: text('revoked_at'),
    createdAt: text('created_at').notNull(),
  },
  (table) => [index('idx_auth_sessions_user_expiry').on(table.userId, table.expiresAt)],
);

export const farmMembers = sqliteTable(
  'farm_members',
  {
    id: text('id').primaryKey(),
    farmId: text('farm_id').notNull().references(() => farms.id, { onDelete: 'cascade' }),
    userId: text('user_id').references(() => appUsers.id, { onDelete: 'set null' }),
    loginId: text('login_id').notNull(),
    identityProvider: text('identity_provider').notNull(),
    identitySubject: text('identity_subject'),
    email: text('email'),
    displayName: text('display_name'),
    phone: text('phone'),
    phoneVerifiedAt: text('phone_verified_at'),
    notificationsEnabled: integer('notifications_enabled').notNull().default(0),
    preferredLanguage: text('preferred_language').notNull().default('ko'),
    invitedByMemberId: text('invited_by_member_id'),
    approvedAt: text('approved_at'),
    joinedAt: text('joined_at'),
    role: text('role').notNull().default('WORKER'),
    status: text('status').notNull().default('ACTIVE'),
    createdAt: text('created_at').notNull(),
    updatedAt: text('updated_at').notNull(),
  },
  (table) => [
    uniqueIndex('uq_farm_members_login').on(table.loginId),
    uniqueIndex('uq_farm_members_provider_subject').on(table.identityProvider, table.identitySubject),
    uniqueIndex('uq_farm_members_farm_user').on(table.farmId, table.userId),
    index('idx_farm_members_farm_status').on(table.farmId, table.status),
  ],
);

export const farmInvitations = sqliteTable(
  'farm_invitations',
  {
    id: text('id').primaryKey(),
    farmId: text('farm_id').notNull().references(() => farms.id, { onDelete: 'cascade' }),
    role: text('role').notNull().default('WORKER'),
    tokenHash: text('token_hash').notNull().unique(),
    expiresAt: text('expires_at').notNull(),
    maxUses: integer('max_uses').notNull().default(1),
    usedCount: integer('used_count').notNull().default(0),
    status: text('status').notNull().default('ACTIVE'),
    createdByMemberId: text('created_by_member_id').references(() => farmMembers.id, { onDelete: 'set null' }),
    createdAt: text('created_at').notNull(),
    updatedAt: text('updated_at').notNull(),
  },
  (table) => [index('idx_farm_invitations_farm_status').on(table.farmId, table.status, table.expiresAt)],
);

export const farmJoinRequests = sqliteTable(
  'farm_join_requests',
  {
    id: text('id').primaryKey(),
    invitationId: text('invitation_id').notNull().references(() => farmInvitations.id, { onDelete: 'restrict' }),
    farmId: text('farm_id').notNull().references(() => farms.id, { onDelete: 'cascade' }),
    userId: text('user_id').notNull().references(() => appUsers.id, { onDelete: 'restrict' }),
    requestedRole: text('requested_role').notNull().default('WORKER'),
    preferredLanguage: text('preferred_language').notNull().default('ko'),
    status: text('status').notNull().default('PENDING'),
    reviewedByMemberId: text('reviewed_by_member_id').references(() => farmMembers.id, { onDelete: 'set null' }),
    reviewedAt: text('reviewed_at'),
    createdAt: text('created_at').notNull(),
    updatedAt: text('updated_at').notNull(),
  },
  (table) => [
    uniqueIndex('uq_farm_join_requests_invite_user').on(table.invitationId, table.userId),
    index('idx_farm_join_requests_farm_status').on(table.farmId, table.status, table.createdAt),
  ],
);

export const farmMemberEvents = sqliteTable(
  'farm_member_events',
  {
    id: text('id').primaryKey(),
    farmId: text('farm_id').notNull().references(() => farms.id, { onDelete: 'cascade' }),
    targetMemberId: text('target_member_id').references(() => farmMembers.id, { onDelete: 'set null' }),
    actorMemberId: text('actor_member_id').references(() => farmMembers.id, { onDelete: 'set null' }),
    targetNameSnapshot: text('target_name_snapshot').notNull(),
    actorNameSnapshot: text('actor_name_snapshot').notNull(),
    eventType: text('event_type').notNull(),
    detailJson: text('detail_json').notNull().default('{}'),
    createdAt: text('created_at').notNull(),
  },
  (table) => [
    index('idx_farm_member_events_farm_created').on(table.farmId, table.createdAt),
    index('idx_farm_member_events_target_created').on(table.targetMemberId, table.createdAt),
  ],
);

export const farmNotes = sqliteTable(
  'farm_notes',
  {
    id: text('id').primaryKey(),
    farmId: text('farm_id').notNull().references(() => farms.id, { onDelete: 'cascade' }),
    itemId: text('item_id').references(() => farmItems.id, { onDelete: 'set null' }),
    authorMemberId: text('author_member_id').references(() => farmMembers.id, { onDelete: 'set null' }),
    authorNameSnapshot: text('author_name_snapshot').notNull(),
    authorRoleSnapshot: text('author_role_snapshot').notNull(),
    language: text('language').notNull().default('ko'),
    category: text('category').notNull(),
    title: text('title').notNull(),
    content: text('content').notNull(),
    pinned: integer('pinned').notNull().default(0),
    status: text('status').notNull().default('ACTIVE'),
    createdAt: text('created_at').notNull(),
    updatedAt: text('updated_at').notNull(),
  },
  (table) => [
    index('idx_farm_notes_farm_status_updated').on(table.farmId, table.status, table.updatedAt),
    index('idx_farm_notes_item_updated').on(table.itemId, table.updatedAt),
  ],
);

export const farmChatMessages = sqliteTable(
  'farm_chat_messages',
  {
    id: text('id').primaryKey(),
    farmId: text('farm_id').notNull().references(() => farms.id, { onDelete: 'cascade' }),
    authorMemberId: text('author_member_id').references(() => farmMembers.id, { onDelete: 'set null' }),
    authorNameSnapshot: text('author_name_snapshot').notNull(),
    authorRoleSnapshot: text('author_role_snapshot').notNull(),
    authorAccountSnapshot: text('author_account_snapshot').notNull(),
    language: text('language').notNull().default('ko'),
    content: text('content').notNull(),
    status: text('status').notNull().default('ACTIVE'),
    createdAt: text('created_at').notNull(),
    updatedAt: text('updated_at').notNull(),
  },
  (table) => [
    index('idx_farm_chat_messages_farm_status_created').on(table.farmId, table.status, table.createdAt),
    index('idx_farm_chat_messages_author_created').on(table.authorMemberId, table.createdAt),
    check('ck_farm_chat_messages_language', sql`${table.language} in ('ko', 'vi', 'th', 'zh-CN')`),
    check('ck_farm_chat_messages_status', sql`${table.status} in ('ACTIVE', 'DELETED')`),
    check('ck_farm_chat_messages_content_length', sql`length(${table.content}) between 1 and 500`),
  ],
);

export const communityChatMessages = sqliteTable(
  'community_chat_messages',
  {
    id: text('id').primaryKey(),
    authorMemberId: text('author_member_id').references(() => farmMembers.id, { onDelete: 'set null' }),
    authorNameSnapshot: text('author_name_snapshot').notNull(),
    authorRoleSnapshot: text('author_role_snapshot').notNull(),
    authorAccountSnapshot: text('author_account_snapshot').notNull(),
    language: text('language').notNull().default('ko'),
    content: text('content').notNull(),
    status: text('status').notNull().default('ACTIVE'),
    createdAt: text('created_at').notNull(),
    updatedAt: text('updated_at').notNull(),
  },
  (table) => [
    index('idx_community_chat_messages_status_created').on(table.status, table.createdAt),
    index('idx_community_chat_messages_author_created').on(table.authorMemberId, table.createdAt),
    check('ck_community_chat_messages_language', sql`${table.language} in ('ko', 'vi', 'th', 'zh-CN')`),
    check('ck_community_chat_messages_status', sql`${table.status} in ('ACTIVE', 'DELETED')`),
    check('ck_community_chat_messages_content_length', sql`length(${table.content}) between 1 and 300`),
  ],
);

export const houses = sqliteTable(
  'houses',
  {
    id: text('id').primaryKey(),
    farmId: text('farm_id').notNull().references(() => farms.id, { onDelete: 'cascade' }),
    code: text('code').notNull(),
    name: text('name').notNull(),
    displayOrder: integer('display_order').notNull().default(0),
    status: text('status').notNull().default('ACTIVE'),
    metadataJson: text('metadata_json').notNull().default('{}'),
    createdAt: text('created_at').notNull(),
    updatedAt: text('updated_at').notNull(),
  },
  (table) => [
    uniqueIndex('uq_houses_farm_code').on(table.farmId, table.code),
    index('idx_houses_farm_order').on(table.farmId, table.displayOrder),
  ],
);

export const beds = sqliteTable(
  'beds',
  {
    id: text('id').primaryKey(),
    houseId: text('house_id').notNull().references(() => houses.id, { onDelete: 'cascade' }),
    code: text('code').notNull(),
    name: text('name').notNull(),
    displayOrder: integer('display_order').notNull().default(0),
    status: text('status').notNull().default('ACTIVE'),
    metadataJson: text('metadata_json').notNull().default('{}'),
    createdAt: text('created_at').notNull(),
    updatedAt: text('updated_at').notNull(),
  },
  (table) => [
    uniqueIndex('uq_beds_house_code').on(table.houseId, table.code),
    index('idx_beds_house_order').on(table.houseId, table.displayOrder),
  ],
);

export const zones = sqliteTable(
  'zones',
  {
    id: text('id').primaryKey(),
    bedId: text('bed_id').notNull().references(() => beds.id, { onDelete: 'cascade' }),
    code: text('code').notNull(),
    name: text('name').notNull(),
    displayOrder: integer('display_order').notNull().default(0),
    status: text('status').notNull().default('ACTIVE'),
    metadataJson: text('metadata_json').notNull().default('{}'),
    createdAt: text('created_at').notNull(),
    updatedAt: text('updated_at').notNull(),
  },
  (table) => [
    uniqueIndex('uq_zones_bed_code').on(table.bedId, table.code),
    index('idx_zones_bed_order').on(table.bedId, table.displayOrder),
  ],
);

export const cameras = sqliteTable(
  'cameras',
  {
    id: text('id').primaryKey(),
    farmId: text('farm_id').notNull().references(() => farms.id, { onDelete: 'cascade' }),
    houseId: text('house_id').references(() => houses.id, { onDelete: 'set null' }),
    bedId: text('bed_id').references(() => beds.id, { onDelete: 'set null' }),
    zoneId: text('zone_id').references(() => zones.id, { onDelete: 'set null' }),
    code: text('code').notNull(),
    name: text('name').notNull(),
    cameraType: text('camera_type').notNull(),
    sourceType: text('source_type').notNull(),
    externalRef: text('external_ref'),
    streamUrl: text('stream_url'),
    connectionStatus: text('connection_status').notNull().default('DISCONNECTED'),
    lastSeenAt: text('last_seen_at'),
    status: text('status').notNull().default('ACTIVE'),
    createdAt: text('created_at').notNull(),
    updatedAt: text('updated_at').notNull(),
  },
  (table) => [
    uniqueIndex('uq_cameras_farm_code').on(table.farmId, table.code),
    index('idx_cameras_zone').on(table.zoneId, table.status),
  ],
);

export const captureSessions = sqliteTable(
  'capture_sessions',
  {
    id: text('id').primaryKey(),
    farmId: text('farm_id').notNull().references(() => farms.id, { onDelete: 'cascade' }),
    cameraId: text('camera_id').references(() => cameras.id, { onDelete: 'set null' }),
    itemId: text('item_id').references(() => farmItems.id, { onDelete: 'set null' }),
    houseId: text('house_id').references(() => houses.id, { onDelete: 'set null' }),
    bedId: text('bed_id').references(() => beds.id, { onDelete: 'set null' }),
    zoneId: text('zone_id').references(() => zones.id, { onDelete: 'set null' }),
    captureMode: text('capture_mode').notNull(),
    sourceType: text('source_type').notNull(),
    processingStatus: text('processing_status').notNull(),
    startedAt: text('started_at').notNull(),
    endedAt: text('ended_at'),
    createdAt: text('created_at').notNull(),
  },
  (table) => [
    index('idx_capture_sessions_farm_started').on(table.farmId, table.startedAt),
    index('idx_capture_sessions_processing').on(table.processingStatus, table.createdAt),
  ],
);

export const harvestRuns = sqliteTable(
  'harvest_runs',
  {
    id: text('id').primaryKey(),
    farmId: text('farm_id').notNull().references(() => farms.id, { onDelete: 'cascade' }),
    itemId: text('item_id').notNull().references(() => farmItems.id, { onDelete: 'restrict' }),
    cameraId: text('camera_id').references(() => cameras.id, { onDelete: 'set null' }),
    status: text('status').notNull(),
    startedAt: text('started_at').notNull(),
    completedAt: text('completed_at'),
    startedByMemberId: text('started_by_member_id').references(() => farmMembers.id, { onDelete: 'set null' }),
    startedByNameSnapshot: text('started_by_name_snapshot'),
    completedByMemberId: text('completed_by_member_id').references(() => farmMembers.id, { onDelete: 'set null' }),
    completedByNameSnapshot: text('completed_by_name_snapshot'),
    note: text('note').notNull().default(''),
    harvestedCount: integer('harvested_count').notNull().default(0),
    totalWeightG: real('total_weight_g').notNull().default(0),
    createdAt: text('created_at').notNull(),
    updatedAt: text('updated_at').notNull(),
  },
  (table) => [
    index('idx_harvest_runs_farm_completed').on(table.farmId, table.completedAt),
    index('idx_harvest_runs_item_status_completed').on(table.itemId, table.status, table.completedAt),
  ],
);

export const harvestGradeSummaries = sqliteTable(
  'harvest_grade_summaries',
  {
    id: text('id').primaryKey(),
    harvestRunId: text('harvest_run_id').notNull().references(() => harvestRuns.id, { onDelete: 'cascade' }),
    gradeCode: text('grade_code').notNull(),
    fruitCount: integer('fruit_count').notNull(),
    totalWeightG: real('total_weight_g').notNull(),
    averageConfidence: real('average_confidence'),
    createdAt: text('created_at').notNull(),
  },
  (table) => [uniqueIndex('uq_harvest_grade_run_grade').on(table.harvestRunId, table.gradeCode)],
);

export const priceForecasts = sqliteTable(
  'price_forecasts',
  {
    id: text('id').primaryKey(),
    cropCode: text('crop_code').notNull().references(() => cropTypes.code, { onDelete: 'cascade' }),
    cultivarCode: text('cultivar_code').references(() => cultivars.code, { onDelete: 'set null' }),
    gradeCode: text('grade_code').notNull(),
    targetDate: text('target_date').notNull(),
    horizonDays: integer('horizon_days').notNull(),
    modelName: text('model_name').notNull(),
    modelVersion: text('model_version').notNull(),
    priceP10PerKg: real('price_p10_per_kg').notNull(),
    priceP50PerKg: real('price_p50_per_kg').notNull(),
    priceP90PerKg: real('price_p90_per_kg').notNull(),
    featureSnapshotJson: text('feature_snapshot_json').notNull().default('{}'),
    status: text('status').notNull(),
    generatedAt: text('generated_at').notNull(),
  },
  (table) => [
    index('idx_price_forecasts_series_target').on(table.cropCode, table.cultivarCode, table.gradeCode, table.targetDate),
  ],
);

export const revenueForecasts = sqliteTable(
  'revenue_forecasts',
  {
    id: text('id').primaryKey(),
    harvestRunId: text('harvest_run_id').notNull().references(() => harvestRuns.id, { onDelete: 'cascade' }),
    gradeBreakdownJson: text('grade_breakdown_json').notNull(),
    estimatedGrossWon: real('estimated_gross_won').notNull(),
    estimatedCostWon: real('estimated_cost_won').notNull().default(0),
    estimatedNetWon: real('estimated_net_won').notNull(),
    revenueP10Won: real('revenue_p10_won'),
    revenueP90Won: real('revenue_p90_won'),
    priceBasisDate: text('price_basis_date').notNull(),
    priceModelName: text('price_model_name').notNull(),
    priceModelVersion: text('price_model_version').notNull(),
    status: text('status').notNull(),
    generatedAt: text('generated_at').notNull(),
  },
  (table) => [
    uniqueIndex('uq_revenue_forecasts_harvest_run').on(table.harvestRunId),
    index('idx_revenue_forecasts_status_generated').on(table.status, table.generatedAt),
  ],
);

export const forecastJobs = sqliteTable(
  'forecast_jobs',
  {
    id: text('id').primaryKey(),
    harvestRunId: text('harvest_run_id').notNull().references(() => harvestRuns.id, { onDelete: 'cascade' }),
    jobType: text('job_type').notNull(),
    status: text('status').notNull(),
    attempts: integer('attempts').notNull().default(0),
    lastError: text('last_error'),
    createdAt: text('created_at').notNull(),
    updatedAt: text('updated_at').notNull(),
  },
  (table) => [
    uniqueIndex('uq_forecast_jobs_run_type').on(table.harvestRunId, table.jobType),
    index('idx_forecast_jobs_status_created').on(table.status, table.createdAt),
  ],
);

export const forecastModelRegistry = sqliteTable(
  'forecast_model_registry',
  {
    id: text('id').primaryKey(),
    modelName: text('model_name').notNull(),
    modelVersion: text('model_version').notNull(),
    algorithm: text('algorithm').notNull(),
    status: text('status').notNull(),
    trainingStartedAt: text('training_started_at'),
    trainingEndedAt: text('training_ended_at'),
    metricsJson: text('metrics_json').notNull().default('{}'),
    artifactUri: text('artifact_uri'),
    deployedAt: text('deployed_at'),
    createdAt: text('created_at').notNull(),
  },
  (table) => [
    uniqueIndex('uq_forecast_model_name_version').on(table.modelName, table.modelVersion),
    index('idx_forecast_model_status').on(table.status, table.deployedAt),
  ],
);

export const farmRevenueSettings = sqliteTable(
  'farm_revenue_settings',
  {
    id: text('id').primaryKey(),
    farmId: text('farm_id').notNull().references(() => farms.id, { onDelete: 'cascade' }),
    itemId: text('item_id').notNull().references(() => farmItems.id, { onDelete: 'cascade' }),
    commissionRate: real('commission_rate').notNull().default(0),
    packagingWonPerKg: real('packaging_won_per_kg').notNull().default(0),
    laborWonPerKg: real('labor_won_per_kg').notNull().default(0),
    shippingWonPerKg: real('shipping_won_per_kg').notNull().default(0),
    status: text('status').notNull().default('ACTIVE'),
    updatedAt: text('updated_at').notNull(),
  },
  (table) => [
    uniqueIndex('uq_farm_revenue_settings_item').on(table.farmId, table.itemId),
    index('idx_farm_revenue_settings_status').on(table.farmId, table.status),
  ],
);

export const captureAssets = sqliteTable(
  'capture_assets',
  {
    id: text('id').primaryKey(),
    captureSessionId: text('capture_session_id').notNull().references(() => captureSessions.id, { onDelete: 'cascade' }),
    modality: text('modality').notNull(),
    objectKey: text('object_key').notNull().unique(),
    originalName: text('original_name').notNull(),
    contentType: text('content_type').notNull(),
    sizeBytes: integer('size_bytes').notNull(),
    createdAt: text('created_at').notNull(),
  },
  (table) => [index('idx_capture_assets_session').on(table.captureSessionId, table.modality)],
);

export const videoAssets = sqliteTable(
  'video_assets',
  {
    id: text('id').primaryKey(),
    captureSessionId: text('capture_session_id').notNull().references(() => captureSessions.id, { onDelete: 'cascade' }),
    cameraId: text('camera_id').references(() => cameras.id, { onDelete: 'set null' }),
    modality: text('modality').notNull(),
    objectKey: text('object_key').unique(),
    originalName: text('original_name'),
    sourceUri: text('source_uri'),
    durationMs: integer('duration_ms'),
    frameRate: real('frame_rate'),
    frameCount: integer('frame_count'),
    processingStatus: text('processing_status').notNull(),
    createdAt: text('created_at').notNull(),
  },
  (table) => [index('idx_video_assets_session').on(table.captureSessionId, table.modality)],
);

export const frames = sqliteTable(
  'frames',
  {
    id: text('id').primaryKey(),
    videoAssetId: text('video_asset_id').notNull().references(() => videoAssets.id, { onDelete: 'cascade' }),
    captureSessionId: text('capture_session_id').notNull().references(() => captureSessions.id, { onDelete: 'cascade' }),
    frameIndex: integer('frame_index').notNull(),
    timestampMs: integer('timestamp_ms').notNull(),
    objectKey: text('object_key').unique(),
    qualityScore: real('quality_score'),
    processingStatus: text('processing_status').notNull(),
    createdAt: text('created_at').notNull(),
  },
  (table) => [
    uniqueIndex('uq_frames_video_index').on(table.videoAssetId, table.frameIndex),
    index('idx_frames_session_time').on(table.captureSessionId, table.timestampMs),
  ],
);

export const frameLocationAssignments = sqliteTable(
  'frame_location_assignments',
  {
    frameId: text('frame_id').primaryKey().references(() => frames.id, { onDelete: 'cascade' }),
    farmId: text('farm_id').notNull().references(() => farms.id, { onDelete: 'cascade' }),
    houseId: text('house_id').references(() => houses.id, { onDelete: 'set null' }),
    bedId: text('bed_id').references(() => beds.id, { onDelete: 'set null' }),
    zoneId: text('zone_id').references(() => zones.id, { onDelete: 'set null' }),
    source: text('source').notNull().default('MANUAL_CORRECTION'),
    confidence: real('confidence'),
    createdAt: text('created_at').notNull(),
    updatedAt: text('updated_at').notNull(),
  },
  (table) => [
    index('idx_frame_location_assignments_farm').on(table.farmId, table.frameId),
    check('ck_frame_location_assignments_source', sql`${table.source} in ('ROBOT_TELEMETRY', 'MANUAL_CORRECTION', 'MODEL_ESTIMATE')`),
    check('ck_frame_location_assignments_confidence', sql`${table.confidence} is null or (${table.confidence} >= 0 and ${table.confidence} <= 1)`),
  ],
);

export const inferenceRuns = sqliteTable(
  'inference_runs',
  {
    id: text('id').primaryKey(),
    captureSessionId: text('capture_session_id').notNull().references(() => captureSessions.id, { onDelete: 'cascade' }),
    task: text('task').notNull(),
    modelVersion: text('model_version').notNull(),
    status: text('status').notNull(),
    startedAt: text('started_at').notNull(),
    finishedAt: text('finished_at'),
    createdAt: text('created_at').notNull(),
  },
  (table) => [index('idx_inference_runs_session_task').on(table.captureSessionId, table.task)],
);

export const framePredictions = sqliteTable(
  'frame_predictions',
  {
    id: text('id').primaryKey(),
    inferenceRunId: text('inference_run_id').notNull().references(() => inferenceRuns.id, { onDelete: 'cascade' }),
    frameId: text('frame_id').notNull().references(() => frames.id, { onDelete: 'cascade' }),
    trackId: text('track_id'),
    classLabel: text('class_label').notNull(),
    confidence: real('confidence'),
    decisionStatus: text('decision_status').notNull(),
    resultJson: text('result_json').notNull().default('{}'),
    createdAt: text('created_at').notNull(),
  },
  (table) => [
    index('idx_frame_predictions_run').on(table.inferenceRunId, table.frameId),
    index('idx_frame_predictions_frame_created').on(table.frameId, table.createdAt),
    index('idx_frame_predictions_track').on(table.trackId, table.createdAt),
  ],
);

export const predictionReviewEvents = sqliteTable(
  'prediction_review_events',
  {
    id: text('id').primaryKey(),
    farmId: text('farm_id').notNull().references(() => farms.id, { onDelete: 'cascade' }),
    framePredictionId: text('frame_prediction_id').notNull().references(() => framePredictions.id, { onDelete: 'cascade' }),
    reviewerMemberId: text('reviewer_member_id').references(() => farmMembers.id, { onDelete: 'set null' }),
    reviewerNameSnapshot: text('reviewer_name_snapshot').notNull(),
    reviewerRoleSnapshot: text('reviewer_role_snapshot').notNull(),
    verdict: text('verdict').notNull(),
    quickNoteCode: text('quick_note_code'),
    note: text('note').notNull().default(''),
    noteLanguage: text('note_language').notNull().default('ko'),
    createdAt: text('created_at').notNull(),
  },
  (table) => [
    index('idx_prediction_reviews_prediction_created').on(table.framePredictionId, table.createdAt),
    index('idx_prediction_reviews_farm_created').on(table.farmId, table.createdAt),
  ],
);

export const miteRecordNotes = sqliteTable(
  'mite_record_notes',
  {
    id: text('id').primaryKey(),
    farmId: text('farm_id').notNull().references(() => farms.id, { onDelete: 'cascade' }),
    captureSessionId: text('capture_session_id').notNull().references(() => captureSessions.id, { onDelete: 'cascade' }),
    trackKey: text('track_key').notNull(),
    targetFrameId: text('target_frame_id').references(() => frames.id, { onDelete: 'set null' }),
    evidenceFramePredictionId: text('evidence_frame_prediction_id').references(() => framePredictions.id, { onDelete: 'set null' }),
    parentNoteId: text('parent_note_id'),
    authorMemberId: text('author_member_id').references(() => farmMembers.id, { onDelete: 'set null' }),
    authorNameSnapshot: text('author_name_snapshot').notNull(),
    authorRoleSnapshot: text('author_role_snapshot').notNull(),
    authorAccountSnapshot: text('author_account_snapshot').notNull().default(''),
    language: text('language').notNull().default('ko'),
    content: text('content').notNull(),
    status: text('status').notNull().default('ACTIVE'),
    createdAt: text('created_at').notNull(),
    updatedAt: text('updated_at').notNull(),
  },
  (table) => [
    index('idx_mite_record_notes_case_status_created').on(table.captureSessionId, table.trackKey, table.status, table.createdAt),
    index('idx_mite_record_notes_frame_status_created').on(table.captureSessionId, table.targetFrameId, table.status, table.createdAt),
    index('idx_mite_record_notes_parent_status_created').on(table.parentNoteId, table.status, table.createdAt),
    index('idx_mite_record_notes_farm_status_created').on(table.farmId, table.status, table.createdAt),
  ],
);

export const miteRecordNoteTranslations = sqliteTable(
  'mite_record_note_translations',
  {
    id: text('id').primaryKey(),
    noteId: text('note_id').notNull().references(() => miteRecordNotes.id, { onDelete: 'cascade' }),
    sourceLanguage: text('source_language').notNull(),
    detectedSourceLanguage: text('detected_source_language'),
    targetLanguage: text('target_language').notNull(),
    sourceUpdatedAt: text('source_updated_at').notNull(),
    translatedContent: text('translated_content').notNull(),
    provider: text('provider').notNull().default('GOOGLE_TRANSLATE_V2'),
    modelVersion: text('model_version').notNull().default('nmt'),
    createdAt: text('created_at').notNull(),
    updatedAt: text('updated_at').notNull(),
  },
  (table) => [
    uniqueIndex('uq_mite_record_note_translations_target').on(table.noteId, table.targetLanguage),
    index('idx_mite_record_note_translations_note_source').on(table.noteId, table.sourceUpdatedAt),
    check('ck_mite_record_note_translations_target', sql`${table.targetLanguage} in ('ko', 'vi', 'th', 'zh-CN')`),
  ],
);

export const phoneVerificationChallenges = sqliteTable(
  'phone_verification_challenges',
  {
    id: text('id').primaryKey(),
    farmId: text('farm_id').notNull().references(() => farms.id, { onDelete: 'cascade' }),
    memberId: text('member_id').references(() => farmMembers.id, { onDelete: 'cascade' }),
    phone: text('phone').notNull(),
    codeHash: text('code_hash').notNull(),
    expiresAt: text('expires_at').notNull(),
    attempts: integer('attempts').notNull().default(0),
    consumedAt: text('consumed_at'),
    createdAt: text('created_at').notNull(),
  },
  (table) => [
    index('idx_phone_challenges_member_created').on(table.memberId, table.createdAt),
    index('idx_phone_challenges_expires').on(table.expiresAt),
  ],
);

export const notificationOutbox = sqliteTable(
  'notification_outbox',
  {
    id: text('id').primaryKey(),
    farmId: text('farm_id').notNull().references(() => farms.id, { onDelete: 'cascade' }),
    framePredictionId: text('frame_prediction_id').references(() => framePredictions.id, { onDelete: 'cascade' }),
    recipientMemberId: text('recipient_member_id').references(() => farmMembers.id, { onDelete: 'set null' }),
    recipientPhone: text('recipient_phone').notNull(),
    notificationType: text('notification_type').notNull(),
    payloadJson: text('payload_json').notNull().default('{}'),
    status: text('status').notNull(),
    attempts: integer('attempts').notNull().default(0),
    lastError: text('last_error'),
    claimedAt: text('claimed_at'),
    createdAt: text('created_at').notNull(),
    sentAt: text('sent_at'),
  },
  (table) => [
    index('idx_notification_outbox_status_created').on(table.status, table.createdAt),
    index('idx_notification_outbox_farm_created').on(table.farmId, table.createdAt),
  ],
);

export const configSources = sqliteTable(
  'config_sources',
  {
    id: text('id').primaryKey(),
    farmId: text('farm_id').references(() => farms.id, { onDelete: 'cascade' }),
    sourceType: text('source_type').notNull(),
    spreadsheetId: text('spreadsheet_id'),
    sheetGid: text('sheet_gid'),
    accessMode: text('access_mode').notNull().default('READ_ONLY'),
    mappingJson: text('mapping_json').notNull().default('{}'),
    status: text('status').notNull(),
    lastImportedAt: text('last_imported_at'),
    createdAt: text('created_at').notNull(),
    updatedAt: text('updated_at').notNull(),
  },
  (table) => [index('idx_config_sources_farm').on(table.farmId, table.status)],
);

export const configImportRuns = sqliteTable(
  'config_import_runs',
  {
    id: text('id').primaryKey(),
    sourceId: text('source_id').notNull().references(() => configSources.id, { onDelete: 'cascade' }),
    status: text('status').notNull(),
    rowsRead: integer('rows_read').notNull().default(0),
    rowsCreated: integer('rows_created').notNull().default(0),
    rowsUpdated: integer('rows_updated').notNull().default(0),
    rowsRejected: integer('rows_rejected').notNull().default(0),
    checksum: text('checksum'),
    errorSummary: text('error_summary'),
    startedAt: text('started_at').notNull(),
    finishedAt: text('finished_at'),
  },
  (table) => [index('idx_config_import_runs_source').on(table.sourceId, table.startedAt)],
);

// 기존 수집 자료를 세션 구조로 이관할 때까지 보존하는 호환 테이블입니다.
export const fruitAssessments = sqliteTable(
  'fruit_assessments',
  {
    id: text('id').primaryKey(),
    farmId: text('farm_id').references(() => farms.id, { onDelete: 'set null' }),
    captureSessionId: text('capture_session_id').references(() => captureSessions.id, { onDelete: 'set null' }),
    cultivar: text('cultivar').notNull(),
    sourceType: text('source_type').notNull().default('PERSONAL_CAPTURE'),
    captureAt: text('capture_at'),
    objectKey: text('object_key').notNull().unique(),
    originalName: text('original_name').notNull(),
    gradePrediction: text('grade_prediction'),
    ripenessPrediction: text('ripeness_prediction'),
    confidence: real('confidence'),
    decisionStatus: text('decision_status').notNull(),
    processingStatus: text('processing_status').notNull(),
    createdAt: text('created_at').notNull(),
  },
  (table) => [
    index('idx_fruit_assessments_created').on(table.createdAt),
    index('idx_fruit_assessments_farm_capture').on(table.farmId, table.captureAt),
  ],
);

export const observations = sqliteTable(
  'observations',
  {
    id: text('id').primaryKey(), farmId: text('farm_id').notNull(), houseId: text('house_id').notNull(),
    bedId: text('bed_id').notNull(), zoneId: text('zone_id').notNull(), plantId: text('plant_id'), leafId: text('leaf_id'),
    cultivar: text('cultivar').notNull(), pestSpecies: text('pest_species').notNull(), captureAt: text('capture_at').notNull(),
    visualSymptomStatus: text('visual_symptom_status').notNull(), activePestStatus: text('active_pest_status').notNull(),
    decisionStatus: text('decision_status').notNull(), environmentStatus: text('environment_status').notNull(),
    processingStatus: text('processing_status').notNull(), captureMethod: text('capture_method').notNull().default('PAIRED_STILL'),
    pairingId: text('pairing_id').notNull().default('LEGACY'), sourceVideoId: text('source_video_id'),
    rgbFrameIndex: integer('rgb_frame_index'), thermalFrameIndex: integer('thermal_frame_index'), createdAt: text('created_at').notNull(),
  },
  (table) => [
    index('idx_observations_zone_capture').on(table.farmId, table.houseId, table.bedId, table.zoneId, table.captureAt),
    index('idx_observations_processing').on(table.processingStatus, table.createdAt),
  ],
);

export const assets = sqliteTable(
  'assets',
  {
    id: text('id').primaryKey(),
    observationId: text('observation_id').notNull().references(() => observations.id, { onDelete: 'cascade' }),
    modality: text('modality').notNull(), objectKey: text('object_key').notNull().unique(), originalName: text('original_name').notNull(),
    contentType: text('content_type').notNull(), sizeBytes: integer('size_bytes').notNull(), createdAt: text('created_at').notNull(),
  },
  (table) => [index('idx_assets_observation').on(table.observationId)],
);
