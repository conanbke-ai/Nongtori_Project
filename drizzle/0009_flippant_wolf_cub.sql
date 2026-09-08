CREATE INDEX IF NOT EXISTS `idx_frame_predictions_frame_created`
ON `frame_predictions` (`frame_id`,`created_at`);
