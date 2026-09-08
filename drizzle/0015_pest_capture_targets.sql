-- Selected observation target; NULL preserves legacy and fruit-only captures.
ALTER TABLE `capture_sessions` ADD `pest_code` text;
